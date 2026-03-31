"""Format the cinema digest as plain text and branded HTML email."""

from __future__ import annotations

import html as html_module
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from cinema_digest.config import CINEMA_URLS
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

PH_LOGO_URL = "https://s3picturehouses.s3.eu-central-1.amazonaws.com/settings/ph1551963779.png"

# Score source icons (Google favicon API — reliable for email)
ICON_MC = "https://www.google.com/s2/favicons?domain=metacritic.com&sz=32"
ICON_IMDB = "https://www.google.com/s2/favicons?domain=imdb.com&sz=32"
ICON_RT = "https://www.google.com/s2/favicons?domain=rottentomatoes.com&sz=32"


def is_highlighted(scores: Scores | None) -> bool:
    """A film is highlighted if Metacritic >= 76 or IMDb >= 7.7."""
    if scores is None:
        return False
    if scores.metacritic is not None and scores.metacritic >= 76:
        return True
    if scores.imdb is not None and scores.imdb >= 7.7:
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
        by_day: dict[str, list[str]] = {}
        for s in sorted(by_cinema[cinema], key=lambda x: x.date):
            day = s.date.strftime("%a")
            by_day.setdefault(day, []).append(s.date.strftime("%H:%M"))
        day_parts = [f"{day} {', '.join(times)}" for day, times in by_day.items()]
        cinema_parts.append(f"{cinema}: {'; '.join(day_parts)}")

    return " | ".join(cinema_parts)


def _format_booking_link_plain(film: Film) -> str:
    """Return a markdown booking link for plain text."""
    url = _film_booking_url(film) if hasattr(film, 'ph_url') else "https://www.picturehouses.com"
    return f"[Book]({url})"


# ---------------------------------------------------------------------------
# Plain text formatting
# ---------------------------------------------------------------------------

def format_film_line(film: Film) -> str:
    """Format a single film as a bullet line."""
    logline = _compact_logline(film.logline)
    scores = _format_scores(film.scores)
    showtimes = _format_showtimes(film.screenings)
    booking = _format_booking_link_plain(film)

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


def _sort_key_mc_desc(film: Film) -> tuple:
    """Sort key: Metacritic descending, then title. Films without MC go last."""
    mc = film.scores.metacritic if film.scores and film.scores.metacritic is not None else -1
    return (-mc, film.title.lower())


def format_digest(films: list[Film], now: datetime | None = None) -> str:
    """Format the complete plain-text digest body."""
    if now is None:
        now = datetime.now(LONDON_TZ)

    sorted_films = sorted(films, key=_sort_key_mc_desc)
    lines = [format_film_line(f) for f in sorted_films]

    date_str = now.strftime("%A %d %B %Y")
    header = f"Cinema Digest - {date_str}\n"
    header += "Clapham Picturehouse & Ritzy\n"
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


def _score_icon(url: str) -> str:
    return f'<img src="{url}" width="14" height="14" alt="" style="vertical-align:middle;margin-right:2px;">'


def _score_link(icon_url: str, label: str, link_url: str | None) -> str:
    icon = _score_icon(icon_url)
    if link_url:
        return f'<a href="{_esc(link_url)}" style="color:{DARK_TEXT};text-decoration:none;">{icon}{label}</a>'
    return f'{icon}{label}'


