"""Format the cinema digest as plain text and branded HTML email."""

from __future__ import annotations

import html as html_module
from datetime import datetime
from zoneinfo import ZoneInfo

from cinema_digest.models import Film, Scores, Screening

LONDON_TZ = ZoneInfo("Europe/London")

# Picturehouse brand colours
PH_PINK = "#E2124D"
PH_BLACK = "#1a1a1a"
PH_WHITE = "#ffffff"
PH_LIGHT_GREY = "#f5f5f5"
PH_MID_GREY = "#888888"

# Dark theme colours
DARK_BG = "#1a1a1a"
DARK_CARD = "#222222"
DARK_CARD_HL = "#2a1a1e"
DARK_BORDER = "#333333"
DARK_TEXT = "#eeeeee"
DARK_TEXT_MUTED = "#aaaaaa"
DARK_TEXT_DIM = "#666666"

# Font stack
FONT_STACK = "Georgia,'Times New Roman',Times,serif"

PH_LOGO_URL = "https://www.picturehouses.com/graphics/picturehouse-og.jpg"


def is_highlighted(scores: Scores | None) -> bool:
    """A film is highlighted if Metacritic >= 70, IMDb >= 7.0, or RT >= 80%."""
    if scores is None:
        return False
    if scores.metacritic is not None and scores.metacritic >= 70:
        return True
    if scores.imdb is not None and scores.imdb >= 7.0:
        return True
    if scores.rotten_tomatoes is not None and scores.rotten_tomatoes >= 80:
        return True
    return False


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _clean_logline(logline: str | None) -> str:
    """Clean up whitespace in a logline without truncating."""
    if not logline:
        return ""
    return " ".join(logline.split())


def _format_scores(scores: Scores | None) -> str:
    """Format scores as 'MC / IMDb / RT%', using N/A for missing values."""
    if scores is None:
        return "N/A / N/A / N/A"
    parts = [
        str(scores.metacritic) if scores.metacritic is not None else "N/A",
        str(scores.imdb) if scores.imdb is not None else "N/A",
        f"{scores.rotten_tomatoes}%" if scores.rotten_tomatoes is not None else "N/A",
    ]
    return " / ".join(parts)


def _format_showtimes(screenings: list[Screening]) -> str:
    """Format showtimes grouped by cinema (plain text)."""
    by_cinema: dict[str, list[Screening]] = {}
    for s in screenings:
        by_cinema.setdefault(s.cinema, []).append(s)

    cinema_parts = []
    for cinema in sorted(by_cinema):
        times = []
        for s in sorted(by_cinema[cinema], key=lambda x: x.date):
            day_abbr = s.date.strftime("%a")
            time_str = s.date.strftime("%H:%M")
            times.append(f"{day_abbr} {time_str}")
        cinema_parts.append(f"{cinema}: {', '.join(times)}")

    return "; ".join(cinema_parts)


def _format_booking_link(screenings: list[Screening]) -> str:
    """Return a markdown link to the earliest available booking."""
    first = min(screenings, key=lambda s: s.date)
    return f"[Book at {first.cinema}]({first.booking_url})"


def _booking_info(screenings: list[Screening]) -> tuple[str, str]:
    """Return (cinema_name, url) for the earliest booking."""
    first = min(screenings, key=lambda s: s.date)
    return first.cinema, first.booking_url


# ---------------------------------------------------------------------------
# Plain text formatting
# ---------------------------------------------------------------------------

def format_film_line(film: Film) -> str:
    """Format a single film as a bullet line."""
    logline = _compact_logline(film.logline)
    scores = _format_scores(film.scores)
    showtimes = _format_showtimes(film.screenings)
    booking = _format_booking_link(film.screenings)

    title_parts = [film.title]
    if film.director:
        title_parts.append(f"dir. {film.director}")

    parts = [f"- **{' — '.join(title_parts)}**"]
    if logline:
        parts.append(logline)
    parts.append(scores)
    parts.append(showtimes)
    parts.append(booking)

    return " - ".join(parts)


def format_digest(films: list[Film], now: datetime | None = None) -> str:
    """Format the complete plain-text digest body."""
    if now is None:
        now = datetime.now(LONDON_TZ)

    sorted_films = sorted(films, key=lambda f: f.title.lower())
    lines = [format_film_line(f) for f in sorted_films]

    date_str = now.strftime("%A %d %B %Y")
    header = f"Cinema Digest - {date_str}\n"
    header += "Clapham Picturehouse and Ritzy Picturehouse (Brixton)\n"
    header += "Showtimes for the next 7 days\n"
    header += "-" * 50 + "\n\n"

    if not lines:
        return header + "No qualifying screenings found for this week.\n"

    return header + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# HTML email formatting
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    return html_module.escape(text)


