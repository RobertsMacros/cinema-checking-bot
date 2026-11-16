"""Main entry point for the cinema digest."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cinema_digest import considering
from cinema_digest.config import RUN_TIME_BUDGET_SECONDS, SEND_RESERVE_SECONDS, Config
from cinema_digest.emailer import build_subject, send_digest
from cinema_digest.enrich import enrich_films
from cinema_digest.filters import filter_screenings
from cinema_digest.formatter import digest_warning, format_digest, format_digest_html
from cinema_digest.models import Film, ScrapeResult
from cinema_digest.ph_scraper import loose_key, parse_ph_listings
from cinema_digest.scraper import scrape_all

logger = logging.getLogger("cinema_digest")

LONDON_TZ = ZoneInfo("Europe/London")

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


def enrichment_notes(films: list[Film], omdb_problems: list[str]) -> list[str]:
    """Notes explaining missing or unfinished scores after enrich_films()."""
    notes = []
    if all(f.scores is None or f.scores.imdb is None for f in films):
        reason = "; ".join(omdb_problems) or "no film matched on OMDb or IMDb"
        logger.warning("No IMDb scores this run: %s", reason)
        notes.append(f"IMDb scores unavailable this week ({reason}).")
    incomplete = sum(1 for f in films if f.scores_incomplete)
    if incomplete:
        notes.append(
            f"Scores for {incomplete} film(s) could not be fetched within the time limit."
        )
    return notes


def subject_flag(films: list[Film], listings_suspect: bool) -> str | None:
    """The "[CHECK: ...]" tag for the email subject, if the listings look wrong."""
    if not films:
        return SUBJECT_FLAG_BROKEN
    if digest_warning(films, listings_suspect):
        return SUBJECT_FLAG_INCOMPLETE
    return None


def listings_check(scraped: ScrapeResult, digest: list[Film], now: datetime | None = None) -> dict:
    """Compare the digest with what the Picturehouse pages showed this run.

    For each cinema page that was read: how many films it listed, which of
    them have a showing in the digest's windows (evenings, weekends, next 7
    days), and which of those are missing from the digest (should be none).
    """
    now = now or datetime.now(LONDON_TZ)
    cinemas: dict[str, dict] = {}
    for cinema, html in scraped.pages.items():
        page_films = parse_ph_listings(html, cinema)
        qualifying = sorted(f.title for f in filter_screenings(page_films, now=now))
        in_digest = {
            loose_key(f.title) for f in digest if any(s.cinema == cinema for s in f.screenings)
        }
        cinemas[cinema] = {
            "films_on_page": len(page_films),
            "qualifying_on_page": qualifying,
            "missing_from_digest": [t for t in qualifying if loose_key(t) not in in_digest],
        }
    return {
        "checked_at": now.isoformat(),
        "sources": list(scraped.sources),
        "listings_suspect": scraped.listings_suspect,
        "warnings": list(scraped.warnings),
        "digest_films": len(digest),
        "cinemas": cinemas,
    }


def write_report(
    directory: Path, scraped: ScrapeResult, digest: list[Film], body: str, html_body: str, subject: str
) -> None:
    """Save what this run produced, so its output can be checked afterwards.

    Nothing private goes in: the listings are public and email addresses are
    not included (the GitHub artefact is visible to anyone who can see the repo).
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "digest.txt").write_text(body, encoding="utf-8")
    (directory / "digest.html").write_text(html_body, encoding="utf-8")
    for cinema, html in scraped.pages.items():
        (directory / f"picturehouse-{cinema}.html").write_text(html, encoding="utf-8")
    check = listings_check(scraped, digest)
    check["subject"] = subject
    (directory / "listings_check.json").write_text(json.dumps(check, indent=2), encoding="utf-8")
    logger.info("Run report written to %s", directory)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger("cinema_digest")
    root.setLevel(level)
    # Safe to call more than once (the web app sets it up on import too).
    if any(isinstance(f, RedactingFilter) for h in root.handlers for f in h.filters):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    handler.addFilter(RedactingFilter())
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
    parser.add_argument(
        "--report",
        metavar="DIR",
        help="Save the digest, the Picturehouse pages and a listings check (JSON) in DIR",
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

    # 2b. Flag films on What's On's Wait and see list
    flagged = considering.mark(filtered, considering.load())
    if flagged:
        logger.info("Flagged %d film(s) from the Wait and see list", flagged)

    # 3. Enrich within the remaining time budget
    if filtered:
        remaining = RUN_TIME_BUDGET_SECONDS - (time.monotonic() - started) - SEND_RESERVE_SECONDS
        omdb_problems = enrich_films(
            filtered,
            config.omdb_api_key,
            tmdb_api_key=config.tmdb_api_key,
            time_budget=max(0.0, remaining),
        ) or []
        notes.extend(enrichment_notes(filtered, omdb_problems))

    # 4. Format
    flag = subject_flag(filtered, scraped.listings_suspect)

    body = format_digest(
        filtered, notes=notes, listings_suspect=scraped.listings_suspect, sources=scraped.sources
    )
    html_body = format_digest_html(
        filtered, notes=notes, listings_suspect=scraped.listings_suspect, sources=scraped.sources
    )

    if args.report:
        try:
            write_report(Path(args.report), scraped, filtered, body, html_body, build_subject(flag))
        except Exception:
            logger.exception("Could not write the run report")

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
            subject_flag=flag,
        )
    except Exception:
        logger.exception("Failed to send digest")
        sys.exit(1)

    logger.info("Done in %.0fs", time.monotonic() - started)


if __name__ == "__main__":
    main()
