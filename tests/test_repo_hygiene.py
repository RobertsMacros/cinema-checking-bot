"""Generated output stays out of the repository."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_no_generated_html_at_the_root():
    # _test_digest.html and digest_preview.html were committed by accident before
    assert sorted(p.name for p in ROOT.glob("*.html")) == []


def test_generated_folders_are_ignored():
    ignored = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()}
    for entry in ("digest_preview.html", "public/", "run-report/", ".cache/", ".env"):
        assert entry in ignored, entry
