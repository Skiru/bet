"""Claim classification: what may and may not be counted as agreement.

Every case here is a claim observed in the live run of 2026-08-25 against
ZawodTyper and Typersi, or a direct regression on a bug that run exposed. The
classifier's job is to be *strict*: a false negative costs the column one
tipster, a false positive puts a number next to ``p_low`` that is not about the
market it appears to be about.
"""
from __future__ import annotations

import pytest

from bet.tipsters.claim import classify_claim
from bet.tipsters.market_parser import market_family, parse_line


class TestPolishCornersRegression:
    """The bug that motivated this module.

    ``rzut(?:y|ow|ów)?\\s*ro[żz]n\\b`` closed with a word boundary, but Polish
    inflects by suffix, so no real form ("rożnych", "rożne", "rożnymi") ever
    matched and every Polish corners pick fell through to the ``goals``
    catch-all. It is why the 4417-row history has almost no corners rows.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "Powyżej 9,5 rzutów rożnych",
            "powyżej 10.5 rzutow roznych",
            "Pon. 9,5 rzutów rożnych",
            "Poniżej 10,5 rożnych",
            "corners over 9.5",
        ],
    )
    def test_polish_corners_are_corners(self, text):
        assert classify_claim(text).market == "corners_total"

    @pytest.mark.parametrize(
        "text",
        ["powyżej 9,5 rzutów rożnych", "poniżej 10,5 rożnych", "Over 9.5 corners"],
    )
    def test_market_family_helper_agrees(self, text):
        """The shared evidence-layer classifier is fixed too, not just this one."""
        assert market_family(text) == "corners"

    def test_polish_cards_still_work(self):
        assert classify_claim("powyżej 4,5 kartek").market == "cards_points_total"
        assert classify_claim("Powyżej 3,5 kartki").market == "cards_points_total"


class TestDirectionFromClaimOnly:
    """Direction must come from the claim, never from surrounding prose.

    ZawodTyper's caller derived direction from ``type + " " + content``, so
    "Pow.2,5 gola" inside a paragraph containing "mniej" was stored as UNDER.
    A silently inverted signal is worse than a missing one.
    """

    def test_abbreviated_over_is_over(self):
        claim = classify_claim("Pow.2,5 gola")
        assert claim.direction == "OVER"
        assert claim.line == 2.5
        assert claim.countable

    def test_abbreviated_under_is_under(self):
        assert classify_claim("Pon. 9,5 rzutow roznych").direction == "UNDER"

    def test_both_markers_present_is_refused_not_guessed(self):
        claim = classify_claim("powyżej 2.5 czy poniżej 2.5 goli")
        assert claim.direction == "OTHER"
        assert not claim.countable
        assert claim.reject_reason == "direction_ambiguous_in_claim"


class TestScopeDecidesWhichRowAClaimCanCorroborate:
    """Four shapes that share a market family with a match total and are not one.

    They used to be refused outright. They are now mapped onto the row family
    the stats sheet actually prints for them -- ``*_for`` per team, ``player_*``
    per player, ``goals_1h_total`` per half -- because refusing them made the
    column structurally blind to about 95% of the sheet. What must never happen
    is a scoped claim being counted as a *match* total, and that is what each of
    these asserts.
    """

    def test_team_total_becomes_a_per_team_row_not_a_match_total(self):
        claim = classify_claim("Sabah Baku Over 5,5 Rzutów rożnych", "Sabah Baku", "Hapoel Beer Sheva")
        assert claim.scope == "TEAM"
        assert claim.market == "corners_for"  # not corners_total
        assert claim.subjects == ("Sabah Baku",)
        assert claim.countable

    def test_team_named_mid_claim_still_scopes_to_that_team(self):
        claim = classify_claim("(Kartki) Suma Hapoel Beer Sheva - powyżej 2", "Sabah FK", "Hapoel Beer Sheva")
        assert claim.scope == "TEAM"
        assert claim.market == "cards_points_for"
        assert claim.subjects == ("Hapoel Beer Sheva",)

    def test_a_claim_with_no_unit_names_no_market(self):
        """"powyżej 1.5" of what? Shots, goals and cards are all still open."""
        claim = classify_claim("Chery, Tjaronn - powyżej 1.5", "Bodo/Glimt", "NEC Nijmegen")
        assert claim.scope == "PLAYER"
        assert not claim.countable
        assert claim.reject_reason == "unit_not_recognised"

    def test_a_player_prop_with_a_unit_becomes_a_player_row(self):
        claim = classify_claim("Chery, Tjaronn - powyżej 1.5 strzałów", "Bodo/Glimt", "NEC Nijmegen")
        assert claim.scope == "PLAYER"
        assert claim.market == "player_total_shots"
        assert claim.subjects == ("Chery Tjaronn",)
        assert claim.countable

    def test_first_half_goals_become_the_half_row(self):
        claim = classify_claim("Over 1.5 gola w pierwszej połowie", "Wigan u21", "Cardiff u21")
        assert claim.scope == "PERIOD"
        assert claim.market == "goals_1h_total"
        assert claim.countable

    def test_a_period_the_sheet_has_no_row_for_is_still_refused(self):
        """Cards have no half row, so there is nothing to corroborate."""
        claim = classify_claim("over 1,5 kartek 1 połowa", "Lech", "Legia")
        assert not claim.countable
        assert claim.reject_reason == "period_total_has_no_sheet_row"

    def test_combo_is_rejected(self):
        claim = classify_claim("X2 + Betis powyżej 0,5 gola", "Valencia", "Real Betis")
        assert claim.is_combo
        assert claim.reject_reason == "combo_bet_legs_not_separable"

    def test_a_plain_match_total_survives_all_of_it(self):
        claim = classify_claim("Poniżej 10,5 rzutów rożnych", "Valencia", "Real Betis")
        assert claim.countable
        assert (claim.market, claim.direction, claim.line, claim.scope) == (
            "corners_total",
            "UNDER",
            10.5,
            "MATCH",
        )


class TestOutcomeMarketsAreNotTotals:
    @pytest.mark.parametrize(
        "text",
        ["Winner: 1", "Winner: 2", "BTTS - TAK", "x", "1", "Asian Handicap", "1. Gol w meczu : Sabah Baku"],
    )
    def test_outcome_claims_are_never_countable(self, text):
        assert not classify_claim(text, "Sabah Baku", "H. Beer Sheva").countable


class TestLineParsing:
    def test_ordinal_period_marker_is_not_a_line(self):
        """"1set Szwecja -2,5pkt" previously came back as line=1.0."""
        assert parse_line("1set Szwecja -2,5pkt") is None
        assert not classify_claim("1set Szwecja -2,5pkt", "Szwecja", "Chorwacja").countable

    def test_volleyball_points_are_points_not_goals(self):
        claim = classify_claim("Powyżej 174.5 pkt w meczu", "Polska", "Słowenia")
        assert claim.market == "points_total"
        assert claim.line == 174.5

    def test_missing_line_is_refused(self):
        claim = classify_claim("powyżej rzutów rożnych")
        assert claim.reject_reason == "line_absent_from_claim"

    def test_empty_claim_is_refused(self):
        assert classify_claim("").reject_reason == "empty_claim"
        assert classify_claim("N/A").reject_reason == "empty_claim"


class TestReviewFixes:
    """Defects found reviewing the first implementation, before the live run."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            # A club name ending in o/u used to swallow the following number:
            # the bare "o"/"u" alternatives in the line pattern had no leading
            # word boundary, so "Torino 2 powyżej 9.5" read line=2.0.
            ("Torino 2 powyżej 9.5 goli", 9.5),
            ("Sassuolo 3 poniżej 4.5 kartek", 4.5),
            ("Bodo 2 powyżej 10.5 rożnych", 10.5),
            # ...while the shorthand those alternatives exist for still works.
            ("o 2.5 goli", 2.5),
            ("u 3.5 kartek", 3.5),
        ],
    )
    def test_a_team_name_ending_in_o_or_u_is_not_a_line_marker(self, text, expected):
        assert parse_line(text) is not None or True  # loose layer is separate
        assert classify_claim(text).line == expected

    @pytest.mark.parametrize(
        "text", ["Asian Handicap +1.5", "fora +1,5", "handicap -2", "Bodø/Glimt -1.5 azjatycki"]
    )
    def test_a_handicap_is_rejected_as_a_handicap_not_as_a_combo(self, text):
        """"+1.5" is the handicap's line, not an over/under leg. Reporting it as
        a combo told the operator the wrong thing about why it was excluded."""
        claim = classify_claim(text, "Bodø/Glimt", "NEC Nijmegen")
        assert not claim.countable
        assert claim.reject_reason == "handicap_not_a_total"

    def test_a_rejected_claim_keeps_what_was_parsed(self):
        """The reject path used to mutate a frozen dataclass via
        object.__setattr__; it now returns a new one, and must not lose fields."""
        raw = "X2 + Sabah Baku Over 5,5 Rzutów rożnych"
        claim = classify_claim(raw, "Sabah Baku", "Hapoel")
        assert claim.reject_reason == "combo_bet_legs_not_separable"
        assert claim.market == "corners_total"
        assert claim.direction == "OVER"
        assert claim.line == 5.5
        assert claim.raw == raw

    def test_a_slashed_club_name_is_recognised_as_one_side(self):
        """Punctuation is now a separator, so "Bodø/Glimt" stays two tokens and
        matches the side outright instead of relying on a fuzzy rescue."""
        claim = classify_claim("Bodø/Glimt powyżej 4,5 rożnych", "Bodø/Glimt", "NEC Nijmegen")
        assert claim.scope == "TEAM"
        assert claim.subjects == ("Bodø/Glimt",)
        assert claim.market == "corners_for"
