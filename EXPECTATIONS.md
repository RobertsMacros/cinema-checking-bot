# Expectations — Cinema Digest Bot

## Global Behaviours

### Scraping
- **Must scrape both cinemas**: Clapham Picturehouse and Ritzy Picturehouse (Brixton)
- **Must extract**: film title, year, duration, logline, screening times, booking URLs
- **Must merge films**: same film at both cinemas should appear once with combined screenings. The merge key is title plus year: same-title films with different known years (remakes) stay separate; an undated listing joins the same-title film
- **No repeated showtimes**: a showtime listed twice (same cinema, same start time) appears once
- **Low film count is a note, not an abort**: fewer than 3 films at a cinema adds a note to the digest ("unusually low; the listings page may have changed"); the digest is still sent with whatever was found
- **One cinema failing doesn't stop the other**: if a cinema page can't be fetched, the digest is sent with the other cinema's films and a warning
- **Resilient to missing data**: films without year/duration/logline should still be included; a missing year doesn't lose the duration
- **Date headers have no year**: pick this year or next (never more than 60 days in the past); the weekday prefix decides when both fit; 29 Feb only in a leap year

### Filtering
- **Weekday rule**: only show screenings from 18:00-21:30
- **Weekend rule**: only show screenings from 11:00-21:30
- **Date window**: today through today+6 days (7 days inclusive)
- **Past screenings excluded**: anything before "now" is dropped
- **Empty films dropped**: films with zero qualifying screenings after filtering are removed

### Score Enrichment
- **OMDb lookup**: search by cleaned title + year, retry without year if not found (the result must still pass the identity check, including the year)
- **Identity check** (OMDb, TMDB, IMDb, Metacritic, RT): title similarity >= 0.6 with leading articles kept; titles that differ only by a leading article are different films ("The Drama" ≠ "Drama"); when both years are known they must be within 1 year (UK release vs production year), which keeps remakes apart
- **TMDB fallback**: if OMDb returns nothing, try TMDB → get IMDB ID → OMDb by ID
- **RT scraping**: fill missing Rotten Tomatoes scores by scraping rottentomatoes.com
- **Caching**: cache the final validated OMDb result per title + year in `.cache/`. Cache hits are re-checked against the title/year; "not found" entries expire after 7 days; OMDb errors (rate limit, bad key) are never cached
- **Graceful failure**: API errors set scores to N/A, never crash the bot
- **Time budget**: the whole run has an 8-minute budget. Score lookups run concurrently (4 films at a time) with short timeouts and a single retry; when the budget is used up, lookups stop, the digest is sent with what was found, and films whose lookups didn't finish show "(scores not fetched (time limit))"

### Formatting
- **Order by score**: films sorted by Metacritic score, highest first; ties and films without a Metacritic score (last) are alphabetical, case-insensitive
- **Score format**: Metacritic / IMDb / RT% (N/A for missing)
- **Highlighting**: star films with MC >= 76 or IMDb >= 7.7 (RT is not used)
- **Showtimes grouped by cinema**: "Clapham: Tue 18:10; Thu 20:30 | Ritzy: Fri 19:00"
- **Booking link**: link to the earliest qualifying screening's booking page (per cinema when a film shows at both). Only links in Picturehouse's current format (`https://web.picturehouses.com/order/showtimes/<cinema>-<session>/seats`) are used; otherwise fall back to the film's Picturehouse page, then the cinema page
- **Logline trimming**: keep as many whole sentences as fit in ~180 chars, never cut mid-sentence. A single first sentence longer than that is kept whole up to 300 chars; beyond that it is shortened at a word boundary and ends with "…" (never a fake full stop)
- **Broken-listings warning**: if no screenings qualify (including when films were parsed but no showtimes could be read, or nothing could be fetched), the digest says the listings page may have changed and the results are probably wrong, instead of "No qualifying screenings found"
- **Notes**: scraping problems (fetch failures, unusually low film counts, films without showtimes) and incomplete scores are listed under the header

### Email
- **Always sent**: every run sends a digest, whatever was found. Problems are flagged, never silently dropped
- **Subject flag**: "[CHECK: listings page may have changed]" when no screenings qualify; "[CHECK: listings incomplete]" when a cinema couldn't be fetched or had no readable showtimes
- **Sent once**: the configured port is used first (465 = implicit TLS, otherwise STARTTLS); the other method is tried only if the first fails before the message is handed over. Server certificates are verified
- **Multipart**: sends both plain text and HTML versions
- **Dry run mode**: print to stdout + write HTML preview to `digest_preview.html`
- **Branded HTML**: Picturehouse brand colours, dark theme, responsive layout

## Per-Feature Expectations

### Scraper: Data Thistle Parsing
- h4 tags contain film titles as links
- First ul after h4 (before any h5) contains metadata (year, country, duration, rating)
- p tags contain logline/description
- h5 tags are date headers ("Wed 11 Mar")
- h6 tags are screening types ("Senior", "Subtitled")
- ul tags under h5 contain time links with booking URLs
- Films listed as "coming soon" may have zero screenings — this is expected. A cinema where every film has zero screenings is not: that is flagged as a likely markup change

### Enrichment: OMDb Pipeline
- Strip trailing "(2026)" and "!" from titles before searching
- If year specified and no result, retry without year
- Similarity check prevents "The Drama" from matching "Drama" (different film)
- Director and plot fields from OMDb enrich the film metadata
- OMDb shorter plot preferred over longer scraped logline

### Enrichment: TMDB Fallback
- Search TMDB by title + year
- Get external IDs endpoint to find IMDB ID
- Look up OMDb by IMDB ID for full MC/RT/IMDb scores
- If no IMDB ID, use TMDB vote_average as IMDb-style score (if >= 10 votes)

### Filter: Time Windows
- Boundary values: 18:00 included (weekday), 17:59 excluded
- Boundary values: 11:00 included (weekend), 10:59 excluded
- Boundary values: 21:30 included, 21:31 excluded
- Date boundary: day 6 included, day 7 excluded

### Formatter: HTML Email
- Warning banner and notes above the film list when there are problems
- All scraped text (titles, loglines, directors, notes) is HTML-escaped
- Picturehouse logo from S3
- Score source icons from Google favicon API
- Film rows with star highlight for high-scored films
- Director, year, duration metadata line
- Compact inline showtimes
- Book button linking to earliest screening (one button per cinema when both show it)
