"""The comparative-market estimator, and the refusals that keep it honest.

The properties tested here are the ones that would let a wrong number reach a
report looking like a right one: a probability that does not sum to one, a
refused metric quietly answering anyway, a devig that disagrees with the rest of
the pipeline's convention, and the cross-market comparison getting its direction
backwards -- which would turn "take the handicap" into "take the H2H".
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from bet.simple_stats.derived_markets import (
    CALIBRATION,
    GATE,
    MIN_SAMPLE,
    REFUSED,
    Calibration,
    devig,
    dutch,
    estimate,
    handicap_versus_three_way,
    overround,
    range_from_ladder,
    required_price,
    skellam_three_way,
)


class TestSkellam:
    def test_three_outcomes_are_a_distribution(self) -> None:
        for lam_a, lam_b in ((4.9, 4.4), (0.2, 9.0), (14.0, 14.0)):
            probs = skellam_three_way(lam_a, lam_b)
            assert math.isclose(sum(probs), 1.0, abs_tol=1e-9)
            assert all(p >= 0 for p in probs)

    def test_equal_rates_are_symmetric(self) -> None:
        more, _, less = skellam_three_way(5.0, 5.0)
        assert math.isclose(more, less, abs_tol=1e-9)

    def test_the_bigger_rate_is_the_favourite(self) -> None:
        more, _, less = skellam_three_way(7.0, 4.0)
        assert more > less

    def test_a_tie_is_likelier_when_counts_are_small(self) -> None:
        # This is why the half-match markets were refused: at a mean under 3 the
        # drawn outcome eats the market, and a three-way read as a two-way is
        # wrong by exactly that much.
        assert skellam_three_way(1.5, 1.5)[1] > skellam_three_way(12.0, 12.0)[1]


class TestEstimate:
    def test_refuses_every_metric_the_replay_rejected(self) -> None:
        for metric in REFUSED:
            result = estimate(metric, [1.0] * 10, [2.0] * 10)
            assert result.verdict == "REFUSED_NO_SIGNAL"
            assert result.probabilities is None
            assert result.reason, "a refusal must carry its reason"

    def test_refuses_a_metric_nobody_measured(self) -> None:
        result = estimate("offsides_for", [1.0] * 10, [2.0] * 10)
        assert result.verdict == "REFUSED_UNKNOWN_METRIC"
        assert result.probabilities is None

    def test_refuses_a_sample_thinner_than_the_replay_admitted(self) -> None:
        result = estimate("corners_for", [5.0] * (MIN_SAMPLE - 1), [5.0] * 10)
        assert result.verdict == "REFUSED_THIN_SAMPLE"
        assert result.probabilities is None

    def test_home_correction_moves_the_call_and_is_not_cosmetic(self) -> None:
        # Two identical samples. The fixture still has a home side, and the
        # measured +1.19 corner advantage has to show up: an uncorrected model
        # would call this exactly even.
        result = estimate("corners_for", [5.0] * 10, [5.0] * 10)
        assert result.verdict == "USABLE"
        assert result.probabilities[0] > result.probabilities[2]
        assert result.called_side == "home"

    def test_a_level_sample_is_not_confident(self) -> None:
        assert not estimate("corners_for", [5.0] * 10, [5.0] * 10).confident

    def test_a_lopsided_sample_clears_the_gate(self) -> None:
        result = estimate("corners_for", [9.0] * 10, [2.0] * 10)
        assert result.confident
        assert result.probabilities[0] >= GATE

    def test_shrinkage_pulls_an_extreme_sample_off_certainty(self) -> None:
        result = estimate("corners_for", [14.0] * 10, [1.0] * 10)
        # Without shrinkage this is ~1.0; the base rate has to survive in it.
        assert result.verdict == "USABLE"
        assert result.probabilities[0] < 0.95

    def test_refuses_a_sample_the_home_correction_would_push_through_zero(self) -> None:
        # mean_away 0.4 minus 1.19/2 is negative. The old code clamped it to
        # 0.05 and answered anyway; clamping invents the asymmetry it reports.
        result = estimate("corners_for", [5.0] * 10, [0.4] * 10)
        assert result.verdict == "REFUSED_OUT_OF_RANGE"
        assert result.probabilities is None

    def test_refuses_an_all_zero_sample_rather_than_reading_it_as_zero_corners(
        self,
    ) -> None:
        # A zero from these providers means "no data", not "no corners", and the
        # clamped version of this returned 0.451 / 0.457 / 0.092 -- a confident
        # shape built out of two samples that said nothing at all.
        result = estimate("corners_for", [0.0] * 10, [0.0] * 10)
        assert result.verdict == "REFUSED_OUT_OF_RANGE"

    def test_a_single_zero_observation_is_not_a_refusal(self) -> None:
        # 107 of the 288 replayed corner fixtures contain at least one zero and
        # they are real: a side can genuinely take no corners in a match.
        result = estimate("corners_for", [0.0, 5.0, 6.0, 4.0, 7.0], [3.0] * 5)
        assert result.verdict == "USABLE"

    def test_poisson_survives_a_cap_no_factorial_could(self) -> None:
        # The direct exp/factorial form raised OverflowError past k = 170. Log
        # space has no ceiling, and the answer must not depend on the cap.
        wide = skellam_three_way(25.0, 25.0, cap=400)
        assert math.isclose(sum(wide), 1.0, abs_tol=1e-12)
        assert math.isclose(skellam_three_way(25.0, 25.0)[0], wide[0], abs_tol=1e-9)

    def test_price_floor_is_the_lower_of_the_two_bootstraps(self) -> None:
        for metric, cal in CALIBRATION.items():
            assert cal.gate_ci and cal.gate_ci_by_day, metric
            assert cal.price_floor == min(cal.gate_ci[0], cal.gate_ci_by_day[0])
            # And it must be below the point estimate, or it is not a floor.
            assert cal.price_floor < cal.gate_hits, metric

    def test_every_calibrated_metric_carries_a_measurement(self) -> None:
        for metric, cal in CALIBRATION.items():
            assert isinstance(cal, Calibration)
            assert cal.n > 0
            assert math.isclose(sum(cal.base), 1.0, abs_tol=0.002), metric
            # The only reason a metric is in this table is that it beat the base
            # rate. If an edit ever makes that untrue, the table is a lie.
            assert cal.brier_model < cal.brier_base, metric


class TestPrices:
    def test_devig_sums_to_one_and_keeps_the_order(self) -> None:
        probs = devig([1.47, 6.9, 3.3])
        assert math.isclose(sum(probs), 1.0, abs_tol=1e-12)
        assert probs[0] > probs[2] > probs[1]

    def test_devig_refuses_an_impossible_price(self) -> None:
        with pytest.raises(ValueError):
            devig([1.0, 3.0])

    def test_overround_is_measured_on_the_real_screen(self) -> None:
        # Inter-Napoli corners, 2026-09-05: three-way 12.8%, two-way 8.5%.
        assert math.isclose(overround([1.47, 6.9, 3.3]), 0.128, abs_tol=0.001)
        assert math.isclose(overround([1.47, 2.47]), 0.085, abs_tol=0.001)

    def test_dutch_is_the_price_of_backing_both(self) -> None:
        assert math.isclose(dutch([6.9, 3.3]), 2.2317, abs_tol=1e-3)

    def test_handicap_beat_the_three_way_on_the_measured_fixture(self) -> None:
        gap = handicap_versus_three_way(
            favourite_price=1.47,
            draw_price=6.9,
            outsider_price=3.3,
            handicap_outsider_price=2.47,
        )
        assert math.isclose(gap.gain, 0.106, abs_tol=0.002)
        assert gap.direct_price > gap.synthetic_price

    def test_the_comparison_can_come_out_the_other_way(self) -> None:
        # Nothing in the arithmetic forces the handicap to win; it won on six of
        # six fixtures because of a margin difference, and a day where the book
        # prices them level has to read as level rather than as an edge.
        gap = handicap_versus_three_way(
            favourite_price=1.47,
            draw_price=6.9,
            outsider_price=3.3,
            handicap_outsider_price=2.10,
        )
        assert gap.gain < 0

    def test_range_market_is_the_ladder_repartitioned(self) -> None:
        # Inter-Napoli corners, 2026-09-05: rungs 8.5 (2.02/1.72) and
        # 11.5 (1.27/3.50) against buckets <9 / 9-11 / 12+.
        low, middle, top = range_from_ladder(
            under_low=(2.02, 1.72), under_high=(1.27, 3.50)
        )
        assert math.isclose(low + middle + top, 1.0, abs_tol=1e-9)
        assert math.isclose(low, 0.4599, abs_tol=5e-4)
        assert math.isclose(middle, 0.2739, abs_tol=5e-4)
        assert math.isclose(top, 0.2662, abs_tol=5e-4)

    def test_range_buckets_are_devigged_not_raw_reciprocals(self) -> None:
        # The raw-reciprocal version made the top bucket look 25.6% short when
        # the honest figure was 6.8%. Guard the difference, not the wording.
        _, _, top = range_from_ladder(under_low=(2.02, 1.72), under_high=(1.27, 3.50))
        assert top > 1 - 1 / 1.27, "an undevigged top bucket understates itself"

    def test_the_middle_bucket_carries_the_market(self) -> None:
        low, middle, top = range_from_ladder(
            under_low=(2.02, 1.72), under_high=(1.27, 3.50)
        )
        edges = [2.02 * low - 1, 3.00 * middle - 1, 3.50 * top - 1]
        assert edges[1] < edges[0] and edges[1] < edges[2]

    def test_range_refuses_to_invent_a_missing_rung(self) -> None:
        low, middle, top = range_from_ladder(under_low=(2.02, 1.72), under_high=None)
        assert middle is None and top is None and low is not None

    def test_required_price_is_the_familiar_shape(self) -> None:
        assert math.isclose(required_price(0.5), 2.1, abs_tol=1e-9)
        assert required_price(0.621) > required_price(
            0.791
        ), "a lower probability must demand a longer price"

    def test_required_price_refuses_a_certainty(self) -> None:
        for bad in (0.0, 1.0, -0.1, 1.2):
            with pytest.raises(ValueError):
                required_price(bad)


class TestScreenReading:
    """The CLI's parsing of Superbet's own spellings -- where the real bug was.

    Loaded by path because ``scripts/simple`` is not a package; the same trick
    ``test_agent_contract`` uses for the other CLIs.
    """

    @staticmethod
    def _cli():
        import importlib.util

        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "derived_markets_cli", root / "scripts" / "simple" / "derived_markets.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    # Newcastle-Bournemouth, 2026-09-05, verbatim: the same rung twice under
    # opposite signs, which is what broke the first version.
    ODDS = [
        {"marketName": "Rzuty rożne handicap", "name": "Newcastle (-1.5)",
         "price": 2.15, "specialBetValue": "-1.5", "status": "active"},
        {"marketName": "Rzuty rożne handicap", "name": "Bournemouth (1.5)",
         "price": 1.61, "specialBetValue": "-1.5", "status": "active"},
        {"marketName": "Rzuty rożne handicap", "name": "Newcastle (-0.5)",
         "price": 1.75, "specialBetValue": "-0.5", "status": "active"},
        {"marketName": "Rzuty rożne handicap", "name": "Bournemouth (0.5)",
         "price": 1.95, "specialBetValue": "-0.5", "status": "active"},
        {"marketName": "Rzuty rożne handicap", "name": "Newcastle (0.5)",
         "price": 1.49, "specialBetValue": "0.5", "status": "active"},
        {"marketName": "Rzuty rożne handicap", "name": "Bournemouth (-0.5)",
         "price": 2.42, "specialBetValue": "0.5", "status": "active"},
    ]

    def test_plus_half_is_read_per_team_not_per_sign(self) -> None:
        cli = self._cli()
        market = "Rzuty rożne handicap"
        assert cli._handicap_plus_half(self.ODDS, market, "Newcastle") == 1.49
        assert cli._handicap_plus_half(self.ODDS, market, "Bournemouth") == 1.95

    def test_minus_half_is_never_mistaken_for_plus_half(self) -> None:
        # "Bournemouth (-0.5)" also contains "(0.5)" as a substring. Matching on
        # containment would return 2.42 here and quietly price the wrong leg.
        cli = self._cli()
        got = cli._handicap_plus_half(self.ODDS, "Rzuty rożne handicap", "Bournemouth")
        assert got != 2.42

    def test_a_blocked_rung_is_not_offered(self) -> None:
        cli = self._cli()
        blocked = [dict(o, status="block") for o in self.ODDS]
        got = cli._handicap_plus_half(blocked, "Rzuty rożne handicap", "Newcastle")
        assert got is None

    def test_missing_market_reads_as_absent_not_as_zero(self) -> None:
        cli = self._cli()
        got = cli._handicap_plus_half(
            self.ODDS, "Liczba kartek - handicap", "Newcastle"
        )
        assert got is None

    def test_three_way_accepts_every_spelling_of_the_draw(self) -> None:
        cli = self._cli()
        for draw_name in ("remis", "Remis", "X", "żadna"):
            prices = {"Inter": 1.47, draw_name: 6.9, "Napoli": 3.3}
            assert cli._three_way_sides(prices, "Inter", "Napoli") == (1.47, 6.9, 3.3)

    def test_three_way_uses_club_names_before_the_positional_fallback(self) -> None:
        # "1"/"2" are Superbet's spelling on some markets and the clubs' names on
        # others. If both were present and the positional keys won, a fixture
        # whose favourite is away would come back reversed.
        cli = self._cli()
        prices = {"Inter": 1.47, "remis": 6.9, "Napoli": 3.3, "1": 9.9, "2": 9.9}
        assert cli._three_way_sides(prices, "Inter", "Napoli") == (1.47, 6.9, 3.3)

    def test_three_way_refuses_a_two_way_market(self) -> None:
        cli = self._cli()
        two_way = {"Inter": 1.47, "Napoli": 2.47}
        assert cli._three_way_sides(two_way, "Inter", "Napoli") is None


class TestCalibrationIsReproducible:
    """The constants must keep matching the replay they were taken from.

    Without this the table in ``derived_markets`` is a memory of a measurement
    rather than the measurement, and any change to the estimator silently
    invalidates every number quoted from it -- including the price floors the
    agent refuses bets on.
    """

    def test_replay_reproduces_every_published_constant(self) -> None:
        root = Path(__file__).resolve().parents[2]
        if not (root / "runs" / "_backtest_actuals.json").exists():
            pytest.skip("no settled slates on disk")
        result = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "simple" / "derived_markets_replay.py"),
                "--check",
            ],
            capture_output=True, text=True, timeout=600,
        )
        assert result.returncode == 0, result.stdout + result.stderr
