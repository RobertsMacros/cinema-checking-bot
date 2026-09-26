"""Enrich films with review scores from OMDb, RT scraping, and TMDB."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, wait
from difflib import SequenceMatcher
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cinema_digest.config import CINEMA_CODES, PH_WHATS_ON_URL
from cinema_digest.models import Film, Scores
from cinema_digest.scraper import normalize_title

logger = logging.getLogger(__name__)

OMDB_API_URL = "https://www.omdbapi.com/"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"

# Cache entries: {"v": CACHE_VERSION, "cached_at": epoch seconds, "data": OMDb dict or None}.
# "data" is only ever a result that passed the title/year check; None means
# "not found" and expires after NEGATIVE_CACHE_TTL so new releases get retried.
CACHE_VERSION = 2
NEGATIVE_CACHE_TTL = 7 * 24 * 60 * 60

# Every score source is optional, so keep retries and timeouts short: a slow or
# blocked site must not stall the run. (connect, read) timeouts in seconds.
_RETRY = Retry(total=1, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
_TIMEOUT = (5, 15)

# Title/year identity check
MIN_TITLE_SIMILARITY = 0.6
YEAR_TOLERANCE = 1  # UK release year can differ from the production year by one

DEFAULT_MAX_WORKERS = 4

_thread_local = threading.local()


def _make_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _thread_session() -> requests.Session:
    """One session per worker thread (requests.Session is not thread-safe)."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = _make_session()
        _thread_local.session = session
    return session




def _read_cache(key: str) -> dict | None:
    """Return a cache entry, or None if missing, corrupt, or in an old format."""
    path = CACHE_DIR / key
    if path.exists():
        try:
            entry = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt cache file: %s", path)
            return None
        if isinstance(entry, dict) and entry.get("v") == CACHE_VERSION:
            return entry
        return None  # pre-v2 files held raw, unvalidated OMDb responses
    return None


def _write_cache(key: str, data: dict | None) -> None:
    """Cache a validated OMDb result, or None for "not found"."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"v": CACHE_VERSION, "cached_at": time.time(), "data": data}
    try:
        (CACHE_DIR / key).write_text(json.dumps(entry))
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


_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+")


def _identity_title(title: str) -> str:
    """Normalize a title for identity checks.

    Like normalize_title but keeps leading articles: "The Drama" and
    "Drama" are different films.
    """
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _cache_key(title: str, year: int | None) -> str:
    # Articles are kept so "The Drama" and "Drama" do not share an entry
    raw = f"{_identity_title(title)}|{year or ''}"
    return hashlib.md5(raw.encode()).hexdigest() + ".json"


def _title_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two titles (articles kept)."""
    return SequenceMatcher(None, _identity_title(a), _identity_title(b)).ratio()


