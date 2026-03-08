"""Shared test fixtures."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from cinema_digest.models import Film, Scores, Screening

LONDON_TZ = ZoneInfo("Europe/London")


@pytest.fixture
def sample_screening_weekday():
    """A Wednesday evening screening."""
    return Screening(
        cinema="Clapham",
        date=datetime(2026, 3, 11, 19, 30, tzinfo=LONDON_TZ),  # Wednesday
        booking_url="https://ticketing.picturehouses.com/test?id=1",
        screening_type=None,
    )


@pytest.fixture
def sample_screening_weekend():
    """A Saturday afternoon screening."""
    return Screening(
        cinema="Ritzy",
        date=datetime(2026, 3, 14, 14, 0, tzinfo=LONDON_TZ),  # Saturday
        booking_url="https://ticketing.picturehouses.com/test?id=2",
        screening_type=None,
    )


@pytest.fixture
def sample_film():
    """A film with screenings at both cinemas."""
    return Film(
        title="Test Film",
        year=2026,
        duration="1h 45min",
        logline="A test film about testing.",
        listing_url="https://film.datathistle.com/listing/123-test-film/",
        screenings=[
            Screening(
                cinema="Clapham",
                date=datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),  # Tuesday
                booking_url="https://ticketing.picturehouses.com/test?id=1",
            ),
            Screening(
                cinema="Clapham",
                date=datetime(2026, 3, 12, 20, 30, tzinfo=LONDON_TZ),  # Thursday
                booking_url="https://ticketing.picturehouses.com/test?id=2",
            ),
            Screening(
                cinema="Ritzy",
                date=datetime(2026, 3, 13, 19, 0, tzinfo=LONDON_TZ),  # Friday
                booking_url="https://ticketing.picturehouses.com/test?id=3",
            ),
        ],
        scores=Scores(metacritic=83, imdb=7.4, rotten_tomatoes=91),
    )
