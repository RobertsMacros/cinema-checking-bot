"""Tests for the interactive web app (serialization + routes)."""

from __future__ import annotations

import pytest

from cinema_digest import webapp
from cinema_digest.models import Film, Scores, Screening


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset the module-level cache between tests."""
    webapp._cache.__init__()
    yield
    webapp._cache.__init__()


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
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: ([low, high], [], False))

    payload = webapp.build_payload(force_refresh=True)
    titles = [f["title"] for f in payload["films"]]
    assert titles == ["High", "Low"]
    assert payload["count"] == 2
    assert payload["error"] is None
    assert payload["warning"] is None


def test_build_payload_puts_considered_films_first(monkeypatch):
    high = Film(title="High", screenings=[], scores=Scores(metacritic=90))
    waiting = Film(title="Waiting", screenings=[], scores=Scores(metacritic=50), considering={"bar": 75})
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: ([high, waiting], [], False))

    payload = webapp.build_payload(force_refresh=True)
    assert [f["title"] for f in payload["films"]] == ["Waiting", "High"]
    assert payload["films"][0]["considering"] is True


def test_build_payload_carries_notes_and_warning(monkeypatch, sample_film):
    monkeypatch.setattr(
        webapp, "build_digest",
        lambda config=None: ([sample_film], ["Ritzy page failed to load."], True),
    )
    payload = webapp.build_payload(force_refresh=True)
    assert payload["notes"] == ["Ritzy page failed to load."]
    assert payload["warning"]  # listings_suspect -> banner text


def test_api_films_route(monkeypatch, sample_film):
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: ([sample_film], [], False))
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
        return [Film(title="Once", screenings=[])], [], False

    monkeypatch.setattr(webapp, "build_digest", fake_build)

    webapp.get_films(force_refresh=True)
    webapp.get_films()  # within TTL -> should not rebuild
    assert calls["n"] == 1


def test_pipeline_error_surfaces(monkeypatch):
    def boom(config=None):
        raise RuntimeError("structure changed")

    monkeypatch.setattr(webapp, "build_digest", boom)
    payload = webapp.build_payload(force_refresh=True)
    assert payload["films"] == []
    assert "structure changed" in payload["error"]


def test_scrape_failure_becomes_note(monkeypatch):
    def scrape_boom():
        raise ConnectionError("down")

    monkeypatch.setattr(webapp, "scrape_all", scrape_boom)
    films, notes, suspect = webapp.build_digest(config=webapp.Config.from_env())
    assert films == []
    assert suspect is True
    assert "ConnectionError" in notes[0]


def test_showtime_links_skip_dead_ticketing_urls(sample_film):
    # conftest's screenings use the dead ticketing.picturehouses.com host
    sample_film.ph_url = "https://www.picturehouses.com/movie-details/020/HO00001/test-film"
    data = webapp.serialize_film(sample_film)

    for s in data["showtimes"]:
        assert "ticketing.picturehouses.com" not in s["url"]
    ritzy = next(s for s in data["showtimes"] if s["cinema"] == "Ritzy")
    assert ritzy["url"] == "https://www.picturehouses.com/movie-details/004/HO00001/test-film"


def test_showtime_and_book_links_keep_current_session_urls(sample_film):
    good = "https://web.picturehouses.com/order/showtimes/020-12345/seats"
    sample_film.screenings[0].booking_url = good  # earliest Clapham screening
    data = webapp.serialize_film(sample_film)

    assert data["showtimes"][0]["url"] == good
    assert data["booking_urls"]["Clapham"] == good


def test_static_build_redacts_api_keys(monkeypatch, tmp_path, capsys):
    import logging

    import build_static

    def fake_payload(force_refresh=False):
        logging.getLogger("cinema_digest.enrich").error(
            "HTTPError for url: https://www.omdbapi.com/?apikey=SECRET123&t=Film"
        )
        return {"films": [], "count": 0, "error": None}

    monkeypatch.setattr(build_static, "build_payload", fake_payload)
    monkeypatch.setattr(build_static, "OUT_DIR", tmp_path)
    root = logging.getLogger("cinema_digest")
    before = list(root.handlers)
    try:
        build_static.main()
    finally:
        root.handlers = before

    err = capsys.readouterr().err
    assert "SECRET123" not in err
    assert "apikey=***" in err
    assert (tmp_path / "films.json").exists()
    assert '"films.json"' in (tmp_path / "index.html").read_text()
