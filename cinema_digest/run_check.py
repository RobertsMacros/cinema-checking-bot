"""Fail a digest run whose output doesn't match the Picturehouse pages.

Reads the listings_check.json written by `python -m cinema_digest.main
--report DIR` and exits 1 (a red GitHub Actions run) when the listings did
not come from Picturehouse, were flagged as incomplete, or a film with a
showing in the digest's windows is missing from the digest. The email has
already been sent by then; this makes the problem visible as a failed run.

    python -m cinema_digest.run_check run-report/listings_check.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cinema_digest.config import CINEMAS


def problems(check: dict) -> list[str]:
    """What is wrong with this run's output (empty when it matches the pages)."""
    out: list[str] = []
    sources = check.get("sources") or []
    if "Picturehouse" not in sources:
        out.append(f"Listings did not come from the Picturehouse pages (sources: {', '.join(sources) or 'none'})")
    if check.get("listings_suspect"):
        out.append("The digest was flagged as incomplete: " + "; ".join(check.get("warnings") or []))
    cinemas = check.get("cinemas") or {}
    for cinema in CINEMAS:
        entry = cinemas.get(cinema)
        if entry is None:
            out.append(f"No Picturehouse page was read for {cinema}")
        elif entry.get("missing_from_digest"):
            out.append(
                f"{cinema}: on the Picturehouse page but missing from the digest: "
                + ", ".join(entry["missing_from_digest"])
            )
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m cinema_digest.run_check <listings_check.json>")
        return 2
    path = Path(args[0])
    try:
        check = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"FAIL: could not read {path}: {e}")
        return 1
    found = problems(check)
    for p in found:
        print(f"FAIL: {p}")
    if found:
        return 1
    counts = ", ".join(
        f"{c}: {len(e.get('qualifying_on_page') or [])} of {e.get('films_on_page')} films have showings in the windows"
        for c, e in check["cinemas"].items()
    )
    print(f"OK: every qualifying Picturehouse film is in the digest ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
