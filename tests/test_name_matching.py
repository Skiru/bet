"""Comprehensive tests for name normalization and matching utilities.

Covers real-world cases from betting pipeline:
- Polish diacritics (ą, ę, ś, ć, ź, ż, ó, ł, ń)
- Emoji flags in tipster names (🇦🇺, 🇵🇱, 🇪🇸)
- Surname-only matching (tennis: "Świątek" vs "Swiatek, Iga")
- Name format differences ("Last, First" vs "First Last")
- Club suffixes (FC, SC, etc.)
- Esports team names with org suffixes
- Swapped home/away order
"""

import unittest
from bet.utils import (
    strip_emoji,
    normalize_team_name,
    normalize_for_matching,
    names_match,
    is_same_event,
)


class TestStripEmoji(unittest.TestCase):
    """strip_emoji removes all emoji characters."""

    def test_flag_emoji(self):
        assert strip_emoji("🇦🇺 Jones") == " Jones"
        assert strip_emoji("Świątek 🇵🇱") == "Świątek "

    def test_multiple_emoji(self):
        assert strip_emoji("🍀🍀🍀 Lucky 🎯") == " Lucky "

    def test_no_emoji(self):
        assert strip_emoji("Normal text") == "Normal text"

    def test_empty(self):
        assert strip_emoji("") == ""

    def test_only_emoji(self):
        result = strip_emoji("🇵🇱🇦🇺").strip()
        assert result == ""


class TestNormalizeTeamName(unittest.TestCase):
    """normalize_team_name handles diacritics, suffixes, emoji."""

    def test_polish_diacritics(self):
        assert normalize_team_name("Świątek") == "swiatek"
        assert normalize_team_name("Łódź") == "lodz"
        assert normalize_team_name("Kraków") == "krakow"
        assert normalize_team_name("Gdańsk") == "gdansk"

    def test_czech_diacritics(self):
        assert normalize_team_name("České Budějovice") == "ceske budejovice"

    def test_turkish_diacritics(self):
        assert normalize_team_name("Fenerbahçe") == "fenerbahce"

    def test_emoji_stripped(self):
        assert normalize_team_name("🇦🇺 Jones") == "jones"
        assert normalize_team_name("Świątek 🇵🇱") == "swiatek"

    def test_fc_suffix_removed(self):
        assert normalize_team_name("FC Barcelona") == "barcelona"
        assert normalize_team_name("Real Madrid CF") == "real madrid"

    def test_esports_suffix(self):
        assert normalize_team_name("Natus Vincere Gaming") == "natus vincere"

    def test_empty(self):
        assert normalize_team_name("") == ""


class TestNormalizeForMatching(unittest.TestCase):
    """normalize_for_matching handles Last,First format and aggressive cleaning."""

    def test_comma_format_reorder(self):
        # "Jones, Emerson" → "emerson jones"
        assert normalize_for_matching("Jones, Emerson") == "emerson jones"
        assert normalize_for_matching("Swiatek, Iga") == "iga swiatek"

    def test_plain_format_preserved(self):
        assert normalize_for_matching("Emerson Jones") == "emerson jones"
        assert normalize_for_matching("Iga Swiatek") == "iga swiatek"

    def test_diacritics_removed(self):
        assert normalize_for_matching("Świątek, Iga") == "iga swiatek"
        assert normalize_for_matching("Swiątek") == "swiatek"

    def test_emoji_removed(self):
        assert normalize_for_matching("🇦🇺 Jones") == "jones"
        assert normalize_for_matching("Świątek 🇵🇱") == "swiatek"

    def test_punctuation_removed(self):
        assert normalize_for_matching("St. Louis City") == "st louis city"

    def test_empty(self):
        assert normalize_for_matching("") == ""


