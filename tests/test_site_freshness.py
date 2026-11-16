"""The hosted site must say when its listings are out of date, and the deploy
must be checkable from outside (fetched_at in films.json)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from tests.browser import open_page, page_html

LONDON = ZoneInfo("Europe/London")


def _payload(fetched_at: datetime, films=None):
    return {
        "films": films or [],
        "cinemas": ["Clapham", "Ritzy"],
        "count": len(films or []),
        "fetched_at": fetched_at.isoformat(),
        "fetched_at_label": fetched_at.strftime("%a %d %b, %H:%M"),
        "warning": None,
        "notes": [],
        "error": None,
    }


def _film(start: datetime):
    return {
        "title": "Wild Horse Nine", "director": None, "year": 2026, "duration": "1h 50min",
        "logline": None, "highlighted": False, "considering": False, "scores_incomplete": False,
        "scores": {"metacritic": 77, "imdb": None, "rotten_tomatoes": None}, "score_urls": {},
        "cinemas": ["Ritzy"],
        "showtimes": [{"cinema": "Ritzy", "day": start.strftime("%a"), "date": "13 Nov",
                       "time": start.strftime("%H:%M"), "iso": start.isoformat(),
                       "url": "https://web.picturehouses.com/order/showtimes/004-1/seats", "type": None}],
        "booking_urls": {"Ritzy": "https://web.picturehouses.com/order/showtimes/004-1/seats"},
    }


class TestStaleSnapshot:
    def test_old_snapshot_says_it_is_out_of_date(self):
        built = datetime(2026, 10, 7, 6, 25, tzinfo=LONDON)
        now = datetime(2026, 11, 16, 9, 0, tzinfo=LONDON)
        with open_page(page_html(_payload(built), now)) as page:
            banner = page.locator("#stale")
            assert banner.is_visible()
            text = banner.inner_text()
            assert "out of date" in text
            assert "Wed 07 Oct" in text

    def test_fresh_snapshot_has_no_stale_warning(self):
        built = datetime(2026, 11, 16, 6, 0, tzinfo=LONDON)
        now = datetime(2026, 11, 16, 9, 0, tzinfo=LONDON)
        start = datetime(2026, 11, 16, 19, 0, tzinfo=LONDON)
        with open_page(page_html(_payload(built, [_film(start)]), now)) as page:
            assert not page.locator("#stale").is_visible()
            assert page.locator(".card").count() == 1
