"""Best-of-five tennis and the format-bound sets_total (2026-10-14).

The night refit's replay (calibrate_from_cache --tennis-set-ratings, audit
B5) wrote sets_total rows at 2.5 for Grand Slam men's matches: a best-of-five
match always has >= 3 sets, so UNDER 2.5 realised ~0 at p ~0.45 and bent the
sets_total UNDER curve. The replay now keeps the set bases of best-of-three
matches only, and SHEET refuses sets_total on a fixture not known to be best
of three (BEST_OF_FIVE_NOT_MODELLED) instead of pricing it.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    GapReason,
    MetricSample,
    PricedRung,
)
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa.calibrate_from_cache import iter_rows, set_values
from scripts.sofa.run_sheet import format_bound_refusal, process_fixture
from tests.sofa.test_audit_2026_10_13_replay import _tennis_history, _tennis_played
from tests.sofa.test_player_markets import dataclasses_replace_tennis
from tests.sofa.test_tennis_rating import _obs


def _event(home: list[int], away: list[int]) -> dict[str, object]:
    def score(games: list[int], won: int) -> dict[str, int]:
        return {"current": won, **{f"period{i}": g for i, g in enumerate(games, 1)}}

    won_home = sum(1 for h, a in zip(home, away, strict=True) if h > a)
    return {"homeScore": score(home, won_home),
            "awayScore": score(away, len(home) - won_home)}


# --- the replay ---------------------------------------------------------------


def test_set_values_keep_best_of_three_only() -> None:
    bo3 = _event([6, 3, 6], [4, 6, 2])
    assert set_values(bo3)["sets"] == (2.0, 1.0)
    # a best-of-five (the winner took three sets): no set base at all - not
    # sets_total, and not the per-set games a best-of-three sample excludes
    for bo5 in (_event([6, 6, 6], [4, 3, 2]),
                _event([6, 3, 7, 6], [4, 6, 5, 2]),
                _event([4, 6, 6, 3, 7], [6, 3, 4, 6, 5])):
        assert set_values(bo5) == {}
    # a format the listing cannot tell is not guessed
    assert set_values({"homeScore": {"current": 1, "period1": 6},
                       "awayScore": {"current": 1, "period1": 4}}) == {}


def test_the_replay_writes_no_set_row_for_a_best_of_five_match() -> None:
    played = _tennis_played(_tennis_history(n_days=20))
    # the last day's matches become best-of-five with a four-set score
    cut = played[-1].timestamp - played[-1].timestamp % 86400
    bo5_ids = set()
    for i, m in enumerate(played):
        if m.timestamp >= cut and m.tennis is not None:
            values = {**m.values, "sets": (3.0, 1.0),
                      "games_set3": (6.0, 4.0)}
            played[i] = dataclasses.replace(
                m, values=values,
                tennis=dataclasses.replace(m.tennis, best_of_five=True))
            bo5_ids.add(m.event_id)
    assert bo5_ids
    rows = list(iter_rows(played, {}, emit_from=cut - 86400))
    set_markets = {"sets_total", "games_set1_total", "games_set2_total",
                   "games_won_set1_for", "games_won_set2_for",
                   "games_won_set3_for"}
    bo3 = {r.market for r in rows if r.event_id not in bo5_ids}
    assert "sets_total" in bo3  # the best-of-three day still has its rows
    bo5 = [r for r in rows if r.event_id in bo5_ids]
    assert bo5  # the match itself is replayed (games)
    assert not [r for r in bo5 if r.market in set_markets]
    # the flag only switches the neighbour pricing, never this rule
    assert cfc.TENNIS_SET_RATINGS is False


# --- SHEET ---------------------------------------------------------------------


def _samples() -> FixtureSamples:
    sets = [2, 3, 2, 2, 3, 2, 3, 2, 2, 3]
    return FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={"sets_total": MetricSample(
            metric="sets_total", side_a=_obs(sets, 100),
            side_b=_obs(sets, 200), h2h=[])},
    )


def _offer() -> FixtureOffer:
    fetched = datetime(2026, 9, 22, 20, tzinfo=UTC)
    return FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market="sets_total", subject="", line=2.5,
                          over_odds=2.1, under_odds=1.7,
                          fetched_at_utc=fetched)])


@pytest.mark.parametrize("best_of", [5, None])
def test_sheet_refuses_sets_total_unless_best_of_three(best_of: int | None) -> None:
    fixture = dataclasses_replace_tennis().model_copy(
        update={"default_period_count": best_of})
    rows, skipped = process_fixture(
        fixture, _samples(), _offer(), baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(),
        stats_only=True, rating_prices=True, set_rating_prices=True)
    assert not [r for r in rows if r.market == "sets_total"]
    reasons = [reason for rung, reason, _ in skipped
               if rung.market == "sets_total"]
    assert reasons == [GapReason.BEST_OF_FIVE_NOT_MODELLED]


def test_sheet_prices_sets_total_on_a_best_of_three() -> None:
    fixture = dataclasses_replace_tennis()
    assert fixture.default_period_count == 3
    assert format_bound_refusal(fixture, "sets_total") is None
    rows, skipped = process_fixture(
        fixture, _samples(), _offer(), baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(),
        stats_only=True, rating_prices=True, set_rating_prices=True)
    assert {r.direction for r in rows if r.market == "sets_total"} == {
        "OVER", "UNDER"}
    assert not [s for s in skipped
                if s[1] is GapReason.BEST_OF_FIVE_NOT_MODELLED]


def test_only_the_format_bound_market_is_refused() -> None:
    bo5 = dataclasses_replace_tennis().model_copy(
        update={"default_period_count": 5})
    assert format_bound_refusal(bo5, "sets_total") is not None
    for market in ("games_total", "games_set1_total", "games_won_set1_for"):
        assert format_bound_refusal(bo5, market) is None
