# Expectations — Cinema Digest Bot

## Global Behaviours

### Scraping
- **Must scrape both cinemas**: Clapham Picturehouse and Ritzy Picturehouse (Brixton)
- **Must extract**: film title, year, duration, logline, screening times, booking URLs
- **Must merge films**: same film at both cinemas should appear once with combined screenings
- **Minimum film count**: at least 3 films per cinema; raise error if fewer (structural breakage detection)
- **Resilient to missing data**: films without year/duration/logline should still be included

### Filtering
- **Weekday rule**: only show screenings from 18:00-21:30
- **Weekend rule**: only show screenings from 11:00-21:30
- **Date window**: today through today+6 days (7 days inclusive)
- **Past screenings excluded**: anything before "now" is dropped
- **Empty films dropped**: films with zero qualifying screenings after filtering are removed

### Score Enrichment
- **OMDb lookup**: search by cleaned title + year, retry without year if not found
- **Title verification**: reject matches with similarity < 0.6 to prevent wrong-film scores
- **TMDB fallback**: if OMDb returns nothing, try TMDB → get IMDB ID → OMDb by ID
- **RT scraping**: fill missing Rotten Tomatoes scores by scraping rottentomatoes.com
- **Caching**: cache OMDb responses to `.cache/` to avoid redundant API calls
- **Graceful failure**: API errors set scores to N/A, never crash the bot

### Formatting
- **Alphabetical order**: films sorted case-insensitively by title
- **Score format**: Metacritic / IMDb / RT% (N/A for missing)
- **Highlighting**: star films with MC >= 70, IMDb >= 7.0, or RT >= 80%
- **Showtimes grouped by cinema**: "Clapham: Tue 18:10, Thu 20:30; Ritzy: Fri 19:00"
- **Booking link**: link to earliest available screening
- **Logline trimming**: prefer sentence breaks within ~180 chars, never cut mid-sentence

### Email
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
- Films listed as "coming soon" may have zero screenings — this is expected

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
- Picturehouse logo from S3
- Score source icons from Google favicon API
- Film rows with star highlight for high-scored films
- Director, year, duration metadata line
- Compact inline showtimes
- Book button linking to earliest screening
