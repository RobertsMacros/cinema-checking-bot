# Cinema Digest

**Roberts Macros: no macro too micro.**

Automatically fetches upcoming film listings from Clapham Picturehouse and Ritzy Picturehouse (Brixton), enriches them with review scores, and emails a formatted digest.

## What it does

1. Scrapes film listings from [Data Thistle](https://film.datathistle.com/) for both cinemas
2. Filters showtimes to evenings (weekdays 18:00-21:30, weekends 11:00-21:30)
3. Enriches each film with Metacritic, IMDb, and Rotten Tomatoes scores via [OMDb API](https://www.omdbapi.com/)
4. Formats a digest ordered by Metacritic score (highest first; unscored films last, alphabetically)
5. Emails the result (or prints it in dry-run mode). A digest is always sent: if the listings look broken, it says so at the top and the subject line is flagged

## Setup

```bash
cd cinema-checking-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
```

The scheduling examples below run `.venv/bin/python`, so the scheduled job uses the interpreter that has the dependencies installed.

### Required credentials

| Variable | Description |
|----------|-------------|
| `OMDB_API_KEY` | Free API key from [omdbapi.com](https://www.omdbapi.com/apikey.aspx) (1000 requests/day) |
| `TMDB_API_KEY` | Free API key from [themoviedb.org](https://www.themoviedb.org/settings/api) (fallback for score lookups) |
| `SMTP_HOST` | SMTP server (default: `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (default: `587`). `465` uses implicit TLS; any other port uses STARTTLS. If the configured port fails before the message is sent, the other method is tried once (465 or 587). |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password or app-specific password |
| `EMAIL_FROM` | Sender email address |
| `EMAIL_TO` | Recipient email address(es), comma-separated |

For Gmail: enable 2FA, then create an [App Password](https://myaccount.google.com/apppasswords).

## Films you are considering

`considering.json` at the repository root lists films parked on What's On's Wait and see list (titles and years only, since this repository is public). What's On's Populate run keeps it up to date. Matching films are listed first in the digest with a pink flag saying whether their Metacritic score has cleared your bar (75 unless the entry says otherwise). Set `CONSIDERING` in the environment to the same JSON to try a list locally.

## Usage

### Dry run (prints to stdout, no email sent)

```bash
python -m cinema_digest.main --dry-run
```

### Send email

```bash
python -m cinema_digest.main
```

### Verbose logging

```bash
python -m cinema_digest.main --dry-run -v
```

## Interactive web app

As well as the scheduled email, the same listings are available as a live,
interactive website you can open whenever you want and filter by cinema.

```bash
pip install -r requirements.txt
python -m cinema_digest.webapp
```

Then open <http://127.0.0.1:5000>. The page lets you:

- **Filter by cinema** (All / Clapham / Ritzy) — a film's showtimes and booking
  buttons narrow to just the selected cinema.
- **Search** by title, director, or logline.
- Toggle **Highlights only** (Metacritic ≥ 76 or IMDb ≥ 7.7).
- **Refresh** to force a fresh scrape.

It reuses the exact scrape → filter → enrich pipeline that powers the email,
and caches results in memory (default 30 min, set `CACHE_TTL_SECONDS`) so
repeat visits are instant. The same `OMDB_API_KEY` / `TMDB_API_KEY` env vars
apply (scores also fall back to direct scraping without them).

A refresh that fails, or loses one cinema, keeps the last complete listings
(if under a day old) and says so on the page; an empty result is retried
after the cooldown rather than cached.
Refreshes are rate limited: no new scrape starts within 60 seconds of the
last one (set `REFRESH_COOLDOWN_SECONDS`), since each takes minutes and uses
OMDb/TMDB quota.

### Options

```bash
python -m cinema_digest.webapp --host 0.0.0.0 --port 8080   # bind publicly
```

### Hosting it

The module exposes a WSGI `app`, so any WSGI server works:

```bash
pip install gunicorn
gunicorn cinema_digest.webapp:app --bind 0.0.0.0:8080 --timeout 600
```

The timeout must exceed the pipeline's worst case: the first request after
the cache expires runs the scrape plus score enrichment, which is capped by
`RUN_TIME_BUDGET_SECONDS` (8 minutes) in `cinema_digest/config.py` and is
usually much quicker. With a shorter timeout gunicorn can kill the worker
mid-refresh, and the cache never fills.

### Netlify (static snapshot)

`netlify.toml` builds a static copy with `build_static.py`. The listings are
collected at build time, so the site needs rebuilding to stay current; the
page hides showtimes that have already started and has no Refresh button.

`.github/workflows/netlify_rebuild.yml` rebuilds it daily. To turn it on:

1. Link the Netlify project to this repo (Project configuration → Build &
   deploy → Link repository). Build hooks only work for linked projects.
2. Create a build hook (Project configuration → Build & deploy → Build hooks).
3. Add its URL as the repo secret `NETLIFY_BUILD_HOOK`.

Until the secret exists the workflow logs a warning and does nothing.

## Running tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v
```

Unit tests run offline (any network access fails the test). The live tests against Data Thistle are skipped unless you ask for them:

```bash
.venv/bin/python -m pytest -m integration      # or: RUN_INTEGRATION=1 pytest tests/
```

## Hosting locally

The script is designed to run unattended on a schedule. It does not need a web server or the computer to be logged in -- it just needs the machine to be powered on and connected to the internet.

All the examples run weekly on Tuesday at 18:00 London time, matching the GitHub Actions schedule (Option 6). Replace `/path/to/cinema-checking-bot` with the real path.

### Option 1: cron (Linux / macOS)

```bash
crontab -e
```

cron uses the system timezone; adjust the hour if your machine is not set to Europe/London:

```cron
0 18 * * 2 cd /path/to/cinema-checking-bot && .venv/bin/python -m cinema_digest.main >> "$HOME/cinema-digest.log" 2>&1
```

Log to a file your user can write (as above). If the shell cannot open the redirect target (e.g. `/var/log/...` for a normal user), cron does not run the command at all. On macOS, cron may also need Full Disk Access if the repo is under `~/Documents` or `~/Desktop`.

cron runs whether or not you are logged in, as long as the machine is on.

### Option 2: launchd (macOS)

launchd reads jobs from two places:

- `/Library/LaunchDaemons/` — system jobs; they run at boot whether or not anyone is logged in. The plist must be owned by `root:wheel` with mode `644`. Use the `UserName` key so the job runs as you, not root.
- `~/Library/LaunchAgents/` — per-user jobs; they run only while you are logged in. Leave out `UserName`.

(`~/Library/LaunchDaemons/` is not a location launchd reads, so a plist there never runs after a reboot.)

Create `/Library/LaunchDaemons/com.cinema-digest.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cinema-digest</string>
    <key>UserName</key>
    <string>your-macos-username</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/cinema-checking-bot/.venv/bin/python</string>
        <string>-m</string>
        <string>cinema_digest.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/cinema-checking-bot</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>2</integer>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/your-macos-username/Library/Logs/cinema-digest.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/your-macos-username/Library/Logs/cinema-digest.log</string>
</dict>
</plist>
```

Load it:

```bash
sudo chown root:wheel /Library/LaunchDaemons/com.cinema-digest.plist
sudo chmod 644 /Library/LaunchDaemons/com.cinema-digest.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.cinema-digest.plist
```

If a Mac is asleep at 18:00 on Tuesday, launchd runs the job when it wakes.

### Option 3: systemd (Linux)

Create `/etc/systemd/system/cinema-digest.service`:

```ini
[Unit]
Description=Cinema Digest Email
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=your-username
WorkingDirectory=/path/to/cinema-checking-bot
ExecStart=/path/to/cinema-checking-bot/.venv/bin/python -m cinema_digest.main
EnvironmentFile=/path/to/cinema-checking-bot/.env
```

Create `/etc/systemd/system/cinema-digest.timer`:

```ini
[Unit]
Description=Run Cinema Digest weekly

[Timer]
OnCalendar=Tue *-*-* 18:00:00 Europe/London
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cinema-digest.timer
systemctl list-timers cinema-digest.timer   # check the next run time
```

systemd timers run whether or not a user is logged in. `Persistent=true` ensures a missed run (e.g. machine was off) fires when the machine comes back online.

### Option 4: Task Scheduler (Windows)

Create a scheduled task that runs every Tuesday at 18:00:

```powershell
$action = New-ScheduledTaskAction `
    -Execute "C:\path\to\cinema-checking-bot\.venv\Scripts\python.exe" `
    -Argument "-m cinema_digest.main" `
    -WorkingDirectory "C:\path\to\cinema-checking-bot"

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 6:00PM

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "CinemaDigest" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Weekly cinema digest email"
```

`-StartWhenAvailable` ensures a missed run (e.g. laptop was asleep) fires when the machine wakes up. The task runs whether or not you are logged in if you configure it under "Run whether user is logged on or not" in the Task Scheduler GUI.

### Option 5: Virtual machine

If your local machine is not always on, run this on a cheap Linux VM (e.g. a free-tier Oracle Cloud instance, a small DigitalOcean droplet, or a Raspberry Pi). Set up using the cron or systemd options above.

### Option 6: GitHub Actions

If this repo is pushed to GitHub, the included workflow at `.github/workflows/cinema_digest.yml` runs **weekly on Tuesday at 17:00 UTC** (18:00 BST in summer, 17:00 GMT in winter). It can also be run by hand from the Actions tab. Add your secrets in the repo's Settings > Secrets and variables > Actions; secrets you leave undefined (e.g. `SMTP_PORT`) fall back to the defaults above.

Notes:

- GitHub often starts scheduled runs late, sometimes by an hour or more.
- GitHub disables scheduled workflows in public repos after 60 days without repository activity. The workflow's last step re-enables itself through the API (using the built-in token, no commits) to prevent that. If the schedule has been disabled anyway, re-enable it from the Actions tab.
- The run has an 8-minute time budget and always sends; score lookups that don't finish in time are marked in the digest. The job timeout (15 minutes) is only a backstop.

## Output format

Each film appears as one line:

```
- **Film Title — dir. Director** - logline - 83 / 7.4 / 91% - Clapham: Tue 18:10; Thu 20:30 | Ritzy: Fri 19:00 - [Book](https://web.picturehouses.com/order/showtimes/020-12345/seats)
```

Score order: Metacritic / IMDb / Rotten Tomatoes. N/A for unavailable scores; "(scores not fetched (time limit))" if the run's time budget ran out before that film's lookups finished. Films are ordered by Metacritic score, highest first; films without a Metacritic score come last, alphabetically.

The Book link goes to the booking page for the film's earliest qualifying screening. If that link isn't in Picturehouse's current booking format, it falls back to the film's Picturehouse page, then the cinema's page.

## Architecture

```
cinema_digest/
  config.py      - Environment variable loading
  models.py      - Film, Screening, Scores dataclasses
  scraper.py     - Data Thistle HTML parsing
  filters.py     - Showtime filtering (time windows, date range)
  enrich.py      - OMDb API score enrichment with caching
  formatter.py   - Markdown digest formatting
  emailer.py     - SMTP email sending
  main.py        - Orchestration entry point
```

## Limitations

- Data Thistle is a third-party scraping source. If they change their HTML structure, the scraper will need updating. The digest is still sent, with a warning at the top and a flagged subject, when a listings page can't be fetched, when films are found but no showtimes can be read, or when nothing qualifies for the next 7 days. An unusually low film count (fewer than 3 at a cinema) is noted in the digest.
- OMDb free tier is limited to 1000 API calls/day (more than enough for ~25 films).
- OMDb does not always have scores for new or niche releases. These show as N/A.
- The script does not detect sold-out or struck-through sessions (Data Thistle does not reliably expose this).

## Possible improvements

- Expire positive OMDb cache entries too (currently only "not found" results expire, after 7 days; delete `.cache/` to refresh scores)
- Add Letterboxd scores as an alternative/supplement to OMDb
- Support additional cinemas by adding URLs to `config.py`
- HTML email with nicer formatting (tables, poster thumbnails)
- Detect and skip "relaxed" or "audio described" duplicates if the user only wants standard screenings
