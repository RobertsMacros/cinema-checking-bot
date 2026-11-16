# Playbook review: cinema-checking-bot

Repository: `RobertsMacros/cinema-checking-bot` (public). Reviewed 15 Nov 2026, read-only. Nothing was changed, committed or pushed.

## How this review was done

| Source | What I read |
|---|---|
| Git history | All 52 commits on all 5 remote branches (`git log --all`, full messages and file stats), the branch graph, deleted files, author and committer dates, and commits that sit on branches but never reached `main` |
| Standing files | Full history of `CLAUDE.md`, `AGENTS.md` (3 commits each), `HANDOVER.md` (3), `README.md` (11), `EXPECTATIONS.md` (2), `.coordination/` (events, requests, README) |
| GitHub | All 5 PRs (bodies, timings), issues (none exist), all 115 Actions runs across 3 workflows, and job logs for 10 key runs (the March 2026 logs have expired: HTTP 410) |
| Hosting | Netlify project `clapham-ritzy-cinema` and its current deploy, read through the Netlify connector. A direct fetch of the live site was blocked by this container's proxy, so the page content itself is **unverified** |
| Code and tests | `cinema_digest/*.py`, workflows, `netlify.toml`, `build_static.py`, `.gitignore`, fixtures; ran the unit suite in a scratch venv: **221 passed in 1.77 s** |
| Coordination | `python3 .coordination/report.py requests` (read-only). It returned "GitHub did not confirm the request". I did not run `start`, because that publishes a claim and you asked for no pushes |

Limits: no PR review comments or Codex review text exist on GitHub (the Codex review only shows up as commit messages); no chat transcripts; no force pushes are visible (the reflog is fresh and the remote history shows none). Where something can't be shown from evidence I say **unknown**.

---

## (E) Unfinished fixes and open problems

Things reported as fixed or done that aren't, and known problems still open. Ordered by severity.

| # | Item | Evidence | What is still wrong | Severity |
|---|---|---|---|---|
| E1 | **Live website frozen since 7 Oct** | Netlify current deploy `6ac5e5df613d046c3703142a`, "Deploy triggered by upload", created 2026-10-07 06:25 UTC, no commit ref. PR #5 says "Live" | The live site is a CLI upload made **before** every Codex review fix (first fix commit `00ca33e` is 06:33). It has never been rebuilt. Hiding started showtimes (`f4f0457`) and Book-link rebuilding (`a1ab309`) came after the deploy, so the page probably still shows 7 to 13 Oct showtimes with Book links. Content unverified (proxy blocked) | **High** |
| E2 | **Daily rebuild reports success but does nothing** | 39 green "Rebuild website" runs, 8 Oct to 15 Nov (e.g. run 43716556227). Log: `NETLIFY_BUILD_HOOK secret is not set; skipping rebuild.` | The secret was never set and Netlify was never linked to the repo. HANDOVER definition of done ("hosted site rebuilds daily … pushes to the repo deploy") is unmet. The workflow exits 0 with a warning, so it is green every day | **High** |
| E3 | **Picturehouse-direct marked "done" without exact-scope proof** | `.coordination/events/9d785efb-….json` (commit `b667efe`), status `done` | The scope says done when a digest "lists every film shown on both Picturehouse pages for the week". The evidence is one manual run that parsed 65 + 68 films and sent 21. Nothing compares the digest with the pages. There is no `.coordination/reports/` verification report, which the coordination README says is needed for automatic completion. The web and static paths were not checked | Medium |
| E4 | **Fallback to Data Thistle is not flagged in the subject** | `cinema_digest/scraper.py:477-481` adds a warning but never sets `listings_suspect` | If Chromium or the Picturehouse page fails, the digest quietly goes back to the source that missed about 90% of films. Only a body note says so, and the subject line stays clean. That is the same failure that went unnoticed for months | Medium-high |
| E5 | **Safety threshold not raised** | `cinema_digest/config.py`: `MIN_FILMS_PER_CINEMA = 3`; HANDOVER says "Raise … to around 15–20" | Still too low to catch a mostly empty source | Medium |
| E6 | **Docs and credits still describe the old source** | `README.md:9`, `:322`, `:332`, `:335`; `EXPECTATIONS.md` "Scraper: Data Thistle Parsing"; `HANDOVER.md` §1 still calls the gap the "Main bug"; footers at `formatter.py:506` and `webapp_template.py:198` say "Listings from Data Thistle" | The HANDOVER definition of done requires docs to match the code. The architecture list leaves out `ph_scraper.py`, `webapp.py` and `considering.py`. The footers credit the wrong source | Medium |
| E7 | **Digest arrives 3 to 5 hours late** | Cron `0 17 * * 2`. Actual starts: 6 Oct 21:19, 13 Oct 21:37, 20 Oct 20:10, 27 Oct 21:01, 3 Nov 22:07, 10 Nov 21:59 UTC | By arrival, Tuesday's evening screenings have started and are filtered out as past. The README admits runs can be "an hour or more" late, but nothing has been done about it | Medium |
| E8 | **Static build cannot use the new source** | `netlify.toml` installs `requirements.txt` (which now includes `playwright`) but never runs `playwright install chromium`; PYTHON_VERSION 3.11 vs 3.12 in the digest workflow | Once Netlify is linked, the site will fall back to Data Thistle (E4) or fail. Untested | Medium |
| E9 | **Wait and see list never populated** | `considering.json` is `[]`; its only commit is `439807b` (28 Sep) | README says "What's On's Populate run keeps it up to date". In 7 weeks nothing has committed to it, so the feature has never fired. Integration unverified | Medium |
| E10 | **TMDB fallback inactive in production** | Run 43414923631 env: `TMDB_API_KEY:` empty (OMDb key now set) | The TMDB → IMDb ID → OMDb route never runs in CI | Low-medium |
| E11 | **Accessibility gaps on the web page** | `webapp_template.py`: search input has no label (line 176); score icons `alt=""` (261, 264) so "–" is read with no source; `--dim #6a6a6a` on `#141414` = 3.41:1, on cards 3.08:1; pink `#E2124D` text on `#141414` = 3.88:1 | Fails WCAG AA for small text and for screen readers | Low-medium |
| E12 | **Special-event titles sent to OMDb uncleaned** | Run 43414923631: no result for "MUBI FEST LIVE: A LONG WINTER + Q&A", "GIANT – The Play" | Event and Q&A wrappers are not stripped, so those films get no scores | Low |
| E13 | **Booking links still use fragile title matching** | HANDOVER item 3; the 13 Nov log still shows "Fetched 303 PH film codes" (`enrich._enrich_ph_links`) | Picturehouse now supplies `ph_url` directly, but the extra what's-on scrape and title match still run | Low |
| E14 | **Sold-out sessions still shown** | README limitation line 335; HANDOVER nice-to-have | The new source could support this, but it isn't done | Low |
| E15 | **Committed test artefact** | `_test_digest.html` (from `362eb7d`, 4 Apr); HANDOVER item 5 | Still tracked | Low |
| E16 | **Netlify build time and cache** | HANDOVER item 4 | Not checked; `.cache/` is not persisted on Netlify | Low (moot until E2) |
| E17 | **Unanswered coordination request** | `.coordination/requests/5b55ff15-….json`, queued 17 Oct (`check:19`) | No event answers it after 29 days, and `report.py requests` could not confirm state today | Low |
| E18 | **Licence and attribution** | No `LICENSE` in a public repo; no TMDB or OMDb attribution in either footer | See D12 | Low |
| E19 | **Actions running on deprecated Node 20** | Run 43414923631 warning for `actions/cache@v4`, `checkout@v4`, `setup-python@v5` | Maintenance pending | Low |
| E20 | **First scheduled run on the new source not yet seen** | Only the manual dispatch on 13 Nov has used it; next scheduled run is Tue 17 Nov | The scheduled path is unobserved | Info |

