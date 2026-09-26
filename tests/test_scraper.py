"""Tests for the scraper parsing logic."""

from datetime import date
from unittest.mock import MagicMock

import requests

from cinema_digest.scraper import (
    _extract_film_blocks,
    _parse_date_header,
    _parse_time_text,
    merge_films,
    parse_cinema,
    scrape_all,
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
    """All cases pass an explicit 'today', so they don't depend on the real date."""

    def test_normal_date(self):
        result = _parse_date_header("Wed 11 Mar", today=date(2026, 3, 1))
        assert result == date(2026, 3, 11)

    def test_single_digit_day(self):
        result = _parse_date_header("Mon 9 Mar", today=date(2026, 3, 1))
        assert result == date(2026, 3, 9)

    def test_year_rollover(self):
        # In Dec 2026, "Wed 6 Jan" is January 2027
        result = _parse_date_header("Wed 6 Jan", today=date(2026, 12, 20))
        assert result == date(2027, 1, 6)

    def test_recent_past_stays_in_this_year(self):
        # A header a few days old is still this year, not next year
        result = _parse_date_header("Wed 11 Mar", today=date(2026, 3, 20))
        assert result == date(2026, 3, 11)

    def test_weekday_picks_the_year(self):
        # 6 Jan 2026 is a Tuesday and 6 Jan 2027 a Wednesday; both are plausible
        # from early January 2026, so the weekday decides
        assert _parse_date_header("Tue 6 Jan", today=date(2026, 1, 2)) == date(2026, 1, 6)
        assert _parse_date_header("Wed 6 Jan", today=date(2026, 1, 2)) == date(2027, 1, 6)

    def test_leap_day_in_next_year(self):
        result = _parse_date_header("Tue 29 Feb", today=date(2027, 12, 20))
        assert result == date(2028, 2, 29)

    def test_leap_day_without_leap_year(self):
        assert _parse_date_header("Sun 29 Feb", today=date(2026, 1, 10)) is None

    def test_invalid_date(self):
        result = _parse_date_header("NotADate", today=date(2026, 3, 1))
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

    def test_screening_dates_use_today(self):
        films = parse_cinema(SAMPLE_HTML, "Clapham", today=date(2026, 3, 1))
        test_film = next(f for f in films if f.title == "Test Film")
        assert min(s.date for s in test_film.screenings) == datetime(2026, 3, 11, 14, 0, tzinfo=LONDON_TZ)

    def test_repeated_showtime_listed_once(self):
        # Data Thistle sometimes lists the same showtime twice
        html = """
        <h4><a href="/listing/1-sexy-beast/">Sexy Beast</a></h4>
        <div><ul class="info"><li>2000</li><li>1h 28min</li></ul></div>
        <h5>Sun 27 Sep</h5>
        <div><ul>
          <li><time><a href="https://web.picturehouses.com/order/showtimes/004-74742/seats">13:10</a></time></li>
          <li><time><a href="https://web.picturehouses.com/order/showtimes/004-74742/seats">13:10</a></time></li>
        </ul></div>
        """
        films = parse_cinema(html, "Ritzy", today=date(2026, 9, 26))
        assert len(films[0].screenings) == 1

    def test_logline_keeps_spaces_around_inline_tags(self):
        html = """
        <h4><a href="/listing/3-play/">A Play</a></h4>
        <div><ul><li>2026</li></ul><p><b>The Misanthrope</b> by Martin Crimp, after <i>Moli\u00e8re</i>.</p></div>
        """
        film = parse_cinema(html, "Clapham")[0]
        assert film.logline == "The Misanthrope by Martin Crimp, after Moli\u00e8re."

    def test_duration_kept_without_year(self):
        html = """
        <h4><a href="/listing/2-no-year/">No Year Film</a></h4>
        <div><ul><li>UK</li><li>1h 30min</li></ul><p>A plot description long enough.</p></div>
        """
        film = parse_cinema(html, "Clapham")[0]
        assert film.year is None
        assert film.duration == "1h 30min"
        assert film.logline == "A plot description long enough."

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

    def test_same_title_different_years_not_merged(self):
        films = [
            Film(title="The Wicker Man", year=1973, screenings=[
                Screening(cinema="Clapham", date=datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ), booking_url="a"),
            ]),
            Film(title="The Wicker Man", year=2026, screenings=[
                Screening(cinema="Ritzy", date=datetime(2026, 3, 12, 19, 0, tzinfo=LONDON_TZ), booking_url="b"),
            ]),
        ]
        merged = merge_films(films)
        assert sorted(f.year for f in merged) == [1973, 2026]
        assert all(len(f.screenings) == 1 for f in merged)

    def test_undated_listing_joins_dated_one(self):
        films = [
            Film(title="The Bride!", year=2026, screenings=[]),
            Film(title="The Bride!", year=None, screenings=[]),
        ]
        merged = merge_films(films)
        assert len(merged) == 1
        assert merged[0].year == 2026

    def test_undated_first_does_not_merge_two_different_years(self):
        films = [
            Film(title="Hamlet", year=None, screenings=[]),
            Film(title="Hamlet", year=1948, screenings=[]),
            Film(title="Hamlet", year=2026, screenings=[]),
        ]
        merged = merge_films(films)
        assert sorted(f.year for f in merged) == [1948, 2026]

    def test_merge_drops_repeated_showtimes(self):
        s = Screening(cinema="Ritzy", date=datetime(2026, 3, 12, 20, 0, tzinfo=LONDON_TZ), booking_url="u")
        films = [
            Film(title="Film", year=2026, screenings=[s]),
            Film(title="Film", year=2026, screenings=[Screening("Ritzy", s.date, "u")]),
        ]
        assert len(merge_films(films)[0].screenings) == 1

    def test_richer_metadata_kept(self):
        films = [
            Film(title="Test", logline=None, screenings=[]),
            Film(title="Test", logline="A great logline about testing.", screenings=[]),
        ]
        merged = merge_films(films)
        assert merged[0].logline == "A great logline about testing."


