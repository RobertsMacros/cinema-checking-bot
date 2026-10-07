"""Build a static version of the web app for hosting (e.g. Netlify).

Runs the same scrape -> filter -> enrich pipeline as the live app, writes
the result to ``public/films.json`` and the page to ``public/index.html``.
The listings are a snapshot from build time; rebuild to refresh them.

    python build_static.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from cinema_digest.main import setup_logging
from cinema_digest.webapp import build_payload
from cinema_digest.webapp_template import PAGE_HTML

OUT_DIR = Path(__file__).resolve().parent / "public"

logger = logging.getLogger("cinema_digest.build_static")


def main() -> None:
    # Redacts API keys from logs: request errors include the full URL, and
    # Netlify keeps build logs.
    setup_logging()
    OUT_DIR.mkdir(exist_ok=True)

    # build_payload never raises: scrape failures come back in payload["error"],
    # so the site still deploys and shows the error instead of failing the build.
    payload = build_payload(force_refresh=True)
    (OUT_DIR / "films.json").write_text(json.dumps(payload), encoding="utf-8")

    html = PAGE_HTML.replace('window.FILMS_URL || "/api/films"', '"films.json"')
    html = html.replace("window.STATIC_SNAPSHOT = false", "window.STATIC_SNAPSHOT = true")
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")

    logger.info(
        "Wrote %d films to %s (error=%s)", payload["count"], OUT_DIR, payload["error"]
    )


if __name__ == "__main__":
    main()
