"""Helpers for tests that render the web page in headless Chromium.

The page is loaded from a string with its data inlined, every other request
is blocked, and the page clock is frozen, so these tests stay offline and
do not depend on today's date.

If Chromium can't start, the tests are skipped, unless REQUIRE_BROWSER_TESTS=1
(set in CI), when they fail instead. PLAYWRIGHT_CHROMIUM_EXECUTABLE points at
a browser binary when Playwright's own download is missing.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime

import pytest

from cinema_digest.webapp_template import PAGE_HTML


def page_html(payload: dict, now: datetime, static: bool = True) -> str:
    """The web page with `payload` inlined as its data and the clock set to `now`."""
    data_url = "data:application/json," + json.dumps(payload).replace("%", "%25").replace("#", "%23")
    html = PAGE_HTML.replace('window.FILMS_URL || "/api/films"', json.dumps(data_url))
    if static:
        html = html.replace("window.STATIC_SNAPSHOT = false", "window.STATIC_SNAPSHOT = true")
    freeze = f"<script>(function(){{const t=Date.parse({json.dumps(now.isoformat())});Date.now=()=>t;}})();</script>"
    return html.replace("<head>", "<head>" + freeze, 1)


@contextmanager
def open_page(html: str):
    """Yield a Playwright page showing `html` once its listings have rendered."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        _unavailable("Playwright is not installed")
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page()
            # Only the inlined page and its data: URL may load
            page.route("**/*", lambda route: route.abort())
            page.set_content(html, wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#content .state.error, #content .grid, #content .state:not(:has(.spinner))')")
            yield page
        finally:
            browser.close()


def _launch(p):
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    try:
        return p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
    except Exception as e:  # browser missing or cannot start
        _unavailable(f"Chromium could not start: {e}")


def _unavailable(reason: str):
    if os.environ.get("REQUIRE_BROWSER_TESTS", "").lower() in ("1", "true", "yes"):
        pytest.fail(reason)
    pytest.skip(reason)
