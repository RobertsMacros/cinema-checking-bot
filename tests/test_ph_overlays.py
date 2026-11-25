"""The Ritzy page can only be read once the banners in front of "Show All Dates" are out of the way.

On 25 Nov 2026 (GitHub run 45581796060) the click on "Show All Dates" timed
out because the Premiere Points banner and a late cookie banner covered it, so
the Ritzy fell back to Data Thistle. These tests open saved Picturehouse markup
in headless Chromium, offline.
"""

from pathlib import Path

import pytest

from cinema_digest.ph_scraper import parse_ph_listings, read_listings_page
from tests.browser import _launch, _unavailable

FIXTURES = Path(__file__).parent / "fixtures"


def _page_html() -> str:
    listings = (FIXTURES / "ph_clapham.html").read_text()
    listings = listings.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    return (FIXTURES / "ph_ritzy_overlays.html").read_text().replace("LISTINGS_GO_HERE", listings)


@pytest.fixture
def page():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        _unavailable("Playwright is not installed")
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            pg = browser.new_page()
            pg.route("**/*", lambda route: route.abort())
            yield pg
        finally:
            browser.close()


def test_reads_listings_when_banners_cover_show_all_dates(page):
    page.set_content(_page_html(), wait_until="domcontentloaded")
    page.wait_for_timeout(700)  # the cookie banner arrives late, as on the live page
    html = read_listings_page(page, click_timeout_ms=3_000)
    films = parse_ph_listings(html, "Ritzy")
    assert "La Bola Negra" in {f.title for f in films}


def test_declines_cookies_rather_than_accepting(page):
    page.set_content(_page_html(), wait_until="domcontentloaded")
    page.wait_for_timeout(700)
    read_listings_page(page, click_timeout_ms=3_000)
    assert page.locator("#onetrust-consent-sdk").count() == 0  # removed by "Reject All"
