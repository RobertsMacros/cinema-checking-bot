"""Inputs that silently do nothing must be visible in the log and run report:
an empty Wait and see list and a missing TMDB key."""

import json
import logging
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import cinema_digest.main as main_module
from cinema_digest import considering
from cinema_digest.enrich import enrich_films
from cinema_digest.models import Film, Scores, ScrapeResult, Screening

LONDON = ZoneInfo("Europe/London")


def test_empty_wait_and_see_list_is_logged(monkeypatch, tmp_path, caplog):
    empty = tmp_path / "considering.json"
    empty.write_text("[]")
    monkeypatch.setattr(considering, "FILE", empty)
    monkeypatch.delenv("CONSIDERING", raising=False)
    with caplog.at_level(logging.INFO, logger="cinema_digest.considering"):
        assert considering.load() == []
    assert any("Wait and see list is empty" in r.getMessage() for r in caplog.records)


def test_wait_and_see_count_is_logged(caplog):
    with caplog.at_level(logging.INFO, logger="cinema_digest.considering"):
        considering.load('[{"title": "Fjord", "year": "2026"}]')
    assert any("Wait and see list: 1 film" in r.getMessage() for r in caplog.records)


def test_missing_tmdb_key_is_logged(caplog):
    session = MagicMock()
    session.get.return_value.status_code = 503
    with caplog.at_level(logging.WARNING, logger="cinema_digest.enrich"):
        enrich_films([], "omdb-key", tmdb_api_key="", session=session)
    assert any("No TMDB API key" in r.getMessage() for r in caplog.records)


def test_run_report_records_list_size_and_keys(monkeypatch, tmp_path):
    tomorrow_evening = datetime.now(LONDON).replace(hour=19, minute=0, second=0, microsecond=0) + timedelta(days=1)
    scraped = ScrapeResult(
        films=[Film(title="Soon", screenings=[Screening("Ritzy", tomorrow_evening, "u")], scores=Scores())],
        sources=["Picturehouse"],
    )
    monkeypatch.setattr(sys, "argv", ["cinema_digest", "--dry-run", "--report", str(tmp_path)])
    monkeypatch.setattr(main_module, "setup_logging", lambda verbose=False: None)
    monkeypatch.setenv("CONSIDERING", '[{"title": "Soon"}]')
    monkeypatch.setenv("OMDB_API_KEY", "x")
    monkeypatch.setenv("TMDB_API_KEY", "")
    with patch.object(main_module, "scrape_all", return_value=scraped), \
            patch.object(main_module, "enrich_films", return_value=[]), \
            patch.object(main_module, "send_digest"):
        main_module.main()
    check = json.loads((tmp_path / "listings_check.json").read_text())
    assert check["wait_and_see_entries"] == 1
    assert check["wait_and_see_matched"] == 1
    assert check["omdb_key_set"] is True
    assert check["tmdb_key_set"] is False
