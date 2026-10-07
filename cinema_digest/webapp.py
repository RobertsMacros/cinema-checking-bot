"""Interactive web app for browsing cinema listings.

Reuses the same scrape -> filter -> enrich pipeline that powers the email
digest, but serves it as a live, interactive single-page site you can open
whenever you want and filter by cinema.

Run it with:

    python -m cinema_digest.webapp

then open http://127.0.0.1:5000 in a browser.

The scraped/enriched listings are cached in memory for a while (see
``CACHE_TTL_SECONDS``) so repeat visits are instant; use the "Refresh"
button in the UI (or add ``?refresh=1`` to ``/api/films``) to force a
fresh scrape.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request

from cinema_digest import considering
from cinema_digest.config import RUN_TIME_BUDGET_SECONDS, Config
from cinema_digest.enrich import enrich_films
from cinema_digest.filters import filter_screenings
from cinema_digest.formatter import (
    _cinema_page_url,
    _compact_logline,
    _film_booking_url,
    _is_valid_booking_url,
    _sort_key_mc_desc,
    digest_warning,
    is_highlighted,
)
from cinema_digest.main import setup_logging
from cinema_digest.models import Film, ScrapeResult
from cinema_digest.scraper import scrape_all
from cinema_digest.webapp_template import PAGE_HTML

logger = logging.getLogger("cinema_digest.webapp")

LONDON_TZ = ZoneInfo("Europe/London")

# How long (seconds) to serve cached listings before re-scraping.
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "1800"))  # 30 min

# Minimum gap between pipeline runs triggered by ?refresh=1. Each run takes
# minutes and spends OMDb/TMDB quota, so repeated refreshes reuse the last one.
REFRESH_COOLDOWN_SECONDS = int(os.environ.get("REFRESH_COOLDOWN_SECONDS", "60"))


# ---------------------------------------------------------------------------
# Data pipeline (scrape -> filter -> enrich), with in-memory caching
# ---------------------------------------------------------------------------

class _Cache:
    """Thread-safe in-memory cache for the enriched film list."""

    def __init__(self) -> None:
        self.films: list[Film] | None = None
        self.notes: list[str] = []
        self.listings_suspect: bool = False
        self.fetched_at: datetime | None = None
        self.error: str | None = None
        # When the last pipeline run finished, successful or not
        self.attempted_at: datetime | None = None
        self.lock = threading.Lock()


_cache = _Cache()


def build_digest(config: Config | None = None) -> tuple[list[Film], list[str], bool]:
    """Run the full pipeline; return (films, notes, listings_suspect).

    Mirrors main.main(): scraping problems become notes rather than errors.
    Isolated so tests can monkeypatch it without touching the network.
    """
    started = time.monotonic()
    if config is None:
        config = Config.from_env()

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

    filtered = filter_screenings(scraped.films)
    considering.mark(filtered, considering.load())
    if filtered:
        remaining = RUN_TIME_BUDGET_SECONDS - (time.monotonic() - started)
        enrich_films(
            filtered,
            config.omdb_api_key,
            tmdb_api_key=config.tmdb_api_key,
            time_budget=max(0.0, remaining),
        )
    return filtered, notes, scraped.listings_suspect


def _is_fresh(now: datetime) -> bool:
    return (
        _cache.films is not None
        and _cache.fetched_at is not None
        and (now - _cache.fetched_at).total_seconds() < CACHE_TTL_SECONDS
    )


def _recently_attempted(now: datetime) -> bool:
    return (
        _cache.attempted_at is not None
        and (now - _cache.attempted_at).total_seconds() < REFRESH_COOLDOWN_SECONDS
    )


def get_films(force_refresh: bool = False) -> _Cache:
    """Return the cache, re-running the pipeline first if it is stale.

    Only one pipeline run happens at a time. Callers that waited on the lock
    reuse a run that finished meanwhile, and no new run starts within
    REFRESH_COOLDOWN_SECONDS of the last one (forced or after a failure).
    """
    requested_at = datetime.now(LONDON_TZ)
    if _is_fresh(requested_at) and not force_refresh:
        return _cache

    with _cache.lock:
        now = datetime.now(LONDON_TZ)
        # Another thread finished a run while we waited for the lock.
        if _cache.attempted_at is not None and _cache.attempted_at >= requested_at:
            return _cache
        # A run finished moments ago (successful or not): don't start another.
        if _recently_attempted(now):
            return _cache
        if _is_fresh(now) and not force_refresh:
            return _cache
        try:
            films, notes, suspect = build_digest()
            if not films and suspect and _cache.films:
                # The scrape failed outright (e.g. a network error). Keep the
                # last good listings rather than replacing them with nothing.
                _cache.error = "; ".join(notes) or "Listings could not be fetched."
                logger.warning("Refresh failed, keeping cached films: %s", _cache.error)
            else:
                _cache.films = films
                _cache.notes = notes
                _cache.listings_suspect = suspect
                _cache.fetched_at = datetime.now(LONDON_TZ)
                _cache.error = None
                logger.info("Cache refreshed: %d films", len(films))
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            logger.exception("Unexpected error building digest")
            _cache.error = f"{type(e).__name__}: {e}"
        _cache.attempted_at = datetime.now(LONDON_TZ)
        return _cache


# ---------------------------------------------------------------------------
# Serialization: Film -> plain dict for the frontend
# ---------------------------------------------------------------------------

def _score_urls(film: Film) -> dict[str, str | None]:
    s = film.scores
    if s is None:
        return {"metacritic": None, "imdb": None, "rotten_tomatoes": None}
    return {
        "metacritic": f"https://www.metacritic.com/movie/{s.mc_slug}/" if s.mc_slug else None,
        "imdb": f"https://www.imdb.com/title/{s.imdb_id}/" if s.imdb_id else None,
        "rotten_tomatoes": f"https://www.rottentomatoes.com{s.rt_slug}" if s.rt_slug else None,
    }


def _booking_urls(film: Film) -> dict[str, str]:
    """Booking URL per cinema, chosen the same way as the email's Book buttons."""
    return {
        cinema: _film_booking_url(film, cinema)
        for cinema in sorted({s.cinema for s in film.screenings})
    }


