"""Generated output stays out of the repository."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_no_generated_html_tracked_at_the_root():
    # _test_digest.html and digest_preview.html were committed by accident before.
    # Checks what git tracks: a local dry run's ignored preview is fine on disk.
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    tracked = subprocess.run(["git", "ls-files", "*.html"], cwd=ROOT, capture_output=True, text=True, check=True)
    assert [f for f in tracked.stdout.split() if "/" not in f] == []


def test_generated_folders_are_ignored():
    ignored = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()}
    for entry in ("digest_preview.html", "public/", "run-report/", ".cache/", ".env"):
        assert entry in ignored, entry