---

## (A) Mistakes log

64 entries. Evidence is a commit hash, run ID or file. "Caught in review" means a reviewer (Codex, or an audit session) found it before or after merge; the cost column says whether it reached live.

| # | Date | What happened | Evidence | Cost | Root cause | Why not caught | Rule or check that would have stopped it |
|---|---|---|---|---|---|---|---|
| 1 | 2026-03-08 | Initial commit included `.DS_Store` and a generated `digest_preview.html` | `44e5139` "moving"; removed in `4f953df` (26 Sep) | Repo noise for 7 months; 3 later commits only regenerated the preview | No `.gitignore` before the first commit | Nothing checks what gets committed | Write `.gitignore` before the first commit; CI fails on tracked OS or generated files |
| 2 | 2026-03-08 | PR #1 merged 53 s after opening, PR #2 after 6 s, PR #3 after 6 s | PR timestamps | Zero review; later bugs (#4 to #12) went straight in | PRs used as a merge button | No review gate | A PR waits for a review pass or written self-review before merge |
| 3 | 2026-03-08 | PR #2 existed only to update a generated HTML preview | PR #2, `ad67bc3` | A PR and merge for a build output | Preview treated as source | No rule on generated files | Generated previews go in scratch or the PR description, never the repo |
| 4 | 2026-03-08 | Logline trimming rule changed three times: ellipsis at word boundary → never truncate → whole sentences up to 180, else 300 with "…" | `70e7c17`, `10d1418` (26 min later), `4f953df` | Three rounds of rework | Requirement not written down before coding | No spec until `EXPECTATIONS.md` on 31 Mar | Write the display rule with examples in EXPECTATIONS before the first implementation |
| 5 | 2026-03-08 | OMDb plot preference changed from ">200 chars" to "always prefer shorter" within 26 min | `70e7c17` → `10d1418` | Rework | Guessed threshold | No user sign-off on the rule | Ask for the rule, or show two examples, before choosing a magic number |
| 6 | 2026-03-08 | Hotlinked Picturehouse logo returned 404 in the email | `10d1418` "Fix broken Picturehouse logo URL" | A broken image in the preview | Third-party asset URL used without checking it | No link check | Check every external asset URL during the build; prefer an inline or owned copy |
| 7 | 2026-03-08 | Cache hits skipped director and logline metadata | `10d1418` "Extract _apply_metadata so cache hits also get director/logline" | Second and later runs showed less detail than first runs | Cache path and fresh path diverged | Tests didn't cover a cache hit | Test the cached path and the fresh path for the same output |
| 8 | 2026-03-08 | Single Book button broke for films showing at both cinemas | `94a251e` | Wrong or broken booking link in the digest | Layout assumed one cinema per film | No two-cinema fixture | Fixtures must include a film at both cinemas |
| 9 | 2026-03-08 | Mixed 11 to 14 px font sizes shipped in the redesign | `94a251e` "Normalize font sizes" | Rework | No type scale | No visual review before merge | Define a type scale first; screenshot review before merge |
| 10 | 2026-03-09 | Two commits pushed to the PR #3 branch after it merged, so they never reached `main` through a PR | `94a251e`, `7895072` only on `origin/claude/reformat-logline-display-w9uNK` | The work was hand-applied later in `2e0f59c` (how is unknown); an abandoned branch remains | Kept working on a merged branch | No check that the branch was already merged | After merge, start a new branch from `main`; delete merged branches |
| 11 | 2026-03-09 | Cinema deep links to ticketing returned 503 | `7895072` "instead of deep ticketing links that 503" | Broken links in emails | Links not checked | No link check | Check that booking URLs resolve, or only use known-good URL formats |
| 12 | 2026-03-09 | Placeholders for missing scores removed ("no dash placeholders"), later reintroduced as "N/A" and "–" | `7895072` vs README "N/A for unavailable scores" and web `–` | Flip-flop | Rule never written down | No spec | One written rule for missing data, in EXPECTATIONS |
| 13 | 2026-03-31 | "Full audit and setup", 1,033 changed lines in one commit, pushed directly to `main` | `2e0f59c` | Hard to review or revert; it led straight into #14 to #18 | Big-bang change, no PR | No branch protection | Branch protection on `main`; one concern per commit |
| 14 | 2026-03-31 | First real runs of the scheduled digest failed three times | Runs 23785369271, 23790355319, 23816734013 (logs expired) | About 15 hours of elapsed firefighting (07:19 to 22:25) | Workflow not tried by hand before relying on it | No dry run in CI | First run a manual dispatch with dry-run, then one real send to yourself |
| 15 | 2026-03-31 | No timeout or verbose logging until after the failures | `dccf889` | Slower diagnosis | Observability added late | n/a | Every scheduled job ships with a timeout and `-v` logs from day one |
| 16 | 2026-03-31 | Wrong diagnosis: "GitHub Actions runners block outbound STARTTLS on port 587". Fixed twice in 80 min with opposite orderings | `59f3f35`, `067f0a4` | Rework. Later logs (26 Sep, 6 Oct, 10 Nov, 13 Nov) show STARTTLS on the configured port succeeding in CI, so the premise was false | Guess written down as fact | No proof asked for | A diagnosis cites a log line; "blocked" needs an error message, not a hunch |
| 17 | 2026-03-31 to 09-26 | 465-first SMTP logic could send the email twice (a failure after `sendmail`, for example in `quit`, fell through to STARTTLS) | `067f0a4`/`362eb7d`; fixed in `4f953df` "so it never sends twice" | Duplicate emails possible for 6 months (whether any happened is unknown) | Retry around a non-idempotent step | No test for failure after send | Never retry after the message is handed over; test that path |
| 18 | 2026-03-08 to 09-26 | STARTTLS without certificate verification | `4f953df` adds `ssl.create_default_context()` (`emailer.py:56`) | SMTP credentials sent over unverified TLS for about 6 months | Default `starttls()` doesn't verify | No security review | Always pass a TLS context; security checklist per PR |
| 19 | 2026-04-04 | Commit titled "hbhb" mixed CI changes, SMTP changes, a test artefact and a preview | `362eb7d` | `_test_digest.html` still tracked (E15); unreadable history | Commit-all habit | No message or content check | Meaningful message; one concern per commit; no artefacts |
| 20 | 2026-03-31 to 11-13 | Scheduled digest ran with `OMDB_API_KEY` empty | Logs of runs 36237094965, 37533112927, 42910349210 show it empty; set by run 43414923631 | Weeks of digests with no IMDb scores (earlier runs unknown: logs expired) | Secret never added; the code warned but still went green | No preflight for required secrets | Preflight step fails, or flags the subject, when a required secret is empty |
| 21 | 2026-03-31 to 11-13 | The OMDb cache step never saved anything | "Path Validation Error … no cache is being saved" (run 36237094965) until `Cache saved with key: omdb-cache-40` on 13 Nov | No caching benefit; repeat lookups each week | Cache depended on the key from #20 | Warning buried in logs | Treat Actions warnings as failures for scheduled jobs |
| 22 | by 2026-09-26 to 11-10 | **Digest missed about 90% of each cinema's programme** (Data Thistle listed 3 to 18 films against 64 to 69 on Picturehouse) | Runs 36237094965 (5 and 6 films), 37533112927 (3 and 5), 42910349210 (13 and 18); HANDOVER table | Weeks of misleading digests; you found it by checking the Ritzy website yourself | Third-party aggregator chosen without checking it against the official site | Only check was "fewer than 3 films"; green runs looked healthy | Before choosing a source, compare it with the official site for a week; alarm on counts below a realistic floor |
| 23 | 2026-03-31 | Safety floor set at 3 films per cinema | `config.py` `MIN_FILMS_PER_CINEMA = 3` | Let #22 through; still unchanged (E5) | Threshold chosen to avoid false alarms, not to catch real failure | n/a | Set floors from measured normal values, for example 25% of a typical week |
| 24 | 2026-03-31 | Unit tests hard-coded 2026 dates for year-less date headers; they became time bombs | Run 36231163248: `assert datetime.date(2027, 3, 11) == datetime.date(2026, 3, 11)` | Red CI, first seen 6 months later | Test depended on today's date | Tests only ran on push; there were no pushes from April to September | Freeze or inject "today" in tests; add a weekly scheduled test run |
| 25 | 2026-09-26 | README commit pushed to `main` and broke CI (the date bomb went off) | `7917bd3`, run 36231163248 failure | Red `main` for 42 min | Pushed without running tests locally | n/a | Run the suite before every push, even for docs |
| 26 | 2026-03-31 to 09-26 | Score cache stored unvalidated results, kept "not found" for ever and cached errors | `4f953df` | Wrong or missing scores could persist indefinitely | Cache written before validation | No cache tests | Validate, then cache; expiry on negatives; never cache errors |
| 27 | 2026-03-31 to 09-26 | Identity check stripped leading articles, so "The Drama" matched "Drama"; years not compared, so remakes matched | `4f953df`, EXPECTATIONS "Identity check" | Wrong film's scores shown in live digests | Similarity on stripped titles only | No near-duplicate fixtures | Test fixtures of near-identical titles and remakes |
| 28 | 2026-03-31 to 09-26 | A broken listings page produced "No qualifying screenings found", which looks like a quiet week | `4f953df` | A silent failure, possibly live | Empty treated as valid | No "suspect" state | Distinguish empty from broken; flag the subject |
| 29 | 2026-03-31 to 09-26 | Duplicate showtimes; same-title films merged across years | `4f953df` | Duplicates and merged remakes in the digest | Merge key was title only | n/a | Merge key title plus year; de-duplicate on (cinema, start) |
| 30 | 2026-03-31 to 09-26 | Films with no year lost their duration (parser bug) | `4f953df` | Missing metadata | Parser coupled fields | No fixture for a missing year | Fixtures with each optional field missing |
| 31 | 2026-03-31 to 09-26 | An empty `SMTP_PORT` secret crashed `int('')` | `4f953df`, `config.py` `_env()` | Run failure when a secret is defined but empty | GitHub passes undefined secrets as "" | n/a | Treat empty as unset for every env var |
| 32 | 2026-03-31 to 09-26 | README scheduling instructions were wrong: launchd under `~/Library/LaunchDaemons` never runs; cron redirect to `/var/log` makes cron skip the job | `4f953df` | Anyone following the README got a schedule that silently never ran | Docs written from memory | Docs never tried | Run every documented command once before publishing it |
| 33 | 2026-03-31 to 09-26 | `EXPECTATIONS.md` was out of date on ordering and star thresholds | `4f953df` "EXPECTATIONS.md updated" | The spec misled reviewers | Spec not updated with code | No doc check in the PR template | A behaviour change updates EXPECTATIONS in the same commit |
| 34 | 2026-03-31 to 09-26 | Weak tests that asserted little | `4f953df` "weak tests made meaningful" | False confidence: "96 unit tests all passing" (`2e0f59c`) | Tests written to pass | No review of tests | Each test names the behaviour it protects; review tests like code |
| 35 | 2026-09-26 | Second mega-commit to `main`: 24 files, +1,928/−741 | `4f953df` | Unreviewable; mixes 15 fixes | Audit fixes batched | No PR | One PR per audit theme |
| 36 | 2026-09-26 | You had to ask why IMDb scores were missing (silent dashes) and why blurb words ran together | `ec6993e` | A correction from you; trust | Missing data had no explanation | No check that every blank has a reason | Every N/A has a reason in the digest |
| 37 | 2026-09-28 | Wait and see list first read from a secret or env var, then switched to `considering.json` 16 min later | `4d7996f` → `439807b` (workflow line added, then removed) | Rework | Integration contract with What's On not agreed first | n/a | Agree the cross-repo contract (file, owner, writer) before coding |
| 38 | 2026-09-28 | Wait and see feature shipped but never fed | `considering.json` `[]`, no commits since | Feature inert for 7 weeks (E9) | Depends on another repo's job that was never confirmed | Done judged by tests, not live data | Done includes one real entry flowing end to end |
| 39 | 2026-09-28 | Thresholds disagree: Wait and see bar 75, star highlight ≥ 76 | README "75 unless the entry says otherwise"; EXPECTATIONS "MC >= 76" | A film at 75 "clears your bar" but gets no star | Two features, two numbers | No single constants table | One settings table for every user-facing threshold |
| 40 | 2026-09-26 to 28 | Concurrency (4 lookups) added on 26 Sep triggered OMDb "Request limit reached" | `5e01930` two days after `4f953df` | Rework; missing scores in runs | Rate limits not considered when adding parallelism | Tests mock OMDb | Check provider rate limits before adding concurrency |
| 41 | 2026-07-06 to 10-07 | Web app branch sat unpushed for 3 months (author date 6 Jul, committer date 7 Oct) | `15384c0` ad/cd dates | Needed `6aebeb0` "Adapt web app to ScrapeResult pipeline from main" | Long-lived local branch | No push or draft PR | Push a draft PR the same day; rebase weekly or abandon |
| 42 | 2026-10-07 | Site deployed by CLI upload from pre-review code before the PR was reviewed | Netlify deploy 06:25 UTC; PR opened 06:29 | Live site carries every bug the review later fixed (E1) | Deploy as a demo step | No deploy-from-main rule | Deploy only from `main` through CI; no manual uploads |
| 43 | 2026-10-07 | Self-review missed about 15 issues that Codex found in 42 min | 10 "Address Codex review" commits, 06:33 to 07:11 | 42 min of fix-up; trust in "Testing" section of PR #5 | Author reviewed own work | n/a | Independent review before a PR is called ready |
| 44 | 2026-10-07 | API keys would have appeared in build logs (OMDb/TMDB `apikey=` in error URLs; Netlify keeps logs) | `00ca33e`, `f4f0457` | Near leak (caught) | Keys sent as query parameters, logs unfiltered | Redaction only in `main()` | Redacting log filter installed at import; secret scan of logs |
| 45 | 2026-10-07 | Web and email picked Book links differently; showtime links used an old URL format | `00ca33e` | Wrong links on the web | Duplicated logic | n/a | One function for each rule, shared by every output |
| 46 | 2026-10-07 | A failed refresh looked like success | `00ca33e` | Stale data shown as current | No stale state in the UI | n/a | Every cached view shows its age and any failure |
| 47 | 2026-10-07 | Static snapshot went stale silently and still showed a Refresh button that couldn't refresh | `f4f0457` | Dead control; stale listings (live in E1) | Live and static modes not distinguished | n/a | List each control and say whether it works in each mode |
| 48 | 2026-10-07 | A failed scrape replaced good cached listings with an empty result; no refresh rate limit | `0570608` | Empty site for 30 min; quota drain risk | Cache replaced on every result | n/a | Never replace good data with worse data; rate-limit expensive actions |
| 49 | 2026-10-07 | Cache timing used wall-clock London times, wrong across DST | `f8a2671` | Refresh blocked an hour or forced re-scrapes twice a year | Time maths on local time | No DST test | Use monotonic or UTC for durations; DST test case |
| 50 | 2026-10-07 | README documented a gunicorn timeout (120 s) shorter than the pipeline budget (480 s) | `517946d` | Worker killed mid-refresh, cache never fills | Numbers in docs not tied to config | n/a | Docs quote config constants, checked by a test |
| 51 | 2026-10-07 | Partial failure removed a cinema; an empty result was cached for the full TTL | `40559b9` | One cinema vanishing for 30 min | Partial results treated as complete | n/a | Compare against configured cinemas, not the last result |
| 52 | 2026-10-07 | A missing cinema didn't count as failure; the page didn't drop showtimes as they started | `729517d` | Stale or partial page | Same as #51 | n/a | Same as #51; re-render on a timer |
| 53 | 2026-10-07 | An empty static build would have deployed an error page | `8ec9b5e` | Near miss (caught) | Build success ≠ content success | n/a | Build fails on zero films |
| 54 | 2026-10-07 | Web hid the "scores incomplete" state the email showed | `731d974` | Missing scores looked like no scores | Two pipelines diverged | n/a | One shared notes builder (done in `731d974`) |
| 55 | 2026-10-07 | Book button opened sessions that had already started | `a1ab309` | Wrong booking link; still on the frozen live site (E1) | Links computed before filtering past showtimes | n/a | Recompute derived links after every filter |
| 56 | 2026-10-08 to 11-15 | Rebuild workflow green 39 times while doing nothing | Runs 37775623464 … 43716556227 | A false sense of a live, updating site (E2) | "No-op until set" design exits 0 | Nobody reads warnings on green runs | A missing required secret fails the run (red), not a warning |
| 57 | 2026-10-08 to 10-17 | Coordination tooling churn on the product repo's `main`: three commits in 4 s, two commits with the same message 3 min apart, a guard fix 12 min later, a destination change a week later | `66065bf`, `9470c5c`, `ab8b324`, `76f1097`, `7ce39a0`, `9f25acf`, `f1c0265` | 10 non-product commits and 9 test runs | Tooling iterated in place across many repos | n/a | Develop tooling in its own repo; roll out once stable |
| 58 | 2026-10-08 onward | `CLAUDE.md` and `AGENTS.md` are identical and hold only coordination rules; the same block appears a third time in `.coordination/README.md` | Files | No project-specific guidance (build, test, sources, deploy) for agents; drift risk | Standing files generated, not written for this project | n/a | One source file with project facts; the other links to it |
| 59 | 2026-11-13 | "Working" event said the work was on branch `picturehouse-direct` awaiting your mock-up approval; commits then landed directly on `main` with no PR | Event `f4a096ac…` vs `105f800` on `main`, no remote branch | Whether you approved is **unknown** from the repo; no reviewable PR | Direct push habit | No branch protection | Changes reach `main` only through a PR that links the approval |
| 60 | 2026-11-13 | Hand-written fixture assumed "Dog-Friendly - Ghosts: The Possession…"; the real page drops "The", so the live run split the film | `0513093` (12 min after `105f800`), fixture diff | A fix-up commit; a split entry in one real email | Fixture invented, not captured | Tests passed on an idealised page | Fixtures are saved real pages (trimmed), refreshed when the site changes |
| 61 | 2026-11-13 | Source switch shipped without updating README, EXPECTATIONS, HANDOVER or footers | E6 | Wrong provenance shown to readers | Docs not part of done | DoD in HANDOVER not checked | PR checklist: docs, footers, threshold, flags |
| 62 | 2026-11-13 | Fallback to the old source flagged only in the body | E4 | The original failure can recur unflagged | Fallback treated as a note | n/a | Any fallback to a known-incomplete source flags the subject |
| 63 | 2026-11-13 | "Done" recorded on one manual run without the required verification report | E3 | Dashboard shows complete; criterion unproven | Done equated with "ran and sent" | Collector rules not followed | Done needs the written report and the exact criterion checked |
| 64 | 2026-03 to 11 | Personal Gmail address in commit author metadata in a public repo | 24 commits by `RobertsMacros`/`Robert Stevens` with a personal Gmail address | Personal address public and harvestable | Local git config used a personal address | n/a | Use the GitHub noreply address for public repos |