def _format_scores_html(scores: Scores | None) -> str:
    na = f'<span style="color:{DARK_TEXT_DIM};">N/A</span>'
    if scores is None:
        return f"{na} / {na} / {na}"
    parts = []
    for val, fmt in [
        (scores.metacritic, lambda v: str(v)),
        (scores.imdb, lambda v: str(v)),
        (scores.rotten_tomatoes, lambda v: f"{v}%"),
    ]:
        parts.append(fmt(val) if val is not None else na)
    return " / ".join(parts)


def _format_showtimes_html(screenings: list[Screening]) -> str:
    by_cinema: dict[str, list[Screening]] = {}
    for s in screenings:
        by_cinema.setdefault(s.cinema, []).append(s)

    parts = []
    for cinema in sorted(by_cinema):
        times = []
        for s in sorted(by_cinema[cinema], key=lambda x: x.date):
            times.append(f'{s.date.strftime("%a")}&nbsp;{s.date.strftime("%H:%M")}')
        parts.append(f'<strong style="color:{PH_WHITE};">{_esc(cinema)}</strong>: {", ".join(times)}')

    return "<br>".join(parts)


def _compact_logline(logline: str | None) -> str:
    """Return a logline suitable for ~2 lines of display.

    Prefers keeping the text intact if it's short enough.  For longer
    loglines we trim to the last full sentence that fits within ~180
    characters so it reads naturally rather than being cut mid-sentence.
    """
    text = _clean_logline(logline)
    if not text or len(text) <= 180:
        return text
    # Try to break at a sentence boundary within 180 chars
    truncated = text[:180]
    for end in (". ", "! ", "? "):
        idx = truncated.rfind(end)
        if idx >= 10:
            return truncated[: idx + 1]
    return truncated.rsplit(" ", 1)[0] + "\u2026"


def _format_showtimes_inline_html(screenings: list[Screening]) -> str:
    """Compact inline showtimes: 'Clapham: Tue 18:10; Ritzy: Fri 19:00'."""
    by_cinema: dict[str, list[Screening]] = {}
    for s in screenings:
        by_cinema.setdefault(s.cinema, []).append(s)

    parts = []
    for cinema in sorted(by_cinema):
        times = []
        for s in sorted(by_cinema[cinema], key=lambda x: x.date):
            times.append(f'{s.date.strftime("%a")}&nbsp;{s.date.strftime("%H:%M")}')
        parts.append(f'<strong style="color:{PH_WHITE};">{_esc(cinema)}</strong>:&nbsp;{", ".join(times)}')

    return " &middot; ".join(parts)


def _film_row_html(film: Film) -> str:
    highlighted = is_highlighted(film.scores)

    row_bg = DARK_CARD_HL if highlighted else DARK_CARD

    logline = _esc(_compact_logline(film.logline))
    scores = _format_scores_html(film.scores)
    showtimes = _format_showtimes_inline_html(film.screenings)
    book_cinema, book_url = _booking_info(film.screenings)

    # Star column content
    star_cell = f'<span style="font-size:16px;">&#11088;</span>' if highlighted else ""

    # Director + year metadata line
    meta_parts: list[str] = []
    if film.director:
        meta_parts.append(_esc(film.director))
    if film.year:
        meta_parts.append(str(film.year))
    if film.duration:
        meta_parts.append(_esc(film.duration))
    meta_line = " &middot; ".join(meta_parts)

    return f"""<tr style="background:{row_bg};">
<td style="padding:8px 4px 8px 8px;border-bottom:1px solid {DARK_BORDER};vertical-align:top;width:28px;text-align:center;">{star_cell}</td>
<td style="padding:8px 6px;border-bottom:1px solid {DARK_BORDER};vertical-align:top;">
  <div style="font-size:14px;font-weight:bold;color:{PH_WHITE};line-height:1.3;">{_esc(film.title)}</div>
  <div style="font-size:11px;color:{DARK_TEXT_DIM};margin-top:2px;">{meta_line}</div>
  <div style="font-size:12px;color:{DARK_TEXT_MUTED};margin-top:3px;line-height:1.4;">{logline}</div>
</td>
<td style="padding:8px 6px;border-bottom:1px solid {DARK_BORDER};vertical-align:top;white-space:nowrap;">
  <div style="font-size:12px;font-weight:bold;color:{DARK_TEXT};">{scores}</div>
</td>
<td style="padding:8px 8px 8px 6px;border-bottom:1px solid {DARK_BORDER};vertical-align:top;">
  <div style="font-size:11px;color:{DARK_TEXT_MUTED};line-height:1.4;">{showtimes}</div>
  <a href="{_esc(book_url)}" style="display:inline-block;background:{PH_PINK};color:{PH_WHITE};text-decoration:none;padding:4px 10px;border-radius:3px;font-size:11px;font-weight:bold;margin-top:4px;">Book</a>
</td>
</tr>"""


