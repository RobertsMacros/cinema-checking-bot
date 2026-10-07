"""Single-page HTML/CSS/JS served by the web app.

Kept as a module-level string so the app has no template-file plumbing and
stays fully self-contained.
"""

from __future__ import annotations

PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cinema Listings — Clapham &amp; Ritzy</title>
<script>window.FILMS_URL = window.FILMS_URL || "/api/films";</script>
<style>
  :root {
    --ph-pink: #E2124D;
    --bg: #141414;
    --card: #1e1e1e;
    --card-hl: #2a1820;
    --border: #313131;
    --text: #f0f0f0;
    --muted: #9a9a9a;
    --dim: #6a6a6a;
    --serif: Georgia, "Times New Roman", Times, serif;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--serif);
    -webkit-font-smoothing: antialiased;
    line-height: 1.4;
  }
  a { color: inherit; }

  header {
    text-align: center;
    padding: 26px 16px 14px;
  }
  header img { width: 150px; height: auto; display: block; margin: 0 auto 10px; }
  header h1 {
    font-size: 22px; font-weight: bold; margin: 0; letter-spacing: 0.5px;
  }
  header .sub { color: var(--muted); font-size: 13px; margin-top: 4px; }

  .toolbar {
    position: sticky; top: 0; z-index: 10;
    background: rgba(20,20,20,0.94);
    backdrop-filter: blur(6px);
    border-bottom: 1px solid var(--border);
    padding: 12px 16px;
  }
  .toolbar-inner { max-width: 900px; margin: 0 auto; }
  .pills { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
  .pill {
    font-family: var(--serif);
    font-size: 14px;
    padding: 6px 16px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .pill:hover { color: var(--text); border-color: var(--muted); }
  .pill.active {
    background: var(--ph-pink); color: #fff; border-color: var(--ph-pink);
  }
  .controls {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
    justify-content: center; margin-top: 10px;
  }
  .controls input[type="search"] {
    font-family: var(--serif); font-size: 14px;
    background: var(--card); color: var(--text);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 7px 12px; width: 220px; max-width: 60vw;
  }
  .controls input[type="search"]::placeholder { color: var(--dim); }
  .toggle { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: 13px; cursor: pointer; }
  .btn {
    font-family: var(--serif); font-size: 13px;
    background: transparent; color: var(--muted);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 7px 14px; cursor: pointer;
  }
  .btn:hover:not(:disabled) { color: var(--text); border-color: var(--muted); }
  .btn:disabled { opacity: 0.5; cursor: default; }

  .meta-bar {
    max-width: 900px; margin: 10px auto 0; padding: 0 16px;
    display: flex; justify-content: space-between; align-items: center;
    color: var(--dim); font-size: 12px; gap: 10px; flex-wrap: wrap;
  }

  main { max-width: 900px; margin: 0 auto; padding: 8px 16px 60px; }

  .grid { display: grid; gap: 12px; grid-template-columns: 1fr; }
  @media (min-width: 640px) { .grid { grid-template-columns: 1fr 1fr; } }

  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px 16px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .card.hl { background: var(--card-hl); border-color: #4a2333; }
  .card .title { font-size: 17px; font-weight: bold; line-height: 1.25; }
  .card .title .star { color: #f5c518; margin-left: 4px; }
  .card .metaline { font-size: 12px; color: var(--dim); }
  .card .logline { font-size: 13px; color: var(--muted); line-height: 1.45; }

  .scores { display: flex; gap: 14px; font-size: 13px; align-items: center; flex-wrap: wrap; }
  .scores a, .scores span.score { display: inline-flex; align-items: center; gap: 4px; text-decoration: none; color: var(--text); }
  .scores img { width: 15px; height: 15px; vertical-align: middle; }
  .scores .na { color: var(--dim); }

  .showtimes { font-size: 13px; display: flex; flex-direction: column; gap: 4px; }
  .showtimes .cine { display: flex; gap: 6px; flex-wrap: wrap; align-items: baseline; }
  .showtimes .cine-name { color: #fff; font-weight: bold; min-width: 58px; }
  .showtimes .slot {
    color: var(--muted); text-decoration: none;
    border: 1px solid var(--border); border-radius: 6px;
    padding: 1px 7px; font-size: 12px; white-space: nowrap;
  }
  .showtimes .slot:hover { border-color: var(--ph-pink); color: var(--text); }

  .booking { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 2px; }
  .booking a {
    background: var(--ph-pink); color: #fff; text-decoration: none;
    font-size: 12px; font-weight: bold; padding: 5px 12px; border-radius: 6px;
  }
  .booking a:hover { background: #c50f42; }

  .state { text-align: center; padding: 60px 20px; color: var(--muted); }
  .spinner {
    width: 34px; height: 34px; margin: 0 auto 16px;
    border: 3px solid var(--border); border-top-color: var(--ph-pink);
    border-radius: 50%; animation: spin 0.9s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error { color: var(--ph-pink); }
  .banner {
    max-width: 900px; margin: 10px auto 0; padding: 10px 14px;
    border: 1px solid #4a2333; background: var(--card-hl); border-radius: 10px;
    color: var(--text); font-size: 13px;
  }
  .banner ul { margin: 6px 0 0; padding-left: 18px; color: var(--muted); }
  .wrap-banner { padding: 0 16px; }
  .badge {
    display: inline-block; font-size: 11px; font-weight: normal; vertical-align: middle;
    border: 1px solid var(--ph-pink); color: var(--ph-pink);
    border-radius: 999px; padding: 1px 8px; margin-left: 6px;
  }

  footer { text-align: center; color: var(--dim); font-size: 11px; padding: 24px 16px 40px; }
  footer a { color: var(--ph-pink); text-decoration: none; }
</style>
</head>
<body>
  <header>
    <img src="https://s3picturehouses.s3.eu-central-1.amazonaws.com/settings/ph1551963779.png" alt="Picturehouse">
    <h1>— Cinema Listings —</h1>
    <div class="sub">Evening &amp; weekend showtimes · next 7 days · Clapham &amp; Ritzy</div>
  </header>

  <div class="toolbar">
    <div class="toolbar-inner">
      <div class="pills" id="pills"></div>
      <div class="controls">
        <input type="search" id="search" placeholder="Search title, director…" autocomplete="off">
        <label class="toggle"><input type="checkbox" id="hlOnly"> Highlights only ⭐</label>
        <button class="btn" id="refresh">↻ Refresh</button>
      </div>
    </div>
  </div>

  <div class="meta-bar">
    <span id="resultCount"></span>
    <span id="updated"></span>
  </div>

  <div class="wrap-banner"><div class="banner" id="banner" hidden></div></div>

  <main>
    <div id="content">
      <div class="state"><div class="spinner"></div>Loading listings…</div>
    </div>
  </main>

  <footer>
    Scores: Metacritic · IMDb · Rotten Tomatoes ·
    Listings from <a href="https://film.datathistle.com/">Data Thistle</a><br>
    ⭐ = Metacritic ≥ 76 or IMDb ≥ 7.7
  </footer>

<script>
const ICONS = {
  metacritic: "https://www.google.com/s2/favicons?domain=metacritic.com&sz=32",
  imdb: "https://www.google.com/s2/favicons?domain=imdb.com&sz=32",
  rotten_tomatoes: "https://www.google.com/s2/favicons?domain=rottentomatoes.com&sz=32",
};

const state = {
  data: null,
  cinema: null,        // null = All
  search: "",
  highlightedOnly: false,
};

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function load(refresh) {
  const btn = $("refresh");
  btn.disabled = true;
  if (refresh) $("content").innerHTML = '<div class="state"><div class="spinner"></div>Refreshing listings…</div>';
  try {
    const url = window.FILMS_URL;
    const res = await fetch(refresh ? url + (url.includes("?") ? "&" : "?") + "refresh=1" : url);
    state.data = await res.json();
  } catch (e) {
    $("content").innerHTML = '<div class="state error">Could not load listings. Try refreshing.</div>';
    btn.disabled = false;
    return;
  }
  btn.disabled = false;
  buildPills();
  render();
}

function buildPills() {
  const cinemas = (state.data && state.data.cinemas) || [];
  const pills = ["All", ...cinemas];
  $("pills").innerHTML = pills.map((name) => {
    const val = name === "All" ? "" : name;
    const active = (state.cinema || "") === val ? " active" : "";
    return `<button class="pill${active}" data-cinema="${esc(val)}">${esc(name)}</button>`;
  }).join("");
  $("pills").querySelectorAll(".pill").forEach((p) => {
    p.addEventListener("click", () => {
      state.cinema = p.dataset.cinema || null;
      buildPills();
      render();
    });
  });
}

function scoreEl(kind, value, url, suffix) {
  if (value == null) {
    return `<span class="score na"><img src="${ICONS[kind]}" alt="">–</span>`;
  }
  const label = esc(value) + (suffix || "");
  const inner = `<img src="${ICONS[kind]}" alt="">${label}`;
  return url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${inner}</a>`
             : `<span class="score">${inner}</span>`;
}

function showtimesHtml(film) {
  const byCinema = {};
  film.showtimes.forEach((s) => {
    if (state.cinema && s.cinema !== state.cinema) return;
    (byCinema[s.cinema] = byCinema[s.cinema] || []).push(s);
  });
  return Object.keys(byCinema).sort().map((cinema) => {
    const byDay = {};
    byCinema[cinema].forEach((s) => {
      const key = s.day + " " + s.date;
      (byDay[key] = byDay[key] || []).push(s);
    });
    const days = Object.keys(byDay).map((day) => {
      const slots = byDay[day].map((s) =>
        `<a class="slot" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(day)} ${esc(s.time)}</a>`
      ).join(" ");
      return slots;
    }).join(" ");
    return `<div class="cine"><span class="cine-name">${esc(cinema)}</span>${days}</div>`;
  }).join("");
}

function bookingHtml(film) {
  const cinemas = Object.keys(film.booking_urls).sort()
    .filter((c) => !state.cinema || c === state.cinema);
  if (cinemas.length === 0) return "";
  if (cinemas.length === 1) {
    return `<div class="booking"><a href="${esc(film.booking_urls[cinemas[0]])}" target="_blank" rel="noopener">Book</a></div>`;
  }
  return `<div class="booking">` + cinemas.map((c) =>
    `<a href="${esc(film.booking_urls[c])}" target="_blank" rel="noopener">Book · ${esc(c)}</a>`
  ).join("") + `</div>`;
}

function cardHtml(film) {
  const meta = [film.director, film.year, film.duration].filter(Boolean).map(esc).join(" · ");
  const sc = film.scores, su = film.score_urls || {};
  const scores = [
    scoreEl("metacritic", sc.metacritic, su.metacritic),
    scoreEl("imdb", sc.imdb, su.imdb),
    scoreEl("rotten_tomatoes", sc.rotten_tomatoes, su.rotten_tomatoes, "%"),
  ].join("");
  return `<div class="card${film.highlighted ? " hl" : ""}">
    <div class="title">${esc(film.title)}${film.highlighted ? '<span class="star">⭐</span>' : ""}${film.considering ? '<span class="badge">Wait and see</span>' : ""}</div>
    ${meta ? `<div class="metaline">${meta}</div>` : ""}
    ${film.logline ? `<div class="logline">${esc(film.logline)}</div>` : ""}
    <div class="showtimes">${showtimesHtml(film)}</div>
    <div class="scores">${scores}</div>
    ${bookingHtml(film)}
  </div>`;
}

function matches(film) {
  if (state.cinema && !film.cinemas.includes(state.cinema)) return false;
  if (state.highlightedOnly && !film.highlighted) return false;
  if (state.search) {
    const q = state.search.toLowerCase();
    const hay = [film.title, film.director, film.logline].filter(Boolean).join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

function renderBanner(data) {
  const notes = data.notes || [];
  // A failed refresh keeps the previous films, so say they may be stale.
  const error = data.error && data.films && data.films.length
    ? `Refresh failed (${data.error}); showing listings from ${data.fetched_at_label || "the last successful load"}.`
    : "";
  const headline = [error, data.warning].filter(Boolean).map(esc).join("<br>");
  if (!headline && notes.length === 0) { $("banner").hidden = true; return; }
  $("banner").innerHTML = headline +
    (notes.length ? "<ul>" + notes.map((n) => `<li>${esc(n)}</li>`).join("") + "</ul>" : "");
  $("banner").hidden = false;
}

function render() {
  const data = state.data;
  if (!data) return;
  renderBanner(data);
  if (data.error && (!data.films || data.films.length === 0)) {
    $("content").innerHTML = `<div class="state error">Couldn't fetch listings: ${esc(data.error)}<br>Try Refresh in a moment.</div>`;
    $("resultCount").textContent = "";
  } else {
    const films = data.films.filter(matches);
    if (films.length === 0) {
      $("content").innerHTML = '<div class="state">No films match your filters.</div>';
    } else {
      $("content").innerHTML = '<div class="grid">' + films.map(cardHtml).join("") + '</div>';
    }
    const total = data.films.length;
    const label = films.length === total ? `${total} films` : `${films.length} of ${total} films`;
    $("resultCount").textContent = label + (state.cinema ? ` · ${state.cinema}` : "");
  }
  $("updated").textContent = data.fetched_at_label ? `Updated ${data.fetched_at_label}` : "";
}

$("search").addEventListener("input", (e) => { state.search = e.target.value.trim(); render(); });
$("hlOnly").addEventListener("change", (e) => { state.highlightedOnly = e.target.checked; render(); });
$("refresh").addEventListener("click", () => load(true));

load(false);
</script>
</body>
</html>
"""
