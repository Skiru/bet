"""Player props settle against a box score, and are priced off a wider basis.

Both halves of the 2026-09-06 change, and they are one change: props could not
be settled, so nobody could see that they were the one family the bar was wrong
about. See ``settle.player_value`` and ``bet_builder_draft.bar_basis_for_row``.
"""
from __future__ import annotations

import pytest

from bet.simple_stats.bet_builder_draft import (
    BAR_REASON_INTERVAL_MID,
    bar_basis_for_row,
    bar_input,
)
from bet.simple_stats.settle import player_value, settle_row

# Philadelphia Union v CF Montréal, 2026-09-05, as bzzoiro reported it. Owusu
# and Westfield are the two rows the operator actually had on a slip that day.
ACTUALS = {
    "home": {"shots_on_target_for": 6.0},
    "away": {"shots_on_target_for": 3.0},
    "total": {"shots_on_target_total": 9.0, "fouls_total": 23.0},
    "players": {
        "9595": {
            "minutes_played": 90.0,
            "player_total_shots": 3.0,
            "player_shots_on_target": 2.0,
            "player_fouls": 0.0,
        },
        "41207": {"minutes_played": 90.0, "player_fouls": 3.0},
        "77777": {"minutes_played": 0.0, "player_fouls": 0.0},
    },
}


class TestPlayerValue:
    def test_reads_the_box_score_by_provider_id(self) -> None:
        assert player_value(ACTUALS, "player_total_shots", "9595") == 3.0
        assert player_value(ACTUALS, "player_shots_on_target", "9595") == 2.0

    def test_an_integer_id_is_accepted(self) -> None:
        # ``subject_id`` is a string on the coupon and an int in some fixtures;
        # a settlement must not turn on which.
        assert player_value(ACTUALS, "player_fouls", 41207) == 3.0

    def test_a_player_who_did_not_come_on_is_not_a_loss(self) -> None:
        # An unused substitute's box score is a full row of zeroes. Settling it
        # would score every OVER as a loss and every UNDER as a win, off a
        # player whose bet the book voided.
        assert player_value(ACTUALS, "player_fouls", "77777") is None

    def test_a_player_absent_from_the_box_score_is_not_a_loss(self) -> None:
        assert player_value(ACTUALS, "player_fouls", "00000") is None

    def test_no_id_means_no_settlement_even_though_a_name_would_resolve(self) -> None:
        # The one rule that must not soften: two players in a fixture can share
        # a surname, and a wrong box score looks exactly like measured evidence.
        assert player_value(ACTUALS, "player_fouls", None) is None
        assert player_value(ACTUALS, "player_fouls", "") is None

    def test_a_market_the_provider_did_not_report_is_a_gap(self) -> None:
        assert player_value(ACTUALS, "player_tackles", "9595") is None


class TestSettleRowRoutesTheFamily:
    def test_a_prop_settles_against_the_player_and_not_his_team(self) -> None:
        # Owusu had 2 shots on target; his side had 6 and the match 9. Only the
        # first of those three numbers may decide this row.
        assert settle_row(
            market="player_shots_on_target", line=0.5, direction="OVER",
            actuals=ACTUALS, player_id="9595",
        ) == ("WON", 2.0)
        assert settle_row(
            market="player_shots_on_target", line=4.5, direction="OVER",
            actuals=ACTUALS, player_id="9595",
        ) == ("LOST", 2.0)

    def test_a_prop_without_an_id_is_no_data_not_a_team_figure(self) -> None:
        outcome, actual = settle_row(
            market="player_fouls", line=0.5, direction="OVER",
            actuals=ACTUALS, team_name="Philadelphia Union",
            home_team="Philadelphia Union", away_team="CF Montréal",
        )
        assert (outcome, actual) == ("NO_DATA", None)

    def test_team_and_match_markets_are_untouched(self) -> None:
        assert settle_row(
            market="shots_on_target_total", line=11.5, direction="UNDER",
            actuals=ACTUALS,
        ) == ("WON", 9.0)
        assert settle_row(
            market="shots_on_target_for", line=4.5, direction="OVER",
            actuals=ACTUALS, team_name="Philadelphia Union",
            home_team="Philadelphia Union", away_team="CF Montréal",
        ) == ("WON", 6.0)


