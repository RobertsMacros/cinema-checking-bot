# Cinema Digest

Automatically fetches upcoming film listings from Clapham Picturehouse and Ritzy Picturehouse (Brixton), enriches them with review scores, and emails a formatted digest.

## What it does

1. Scrapes film listings from [Data Thistle](https://film.datathistle.com/) for both cinemas
2. Filters showtimes to evenings (weekdays 18:00-21:30, weekends 11:00-21:30)
3. Enriches each film with Metacritic, IMDb, and Rotten Tomatoes scores via [OMDb API](https://www.omdbapi.com/)
4. Formats a clean, alphabetised digest
5. Emails the result (or prints it in dry-run mode)

## Setup

```bash
cd cinema-digest
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
```

### Required credentials

| Variable | Description |
|----------|-------------|
| `OMDB_API_KEY` | Free API key from [omdbapi.com](https://www.omdbapi.com/apikey.aspx) (1000 requests/day) |
| `TMDB_API_KEY` | Free API key from [themoviedb.org](https://www.themoviedb.org/settings/api) (fallback for score lookups) |
| `SMTP_HOST` | SMTP server (default: `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (default: `587`) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password or app-specific password |
| `EMAIL_FROM` | Sender email address |
| `EMAIL_TO` | Recipient email address(es), comma-separated |

For Gmail: enable 2FA, then create an [App Password](https://myaccount.google.com/apppasswords).

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

## Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Hosting locally

The script is designed to run unattended on a schedule. It does not need a web server or the computer to be logged in -- it just needs the machine to be powered on and connected to the internet.

### Option 1: cron (Linux / macOS)

```bash
crontab -e
```

Add a line to run at 07:00 London time. Since cron uses the system timezone, adjust if your machine is not set to Europe/London:

```cron
0 7 * * * cd /path/to/cinema-digest && /usr/bin/python3 -m cinema_digest.main >> /var/log/cinema-digest.log 2>&1
```

cron runs whether or not you are logged in, as long as the machine is on.

### Option 2: launchd (macOS)

Create `~/Library/LaunchDaemons/com.cinema-digest.plist` (use LaunchDaemons, not LaunchAgents, so it runs even when not logged in):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cinema-digest</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>cinema_digest.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/cinema-digest</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/cinema-digest.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/cinema-digest.log</string>
</dict>
</plist>
```

Load it:

```bash
sudo launchctl load ~/Library/LaunchDaemons/com.cinema-digest.plist
```

Note: LaunchDaemons run as root and persist across logouts and reboots. If you prefer user-level (runs only when logged in), use `~/Library/LaunchAgents/` instead.

### Option 3: systemd (Linux)

Create `/etc/systemd/system/cinema-digest.service`:

```ini
[Unit]
Description=Cinema Digest Email
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/cinema-digest
ExecStart=/usr/bin/python3 -m cinema_digest.main
EnvironmentFile=/path/to/cinema-digest/.env
```

Create `/etc/systemd/system/cinema-digest.timer`:

```ini
[Unit]
Description=Run Cinema Digest daily

[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cinema-digest.timer
sudo systemctl start cinema-digest.timer
```

systemd timers run whether or not a user is logged in. `Persistent=true` ensures a missed run (e.g. machine was off) fires when the machine comes back online.

### Option 4: Task Scheduler (Windows)

Create a scheduled task that runs daily at 07:00:

```powershell
$action = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument "-m cinema_digest.main" `
    -WorkingDirectory "C:\path\to\cinema-checking-bot"

$trigger = New-ScheduledTaskTrigger -Daily -At 7:00AM

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "CinemaDigest" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily cinema digest email"
```

`-StartWhenAvailable` ensures a missed run (e.g. laptop was asleep) fires when the machine wakes up. The task runs whether or not you are logged in if you configure it under "Run whether user is logged on or not" in the Task Scheduler GUI.

### Option 5: Virtual machine

If your local machine is not always on, run this on a cheap Linux VM (e.g. a free-tier Oracle Cloud instance, a small DigitalOcean droplet, or a Raspberry Pi). Set up using the cron or systemd options above.

### Option 6: GitHub Actions

If this repo is pushed to GitHub, the included workflow at `.github/workflows/cinema_digest.yml` runs daily at 06:00 UTC (07:00 BST / 06:00 GMT). Add your secrets in the repo's Settings > Secrets and variables > Actions.

## Output format

Each film appears as one line:

```
- **Film Title** - logline - 83 / 7.4 / 91% - Clapham: Tue 18:10, Thu 20:30; Ritzy: Fri 19:00 - [Book at Ritzy](https://...)
```

Score order: Metacritic / IMDb / Rotten Tomatoes. N/A for unavailable scores.

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

- Data Thistle is a third-party scraping source. If they change their HTML structure, the scraper will need updating. The code validates minimum film counts to detect this.
- OMDb free tier is limited to 1000 API calls/day (more than enough for ~25 films).
- OMDb does not always have scores for new or niche releases. These show as N/A.
- The script does not detect sold-out or struck-through sessions (Data Thistle does not reliably expose this).

## Possible improvements

- Add an OMDb cache expiry (currently cached forever; delete `.cache/` to refresh)
- Persist the OMDb cache across GitHub Actions runs using `actions/cache`
- Add Letterboxd scores as an alternative/supplement to OMDb
- Support additional cinemas by adding URLs to `config.py`
- HTML email with nicer formatting (tables, poster thumbnails)
- Detect and skip "relaxed" or "audio described" duplicates if the user only wants standard screenings
