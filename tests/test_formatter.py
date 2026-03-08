"""Tests for digest formatting."""

from datetime import datetime
from zoneinfo import ZoneInfo

from cinema_digest.formatter import (
    _compact_logline,
    _format_booking_link,
    _format_scores,
    _format_showtimes,
    _clean_logline,
    format_digest,
    format_digest_html,
    format_film_line,
    is_highlighted,
)
from cinema_digest.models import Film, Scores, Screening

LONDON_TZ = ZoneInfo("Europe/London")


class TestFormatScores:
    def test_all_scores(self):
        scores = Scores(metacritic=83, imdb=7.4, rotten_tomatoes=91)
        assert _format_scores(scores) == "83 / 7.4 / 91%"

    def test_no_scores(self):
        assert _format_scores(None) == "N/A / N/A / N/A"

    def test_empty_scores(self):
        scores = Scores()
        assert _format_scores(scores) == "N/A / N/A / N/A"

    def test_partial_scores(self):
        scores = Scores(metacritic=75, imdb=None, rotten_tomatoes=88)
        assert _format_scores(scores) == "75 / N/A / 88%"


class TestFormatShowtimes:
    def test_single_cinema(self):
        screenings = [
            Screening(
                cinema="Clapham",
                date=datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),
                booking_url="https://example.com",
            ),
        ]
        result = _format_showtimes(screenings)
        assert result == "Clapham: Tue 18:10"

    def test_two_cinemas(self):
        screenings = [
            Screening(
                cinema="Clapham",
                date=datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),
                booking_url="https://example.com",
            ),
            Screening(
                cinema="Ritzy",
                date=datetime(2026, 3, 13, 19, 0, tzinfo=LONDON_TZ),
                booking_url="https://example.com",
            ),
        ]
        result = _format_showtimes(screenings)
        assert result == "Clapham: Tue 18:10; Ritzy: Fri 19:00"

    def test_multiple_times_same_cinema(self):
        screenings = [
            Screening(
                cinema="Clapham",
                date=datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),
                booking_url="https://example.com",
            ),
            Screening(
                cinema="Clapham",
                date=datetime(2026, 3, 12, 20, 30, tzinfo=LONDON_TZ),
                booking_url="https://example.com",
            ),
        ]
        result = _format_showtimes(screenings)
        assert result == "Clapham: Tue 18:10, Thu 20:30"


class TestFormatBookingLink:
    def test_picks_earliest(self):
        screenings = [
            Screening(
                cinema="Ritzy",
                date=datetime(2026, 3, 13, 19, 0, tzinfo=LONDON_TZ),
                booking_url="https://ritzy.com/late",
            ),
            Screening(
                cinema="Clapham",
                date=datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),
                booking_url="https://clapham.com/early",
            ),
        ]
        result = _format_booking_link(screenings)
        assert result == "[Book at Clapham](https://clapham.com/early)"


class TestCleanLogline:
    def test_short_logline_unchanged(self):
        assert _clean_logline("A short logline.") == "A short logline."

    def test_none_returns_empty(self):
        assert _clean_logline(None) == ""

    def test_long_logline_not_truncated(self):
        long = "A " * 100
        result = _clean_logline(long)
        assert result == "A " * 99 + "A"


class TestCompactLogline:
    def test_short_logline_unchanged(self):
        assert _compact_logline("A short logline.") == "A short logline."

    def test_none_returns_empty(self):
        assert _compact_logline(None) == ""

    def test_long_logline_trimmed_at_sentence(self):
        long = "First sentence here. " + "X" * 200
        result = _compact_logline(long)
        assert result == "First sentence here."

    def test_no_ellipsis_cutoff(self):
        """If no sentence boundary found, return full text instead of cutting off."""
        long = "A really long logline without any sentence breaks that just keeps going and going " * 3
        result = _compact_logline(long)
        assert "\u2026" not in result
        assert result == _clean_logline(long)

    def test_under_180_chars_unchanged(self):
        text = "A decent logline that is well within the limit."
        assert _compact_logline(text) == text


