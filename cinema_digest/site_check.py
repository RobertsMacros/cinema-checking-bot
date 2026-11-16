"""Check the hosted site from outside, after a deploy or on a schedule.

Reads <url>/films.json and fails (exit code 1) when the listings are older
than --max-age-hours, have fewer than --min-films films at a cinema, leave
out a configured cinema, or carry the page's own incomplete-listings
warning. This checks what visitors actually get, not whether a build step
exited cleanly.

    python -m cinema_digest.site_check --url https://clapham-ritzy-cinema.netlify.app
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Callable

import requests

from cinema_digest.config import CINEMAS

DEFAULT_URL = "https://clapham-ritzy-cinema.netlify.app"
# The site is rebuilt daily; allow for a late GitHub schedule.
DEFAULT_MAX_AGE_HOURS = 30
# The site lists only films with an evening or weekend showing in the next 7
# days: 11 at Clapham and 13 at the Ritzy on 16 Nov 2026 (from 65 and 64 on
# the pages). This floor is a backstop; a short Picturehouse page or a fall
# back to Data Thistle already sets the page's warning, which fails the check.
DEFAULT_MIN_FILMS_PER_CINEMA = 5


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

    # The floor applies per cinema: 19 at one and 1 at the other is not a full site
    films = payload.get("films") or []
    for cinema in CINEMAS:
        n = sum(1 for film in films if cinema in (film.get("cinemas") or []))
        if n == 0:
            problems.append(f"no films listed for {cinema}")
        elif n < min_films:
            problems.append(f"only {n} films listed for {cinema} (expected at least {min_films})")

    # The page's own flags: a fallback or partial week deploys with a warning
    # banner, and that must not pass as a healthy site
    if payload.get("warning"):
        problems.append(f"the site is flagged as incomplete: {payload['warning']}")
    if payload.get("error"):
        problems.append(f"the last refresh failed: {payload['error']}")
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
    parser.add_argument("--min-films", type=int, default=DEFAULT_MIN_FILMS_PER_CINEMA,
                        help="films with a showing, per cinema")
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
