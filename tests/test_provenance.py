"""The email and the web page say where the listings came from this run, and
credit the score data as its terms require."""

from datetime import datetime
from zoneinfo import ZoneInfo

from cinema_digest import webapp
from cinema_digest.formatter import format_digest, format_digest_html
from cinema_digest.models import Film, Scores, Screening
from tests.browser import open_page, page_html

LONDON = ZoneInfo("Europe/London")
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=LONDON)
TMDB_NOTICE = "This product uses the TMDB API but is not endorsed or certified by TMDB"


def _film():
    return Film(title="Fjord", screenings=[Screening("Ritzy", datetime(2026, 11, 13, 19, 0, tzinfo=LONDON), "u")],
                scores=Scores(metacritic=80))


def _footer(html: str) -> str:
    return html.split("<!-- Footer -->", 1)[1]


class TestEmail:
    def test_picturehouse_only(self):
        footer = _footer(format_digest_html([_film()], now=NOW, sources=["Picturehouse"]))
        assert "Picturehouse" in footer
        assert "Data Thistle" not in footer

    def test_both_sources(self):
        footer = _footer(format_digest_html([_film()], now=NOW, sources=["Picturehouse", "Data Thistle"]))
        assert "Picturehouse" in footer and "Data Thistle" in footer

    def test_score_credits_and_no_affiliation(self):
        footer = _footer(format_digest_html([_film()], now=NOW, sources=["Picturehouse"]))
        assert "OMDb" in footer and TMDB_NOTICE in footer
        assert "Not affiliated with Picturehouse Cinemas" in footer

    def test_plain_text_names_the_sources(self):
        body = format_digest([_film()], now=NOW, sources=["Data Thistle"])
        assert "Listings from: Data Thistle" in body
        assert TMDB_NOTICE in body


class TestWeb:
    def test_payload_carries_the_sources(self, monkeypatch):
        monkeypatch.setattr(webapp, "build_digest",
                            lambda config=None: ([_film()], [], False, ["Picturehouse", "Data Thistle"]))
        webapp._cache.__init__()
        assert webapp.build_payload(force_refresh=True)["sources"] == ["Picturehouse", "Data Thistle"]

    def test_footer_shows_this_runs_sources_and_credits(self):
        payload = {"films": [], "cinemas": [], "count": 0, "fetched_at": NOW.isoformat(),
                   "fetched_at_label": "Fri 13 Nov, 12:00", "warning": None, "notes": [], "error": None,
                   "sources": ["Picturehouse"]}
        with open_page(page_html(payload, NOW)) as page:
            footer = page.locator("footer").inner_text()
        assert "Listings from Picturehouse" in footer
        assert "Data Thistle" not in footer
        assert TMDB_NOTICE in footer
        assert "Not affiliated with Picturehouse Cinemas" in footer
