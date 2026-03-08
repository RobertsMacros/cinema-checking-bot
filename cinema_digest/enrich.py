"""Enrich films with review scores from OMDb API."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cinema_digest.models import Film, Scores
from cinema_digest.scraper import normalize_title

logger = logging.getLogger(__name__)

OMDB_API_URL = "https://www.omdbapi.com/"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"

_RETRY = Retry(total=3, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])


def _make_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _cache_key(title: str, year: int | None) -> str:
    raw = f"{normalize_title(title)}|{year or ''}"
    return hashlib.md5(raw.encode()).hexdigest() + ".json"


def _read_cache(key: str) -> dict | None:
    path = CACHE_DIR / key
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt cache file: %s", path)
            return None
    return None


def _write_cache(key: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        (CACHE_DIR / key).write_text(json.dumps(data))
    except OSError:
        logger.warning("Could not write cache file: %s", key)


def _clean_title_for_search(title: str) -> str:
    """Strip noise from a title before querying OMDb."""
    t = title.strip()
    # Remove trailing year in parens: "Film Name (2026)" -> "Film Name"
    t = re.sub(r"\s*\(\d{4}\)\s*$", "", t)
    # Remove trailing exclamation marks that some listings add
    t = re.sub(r"!+$", "", t).strip()
    return t


def _title_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two normalized titles."""
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def _parse_scores(data: dict) -> Scores:
    """Extract Metacritic, IMDb, and Rotten Tomatoes scores from OMDb response."""
    mc_raw = data.get("Metascore", "N/A")
    metacritic = int(mc_raw) if mc_raw and mc_raw != "N/A" else None

    imdb_raw = data.get("imdbRating", "N/A")
    imdb = float(imdb_raw) if imdb_raw and imdb_raw != "N/A" else None

    rt = None
    for r in data.get("Ratings", []):
        if r.get("Source") == "Rotten Tomatoes":
            val = r["Value"].rstrip("%")
            try:
                rt = int(val)
            except ValueError:
                pass
            break

    return Scores(metacritic=metacritic, imdb=imdb, rotten_tomatoes=rt)


def fetch_omdb(
    title: str,
    year: int | None,
    api_key: str,
    session: requests.Session | None = None,
) -> dict:
    """Query OMDb API for a film. Returns raw JSON dict."""
    s = session or _make_session()
    params: dict[str, str] = {"apikey": api_key, "t": title, "type": "movie"}
    if year:
        params["y"] = str(year)

    response = s.get(OMDB_API_URL, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def enrich_film(
    film: Film,
    api_key: str,
    session: requests.Session | None = None,
) -> None:
    """Enrich a single film with scores. Mutates film.scores in place."""
    if not api_key:
        logger.warning("No OMDb API key configured; skipping enrichment")
        film.scores = Scores()
        return

    clean_title = _clean_title_for_search(film.title)
    cache_key = _cache_key(clean_title, film.year)

    # Check cache first
    cached = _read_cache(cache_key)
    if cached is not None:
        if cached.get("Response") == "True":
            film.scores = _parse_scores(cached)
            logger.debug("Cache hit for %r", film.title)
        else:
            film.scores = Scores()
            logger.debug("Cache hit (not found) for %r", film.title)
        return

    # Fetch from OMDb
    data = fetch_omdb(clean_title, film.year, api_key, session)
    _write_cache(cache_key, data)

    if data.get("Response") != "True":
        logger.info("OMDb: no result for %r (year=%s)", clean_title, film.year)
        # Try again without year if we had one
        if film.year:
            data = fetch_omdb(clean_title, None, api_key, session)
            _write_cache(_cache_key(clean_title, None), data)
        if data.get("Response") != "True":
            film.scores = Scores()
            return

    # Check for title mismatch
    returned_title = data.get("Title", "")
    similarity = _title_similarity(clean_title, returned_title)
    if similarity < 0.6:
        logger.warning(
            "Possible mismatch for %r: OMDb returned %r (similarity=%.2f). Using N/A.",
            film.title,
            returned_title,
            similarity,
        )
        film.scores = Scores()
        return

    if similarity < 0.85:
        logger.info(
            "Weak match for %r: OMDb returned %r (similarity=%.2f). Accepting cautiously.",
            film.title,
            returned_title,
            similarity,
        )

    film.scores = _parse_scores(data)
    logline_from_omdb = data.get("Plot")
    if logline_from_omdb and logline_from_omdb != "N/A" and not film.logline:
        film.logline = logline_from_omdb


def enrich_films(
    films: list[Film],
    api_key: str,
    session: requests.Session | None = None,
) -> None:
    """Enrich all films with scores. Failures are logged but do not propagate."""
    if not api_key:
        logger.warning("No OMDb API key configured; all scores will be N/A")
        for film in films:
            film.scores = Scores()
        return

    s = session or _make_session()
    for film in films:
        try:
            enrich_film(film, api_key, session=s)
        except Exception:
            logger.exception("Failed to enrich %r", film.title)
            film.scores = Scores()
