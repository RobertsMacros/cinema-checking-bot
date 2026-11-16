"""Accessibility of the web page and the email: names for controls and
icons, text contrast of at least 4.5:1 (WCAG AA), and the page language."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from cinema_digest import formatter
from cinema_digest.formatter import format_digest_html
from cinema_digest.models import Film, Scores, Screening
from cinema_digest.webapp_template import PAGE_HTML
from tests.browser import open_page, page_html

LONDON = ZoneInfo("Europe/London")
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=LONDON)


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted([_luminance(a), _luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _css_var(name: str) -> str:
    return re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", PAGE_HTML).group(1)


class TestContrast:
    def test_web_text_colours(self):
        backgrounds = [_css_var(n) for n in ("bg", "card", "card-hl")]
        for text in ("text", "muted", "dim", "pink-text"):
            for bg in backgrounds:
                assert contrast(_css_var(text), bg) >= 4.5, (text, bg)

    def test_web_pink_is_only_used_for_text_through_the_text_token(self):
        # PH pink (#E2124D) is 3.9:1 on the page: fine for borders and the
        # active pill (white on pink is 4.7:1), not for text
        assert not re.search(r"(?<![-\w])color:\s*var\(--ph-pink\)", PAGE_HTML)

    def test_email_text_colours(self):
        for text in (formatter.DARK_TEXT, formatter.DARK_TEXT_MUTED, formatter.DARK_TEXT_DIM, formatter.LINK_ON_DARK):
            for bg in (formatter.DARK_BG, formatter.DARK_CARD, formatter.DARK_CARD_HL):
                assert contrast(text, bg) >= 4.5, (text, bg)


def _film(**kw):
    return Film(title="Fjord", screenings=[Screening("Ritzy", datetime(2026, 11, 13, 19, 0, tzinfo=LONDON), "u")],
                scores=Scores(metacritic=80), **kw)


class TestEmail:
    def test_score_icons_name_their_source(self):
        html = format_digest_html([_film()], now=NOW)
        for name in ("Metacritic", "IMDb", "Rotten Tomatoes"):
            assert f'alt="{name}"' in html

    def test_missing_scores_are_written_out(self):
        html = format_digest_html([_film()], now=NOW)
        scores = html.split('alt="IMDb"', 1)[1][:200]
        assert "N/A" in scores

    def test_language_and_no_em_dashes(self):
        html = format_digest_html([_film()], now=NOW)
        assert '<html lang="en-GB">' in html
        assert "&mdash;" not in html and "\u2014" not in html


def _payload():
    start = datetime(2026, 11, 13, 19, 0, tzinfo=LONDON)
    film = {
        "title": "Fjord", "director": None, "year": 2026, "duration": None, "logline": None,
        "highlighted": True, "considering": False, "scores_incomplete": False,
        "scores": {"metacritic": 80, "imdb": None, "rotten_tomatoes": None}, "score_urls": {},
        "cinemas": ["Ritzy"],
        "showtimes": [{"cinema": "Ritzy", "day": "Fri", "date": "13 Nov", "time": "19:00",
                       "iso": start.isoformat(), "url": "https://web.picturehouses.com/order/showtimes/004-1/seats",
                       "type": None}],
        "booking_urls": {"Ritzy": "https://web.picturehouses.com/order/showtimes/004-1/seats"},
    }
    return {"films": [film], "cinemas": ["Clapham", "Ritzy"], "count": 1, "fetched_at": NOW.isoformat(),
            "fetched_at_label": "Fri 13 Nov, 12:00", "warning": None, "notes": [], "error": None,
            "sources": ["Picturehouse"]}


class TestWebPage:
    def test_controls_and_icons_have_names(self):
        with open_page(page_html(_payload(), NOW)) as page:
            assert page.get_attribute("html", "lang") == "en-GB"
            assert page.get_by_role("searchbox", name="Search films").count() == 1
            alts = page.eval_on_selector_all(".scores img", "els => els.map(e => e.alt)")
            assert alts == ["Metacritic", "IMDb", "Rotten Tomatoes"]
            assert "N/A" in page.locator(".scores").inner_text()
            star = page.locator(".star")
            assert star.get_attribute("role") == "img" and "Highlight" in star.get_attribute("aria-label")

    def test_cinema_filter_says_which_is_selected(self):
        with open_page(page_html(_payload(), NOW)) as page:
            assert page.get_by_role("group", name="Cinema").count() == 1
            all_btn = page.get_by_role("button", name="All")
            assert all_btn.get_attribute("aria-pressed") == "true"
            page.get_by_role("button", name="Ritzy").click()
            assert page.get_by_role("button", name="Ritzy").get_attribute("aria-pressed") == "true"
            assert page.get_by_role("button", name="All").get_attribute("aria-pressed") == "false"

    def test_heading_has_no_em_dashes(self):
        with open_page(page_html(_payload(), NOW)) as page:
            assert page.locator("h1").inner_text() == "Cinema Listings"
