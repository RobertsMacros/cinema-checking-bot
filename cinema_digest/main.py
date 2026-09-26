"""Main entry point for the cinema digest."""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time

from cinema_digest.config import RUN_TIME_BUDGET_SECONDS, SEND_RESERVE_SECONDS, Config
from cinema_digest.emailer import send_digest
from cinema_digest.enrich import enrich_films
from cinema_digest.filters import filter_screenings
from cinema_digest.formatter import digest_warning, format_digest, format_digest_html
from cinema_digest.models import ScrapeResult
from cinema_digest.scraper import scrape_all

logger = logging.getLogger("cinema_digest")

SUBJECT_FLAG_BROKEN = "CHECK: listings page may have changed"
SUBJECT_FLAG_INCOMPLETE = "CHECK: listings incomplete"

_SECRET_PARAM = re.compile(r"((?:api_?key|apikey|token|password)=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: str) -> str:
    """Hide API keys and similar values in URLs (e.g. ?apikey=...)."""
    return _SECRET_PARAM.sub(r"\1***", text)


class RedactingFilter(logging.Filter):
    """Redact secrets from log messages and tracebacks.

    OMDb and TMDB take their keys as query parameters, and requests puts the
    full URL into HTTP error messages.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    handler.addFilter(RedactingFilter())
    root = logging.getLogger("cinema_digest")
    root.setLevel(level)
    root.addHandler(handler)


def main() -> None:
    started = time.monotonic()
    parser = argparse.ArgumentParser(description="Cinema digest email sender")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest to stdout instead of emailing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)
    config = Config.from_env()
    dry_run = args.dry_run or config.dry_run

    # 1. Scrape. Never abort here: whatever happens, a digest is sent and any
    # problem is flagged in it.
    logger.info("Starting cinema digest")
    try:
        scraped = scrape_all()
    except Exception as e:
        logger.exception("Unexpected error during scraping")
        scraped = ScrapeResult(
            warnings=[f"Scraping failed with an unexpected error ({type(e).__name__})."],
            listings_suspect=True,
        )

    logger.info("Scraped %d unique films", len(scraped.films))
    notes = list(scraped.warnings)

    # 2. Filter
    filtered = filter_screenings(scraped.films)
    if not filtered:
        total_screenings = sum(len(f.screenings) for f in scraped.films)
        logger.warning(
            "No qualifying screenings (%d films, %d screenings parsed)",
            len(scraped.films),
            total_screenings,
        )
        notes.append(
            f"Parsed {len(scraped.films)} film(s) and {total_screenings} screening(s) in total; "
            f"none fell in the next 7 days' viewing windows."
        )

    # 3. Enrich within the remaining time budget
    if filtered:
        remaining = RUN_TIME_BUDGET_SECONDS - (time.monotonic() - started) - SEND_RESERVE_SECONDS
        omdb_problems = enrich_films(
            filtered,
            config.omdb_api_key,
            tmdb_api_key=config.tmdb_api_key,
            time_budget=max(0.0, remaining),
        ) or []
        if all(f.scores is None or f.scores.imdb is None for f in filtered):
            reason = "; ".join(omdb_problems) or "no film matched on OMDb or IMDb"
            logger.warning("No IMDb scores this run: %s", reason)
            notes.append(f"IMDb scores unavailable this week ({reason}).")
        incomplete = sum(1 for f in filtered if f.scores_incomplete)
        if incomplete:
            notes.append(
                f"Scores for {incomplete} film(s) could not be fetched within the time limit."
            )

    # 4. Format
    warning = digest_warning(filtered, scraped.listings_suspect)
    subject_flag = None
    if not filtered:
        subject_flag = SUBJECT_FLAG_BROKEN
    elif warning:
        subject_flag = SUBJECT_FLAG_INCOMPLETE

    body = format_digest(filtered, notes=notes, listings_suspect=scraped.listings_suspect)
    html_body = format_digest_html(filtered, notes=notes, listings_suspect=scraped.listings_suspect)

    # 5. Send
    try:
        send_digest(
            body,
            html_body,
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=config.smtp_password,
            from_addr=config.email_from,
            to_addrs=config.email_to,
            dry_run=dry_run,
            subject_flag=subject_flag,
        )
    except Exception:
        logger.exception("Failed to send digest")
        sys.exit(1)

    logger.info("Done in %.0fs", time.monotonic() - started)


if __name__ == "__main__":
    main()
