"""Configuration loading from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


CINEMAS = {
    "Clapham": "https://film.datathistle.com/cinema/46847-clapham-picturehouse-london-sw4/",
    "Ritzy": "https://film.datathistle.com/cinema/46857-ritzy-picturehouse-brixton/",
}

# Picturehouse website pages (stable links for booking)
CINEMA_URLS = {
    "Clapham": "https://www.picturehouses.com/cinema/clapham-picturehouse",
    "Ritzy": "https://www.picturehouses.com/cinema/the-ritzy",
}

# Picturehouse cinema codes for movie-details URLs
CINEMA_CODES = {
    "Clapham": "020",
    "Ritzy": "004",
}

PH_WHATS_ON_URL = "https://www.picturehouses.com/whats-on"

# Minimum number of films we expect per cinema. If we find fewer, something
# is likely wrong with the scraper or the page structure has changed.
MIN_FILMS_PER_CINEMA = 3

# Whole-run time budget. Score lookups stop when it is used up (minus a reserve
# for formatting and sending) so the digest always goes out. Keep this well
# under the GitHub Actions job timeout.
RUN_TIME_BUDGET_SECONDS = 8 * 60
SEND_RESERVE_SECONDS = 90


def _env(name: str, default: str) -> str:
    """Read an env var, treating empty as unset.

    GitHub Actions passes secrets that are not defined as empty strings.
    """
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment."""

    omdb_api_key: str
    tmdb_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    email_to: list[str]
    dry_run: bool

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()
        return cls(
            omdb_api_key=os.environ.get("OMDB_API_KEY", ""),
            tmdb_api_key=os.environ.get("TMDB_API_KEY", ""),
            smtp_host=_env("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(_env("SMTP_PORT", "587")),
            smtp_user=os.environ.get("SMTP_USER", ""),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            email_from=os.environ.get("EMAIL_FROM", ""),
            email_to=[
                a.strip()
                for a in os.environ.get("EMAIL_TO", "").split(",")
                if a.strip()
            ],
            dry_run=os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes"),
        )
