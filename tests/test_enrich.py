"""Tests for score enrichment logic."""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import cinema_digest.enrich as enrich_module
from cinema_digest.enrich import (
    NEGATIVE_CACHE_TTL,
    _cache_key,
    _clean_title_for_search,
    _fetch_mc_score,
    _fetch_tmdb,
    _find_imdb_id,
    _find_rt_slug,
    _is_same_film,
    _parse_scores,
    _title_similarity,
    enrich_film,
    enrich_films,
)
from cinema_digest.models import Film, Scores, Screening

from datetime import datetime
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")

NOT_FOUND = {"Response": "False", "Error": "Movie not found!"}


def _omdb(title, year=None, metascore="70", **extra):
    data = {
        "Response": "True",
        "Title": title,
        "Metascore": metascore,
        "imdbRating": "7.0",
        "Ratings": [],
    }
    if year is not None:
        data["Year"] = str(year)
    data.update(extra)
    return data


class FakeResponse:
    def __init__(self, status_code=404, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise enrich_module.requests.HTTPError(f"{self.status_code}")


class FakeSession:
    """Offline stand-in for requests.Session: every URL is a 404 unless routed."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def _respond(self, url, **kwargs):
        self.calls.append(url)
        for prefix, response in self.routes.items():
            if url.startswith(prefix):
                return response
        return FakeResponse(404)

    def get(self, url, **kwargs):
        return self._respond(url, **kwargs)

    def post(self, url, **kwargs):
        return self._respond(url, **kwargs)


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich_module, "CACHE_DIR", tmp_path)
    return tmp_path


class TestCleanTitleForSearch:
    def test_strips_trailing_year(self):
        assert _clean_title_for_search("Film Name (2026)") == "Film Name"

    def test_strips_trailing_exclamation(self):
        assert _clean_title_for_search("The Bride!") == "The Bride"

    def test_normal_title_unchanged(self):
        assert _clean_title_for_search("The Great Gatsby") == "The Great Gatsby"

    def test_whitespace_stripped(self):
        assert _clean_title_for_search("  Film  ") == "Film"


class TestTitleSimilarity:
    def test_identical_titles(self):
        assert _title_similarity("The Great Gatsby", "The Great Gatsby") == 1.0

    def test_similar_titles(self):
        sim = _title_similarity("The Great Gatsby", "Great Gatsby")
        assert 0.8 < sim < 1.0  # articles count, so not identical

    def test_different_titles(self):
        sim = _title_similarity("The Great Gatsby", "Raging Bull")
        assert sim < 0.4

    def test_accents_and_punctuation_ignored(self):
        assert _title_similarity("Amélie!", "Amelie") == 1.0


class TestIsSameFilm:
    def test_article_only_difference_is_a_different_film(self):
        assert _is_same_film("The Drama", None, "Drama", None) is False
        assert _is_same_film("Drama", None, "The Drama", None) is False

    def test_identical_title_same_year(self):
        assert _is_same_film("Sexy Beast", 2000, "Sexy Beast", 2000) is True

    def test_year_off_by_one_accepted(self):
        # UK release year vs production year
        assert _is_same_film("Sexy Beast", 2000, "Sexy Beast", 2001) is True

    def test_remake_rejected_by_year(self):
        assert _is_same_film("The Wicker Man", 2026, "The Wicker Man", 1973) is False

    def test_unknown_year_falls_back_to_title(self):
        assert _is_same_film("The Wicker Man", None, "The Wicker Man", 1973) is True

    def test_dissimilar_title_rejected(self):
        assert _is_same_film("The Great Gatsby", 2013, "Completely Different Film", 2013) is False


class TestParseScores:
    def test_full_scores(self):
        data = {
            "Metascore": "69",
            "imdbRating": "7.2",
            "Ratings": [{"Source": "Rotten Tomatoes", "Value": "48%"}],
        }
        scores = _parse_scores(data)
        assert scores.metacritic == 69
        assert scores.imdb == 7.2
        assert scores.rotten_tomatoes == 48

    def test_missing_scores(self):
        data = {"Metascore": "N/A", "imdbRating": "N/A", "Ratings": []}
        scores = _parse_scores(data)
        assert scores.metacritic is None
        assert scores.imdb is None
        assert scores.rotten_tomatoes is None

    def test_partial_scores(self):
        data = {
            "Metascore": "85",
            "imdbRating": "N/A",
            "Ratings": [{"Source": "Rotten Tomatoes", "Value": "92%"}],
        }
        scores = _parse_scores(data)
        assert scores.metacritic == 85
        assert scores.imdb is None
        assert scores.rotten_tomatoes == 92


class TestEnrichFilm:
    def test_no_api_key_sets_empty_scores(self):
        film = Film(title="Test", screenings=[])
        enrich_film(film, api_key="")
        assert film.scores == Scores()

    @patch("cinema_digest.enrich._read_cache", return_value=None)
    @patch("cinema_digest.enrich._write_cache")
    @patch("cinema_digest.enrich.fetch_omdb")
    def test_successful_enrichment(self, mock_fetch, mock_write, mock_read):
        mock_fetch.return_value = {
            "Response": "True",
            "Title": "The Great Gatsby",
            "Metascore": "55",
            "imdbRating": "7.2",
            "Ratings": [{"Source": "Rotten Tomatoes", "Value": "48%"}],
            "Director": "Baz Luhrmann",
            "Plot": "A writer recounts his time with Jay Gatsby.",
        }
        film = Film(title="The Great Gatsby", year=2013, screenings=[])
        enrich_film(film, api_key="test_key")
        assert film.scores.metacritic == 55
        assert film.scores.imdb == 7.2
        assert film.scores.rotten_tomatoes == 48
        assert film.director == "Baz Luhrmann"

    @patch("cinema_digest.enrich._read_cache", return_value=None)
    @patch("cinema_digest.enrich._write_cache")
    @patch("cinema_digest.enrich.fetch_omdb")
    def test_title_mismatch_returns_empty(self, mock_fetch, mock_write, mock_read):
        mock_fetch.return_value = {
            "Response": "True",
            "Title": "Completely Different Film",
            "Metascore": "90",
            "imdbRating": "8.5",
            "Ratings": [],
        }
        film = Film(title="The Great Gatsby", year=2013, screenings=[])
        enrich_film(film, api_key="test_key")
        assert film.scores == Scores()

    @patch("cinema_digest.enrich._read_cache", return_value=None)
    @patch("cinema_digest.enrich._write_cache")
    @patch("cinema_digest.enrich.fetch_omdb")
    def test_not_found_retries_without_year(self, mock_fetch, mock_write, mock_read):
        mock_fetch.side_effect = [
            {"Response": "False", "Error": "Movie not found!"},
            {
                "Response": "True",
                "Title": "Test Film",
                "Metascore": "70",
                "imdbRating": "7.0",
                "Ratings": [],
            },
        ]
        film = Film(title="Test Film", year=2026, screenings=[])
        enrich_film(film, api_key="test_key")
        assert film.scores.metacritic == 70
        assert mock_fetch.call_count == 2

    @patch("cinema_digest.enrich.fetch_omdb")
    def test_cache_hit_skips_api(self, mock_fetch, cache_dir):
        data = _omdb(
            "Cached Film",
            2025,
            metascore="80",
            imdbRating="7.5",
            Ratings=[{"Source": "Rotten Tomatoes", "Value": "85%"}],
        )
        enrich_module._write_cache(_cache_key("Cached Film", 2025), data)
        film = Film(title="Cached Film", year=2025, screenings=[])
        enrich_film(film, api_key="test_key")
        mock_fetch.assert_not_called()
        assert film.scores.metacritic == 80
        assert film.scores.imdb == 7.5
        assert film.scores.rotten_tomatoes == 85

    @patch("cinema_digest.enrich._read_cache", return_value=None)
    @patch("cinema_digest.enrich._write_cache")
    @patch("cinema_digest.enrich.fetch_omdb")
    def test_remake_with_same_title_rejected(self, mock_fetch, mock_write, mock_read):
        # Year search misses; the no-year retry finds the 1973 original
        mock_fetch.side_effect = [NOT_FOUND, _omdb("The Wicker Man", 1973, metascore="89")]
        film = Film(title="The Wicker Man", year=2026, screenings=[])
        enrich_film(film, api_key="test_key")
        assert film.scores == Scores()

    @patch("cinema_digest.enrich._read_cache", return_value=None)
    @patch("cinema_digest.enrich._write_cache")
    @patch("cinema_digest.enrich.fetch_omdb")
    def test_article_only_match_rejected(self, mock_fetch, mock_write, mock_read):
        mock_fetch.return_value = _omdb("Drama", 2026, metascore="90")
        film = Film(title="The Drama", year=2026, screenings=[])
        enrich_film(film, api_key="test_key")
        assert film.scores == Scores()


class TestOmdbCache:
    def test_scores_found_by_no_year_retry_survive_a_second_run(self, cache_dir):
        with patch.object(enrich_module, "fetch_omdb", side_effect=[NOT_FOUND, _omdb("Test Film")]):
            first = Film(title="Test Film", year=2026)
            enrich_film(first, api_key="k")
        with patch.object(enrich_module, "fetch_omdb", side_effect=AssertionError("should use cache")):
            second = Film(title="Test Film", year=2026)
            enrich_film(second, api_key="k")
        assert first.scores.metacritic == 70
        assert second.scores.metacritic == 70

    def test_rejected_mismatch_never_accepted_on_later_run(self, cache_dir):
        wrong = _omdb("Completely Different Film", 2013, metascore="90")
        with patch.object(enrich_module, "fetch_omdb", return_value=wrong):
            first = Film(title="The Great Gatsby", year=2013)
            enrich_film(first, api_key="k")
            second = Film(title="The Great Gatsby", year=2013)
            enrich_film(second, api_key="k")
        assert first.scores.metacritic is None
        assert second.scores.metacritic is None

    def test_cached_entry_rechecked_against_title(self, cache_dir):
        # A cache entry that doesn't pass the title check is ignored and refetched
        key = _cache_key("The Great Gatsby", 2013)
        enrich_module._write_cache(key, _omdb("Completely Different Film", 2013, metascore="90"))
        with patch.object(enrich_module, "fetch_omdb", return_value=_omdb("The Great Gatsby", 2013, metascore="55")) as f:
            film = Film(title="The Great Gatsby", year=2013)
            enrich_film(film, api_key="k")
        assert f.called
        assert film.scores.metacritic == 55

    def test_legacy_raw_cache_files_ignored(self, cache_dir):
        # Pre-v2 cache files stored raw OMDb responses, including mismatches
        key = _cache_key("The Great Gatsby", 2013)
        (cache_dir / key).write_text(json.dumps(_omdb("Completely Different Film", metascore="90")))
        with patch.object(enrich_module, "fetch_omdb", return_value=NOT_FOUND):
            film = Film(title="The Great Gatsby", year=2013)
            enrich_film(film, api_key="k")
        assert film.scores == Scores()

    def test_not_found_is_cached_for_a_while(self, cache_dir):
        with patch.object(enrich_module, "fetch_omdb", return_value=NOT_FOUND) as f:
            enrich_film(Film(title="New Release", year=2026), api_key="k")
            calls_after_first = f.call_count
            enrich_film(Film(title="New Release", year=2026), api_key="k")
        assert calls_after_first == 2  # with year, then without
        assert f.call_count == calls_after_first  # second run served from cache

    def test_not_found_expires(self, cache_dir, monkeypatch):
        with patch.object(enrich_module, "fetch_omdb", return_value=NOT_FOUND):
            enrich_film(Film(title="New Release", year=2026), api_key="k")
        later = time.time() + NEGATIVE_CACHE_TTL + 60
        monkeypatch.setattr(enrich_module.time, "time", lambda: later)
        with patch.object(enrich_module, "fetch_omdb", return_value=_omdb("New Release", 2026)) as f:
            film = Film(title="New Release", year=2026)
            enrich_film(film, api_key="k")
        assert f.called
        assert film.scores.metacritic == 70

    def test_omdb_errors_are_not_cached(self, cache_dir):
        limit = {"Response": "False", "Error": "Request limit reached!"}
        with patch.object(enrich_module, "fetch_omdb", return_value=limit):
            enrich_film(Film(title="Busy Day", year=2026), api_key="k")
        assert list(cache_dir.iterdir()) == []

    def test_article_titles_get_separate_cache_entries(self):
        assert _cache_key("The Drama", 2026) != _cache_key("Drama", 2026)


class TestOtherSourcesCheckYear:
    def test_tmdb_skips_same_title_other_year(self):
        results = {
            "results": [
                {"id": 1, "title": "The Wicker Man", "release_date": "1973-12-06"},
                {"id": 2, "title": "The Wicker Man", "release_date": "2026-03-01"},
            ]
        }
        session = FakeSession({"https://api.themoviedb.org": FakeResponse(200, results)})
        best = _fetch_tmdb("The Wicker Man", 2026, "key", session)
        assert best["id"] == 2

    def test_imdb_suggestion_skips_same_title_other_year(self):
        payload = {"d": [
            {"id": "tt0070917", "l": "The Wicker Man", "y": 1973, "qid": "movie"},
            {"id": "tt0450345", "l": "The Wicker Man", "y": 2006, "qid": "movie"},
        ]}
        session = FakeSession({"https://v2.sg.media-imdb.com": FakeResponse(200, payload)})
        assert _find_imdb_id("The Wicker Man", 2006, session) == "tt0450345"
        assert _find_imdb_id("The Wicker Man", 2026, session) is None

    def test_metacritic_page_for_other_year_rejected(self):
        page = (
            '<script type="application/ld+json">'
            + json.dumps({"@type": "Movie", "name": "The Wicker Man", "datePublished": "1974-01-01",
                          "aggregateRating": {"ratingValue": 89}})
            + "</script>"
        )
        session = FakeSession({"https://www.metacritic.com/movie/the-wicker-man/": FakeResponse(200, text=page)})
        assert _fetch_mc_score("The Wicker Man", 2026, session) == (None, None)
        assert _fetch_mc_score("The Wicker Man", 1973, session) == (89, "the-wicker-man")

    def test_rt_search_uses_release_year(self):
        page = """
        <search-page-media-row release-year="1973"><a href="https://www.rottentomatoes.com/m/the_wicker_man">The Wicker Man</a></search-page-media-row>
        <search-page-media-row release-year="2026"><a href="https://www.rottentomatoes.com/m/the_wicker_man_2026">The Wicker Man</a></search-page-media-row>
        """
        session = FakeSession({"https://www.rottentomatoes.com/search": FakeResponse(200, text=page)})
        assert _find_rt_slug("The Wicker Man", 2026, session) == "/m/the_wicker_man_2026"


def _screened(title, **kwargs):
    return Film(
        title=title,
        screenings=[Screening("Clapham", datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ), "u")],
        **kwargs,
    )


class TestEnrichFilms:
    def test_no_api_key_sets_all_empty(self):
        session = FakeSession()
        films = [_screened("A"), _screened("B")]
        enrich_films(films, api_key="", session=session)
        assert all(f.scores == Scores() for f in films)
        assert not any(f.scores_incomplete for f in films)
        assert not any("omdbapi" in url for url in session.calls)

    @patch("cinema_digest.enrich._read_cache", return_value=None)
    @patch("cinema_digest.enrich._write_cache")
    @patch("cinema_digest.enrich.fetch_omdb")
    def test_exception_does_not_crash(self, mock_fetch, mock_write, mock_read):
        mock_fetch.side_effect = Exception("Network error")
        films = [_screened("A")]
        enrich_films(films, api_key="test_key", session=FakeSession())
        assert mock_fetch.called
        assert films[0].scores == Scores()

    def test_scraped_scores_used_without_omdb(self):
        page = (
            '<script type="application/ld+json">'
            + json.dumps({"@type": "Movie", "name": "Sexy Beast", "datePublished": "2001-06-13",
                          "aggregateRating": {"ratingValue": 79}})
            + "</script>"
        )
        session = FakeSession({"https://www.metacritic.com/movie/sexy-beast/": FakeResponse(200, text=page)})
        films = [_screened("Sexy Beast", year=2000)]
        enrich_films(films, api_key="", session=session)
        assert films[0].scores.metacritic == 79

    def test_zero_budget_marks_all_incomplete_without_requests(self):
        session = FakeSession()
        films = [_screened("A"), _screened("B")]
        enrich_films(films, api_key="k", session=session, time_budget=0)
        assert all(f.scores_incomplete for f in films)
        assert all(f.scores == Scores() for f in films)
        assert session.calls == []

    def test_concurrent_run_stops_at_budget(self, monkeypatch):
        """A film whose lookups hang past the budget is marked incomplete; others keep scores."""
        release = threading.Event()

        def fake_enrich_one(film, api_key, tmdb_api_key, session, deadline):
            if film.title == "Slow":
                release.wait(5)
            film.scores = Scores(metacritic=80)
            return film

        monkeypatch.setattr(enrich_module, "_enrich_one", fake_enrich_one)
        monkeypatch.setattr(enrich_module, "_enrich_ph_links", lambda films, session: None)
        films = [_screened("Fast"), _screened("Slow")]
        started = time.monotonic()
        try:
            enrich_films(films, api_key="k", time_budget=0.3, max_workers=2)
        finally:
            release.set()
        assert time.monotonic() - started < 3
        fast, slow = films
        assert fast.scores.metacritic == 80 and not fast.scores_incomplete
        assert slow.scores == Scores() and slow.scores_incomplete

    def test_concurrent_run_copies_results_back(self, monkeypatch):
        def fake_enrich_one(film, api_key, tmdb_api_key, session, deadline):
            film.scores = Scores(imdb=7.1)
            film.director = "Someone"
            return film

        monkeypatch.setattr(enrich_module, "_enrich_one", fake_enrich_one)
        monkeypatch.setattr(enrich_module, "_enrich_ph_links", lambda films, session: None)
        films = [_screened("A"), _screened("B"), _screened("C")]
        enrich_films(films, api_key="k", max_workers=3)
        assert all(f.scores.imdb == 7.1 and f.director == "Someone" for f in films)
