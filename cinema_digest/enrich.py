"""Enrich films with review scores from OMDb, RT scraping, and TMDB."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

import requests
from bs4 import BeautifulSoup
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


def _apply_metadata(film: Film, data: dict) -> None:
    """Apply director, IMDB ID, and logline from OMDb data to a film."""
    director = data.get("Director")
    if director and director != "N/A" and not film.director:
        film.director = director

    imdb_id = data.get("imdbID")
    if imdb_id and not film.imdb_id:
        film.imdb_id = imdb_id

    logline_from_omdb = data.get("Plot")
    if logline_from_omdb and logline_from_omdb != "N/A":
        # Always prefer OMDb plot when it's shorter than scraped logline
        if not film.logline or len(logline_from_omdb) < len(film.logline):
            film.logline = logline_from_omdb


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
            _apply_metadata(film, cached)
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
    _apply_metadata(film, data)


TMDB_API_URL = "https://api.themoviedb.org/3"


def _fetch_tmdb(
    title: str,
    year: int | None,
    api_key: str,
    session: requests.Session,
) -> dict | None:
    """Search TMDB for a film and return its details, or None."""
    params: dict[str, str] = {"api_key": api_key, "query": title}
    if year:
        params["year"] = str(year)

    resp = session.get(f"{TMDB_API_URL}/search/movie", params=params, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        if year:
            # Retry without year
            params.pop("year")
            resp = session.get(f"{TMDB_API_URL}/search/movie", params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        if not results:
            return None

    # Pick the best match by title similarity
    best = max(results[:5], key=lambda r: _title_similarity(title, r.get("title", "")))
    sim = _title_similarity(title, best.get("title", ""))
    if sim < 0.6:
        logger.info("TMDB: no good match for %r (best=%r, sim=%.2f)", title, best.get("title"), sim)
        return None

    return best


def _fetch_omdb_by_imdb_id(
    imdb_id: str,
    api_key: str,
    session: requests.Session,
) -> dict:
    """Query OMDb by IMDb ID for full scores."""
    params: dict[str, str] = {"apikey": api_key, "i": imdb_id, "type": "movie"}
    resp = session.get(OMDB_API_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _enrich_via_tmdb_imdb(
    film: Film,
    omdb_key: str,
    tmdb_key: str,
    session: requests.Session,
) -> bool:
    """Try TMDB search → get IMDB ID → OMDb lookup by ID. Returns True if scores found."""
    clean = _clean_title_for_search(film.title)
    tmdb_data = _fetch_tmdb(clean, film.year, tmdb_key, session)
    if not tmdb_data:
        return False

    # TMDB movie search results don't include imdb_id; need the detail endpoint
    tmdb_id = tmdb_data.get("id")
    if not tmdb_id:
        return False

    detail_resp = session.get(
        f"{TMDB_API_URL}/movie/{tmdb_id}/external_ids",
        params={"api_key": tmdb_key},
        timeout=15,
    )
    detail_resp.raise_for_status()
    imdb_id = detail_resp.json().get("imdb_id")
    if not imdb_id:
        logger.debug("TMDB: no IMDB ID for %r (tmdb_id=%s)", film.title, tmdb_id)
        return False

    # Now look up OMDb by IMDB ID for real MC/RT/IMDb scores
    data = _fetch_omdb_by_imdb_id(imdb_id, omdb_key, session)
    if data.get("Response") != "True":
        return False

    film.scores = _parse_scores(data)
    _apply_metadata(film, data)
    logger.info("TMDB→OMDb: enriched %r via IMDB ID %s", film.title, imdb_id)
    return True


def _apply_tmdb_data(film: Film, data: dict) -> None:
    """Apply TMDB data as fallback for missing scores/metadata."""
    vote = data.get("vote_average")
    vote_count = data.get("vote_count", 0)
    if vote and vote_count >= 10 and film.scores is not None:
        if film.scores.imdb is None:
            film.scores.imdb = round(vote, 1)
            logger.debug("TMDB: filled IMDb-style score %.1f for %r", vote, film.title)

    overview = data.get("overview")
    if overview and (not film.logline or len(overview) < len(film.logline)):
        film.logline = overview


# ---------------------------------------------------------------------------
# Rotten Tomatoes scraping (no API key needed)
# ---------------------------------------------------------------------------

RT_SEARCH_URL = "https://www.rottentomatoes.com/search"
RT_BASE = "https://www.rottentomatoes.com"

_RT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CinemaDigestBot/1.0)",
    "Accept": "text/html",
}


def _find_rt_slug(title: str, year: int | None, session: requests.Session) -> str | None:
    """Search RT and return the movie page slug (e.g. '/m/the_bride_2026')."""
    query = title
    if year:
        query = f"{title} {year}"
    resp = session.get(
        RT_SEARCH_URL,
        params={"search": query},
        headers=_RT_HEADERS,
        timeout=15,
    )
    if resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    # Movie result links look like /m/some_slug
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("/m/"):
            # Check the link text roughly matches our title
            link_text = a_tag.get_text(strip=True)
            if link_text and _title_similarity(title, link_text) >= 0.6:
                return href
    return None


def _scrape_rt_scores(slug: str, session: requests.Session) -> tuple[int | None, int | None]:
    """Scrape RT movie page for (tomatometer, audience_score).

    Extracts from JSON-LD structured data embedded in the page.
    """
    resp = session.get(
        f"{RT_BASE}{slug}",
        headers=_RT_HEADERS,
        timeout=15,
    )
    if resp.status_code != 200:
        return None, None

    soup = BeautifulSoup(resp.text, "html.parser")

    tomatometer = None
    audience = None

    # Try JSON-LD first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "Movie":
                rating = data.get("aggregateRating", {})
                val = rating.get("ratingValue")
                if val is not None:
                    tomatometer = int(val)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    # Fallback: look for score patterns in the page text
    if tomatometer is None:
        text = resp.text
        # Pattern like "score":"59" near "tomatometerScore" or similar
        m = re.search(r'"tomatometerScore"\s*:\s*\{[^}]*"score"\s*:\s*"?(\d+)"?', text)
        if m:
            tomatometer = int(m.group(1))

    # Audience score
    m = re.search(r'"audienceScore"\s*:\s*\{[^}]*"score"\s*:\s*"?(\d+)"?', resp.text)
    if m:
        audience = int(m.group(1))

    return tomatometer, audience


def _enrich_from_rt(film: Film, session: requests.Session) -> None:
    """Try to fill missing RT score by scraping rottentomatoes.com."""
    if film.scores and film.scores.rotten_tomatoes is not None:
        return  # Already have RT score

    clean = _clean_title_for_search(film.title)
    slug = _find_rt_slug(clean, film.year, session)
    if not slug:
        logger.debug("RT: no slug found for %r", film.title)
        return

    tomatometer, _audience = _scrape_rt_scores(slug, session)
    if tomatometer is not None:
        if film.scores is None:
            film.scores = Scores()
        film.scores.rotten_tomatoes = tomatometer
        logger.info("RT scrape: %r → %d%%", film.title, tomatometer)


def enrich_films(
    films: list[Film],
    api_key: str,
    tmdb_api_key: str = "",
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

    # TMDB→IMDB ID→OMDb pass: find films on TMDB, get IMDB ID, look up full scores
    if tmdb_api_key:
        for film in films:
            scores = film.scores
            has_any = scores and (
                scores.metacritic is not None
                or scores.imdb is not None
                or scores.rotten_tomatoes is not None
            )
            if has_any:
                continue
            try:
                found = _enrich_via_tmdb_imdb(film, api_key, tmdb_api_key, s)
                if not found:
                    # Fall back to basic TMDB data (vote_average as IMDb-style)
                    clean = _clean_title_for_search(film.title)
                    tmdb_data = _fetch_tmdb(clean, film.year, tmdb_api_key, s)
                    if tmdb_data:
                        _apply_tmdb_data(film, tmdb_data)
                        logger.info("TMDB fallback enriched %r", film.title)
            except Exception:
                logger.exception("TMDB fallback failed for %r", film.title)

    # RT scraping pass — fills missing RT scores for any film
    for film in films:
        if film.scores and film.scores.rotten_tomatoes is not None:
            continue
        try:
            _enrich_from_rt(film, s)
        except Exception:
            logger.exception("RT scrape failed for %r", film.title)
