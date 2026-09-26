"""Tests for digest formatting."""

from datetime import datetime
from zoneinfo import ZoneInfo

from cinema_digest.formatter import (
    LISTINGS_WARNING,
    _book_buttons_html,
    _compact_logline,
    _film_booking_url,
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
        assert result == "Clapham: Tue 18:10 | Ritzy: Fri 19:00"

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
        assert result == "Clapham: Tue 18:10; Thu 20:30"


class TestFormatBookingLink:
    def test_film_with_ph_url(self):
        film = Film(
            title="Test",
            ph_url="https://www.picturehouses.com/movie-details/020/HO123/test",
            screenings=[
                Screening(
                    cinema="Clapham",
                    date=datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),
                    booking_url="https://old.com",
                ),
            ],
            scores=Scores(),
        )
        result = format_film_line(film)
        assert "picturehouses.com/movie-details" in result

    def test_earliest_screening_booking_link_used(self):
        film = Film(
            title="Test",
            ph_url="https://www.picturehouses.com/movie-details/020/HO123/test",
            screenings=[
                Screening("Ritzy", datetime(2026, 3, 12, 19, 0, tzinfo=LONDON_TZ),
                          "https://web.picturehouses.com/order/showtimes/004-222/seats"),
                Screening("Clapham", datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),
                          "https://web.picturehouses.com/order/showtimes/020-111/seats"),
            ],
        )
        assert _film_booking_url(film) == "https://web.picturehouses.com/order/showtimes/020-111/seats"
        assert "(https://web.picturehouses.com/order/showtimes/020-111/seats)" in format_film_line(film)

    def test_old_ticketing_links_fall_back_to_film_page(self):
        # Data Thistle's old ticketing.picturehouses.com links are dead
        film = Film(
            title="Test",
            ph_url="https://www.picturehouses.com/movie-details/020/HO123/test",
            screenings=[
                Screening("Ritzy", datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ),
                          "https://ticketing.picturehouses.com/Ticketing/visSelectTickets.aspx?cinemacode=004&txtSessionId=1"),
            ],
        )
        assert _film_booking_url(film) == "https://www.picturehouses.com/movie-details/004/HO123/test"

    def test_no_valid_link_and_no_film_page_uses_cinema_page(self):
        film = Film(
            title="Test",
            screenings=[Screening("Ritzy", datetime(2026, 3, 10, 18, 10, tzinfo=LONDON_TZ), "javascript:alert(1)")],
        )
        assert _film_booking_url(film) == "https://www.picturehouses.com/cinema/the-ritzy"

    def test_two_cinema_buttons_use_each_cinemas_earliest_screening(self):
        film = Film(
            title="Test",
            screenings=[
                Screening("Clapham", datetime(2026, 3, 12, 20, 0, tzinfo=LONDON_TZ),
                          "https://web.picturehouses.com/order/showtimes/020-2/seats"),
                Screening("Clapham", datetime(2026, 3, 11, 20, 0, tzinfo=LONDON_TZ),
                          "https://web.picturehouses.com/order/showtimes/020-1/seats"),
                Screening("Ritzy", datetime(2026, 3, 13, 19, 0, tzinfo=LONDON_TZ),
                          "https://web.picturehouses.com/order/showtimes/004-9/seats"),
            ],
        )
        html = _book_buttons_html(film)
        assert "020-1/seats" in html and "020-2/seats" not in html
        assert "004-9/seats" in html


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
        long = "First sentence here. Second part is very long " + "X" * 200
        result = _compact_logline(long)
        assert result == "First sentence here."

    def test_keeps_as_many_whole_sentences_as_fit(self):
        text = "One sentence here. " * 12 + "Last."
        result = _compact_logline(text)
        assert result.endswith("here.")
        assert len(result) <= 180
        assert result.count("One sentence here.") == 9
        assert "Last" not in result

    def test_long_first_sentence_kept_whole(self):
        """Never cut mid-sentence: a 200-char first sentence is kept intact."""
        first = (
            "A man, who has lived alone in the mountains for forty years with nothing but "
            "his goats and a radio, returns to the village where he was born and discovers "
            "that nobody remembers him."
        )
        text = first + " Then more happens."
        assert len(first) > 180
        assert _compact_logline(text) == first

    def test_endless_sentence_marked_with_ellipsis(self):
        """With no sentence end in reach, the cut is marked with an ellipsis, not a fake full stop."""
        long = "A really long logline without any sentence breaks that just keeps going and going " * 5
        result = _compact_logline(long)
        assert result.endswith("\u2026")
        assert not result.endswith(".\u2026")
        assert len(result) <= 300
        assert long.startswith(result[:-1])

    def test_under_120_chars_unchanged(self):
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
        assert "[Book]" in result
        assert "picturehouses.com" in result

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
    def test_ordered_by_metacritic_then_title(self):
        """Highest Metacritic first; ties and unscored films alphabetical (case-insensitive)."""
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)

        def film(title, mc):
            return Film(
                title=title,
                screenings=[
                    Screening(
                        cinema="Clapham",
                        date=datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ),
                        booking_url="https://example.com",
                    ),
                ],
                scores=Scores(metacritic=mc, imdb=9.9 if mc is None else None),
            )

        films = [
            film("alpha unscored", None),
            film("Zebra Film", 90),
            film("Mid Film", 60),
            film("Beta Film", 60),
            film("Omega unscored", None),
        ]
        result = format_digest(films, now=now)
        order = [line.split("**")[1] for line in result.splitlines() if line.startswith("- **")]
        assert order == ["Zebra Film", "Beta Film", "Mid Film", "alpha unscored", "Omega unscored"]
        # The HTML version uses the same order
        html = format_digest_html(films, now=now)
        positions = [html.index(t) for t in order]
        assert positions == sorted(positions)

    def test_empty_films_warns_listings_may_have_changed(self):
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)
        result = format_digest([], now=now)
        assert LISTINGS_WARNING in result
        assert "No qualifying screenings" not in result

    def test_notes_and_suspect_banner(self):
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)
        film = Film(
            title="Only Film",
            screenings=[Screening("Ritzy", datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ), "u")],
            scores=Scores(),
        )
        result = format_digest([film], now=now, notes=["Could not fetch the Clapham listings."], listings_suspect=True)
        assert "WARNING: part of the listings could not be read" in result
        assert "* Could not fetch the Clapham listings." in result
        assert "Only Film" in result

    def test_incomplete_scores_marked(self):
        film = Film(
            title="Slow Film",
            screenings=[Screening("Ritzy", datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ), "u")],
            scores=Scores(),
            scores_incomplete=True,
        )
        assert "N/A / N/A / N/A (scores not fetched (time limit))" in format_film_line(film)
        assert "scores not fetched (time limit)" in format_digest_html([film])


