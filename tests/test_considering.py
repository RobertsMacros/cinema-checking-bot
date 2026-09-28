"""Films on What's On's Wait and see list are flagged and listed first."""

from cinema_digest import considering
from cinema_digest.formatter import format_digest, format_digest_html
from cinema_digest.models import Film, Scores


def _films():
    return [
        Film(title="Big Hit", year=2026, scores=Scores(metacritic=90)),
        Film(title="The Waiting Film", year=2026, scores=Scores(metacritic=81)),
        Film(title="Unscored", year=2026),
        Film(title="Remake", year=1969),
    ]


def test_load_handles_missing_and_bad_values():
    assert considering.load("") == []
    assert considering.load("not json") == []
    assert considering.load('{"title": "x"}') == []
    assert considering.load('[{"title": "A"}, {"nope": 1}, {"title": ""}]') == [{"title": "A"}]


def test_mark_matches_title_and_year():
    films = _films()
    n = considering.mark(films, [
        {"title": "Waiting Film", "year": "2026", "bar": 75},   # article dropped: still matches
        {"title": "Unscored", "year": None, "bar": 80},
        {"title": "Remake", "year": "2026"},                   # same title, other year: not flagged
    ])
    assert n == 2
    assert films[1].considering == {"bar": 75}
    assert films[2].considering == {"bar": 80}
    assert films[3].considering is None


def test_labels():
    films = _films()
    considering.mark(films, [{"title": "The Waiting Film", "bar": 85}, {"title": "Unscored"}])
    assert considering.label(films[1]) == "On your Wait and see list: Metacritic 81, under your 85"
    assert considering.label(films[2]) == "On your Wait and see list: no Metacritic score yet (you wanted 75)"
    films[1].considering = {"bar": 75}
    assert considering.label(films[1]) == "On your Wait and see list: Metacritic 81 clears your 75"
    assert considering.label(films[0]) is None


def test_considered_films_come_first_in_both_formats():
    films = _films()
    considering.mark(films, [{"title": "The Waiting Film", "year": "2026", "bar": 75}])
    text = format_digest(films)
    assert text.index("The Waiting Film") < text.index("Big Hit")
    assert "[On your Wait and see list: Metacritic 81 clears your 75]" in text
    html = format_digest_html(films)
    assert html.index("The Waiting Film") < html.index("Big Hit")
    assert "Metacritic 81 clears your 75" in html
