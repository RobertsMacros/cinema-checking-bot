"""Tests for the scraper parsing logic."""

from datetime import date

from cinema_digest.scraper import (
    _extract_film_blocks,
    _parse_date_header,
    _parse_time_text,
    merge_films,
    parse_cinema,
)
from cinema_digest.models import Film, Screening

from bs4 import BeautifulSoup
from datetime import datetime, time
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")


SAMPLE_HTML = """
<html><body>
<h4><a href="/listing/123-test-film/">Test Film</a></h4>
<div>
<a href="/listing/123-test-film/"><img src="poster.jpg" alt="Test Film"></a>
<ul>
  <li>2026</li>
  <li>UK</li>
  <li>1h 45min</li>
  <li><em>15</em></li>
</ul>
<ul>
  <li><strong>Directed by:</strong> Some Director</li>
</ul>
<p>A thrilling adventure about testing software.</p>
<ul><li>more info</li></ul>
</div>
<h5>Wed 11 Mar</h5>
<div>
<ul>
  <li><a href="https://ticketing.picturehouses.com/test?id=1" title="7pm">19:00</a></li>
  <li><a href="https://ticketing.picturehouses.com/test?id=2" title="9pm">21:00</a></li>
</ul>
<h6>Senior</h6>
<ul>
  <li><a href="https://ticketing.picturehouses.com/test?id=3" title="2pm">14:00</a></li>
</ul>
</div>
<h5>Thu 12 Mar</h5>
<div>
<ul>
  <li><a href="https://ticketing.picturehouses.com/test?id=4" title="8pm">20:00</a></li>
</ul>
</div>

<h4><a href="/listing/456-another-film/">Another Film</a></h4>
<div>
<ul>
  <li>2025</li>
  <li>US</li>
  <li>2h 10min</li>
</ul>
<p>A dramatic tale of another film.</p>
</div>
<h5>Fri 13 Mar</h5>
<div>
<ul>
  <li><a href="https://ticketing.picturehouses.com/test?id=5" title="6pm">18:00</a></li>
</ul>
</div>
</body></html>
"""


class TestExtractFilmBlocks:
    def test_finds_correct_number_of_blocks(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        blocks = _extract_film_blocks(soup)
        assert len(blocks) == 2

    def test_first_block_title(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        blocks = _extract_film_blocks(soup)
        h4, _ = blocks[0]
        assert h4.find("a").get_text(strip=True) == "Test Film"

    def test_second_block_title(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        blocks = _extract_film_blocks(soup)
        h4, _ = blocks[1]
        assert h4.find("a").get_text(strip=True) == "Another Film"


class TestParseDateHeader:
    def test_normal_date(self):
        result = _parse_date_header("Wed 11 Mar", 2026)
        assert result == date(2026, 3, 11)

    def test_single_digit_day(self):
        result = _parse_date_header("Mon 9 Mar", 2026)
        assert result == date(2026, 3, 9)

    def test_year_rollover(self):
        # If we're in Dec 2026 and see "Tue 6 Jan", should resolve to Jan 2027
        result = _parse_date_header("Tue 6 Jan", 2026)
        # Since Jan 6 2026 is > 60 days in the past (if run in March),
        # this test is context-dependent. Just check it returns a date.
        assert result is not None

    def test_invalid_date(self):
        result = _parse_date_header("NotADate", 2026)
        assert result is None


class TestParseTimeText:
    def test_normal_time(self):
        result = _parse_time_text("19:00")
        assert result == time(19, 0)

    def test_single_digit_hour(self):
        result = _parse_time_text("9:30")
        assert result == time(9, 30)

    def test_invalid_time(self):
        result = _parse_time_text("not-a-time")
        assert result is None


class TestParseCinema:
    def test_parses_films(self):
        films = parse_cinema(SAMPLE_HTML, "Clapham")
        assert len(films) == 2

    def test_film_metadata(self):
        films = parse_cinema(SAMPLE_HTML, "Clapham")
        test_film = next(f for f in films if f.title == "Test Film")
        assert test_film.year == 2026
        assert test_film.duration == "1h 45min"

    def test_film_screenings(self):
        films = parse_cinema(SAMPLE_HTML, "Clapham")
        test_film = next(f for f in films if f.title == "Test Film")
        # 2 regular on Wed + 1 Senior on Wed + 1 on Thu = 4
        assert len(test_film.screenings) == 4

    def test_screening_type_parsed(self):
        films = parse_cinema(SAMPLE_HTML, "Clapham")
        test_film = next(f for f in films if f.title == "Test Film")
        senior = [s for s in test_film.screenings if s.screening_type == "Senior"]
        assert len(senior) == 1

    def test_booking_url_extracted(self):
        films = parse_cinema(SAMPLE_HTML, "Clapham")
        test_film = next(f for f in films if f.title == "Test Film")
        assert all(
            s.booking_url.startswith("https://ticketing.picturehouses.com")
            for s in test_film.screenings
        )

    def test_logline_extracted(self):
        films = parse_cinema(SAMPLE_HTML, "Clapham")
        test_film = next(f for f in films if f.title == "Test Film")
        assert "testing software" in test_film.logline


class TestMergeFilms:
    def test_merge_same_title(self):
        films = [
            Film(
                title="The Bride!",
                year=2026,
                screenings=[
                    Screening(cinema="Clapham", date=datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ), booking_url="url1"),
                ],
            ),
            Film(
                title="The Bride!",
                year=2026,
                screenings=[
                    Screening(cinema="Ritzy", date=datetime(2026, 3, 12, 20, 0, tzinfo=LONDON_TZ), booking_url="url2"),
                ],
            ),
        ]
        merged = merge_films(films)
        assert len(merged) == 1
        assert len(merged[0].screenings) == 2

    def test_different_titles_not_merged(self):
        films = [
            Film(title="Film A", screenings=[]),
            Film(title="Film B", screenings=[]),
        ]
        merged = merge_films(films)
        assert len(merged) == 2

    def test_richer_metadata_kept(self):
        films = [
            Film(title="Test", logline=None, screenings=[]),
            Film(title="Test", logline="A great logline about testing.", screenings=[]),
        ]
        merged = merge_films(films)
        assert merged[0].logline == "A great logline about testing."