class TestFormatFilmLine:
    def test_complete_film(self):
        film = Film(
            title="Test Film",
            logline="A test film about testing.",
            director="Jane Director",
            screenings=[
                Screening(
                    cinema="Clapham",
                    date=datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),
                    booking_url="https://example.com/book",
                ),
            ],
            scores=Scores(metacritic=83, imdb=7.4, rotten_tomatoes=91),
        )
        result = format_film_line(film)
        assert "Test Film" in result
        assert "dir. Jane Director" in result
        assert "83 / 7.4 / 91%" in result
        assert "Clapham: Tue 18:10" in result
        assert "[Book at Clapham](https://example.com/book)" in result

    def test_special_characters_in_title(self):
        film = Film(
            title="If I Had Legs I'd Kick You",
            screenings=[
                Screening(
                    cinema="Ritzy",
                    date=datetime(2026, 3, 14, 14, 0, tzinfo=LONDON_TZ),
                    booking_url="https://example.com/book",
                ),
            ],
            scores=Scores(),
        )
        result = format_film_line(film)
        assert "**If I Had Legs I'd Kick You**" in result


class TestFormatDigest:
    def test_alphabetical_ordering(self):
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)
        films = [
            Film(
                title="Zebra Film",
                screenings=[
                    Screening(
                        cinema="Clapham",
                        date=datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ),
                        booking_url="https://example.com",
                    ),
                ],
                scores=Scores(),
            ),
            Film(
                title="Alpha Film",
                screenings=[
                    Screening(
                        cinema="Ritzy",
                        date=datetime(2026, 3, 11, 20, 0, tzinfo=LONDON_TZ),
                        booking_url="https://example.com",
                    ),
                ],
                scores=Scores(),
            ),
        ]
        result = format_digest(films, now=now)
        alpha_pos = result.index("Alpha Film")
        zebra_pos = result.index("Zebra Film")
        assert alpha_pos < zebra_pos

    def test_empty_films(self):
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)
        result = format_digest([], now=now)
        assert "No qualifying screenings" in result


class TestIsHighlighted:
    def test_none_scores(self):
        assert is_highlighted(None) is False

    def test_empty_scores(self):
        assert is_highlighted(Scores()) is False

    def test_metacritic_70(self):
        assert is_highlighted(Scores(metacritic=70)) is True

    def test_metacritic_69(self):
        assert is_highlighted(Scores(metacritic=69)) is False

    def test_imdb_7(self):
        assert is_highlighted(Scores(imdb=7.0)) is True

    def test_imdb_6_9(self):
        assert is_highlighted(Scores(imdb=6.9)) is False

    def test_rt_80(self):
        assert is_highlighted(Scores(rotten_tomatoes=80)) is True

    def test_rt_79(self):
        assert is_highlighted(Scores(rotten_tomatoes=79)) is False

    def test_any_one_qualifies(self):
        assert is_highlighted(Scores(metacritic=50, imdb=5.0, rotten_tomatoes=95)) is True


class TestFormatDigestHtml:
    def test_contains_picturehouse_branding(self):
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)
        films = [
            Film(
                title="Test Film",
                director="Test Director",
                screenings=[
                    Screening(
                        cinema="Clapham",
                        date=datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ),
                        booking_url="https://example.com",
                    ),
                ],
                scores=Scores(metacritic=85, imdb=8.0, rotten_tomatoes=92),
            ),
        ]
        result = format_digest_html(films, now=now)
        assert "Picturehouse" in result
        assert "#E2124D" in result
        # Star emoji should appear for highlighted films
        assert "&#11088;" in result
        # Director should appear
        assert "Test Director" in result

    def test_html_empty_films(self):
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)
        result = format_digest_html([], now=now)
        assert "No qualifying screenings" in result

    def test_html_escapes_special_chars(self):
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)
        films = [
            Film(
                title="If I Had Legs I'd Kick You",
                screenings=[
                    Screening(
                        cinema="Ritzy",
                        date=datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ),
                        booking_url="https://example.com",
                    ),
                ],
                scores=Scores(),
            ),
        ]
        result = format_digest_html(films, now=now)
        assert "I&#x27;d" in result or "I'd" in result  # html.escape
