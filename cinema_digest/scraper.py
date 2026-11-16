"""Scrape film listings from Data Thistle cinema pages."""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cinema_digest.config import CINEMA_URLS, CINEMAS, MIN_FILMS_PER_CINEMA
from cinema_digest.models import Film, Screening, ScrapeResult
from cinema_digest.ph_scraper import PicturehouseUnavailable, fetch_ph_pages, parse_ph_listings

logger = logging.getLogger(__name__)

LONDON_TZ = ZoneInfo("Europe/London")
DATA_THISTLE_BASE = "https://film.datathistle.com"

# Retry strategy for HTTP requests
_RETRY = Retry(total=2, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])

# (connect, read) timeouts in seconds
_TIMEOUT = (10, 30)

# How far back a date header may be before we assume it belongs to next year
_MAX_PAST_DAYS = 60


def _make_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {"User-Agent": "CinemaDigest/1.0 (personal film listing aggregator)"}
    )
    return session


def fetch_page(
    url: str,
    session: requests.Session | None = None,
    timeout: float | tuple[float, float] = _TIMEOUT,
) -> str:
    """Fetch a page with retries and timeout."""
    s = session or _make_session()
    response = s.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def normalize_title(title: str) -> str:
    """Normalize a title for comparison/merging.

    Lowercases, strips leading articles, removes punctuation,
    collapses whitespace, and normalizes unicode.
    """
    t = unicodedata.normalize("NFKD", title)
    t = t.lower().strip()
    t = re.sub(r"^(the|a|an)\s+", "", t)
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_date_header(text: str, today: date | None = None) -> date | None:
    """Parse a date header like 'Mon 9 Mar' into a date object.

    The header has no year, so we pick this year or next year: the first
    candidate that is no more than 60 days in the past (handles the Dec/Jan
    crossover). If the weekday prefix matches exactly one candidate, that
    candidate wins. 29 Feb is only accepted in a leap year.
    """
    if today is None:
        today = datetime.now(LONDON_TZ).date()

    text = text.strip()
    # Split day-of-week prefix: "Mon 9 Mar" -> "Mon", "9 Mar"
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    weekday, day_month = parts

    try:
        # 2000 is a leap year, so "29 Feb" validates here
        parsed = datetime.strptime(f"{day_month} 2000", "%d %b %Y")
    except ValueError:
        logger.warning("Could not parse date header: %r", text)
        return None

    candidates = []
    for year in (today.year, today.year + 1):
        try:
            d = date(year, parsed.month, parsed.day)
        except ValueError:  # 29 Feb in a non-leap year
            continue
        if (today - d).days <= _MAX_PAST_DAYS:
            candidates.append(d)

    if not candidates:
        logger.warning("Could not place date header in a year: %r", text)
        return None

    matching_weekday = [d for d in candidates if d.strftime("%a").lower() == weekday[:3].lower()]
    if len(matching_weekday) == 1:
        return matching_weekday[0]
    return candidates[0]


def _parse_time_text(time_text: str) -> time | None:
    """Parse a time string like '12:00' or '9:30' into a time object."""
    time_text = time_text.strip()
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_text)
    if not match:
        logger.warning("Could not parse time: %r", time_text)
        return None
    return time(int(match.group(1)), int(match.group(2)))


def _extract_year(metadata_items: list[str]) -> int | None:
    """Extract a 4-digit year from metadata list items."""
    for item in metadata_items:
        match = re.match(r"^(19|20)\d{2}$", item.strip())
        if match:
            return int(match.group(0))
    return None


def _extract_duration(metadata_items: list[str]) -> str | None:
    """Extract duration string like '2h 6min' from metadata."""
    for item in metadata_items:
        if re.search(r"\d+h|\d+min", item):
            return item.strip()
    return None


