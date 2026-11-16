"""Guards on the GitHub Actions workflows, read as text (no YAML parser needed)."""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text()


def _all():
    return {p.name: p.read_text() for p in WORKFLOWS.glob("*.yml")}


def test_no_workflow_skips_silently_when_a_secret_is_missing():
    # A missing secret must turn the run red. "warning ... exit 0" kept the
    # old rebuild green for 39 days while it did nothing.
    for name, text in _all().items():
        assert not re.search(r"::warning::[^\n]*not set[^\n]*\n\s*exit 0", text), name


def test_website_deploy_fails_without_its_secrets_and_checks_the_live_site():
    text = _read("deploy_site.yml")
    assert "NETLIFY_AUTH_TOKEN" in text and "NETLIFY_SITE_ID" in text
    assert re.search(r"::error::Missing repository secret", text)
    assert "exit 1" in text
    assert "playwright install --with-deps chromium" in text
    assert "cinema_digest.site_check" in text


def test_actions_are_on_node_24_versions():
    # checkout@v4, setup-python@v5 and cache@v4 run on the deprecated Node 20
    minimum = {"actions/checkout": 5, "actions/setup-python": 6, "actions/cache": 5, "actions/upload-artifact": 6}
    for name, text in _all().items():
        for action, version in re.findall(r"uses:\s*(actions/[\w-]+)@v(\d+)", text):
            assert int(version) >= minimum.get(action, 0), f"{name}: {action}@v{version}"


def test_digest_is_scheduled_early_enough_to_survive_github_delays():
    # Scheduled at 17:00 UTC it started between 20:10 and 22:07 UTC in Oct and
    # Nov 2026, after Tuesday's evening screenings had begun. Start by 12:xx
    # UTC, off the hour (on-the-hour schedules are delayed most). The worst
    # delay seen was 5 h 7 min, so 12:17 still arrives before 18:00.
    minute, hour = re.search(r"cron:\s*'(\d+) (\d+) \* \* 2'", _read("cinema_digest.yml")).groups()
    assert int(minute) != 0
    assert int(hour) <= 12


def test_digest_run_saves_its_output_and_checks_it_against_the_pages():
    text = _read("cinema_digest.yml")
    assert "--report run-report" in text
    assert "actions/upload-artifact@" in text
    assert "python -m cinema_digest.run_check run-report/listings_check.json" in text
    # A manual dry run builds everything but sends no email
    assert re.search(r"dry_run:\s*\n\s*description:", text)
    assert "DRY_RUN: ${{ inputs.dry_run" in text


def test_tests_run_on_a_schedule_and_require_the_browser_tests():
    text = _read("tests.yml")
    assert re.search(r"^\s*schedule:\s*\n\s*- cron:", text, re.MULTILINE)
    assert "REQUIRE_BROWSER_TESTS" in text
    assert "playwright install --with-deps chromium" in text
