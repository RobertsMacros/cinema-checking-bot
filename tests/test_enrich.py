"""Tests for score enrichment logic."""

from unittest.mock import MagicMock, patch

from cinema_digest.enrich import (
    _clean_title_for_search,
    _parse_scores,
    _title_similarity,
    enrich_film,
    enrich_films,
)
from cinema_digest.models import Film, Scores, Screening

from datetime import datetime
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")


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
        assert sim > 0.8

    def test_different_titles(self):
        sim = _title_similarity("The Great Gatsby", "Raging Bull")
        assert sim < 0.4


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

    @patch("cinema_digest.enrich._read_cache")
    def test_cache_hit_skips_api(self, mock_read):
        mock_read.return_value = {
            "Response": "True",
            "Title": "Cached Film",
            "Metascore": "80",
            "imdbRating": "7.5",
            "Ratings": [{"Source": "Rotten Tomatoes", "Value": "85%"}],
            "Director": "N/A",
            "Plot": "N/A",
        }
        film = Film(title="Cached Film", year=2025, screenings=[])
        enrich_film(film, api_key="test_key")
        assert film.scores.metacritic == 80
        assert film.scores.imdb == 7.5
        assert film.scores.rotten_tomatoes == 85


class TestEnrichFilms:
    def test_no_api_key_sets_all_empty(self):
        films = [Film(title="A", screenings=[]), Film(title="B", screenings=[])]
        enrich_films(films, api_key="")
        assert all(f.scores == Scores() for f in films)

    @patch("cinema_digest.enrich._read_cache", return_value=None)
    @patch("cinema_digest.enrich._write_cache")
    @patch("cinema_digest.enrich.fetch_omdb")
    def test_exception_does_not_crash(self, mock_fetch, mock_write, mock_read):
        mock_fetch.side_effect = Exception("Network error")
        films = [Film(title="A", screenings=[])]
        enrich_films(films, api_key="test_key")
        assert films[0].scores == Scores()
