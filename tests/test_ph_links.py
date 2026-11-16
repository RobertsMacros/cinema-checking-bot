"""Film page links: keep the one read from the cinema's own page; only guess
(by matching titles against Picturehouse's film codes) for films that have none.

These tests cover which films get a link and whether the codes are fetched,
not the what's-on page parser, so the code lookup returns parsed codes.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from cinema_digest import enrich
from cinema_digest.models import Film, Screening
from cinema_digest.scraper import normalize_title

LONDON = ZoneInfo("Europe/London")
WHEN = datetime(2026, 11, 13, 19, 0, tzinfo=LONDON)
DIRECT = "https://www.picturehouses.com/movie-details/004/HO00018878/fjord"


def _codes(monkeypatch, codes):
    calls = []

    def fetch(session):
        calls.append(session)
        return codes

    monkeypatch.setattr(enrich, "_fetch_ph_film_codes", fetch)
    return calls


def test_links_from_the_cinema_page_are_kept_and_nothing_is_fetched(monkeypatch):
    calls = _codes(monkeypatch, {normalize_title("Fjord"): ("HO00099999", "fjord")})
    film = Film(title="Fjord", ph_url=DIRECT, screenings=[Screening("Ritzy", WHEN, "u")])
    enrich._enrich_ph_links([film], session=object())
    assert film.ph_url == DIRECT
    assert calls == []


def test_films_without_a_link_are_still_matched(monkeypatch):
    calls = _codes(monkeypatch, {normalize_title("Only On Data Thistle"): ("HO00012345", "only-on-data-thistle")})
    film = Film(title="Only On Data Thistle", screenings=[Screening("Clapham", WHEN, "u")])
    enrich._enrich_ph_links([film], session=object())
    assert film.ph_url == "https://www.picturehouses.com/movie-details/020/HO00012345/only-on-data-thistle"
    assert len(calls) == 1
