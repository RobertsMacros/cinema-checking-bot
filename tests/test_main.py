"""Tests for the main entry point: the digest is always sent."""

import logging
import sys
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import cinema_digest.main as main_module
from cinema_digest.models import Film, Scores, ScrapeResult, Screening

LONDON_TZ = ZoneInfo("Europe/London")


def _run_main(monkeypatch, scraped, omdb_problems=None):
    """Run main() with scraping, enrichment and sending mocked out.

    scraped is the ScrapeResult to return, or an exception for scrape_all to raise.
    """
    monkeypatch.setattr(sys, "argv", ["cinema_digest", "--dry-run"])
    monkeypatch.setattr(main_module, "setup_logging", lambda verbose=False: None)
    if isinstance(scraped, Exception):
        scrape_patch = patch.object(main_module, "scrape_all", side_effect=scraped)
    else:
        scrape_patch = patch.object(main_module, "scrape_all", return_value=scraped)
    with scrape_patch, patch.object(main_module, "enrich_films", return_value=omdb_problems or []) as enrich, \
            patch.object(main_module, "send_digest") as send:
        main_module.main()
    return enrich, send


def _upcoming_film(title="Soon"):
    when = datetime.now(LONDON_TZ).replace(hour=19, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return Film(title=title, screenings=[Screening("Ritzy", when, "u")], scores=Scores())


class TestMainAlwaysSends:
    def test_no_screenings_sends_flagged_warning(self, monkeypatch):
        scraped = ScrapeResult(films=[Film(title=f"Film {i}") for i in range(5)])
        _, send = _run_main(monkeypatch, scraped)
        send.assert_called_once()
        body, html = send.call_args.args
        assert "listings page may have changed" in body
        assert "listings page may have changed" in html
        assert "No qualifying screenings" not in body
        assert "Parsed 5 film(s) and 0 screening(s)" in body
        assert send.call_args.kwargs["subject_flag"] == main_module.SUBJECT_FLAG_BROKEN

    def test_scraper_crash_still_sends(self, monkeypatch):
        _, send = _run_main(monkeypatch, RuntimeError("boom"))
        send.assert_called_once()
        body = send.call_args.args[0]
        assert "Scraping failed with an unexpected error (RuntimeError)" in body
        assert send.call_args.kwargs["subject_flag"] == main_module.SUBJECT_FLAG_BROKEN

    def test_healthy_run_not_flagged(self, monkeypatch):
        enrich, send = _run_main(monkeypatch, ScrapeResult(films=[_upcoming_film()]))
        enrich.assert_called_once()
        assert enrich.call_args.kwargs["time_budget"] > 0
        assert send.call_args.kwargs["subject_flag"] is None
        assert "Soon" in send.call_args.args[0]

    def test_partial_failure_flagged_incomplete(self, monkeypatch):
        scraped = ScrapeResult(
            films=[_upcoming_film()],
            warnings=["Could not fetch the Clapham listings (ConnectionError)."],
            listings_suspect=True,
        )
        _, send = _run_main(monkeypatch, scraped)
        body = send.call_args.args[0]
        assert "Could not fetch the Clapham listings" in body
        assert send.call_args.kwargs["subject_flag"] == main_module.SUBJECT_FLAG_INCOMPLETE


class TestMissingImdbExplained:
    def test_no_imdb_scores_adds_reason(self, monkeypatch):
        _, send = _run_main(monkeypatch, ScrapeResult(films=[_upcoming_film()]),
                            omdb_problems=["OMDb said: Request limit reached!"])
        body, html = send.call_args.args
        assert "IMDb scores unavailable this week (OMDb said: Request limit reached!)" in body
        assert "IMDb scores unavailable this week" in html

    def test_imdb_present_no_note(self, monkeypatch):
        film = _upcoming_film()
        film.scores = Scores(imdb=7.3)
        _, send = _run_main(monkeypatch, ScrapeResult(films=[film]))
        assert "IMDb scores unavailable" not in send.call_args.args[0]


class TestRedaction:
    def test_redact_hides_api_keys(self):
        text = "401 Client Error for url: https://www.omdbapi.com/?apikey=SECRET123&t=Film&api_key=TMDBKEY"
        redacted = main_module.redact(text)
        assert "SECRET123" not in redacted and "TMDBKEY" not in redacted
        assert "apikey=***" in redacted and "t=Film" in redacted

    def test_filter_redacts_messages_and_tracebacks(self, capsys):
        logger = logging.getLogger("cinema_digest.test_redaction")
        handler = logging.StreamHandler(sys.stderr)
        handler.addFilter(main_module.RedactingFilter())
        logger.addHandler(handler)
        try:
            try:
                raise ValueError("bad url https://www.omdbapi.com/?apikey=SECRET123&t=x")
            except ValueError:
                logger.exception("Failed for %s", "https://x/?apikey=SECRET456")
        finally:
            logger.removeHandler(handler)
        err = capsys.readouterr().err
        assert "SECRET123" not in err and "SECRET456" not in err
        assert "ValueError" in err