def _cinema_html(n_films: int, with_times: bool = True) -> str:
    blocks = []
    for i in range(n_films):
        times = (
            '<h5>Mon 28 Sep</h5><div><ul><li><a href="https://web.picturehouses.com/order/showtimes/020-1/seats">19:00</a></li></ul></div>'
            if with_times
            else ""
        )
        blocks.append(f'<h4><a href="/listing/{i}-f/">Film {i}</a></h4><div><ul><li>2026</li></ul></div>{times}')
    return "".join(blocks)


def _session_returning(*pages):
    session = MagicMock()
    responses = []
    for page in pages:
        if isinstance(page, Exception):
            responses.append(page)
        else:
            resp = MagicMock()
            resp.text = page
            resp.raise_for_status.return_value = None
            responses.append(resp)
    session.get.side_effect = responses
    return session


class TestScrapeAll:
    TODAY = date(2026, 9, 26)

    def test_healthy_pages_have_no_warnings(self):
        result = scrape_all(_session_returning(_cinema_html(5), _cinema_html(5)), today=self.TODAY)
        assert len(result.films) == 5  # same titles merge across cinemas
        assert result.warnings == []
        assert result.listings_suspect is False

    def test_low_film_count_is_a_note_not_an_abort(self):
        result = scrape_all(_session_returning(_cinema_html(1), _cinema_html(5)), today=self.TODAY)
        assert len(result.films) == 5
        assert any("unusually low" in w and "Clapham" in w for w in result.warnings)
        assert result.listings_suspect is False

    def test_fetch_failure_keeps_other_cinema(self):
        session = _session_returning(requests.ConnectionError("down"), _cinema_html(4))
        result = scrape_all(session, today=self.TODAY)
        assert len(result.films) == 4
        assert result.listings_suspect is True
        assert any("Could not fetch the Clapham listings" in w for w in result.warnings)

    def test_films_without_showtimes_flagged(self):
        result = scrape_all(
            _session_returning(_cinema_html(5, with_times=False), _cinema_html(5, with_times=False)),
            today=self.TODAY,
        )
        assert len(result.films) == 5
        assert result.listings_suspect is True
        assert any("no showtimes could be read" in w for w in result.warnings)
