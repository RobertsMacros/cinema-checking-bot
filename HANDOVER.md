# Handover: review + fix listings collection

**Repo:** `RobertsMacros/cinema-checking-bot`, branch `claude/newsletter-cinema-webapp-0vlt2a` (not yet merged to `main`)
**Live site:** https://clapham-ritzy-cinema.netlify.app (Netlify project `clapham-ritzy-cinema`)

## What this project is

A bot that collects film listings for two London cinemas (Clapham Picturehouse and the Ritzy, Brixton), keeps evening/weekend showtimes for the next 7 days, adds review scores (Metacritic, IMDb, Rotten Tomatoes), and outputs them in two ways:

1. **Email digest.** `python -m cinema_digest.main` runs weekly through `.github/workflows/cinema_digest.yml`.
2. **Interactive web app** (new on this branch). The page can be filtered by cinema, searched, and set to show highlighted films only.
   - Local: `python -m cinema_digest.webapp` starts a Flask app with an in-memory cache, serving `/` and `/api/films`.
   - Hosted: `build_static.py` runs the pipeline at build time and writes `public/films.json` and `public/index.html`. `netlify.toml` configures the build.

Pipeline: `scraper.scrape_all()` → `filters.filter_screenings()` → `enrich.enrich_films()` → formatter (email) or `webapp.serialize_film()` (web).

## 1. Main bug: the listings source is missing ~90% of the programme

The scraper uses **Data Thistle** (`config.CINEMAS`). Data Thistle's pages for these cinemas list only a few films, so the parsing is not the problem. Checked on 6–7 Oct 2026:

| Source | Ritzy | Clapham |
|---|---|---|
| Data Thistle page (`/listing/` links in the HTML) | 5 films | 3 films |
| Picturehouse's own endpoint | **69 films, 334 showtimes** | **64 films, 254 showtimes** |

The page has no pagination and no JavaScript loading. The data is simply not there. The user checked the Ritzy website: about 4 films today and 10–15 tomorrow. The Picturehouse endpoint matched this: 4 showtimes on 6 Oct, then about 22 a day. Data Thistle returned 26 showtimes for the whole week across both cinemas.

The safety check `MIN_FILMS_PER_CINEMA = 3` in `config.py` is too low to catch this.

### Recommended fix: use Picturehouse's own endpoint as the primary source

This worked from Python `requests` with a browser User-Agent:

```python
s = requests.Session()
UA = {"User-Agent": "Mozilla/5.0 ... Chrome/120 Safari/537.36", "X-Requested-With": "XMLHttpRequest"}
page = s.get("https://www.picturehouses.com/cinema/the-ritzy", headers=UA)   # sets session cookie
token = re.search(r'csrf-token" content="([^"]+)"', page.text).group(1)        # or name="_token" value="..."
data = s.post(
    "https://www.picturehouses.com/api/scheduled-movies-ajax",
    data={"cinema_id": "004", "_token": token},
    headers={**UA, "X-CSRF-TOKEN": token},
).json()
# data["movies"] -> list of films
```

- Cinema IDs are already in `config.CINEMA_CODES`: Ritzy `004`, Clapham `020`. Page slugs come from `config.CINEMA_URLS`.
- The response has content-type `text/html` but the body is JSON. Use `.json()`.
- Fields on each film: `ScheduledFilmId` (the `HO000…` code, which can build the `ph_url` directly), `Title`, `show_times`, `image_url` (poster), `available_cinemas`.
- Fields on each entry in `show_times`: `Showtime` (ISO local time, e.g. `2026-10-25T12:30:00`, no timezone, so treat it as Europe/London), `SessionId`, `ScreenName`, `SeatsAvailable`, `SoldoutStatus`, `SessionAttributesNames` (e.g. `["2D","reDiscover"]`; useful for `screening_type`), `CinemaId`.
- The response includes dates well beyond 7 days, but `filter_screenings` already handles that.
- `/api/get-movies-ajax` returned a 500. Don't use it.

Suggested implementation:
- Add a `picturehouse` source module that returns the same `list[Film]` / `Screening` models, so filtering, enrichment, the email and the web app keep working unchanged.
- Keep Data Thistle as a fallback only if that's cheap to do.
- Build per-session booking URLs if the site has a usable pattern. Otherwise use `ph_url`.
- Raise `MIN_FILMS_PER_CINEMA` to around 15–20.
- Add fixture-based tests using a saved JSON response. Don't call the network in tests.
- New features this source allows (nice to have): drop sold-out sessions (`SoldoutStatus`) and show posters (`image_url`). The README lists sold-out detection as a limitation that Data Thistle couldn't support.

## 2. Other issues to review

1. **The hosted site has no refresh schedule.** Its data is a snapshot from the last Netlify build, so the "Refresh" button only reloads that snapshot. A scheduled rebuild is needed, at least daily. Options:
   - a GitHub Actions cron that triggers a Netlify build hook
   - a Netlify Scheduled Function that POSTs to a build hook
2. **Netlify is not linked to GitHub.** The first deploy was uploaded through the Netlify CLI, so pushing to the repo does not redeploy. Link the repo in the Netlify UI (Project configuration → Build & deploy → Link repository), or deploy from CI.
3. **Two tests fail before any of these changes.** `tests/test_scraper.py::TestParseDateHeader::test_normal_date` and `test_single_digit_day` hard-code March 2026. `_parse_date_header` moves dates more than 60 days in the past into the next year, so these tests depend on today's date. Pass `today` into the function so the tests can fix it. This becomes irrelevant if Data Thistle is dropped.
4. **The documentation contradicts the code.** `EXPECTATIONS.md` says films are sorted alphabetically and starred at MC ≥ 70 / IMDb ≥ 7.0 / RT ≥ 80%. The code sorts by Metacritic, descending, and uses MC ≥ 76 or IMDb ≥ 7.7 (`formatter.is_highlighted`). The README says the GitHub Action runs daily at 06:00 UTC, but the workflow cron is weekly: Tuesday 17:00 UTC.
5. **Booking links** come from Data Thistle `booking_url`s plus `ph_url` matched by normalised title against the Picturehouse what's-on page (`enrich._enrich_ph_links`). That title matching is fragile, and the new source makes it unnecessary.
6. **Smaller items:**
   - `formatter._format_booking_link_plain` contains a meaningless `hasattr(film, 'ph_url')` check.
   - `.DS_Store` and `_test_digest.html` are committed.
   - The time-window rules in `filters.py` and the `CACHE_TTL_SECONDS` default (30 min) are worth checking against what the user wants.

## Definition of done

- Both cinemas return realistic counts (dozens of films, about 10–25 showtimes a day each) in both the email and the web app.
- Tests pass with no network access (`pytest tests/`), including the two date tests.
- The hosted site rebuilds automatically at least daily, and pushes to the repo deploy.
- Docs (`README.md`, `EXPECTATIONS.md`) match the code.

## How to run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -q
python -m cinema_digest.webapp        # http://127.0.0.1:5000
python build_static.py                # writes public/ (what Netlify serves)
python -m cinema_digest.main --dry-run
```

Optional env vars, which improve score lookups: `OMDB_API_KEY` and `TMDB_API_KEY` (see `.env.example`). They are not set on Netlify yet.
