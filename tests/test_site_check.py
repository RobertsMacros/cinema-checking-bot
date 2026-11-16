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


def test_missing_cinema_fails():
    problems = check_payload(_payload(cinemas=("Ritzy",)), NOW, 30, 15)
    assert any("Clapham" in p for p in problems)


def test_main_exits_non_zero_on_problems(capsys):
    code = main(["--url", "https://example.invalid"], fetch=lambda url: _payload(age_hours=100), now=NOW)
    assert code == 1
    assert "old" in capsys.readouterr().out


def test_main_reads_films_json(capsys):
    seen = []
    code = main(["--url", "https://example.invalid/"], fetch=lambda url: seen.append(url) or _payload(), now=NOW)
    assert code == 0
    assert seen == ["https://example.invalid/films.json"]
