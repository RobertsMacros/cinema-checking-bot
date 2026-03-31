"""Data models for cinema digest."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Screening:
    """A single screening of a film at a specific cinema."""

    cinema: str  # "Clapham" or "Ritzy"
    date: datetime  # timezone-aware (Europe/London)
    booking_url: str
    screening_type: str | None = None  # "Senior", "Kids", "Subtitled", etc.


@dataclass
class Scores:
    """Review scores from external sources."""

    metacritic: int | None = None  # 0-100
    imdb: float | None = None  # 0.0-10.0
    rotten_tomatoes: int | None = None  # 0-100
    imdb_id: str | None = None  # e.g. "tt1234567"
    mc_slug: str | None = None  # e.g. "sinners"
    rt_slug: str | None = None  # e.g. "/m/the_great_gatsby_2013"


@dataclass
class Film:
    """A film with its metadata, screenings, and scores."""

    title: str
    year: int | None = None
    duration: str | None = None  # raw string like "2h 6min"
    logline: str | None = None
    director: str | None = None
    listing_url: str | None = None  # Data Thistle listing page
    ph_url: str | None = None  # Picturehouse movie-details page
    screenings: list[Screening] = field(default_factory=list)
    scores: Scores | None = None