def _format_scores_html(scores: Scores | None) -> str:
    na = f'<span style="color:{DARK_TEXT_DIM};">—</span>'

    def _val(v, fmt):
        return fmt(v) if v is not None else na

    if scores is None:
        mc_val = imdb_val = rt_val = na
        mc_url = imdb_url = rt_url = None
    else:
        mc_val = _val(scores.metacritic, str)
        imdb_val = _val(scores.imdb, str)
        rt_val = _val(scores.rotten_tomatoes, lambda v: f"{v}%")
        # Build clickable links to the score source pages
        imdb_url = f"https://www.imdb.com/title/{scores.imdb_id}/" if scores.imdb_id else None
        mc_url = f"https://www.metacritic.com/movie/{scores.mc_slug}/" if scores.mc_slug else None
        rt_url = f"https://www.rottentomatoes.com{scores.rt_slug}" if scores.rt_slug else None

    parts = [
        _score_link(ICON_MC, mc_val, mc_url),
        _score_link(ICON_IMDB, imdb_val, imdb_url),
        _score_link(ICON_RT, rt_val, rt_url),
    ]
    return ' &nbsp; '.join(parts)


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
    loglines we find the first full sentence break (". " followed by
    an uppercase letter) and cut there.
    """
    text = _clean_logline(logline)
    if not text or len(text) <= 180:
        return text
    # Find a sentence break within 120 chars
    for m in re.finditer(r'[.!?]\s+(?=[A-Z])', text):
        if m.start() <= 180:
            return text[:m.start() + 1]
        break  # first break is past limit
    # Try comma or semicolon break for a natural pause
    truncated = text[:180]
    for sep in (", and ", "; ", ", who ", ", where ", ", exploring ", ", facing "):
        idx = truncated.rfind(sep)
        if idx >= 40:
            return text[:idx] + "."
    # Last resort: break at last comma
    idx = truncated.rfind(", ")
    if idx >= 40:
        return text[:idx] + "."
    # Break at last space
    return text[:177].rsplit(" ", 1)[0] + "."


def _format_showtimes_inline_html(screenings: list[Screening]) -> str:
    """Compact inline showtimes grouped by day: 'Clapham: Tue 18:10; Sun 14:50, 17:20'."""
    by_cinema: dict[str, list[Screening]] = {}
    for s in screenings:
        by_cinema.setdefault(s.cinema, []).append(s)

    parts = []
    for cinema in sorted(by_cinema):
        # Group by day abbreviation
        by_day: dict[str, list[str]] = {}
        for s in sorted(by_cinema[cinema], key=lambda x: x.date):
            day = s.date.strftime("%a")
            by_day.setdefault(day, []).append(s.date.strftime("%H:%M"))
        day_parts = []
        for day, times in by_day.items():
            day_parts.append(f'{day}&nbsp;{", ".join(times)}')
        parts.append(f'<strong style="color:{PH_WHITE};">{_esc(cinema)}</strong>:&nbsp;{"; ".join(day_parts)}')

    return "<br>".join(parts)


def _film_booking_url(film: Film) -> str:
    """Return the best booking URL: PH film page > PH cinema page > fallback."""
    if film.ph_url:
        return film.ph_url
    first = min(film.screenings, key=lambda s: s.date)
    return CINEMA_URLS.get(first.cinema, "https://www.picturehouses.com")


def _book_buttons_html(film: Film, on_pink: bool = False) -> str:
    """Build booking button(s). Single 'Book' if one cinema, 'Clapham'/'Ritzy' if both."""
    cinemas = sorted(set(s.cinema for s in film.screenings))
    bg = PH_WHITE if on_pink else PH_PINK
    fg = PH_PINK if on_pink else PH_WHITE
    btn = (
        'display:inline-block;background:{bg};color:{fg};text-decoration:none;'
        'padding:4px 10px;border-radius:3px;font-size:12px;font-weight:bold;margin-right:4px;'
    ).format(bg=bg, fg=fg)

    if len(cinemas) <= 1:
        url = _film_booking_url(film)
        return f'<a href="{_esc(url)}" style="{btn}">Book</a>'

    # Both cinemas — one button each
    buttons = []
    for cinema in cinemas:
        url = _film_booking_url(film)
        # Use cinema-specific PH URL if we can build one
        cinema_url = CINEMA_URLS.get(cinema, url)
        if film.ph_url:
            # Swap the cinema code in the ph_url
            from cinema_digest.config import CINEMA_CODES
            code = CINEMA_CODES.get(cinema, "000")
            cinema_url = re.sub(r'/movie-details/\d+/', f'/movie-details/{code}/', film.ph_url)
        buttons.append(f'<a href="{_esc(cinema_url)}" style="{btn}">{_esc(cinema)}</a>')
    return " ".join(buttons)


def _film_row_html(film: Film, is_top: bool = False) -> str:
    highlighted = is_highlighted(film.scores)

    logline = _esc(_compact_logline(film.logline))
    scores = _format_scores_html(film.scores)
    showtimes = _format_showtimes_inline_html(film.screenings)
    book_buttons = _book_buttons_html(film)

    star = " &#11088;" if highlighted else ""

    # Director + year metadata line
    meta_parts: list[str] = []
    if film.director:
        meta_parts.append(_esc(film.director))
    if film.year:
        meta_parts.append(str(film.year))
    if film.duration:
        meta_parts.append(_esc(film.duration))
    meta_line = " &middot; ".join(meta_parts)

    card_bg = DARK_CARD
    radius = "12px"
    title_color = PH_WHITE
    meta_color = DARK_TEXT_DIM
    text_color = DARK_TEXT_MUTED

    return f"""<tr><td colspan="4" style="padding:0 0 8px 0;">
