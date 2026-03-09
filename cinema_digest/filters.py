"""Showtime filtering logic."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from cinema_digest.models import Film, Screening

logger = logging.getLogger(__name__)

LONDON_TZ = ZoneInfo("Europe/London")


def _is_weekend(d: date) -> bool:
    return d.weekday() in (5, 6)  # Saturday=5, Sunday=6


def _in_time_window(dt: datetime) -> bool:
    """Check if a screening time falls within the allowed window.

    Weekdays (Mon-Fri): 18:00 <= time <= 21:30
    Weekends (Sat-Sun): 11:00 <= time <= 21:30
    """
    t = dt.time()
    cutoff_late = time(21, 30)

    if _is_weekend(dt.date()):
        return time(11, 0) <= t <= cutoff_late
    else:
        return time(18, 0) <= t <= cutoff_late


def filter_screenings(
    films: list[Film],
    now: datetime | None = None,
) -> list[Film]:
    """Filter films to only include qualifying screenings.

    Rules:
    - Must be within today .. today+6 days (inclusive), in Europe/London time
    - Must pass the time window check (weekday/weekend rules)
    - Must not be in the past
    - Films with zero qualifying screenings are dropped
    """
    if now is None:
        now = datetime.now(LONDON_TZ)

    today = now.date()
    end_date = today + timedelta(days=6)

    result = []
    for film in films:
        kept: list[Screening] = []
        for s in film.screenings:
            s_date = s.date.date()

            if s_date < today or s_date > end_date:
                continue
            if s.date <= now:
                continue
            if not _in_time_window(s.date):
                continue

            kept.append(s)

        if not kept:
            continue

        kept.sort(key=lambda s: s.date)

        filtered_film = Film(
            title=film.title,
            year=film.year,
            duration=film.duration,
            logline=film.logline,
            director=film.director,
            imdb_id=film.imdb_id,
            listing_url=film.listing_url,
            screenings=kept,
            scores=film.scores,
        )
        result.append(filtered_film)

    logger.info(
        "After filtering: %d films with qualifying screenings (from %d total)",
        len(result),
        len(films),
    )
    return result