The history supports 64 entries. Most are evidenced directly; 17, 20 and 59 have parts marked unknown.

### Themes that repeated

1. **Green but wrong.** Successful runs hid wrong output: 90% of films missing (#22), no IMDb scores (#20), a cache that never saved (#21), a rebuild that never ran (#56), a frozen site (#42). Exit codes and test counts stood in for checking the output.
2. **Thresholds and rules guessed, then reworked.** Logline length (#4), plot preference (#5), placeholders (#12), the 3-film floor (#23), the 75/76 bars (#39), booking links (#8, #11, #45, #55).
3. **Big pushes straight to `main` without review**, or rubber-stamp PRs (#2, #13, #35, #59).
4. **Diagnosis by assumption** (#16) and fixtures by assumption (#60, #24).
5. **Docs drift.** README, EXPECTATIONS and HANDOVER fell behind the code (#32, #33, #50, #61).
6. **Deploy and secrets outside the repo never checked.** Netlify link, build hook, OMDb and TMDB keys (#20, #42, #56, E10).
7. **Silent degradation.** Fallbacks and missing data not visible to the reader (#28, #36, #46, #62).

---

## (B) Instructions or corrections given more than once

Your chat instructions aren't in the repo, so these are inferred from commits that restate or reverse a requirement.

| Topic | Times | Evidence | Lesson |
|---|---|---|---|
| Booking links must go to the right place | 6+ | `94a251e`, `7895072`, `2e0f59c`, `4f953df`, `00ca33e`, `a1ab309` | Write one booking-link rule with examples and test it against live URLs |
| Don't fail silently; explain problems in the digest | 5 | `4f953df` (always send, flag subject), `ec6993e` (explain IMDb gaps), `00ca33e` (refresh errors), `731d974` (scores incomplete), `105f800` (fallback note) | Make "every gap has a stated reason" a standing rule |
| Logline length and cut style | 3 | `70e7c17`, `10d1418`, `4f953df` | Settle display rules with examples up front |
| Missing-score display | 3 | `70e7c17`, `7895072`, `4f953df` | Same |
| Keep keys out of logs | 3 | `4f953df`, `00ca33e`, `f4f0457` | Redaction at import time plus a log secret scan |
| Don't commit generated files | 5 `.gitignore` edits | `63c356f`, `4f953df`, `798acfa`, `c211d84` (and `_test_digest.html` still tracked) | `.gitignore` template on day one |
| Listings must match what the cinema website shows | 2 | You checked the Ritzy site (HANDOVER), then the 13 Nov "every film shown" scope | Make "compare with the official page" a release check |
| README with the Roberts Macros tagline and install and usage | 1 commit (`7917bd3`), applied from your standing preferences | n/a | Already a standing preference; keep it in the template |
| Show a before-and-after mock-up before pushing | stated in the 13 Nov event | `f4a096ac…` | Whether it was honoured is unknown (#59) |

---

## (C) Near misses

| # | Near miss | Evidence | What stopped it |
|---|---|---|---|
| 1 | OMDb and TMDB keys written to Netlify build logs and public CI logs via request-error URLs | `00ca33e`, `f4f0457`, `4f953df` | Redaction filter. In CI the OMDb key was empty until November, so no CI leak was possible before then |
| 2 | Duplicate emails from the SMTP fallback | `4f953df` | Rewritten so fallback only happens before handover |
| 3 | Unverified TLS for SMTP login | `emailer.py:56` from `4f953df` | Added a default SSL context |
| 4 | Empty static build replacing the site with an error page | `8ec9b5e` | Build exits 1 on zero films |
| 5 | gunicorn killing workers mid-refresh | `517946d` | Timeout raised to 600 s in docs |
| 6 | `?refresh=1` bursts draining OMDb/TMDB quota | `0570608` | 60 s cooldown and lock coalescing |
| 7 | Scheduled workflow disabled after 60 days without activity: no commits from 4 Apr to 26 Sep (175 days) and no keepalive | Runs continued weekly; keepalive added in `4f953df` | **Unknown** why it wasn't disabled (possibly the manual dispatch on 2 Sep) |
| 8 | Audit tool outputs `fix_manifest.json` and `insight_dump.md` nearly committed | `.gitignore` | Ignored in `4f953df` |
| 9 | Personal Wait and see list published in a public repo | README "titles and years only, since this repository is public" | Deliberate minimisation |
| 10 | Cookie consent on the Picturehouse page | `ph_scraper._dismiss_cookie_banner` chooses "Reject All" | Good default |
| 11 | Cache poisoning with wrong-film scores | `4f953df` | Validate-then-cache, re-check on hit (this did reach live before the fix: #26, #27) |

---

## (D) Answers

### D1. Structure and standing files

| File | Purpose | State |
|---|---|---|
| `README.md` | Setup, credentials table, usage, web app, Netlify, six scheduling options, output format, architecture, limitations | Detailed, but out of date on source (E6); 4 em dashes |
| `EXPECTATIONS.md` | Behaviour spec with boundary values (18:00 in, 17:59 out; day 6 in, day 7 out) | The best file here; out of date on source |
| `HANDOVER.md` | Codex handover dated 6 to 7 Oct, with a measured evidence table and definition of done | Good format; now stale, its DoD mostly unmet |
| `CLAUDE.md`, `AGENTS.md` | Coordination reporting only, identical | No project facts (#58) |
| `.coordination/` | Events, one queued request, reporter script | Done event lacks a report (E3) |
| Workflows | `cinema_digest.yml` (weekly), `tests.yml` (push and PR, Python 3.11 to 3.13), `netlify_rebuild.yml` (daily, no-op) | See E2, E7 |
| Missing | `LICENSE`, decisions log, changelog, saved audit reports, PR template, branch protection | Audit results exist only as commit messages |

### D2. Decided before building, and what should have been

- **Decided (evidenced):** cinemas (Clapham, Ritzy), evening and weekend windows, Metacritic-first ordering, email as the output, Data Thistle as the source. `EXPECTATIONS.md` arrived on 31 Mar, three weeks after the first code.
- **Not decided, and it cost rework:** source completeness against the official site (#22); delivery time and tolerance for lateness (E7); hosting and deploy path (#42, #56); which secrets CI needs (#20); display rules for loglines, missing scores and links (#4, #12, B); one table of thresholds (#39); terms of use for every scraped site (D12); the cross-repo contract with What's On (#37, #38).

### D3. Good habits to copy

1. **A behaviour spec with boundary values** (`EXPECTATIONS.md`).
2. **Always send, flag problems in the subject** ("[CHECK: listings page may have changed]").
3. **Offline unit tests with network blocked** (`tests/conftest.py`), live tests opt-in with `-m integration`.
4. **A whole-run time budget** (8 min) so the digest always goes out, with unfinished lookups marked.
5. **Keepalive step** for scheduled workflows in public repos.
6. **A handover with measured evidence** (Data Thistle 5/3 films vs Picturehouse 69/64) and an explicit definition of done.
7. **Honest PR bodies:** PR #5 has a "Known issue, not fixed here" section.
8. **Plain-English commit messages that say why** (from September onward, for example `ec6993e`, `0513093`).
9. **Pushing back with evidence:** `ec6993e` notes the garbled Misanthrope blurb was Data Thistle's own copy.
10. **Data minimisation** for the public `considering.json`.
11. **Fallback design:** Picturehouse primary, Data Thistle fills gaps; the static build refuses to deploy an empty site.

### D4. Workflow

| Aspect | Evidence |
|---|---|
| Sessions | Six Claude sessions, identifiable from `Claude-Session` trailers or commit style: 8 to 9 Mar (`016VGct…`), 31 Mar local Claude Code (no trailer), 26 to 28 Sep (`01NWHC…`), 28 Sep (`01Ez8fk…`), 6 Jul and 6 to 7 Oct (`014PoRv…`), 13 Nov (`011DzsJ…`). One Codex review (7 Oct) |
| Branches | `claude/*` branches for 3 of 6 sessions; 4 remote branches remain after merge, one with unmerged commits (#10) |
| Direct pushes to `main` | 23 of the 45 non-merge commits on `main`, including both mega-commits and the 13 Nov source switch |
| PRs | 5, all merged; 3 merged within a minute; PR #5 merged 2.5 h after opening, following review fixes |
| Mock-ups | `digest_preview.html` (later untracked), `_test_digest.html` (still tracked), and a before-and-after mock-up named in the 13 Nov event (approval unknown) |
| Gap between sessions | 4 Apr to 26 Sep with no commits while the digest ran weekly with the 90% gap |

### D5. Tests and verification gates

- **Today:** 221 unit tests pass in 1.77 s; CI runs them on push and PR across Python 3.11, 3.12 and 3.13. No scheduled test run. Integration tests are opt-in and never run in CI.
- **What they missed:** source completeness (#22); date bombs (#24); secrets present in CI (#20); deploy state (#42, #56); delivery time (E7); real-page fixtures (#60); cache-hit path (#7); near-identical titles (#27); accessibility (E11); the static build with Chromium (E8).
- **Gates that worked:** the Codex review on PR #5 (about 15 issues in 42 min); the September audit; `build_static.py` failing on zero films.
- **Missing gate:** an output check, such as "Ritzy shows at least N films and at least M showtimes on 3 or more days", run against the real email or JSON after each scheduled run.

### D6. Design and UI problems

Mixed 11 to 14 px fonts (`94a251e`); hotlinked logo 404 (`10d1418`); single Book button breaking for two cinemas (`94a251e`); a Refresh button on the static site that can't refresh (`f4f0457`); a page heading wrapped in decorative em dashes; Picturehouse logo and brand colours on a site that is not Picturehouse's (see D12); star emoji as the only highlight marker; no posters, even though the new source has them.

### D7. UX problems

The digest arrives 3 to 5 hours late, after Tuesday's evening screenings start (E7). For months it listed a tenth of the programme (#22). IMDb scores were blank with no reason (#36). Wrong-film scores appeared before September (#27). Book links have been wrong in several ways (B). Special screenings split from the main film (#60). The 75 vs 76 threshold mismatch (#39). The live website is stale and shows old showtimes (E1). Evening and weekend windows are fixed in code with no user setting.

### D8. AI-sounding copy and deslop rules that mattered

- **AI-sounding:** PR #1 body ("redesigns the film digest formatting to improve readability and information density", "Key Changes", "All changes maintain backward compatibility"); PR #3 auto-title "Claude/reformat logline display w9u nk"; commit "hbhb"; ten commits all prefixed "Address Codex review:".
- **Improved:** from September, messages describe what the reader sees ("Fold special screenings into the main film even when the title drops 'The'").
- **Rules that mattered:** say why data is missing in plain words ("IMDb scores unavailable this week (no OMDb API key is set)"); never end a shortened logline with a fake full stop; flag problems in the subject, not only the body; no em dashes (still 4 in the README, 2 in EXPECTATIONS, 4 in `formatter.py`, 3 in `webapp_template.py`).

### D9. Accessibility

Never audited. Found: search box with only a placeholder, no label; score icons with empty `alt`, so "–" or a number is read with no source name; contrast below 4.5:1 for small text (`--dim` 3.41:1 and 3.08:1, pink text 3.88:1); cinema filter pills have no `aria-pressed`; meaning carried by an emoji star; `lang="en"` rather than `en-GB`. The email uses `role="presentation"` tables (good) and decorative icons with `alt=""`, which is right only if the score label is in text.

### D10. Data sources, scraping, fallbacks and provenance

| Source | How | Used for | Fallback | Provenance shown |
|---|---|---|---|---|
| Picturehouse cinema pages | Playwright headless Chromium, browser user agent, clicks "Show all dates" | Primary listings since 13 Nov | Data Thistle, with a body note | No (footers still credit Data Thistle) |
| Data Thistle | `requests` and HTML parsing | Primary until 13 Nov; now year, description and extras | None | Yes, but now wrong |
| Picturehouse what's-on page | `requests`, browser user agent | Film codes for links | Cinema page | No |
| OMDb API | Key in query string | MC, IMDb, RT scores | TMDB (inactive in CI) | Score names only |
| TMDB API | Key | IMDb ID lookup, vote average | None | **None** |
| IMDb suggestion and GraphQL endpoints | Scraped with a spoofed Chrome user agent | IMDb ID, rating, plot | n/a | Score name only |
| Metacritic, Rotten Tomatoes | Scraped | Fill missing scores | n/a | Score name only |
| Google favicon API, Picturehouse S3 logo | Hotlinked images | Icons and logo | None (the logo broke once) | n/a |
| `considering.json` | Committed by What's On (never happened) | Wait and see flag | `CONSIDERING` env var | n/a |

Key lesson: a third-party aggregator was the only source for months without being compared with the official site.

### D11. Security and privacy

- **Keys:** OMDb and TMDB keys in GitHub secrets; keys go in query strings, so redaction is needed (#44, `main.setup_logging` RedactingFilter). Logs from a public repo's Actions runs are public.
- **Fixed late:** unverified SMTP TLS for about 6 months (#18).
- **Open:** personal Gmail address in public commit metadata (#64); the `actions: write` token on the digest job, used for the keepalive (scoped, acceptable).
- **Good:** `.env` ignored; `.env.example` has no values; empty secrets treated as unset; the public list holds titles and years only; Picturehouse cookies rejected.
- No secrets found in the tracked files or history I read. A full secret scan of every blob was **not** run.

### D12. Legal

- **Scraping:** IMDb's conditions of use forbid scraping without permission; Metacritic, Rotten Tomatoes and Picturehouse are scraped with browser user agents. Whether anyone reviewed these sites' terms is **unknown**. Data Thistle terms **unknown**.
- **API terms:** OMDb's free tier is for non-commercial use (**unverified** for current terms); TMDB requires visible attribution and a "not endorsed" notice, which is absent.
- **Branding:** the public website and the email use Picturehouse's logo and brand colours. That could be read as an official Picturehouse page.
- **Licence:** the repo is public with no `LICENSE`, so reuse rights are unclear.
- **Data protection:** the only personal data is your email address (secrets, commit metadata) and your Wait and see titles (minimised). No other users.

### D13. Costs and quotas

| Item | Cost or quota | Evidence |
|---|---|---|
| GitHub Actions | Free (public repo); digest runs 25 to 90 s, plus Chromium install since 13 Nov | Run timings |
| Netlify | `nf_team_dev` plan; one deploy in total | Netlify project |
| OMDb | 1,000 requests a day, free; rate-limited bursts (`5e01930`) | README, code |
| TMDB | Free; key unset in CI | Run 43414923631 |
| Money spent | **Unknown**; nothing in the repo suggests paid services |
| Biggest cost | Your time, and weeks of incomplete digests |

### D14. Release, and what done means

- **Release** has been "push to `main`" for the digest (the next scheduled run picks it up) and "CLI upload" for the website (once).
- **"Done" was claimed on:** test counts (`2e0f59c` "all passing"), one manual run (`b667efe`), and a deploy that finished (PR #5). None of them checked the output against the real cinema pages, or checked the deployed site after merge.
- **What done should mean here:** the scheduled run, not a manual one, sends a digest whose film and showtime counts match the official pages within a stated tolerance; the live site's deploy commit equals `main`; docs, footers and EXPECTATIONS match; required secrets are present; the coordination report covers each criterion.

### D15. Five rules for day one

1. **Prove the data against the official source before building on it, then keep checking.** Compare listings counts with the cinema's own site for a week; alarm on realistic floors, not "fewer than 3".
2. **Green means the output is right, not that the job exited 0.** Every scheduled job checks its own output and required secrets, and fails red, never "warning and skip".
3. **Nothing reaches `main` or production except through a reviewed PR and CI.** Branch protection on, no manual deploys, deploy commit must equal `main`.
4. **Write the rules before the code.** EXPECTATIONS (display rules, thresholds, fallbacks, delivery time) with examples, plus a decisions log, updated in the same PR as any behaviour change.
5. **Done needs evidence of the exact criterion in the real environment.** A live check (the real email, the live page) and updated docs, attached to the PR or coordination report. Tests passing and "it ran" are not done.
