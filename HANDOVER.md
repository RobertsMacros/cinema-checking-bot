# Handover

**Repo:** `RobertsMacros/cinema-checking-bot` (public)
**Live site:** https://clapham-ritzy-cinema.netlify.app (Netlify project `clapham-ritzy-cinema`)
**Review this follows:** `docs/reviews/playbook-review-2026-11-15.md` (section E lists the open problems)
**Fixes:** branch `claude/dazzling-hopper-1h5hjl`, merged into `main` through PR #6 on 16 Nov 2026 with Robert's approval. Results per item: `docs/reviews/fixes-2026-11-16.md`. Decisions: `DECISIONS.md`

## What this project is

A bot that collects film listings for two London cinemas (Clapham Picturehouse and the Ritzy, Brixton), keeps evening and weekend showtimes for the next 7 days, adds review scores (Metacritic, IMDb, Rotten Tomatoes) and outputs them two ways:

1. **Email digest.** `python -m cinema_digest.main`, run weekly by `.github/workflows/cinema_digest.yml`.
2. **Web page.** Local: `python -m cinema_digest.webapp` (Flask, in-memory cache). Hosted: `build_static.py` writes `public/films.json` and `public/index.html`, deployed daily by `.github/workflows/deploy_site.yml`.

Pipeline: `scraper.scrape_all()` (Picturehouse pages through headless Chromium, Data Thistle as backup) → `filters.filter_screenings()` → `enrich.enrich_films()` → formatter (email) or `webapp.serialize_film()` (web).

## Current state

