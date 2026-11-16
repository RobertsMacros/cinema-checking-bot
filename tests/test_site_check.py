"""Checking the live site after a deploy (cinema_digest.site_check)."""

from datetime import datetime, timedelta, timezone

import pytest

from cinema_digest.site_check import check_payload, main

NOW = datetime(2026, 11, 16, 7, 0, tzinfo=timezone.utc)


def _payload(age_hours=1, count=40, cinemas=("Clapham", "Ritzy"), warning=None):
    return {
        "fetched_at": (NOW - timedelta(hours=age_hours)).isoformat(),
        "count": count,
        "films": [{"cinemas": list(cinemas)}] * count,
        "warning": warning,
    }


def test_fresh_full_site_passes():
    assert check_payload(_payload(), NOW, max_age_hours=30, min_films=15) == []


def test_old_site_fails():
    problems = check_payload(_payload(age_hours=24 * 39), NOW, max_age_hours=30, min_films=15)
    assert any("old" in p for p in problems)


def test_missing_timestamp_fails():
    payload = _payload()
    payload["fetched_at"] = None
    assert check_payload(payload, NOW, 30, 15)


def test_too_few_films_fails():
    assert any("films" in p for p in check_payload(_payload(count=6), NOW, 30, 15))


def test_one_thin_cinema_fails_even_if_the_total_is_high():
    payload = _payload(count=20)
    payload["films"] = [{"cinemas": ["Clapham"]}] * 19 + [{"cinemas": ["Ritzy"]}]
    problems = check_payload(payload, NOW, 30, 15)
    assert any("Ritzy" in p for p in problems)


def test_missing_cinema_fails():
    problems = check_payload(_payload(cinemas=("Ritzy",)), NOW, 30, 15)
    assert any("Clapham" in p for p in problems)


def test_site_flagged_as_incomplete_fails():
    # A fallback week can still have 15+ films; the page's own warning says it is incomplete
    problems = check_payload(_payload(warning="WARNING: part of the listings could not be read"), NOW, 30, 15)
    assert any("incomplete" in p or "warning" in p for p in problems)


def test_site_with_a_refresh_error_fails():
    payload = _payload()
    payload["error"] = "The refresh found no listings for Ritzy."
    assert check_payload(payload, NOW, 30, 15)


def test_main_exits_non_zero_on_problems(capsys):
    code = main(["--url", "https://example.invalid"], fetch=lambda url: _payload(age_hours=100), now=NOW)
    assert code == 1
    assert "old" in capsys.readouterr().out


def test_main_reads_films_json(capsys):
    seen = []
    code = main(["--url", "https://example.invalid/"], fetch=lambda url: seen.append(url) or _payload(), now=NOW)
    assert code == 0
    assert seen == ["https://example.invalid/films.json"]


def test_default_floor_passes_a_real_normal_week():
    # 16 Nov 2026 dry run on the real pages: 11 Clapham and 13 Ritzy films had
    # evening or weekend showings; that must pass the default check
    from cinema_digest.site_check import DEFAULT_MIN_FILMS_PER_CINEMA

    payload = _payload(count=24)
    payload["films"] = [{"cinemas": ["Clapham"]}] * 11 + [{"cinemas": ["Ritzy"]}] * 13
    assert check_payload(payload, NOW, 30, DEFAULT_MIN_FILMS_PER_CINEMA) == []
