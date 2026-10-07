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
    # Importing the web app already installed a handler bound to the real
    # stderr; start clean so the one build_static installs writes to capsys.
    root.handlers = []
    try:
        build_static.main()
    finally:
        root.handlers = before

    err = capsys.readouterr().err
    assert "SECRET123" not in err
    assert "apikey=***" in err
    assert (tmp_path / "films.json").exists()
    html = (tmp_path / "index.html").read_text()
    assert 'window.FILMS_URL = "films.json"' in html
    assert "window.STATIC_SNAPSHOT = true" in html


def _redacting_handlers():
    import logging

    from cinema_digest.main import RedactingFilter

    root = logging.getLogger("cinema_digest")
    return [h for h in root.handlers if any(isinstance(f, RedactingFilter) for f in h.filters)]


def test_wsgi_app_installs_log_redaction():
    # gunicorn imports webapp.app and never calls main()
    import logging

    root = logging.getLogger("cinema_digest")
    before = list(root.handlers)
    root.handlers = []
    try:
        webapp.create_app()
        assert len(_redacting_handlers()) == 1
    finally:
        root.handlers = before


def test_setup_logging_does_not_duplicate_handlers():
    import logging

    from cinema_digest.main import setup_logging

    root = logging.getLogger("cinema_digest")
    before = list(root.handlers)
    root.handlers = []
    try:
        setup_logging()
        setup_logging()
        webapp.create_app()
        assert len(root.handlers) == 1
    finally:
        root.handlers = before


def test_failed_scrape_keeps_cached_films(monkeypatch):
    results = [
        ([Film(title="Good", screenings=[])], [], False),
        ([], ["Scraping failed with an unexpected error (ConnectionError)."], True),
    ]
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: results.pop(0))
    monkeypatch.setattr(webapp, "REFRESH_COOLDOWN_SECONDS", 0)

    first = webapp.build_payload(force_refresh=True)
    second = webapp.build_payload(force_refresh=True)

    assert [f["title"] for f in second["films"]] == ["Good"]
    assert "ConnectionError" in second["error"]
    assert second["fetched_at"] == first["fetched_at"]  # still the good load's time


def test_forced_refreshes_within_cooldown_reuse_last_run(monkeypatch):
    calls = {"n": 0}

    def fake_build(config=None):
        calls["n"] += 1
        return [Film(title="Once", screenings=[])], [], False

    monkeypatch.setattr(webapp, "build_digest", fake_build)
    for _ in range(5):
        webapp.get_films(force_refresh=True)
    assert calls["n"] == 1


def test_concurrent_forced_refreshes_coalesce(monkeypatch):
    import threading
    import time as _time

    calls = {"n": 0}
    started = threading.Event()

    def slow_build(config=None):
        calls["n"] += 1
        started.set()
        _time.sleep(0.3)
        return [Film(title="Once", screenings=[])], [], False

    monkeypatch.setattr(webapp, "build_digest", slow_build)
    monkeypatch.setattr(webapp, "REFRESH_COOLDOWN_SECONDS", 0)  # isolate coalescing

    first = threading.Thread(target=webapp.get_films, kwargs={"force_refresh": True})
    first.start()
    started.wait()
    # These arrive while the first run holds the lock
    waiters = [
        threading.Thread(target=webapp.get_films, kwargs={"force_refresh": True})
        for _ in range(4)
    ]
    for t in waiters:
        t.start()
    for t in [first, *waiters]:
        t.join()
    assert calls["n"] == 1


def test_empty_refresh_keeps_cached_films_even_if_not_flagged(monkeypatch):
    # e.g. a markup change: pages load fine but nothing parses
    results = [
        ([Film(title="Good", screenings=[])], [], False),
        ([], [], False),
    ]
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: results.pop(0))
    monkeypatch.setattr(webapp, "REFRESH_COOLDOWN_SECONDS", 0)

    webapp.build_payload(force_refresh=True)
    payload = webapp.build_payload(force_refresh=True)

    assert [f["title"] for f in payload["films"]] == ["Good"]
    assert payload["error"] == "The refresh found no listings."


