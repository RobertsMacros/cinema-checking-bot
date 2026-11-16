# Handover

**Repo:** `RobertsMacros/cinema-checking-bot` (public)
**Live site:** https://clapham-ritzy-cinema.netlify.app (Netlify project `clapham-ritzy-cinema`)
**Review this follows:** `docs/reviews/playbook-review-2026-11-15.md` (section E lists the open problems)
**Fix branch:** `claude/dazzling-hopper-1h5hjl` (not merged; nothing here is live until it is)

## What this project is

A bot that collects film listings for two London cinemas (Clapham Picturehouse and the Ritzy, Brixton), keeps evening and weekend showtimes for the next 7 days, adds review scores (Metacritic, IMDb, Rotten Tomatoes) and outputs them two ways:

1. **Email digest.** `python -m cinema_digest.main`, run weekly by `.github/workflows/cinema_digest.yml`.
2. **Web page.** Local: `python -m cinema_digest.webapp` (Flask, in-memory cache). Hosted: `build_static.py` writes `public/films.json` and `public/index.html`, deployed daily by `.github/workflows/deploy_site.yml`.

Pipeline: `scraper.scrape_all()` (Picturehouse pages through headless Chromium, Data Thistle as backup) → `filters.filter_screenings()` → `enrich.enrich_films()` → formatter (email) or `webapp.serialize_film()` (web).

## Current state

| Area | State |
|---|---|
| Listings source | Picturehouse cinema pages since 13 Nov (`105f800`), Data Thistle fills gaps and is the fallback |
| Live website | **Still the 7 Oct manual upload.** It will stay frozen until the deploy secrets below are added and this branch is merged |
| Daily website deploy | `deploy_site.yml` builds in GitHub Actions, deploys with the Netlify CLI and checks the live `films.json`. It fails red without its secrets (the old `netlify_rebuild.yml` skipped and went green) |
| Stale page warning | A static snapshot over 36 hours old shows a yellow "out of date" banner |
| Incomplete listings | Fewer than 15 films at a cinema, or a fall back to Data Thistle, flags the subject "[CHECK: listings incomplete]" (it used to be a body note only, with a floor of 3) |
| Proof per digest run | Each run uploads a report (digest, Picturehouse pages, `listings_check.json`) and `run_check` turns the run red if a film on the pages is missing from the digest |
| Tests | Run on every push (including `claude/**` branches), on PRs and weekly; browser tests of the page run in CI |

## Needs Robert

These need your accounts, secrets or decisions. Nothing here has been done.

| # | What | Exact steps |
|---|---|---|
| R1 | Turn on the daily website deploy (fixes the frozen site) | 1. Netlify → User settings → Applications → Personal access tokens → New access token; copy it. 2. Netlify → `clapham-ritzy-cinema` → Project configuration → General → Project details → copy Project ID. 3. GitHub → this repo → Settings → Secrets and variables → Actions → New repository secret: `NETLIFY_AUTH_TOKEN` (the token) and `NETLIFY_SITE_ID` (the ID). 4. After merging this branch: Actions → Deploy website → Run workflow on `main`. 5. Check the run is green and its last step prints `OK: <n> films`. 6. Open the site and check the "Updated" time is today |
| R3 | Prove the Picturehouse switch on real pages (the 13 Nov "done" was based on one run that never compared the digest with the pages) | After merging: Actions → Cinema Digest → Run workflow → tick **Dry run** → Run. When it finishes: the last step should print `OK: every qualifying Picturehouse film is in the digest (...)`. Download the `digest-run-<n>` artefact and open `digest.html`; compare its film list with picturehouses.com for both cinemas this week. If the step is red, the log names the missing films |
| R4 | Check the first scheduled digest on the new code | The next Tuesday run: it should be green, the email subject should have no "[CHECK" tag, and the artefact's `listings_check.json` should show 60 or more `films_on_page` per cinema |
| R2 | Delete the old build hook secret if you ever created one | Settings → Secrets and variables → Actions: remove `NETLIFY_BUILD_HOOK` if listed (the workflow that used it is gone) |

## Definition of done for the website

- The latest "Deploy website" run on `main` is green, including its live-site check.
- The live `films.json` is under 30 hours old, lists at least 15 films and includes both cinemas (`python -m cinema_digest.site_check` exits 0).
- Netlify's current deploy says "GitHub Actions run …", not "Deploy triggered by upload".

## How to run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium
pytest tests/ -q
python -m cinema_digest.webapp        # http://127.0.0.1:5000
python build_static.py                # writes public/ (what Netlify serves)
python -m cinema_digest.main --dry-run
python -m cinema_digest.site_check    # is the live site fresh and complete?
```

Optional env vars, which improve score lookups: `OMDB_API_KEY` and `TMDB_API_KEY` (see `.env.example`).
