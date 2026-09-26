"""Shared test fixtures.

Unit tests run offline: any attempt to open a network connection fails the
test. Live integration tests (marked `integration`) are skipped unless asked
for with `pytest -m integration` or RUN_INTEGRATION=1.
"""

import os
import socket
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from cinema_digest.models import Film, Scores, Screening

LONDON_TZ = ZoneInfo("Europe/London")


def _integration_requested(config) -> bool:
    if os.environ.get("RUN_INTEGRATION", "").lower() in ("1", "true", "yes"):
        return True
    return "integration" in (config.getoption("-m") or "")


def pytest_collection_modifyitems(config, items):
    if _integration_requested(config):
        return
    skip = pytest.mark.skip(reason="live test: run with -m integration or RUN_INTEGRATION=1")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    """Fail any unit test that tries to reach the network.

    The code under test swallows most errors (by design), so attempts are
    recorded and checked after the test rather than relying on the raise.
    """
    if "integration" in request.keywords:
        yield
        return

    attempts = []

    def guard(*args, **kwargs):
        attempts.append(args[1:] or args)
        raise OSError("network access blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    yield
    assert not attempts, f"unit test tried to open network connections: {attempts}"


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