def test_cache_timing_uses_monotonic_clock(monkeypatch):
    # Freshness and cooldown must not use London wall-clock time, which jumps
    # an hour at DST changes; drive a fake monotonic clock instead.
    clock = {"now": 1000.0}
    monkeypatch.setattr(webapp.time, "monotonic", lambda: clock["now"])
    calls = {"n": 0}

    def fake_build(config=None):
        calls["n"] += 1
        return [Film(title="Once", screenings=[])], [], False

    monkeypatch.setattr(webapp, "build_digest", fake_build)

    webapp.get_films()
    clock["now"] += webapp.CACHE_TTL_SECONDS - 1
    webapp.get_films()
    assert calls["n"] == 1  # still fresh

    clock["now"] += 2
    webapp.get_films()
    assert calls["n"] == 2  # expired by the monotonic clock

    clock["now"] += webapp.REFRESH_COOLDOWN_SECONDS - 1
    webapp.get_films(force_refresh=True)
    assert calls["n"] == 2  # within cooldown

    clock["now"] += 2
    webapp.get_films(force_refresh=True)
    assert calls["n"] == 3


def _clapham_and_ritzy():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    when = datetime(2026, 3, 11, 19, 30, tzinfo=ZoneInfo("Europe/London"))
    return [
        Film(title="At Clapham", screenings=[Screening("Clapham", when, "")]),
        Film(title="At Ritzy", screenings=[Screening("Ritzy", when, "")]),
    ]


def test_partial_cinema_failure_keeps_complete_cache(monkeypatch):
    both = _clapham_and_ritzy()
    results = [
        (both, [], False),
        ([both[0]], ["Could not fetch the Ritzy listings (ConnectionError)."], True),
    ]
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: results.pop(0))
    monkeypatch.setattr(webapp, "REFRESH_COOLDOWN_SECONDS", 0)

    webapp.build_payload(force_refresh=True)
    payload = webapp.build_payload(force_refresh=True)

    assert payload["cinemas"] == ["Clapham", "Ritzy"]
    assert "Ritzy" in payload["error"]


def test_partial_result_replaces_a_day_old_cache(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(webapp.time, "monotonic", lambda: clock["now"])
    both = _clapham_and_ritzy()
    results = [
        (both, [], False),
        ([both[0]], ["Could not fetch the Ritzy listings (ConnectionError)."], True),
    ]
    monkeypatch.setattr(webapp, "build_digest", lambda config=None: results.pop(0))

    webapp.build_payload(force_refresh=True)
    clock["now"] += webapp.GOOD_RESULT_MAX_AGE_SECONDS + 1
    payload = webapp.build_payload(force_refresh=True)

    # Too old to prefer: show the partial result, flagged, not day-old listings
    assert payload["cinemas"] == ["Clapham"]
    assert payload["error"] is None
    assert payload["notes"] == ["Could not fetch the Ritzy listings (ConnectionError)."]
    assert payload["warning"]


def test_empty_first_scrape_is_an_error_and_retries(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(webapp.time, "monotonic", lambda: clock["now"])
    calls = {"n": 0}

    def empty_build(config=None):
        calls["n"] += 1
        return [], ["Could not fetch the Clapham listings (Timeout)."], True

    monkeypatch.setattr(webapp, "build_digest", empty_build)

    payload = webapp.build_payload()
    assert payload["films"] == []
    assert "Clapham" in payload["error"]
    assert payload["fetched_at"] is None  # not reported as a successful load

    clock["now"] += webapp.REFRESH_COOLDOWN_SECONDS + 1
    webapp.build_payload()  # ordinary request, no ?refresh=1
    assert calls["n"] == 2  # retried after the cooldown, not held for the TTL
