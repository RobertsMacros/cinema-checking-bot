"""Incomplete listings must be flagged in the subject, and each run must be
able to show that every film on the Picturehouse pages made it into the digest."""

import json
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import cinema_digest.main as main_module
from cinema_digest import run_check
from cinema_digest.config import MIN_FILMS_PER_CINEMA
from cinema_digest.models import Film, Scores, ScrapeResult, Screening
from cinema_digest.scraper import scrape_all

LONDON = ZoneInfo("Europe/London")
FIXTURE = (Path(__file__).parent / "fixtures" / "ph_clapham.html").read_text()
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=LONDON)


def _dt_films(n: int, cinema: str, title: str = "DT Film") -> list[Film]:
    """Data Thistle films as the parser returns them.

    These tests check how scrape_all flags and credits a week, not the Data
    Thistle parser, so they hand it parsed films instead of feeding made-up
    markup through the parser. (The parser's own tests still use hand-written
    HTML until saved pages replace it: HANDOVER F6.)
    """
    when = datetime(2026, 11, 13, 19, 0, tzinfo=LONDON)
    return [Film(title=f"{title} {i}", year=2026, screenings=[Screening(cinema, when, "u")]) for i in range(n)]


def _scrape(monkeypatch, dt_by_cinema: dict, ph_fetcher):
    monkeypatch.setattr("cinema_digest.scraper.parse_cinema",
                        lambda html, cinema, today=None: list(dt_by_cinema.get(cinema, [])))
    return scrape_all(_session("<html>dt page</html>", "<html>dt page</html>"),
                      today=date(2026, 11, 13), ph_fetcher=ph_fetcher)


def _ph_pages(urls):
    return {n: FIXTURE for n in urls}


def _session(*pages):
    session = MagicMock()
    out = []
    for p in pages:
        r = MagicMock()
        r.text = p
        r.raise_for_status = MagicMock()
        out.append(r)
    session.get.side_effect = out
    return session


def _broken(urls):
    raise RuntimeError("browser failed to start")


class TestFallbackAndLowCountsAreFlagged:
    def test_partly_loaded_picturehouse_page_flags_the_subject(self, monkeypatch):
        # The saved page has 6 films; Data Thistle adds 12 more, so the combined
        # count clears the floor, but a real page lists 60 or more: it didn't load
        dt = {c: _dt_films(12, c) for c in ("Clapham", "Ritzy")}
        result = _scrape(monkeypatch, dt, _ph_pages)
        assert len([f for f in result.films if any(s.cinema == "Clapham" for s in f.screenings)]) >= MIN_FILMS_PER_CINEMA
        assert result.listings_suspect is True
        assert any("Picturehouse page showed only 6 films" in w for w in result.warnings)

    def test_picturehouse_unreadable_flags_the_subject(self, monkeypatch):
        dt = {c: _dt_films(20, c) for c in ("Clapham", "Ritzy")}
        result = _scrape(monkeypatch, dt, _broken)
        assert result.listings_suspect is True
        assert main_module.subject_flag(result.films, result.listings_suspect) == main_module.SUBJECT_FLAG_INCOMPLETE

    def test_too_few_films_flags_the_subject(self, monkeypatch):
        dt = {"Clapham": _dt_films(4, "Clapham"), "Ritzy": _dt_films(20, "Ritzy", "Ritzy Film")}
        result = _scrape(monkeypatch, dt, None)
        assert result.listings_suspect is True
        assert any("unusually low" in w and "Clapham" in w for w in result.warnings)

    def test_sources_record_what_was_used(self, monkeypatch):
        ok = _scrape(monkeypatch, {}, _ph_pages)
        assert ok.sources == ["Picturehouse"]
        assert set(ok.pages) == {"Clapham", "Ritzy"}
        fallback = _scrape(monkeypatch, {c: _dt_films(20, c) for c in ("Clapham", "Ritzy")}, _broken)
        assert fallback.sources == ["Data Thistle"]

    def test_data_thistle_is_credited_when_it_only_adds_details(self, monkeypatch):
        # Picturehouse pages have no year or description; Data Thistle's copy of
        # the same film supplies them, so it must be named as a source
        same_showing = datetime(2026, 11, 13, 20, 30, tzinfo=LONDON)
        dt = {"Clapham": [Film(title="Wild Horse Nine", year=2026, logline="A story about horses.",
                               screenings=[Screening("Clapham", same_showing, "u")])]}
        result = _scrape(monkeypatch, dt, _ph_pages)
        film = next(f for f in result.films if f.title == "Wild Horse Nine")
        assert film.year == 2026
        assert result.sources == ["Picturehouse", "Data Thistle"]

    def test_data_thistle_pages_are_kept_for_the_run_report(self, monkeypatch):
        result = _scrape(monkeypatch, {c: _dt_films(20, c) for c in ("Clapham", "Ritzy")}, None)
        assert result.dt_pages == {"Clapham": "<html>dt page</html>", "Ritzy": "<html>dt page</html>"}

    def test_subject_flags(self):
        film = Film(title="A", screenings=[Screening("Ritzy", NOW, "u")])
        assert main_module.subject_flag([], False) == main_module.SUBJECT_FLAG_BROKEN
        assert main_module.subject_flag([film], True) == main_module.SUBJECT_FLAG_INCOMPLETE
        assert main_module.subject_flag([film], False) is None


