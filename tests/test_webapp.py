"""Tests for the interactive web app (serialization + routes)."""

from __future__ import annotations

import pytest

from cinema_digest import webapp
from cinema_digest.models import Film, Scores, Screening


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset the module-level cache between tests."""
    webapp._cache.films = None
    webapp._cache.fetched_at = None
    webapp._cache.error = None
    yield
    webapp._cache.films = None
    webapp._cache.fetched_at = None
    webapp._cache.error = None


def test_serialize_film(sample_film):
    data = webapp.serialize_film(sample_film)

    assert data["title"] == "Test Film"
    assert data["scores"] == {"metacritic": 83, "imdb": 7.4, "rotten_tomatoes": 91}
    # Screens at both cinemas -> both listed, sorted
    assert data["cinemas"] == ["Clapham", "Ritzy"]
    # Showtimes sorted chronologically, carry cinema + booking url
    assert [s["cinema"] for s in data["showtimes"]] == ["Clapham", "Clapham", "Ritzy"]
    assert all(s["url"].startswith("https://") for s in data["showtimes"])
    # A booking URL exists per cinema
    assert set(data["booking_urls"].keys()) == {"Clapham", "Ritzy"}
    # MC 83 / IMDb 7.4 -> highlighted
    assert data["highlighted"] is True


def test_serialize_film_no_scores(sample_screening_weekday):
    film = Film(title="Scoreless", screenings=[sample_screening_weekday])
    data = webapp.serialize_film(film)
    assert data["scores"] == {"metacritic": None, "imdb": None, "rotten_tomatoes": None}
    assert data["highlighted"] is False
    assert data["cinemas"] == ["Clapham"]


def test_build_payload_sorts_by_metacritic(monkeypatch):
    low = Film(title="Low", screenings=[], scores=Scores(metacritic=40))
    high = Film(title="High", screenings=[], scores=Scores(metacritic=90))
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: [low, high])

    payload = webapp.build_payload(force_refresh=True)
    titles = [f["title"] for f in payload["films"]]
    assert titles == ["High", "Low"]
    assert payload["count"] == 2
    assert payload["error"] is None


def test_api_films_route(monkeypatch, sample_film):
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: [sample_film])
    app = webapp.create_app()
    client = app.test_client()

    resp = client.get("/api/films")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 1
    assert body["films"][0]["title"] == "Test Film"
    assert body["cinemas"] == ["Clapham", "Ritzy"]


def test_index_route_serves_page():
    app = webapp.create_app()
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Cinema Listings" in resp.data
    assert b"/api/films" in resp.data


def test_cache_reuses_result(monkeypatch):
    calls = {"n": 0}

    def fake_build(config=None):
        calls["n"] += 1
        return [Film(title="Once", screenings=[])]

    monkeypatch.setattr(webapp, "build_digest", fake_build)

    webapp.get_films(force_refresh=True)
    webapp.get_films()  # within TTL -> should not rebuild
    assert calls["n"] == 1


def test_scraper_error_surfaces(monkeypatch):
    from cinema_digest.scraper import ScraperError

    def boom(config=None):
        raise ScraperError("structure changed")

    monkeypatch.setattr(webapp, "build_digest", boom)
    films, fetched_at, error = webapp.get_films(force_refresh=True)
    assert films == []
    assert "structure changed" in error