def _year_from(value: object) -> int | None:
    """Pull a 4-digit year out of '2026', '2019–2020', '2026-03-01', 2026, etc."""
    if value is None:
        return None
    match = re.search(r"(19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


def _is_same_film(
    title: str,
    year: int | None,
    candidate_title: str,
    candidate_year: int | None,
) -> bool:
    """Decide whether a search result is the film we asked about.

    - Titles must be at least MIN_TITLE_SIMILARITY alike, articles included.
    - Titles that differ only by a leading article are different films.
    - When both years are known they must be within YEAR_TOLERANCE, which
      keeps remakes and older films of the same name apart.
    """
    a = _identity_title(title)
    b = _identity_title(candidate_title)
    if not a or not b:
        return False
    if a != b and _LEADING_ARTICLE.sub("", a) == _LEADING_ARTICLE.sub("", b):
        return False
    if SequenceMatcher(None, a, b).ratio() < MIN_TITLE_SIMILARITY:
        return False
    if year and candidate_year and abs(year - candidate_year) > YEAR_TOLERANCE:
        return False
    return True


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

    imdb_id = data.get("imdbID")
    return Scores(metacritic=metacritic, imdb=imdb, rotten_tomatoes=rt, imdb_id=imdb_id)


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

    response = s.get(OMDB_API_URL, params=params, timeout=_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _apply_metadata(film: Film, data: dict) -> None:
    """Apply director and logline from OMDb data to a film."""
    director = data.get("Director")
    if director and director != "N/A" and not film.director:
        film.director = director

    logline_from_omdb = data.get("Plot")
    if logline_from_omdb and logline_from_omdb != "N/A":
        # Always prefer OMDb plot when it's shorter than scraped logline
        if not film.logline or len(logline_from_omdb) < len(film.logline):
            film.logline = logline_from_omdb


def _lookup_omdb(
    title: str,
    year: int | None,
    api_key: str,
    session: requests.Session | None = None,
) -> tuple[dict | None, bool]:
    """Search OMDb by title (+ year, then without year) and validate the result.

    Returns (data, definitive). data is an OMDb response that passed the
    title/year check, or None. definitive is False when OMDb answered with an
    error other than "not found" (rate limit, bad key...), so the caller must
    not cache the outcome.
    """
    definitive = True
    query_years = [year, None] if year else [None]
    for query_year in query_years:
        data = fetch_omdb(title, query_year, api_key, session)
        if data.get("Response") != "True":
            error = data.get("Error", "")
            if error == "Movie not found!":
                logger.info("OMDb: no result for %r (year=%s)", title, query_year)
            else:
                logger.warning("OMDb error for %r: %s", title, error or "unknown")
                definitive = False
            continue

        returned_title = data.get("Title", "")
        returned_year = _year_from(data.get("Year"))
        if not _is_same_film(title, year, returned_title, returned_year):
            logger.warning(
                "Possible mismatch for %r (%s): OMDb returned %r (%s). Ignoring.",
                title,
                year,
                returned_title,
                returned_year,
            )
            continue

        similarity = _title_similarity(title, returned_title)
        if similarity < 0.85:
            logger.info(
                "Weak match for %r: OMDb returned %r (similarity=%.2f). Accepting cautiously.",
                title,
                returned_title,
                similarity,
            )
        return data, True

    return None, definitive


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

    # Check cache first. Positive entries are re-validated (the rules may have
    # changed since they were written); negative entries expire.
    cached = _read_cache(cache_key)
    if cached is not None:
        data = cached.get("data")
        if data is None:
            age = time.time() - cached.get("cached_at", 0)
            if age < NEGATIVE_CACHE_TTL:
                film.scores = Scores()
                logger.debug("Cache hit (not found) for %r", film.title)
                return
            logger.debug("Expired not-found cache entry for %r; retrying OMDb", film.title)
        elif _is_same_film(clean_title, film.year, data.get("Title", ""), _year_from(data.get("Year"))):
            film.scores = _parse_scores(data)
            _apply_metadata(film, data)
            logger.debug("Cache hit for %r", film.title)
            return
        else:
            logger.info("Cached OMDb result for %r failed the title check; refetching", film.title)

    data, definitive = _lookup_omdb(clean_title, film.year, api_key, session)
    if definitive:
        _write_cache(cache_key, data)

    if data is None:
        film.scores = Scores()
        return

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

    resp = session.get(f"{TMDB_API_URL}/search/movie", params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        if year:
            # Retry without year (the year check below still applies)
            params.pop("year")
            resp = session.get(f"{TMDB_API_URL}/search/movie", params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        if not results:
            return None

    matches = [
        r
        for r in results[:10]
        if _is_same_film(title, year, r.get("title", ""), _year_from(r.get("release_date")))
    ]
    if not matches:
        logger.info("TMDB: no good match for %r (%s)", title, year)
        return None

    # Prefer an exact year match, then the closest title
    return max(
        matches,
        key=lambda r: (
            year is not None and _year_from(r.get("release_date")) == year,
            _title_similarity(title, r.get("title", "")),
        ),
    )


def _fetch_omdb_by_imdb_id(
    imdb_id: str,
    api_key: str,
    session: requests.Session,
) -> dict:
    """Query OMDb by IMDb ID for full scores."""
    params: dict[str, str] = {"apikey": api_key, "i": imdb_id, "type": "movie"}
    resp = session.get(OMDB_API_URL, params=params, timeout=_TIMEOUT)
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
        timeout=_TIMEOUT,
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
# IMDb scraping (no API key needed)
# ---------------------------------------------------------------------------

IMDB_SUGGEST_URL = "https://v2.sg.media-imdb.com/suggestion"
IMDB_GRAPHQL_URL = "https://caching.graphql.imdb.com/"

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _find_imdb_id(
    title: str, year: int | None, session: requests.Session
) -> str | None:
    """Search IMDb suggestions for a film and return the IMDb ID."""
    query = re.sub(r"[^\w\s]", "", title.lower()).replace(" ", "_")[:20]
    first_char = query[0] if query else "a"
    url = f"{IMDB_SUGGEST_URL}/{first_char}/{query}.json"

    resp = session.get(url, headers=_BROWSER_HEADERS, timeout=_TIMEOUT)
    if resp.status_code != 200:
        return None

    results = resp.json().get("d", [])
    # Filter to movies only
    movies = [r for r in results if r.get("qid") in ("movie", "tvMovie")]
    if not movies:
        return None

    matches = [m for m in movies if _is_same_film(title, year, m.get("l", ""), m.get("y"))]
    if not matches:
        return None

    # Prefer an exact year match, then the closest title
    best = max(
        matches,
        key=lambda m: (year is not None and m.get("y") == year, _title_similarity(title, m.get("l", ""))),
    )
    return best["id"]


def _fetch_imdb_rating(
    imdb_id: str, session: requests.Session
) -> float | None:
    """Fetch IMDb rating via the public GraphQL endpoint."""
    query = (
        '{ title(id: "' + imdb_id + '") { '
        "ratingsSummary { aggregateRating voteCount } } }"
    )
    resp = session.post(
        IMDB_GRAPHQL_URL,
        json={"query": query},
        headers={**_BROWSER_HEADERS, "content-type": "application/json"},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    rating = (
        data.get("data", {})
        .get("title", {})
        .get("ratingsSummary", {})
        .get("aggregateRating")
    )
    if rating and isinstance(rating, (int, float)):
        return round(float(rating), 1)
    return None


def _enrich_from_imdb(film: Film, session: requests.Session) -> None:
    """Fill missing IMDb score and ID by scraping IMDb directly."""
    if film.scores and film.scores.imdb is not None and film.scores.imdb_id:
        return

    clean = _clean_title_for_search(film.title)
    imdb_id = _find_imdb_id(clean, film.year, session)
    if not imdb_id:
        logger.debug("IMDb: no ID found for %r", film.title)
        return

    if film.scores is None:
        film.scores = Scores()
    film.scores.imdb_id = imdb_id

    if film.scores.imdb is None:
        rating = _fetch_imdb_rating(imdb_id, session)
        if rating:
            film.scores.imdb = rating
            logger.info("IMDb scrape: %r → %.1f (ID=%s)", film.title, rating, imdb_id)


# ---------------------------------------------------------------------------
# Metacritic scraping (no API key needed)
# ---------------------------------------------------------------------------

MC_MOVIE_URL = "https://www.metacritic.com/movie"


def _mc_slug(title: str) -> str:
    """Convert a film title to a Metacritic URL slug (keeps articles)."""
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s


def _fetch_mc_score(
    title: str, year: int | None, session: requests.Session
) -> tuple[int | None, str | None]:
    """Fetch Metacritic score from the movie page. Returns (score, slug).

    Each candidate page is checked against the title and year from its
    JSON-LD, so a same-title older film is not picked up.
    """
    slug = _mc_slug(title)
    # Also try without leading article for edge cases
    slug_no_article = re.sub(r"^(the|a|an)-", "", slug)
    candidates = []
    if year:
        # Metacritic disambiguates newer same-title films with a year suffix
        candidates.append(f"{slug}-{year}")
    candidates.append(slug)
    if slug_no_article != slug:
        candidates.append(slug_no_article)

    for candidate in candidates:
        url = f"{MC_MOVIE_URL}/{candidate}/"
        resp = session.get(url, headers=_BROWSER_HEADERS, timeout=_TIMEOUT)
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if not isinstance(data, dict):
                    continue
                page_title = data.get("name")
                page_year = _year_from(data.get("datePublished"))
                if page_title and not _is_same_film(title, year, page_title, page_year):
                    logger.debug("MC: %s is %r (%s), not %r (%s)", candidate, page_title, page_year, title, year)
                    continue
                rating = data.get("aggregateRating", {})
                score = rating.get("ratingValue")
                if score is not None:
                    return int(score), candidate
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

    return None, None


def _enrich_from_mc(film: Film, session: requests.Session) -> None:
    """Fill missing Metacritic score by scraping metacritic.com."""
    if film.scores and film.scores.metacritic is not None:
        return

    clean = _clean_title_for_search(film.title)
    score, slug = _fetch_mc_score(clean, film.year, session)

    if film.scores is None:
        film.scores = Scores()

    if slug:
        film.scores.mc_slug = slug
    if score is not None:
        film.scores.metacritic = score
        logger.info("MC scrape: %r → %d (slug=%s)", film.title, score, slug)


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
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    # Movie result links look like /m/some_slug or full URLs containing /m/
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # Handle both relative (/m/slug) and absolute (https://...com/m/slug) URLs
        if "/m/" in href:
            # Extract the /m/slug portion
            idx = href.index("/m/")
            slug = href[idx:]
            # Check the link text (and release year, when shown) match our film
            link_text = a_tag.get_text(strip=True)
            row = a_tag.find_parent("search-page-media-row")
            release_year = _year_from(row.get("release-year")) if row else None
            if link_text and _is_same_film(title, year, link_text, release_year):
                return slug
    return None


def _scrape_rt_scores(slug: str, session: requests.Session) -> tuple[int | None, int | None]:
    """Scrape RT movie page for (tomatometer, audience_score).

    Extracts from JSON-LD structured data embedded in the page.
    """
    resp = session.get(
        f"{RT_BASE}{slug}",
        headers=_RT_HEADERS,
        timeout=_TIMEOUT,
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
    if film.scores is None:
        film.scores = Scores()
    film.scores.rt_slug = slug
    if tomatometer is not None:
        film.scores.rotten_tomatoes = tomatometer
        logger.info("RT scrape: %r → %d%%", film.title, tomatometer)


# ---------------------------------------------------------------------------
# Logline fallback — check multiple sources for a short logline
# ---------------------------------------------------------------------------

LOGLINE_CAP = 180


def _fetch_imdb_plot(imdb_id: str, session: requests.Session) -> str | None:
    """Get a short plot summary from IMDb GraphQL (clean, concise)."""
    try:
        query = (
            '{ title(id: "' + imdb_id + '") { '
            "plot { plotText { plainText } } } }"
        )
        resp = session.post(
            IMDB_GRAPHQL_URL,
            json={"query": query},
            headers={**_BROWSER_HEADERS, "content-type": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        plot = (
            resp.json()
            .get("data", {})
            .get("title", {})
            .get("plot", {})
            .get("plotText", {})
            .get("plainText")
        )
        if plot and len(plot) > 20:
            return plot
    except Exception:
        pass
    return None


def _is_real_logline(text: str) -> bool:
    """Filter out SEO filler that isn't a real plot description."""
    filler = [
        "discover reviews",
        "stay updated",
        "critic and audience scores",
        "rotten tomatoes",
        "metacritic",
    ]
    lower = text.lower()
    return not any(f in lower for f in filler)


def _enrich_logline(film: Film, session: requests.Session) -> None:
    """For a film with a long logline, check IMDb for a shorter alternative."""
    if film.logline and len(film.logline) <= LOGLINE_CAP:
        return  # already short enough

    candidates: list[str] = []
    if film.logline and _is_real_logline(film.logline):
        candidates.append(film.logline)

    # Best source: IMDb plot (concise, always a real synopsis)
    if film.scores and film.scores.imdb_id:
        alt = _fetch_imdb_plot(film.scores.imdb_id, session)
        if alt and _is_real_logline(alt):
            candidates.append(alt)

    if not candidates:
        return

    # Prefer one that fits the cap; if none fit, take shortest
    under_cap = [c for c in candidates if len(c) <= LOGLINE_CAP]
    if under_cap:
        film.logline = max(under_cap, key=len)
    else:
        film.logline = min(candidates, key=len)

    logger.debug(
        "Logline for %r: %d chars %s",
        film.title,
        len(film.logline),
        "(OK)" if len(film.logline) <= LOGLINE_CAP else "(long)",
    )


# ---------------------------------------------------------------------------
# Picturehouse booking links (scrape film codes from PH website)
# ---------------------------------------------------------------------------


def _fetch_ph_film_codes(session: requests.Session) -> dict[str, tuple[str, str]]:
    """Fetch film HO codes from Picturehouse whats-on page.

    Returns dict mapping normalized title -> (ho_code, slug).
    """
    resp = session.get(PH_WHATS_ON_URL, headers=_BROWSER_HEADERS, timeout=_TIMEOUT)
    if resp.status_code != 200:
        logger.warning("Failed to fetch PH whats-on: %d", resp.status_code)
        return {}

    codes: dict[str, tuple[str, str]] = {}
    for match in re.finditer(r'/movie-details/\d+/(HO\d+)/([^?"]+)', resp.text):
        ho_code, slug = match.group(1), match.group(2)
        norm = normalize_title(slug.replace("-", " "))
        codes[norm] = (ho_code, slug)

    logger.info("Fetched %d PH film codes", len(codes))
    return codes


def _build_ph_url(ho_code: str, slug: str, cinema: str) -> str:
    """Build a Picturehouse movie-details URL."""
    code = CINEMA_CODES.get(cinema, "000")
    return f"https://www.picturehouses.com/movie-details/{code}/{ho_code}/{slug}"


def _enrich_ph_links(films: list[Film], session: requests.Session) -> None:
    """Set ph_url on each film by matching against PH website."""
    try:
        codes = _fetch_ph_film_codes(session)
    except Exception:
        logger.exception("Failed to fetch PH film codes")
        return

    for film in films:
        norm = normalize_title(film.title)
        match = codes.get(norm)
        if match:
            ho_code, slug = match
            first = min(film.screenings, key=lambda s: s.date)
            film.ph_url = _build_ph_url(ho_code, slug, first.cinema)
            logger.debug("PH link: %r → %s", film.title, film.ph_url)
        else:
            logger.debug("PH: no match for %r", film.title)


def _enrich_tmdb_fallback(
    film: Film,
    omdb_key: str,
    tmdb_key: str,
    session: requests.Session,
) -> None:
    """TMDB → IMDb ID → OMDb, then basic TMDB data, for films with no scores yet."""
    scores = film.scores
    has_any = scores and (
        scores.metacritic is not None
        or scores.imdb is not None
        or scores.rotten_tomatoes is not None
    )
    if has_any:
        return

    found = _enrich_via_tmdb_imdb(film, omdb_key, tmdb_key, session)
    if not found:
        # Fall back to basic TMDB data (vote_average as IMDb-style)
        clean = _clean_title_for_search(film.title)
        tmdb_data = _fetch_tmdb(clean, film.year, tmdb_key, session)
        if tmdb_data:
            _apply_tmdb_data(film, tmdb_data)
            logger.info("TMDB fallback enriched %r", film.title)


def _expired(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _enrich_one(
    film: Film,
    api_key: str,
    tmdb_api_key: str,
    session: requests.Session,
    deadline: float | None,
) -> Film:
    """Run every score source for one film, stopping early at the deadline.

    Each source's failure is logged and skipped. If the deadline passes before
    a score source was tried, the film is marked scores_incomplete.
    """
    # (name, is_score_source, step)
    steps: list[tuple[str, bool, object]] = []
    if api_key:
        steps.append(("OMDb", True, lambda: enrich_film(film, api_key, session=session)))
        if tmdb_api_key:
            steps.append(
                ("TMDB", True, lambda: _enrich_tmdb_fallback(film, api_key, tmdb_api_key, session))
            )
    steps += [
        ("IMDb", True, lambda: _enrich_from_imdb(film, session)),
        ("Metacritic", True, lambda: _enrich_from_mc(film, session)),
        ("Rotten Tomatoes", True, lambda: _enrich_from_rt(film, session)),
        ("logline", False, lambda: _enrich_logline(film, session)),
    ]

    for name, is_score_source, step in steps:
        if _expired(deadline):
            if is_score_source:
                film.scores_incomplete = True
                logger.warning("Time budget used up before %s lookup for %r", name, film.title)
            break
        try:
            step()
        except Exception:
            logger.exception("%s lookup failed for %r", name, film.title)

    if film.scores is None:
        film.scores = Scores()
    return film


def _copy_enrichment(src: Film, dst: Film) -> None:
    dst.scores = src.scores
    dst.director = src.director
    dst.logline = src.logline
    dst.scores_incomplete = src.scores_incomplete


def _mark_incomplete(film: Film) -> None:
    if film.scores is None:
        film.scores = Scores()
    film.scores_incomplete = True


def _enrich_concurrently(
    films: list[Film],
    api_key: str,
    tmdb_api_key: str,
    deadline: float | None,
    max_workers: int,
) -> None:
    """Enrich films in parallel, each worker on a copy with its own session.

    Results are copied back only for films that finished before the deadline;
    the rest are marked scores_incomplete. Stragglers are abandoned (they stop
    at their next deadline check, within one request timeout).
    """

    def work(film: Film) -> Film:
        return _enrich_one(copy.deepcopy(film), api_key, tmdb_api_key, _thread_session(), deadline)

    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="enrich")
    try:
        futures = {executor.submit(work, film): film for film in films}
        timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
        done, _ = wait(futures, timeout=timeout)
        for future, film in futures.items():
            if future in done and future.exception() is None:
                _copy_enrichment(future.result(), film)
            else:
                _mark_incomplete(film)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def enrich_films(
    films: list[Film],
    api_key: str,
    tmdb_api_key: str = "",
    session: requests.Session | None = None,
    time_budget: float | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> None:
    """Enrich all films with scores. Failures are logged but do not propagate.

    time_budget (seconds) caps the whole enrichment: films whose lookups did
    not finish in time keep whatever they have and are marked
    scores_incomplete. With an explicit session (or max_workers=1) films are
    processed one at a time on that session; otherwise up to max_workers
    films are looked up concurrently.
    """
    deadline = time.monotonic() + time_budget if time_budget is not None else None

    if not api_key:
        logger.warning("No OMDb API key configured; OMDb scores will be N/A")

    if session is not None or max_workers <= 1:
        s = session or _make_session()
        for film in films:
            if _expired(deadline):
                _mark_incomplete(film)
                continue
            _enrich_one(film, api_key, tmdb_api_key, s, deadline)
    else:
        _enrich_concurrently(films, api_key, tmdb_api_key, deadline, max_workers)

    # Picturehouse booking links
    if _expired(deadline):
        logger.warning("Skipping Picturehouse film links: time budget used up")
    else:
        _enrich_ph_links(films, session or _make_session())

    incomplete = sum(1 for f in films if f.scores_incomplete)
    if incomplete:
        logger.warning("Scores incomplete for %d film(s): time budget used up", incomplete)
