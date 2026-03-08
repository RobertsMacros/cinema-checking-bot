"""Tests for showtime filtering logic."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cinema_digest.filters import filter_screenings
from cinema_digest.models import Film, Screening

LONDON_TZ = ZoneInfo("Europe/London")

# Use a fixed "now" for deterministic tests: Wednesday 2026-03-11 at 10:00
NOW = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)


def _make_film(screenings: list[Screening], title: str = "Test") -> Film:
    return Film(title=title, screenings=screenings)


def _make_screening(dt: datetime, cinema: str = "Clapham") -> Screening:
    return Screening(cinema=cinema, date=dt, booking_url="https://example.com")


class TestWeekdayBoundaries:
    """Weekday rule: 18:00 <= time <= 21:30."""

    def test_weekday_1759_excluded(self):
        # Wednesday at 17:59
        s = _make_screening(datetime(2026, 3, 11, 17, 59, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert result == []

    def test_weekday_1800_included(self):
        s = _make_screening(datetime(2026, 3, 11, 18, 0, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert len(result) == 1
        assert len(result[0].screenings) == 1

    def test_weekday_2130_included(self):
        s = _make_screening(datetime(2026, 3, 11, 21, 30, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert len(result) == 1

    def test_weekday_2131_excluded(self):
        s = _make_screening(datetime(2026, 3, 11, 21, 31, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert result == []


class TestWeekendBoundaries:
    """Weekend rule: 11:00 <= time <= 21:30."""

    def test_weekend_1059_excluded(self):
        # Saturday at 10:59
        s = _make_screening(datetime(2026, 3, 14, 10, 59, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert result == []

    def test_weekend_1100_included(self):
        s = _make_screening(datetime(2026, 3, 14, 11, 0, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert len(result) == 1

    def test_weekend_2130_included(self):
        s = _make_screening(datetime(2026, 3, 14, 21, 30, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert len(result) == 1

    def test_weekend_2131_excluded(self):
        s = _make_screening(datetime(2026, 3, 14, 21, 31, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert result == []


class TestDateWindow:
    """Tests for the 7-day window."""

    def test_today_included(self):
        # Wednesday evening (today)
        s = _make_screening(datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert len(result) == 1

    def test_day_six_included(self):
        # Tuesday 2026-03-17 (day 6 from Wednesday 2026-03-11)
        s = _make_screening(datetime(2026, 3, 17, 19, 0, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert len(result) == 1

    def test_day_seven_excluded(self):
        # Wednesday 2026-03-18 (day 7, outside window)
        s = _make_screening(datetime(2026, 3, 18, 19, 0, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert result == []

    def test_past_screening_excluded(self):
        # Earlier today (before now)
        s = _make_screening(datetime(2026, 3, 11, 9, 0, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert result == []

    def test_yesterday_excluded(self):
        s = _make_screening(datetime(2026, 3, 10, 19, 0, tzinfo=LONDON_TZ))
        result = filter_screenings([_make_film([s])], now=NOW)
        assert result == []


class TestFilmDropping:
    """Films with zero qualifying screenings should be dropped."""

    def test_film_with_no_qualifying_screenings_dropped(self):
        # All screenings are too early on a weekday
        screenings = [
            _make_screening(datetime(2026, 3, 11, 12, 0, tzinfo=LONDON_TZ)),
            _make_screening(datetime(2026, 3, 12, 14, 0, tzinfo=LONDON_TZ)),
        ]
        result = filter_screenings([_make_film(screenings)], now=NOW)
        assert result == []

    def test_film_with_some_qualifying_screenings_kept(self):
        screenings = [
            _make_screening(datetime(2026, 3, 11, 12, 0, tzinfo=LONDON_TZ)),  # excluded
            _make_screening(datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ)),  # kept
        ]
        result = filter_screenings([_make_film(screenings)], now=NOW)
        assert len(result) == 1
        assert len(result[0].screenings) == 1
        assert result[0].screenings[0].date.hour == 19

    def test_multiple_films_mixed(self):
        film1 = _make_film(
            [_make_screening(datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ))],
            title="A Film",
        )
        film2 = _make_film(
            [_make_screening(datetime(2026, 3, 11, 12, 0, tzinfo=LONDON_TZ))],
            title="B Film",
        )
        result = filter_screenings([film1, film2], now=NOW)
        assert len(result) == 1
        assert result[0].title == "A Film"
