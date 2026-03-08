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

from cinema_digest.config import CINEMAS, MIN_FILMS_PER_CINEMA
from cinema_digest.models import Film, Screening

logger = logging.getLogger(__name__)

LONDON_TZ = ZoneInfo("Europe/London")
DATA_THISTLE_BASE = "https://film.datathistle.com"

# Retry strategy for HTTP requests
_RETRY = Retry(total=3, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])


class ScraperError(Exception):
    """Raised when scraping fails in a way that indicates structural breakage."""


def _make_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {"User-Agent": "CinemaDigest/1.0 (personal film listing aggregator)"}
    )
    return session


def fetch_page(url: str, session: requests.Session | None = None, timeout: int = 30) -> str:
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


def _parse_date_header(text: str, reference_year: int) -> date | None:
    """Parse a date header like 'Mon 9 Mar' into a date object.

    Uses reference_year, adjusting to next year if the resulting date
    is more than 60 days in the past (handles Dec/Jan crossover).
    """
    text = text.strip()
    # Strip day-of-week prefix: "Mon 9 Mar" -> "9 Mar"
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    day_month = parts[1]

    try:
        parsed = datetime.strptime(f"{day_month} {reference_year}", "%d %b %Y")
    except ValueError:
        logger.warning("Could not parse date header: %r", text)
        return None

    today = datetime.now(LONDON_TZ).date()
    if (today - parsed.date()).days > 60:
        parsed = parsed.replace(year=reference_year + 1)

    return parsed.date()


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
    h4: Tag, siblings: list[Tag], cinema_name: str, reference_year: int
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
            current_date = _parse_date_header(date_text, reference_year)
            current_screening_type = None  # reset on new date
            continue

        # Screening type label
        if elem.name == "h6":
            current_screening_type = elem.get_text(strip=True) or None
            continue

        # Description paragraph (take first meaningful one as logline)
        if elem.name == "p" and logline is None:
            text = elem.get_text(strip=True)
            if text and len(text) > 10:
                logline = text
            continue

        # Lists: either metadata or showtimes
        if elem.name == "ul":
            items = elem.find_all("li")

            # Check if this is a metadata list (first ul before any h5)
            if current_date is None and not found_first_metadata_ul:
                item_texts = [li.get_text(strip=True) for li in items]
                extracted_year = _extract_year(item_texts)
                if extracted_year:
                    year = extracted_year
                    duration = _extract_duration(item_texts)
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
        screenings=screenings,
    )


def parse_cinema(html: str, cinema_name: str) -> list[Film]:
    """Parse a Data Thistle cinema page into a list of Film objects."""
    soup = BeautifulSoup(html, "html.parser")
    blocks = _extract_film_blocks(soup)
    reference_year = datetime.now(LONDON_TZ).year

    films = []
    for h4, siblings in blocks:
        try:
            film = _parse_film_block(h4, siblings, cinema_name, reference_year)
            if film:
                films.append(film)
        except Exception:
            title_text = h4.get_text(strip=True) if h4 else "unknown"
            logger.exception("Failed to parse film block for %r", title_text)

    logger.info("Parsed %d films from %s", len(films), cinema_name)
    return films


def merge_films(all_films: list[Film]) -> list[Film]:
    """Merge films from different cinemas that share the same title.

    Uses normalized title as merge key. Combines screenings and keeps
    the richer metadata from whichever Film has more data.
    """
    merged: dict[str, Film] = {}

    for film in all_films:
        key = normalize_title(film.title)
        if key in merged:
            existing = merged[key]
            existing.screenings.extend(film.screenings)
            # Keep richer metadata
            if film.logline and (not existing.logline or len(film.logline) > len(existing.logline)):
                existing.logline = film.logline
            if film.year and not existing.year:
                existing.year = film.year
            if film.duration and not existing.duration:
                existing.duration = film.duration
            if film.listing_url and not existing.listing_url:
                existing.listing_url = film.listing_url
        else:
            merged[key] = Film(
                title=film.title,
                year=film.year,
                duration=film.duration,
                logline=film.logline,
                listing_url=film.listing_url,
                screenings=list(film.screenings),
            )

    return list(merged.values())


def scrape_all(session: requests.Session | None = None) -> list[Film]:
    """Fetch and parse listings from all configured cinemas.

    Returns merged list of films with screenings from all cinemas.
    Raises ScraperError if any cinema returns suspiciously few results.
    """
    s = session or _make_session()
    all_films: list[Film] = []

    for cinema_name, url in CINEMAS.items():
        logger.info("Fetching listings for %s from %s", cinema_name, url)
        html = fetch_page(url, session=s)
        films = parse_cinema(html, cinema_name)

        if len(films) < MIN_FILMS_PER_CINEMA:
            raise ScraperError(
                f"Only found {len(films)} films for {cinema_name} "
                f"(expected at least {MIN_FILMS_PER_CINEMA}). "
                f"The page structure may have changed."
            )

        all_films.extend(films)

    merged = merge_films(all_films)
    logger.info("Total unique films after merging: %d", len(merged))
    return merged
