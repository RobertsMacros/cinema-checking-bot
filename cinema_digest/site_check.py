"""Check the hosted site from outside, after a deploy or on a schedule.

Reads <url>/films.json and fails (exit code 1) when the listings are older
than --max-age-hours, have fewer than --min-films films, or leave out a
configured cinema. This checks what visitors actually get, not whether a
build step exited cleanly.

    python -m cinema_digest.site_check --url https://clapham-ritzy-cinema.netlify.app
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Callable

import requests

from cinema_digest.config import CINEMAS, MIN_FILMS_PER_CINEMA

DEFAULT_URL = "https://clapham-ritzy-cinema.netlify.app"
# The site is rebuilt daily; allow for a late GitHub schedule.
DEFAULT_MAX_AGE_HOURS = 30


def check_payload(payload: dict, now: datetime, max_age_hours: float, min_films: int) -> list[str]:
    """Return what is wrong with a films.json payload (empty when it looks right)."""
    problems: list[str] = []
    fetched = payload.get("fetched_at")
    if not fetched:
        problems.append("films.json has no fetched_at time, so its age is unknown")
    else:
        age = (now - datetime.fromisoformat(fetched)).total_seconds() / 3600
        if age > max_age_hours:
            problems.append(f"listings are {age:.0f} hours old (limit {max_age_hours:g})")

    count = payload.get("count") or 0
    if count < min_films:
        problems.append(f"only {count} films listed (expected at least {min_films})")

    seen = {c for film in payload.get("films") or [] for c in film.get("cinemas") or []}
    for cinema in CINEMAS:
        if cinema not in seen:
            problems.append(f"no films listed for {cinema}")
    return problems


def _fetch(url: str) -> dict:
    resp = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
    resp.raise_for_status()
    return resp.json()


def main(
    argv: list[str] | None = None,
    fetch: Callable[[str], dict] = _fetch,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Check the hosted listings are fresh and complete")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    parser.add_argument("--min-films", type=int, default=MIN_FILMS_PER_CINEMA)
    args = parser.parse_args(argv)

    url = args.url.rstrip("/") + "/films.json"
    try:
        payload = fetch(url)
    except Exception as e:
        print(f"FAIL: could not read {url}: {type(e).__name__}: {e}")
        return 1
    problems = check_payload(payload, now or datetime.now(timezone.utc), args.max_age_hours, args.min_films)
    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        return 1
    print(f"OK: {payload.get('count')} films, fetched {payload.get('fetched_at')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