def _dedupe_screenings(screenings: list[Screening]) -> list[Screening]:
    """Drop repeated showtimes (same cinema, same start time), keeping the first."""
    seen: set[tuple[str, datetime]] = set()
    unique: list[Screening] = []
    for s in screenings:
        key = (s.cinema, s.date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return unique


def _extract_film_blocks(soup: BeautifulSoup) -> list[tuple[Tag, list[Tag]]]:
    """Extract film blocks from the page.

    Returns list of (h4_tag, [sibling_tags_until_next_h4]).
    Each h4 starts a new film; everything between it and the next h4
    belongs to that film.
    """
    h4s = soup.find_all("h4")
    if not h4s:
        return []

    blocks = []
    for h4 in h4s:
        siblings = []
        for sib in h4.next_siblings:
            if isinstance(sib, Tag):
                if sib.name == "h4":
                    break
                siblings.append(sib)
        blocks.append((h4, siblings))
    return blocks


def _flatten_elements(siblings: list[Tag]) -> list[Tag]:
    """Flatten the element tree for parsing.

    Data Thistle wraps metadata and showtime elements inside <div> containers.
    This function yields a flat sequence of the meaningful elements (h5, h6,
    ul, p, etc.) regardless of whether they are direct siblings or nested
    inside divs.
    """
    result: list[Tag] = []
    for sib in siblings:
        if not isinstance(sib, Tag):
            continue
        if sib.name == "div":
            # Descend into div children
            for child in sib.children:
                if isinstance(child, Tag):
                    result.append(child)
        else:
            result.append(sib)
    return result


def _parse_film_block(
    h4: Tag, siblings: list[Tag], cinema_name: str, today: date | None = None
) -> Film | None:
    """Parse a single film block into a Film object."""
    # Extract title and listing URL
    link = h4.find("a")
    if not link:
        logger.warning("h4 without link, skipping: %s", h4.get_text(strip=True))
        return None

    title = link.get_text(strip=True)
    href = link.get("href", "")
    listing_url = f"{DATA_THISTLE_BASE}{href}" if href.startswith("/") else href

    # Flatten the element tree -- Data Thistle wraps content in <div>s
    elements = _flatten_elements(siblings)

    # Walk flattened elements to extract metadata, logline, and showtimes
    year = None
    duration = None
    logline = None
    screenings: list[Screening] = []
    current_date: date | None = None
    current_screening_type: str | None = None
    found_first_metadata_ul = False

    for elem in elements:
        # Date header
        if elem.name == "h5":
            date_text = elem.get_text(strip=True)
            current_date = _parse_date_header(date_text, today)
            current_screening_type = None  # reset on new date
            continue

        # Screening type label
        if elem.name == "h6":
            current_screening_type = elem.get_text(strip=True) or None
            continue

        # Description paragraph (take first meaningful one as logline)
        if elem.name == "p" and logline is None:
            # A separator keeps words apart across inline tags (<b>, <i>, <a>).
            text = re.sub(r"\s+([,.;:!?)])", r"\1", elem.get_text(" ", strip=True))
            if text and len(text) > 10:
                logline = text
            continue

        # Lists: either metadata or showtimes
        if elem.name == "ul":
            items = elem.find_all("li")

            # Check if this is a metadata list (first ul before any h5 that
            # carries a year or a duration; either may be missing)
            if current_date is None and not found_first_metadata_ul:
                item_texts = [li.get_text(strip=True) for li in items]
                extracted_year = _extract_year(item_texts)
                extracted_duration = _extract_duration(item_texts)
                if extracted_year or extracted_duration:
                    year = extracted_year
                    duration = extracted_duration
                    found_first_metadata_ul = True
                    continue

            # Otherwise, it's a showtime list (if we have a current date)
            if current_date is not None:
                for li in items:
                    time_link = li.find("a")
                    if not time_link:
                        continue

                    time_text = time_link.get_text(strip=True)
                    booking_url = time_link.get("href", "")

                    parsed_time = _parse_time_text(time_text)
                    if parsed_time is None:
                        continue

                    screening_dt = datetime(
                        current_date.year,
                        current_date.month,
                        current_date.day,
                        parsed_time.hour,
                        parsed_time.minute,
                        tzinfo=LONDON_TZ,
                    )

                    screenings.append(
                        Screening(
                            cinema=cinema_name,
                            date=screening_dt,
                            booking_url=booking_url,
                            screening_type=current_screening_type,
                        )
                    )

                # Reset screening type after consuming a showtime list
                current_screening_type = None

    if not title:
        return None

    return Film(
        title=title,
        year=year,
        duration=duration,
        logline=logline,
        listing_url=listing_url,
        screenings=_dedupe_screenings(screenings),
    )


def parse_cinema(html: str, cinema_name: str, today: date | None = None) -> list[Film]:
    """Parse a Data Thistle cinema page into a list of Film objects."""
    soup = BeautifulSoup(html, "html.parser")
    blocks = _extract_film_blocks(soup)

    films = []
    for h4, siblings in blocks:
        try:
            film = _parse_film_block(h4, siblings, cinema_name, today)
            if film:
                films.append(film)
        except Exception:
            title_text = h4.get_text(strip=True) if h4 else "unknown"
            logger.exception("Failed to parse film block for %r", title_text)

    logger.info("Parsed %d films from %s", len(films), cinema_name)
    return films


def _merge_key(film: Film, merged: dict[tuple[str, int | None], Film]) -> tuple[str, int | None]:
    """Pick the merge key for a film: normalized title plus year.

    Films with the same title but different known years (remakes) stay
    separate. A film with no year joins the only film of that title, or an
    undated one; a dated film joins the same year, or an undated one.
    """
    title_key = normalize_title(film.title)
    same_title = [k for k in merged if k[0] == title_key]
    if film.year is None:
        if len(same_title) == 1:
            return same_title[0]
        undated = [k for k in same_title if merged[k].year is None]
        return undated[0] if undated else (title_key, None)
    for k in same_title:
        if merged[k].year == film.year:
            return k
    for k in same_title:
        if merged[k].year is None:
            return k
    return (title_key, film.year)


def merge_films(all_films: list[Film]) -> list[Film]:
    """Merge films from different cinemas that are the same film.

    Uses normalized title plus year as merge key, so remakes that share a
    title are kept apart. Combines screenings (dropping repeated showtimes)
    and keeps the richer metadata from whichever Film has more data.
    """
    merged: dict[tuple[str, int | None], Film] = {}

    for film in all_films:
        key = _merge_key(film, merged)
        if key in merged:
            existing = merged[key]
            existing.screenings = _dedupe_screenings(existing.screenings + film.screenings)
            # Keep richer metadata
            if film.logline and (not existing.logline or len(film.logline) > len(existing.logline)):
                existing.logline = film.logline
            if film.year and not existing.year:
                existing.year = film.year
            if film.duration and not existing.duration:
                existing.duration = film.duration
            if film.listing_url and not existing.listing_url:
                existing.listing_url = film.listing_url
            if film.ph_url and not existing.ph_url:
                existing.ph_url = film.ph_url
            if film.director and not existing.director:
                existing.director = film.director
        else:
            merged[key] = Film(
                title=film.title,
                year=film.year,
                duration=film.duration,
                logline=film.logline,
                listing_url=film.listing_url,
                director=film.director,
                ph_url=film.ph_url,
                screenings=_dedupe_screenings(list(film.screenings)),
            )

    return list(merged.values())


def combine_sources(ph_films: list[Film], dt_films: list[Film]) -> tuple[list[Film], int, int]:
    """Combine one cinema's Picturehouse and Data Thistle listings.

    Picturehouse is the primary source. Data Thistle adds its year and
    description (used to look up scores) and any film or showtime the
    Picturehouse page did not show, so nothing listed in either place is lost.
    Returns (films, films only on Data Thistle, showtimes only on Data Thistle).
    """
    combined = [
        Film(
            title=f.title,
            duration=f.duration,
            ph_url=f.ph_url,
            screenings=list(f.screenings),
        )
        for f in ph_films
    ]
    by_title = {normalize_title(f.title): f for f in combined}
    extra_films = 0
    extra_times = 0

    for dt in dt_films:
        match = by_title.get(normalize_title(dt.title))
        if match is None:
            combined.append(dt)
            by_title[normalize_title(dt.title)] = dt
            extra_films += 1
            logger.info("Only on Data Thistle: %r", dt.title)
            continue
        match.year = match.year or dt.year
        match.logline = match.logline or dt.logline
        match.listing_url = match.listing_url or dt.listing_url
        if dt.duration and not match.duration:
            match.duration = dt.duration
        known = {(s.cinema, s.date) for s in match.screenings}
        for s in dt.screenings:
            if (s.cinema, s.date) not in known:
                match.screenings.append(s)
                known.add((s.cinema, s.date))
                extra_times += 1
                logger.info("Showtime only on Data Thistle: %r %s", dt.title, s.date)
        match.screenings.sort(key=lambda s: s.date)

    return combined, extra_films, extra_times


_DEFAULT_PH_FETCHER = object()


def scrape_all(
    session: requests.Session | None = None,
    today: date | None = None,
    ph_fetcher=_DEFAULT_PH_FETCHER,
) -> ScrapeResult:
    """Fetch and parse listings from all configured cinemas.

    Reads each cinema's own Picturehouse page first and adds anything extra
    that Data Thistle lists. Pass ph_fetcher=None to use Data Thistle only.

    Never raises for a single cinema: a failed fetch, an unusually low film
    count, or films with no readable showtimes are recorded as warnings on
    the result so the digest can still be sent and flag the problem.
    """
    s = session or _make_session()
    result = ScrapeResult()
    all_films: list[Film] = []

    ph_pages: dict[str, str] = {}
    if ph_fetcher is not None:
        fetcher = fetch_ph_pages if ph_fetcher is _DEFAULT_PH_FETCHER else ph_fetcher
        try:
            ph_pages = fetcher(CINEMA_URLS)
        except PicturehouseUnavailable as e:
            logger.error("Picturehouse pages unavailable: %s", e)
        except Exception:
            logger.exception("Unexpected error reading the Picturehouse pages")

    result.pages = dict(ph_pages)

    def used(source: str) -> None:
        if source not in result.sources:
            result.sources.append(source)

    for cinema_name, url in CINEMAS.items():
        ph_films: list[Film] = []
        if cinema_name in ph_pages:
            ph_films = parse_ph_listings(ph_pages[cinema_name], cinema_name)
        if ph_fetcher is not None and not ph_films:
            # Data Thistle alone has missed most of the programme before, so
            # this flags the subject, not just a note in the body.
            result.warnings.append(
                f"The {cinema_name} Picturehouse page could not be read, so its films come "
                f"from Data Thistle only, which can miss most of the programme."
            )
            result.listings_suspect = True

        logger.info("Fetching Data Thistle listings for %s from %s", cinema_name, url)
        dt_films: list[Film] = []
        dt_error: str | None = None
        try:
            html = fetch_page(url, session=s)
            dt_films = parse_cinema(html, cinema_name, today)
        except requests.RequestException as e:
            logger.error("Could not fetch %s Data Thistle listings: %s", cinema_name, e)
            dt_error = type(e).__name__

        if dt_error and not ph_films:
            result.warnings.append(
                f"Could not fetch the {cinema_name} listings ({dt_error}); "
                f"{cinema_name} films are missing from this digest."
            )
            result.listings_suspect = True
            continue

        if ph_films:
            films, extra_films, extra_times = combine_sources(ph_films, dt_films)
            logger.info(
                "%s: %d films from Picturehouse, plus %d film(s) and %d showtime(s) only on Data Thistle",
                cinema_name, len(ph_films), extra_films, extra_times,
            )
            used("Picturehouse")
            if extra_films or extra_times:
                used("Data Thistle")
        else:
            films = dt_films
            if dt_films:
                used("Data Thistle")

        screening_count = sum(len(f.screenings) for f in films)

        if len(films) < MIN_FILMS_PER_CINEMA:
            logger.warning("Only %d films found for %s", len(films), cinema_name)
            result.warnings.append(
                f"Only {len(films)} film(s) found for {cinema_name}, which is unusually low "
                f"(a normal week has 60 or more). The listings are probably incomplete."
            )
            result.listings_suspect = True
        if films and screening_count == 0:
            logger.warning("%d films but no showtimes parsed for %s", len(films), cinema_name)
            result.warnings.append(
                f"{len(films)} film(s) found for {cinema_name} but no showtimes could be read. "
                f"The listings page may have changed."
            )
            result.listings_suspect = True

        all_films.extend(films)

    result.films = merge_films(all_films)
    logger.info("Total unique films after merging: %d", len(result.films))
    return result