def format_digest_html(films: list[Film], now: datetime | None = None) -> str:
    """Format the complete HTML email with Picturehouse branding."""
    if now is None:
        now = datetime.now(LONDON_TZ)

    date_str = now.strftime("%A %d %B %Y")
    sorted_films = sorted(films, key=lambda f: f.title.lower())

    if sorted_films:
        film_rows = "\n".join(_film_row_html(f) for f in sorted_films)
    else:
        film_rows = (
            f'<tr><td colspan="4" style="padding:30px;text-align:center;color:{DARK_TEXT_MUTED};'
            f'background:{DARK_CARD};font-size:14px;">No qualifying screenings found for this week.</td></tr>'
        )

    highlighted_count = sum(1 for f in sorted_films if is_highlighted(f.scores))
    legend = ""
    if highlighted_count > 0:
        legend = f"""<tr>
<td colspan="4" style="padding:6px 8px;font-size:11px;color:{DARK_TEXT_MUTED};background:{DARK_CARD};">
  &#11088; = Metacritic &ge; 70, IMDb &ge; 7.0, or Rotten Tomatoes &ge; 80%
</td>
</tr>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Cinema Digest - {_esc(date_str)}</title>
</head>
<body style="margin:0;padding:0;background:{DARK_BG};font-family:{FONT_STACK};color:{DARK_TEXT};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="background:{DARK_BG};">
<tr><td align="center" style="padding:20px 10px;">
<!--[if mso]><table width="620" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
<table cellpadding="0" cellspacing="0" border="0" role="presentation" style="max-width:620px;width:100%;">

<!-- Header -->
<tr><td style="background:{DARK_BG};padding:24px 20px;text-align:center;">
  <img src="{PH_LOGO_URL}" alt="Picturehouse Cinemas" width="200" style="max-width:200px;width:100%;height:auto;margin-bottom:12px;display:block;margin-left:auto;margin-right:auto;">
  <div style="color:{PH_WHITE};font-size:24px;font-weight:bold;letter-spacing:0.5px;font-family:{FONT_STACK};">Cinema Digest</div>
  <div style="color:{DARK_TEXT_MUTED};font-size:13px;margin-top:4px;">{_esc(date_str)}</div>
</td></tr>

<!-- Pink bar -->
<tr><td style="background:{PH_PINK};padding:10px 20px;text-align:center;">
  <span style="color:{PH_WHITE};font-size:12px;font-weight:bold;letter-spacing:1px;text-transform:uppercase;">Clapham Picturehouse &amp; Ritzy Picturehouse, Brixton</span>
</td></tr>

<!-- Info -->
<tr><td style="background:{DARK_CARD};padding:12px 20px;text-align:center;border-bottom:1px solid {DARK_BORDER};">
  <span style="font-size:12px;color:{DARK_TEXT_MUTED};">Evening &amp; weekend showtimes for the next 7 days &middot; Weekdays from 18:00 &middot; Weekends from 11:00</span>
</td></tr>

{legend}

<!-- Films -->
<tr><td colspan="1" style="padding:0;">
<table cellpadding="0" cellspacing="0" border="0" role="presentation" style="width:100%;">
{film_rows}
</table>
</td></tr>

<!-- Footer -->
<tr><td style="background:{DARK_BG};padding:20px;text-align:center;">
  <div style="color:{DARK_TEXT_DIM};font-size:11px;line-height:1.6;">
    Scores: Metacritic / IMDb / Rotten Tomatoes<br>
    Listings from <a href="https://film.datathistle.com/" style="color:{PH_PINK};text-decoration:none;">Data Thistle</a>
    &middot; Scores from <a href="https://www.omdbapi.com/" style="color:{PH_PINK};text-decoration:none;">OMDb</a>
  </div>
</td></tr>

</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr>
</table>
</body>
</html>"""