class _Row:
    def __init__(self, *, p_central, p_low, sample_size, hits,
                 player_id=None, player_name=None):
        self.p_central = p_central
        self.p_low = p_low
        self.sample_size = sample_size
        self.hits = hits
        self.player_id = player_id
        self.player_name = player_name


# Prince Owusu, shots on target over 0.5, as the 2026-09-05 file shipped it.
PROP = _Row(p_central=0.8169, p_low=0.5650, sample_size=9, hits=8,
            player_id="9595", player_name="Prince Owusu")
# Bragantino v Bahia, shots on target under 11.5, same file.
TEAM = _Row(p_central=0.8560, p_low=0.6540, sample_size=21, hits=18)


class TestBarBasisIsPerFamily:
    def test_a_prop_is_priced_off_the_interval_midpoint(self) -> None:
        probability, reason = bar_input(PROP, "p_central")
        assert probability == pytest.approx((0.8169 + 0.5650) / 2)
        assert reason == BAR_REASON_INTERVAL_MID

    def test_a_team_row_keeps_p_central(self) -> None:
        assert bar_input(TEAM, "p_central") == (0.8560, None)

    def test_the_midpoint_raises_the_price_a_prop_must_beat(self) -> None:
        # The point of the change: Owusu at 1.48 cleared a 1.35 bar on
        # p_central and does not clear the bar on the midpoint.
        margin = 1.10
        assert (1.0 / 0.8169) * margin < 1.48 < (1.0 / bar_input(PROP, "p_central")[0]) * margin

    def test_an_explicit_p_low_arm_is_never_overridden(self) -> None:
        # ``--bar-basis p_low`` is the comparison baseline; a family override
        # that quietly loosened it would make every arm comparison a lie.
        assert bar_input(PROP, "p_low") == (0.5650, None)
        assert bar_basis_for_row(PROP, "p_low") == "p_low"

    def test_a_row_identified_only_by_player_name_still_counts_as_a_prop(self) -> None:
        named = _Row(p_central=0.90, p_low=0.60, sample_size=10, hits=10,
                     player_name="Somebody")
        assert bar_basis_for_row(named, "p_central") == "p_interval_mid"

    def test_the_small_sample_cap_still_binds_under_the_midpoint(self) -> None:
        # A thin sample cannot claim more than its own lower bound, whichever
        # basis it was routed to.
        thin = _Row(p_central=0.99, p_low=0.40, sample_size=4, hits=4,
                    player_id="1")
        probability, _ = bar_input(thin, "p_central")
        assert probability <= 0.40


class TestCrossMatchAccumulator:
    """``bet_builder_draft.accumulator`` -- the arithmetic the file was missing."""

    def test_the_joint_is_the_product_and_the_bar_is_the_margin_over_it(self) -> None:
        from bet.simple_stats.bet_builder_draft import accumulator

        acc = accumulator([0.8, 0.75], [1.50, 1.60], 1.10)
        assert acc is not None
        assert acc.probability == pytest.approx(0.60)
        assert acc.required_odds == pytest.approx(1.10 / 0.60, abs=1e-4)
        # A book prices a cross-match parlay as the product of its legs, so
        # unlike a Bet Builder this one *is* computable.
        assert acc.offered_odds == pytest.approx(2.40)
        assert acc.surplus == pytest.approx(2.40 - 1.10 / 0.60, abs=1e-4)

    def test_the_2026_09_05_slip_reads_as_a_one_in_five(self) -> None:
        # The five legs the operator actually combined, at the pipeline's own
        # shrunk probabilities. Each was worth its price; the slip was not a
        # coin flip, and nothing in the file said so.
        from bet.simple_stats.bet_builder_draft import accumulator

        acc = accumulator(
            [0.785, 0.693, 0.699, 0.646, 0.793],
            [1.42, 1.52, 1.59, 1.78, 1.41],
            1.10,
        )
        assert acc is not None
        assert acc.probability == pytest.approx(0.195, abs=0.002)
        assert acc.offered_odds == pytest.approx(8.61, abs=0.02)
        # Positive expectation and still a losing bet four times in five.
        assert acc.surplus is not None and acc.surplus > 0

    def test_a_single_leg_is_not_an_accumulator(self) -> None:
        from bet.simple_stats.bet_builder_draft import accumulator

        assert accumulator([0.8], [1.5], 1.10) is None

    def test_an_unpriced_leg_leaves_the_screen_price_unknown(self) -> None:
        from bet.simple_stats.bet_builder_draft import accumulator

        acc = accumulator([0.8, 0.75], [1.50, None], 1.10)
        assert acc is not None
        assert acc.offered_odds is None and acc.surplus is None
        # The bar is still computable: it needs only our own probabilities.
        assert acc.required_odds == pytest.approx(1.10 / 0.60, abs=1e-4)

    def test_an_impossible_probability_is_refused_rather_than_divided_by(self) -> None:
        from bet.simple_stats.bet_builder_draft import accumulator

        assert accumulator([0.8, 0.0], [1.5, 2.0], 1.10) is None


