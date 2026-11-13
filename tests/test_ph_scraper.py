"""Tests for reading listings from the Picturehouse pages and combining sources."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from cinema_digest.models import Film, Screening
from cinema_digest.ph_scraper import parse_ph_listings, split_special_title
from cinema_digest.scraper import combine_sources, scrape_all

LONDON = ZoneInfo("Europe/London")
FIXTURE = (Path(__file__).parent / "fixtures" / "ph_clapham.html").read_text()


def _by_title(films):
    return {f.title: f for f in films}


def _at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=LONDON)


class TestParsePicturehouse:
    def test_reads_every_film_and_showtime(self):
        films = _by_title(parse_ph_listings(FIXTURE, "Clapham"))
        assert set(films) == {
            "La Bola Negra",
            "Wild Horse Nine",
            "Primetime",
            "Shaun the Sheep: The Beast of Mossy Bottom",
            "Ghosts: The Possession of Button House",
            "MUBI FEST LIVE: A LONG WINTER + Q&A",
        }
        assert [s.date for s in films["Wild Horse Nine"].screenings] == [
            _at(2026, 11, 13, 14, 15),
            _at(2026, 11, 13, 20, 30),
            _at(2026, 11, 14, 17, 30),
            _at(2026, 11, 14, 20, 10),
        ]

    def test_date_comes_from_the_day_block_not_the_heading(self):
        # "TODAY" and "TOMORROW" headings are ignored; the class carries the date
        films = _by_title(parse_ph_listings(FIXTURE, "Clapham"))
        assert films["Primetime"].screenings[0].date == _at(2026, 11, 13, 20, 45)

    def test_labels_become_screening_types(self):
        films = _by_title(parse_ph_listings(FIXTURE, "Clapham"))
        assert films["La Bola Negra"].screenings[0].screening_type == "Subtitled"
        assert films["Primetime"].screenings[0].screening_type is None
        mubi = films["MUBI FEST LIVE: A LONG WINTER + Q&A"].screenings[0]
        assert mubi.screening_type == "Ad and Trailer Free, Live via Satellite, Q&A"

    def test_special_screenings_fold_into_the_main_film(self):
        films = _by_title(parse_ph_listings(FIXTURE, "Clapham"))
        ghosts = films["Ghosts: The Possession of Button House"]
        assert [(s.date, s.screening_type) for s in ghosts.screenings] == [
            (_at(2026, 11, 15, 10, 45), "Dog Friendly"),
            (_at(2026, 11, 15, 13, 10), None),
        ]
        # The film link is the main listing, not the dog-friendly one
        assert ghosts.ph_url.endswith("/ghosts-the-possession-of-button-house")
        shaun = films["Shaun the Sheep: The Beast of Mossy Bottom"]
        assert [s.screening_type for s in shaun.screenings] == ["Kids' Club", "Relaxed"]

    def test_javascript_booking_link_is_rebuilt_from_session_id(self):
        films = _by_title(parse_ph_listings(FIXTURE, "Clapham"))
        kids = films["Shaun the Sheep: The Beast of Mossy Bottom"].screenings[0]
        assert kids.booking_url == "https://web.picturehouses.com/order/showtimes/020-80833/seats"

    def test_running_time_and_page_link(self):
        films = _by_title(parse_ph_listings(FIXTURE, "Clapham"))
        assert films["La Bola Negra"].duration == "155 min"
        assert films["La Bola Negra"].ph_url == (
            "https://www.picturehouses.com/movie-details/020/HO00018749/la-bola-negra"
        )

    def test_laser_projection_label_is_dropped(self):
        html = FIXTURE.replace("<p><a>Subtitled</a></p>", "<p><a>Laser Projection</a><a>Subtitled</a></p>", 1)
        films = _by_title(parse_ph_listings(html, "Clapham"))
        assert films["La Bola Negra"].screenings[0].screening_type == "Subtitled"

    def test_empty_page_gives_no_films(self):
        assert parse_ph_listings("<html><body></body></html>", "Clapham") == []

    def test_split_special_title(self):
        assert split_special_title("Relaxed:Shaun the Sheep") == ("Shaun the Sheep", "Relaxed")
        assert split_special_title("Dog-Friendly Screening: Elf") == ("Elf", "Dog Friendly")
        assert split_special_title("Prima Facie + panel") == ("Prima Facie + panel", None)


def _screening(cinema, when, url="u"):
    return Screening(cinema=cinema, date=when, booking_url=url)


class TestCombineSources:
    def test_picturehouse_is_primary_and_data_thistle_fills_gaps(self):
        ph = [Film(title="Fjord", duration="146 min", ph_url="ph",
                   screenings=[_screening("Ritzy", _at(2026, 11, 13, 19, 30))])]
        dt = [
            Film(title="Fjord", year=2026, logline="A story.", screenings=[
                _screening("Ritzy", _at(2026, 11, 13, 19, 30)),  # same showing
                _screening("Ritzy", _at(2026, 11, 14, 19, 30)),  # only on DT
            ]),
            Film(title="Only On Data Thistle", year=2025,
                 screenings=[_screening("Ritzy", _at(2026, 11, 15, 18, 0))]),
        ]
        films, extra_films, extra_times = combine_sources(ph, dt)
        by = _by_title(films)
        assert extra_films == 1 and extra_times == 1
        assert by["Fjord"].year == 2026  # year kept for score lookups
        assert by["Fjord"].logline == "A story."
        assert by["Fjord"].ph_url == "ph"
        assert len(by["Fjord"].screenings) == 2
        assert "Only On Data Thistle" in by

    def test_titles_match_despite_punctuation(self):
        ph = [Film(title="GIANT – The Play", screenings=[_screening("Ritzy", _at(2026, 11, 19, 19, 30))])]
        dt = [Film(title="Giant - The Play", screenings=[_screening("Ritzy", _at(2026, 11, 19, 19, 30))])]
        films, extra_films, extra_times = combine_sources(ph, dt)
        assert len(films) == 1 and extra_films == 0 and extra_times == 0


DT_EMPTY = "<html><body></body></html>"


def _session(*responses):
    session = MagicMock()
    out = []
    for r in responses:
        resp = MagicMock()
        resp.text = r
        resp.raise_for_status = MagicMock()
        out.append(resp)
    session.get.side_effect = out
    return session


class TestScrapeAllWithPicturehouse:
    TODAY = date(2026, 11, 13)

    def test_uses_picturehouse_pages(self):
        result = scrape_all(
            _session(DT_EMPTY, DT_EMPTY),
            today=self.TODAY,
            ph_fetcher=lambda urls: {name: FIXTURE for name in urls},
        )
        assert "Ghosts: The Possession of Button House" in _by_title(result.films)
        assert not any("could not be read" in w for w in result.warnings)

    def test_falls_back_to_data_thistle_with_a_note(self):
        def broken(urls):
            raise RuntimeError("browser crashed")

        result = scrape_all(_session(DT_EMPTY, DT_EMPTY), today=self.TODAY, ph_fetcher=broken)
        assert sum("Picturehouse page could not be read" in w for w in result.warnings) == 2