<table cellpadding="0" cellspacing="0" border="0" role="presentation" style="width:100%;background:{card_bg};border-radius:{radius};overflow:hidden;">
<tr>
<td style="padding:10px 14px;vertical-align:top;">
  <div style="font-size:14px;font-weight:bold;color:{title_color};line-height:1.3;">{_esc(film.title)}{star}</div>
  <div style="font-size:12px;color:{meta_color};margin-top:2px;">{meta_line}</div>
  <div style="font-size:12px;color:{text_color};margin-top:3px;line-height:1.4;">{logline}</div>
</td>
</tr>
<tr>
<td style="padding:0 14px 10px 14px;">
  <div style="font-size:12px;color:{text_color};line-height:1.5;">{showtimes}</div>
  <div style="font-size:12px;margin-top:6px;">{scores} &nbsp; {book_buttons}</div>
</td>
</tr>
</table>
</td></tr>"""


def format_digest_html(films: list[Film], now: datetime | None = None) -> str:
    """Format the complete HTML email with Picturehouse branding."""
    if now is None:
        now = datetime.now(LONDON_TZ)

    date_str = now.strftime("%A %d %B %Y")
    sorted_films = sorted(films, key=_sort_key_mc_desc)

    if sorted_films:
        film_rows = "\n".join(_film_row_html(f) for f in sorted_films)
    else:
        film_rows = (
            f'<tr><td colspan="4" style="padding:30px;text-align:center;color:{DARK_TEXT_MUTED};'
            f'background:{DARK_CARD};font-size:14px;">No qualifying screenings found for this week.</td></tr>'
        )

    highlighted_count = sum(1 for f in sorted_films if is_highlighted(f.scores))
    star_legend = ""
    if highlighted_count > 0:
        star_legend = f'<br>&#11088; = Metacritic &ge; 76 or IMDb &ge; 7.7'

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
  <img src="{PH_LOGO_URL}" alt="Picturehouse Cinemas" width="185" height="109" style="width:185px;height:109px;margin-bottom:12px;display:block;margin-left:auto;margin-right:auto;-ms-interpolation-mode:bicubic;image-rendering:-webkit-optimize-contrast;">
  <div style="color:{PH_WHITE};font-size:24px;font-weight:bold;letter-spacing:0.5px;font-family:{FONT_STACK};">&mdash;&ensp;Cinema Digest&ensp;&mdash;</div>
  <div style="color:{DARK_TEXT_MUTED};font-size:13px;margin-top:4px;">{_esc(date_str)}</div>
</td></tr>

<!-- Info -->
<tr><td style="background:{PH_PINK};padding:12px 20px;text-align:center;border-radius:12px;">
  <span style="font-size:12px;color:{PH_WHITE};">Evening &amp; weekend showtimes for the next 7 days at Clapham Picturehouse and Ritzy &middot; Weekdays from 18:00 &middot; Weekends from 11:00</span>
</td></tr>

<!-- Films -->
<tr><td colspan="1" style="padding:8px;">
<table cellpadding="0" cellspacing="0" border="0" role="presentation" style="width:100%;">
{film_rows}
</table>
</td></tr>

<!-- Footer -->
<tr><td style="background:{DARK_BG};padding:20px;text-align:center;">
  <div style="color:{DARK_TEXT_DIM};font-size:11px;line-height:1.6;">
    Scores: {_score_icon(ICON_MC)}Metacritic &middot; {_score_icon(ICON_IMDB)}IMDb &middot; {_score_icon(ICON_RT)}Rotten Tomatoes{star_legend}<br>
    Listings from <a href="https://film.datathistle.com/" style="color:{PH_PINK};text-decoration:none;">Data Thistle</a>
  </div>
</td></tr>

</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr>
</table>
</body>
</html>"""
