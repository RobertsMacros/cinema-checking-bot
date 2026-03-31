"""End-to-end integration test: scrape live site, filter, format."""

import pytest

from cinema_digest.scraper import scrape_all, _make_session, ScraperError
from cinema_digest.filters import filter_screenings
from cinema_digest.formatter import format_digest, format_digest_html


@pytest.mark.integration
class TestLiveScraping:
    """Tests against the live Data Thistle site. Skipped in CI."""

    @pytest.fixture(autouse=True)
    def _session(self):
        self.session = _make_session()

    def test_scrape_returns_films(self):
        films = scrape_all(session=self.session)
        assert len(films) >= 3, f"Expected at least 3 films, got {len(films)}"

    def test_films_have_titles(self):
        films = scrape_all(session=self.session)
        for film in films:
            assert film.title, f"Film has empty title: {film}"

    def test_films_have_screenings_or_are_upcoming(self):
        films = scrape_all(session=self.session)
        with_screenings = [f for f in films if f.screenings]
        assert len(with_screenings) >= 3, (
            f"Expected at least 3 films with screenings, got {len(with_screenings)}"
        )

    def test_screenings_have_booking_urls(self):
        films = scrape_all(session=self.session)
        for film in films:
            for s in film.screenings:
                assert s.booking_url, f"Screening for {film.title} has no booking URL"

    def test_filter_produces_results(self):
        films = scrape_all(session=self.session)
        filtered = filter_screenings(films)
        # There should be at least some films showing this week
        assert len(filtered) >= 1, "No films passed filtering - check time windows"

    def test_format_produces_output(self):
        films = scrape_all(session=self.session)
        filtered = filter_screenings(films)
        if not filtered:
            pytest.skip("No films to format this week")
        text = format_digest(filtered)
        assert "Cinema Digest" in text
        assert len(text) > 100

    def test_html_format_produces_output(self):
        films = scrape_all(session=self.session)
        filtered = filter_screenings(films)
        if not filtered:
            pytest.skip("No films to format this week")
        html = format_digest_html(filtered)
        assert "<!DOCTYPE html>" in html
        assert "Picturehouse" in html