def _showtime_url(film: Film, booking_url: str | None, cinema: str) -> str:
    """The screening's own link if it is in Picturehouse's current format.

    Older links (e.g. ticketing.picturehouses.com) are dead, so those fall
    back to the film's page at that cinema, as in the email.
    """
    if _is_valid_booking_url(booking_url):
        return booking_url
    return _cinema_page_url(film, cinema)


def serialize_film(film: Film) -> dict:
    """Convert a Film into a JSON-serializable dict for the frontend."""
    scores = film.scores
    showtimes = [
        {
            "cinema": s.cinema,
            "day": s.date.strftime("%a"),
            "date": f"{s.date.day} {s.date.strftime('%b')}",
            "time": s.date.strftime("%H:%M"),
            "iso": s.date.isoformat(),
            "url": _showtime_url(film, s.booking_url, s.cinema),
            "type": s.screening_type,
        }
        for s in sorted(film.screenings, key=lambda s: s.date)
    ]
    return {
        "title": film.title,
        "director": film.director,
        "year": film.year,
        "duration": film.duration,
        "logline": _compact_logline(film.logline),
        "highlighted": is_highlighted(scores),
        "considering": bool(film.considering),
        "scores": {
            "metacritic": scores.metacritic if scores else None,
            "imdb": scores.imdb if scores else None,
            "rotten_tomatoes": scores.rotten_tomatoes if scores else None,
        },
        "score_urls": _score_urls(film),
        "cinemas": sorted({s.cinema for s in film.screenings}),
        "showtimes": showtimes,
        "booking_urls": _booking_urls(film),
    }


def build_payload(force_refresh: bool = False) -> dict:
    """Build the JSON payload served at /api/films."""
    cache = get_films(force_refresh=force_refresh)
    films = cache.films or []
    ordered = sorted(films, key=_sort_key_mc_desc)
    fetched_at = cache.fetched_at
    return {
        "films": [serialize_film(f) for f in ordered],
        "cinemas": sorted({s.cinema for f in films for s in f.screenings}),
        "fetched_at": fetched_at.isoformat() if fetched_at else None,
        "fetched_at_label": fetched_at.strftime("%a %d %b, %H:%M") if fetched_at else None,
        "count": len(ordered),
        "warning": digest_warning(films, cache.listings_suspect) if fetched_at else None,
        "notes": list(cache.notes),
        "error": cache.error,
    }


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    # Here rather than in main() so WSGI servers (gunicorn) get it too:
    # redacts API keys that requests puts in HTTP error messages.
    setup_logging()
    app = Flask(__name__)

    @app.route("/")
    def index() -> str:
        return PAGE_HTML

    @app.route("/api/films")
    def api_films():
        force = request.args.get("refresh") in ("1", "true", "yes")
        return jsonify(build_payload(force_refresh=force))

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app


# Module-level WSGI app for hosting (e.g. `gunicorn cinema_digest.webapp:app`).
app = create_app()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Cinema listings web app")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    app = create_app()
    logger.info("Starting cinema web app on http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
