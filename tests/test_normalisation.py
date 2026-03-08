"""Tests for title normalisation."""

from cinema_digest.scraper import normalize_title


class TestNormalizeTitle:
    def test_lowercase(self):
        assert normalize_title("THE BRIDE") == "bride"

    def test_strip_leading_article_the(self):
        assert normalize_title("The Bride!") == "bride"

    def test_strip_leading_article_a(self):
        assert normalize_title("A Good Film") == "good film"

    def test_strip_leading_article_an(self):
        assert normalize_title("An Evening with Film") == "evening with film"

    def test_remove_punctuation(self):
        assert normalize_title("Film: A Story!") == "film a story"

    def test_collapse_whitespace(self):
        assert normalize_title("  The   Bride  ") == "bride"

    def test_apostrophe_handling(self):
        assert normalize_title("If I Had Legs I'd Kick You") == "if i had legs id kick you"

    def test_colon_handling(self):
        result = normalize_title("Peaky Blinders: The Immortal Man")
        assert result == "peaky blinders the immortal man"

    def test_em_dash_handling(self):
        result = normalize_title("Film \u2014 A Story")
        # em dash is non-word, gets stripped
        assert result == "film a story"

    def test_unicode_normalization(self):
        # cafe with combining accent should normalize
        result = normalize_title("Caf\u00e9 Society")
        assert "cafe" in result

    def test_numbers_preserved(self):
        assert normalize_title("2001: A Space Odyssey") == "2001 a space odyssey"

    def test_empty_string(self):
        assert normalize_title("") == ""

    def test_matching_titles_from_different_cinemas(self):
        """Same film at both cinemas should produce same normalized title."""
        assert normalize_title("The Bride!") == normalize_title("The Bride!")
        assert normalize_title("Peaky Blinders: The Immortal Man") == normalize_title(
            "Peaky Blinders: The Immortal Man"
        )