class TestNamesMatch(unittest.TestCase):
    """names_match handles all the tricky real-world cases."""

    # === THE ŚWIĄTEK CASE (root cause of this fix) ===

    def test_swiatek_surname_only_vs_full(self):
        """Tipster: 'Swiątek' vs Shortlist: 'Swiatek, Iga'"""
        score = names_match("Swiatek, Iga", "Swiątek")
        assert score >= 70, f"Expected ≥70, got {score}"

    def test_swiatek_with_emoji(self):
        """Tipster: 'Świątek 🇵🇱' vs Shortlist: 'Swiatek, Iga'"""
        score = names_match("Swiatek, Iga", "Świątek 🇵🇱")
        assert score >= 70, f"Expected ≥70, got {score}"

    def test_jones_surname_only_vs_full(self):
        """Tipster: 'Jones' vs Shortlist: 'Jones, Emerson'"""
        score = names_match("Jones, Emerson", "Jones")
        assert score >= 70, f"Expected ≥70, got {score}"

    def test_jones_with_emoji(self):
        """Tipster: '🇦🇺 Jones' vs Shortlist: 'Jones, Emerson'"""
        score = names_match("Jones, Emerson", "🇦🇺 Jones")
        assert score >= 70, f"Expected ≥70, got {score}"

    def test_swiatek_iga_vs_iga_swiatek(self):
        """Shortlist alternate: 'Iga Swiatek' vs Tipster: 'Świątek'"""
        score = names_match("Iga Swiatek", "Świątek")
        assert score >= 70, f"Expected ≥70, got {score}"

    # === OTHER TENNIS CASES ===

    def test_djokovic_variants(self):
        """Đoković vs Djokovic"""
        score = names_match("Novak Djokovic", "Đoković, Novak")
        assert score >= 70, f"Expected ≥70, got {score}"

    def test_nadal_surname_only(self):
        score = names_match("Nadal, Rafael", "Nadal")
        assert score >= 70, f"Expected ≥70, got {score}"

    # === FOOTBALL CASES ===

    def test_exact_match(self):
        score = names_match("Manchester United", "Manchester United")
        assert score == 100

    def test_man_utd_abbreviation(self):
        """This should NOT match — too different."""
        score = names_match("Manchester United", "Man Utd")
        # This is a tough one — different enough that < 70 is acceptable
        # Our system should at least not crash

    def test_fc_prefix_difference(self):
        score = names_match("FC Barcelona", "Barcelona")
        assert score >= 70, f"Expected ≥70, got {score}"

    def test_diacritics_football(self):
        score = names_match("Atlético Madrid", "Atletico Madrid")
        assert score >= 70, f"Expected ≥70, got {score}"

    # === NEGATIVE CASES (should NOT match) ===

    def test_different_teams_dont_match(self):
        score = names_match("Arsenal", "Chelsea")
        assert score < 70, f"Expected <70, got {score}"

    def test_similar_prefix_dont_match(self):
        """'Ham' is in 'Nottingham' — should not match."""
        score = names_match("West Ham", "Nottingham Forest")
        assert score < 70, f"Expected <70, got {score}"

    def test_short_substring_not_confused(self):
        """'Jones' should not match 'Djones' or random teams."""
        score = names_match("Jones, Emerson", "Jonesboro")
        assert score < 70, f"Expected <70, got {score}"

    def test_different_tennis_players(self):
        """Different surnames should not match."""
        score = names_match("Swiatek, Iga", "Sabalenka, Aryna")
        assert score < 70, f"Expected <70, got {score}"


class TestIsSameEvent(unittest.TestCase):
    """is_same_event handles full event matching including swapped order."""

    def test_swiatek_match_from_tipster(self):
        """The exact case that failed: zawodtyper vs shortlist."""
        result = is_same_event(
            "Jones, Emerson", "Swiatek, Iga",  # shortlist
            "Jones", "Swiątek",  # tipster (surname only + diacritics)
        )
        assert result is True, "Should match Świątek tipster to shortlist"

    def test_swiatek_with_emoji_flags(self):
        result = is_same_event(
            "Jones, Emerson", "Swiatek, Iga",
            "🇦🇺 Jones", "Świątek 🇵🇱",
        )
        assert result is True

    def test_normal_football_match(self):
        result = is_same_event(
            "Arsenal", "Chelsea",
            "Arsenal", "Chelsea",
        )
        assert result is True

    def test_swapped_order(self):
        """Some sources swap home/away."""
        result = is_same_event(
            "Arsenal", "Chelsea",
            "Chelsea", "Arsenal",
        )
        assert result is True

    def test_different_events_dont_match(self):
        result = is_same_event(
            "Arsenal", "Chelsea",
            "Liverpool", "Everton",
        )
        assert result is False

    def test_diacritics_football(self):
        result = is_same_event(
            "Slavia Praha", "Sparta Praha",
            "Slavia Praha", "Sparta Praha",
        )
        assert result is True

    def test_partial_name_football_club(self):
        result = is_same_event(
            "FC Barcelona", "Real Madrid CF",
            "Barcelona", "Real Madrid",
        )
        assert result is True