class TestUnreviewedScopeSibling:
    """An analyst objection to the estimand lands on one scope; the other ships."""

    def _row(self, market, event_id="e1"):
        from bet.simple_stats.contracts import StatsSheetRow
        return StatsSheetRow(
            event_id=event_id, sport="football", market=market, line=9.5,
            direction="UNDER", hits=16, sample_size=20, pushes=0, hit_rate=0.8,
            p_low=0.594, p_central=0.730, mean=7.2, median=6.5, dispersion=2.97,
            confidence="HIGH", data_quality="READY",
            cross_provider_agreement="SINGLE_SOURCE", corroborated_matches=0,
            sources=["bzzoiro"],
        )

    def _veto(self, market, event_id="e1"):
        from bet.simple_stats.coupons import AnalystVeto
        return AnalystVeto(
            event_id=event_id, market=market, action="DOWNGRADE",
            reason_class="SAMPLE_NOT_REPRESENTATIVE", reason="x",
        )

    def test_the_match_total_is_flagged_when_the_team_row_was_struck(self) -> None:
        # The live 2026-09-06 Corinthians case: four *_for markets downgraded,
        # shots_on_target_total left unmarked and the only bettable row there.
        from bet.simple_stats.bet_builder_draft import VetoIndex
        from bet.simple_stats.coupons import unreviewed_sibling_note

        vetoes = [self._veto("shots_on_target_for")]
        note = unreviewed_sibling_note(
            self._row("shots_on_target_total"), VetoIndex(vetoes), vetoes
        )
        assert note is not None and "shots_on_target_for" in note

    def test_a_row_the_analyst_did_strike_is_not_flagged_twice(self) -> None:
        from bet.simple_stats.bet_builder_draft import VetoIndex
        from bet.simple_stats.coupons import unreviewed_sibling_note

        vetoes = [self._veto("shots_on_target_for"),
                  self._veto("shots_on_target_total")]
        assert unreviewed_sibling_note(
            self._row("shots_on_target_total"), VetoIndex(vetoes), vetoes
        ) is None

    def test_a_veto_on_another_fixture_does_not_reach_across(self) -> None:
        from bet.simple_stats.bet_builder_draft import VetoIndex
        from bet.simple_stats.coupons import unreviewed_sibling_note

        vetoes = [self._veto("shots_on_target_for", event_id="e2")]
        assert unreviewed_sibling_note(
            self._row("shots_on_target_total"), VetoIndex(vetoes), vetoes
        ) is None

    def test_a_market_with_no_sibling_scope_is_left_alone(self) -> None:
        from bet.simple_stats.bet_builder_draft import VetoIndex, scope_sibling
        from bet.simple_stats.coupons import unreviewed_sibling_note

        assert scope_sibling("total_games") is None
        vetoes = [self._veto("total_games")]
        assert unreviewed_sibling_note(
            self._row("total_games"), VetoIndex(vetoes), vetoes
        ) is None

    def test_it_reports_and_never_changes_the_bar(self) -> None:
        # The whole design constraint: widening a veto by rule once inverted
        # the analyst's own picks. This may only ever add a sentence.
        from bet.simple_stats.bet_builder_draft import VetoIndex, required_odds

        row = self._row("shots_on_target_total")
        vetoes = [self._veto("shots_on_target_for")]
        index = VetoIndex(vetoes)
        assert index.for_row(row) is None
        assert required_odds(row, "LEAN", basis="p_central") == pytest.approx(
            (1.0 / 0.730) * 1.10, abs=1e-3
        )