class TestIsHighlighted:
    def test_none_scores(self):
        assert is_highlighted(None) is False

    def test_empty_scores(self):
        assert is_highlighted(Scores()) is False

    def test_metacritic_76(self):
        assert is_highlighted(Scores(metacritic=76)) is True

    def test_metacritic_75(self):
        assert is_highlighted(Scores(metacritic=75)) is False

    def test_imdb_77(self):
        assert is_highlighted(Scores(imdb=7.7)) is True

    def test_imdb_76(self):
        assert is_highlighted(Scores(imdb=7.6)) is False

    def test_rt_not_used_for_highlight(self):
        assert is_highlighted(Scores(rotten_tomatoes=100)) is False

    def test_mc_qualifies_alone(self):
        assert is_highlighted(Scores(metacritic=80, imdb=5.0, rotten_tomatoes=20)) is True


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
        assert "the listings page may have changed" in result
        assert "No qualifying screenings" not in result

    def test_html_notes_escaped(self):
        result = format_digest_html([], notes=["<b>bad</b> & worse"])
        assert "&lt;b&gt;bad&lt;/b&gt; &amp; worse" in result
        assert "<b>bad</b>" not in result

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
        assert "If I Had Legs I&#x27;d Kick You" in result

    def test_html_escapes_markup_in_scraped_fields(self):
        now = datetime(2026, 3, 11, 10, 0, tzinfo=LONDON_TZ)
        film = Film(
            title='<script>alert(1)</script>',
            director='"><img src=x onerror=alert(1)>',
            logline="<iframe src=evil>",
            screenings=[Screening("Ritzy", datetime(2026, 3, 11, 19, 0, tzinfo=LONDON_TZ), "u")],
            scores=Scores(),
        )
        result = format_digest_html([film], now=now)
        assert "<script>" not in result
        assert "<img src=x" not in result
        assert "<iframe" not in result
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result
