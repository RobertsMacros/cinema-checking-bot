"""Event wrappers around a film's title are removed before score lookups.

Seen in the 13 Nov 2026 run: "MUBI FEST LIVE: A LONG WINTER + Q&A" found
nothing on OMDb. Real titles that contain a colon must be left alone.
"""

import pytest

from cinema_digest.enrich import _clean_title_for_search


@pytest.mark.parametrize(
    "listed, searched",
    [
        ("MUBI FEST LIVE: A LONG WINTER + Q&A", "A LONG WINTER"),
        ("Sentimental Value + Q&A with Joachim Trier", "Sentimental Value"),
        ("Hamnet + Intro", "Hamnet"),
        ("Hamnet + Recorded Q&A", "Hamnet"),
        ("Preview: Hamnet", "Hamnet"),
        ("Exclusive Preview: Hamnet", "Hamnet"),
        ("Parent & Baby Screening: Wicked: For Good", "Wicked: For Good"),
        ("Toddler Time: The Gruffalo", "The Gruffalo"),
        ("Kids' Club: Shaun the Sheep: The Beast of Mossy Bottom", "Shaun the Sheep: The Beast of Mossy Bottom"),
        ("Silver Screen: Fjord", "Fjord"),
        ("Dune (2026)", "Dune"),
    ],
)
def test_event_wrappers_are_removed(listed, searched):
    assert _clean_title_for_search(listed) == searched


@pytest.mark.parametrize(
    "title",
    [
        "Mission: Impossible",
        "Ghosts: The Possession of Button House",
        "Shaun the Sheep: The Beast of Mossy Bottom",
        "National Theatre Live: Golden Boy",  # a stage recording, listed as such on OMDb
        "Black Is Boundless: Black Joy",
        "Romeo + Juliet",
    ],
)
def test_real_titles_are_left_alone(title):
    assert _clean_title_for_search(title) == title