| Area | State |
|---|---|
| Listings source | Picturehouse cinema pages since 13 Nov (`105f800`), Data Thistle fills gaps and is the fallback |
| Live website | **Still the 7 Oct manual upload.** It stays frozen until the deploy secrets (R1) are added. Until then the daily "Deploy website" run fails red, by design |
| Daily website deploy | `deploy_site.yml` builds in GitHub Actions, deploys with the Netlify CLI and checks the live `films.json`. It fails red without its secrets (the old `netlify_rebuild.yml` skipped and went green) |
| Stale page warning | A static snapshot over 36 hours old shows a yellow "out of date" banner; when every showtime in it has passed, the page says so instead of "No films match your filters" |
| Incomplete listings | Fewer than 15 films at a cinema, or a fall back to Data Thistle, flags the subject "[CHECK: listings incomplete]" (it used to be a body note only, with a floor of 3) |
| Digest send time | Scheduled for Tuesday 12:17 UTC (was 17:00 UTC, which GitHub started at 20:10 to 22:07 UTC in Oct and Nov, after the evening's screenings began). See R5 to change it |
| Provenance | Email, plain text and web footers name the sources actually used, credit OMDb and TMDB (TMDB's required notice) and say "Not affiliated with Picturehouse Cinemas." They used to say "Listings from Data Thistle" even after the switch |
| Accessibility | Text contrast now 5.2:1 or better on the page (was 3.1 to 3.9:1) and in the email; labelled search box; score icons named; cinema filter reports which is selected and keeps keyboard focus; `lang="en-GB"`; em dashes gone from headings |
| Event titles | "MUBI FEST LIVE: A LONG WINTER + Q&A" and similar are looked up as the film ("A LONG WINTER"); the digest still shows the listed title. Not yet checked against OMDb itself (needs a live run, R3) |
| Film page links | The link read from the cinema's own Picturehouse page is kept; the what's-on title match (fragile) only fills films that have none, and isn't fetched when every film has a link |
| Proof per digest run | Each run uploads a report (digest, Picturehouse pages, `listings_check.json`) and `run_check` turns the run red if a film on the pages is missing from the digest |
| Tests | Run on every push (including `claude/**` branches), on PRs and weekly; browser tests of the page run in CI |

## Needs Robert

Only what needs your accounts, secrets, settings or Mac. Everything else from the earlier list is done or moved to the follow-ups below.

| # | What | Exact steps |
|---|---|---|
| R1 | Turn on the daily website deploy (the live site is still the 7 Oct upload) | 1. Netlify → User settings → Applications → Personal access tokens → New access token; copy it. 2. Netlify → `clapham-ritzy-cinema` → Project configuration → General → Project details → copy Project ID. 3. GitHub → this repo → Settings → Secrets and variables → Actions → New repository secret: `NETLIFY_AUTH_TOKEN` (the token) and `NETLIFY_SITE_ID` (the ID). 4. Actions → Deploy website → Run workflow on `main`. 5. The run should be green and its last step print `OK: <n> films`. 6. Open the site: "Updated" should show today. While you are in Secrets, delete `NETLIFY_BUILD_HOOK` if it is listed (nothing uses it now) |
| R2 | Add the TMDB key | Free key at themoviedb.org → Settings → API. GitHub → Settings → Secrets and variables → Actions → New repository secret `TMDB_API_KEY`. The next digest run's report should show `tmdb_key_set: true` |
| R3 | Let What's On feed the Wait and see list | `considering.json` has been `[]` since 28 Sep. What's On's Populate task (`docs/populate-task.md` step f2 in the whats-on repo) is meant to clone this repo, write the file and push to `main`, but nothing has ever arrived, most likely because the session that runs it can't push here. In the Claude task or environment that runs Populate, add `RobertsMacros/cinema-checking-bot` with push access. If you also do R4, that push to `main` will be refused: either let Populate open a PR instead (a change in whats-on) or give it a bypass in the ruleset |
| R4 | Protect `main` | GitHub → Settings → Rules → Rulesets → New branch ruleset for `main`: require a pull request, require the three `test` status checks, block force pushes. 23 of the 45 commits on `main` before this work were pushed directly. Mind the Populate push in R3 |
| R5 | Tidy the old branches | This session's git access can only push its own branch, so I couldn't do this. On GitHub → Branches, delete `claude/newsletter-cinema-webapp-0vlt2a`, `claude/readme-roberts-macros` and `claude/whats-on-roadmap-review-02klzo` (all fully merged). For `claude/reformat-logline-display-w9uNK` (two commits never merged through a PR; their changes reached `main` by hand in `2e0f59c`), first make a tag to keep them: Releases → Draft a new release → Choose a tag → type `archive/reformat-logline-display-w9uNK`, target that branch → Create tag, discard the draft. Then delete the branch (DEC-5) |
| R6 | Keep your personal email out of future commits | On your Mac: `git config --global user.email <id>+RobertsMacros@users.noreply.github.com` (the exact address is on GitHub → Settings → Emails). On that page tick "Keep my email addresses private" and "Block command line pushes that expose my email". 24 older commits carry your personal address. Removing it needs a history rewrite of a public repo, which breaks clones and can't recall copies, so I recommend leaving them |

## Follow-ups for an agent session (no Robert needed)

| # | What | How |
|---|---|---|
| F1 | Check the first scheduled digest on the new code (Tue 17 Nov, 12:17 UTC) | The run should be green, the subject should have no "[CHECK" tag, and `run_check` should print OK. If GitHub starts it late, note the delay against DEC-1 |
| F2 | Check the first real deploy once R1 is done | Green run, `site_check` OK, Netlify deploy titled "GitHub Actions run …", and how long the build took (review item E16) |
| F3 | Hide sold-out sessions | Needs a saved Picturehouse page with a sold-out session. Every digest run's artefact holds the pages (`picturehouse-<cinema>.html`); download one from a week with a sold-out showing (this session's network could not reach artefact storage), save the film's block as a fixture, then drop those sessions in `ph_scraper.parse_ph_listings` with a test |
| F4 | Publish the coordination records | This session could not reach `RobertsMacros/project-coordination-data`. From a session with `gh` access to it, run `python3 .coordination/report.py retry --event <id> --actor f6939167-7453-452d-837c-185ca19555c4` for each event added on 16 Nov in `.coordination/events/` |
| F6 | Replace hand-written Data Thistle markup in the parser tests with real pages | `tests/test_scraper.py` (`SAMPLE_HTML`, from before this work) tests the Data Thistle parser on hand-written HTML, against the CLAUDE.md fixture rule. This session could not reach Data Thistle. Each run report now saves `datathistle-<cinema>.html`: download one artefact, trim the pages into `tests/fixtures/` and point those tests at them |
| F5 | Proposal, not started: house UI rules | The web page and email still use a serif font and middle dots (U1). A restyle should start from two or three mock-ups for Robert to choose from |

## Done on 16 Nov from the earlier list

- Review and merge: PR #6, after an independent review and green checks on the final head.
- Proof on real pages: dry run 43844098986 (no email) read 65 Clapham and 64 Ritzy films, and `run_check` printed "OK: every qualifying Picturehouse film is in the digest".
- Send time kept at 12:17 UTC (DEC-1). MIT licence added (DEC-2). Logo removed from the public page (DEC-3). Highlight and Wait and see bars kept separate (DEC-4).

## Definition of done for the website

- The latest "Deploy website" run on `main` is green, including its live-site check.
- The live `films.json` is under 30 hours old, lists at least 5 films with showings at each cinema and carries no incomplete-listings warning (`python -m cinema_digest.site_check` exits 0).
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
