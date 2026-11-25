"""Read film listings straight from the Picturehouse cinema pages.

Picturehouse does not put showtimes in the page HTML. The page's own script
loads them after it opens, so we open the page in a headless browser, wait
for the listings to appear, and parse what is shown. This is the same view a
person gets in their browser, which is why it is the primary source.
Data Thistle stays as a backup (see scraper.scrape_all).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, time

from bs4 import BeautifulSoup, Tag

from cinema_digest.config import CINEMA_CODES
from cinema_digest.models import Film, Screening

logger = logging.getLogger(__name__)

from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")

# A day block on the page: <div class="show_all_dates_class class_2026-11-14">
_DAY_CLASS = re.compile(r"^class_(\d{4})-(\d{2})-(\d{2})$")

# Picturehouse lists some accessible or special screenings as their own film,
# e.g. "Relaxed:Shaun the Sheep..." or "Dog-Friendly - Ghosts...". Fold these
# into the main film as a screening type, so the digest shows one entry.
_SPECIAL_PREFIX = re.compile(
    r"^(?P<label>dog[- ]friendly(?: screening)?|relaxed(?: screening)?)\s*[:\-–]\s*(?P<title>.+)$",
    re.IGNORECASE,
)

# Labels on (nearly) every showing that tell you nothing when choosing a film
_IGNORED_LABELS = {"laser projection"}

# How long to wait for the listings to render, in milliseconds
_PAGE_TIMEOUT_MS = 60_000
_LISTINGS_TIMEOUT_MS = 45_000
_LISTING_SELECTOR = ".show_all_dates_class .cinemaList_box"

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


class PicturehouseUnavailable(Exception):
    """The Picturehouse page could not be opened or showed no listings."""


def split_special_title(title: str) -> tuple[str, str | None]:
    """Return (main title, screening label) for special-screening titles."""
    m = _SPECIAL_PREFIX.match(title.strip())
    if not m:
        return title.strip(), None
    label = m.group("label").strip()
    label = "Dog Friendly" if label.lower().startswith("dog") else "Relaxed"
    return m.group("title").strip(), label


def loose_key(title: str) -> str:
    """Match key that ignores case, punctuation and the words the/a/an.

    Picturehouse's special-screening titles sometimes drop an article
    ("Dog-Friendly - Ghosts: Possession of Button House").
    """
    t = re.sub(r"[^\w\s]", " ", title.lower())
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_loose_key = loose_key


def _title_of(box: Tag) -> str | None:
    h3 = box.select_one(".hideOnMob h3") or box.select_one("h3")
    if h3 is None:
        return None
    # The rating and running time sit inside the h3; take the text before them
    for node in h3.children:
        text = node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node).strip()
        if text:
            return text
    return None


def _booking_url(link: Tag, cinema_name: str) -> str:
    href = link.get("href", "") or ""
    if href.startswith("http"):
        return href
    # Some sessions (e.g. Kids' Club) have a javascript: link; build the
    # standard booking link from the session ID instead.
    session_id = link.get("data-sessionid")
    code = CINEMA_CODES.get(cinema_name)
    if session_id and code:
        return f"https://web.picturehouses.com/order/showtimes/{code}-{session_id}/seats"
    return ""


def parse_ph_listings(html: str, cinema_name: str) -> list[Film]:
    """Parse a rendered Picturehouse cinema page into films with screenings."""
    soup = BeautifulSoup(html, "html.parser")
    films: dict[str, Film] = {}

    for day in soup.select(".show_all_dates_class"):
        day_match = None
        for cls in day.get("class", []):
            day_match = _DAY_CLASS.match(cls)
            if day_match:
                break
        if not day_match:
            continue
        year, month, dom = (int(x) for x in day_match.groups())

        for box in day.select(".cinemaList_box"):
            raw_title = _title_of(box)
            if not raw_title:
                continue
            title, special = split_special_title(raw_title)

            film = films.get(_loose_key(title))
            if film is None:
                link = box.select_one(".cinema_ListingBox a")
                duration = box.select_one(".moviMint")
                film = Film(
                    title=title,
                    duration=duration.get_text(strip=True) if duration else None,
                    # Only take the page link from the main listing, not a special one
                    ph_url=(link.get("href") if link and not special else None),
                )
                films[_loose_key(title)] = film
            elif film.ph_url is None and not special:
                # First seen as a special screening: take the main listing's title and link
                film.title = title
                link = box.select_one(".cinema_ListingBox a")
                film.ph_url = link.get("href") if link else None

            for li in box.select(".cinemaTime_list li"):
                link = li.select_one("a.movie_time_button") or li.select_one("a")
                if link is None:
                    continue
                time_box = link.select_one(".timeBox")
                m = re.match(r"^(\d{1,2}):(\d{2})$", (time_box.get_text(strip=True) if time_box else ""))
                if not m:
                    continue
                start = datetime(year, month, dom, int(m.group(1)), int(m.group(2)), tzinfo=LONDON_TZ)
                labels = [
                    a.get_text(strip=True)
                    for a in li.select("p a")
                    if a.get_text(strip=True) and a.get_text(strip=True).lower() not in _IGNORED_LABELS
                ]
                if special and special not in labels:
                    labels.insert(0, special)
                film.screenings.append(
                    Screening(
                        cinema=cinema_name,
                        date=start,
                        booking_url=_booking_url(link, cinema_name),
                        screening_type=", ".join(labels) or None,
                    )
                )

    result = [f for f in films.values() if f.screenings]
    for f in result:
        f.screenings.sort(key=lambda s: s.date)
    logger.info("Parsed %d films from the %s Picturehouse page", len(result), cinema_name)
    return result


def fetch_ph_pages(urls: dict[str, str]) -> dict[str, str]:
    """Open each cinema page in a headless browser and return the rendered HTML.

    Returns {cinema_name: html}. A cinema that fails is left out, and the
    caller falls back to Data Thistle for it. Raises PicturehouseUnavailable
    only if the browser itself cannot start.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise PicturehouseUnavailable("Playwright is not installed") from e

    pages: dict[str, str] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(user_agent=_USER_AGENT, locale="en-GB")
                for cinema_name, url in urls.items():
                    page = context.new_page()
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT_MS)
                        pages[cinema_name] = read_listings_page(page)
                    except PlaywrightError as e:
                        logger.error("Could not read the %s Picturehouse page: %s", cinema_name, e)
                    finally:
                        page.close()
            finally:
                browser.close()
    except PlaywrightError as e:
        raise PicturehouseUnavailable(f"Browser failed: {e}") from e
    return pages


