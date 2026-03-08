"""Configuration loading from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


CINEMAS = {
    "Clapham": "https://film.datathistle.com/cinema/46847-clapham-picturehouse-london-sw4/",
    "Ritzy": "https://film.datathistle.com/cinema/46857-ritzy-picturehouse-brixton/",
}

# Minimum number of films we expect per cinema. If we find fewer, something
# is likely wrong with the scraper or the page structure has changed.
MIN_FILMS_PER_CINEMA = 3


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
            smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
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