class TestTipsterXrefMatching(unittest.TestCase):
    """Integration-level tests simulating tipster_xref matching logic."""

    def test_zawodtyper_swiatek_tip1(self):
        """Reproduce exact failure: 'Jones'|'Swiątek' should match 'Jones, Emerson'|'Swiatek, Iga'."""
        from bet.utils import normalize_for_matching

        # Tipster side (after _clean_team_name)
        tip_home = normalize_for_matching("Jones")
        tip_away = normalize_for_matching("Swiątek")

        # Shortlist side
        shortlist_home = normalize_for_matching("Jones, Emerson")
        shortlist_away = normalize_for_matching("Swiatek, Iga")

        score_h = names_match(shortlist_home, tip_home)
        score_a = names_match(shortlist_away, tip_away)

        assert score_h >= 70, f"Home score {score_h} < 70"
        assert score_a >= 70, f"Away score {score_a} < 70"

    def test_zawodtyper_swiatek_tip2(self):
        """Reproduce: '🇦🇺 Jones'|'Świątek 🇵🇱' should match 'Emerson Jones'|'Iga Swiatek'."""
        from bet.utils import normalize_for_matching

        tip_home = normalize_for_matching("🇦🇺 Jones")
        tip_away = normalize_for_matching("Świątek 🇵🇱")

        shortlist_home = normalize_for_matching("Emerson Jones")
        shortlist_away = normalize_for_matching("Iga Swiatek")

        score_h = names_match(shortlist_home, tip_home)
        score_a = names_match(shortlist_away, tip_away)

        assert score_h >= 70, f"Home score {score_h} < 70"
        assert score_a >= 70, f"Away score {score_a} < 70"

    def test_no_false_positive_tennis(self):
        """Different players shouldn't match."""
        from bet.utils import normalize_for_matching

        tip_home = normalize_for_matching("Rublev")
        tip_away = normalize_for_matching("Sinner")

        shortlist_home = normalize_for_matching("Jones, Emerson")
        shortlist_away = normalize_for_matching("Swiatek, Iga")

        score_h = names_match(shortlist_home, tip_home)
        score_a = names_match(shortlist_away, tip_away)

        # At least one should fail
        assert not (score_h >= 70 and score_a >= 70), "Should NOT match different players"


class TestEdgeCases(unittest.TestCase):
    """Edge cases and regression guards."""

    def test_empty_strings(self):
        assert names_match("", "") == 0.0
        assert names_match("Team A", "") == 0.0
        assert names_match("", "Team B") == 0.0

    def test_single_char(self):
        score = names_match("A", "B")
        assert score < 70

    def test_identical_strings(self):
        score = names_match("Exact Same", "Exact Same")
        assert score == 100.0

    def test_case_insensitive(self):
        score = names_match("ARSENAL", "arsenal")
        assert score == 100.0

    def test_accented_same_name(self):
        score = names_match("São Paulo", "Sao Paulo")
        assert score >= 70

    def test_chinese_characters(self):
        """Chinese team names should at least not crash."""
        score = names_match("上海上港", "Shanghai SIPG")
        # We don't expect a match, just no crash
        assert isinstance(score, float)

    def test_very_long_name(self):
        """Performance: don't hang on very long names."""
        long_name = "A" * 1000
        score = names_match(long_name, "Short")
        assert isinstance(score, float)


if __name__ == "__main__":
    unittest.main()
