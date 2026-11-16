"""Film page links: keep the one read from the cinema's own page; only guess
(by matching titles on the what's-on page) for films that have none."""

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from cinema_digest.enrich import _enrich_ph_links
from cinema_digest.models import Film, Screening

LONDON = ZoneInfo("Europe/London")
WHEN = datetime(2026, 11, 13, 19, 0, tzinfo=LONDON)
DIRECT = "https://www.picturehouses.com/movie-details/004/HO00018878/fjord"


def _session(html: str):
    s = MagicMock()
    s.get.return_value.status_code = 200
    s.get.return_value.text = html
    return s


def test_links_from_the_cinema_page_are_kept_and_nothing_is_fetched():
    film = Film(title="Fjord", ph_url=DIRECT, screenings=[Screening("Ritzy", WHEN, "u")])
    session = _session('<a href="/movie-details/000/HO00099999/fjord">')
    _enrich_ph_links([film], session)
    assert film.ph_url == DIRECT
    session.get.assert_not_called()


def test_films_without_a_link_are_still_matched():
    film = Film(title="Only On Data Thistle", screenings=[Screening("Clapham", WHEN, "u")])
    session = _session('<a href="/movie-details/000/HO00012345/only-on-data-thistle">')
    _enrich_ph_links([film], session)
    assert film.ph_url == "https://www.picturehouses.com/movie-details/020/HO00012345/only-on-data-thistle"
    session.get.assert_called_once()