class TestListingsCheck:
    @staticmethod
    def _scraped(monkeypatch):
        # The fixture is a trimmed page with 6 films; a real page has 60 or more
        monkeypatch.setattr("cinema_digest.scraper.MIN_FILMS_PER_CINEMA", 3)
        return scrape_all(_session("<html></html>", "<html></html>"), today=date(2026, 11, 13),
                          ph_fetcher=lambda urls: {n: FIXTURE for n in urls})

    def test_every_qualifying_picturehouse_film_is_in_the_digest(self, monkeypatch):
        from cinema_digest.filters import filter_screenings

        scraped = self._scraped(monkeypatch)
        digest = filter_screenings(scraped.films, now=NOW)
        check = main_module.listings_check(scraped, digest, now=NOW)
        for cinema in ("Clapham", "Ritzy"):
            entry = check["cinemas"][cinema]
            assert entry["films_on_page"] == 6
            assert entry["qualifying_on_page"]  # some evening or weekend showings
            assert entry["missing_from_digest"] == []
        assert run_check.problems(check) == []

    def test_a_dropped_film_is_reported(self, monkeypatch):
        from cinema_digest.filters import filter_screenings

        scraped = self._scraped(monkeypatch)
        digest = [f for f in filter_screenings(scraped.films, now=NOW) if f.title != "Wild Horse Nine"]
        check = main_module.listings_check(scraped, digest, now=NOW)
        assert check["cinemas"]["Ritzy"]["missing_from_digest"] == ["Wild Horse Nine"]
        assert any("Wild Horse Nine" in p for p in run_check.problems(check))

    def test_fallback_run_is_a_problem(self):
        check = {"listings_suspect": True, "sources": ["Data Thistle"], "warnings": ["x"], "cinemas": {}}
        problems = run_check.problems(check)
        assert any("Picturehouse" in p for p in problems)
        assert any("flagged" in p for p in problems)

    def test_run_check_exit_code(self, tmp_path):
        good = tmp_path / "good.json"
        good.write_text(json.dumps({"listings_suspect": False, "sources": ["Picturehouse"], "warnings": [],
                                    "cinemas": {"Clapham": {"missing_from_digest": []},
                                                "Ritzy": {"missing_from_digest": []}}}))
        assert run_check.main([str(good)]) == 0
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"listings_suspect": False, "sources": ["Picturehouse"], "warnings": [],
                                   "cinemas": {"Ritzy": {"missing_from_digest": ["Fjord"]}}}))
        assert run_check.main([str(bad)]) == 1


def test_main_writes_a_run_report(monkeypatch, tmp_path):
    scraped = ScrapeResult(
        films=[Film(title="Soon", screenings=[Screening("Ritzy", datetime(2099, 1, 6, 19, 0, tzinfo=LONDON), "u")],
                    scores=Scores())],
        sources=["Picturehouse"],
        pages={"Ritzy": "<html>page</html>"},
        dt_pages={"Ritzy": "<html>dt</html>"},
    )
    monkeypatch.setattr(sys, "argv", ["cinema_digest", "--dry-run", "--report", str(tmp_path / "report")])
    monkeypatch.setattr(main_module, "setup_logging", lambda verbose=False: None)
    with patch.object(main_module, "scrape_all", return_value=scraped), \
            patch.object(main_module, "enrich_films", return_value=[]), \
            patch.object(main_module, "send_digest"):
        main_module.main()
    report = tmp_path / "report"
    assert (report / "digest.html").exists() and (report / "digest.txt").exists()
    assert (report / "picturehouse-Ritzy.html").read_text() == "<html>page</html>"
    assert (report / "datathistle-Ritzy.html").read_text() == "<html>dt</html>"
    check = json.loads((report / "listings_check.json").read_text())
    assert check["sources"] == ["Picturehouse"]
    assert "subject" in check
