"""Films Robert parked on "Wait and see" in What's On, flagged in the digest.

What's On (RobertsMacros/whats-on) has a Wait and see button for films with
no reviews yet: the film waits there until its Metacritic score reaches a bar
(75 by default). Its Populate run writes that list to this repository's
Actions variable CONSIDERING as JSON:

    [{"title": "Dune: Part Three", "year": "2026", "bar": 75, "score": null}]

Titles, years, bars and scores only; nothing else about the decision. An
empty or missing variable means nothing is flagged.
"""

from __future__ import annotations

import json
import logging
import os

from cinema_digest.models import Film
from cinema_digest.scraper import normalize_title

logger = logging.getLogger(__name__)

DEFAULT_BAR = 75


def load(raw: str | None = None) -> list[dict]:
    """The CONSIDERING list, or [] when it is missing or unreadable."""
    raw = os.environ.get("CONSIDERING", "") if raw is None else raw
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("CONSIDERING is not valid JSON; no films flagged")
        return []
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict) and isinstance(d.get("title"), str) and d["title"].strip()]


def _year(v) -> int | None:
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


def mark(films: list[Film], entries: list[dict]) -> int:
    """Set film.considering on every listed film that matches; returns how many.

    Matches on the normalised title; when both sides carry a year they must be
    within a year of each other, so a remake with the same title is not flagged.
    """
    by_title: dict[str, list[dict]] = {}
    for e in entries:
        by_title.setdefault(normalize_title(e["title"]), []).append(e)
    n = 0
    for film in films:
        for e in by_title.get(normalize_title(film.title), []):
            ey = _year(e.get("year"))
            if ey and film.year and abs(ey - film.year) > 1:
                continue
            bar = e.get("bar") if isinstance(e.get("bar"), int) else DEFAULT_BAR
            film.considering = {"bar": bar}
            n += 1
            break
    return n


def label(film: Film) -> str | None:
    """One line for the digest: whether the film has cleared Robert's bar."""
    if not film.considering:
        return None
    bar = film.considering["bar"]
    mc = film.scores.metacritic if film.scores else None
    if mc is None:
        return f"On your Wait and see list: no Metacritic score yet (you wanted {bar})"
    if mc >= bar:
        return f"On your Wait and see list: Metacritic {mc} clears your {bar}"
    return f"On your Wait and see list: Metacritic {mc}, under your {bar}"