def read_listings_page(page, click_timeout_ms: int = 15_000) -> str:
    """Show every date on a loaded Picturehouse cinema page and return its HTML."""
    _clear_overlays(page)
    # The listings only load once "Show all dates" is pressed
    button = page.locator("#show_all_dates_btn").first
    try:
        button.click(timeout=click_timeout_ms)
    except Exception:
        # Something still covers the button: fire its own click handler instead
        logger.warning("Show all dates was covered on the page; pressing it directly")
        button.dispatch_event("click")
    page.wait_for_selector(_LISTING_SELECTOR, timeout=_LISTINGS_TIMEOUT_MS)
    # Let late day blocks finish rendering
    page.wait_for_timeout(2_000)
    return page.content()


# Banners seen in front of "Show all dates" (GitHub run 45581796060, 25 Nov 2026)
_OVERLAYS = ("#onetrust-consent-sdk", "#popupbanner")


def _clear_overlays(page) -> None:
    """Decline cookies, close the marketing banner and hide anything left over.

    The cookie banner can arrive a moment after the page loads, so wait briefly
    for it before declining.
    """
    try:
        page.wait_for_selector("#onetrust-reject-all-handler", state="visible", timeout=5_000)
    except Exception:
        pass
    _dismiss_cookie_banner(page)
    try:
        close = page.locator("#popupbanner-close")
        if close.count() and close.first.is_visible():
            close.first.click(timeout=2_000)
    except Exception:
        pass
    page.add_style_tag(content=", ".join(_OVERLAYS) + " { display: none !important; }")


def _dismiss_cookie_banner(page) -> None:
    """Decline non-essential cookies if the banner is in the way."""
    for label in ("Reject All", "Reject all", "Necessary only"):
        try:
            button = page.get_by_role("button", name=label)
            if button.count():
                button.first.click(timeout=2_000)
                return
        except Exception:
            continue
