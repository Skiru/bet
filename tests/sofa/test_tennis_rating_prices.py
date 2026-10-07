"""Tennis games families priced by the rating's neighbours (2026-10-07).

Measured out of sample (243,025 singles, two walk-forward windows, bootstrap by
match): games_won_for / handicap_games / most_games from the neighbours beat
the sample estimator by -0.072 log-loss [-0.074, -0.070]; games_total only as
a 50/50 mix with the NB (-0.0088).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa.tennis_rating import RATING_PRICED_MARKETS, W_GAMES_TOTAL_RATING
from tests.sofa.test_stats_only_sheet import _tennis


def test_switch_off_keeps_the_sample_estimator() -> None:
    off = _tennis(1.85, 1.85, stats_only=True, rating_prices=False)
    plain = _tennis(1.85, 1.85, stats_only=True, rated=False)
    for key in off:
        assert off[key].p_central == plain[key].p_central, key


def test_games_won_for_is_the_rating_alone_and_ignores_the_price() -> None:
    short = _tennis(1.40, 3.00, stats_only=True, rating_prices=True)
    long_ = _tennis(3.00, 1.40, stats_only=True, rating_prices=True)
    for direction in ("OVER", "UNDER"):
        row = short[("games_won_for", direction)]
        assert row.p_central == long_[("games_won_for", direction)].p_central
        assert row.forecast_p is not None
        assert row.p_central == pytest.approx(row.forecast_p, abs=2e-3)
    assert RATING_PRICED_MARKETS >= {"games_won_for", "handicap_games",
                                     "most_games"}


def test_games_total_is_the_half_half_mix_of_the_nb_and_the_rating() -> None:
    off = _tennis(1.85, 1.85, stats_only=True, rating_prices=False)
    on = _tennis(1.85, 1.85, stats_only=True, rating_prices=True)
    for direction in ("OVER", "UNDER"):
        row = on[("games_total", direction)]
        assert row.forecast_p is not None
        expect = (W_GAMES_TOTAL_RATING * row.forecast_p
                  + (1.0 - W_GAMES_TOTAL_RATING) * off[("games_total", direction)]
                  .p_central)
        assert row.p_central == pytest.approx(expect, abs=2e-3)


def test_a_family_not_measured_and_an_unrated_fixture_are_untouched() -> None:
    off = _tennis(1.85, 1.85, stats_only=True, rating_prices=False)
    on = _tennis(1.85, 1.85, stats_only=True, rating_prices=True)
    for direction in ("OVER", "UNDER"):  # per-set games: not in the measurement
        assert (on[("games_won_set1_for", direction)].p_central
                == off[("games_won_set1_for", direction)].p_central)
    unrated_off = _tennis(1.85, 1.85, stats_only=True, rated=False)
    unrated_on = _tennis(1.85, 1.85, stats_only=True, rated=False,
                         rating_prices=True)
    for key in unrated_off:
        assert unrated_on[key].p_central == unrated_off[key].p_central, key


def test_the_switch_opens_at_its_moment(monkeypatch: pytest.MonkeyPatch) -> None:
    at = epochs.TENNIS_RATING_PRICES_FROM_UTC
    assert at is not None
    day = epochs.TENNIS_RATING_PRICES_DATE
    assert not epochs.tennis_rating_prices(day, at.replace(minute=at.minute - 1))
    assert epochs.tennis_rating_prices(day, at)
    assert not epochs.tennis_rating_prices("2026-10-06", datetime(
        2026, 10, 9, tzinfo=UTC))


# --- the derived path (handicap_games / most_games): the rating alone ---------

def _derived(rating_p, over_odds: float, stats_only: bool = True,
             side: str = "chelsea", under_odds: float | None = 1.60):
    from bet.sofa.contracts import FixtureOffer, PricedRung
    from bet.sofa.derived import price_derived_rungs
    from bet.sofa.timeutil import now
    from tests.sofa.test_derived_markets import make_fixture, make_samples

    samples = make_samples("games_won_for", [12, 12, 11, 12, 12, 12, 11, 12, 12, 11],
                           [12, 11, 12, 12, 11, 12, 12, 11, 12, 12])
    rungs = [PricedRung(market="handicap_games", subject=side, line=-1.5,
                        over_odds=over_odds, under_odds=under_odds, fetched_at_utc=now())]
    rows, _ = price_derived_rungs(
        fixture=make_fixture(), samples=samples,
        offer=FixtureOffer(sofascore_event_id=1, status="PRICED", rungs=rungs,
                           unmapped_markets=[]),
        correlations={}, vetoes=[], min_sample=5, max_ladder_sigma=99.0,
        k_price=10.0, unfitted=[], rating_p=rating_p, stats_only=stats_only)
    return rows


def test_the_derived_p_is_the_ratings_and_never_the_price() -> None:
    seen: list[tuple[str, str | None, float, str]] = []

    def rating_p(market: str, side: str | None, line: float, direction: str):  # type: ignore[no-untyped-def]
        seen.append((market, side, line, direction))
        return 0.731

    cheap = _derived(rating_p, 1.30)
    dear = _derived(rating_p, 3.50)
    assert cheap and dear
    assert cheap[0].p_central == pytest.approx(0.731, abs=1e-3)
    assert cheap[0].p_central == dear[0].p_central  # the odds are not an input
    assert seen[0][0] == "handicap_games" and seen[0][1] == "side_b"


def test_the_old_rule_still_goes_through_the_price_blend(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from bet.sofa import derived

    calls: list[tuple[float, float | None]] = []

    def spy(p: float, market_p: float | None, *a, **k):  # type: ignore[no-untyped-def]
        calls.append((p, market_p))
        return p

    monkeypatch.setattr(derived, "blend_with_price", spy)
    _derived(lambda *a: 0.731, 1.9, stats_only=False)
    assert calls and calls[0][0] == 0.731
    calls.clear()
    _derived(lambda *a: 0.731, 1.9, stats_only=True)
    assert calls == []  # stats-only: the price is not even asked


def test_a_rating_that_does_not_price_the_selection_leaves_the_sample() -> None:
    sample = _derived(None, 1.90)
    declined = _derived(lambda *a: None, 1.90)
    assert sample[0].p_central == declined[0].p_central


def test_the_stats_only_rating_reader_prices_the_measured_families_only() -> None:
    from scripts.sofa.run_sheet import _stats_only_rating_p

    class Rating:
        def read(self, market: str, side: str, line: float, direction: str) -> float:
            return 0.62

    read = _stats_only_rating_p(Rating())  # type: ignore[arg-type]
    assert read("handicap_games", "side_a", -1.5, "OVER") == 0.62
    assert read("most_games", "side_b", 0.0, "OVER") == 0.62
    assert read("most_games", "draw", 0.0, "OVER") is None      # the draw: sample
    assert read("games_total", "side_a", 20.5, "OVER") is None  # mixed elsewhere
    assert read("handicap_games", None, -1.5, "OVER") is None
