"""Main entry point for the cinema digest."""

from __future__ import annotations

import argparse
import logging
import sys

from cinema_digest.config import Config
from cinema_digest.emailer import send_digest
from cinema_digest.enrich import enrich_films
from cinema_digest.filters import filter_screenings
from cinema_digest.formatter import format_digest, format_digest_html
from cinema_digest.scraper import ScraperError, scrape_all

logger = logging.getLogger("cinema_digest")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    root = logging.getLogger("cinema_digest")
    root.setLevel(level)
    root.addHandler(handler)


def main() -> None:
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

    # 1. Scrape
    logger.info("Starting cinema digest")
    try:
        films = scrape_all()
    except ScraperError as e:
        logger.error("Scraping failed: %s", e)
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected error during scraping")
        sys.exit(1)

    logger.info("Scraped %d unique films", len(films))

    # 2. Filter
    filtered = filter_screenings(films)
    if not filtered:
        logger.warning("No films have qualifying screenings this week")

    # 3. Enrich (even if empty, this is a no-op)
    if filtered:
        enrich_films(filtered, config.omdb_api_key)

    # 4. Format
    body = format_digest(filtered)
    html_body = format_digest_html(filtered)

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
        )
    except Exception:
        logger.exception("Failed to send digest")
        sys.exit(1)

    logger.info("Done")


if __name__ == "__main__":
    main()
