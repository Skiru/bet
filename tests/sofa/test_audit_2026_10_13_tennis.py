"""Audit 2026-10-13, tennis items (docs/sofa/history/AUDYT_RYNKOW_KONTEKST_
2026-10-13.md): B5 - the per-set games and sets_total read off the rating's
neighbours behind epochs.TENNIS_SET_RATING_PRICES_FROM_UTC; B6 - the serve
index as a second neighbour coordinate (measurement only). Offline and fast."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import FixtureOffer, PricedRung
from bet.sofa.engine import _tilted_weights, p_empirical_centred_raw
from bet.sofa.tennis_rating import (
    SET_RATING_PRICED_MARKETS,
    MatchForecast,
    Outcome,
    TennisResult,
    _outcomes,
)
from scripts.sofa import measure_tennis_set_markets as b5
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_player_markets import dataclasses_replace_tennis
from tests.sofa.test_tennis_rating import _POOL, _forecast
from tests.sofa.test_tennis_rating import _samples as tennis_samples

# --- B5: the neighbours know set three ----------------------------------------


def _result(sets: tuple[tuple[int, int], ...]) -> TennisResult:
    return TennisResult(
        event_id=1, ts=0, tier="CH", surface="hard", home_id=1, away_id=2,
        home_won=sum(a > b for a, b in sets) == 2, sets=sets, minutes=None,
        completed=True)


def test_an_outcome_carries_set_three_only_when_a_full_set_was_played() -> None:
    home, away = _outcomes(_result(((6, 4), (3, 6), (7, 5))), 0.6)
    assert home.set3 == (7, 5) and away.set3 == (5, 7)
    # a 10-point match tiebreak is a 1-0 "set": no set-three games
    mtb = _outcomes(_result(((6, 4), (3, 6), (1, 0))), 0.6)
    assert mtb[0].match_tiebreak and mtb[0].set3 is None and mtb[1].set3 is None
    straight = _outcomes(_result(((6, 4), (6, 3))), 0.6)
    assert straight[0].set3 is None and straight[1].set3 is None


def test_set_three_is_read_conditional_on_a_played_third_set() -> None:
    pool = [
        Outcome(0.5, 12, 6, 2, 0, (6, 3), (6, 3)),
        Outcome(0.5, 17, 15, 3, 0, (6, 4), (4, 6), set3=(7, 5)),
        Outcome(0.5, 13, 16, 3, 0, (6, 4), (4, 6), set3=(3, 6)),
        Outcome(0.5, 11, 12, 3, 0, (6, 4), (4, 6), True, set3=None),  # MTB
    ]
    mirrored = [Outcome(0.5, o.games_against, o.games_for, o.sets, o.tiebreaks,
                        (o.set1[1], o.set1[0]), (o.set2[1], o.set2[0]),
                        o.match_tiebreak,
                        set3=None if o.set3 is None else (o.set3[1], o.set3[0]))
                for o in pool]
    f = MatchForecast(0.5, tuple(pool), tuple(mirrored), 20, 20)
    # two neighbours played a full third set: 7 and 3 games
    assert f.read("games_won_set3_for", "side_a", 4.5, "OVER") == 0.5
    assert f.read("games_won_set3_for", "side_a", 2.5, "OVER") == 1.0
    assert f.read("games_won_set3_for", "side_b", 5.5, "UNDER") == 0.5
    assert f.read("games_won_set3_for", None, 4.5, "OVER") is None
    # no neighbour with a third set: nothing to read, not a 0
    none = MatchForecast(0.5, tuple(pool[:1]), tuple(mirrored[:1]), 20, 20)
    assert none.read("games_won_set3_for", "side_a", 4.5, "OVER") is None
    # never priced through probability() (RATED_MARKETS is unchanged)
    assert f.probability("games_won_set3_for", "side_a", 4.5, "OVER") is None


def test_the_set_markets_are_the_audits_six() -> None:
    assert SET_RATING_PRICED_MARKETS == {
        "games_set1_total", "games_set2_total", "games_won_set1_for",
        "games_won_set2_for", "games_won_set3_for", "sets_total"}


# --- B5: the switch ------------------------------------------------------------


def test_the_set_rating_switch_is_on_from_the_refit_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # switched on with the refit of 2026-10-13 (18:10Z, operator O6)
    on = datetime(2026, 10, 13, 18, 10, tzinfo=UTC)
    assert epochs.TENNIS_SET_RATING_PRICES_FROM_UTC == on
    assert epochs.tennis_set_rating_prices("2026-10-13", on)
    assert not epochs.tennis_set_rating_prices("2026-10-13", datetime(
        2026, 10, 13, 18, 9, tzinfo=UTC))
    at = datetime(2026, 10, 20, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "TENNIS_SET_RATING_PRICES_FROM_UTC", at)
    assert epochs.tennis_set_rating_prices("2026-10-20", at)
    assert not epochs.tennis_set_rating_prices("2026-10-20", datetime(
        2026, 10, 19, 23, 59, tzinfo=UTC))
    # a rebuild of an earlier day keeps the rule it printed under
    assert not epochs.tennis_set_rating_prices("2026-10-19", datetime(
        2026, 10, 21, tzinfo=UTC))


def _offer(over: float, under: float) -> FixtureOffer:
    fetched = datetime(2026, 9, 22, 20, tzinfo=UTC)
    rungs = [
        PricedRung(market="games_total", subject="", line=20.5,
                   over_odds=over, under_odds=under, fetched_at_utc=fetched),
        PricedRung(market="games_won_for", subject="Kenta Kawada", line=10.5,
                   over_odds=over, under_odds=under, fetched_at_utc=fetched),
        PricedRung(market="games_won_set1_for", subject="Kenta Kawada", line=4.5,
                   over_odds=over, under_odds=under, fetched_at_utc=fetched),
    ]
    return FixtureOffer(sofascore_event_id=1, status="PRICED",
                        unmapped_markets=[], rungs=rungs)


def _sheet(set_rating_prices: bool | None, over: float = 1.85,
           under: float = 1.85, rated: bool = True) -> list[dict[str, object]]:
    kwargs = {} if set_rating_prices is None else {
        "set_rating_prices": set_rating_prices}
    rows, _ = process_fixture(
        dataclasses_replace_tennis(), tennis_samples(), _offer(over, under),
        baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), rating=_forecast(_POOL) if rated else None,
        stats_only=True, rating_prices=True, **kwargs,  # type: ignore[arg-type]
    )
    return [sheet_row_json(r) for r in rows]


def test_off_the_sheet_is_byte_identical() -> None:
    default = json.dumps(_sheet(None), sort_keys=True)
    assert json.dumps(_sheet(False), sort_keys=True) == default


def test_on_the_per_set_row_is_the_neighbours_and_ignores_the_price() -> None:
    off = {(r["market"], r["direction"]): r for r in _sheet(False)}
    on = {(r["market"], r["direction"]): r for r in _sheet(True)}
    dear = {(r["market"], r["direction"]): r for r in _sheet(True, 3.0, 1.3)}
    f = _forecast(_POOL)
    for direction in ("OVER", "UNDER"):
        key = ("games_won_set1_for", direction)
        want = f.read("games_won_set1_for", "side_a", 4.5, direction)
        assert want is not None
        assert on[key]["p_central"] == pytest.approx(want)
        assert on[key]["forecast_p"] == pytest.approx(want)
        assert on[key]["forecast_source"] == "tennis_rating"
        assert dear[key]["p_central"] == on[key]["p_central"]
        assert off[key]["p_central"] != on[key]["p_central"]
        # the families already rated are untouched by this switch
        for market in ("games_won_for", "games_total"):
            assert on[(market, direction)] == off[(market, direction)]


def test_on_an_unrated_fixture_keeps_the_sample() -> None:
    on = json.dumps(_sheet(True, rated=False), sort_keys=True)
    assert on == json.dumps(_sheet(False, rated=False), sort_keys=True)


# --- B5: the measurement's sample estimator is SHEET's ---------------------------


def test_the_measured_sample_estimator_is_the_engines() -> None:
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(5, 20)
        values = [float(rng.choice((2, 3, 4, 5, 6, 6, 6, 7))) for _ in range(n)]
        prior = rng.choice((None, 4.7396, 3.0, 6.5))
        line = rng.choice((2.5, 3.5, 4.5, 5.5, 6.5))
        direction = rng.choice(("OVER", "UNDER"))
        centre = b5.centre_of(values, prior, 5.0)
        weights = _tilted_weights(values, centre)
        got = b5.sample_p(values, centre, line, direction, weights)
        mean = sum(values) / n
        want = p_empirical_centred_raw(values, line, direction,  # type: ignore[arg-type]
                                       centre - mean)
        assert got == pytest.approx(want, abs=1e-9)


def test_past_values_read_set_three_like_extract_metric() -> None:
    assert "games_won_set3_for" not in b5.past_values(((6, 4), (6, 3)))
    assert "games_won_set3_for" not in b5.past_values(((6, 4), (3, 6), (1, 0)))
    v = b5.past_values(((6, 4), (3, 6), (7, 6)))
    assert v["games_won_set3_for"] == 7.0 and v["sets_total"] == 3.0
    assert v["games_set1_total"] == 10.0 and v["games_won_set2_for"] == 3.0
    flipped = b5.past_values(b5.flip(((6, 4), (3, 6), (7, 6))))
    assert flipped["games_won_set3_for"] == 6.0


def test_the_bootstrap_resamples_matches() -> None:
    import numpy as np

    match = np.array([1, 1, 2, 2, 3, 3], dtype=np.int64)
    d = np.array([-1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
    mean, lo, hi = b5.boot_mean_diff(match, d, 200)
    assert mean == lo == hi == -1.0


# --- B6: the serve index and the 2-D neighbours (measurement only) -------------


def test_the_2d_neighbours_are_the_exact_nearest() -> None:
    import numpy as np

    from scripts.sofa import measure_tennis_serve_neighbours as b6

    rng = np.random.default_rng(3)
    cell = b6._Cell2D()
    ps = rng.beta(2, 2, 3000)
    ds = rng.normal(0, 0.4, 3000)
    for p, d in zip(ps, ds, strict=True):
        cell.add(Outcome(float(p), 12, 10, 2, 0, (6, 4), (6, 6)), float(d))
    for p0, d0 in ((0.5, 0.0), (0.97, 1.2), (0.02, -1.0)):
        got = cell.nearest(p0, d0, k=50)
        assert got is not None and len(got) == 50
        dist = ((ps - p0) / ps.std()) ** 2 + ((ds - d0) / ds.std()) ** 2
        want = set(np.argsort(dist)[:50].tolist())
        got_idx = {cell.rows.index(o) for o in got}
        assert got_idx == want
    assert b6._Cell2D().nearest(0.5, 0.0) is None  # thinner than k: no read


def test_the_serve_index_waits_for_six_matches_and_reads_before_the_match() -> None:
    from scripts.sofa import measure_tennis_serve_neighbours as b6

    sr = b6.ServeRatings()
    r = _result(((6, 4), (6, 3)))
    for _ in range(5):
        sr.update(r, (40, 55, 25, 50))
    assert sr.index(1, 2) is None
    sr.update(r, (40, 55, 25, 50))
    d = sr.index(1, 2)
    assert d is not None
    # symmetric in the two players: one index per match
    assert sr.index(2, 1) == pytest.approx(d)


def test_the_handicap_row_wins_like_the_derived_market() -> None:
    from scripts.sofa import measure_tennis_serve_neighbours as b6

    assert b6.wins("handicap_games", -3.0, 4.5, "OVER") == 1   # +4.5, lost by 3
    assert b6.wins("handicap_games", 3.0, -4.5, "OVER") == 0   # -4.5, won by 3
    assert b6.wins("games_total", 21.0, 20.5, "UNDER") == 0
