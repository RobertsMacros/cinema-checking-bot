# Expectations: Cinema Digest Bot

## Global Behaviours

### Scraping
- **Must scrape both cinemas**: Clapham Picturehouse and Ritzy Picturehouse (Brixton)
- **Must extract**: film title, year, duration, logline, screening times, booking URLs
- **Must merge films**: same film at both cinemas should appear once with combined screenings. The merge key is title plus year: same-title films with different known years (remakes) stay separate; an undated listing joins the same-title film
- **No repeated showtimes**: a showtime listed twice (same cinema, same start time) appears once
- **Low film count flags the digest, never aborts it**: fewer than 15 films at a cinema (a normal Picturehouse page lists 60 or more) adds a note and flags the subject "[CHECK: listings incomplete]"; the digest is still sent with whatever was found
- **Picturehouse first, Data Thistle as backup**: each cinema's Picturehouse page is read in headless Chromium; Data Thistle adds year, description and anything the page lacked. If a Picturehouse page can't be read, that cinema comes from Data Thistle only, with a note and the subject flagged "[CHECK: listings incomplete]"
- **Run report**: with `--report DIR`, every run saves its digest, the Picturehouse pages and `listings_check.json`; every film with a qualifying showing on a Picturehouse page must appear in the digest (`run_check` fails the run otherwise)
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
- **Highlighting**: star films with MC >= 76 or IMDb >= 7.7 (RT is not used). This is separate from the Wait and see bar (75 by default, per film), see DEC-4 in `DECISIONS.md`
- **Showtimes grouped by cinema**: "Clapham: Tue 18:10; Thu 20:30 | Ritzy: Fri 19:00"
- **Booking link**: link to the earliest qualifying screening's booking page (per cinema when a film shows at both). Only links in Picturehouse's current format (`https://web.picturehouses.com/order/showtimes/<cinema>-<session>/seats`) are used; otherwise fall back to the film's Picturehouse page, then the cinema page
- **Logline trimming**: keep as many whole sentences as fit in ~180 chars, never cut mid-sentence. A single first sentence longer than that is kept whole up to 300 chars; beyond that it is shortened at a word boundary and ends with "…" (never a fake full stop)
- **Broken-listings warning**: if no screenings qualify (including when films were parsed but no showtimes could be read, or nothing could be fetched), the digest says the listings page may have changed and the results are probably wrong, instead of "No qualifying screenings found"
- **Notes**: scraping problems (fetch failures, unusually low film counts, films without showtimes) and incomplete scores are listed under the header

### Email
- **Always sent**: every run sends a digest, whatever was found. Problems are flagged, never silently dropped
- **Subject flag**: "[CHECK: listings page may have changed]" when no screenings qualify; "[CHECK: listings incomplete]" when a cinema couldn't be fetched, had no readable showtimes, had fewer than 15 films, or fell back to Data Thistle only
- **Sent once**: the configured port is used first (465 = implicit TLS, otherwise STARTTLS); the other method is tried only if the first fails before the message is handed over. Server certificates are verified
- **Multipart**: sends both plain text and HTML versions
- **Dry run mode**: print to stdout + write HTML preview to `digest_preview.html`
- **Branded HTML**: Picturehouse brand colours, dark theme, responsive layout
- **Accessible**: `lang="en-GB"`; all text at least 4.5:1 contrast on its background (Picturehouse pink is used for fills and borders; pink text uses a lighter shade); no em dashes in headings or copy. On the web page the search box has a label, the cinema filter is a named group whose buttons report `aria-pressed`, keyboard focus stays on the chosen button, and the highlight star has a spoken label
- **Provenance and credits**: the footer (email, plain text and web page) names the listing sources actually used this run (Picturehouse Cinemas, Data Thistle or both), credits the score sources, carries TMDB's required notice ("This product uses the TMDB API but is not endorsed or certified by TMDB") and says "Not affiliated with Picturehouse Cinemas."

## Per-Feature Expectations

### Scraper: Picturehouse Pages (primary)
- Each cinema page is opened in headless Chromium; "Show all dates" is pressed and the listings parsed once rendered
- Day blocks carry the date in a class (`class_2026-11-14`); headings like "TODAY" are ignored
- Special screenings listed as their own film ("Relaxed: …", "Dog-Friendly - …") fold into the main film as a screening type, even when the special title drops "The"
- A page that yields no films counts as unreadable: that cinema falls back to Data Thistle and the subject is flagged
- A page that yields fewer than 15 films (it may not have loaded fully) is still used, with Data Thistle adding to it, but adds a note and flags the subject
- Data Thistle is named as a source whenever it was read, since it always supplies the year and description the Picturehouse pages lack

### Scraper: Data Thistle Parsing (backup and extra detail)
- h4 tags contain film titles as links
- First ul after h4 (before any h5) contains metadata (year, country, duration, rating)
- p tags contain logline/description
- h5 tags are date headers ("Wed 11 Mar")
- h6 tags are screening types ("Senior", "Subtitled")
- ul tags under h5 contain time links with booking URLs
- Films listed as "coming soon" may have zero screenings; this is expected. A cinema where every film has zero screenings is not: that is flagged as a likely markup change

### Enrichment: OMDb Pipeline
- Strip trailing "(2026)" and "!" from titles before searching, and Picturehouse event wrappers: known series labels in front ("MUBI FEST LIVE:", "Preview:", "Parent & Baby Screening:", "Kids' Club:" and similar) and extras after ("+ Q&A", "+ Intro"). Real titles with a colon or "+" ("Mission: Impossible", "Romeo + Juliet") are left alone. The digest still shows the title as listed
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
- Score source icons from Google favicon API; next to a score each icon has alt text naming its source (Metacritic, IMDb, Rotten Tomatoes), and a missing score reads "N/A"
- Film rows with star highlight for high-scored films
- Director, year, duration metadata line
- Compact inline showtimes
- Book button linking to earliest screening (one button per cinema when both show it)
