"""Where a SHEET row's prior comes from, and the ways it described another match.

All found by sofa-verifier on the 2026-09-23 rebuilds, on staked PDF legs:

  * a league with no fitted baseline was shrunk toward the GLOBAL pool (3.29
    goals) while that day's own samples held 72 matches of the league at 2.10;
  * the first fix built that league mean from the priced match's own sample
    too (half the Goiano pool), and from Nigeria's broken half-time split;
  * a cup tie has its own competition id, so it fell back to the global pool
    while the teams' own leagues were measured on the same page;
  * a match total was priced from a pool that was one side's history — 2
    Sant Andreu matches and 9 of Castilla's — though SAMPLES said THIN_SAMPLE.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import FixtureSamples, MetricSample, Observation
from scripts.sofa.fit_constants import MIN_BASELINE_OBSERVATIONS
from scripts.sofa.run_sheet import (
    MIN_DAY_LEAGUE_OBSERVATIONS,
    day_league_observations,
    day_league_prior,
    home_competition,
    process_fixture,
    resolve_prior,
)
from tests.sofa.test_sheet import make_fixture, make_offer, rung

GAUCHO = 18643


def _obs(ids: range, value: float, comp: int = GAUCHO) -> list[Observation]:
    return [
        Observation(sofascore_event_id=i, match_date_utc=datetime(2026, 9, 1, tzinfo=UTC),
                    opponent="x", value=value, competition_id=comp, season_id=1,
                    venue="home")
        for i in ids
    ]


def _samples(eid: int, metric: str, a: list[Observation], b: list[Observation],
             h2h: list[Observation] | None = None) -> FixtureSamples:
    return FixtureSamples(
        sofascore_event_id=eid, readiness="READY",
        metrics={metric: MetricSample(metric=metric, side_a=a, side_b=b, h2h=h2h or [])},
        gaps=[])


def test_the_day_bar_is_the_fitted_bar() -> None:
    assert MIN_DAY_LEAGUE_OBSERVATIONS == MIN_BASELINE_OBSERVATIONS


def test_a_shared_league_match_counts_once() -> None:
    fixtures = [make_fixture(sofascore_event_id=1), make_fixture(sofascore_event_id=2)]
    samples = [
        _samples(1, "goals_total", _obs(range(100, 120), 2.0), _obs(range(120, 130), 2.0)),
        # 110..119 repeat fixture 1's matches; 200..209 are new, at 3 goals.
        _samples(2, "goals_total", _obs(range(110, 120), 2.0), _obs(range(200, 210), 3.0)),
    ]
    pool = day_league_observations(fixtures, samples)["goals_total"][str(GAUCHO)]
    assert len(pool) == 40


def test_a_per_side_metric_keeps_both_teams_of_one_match() -> None:
    fixtures = [make_fixture(sofascore_event_id=1), make_fixture(sofascore_event_id=2)]
    samples = [
        _samples(1, "corners_for", _obs(range(100, 115), 4.0), _obs(range(300, 315), 6.0)),
        _samples(2, "corners_for", _obs(range(100, 115), 5.0), []),
    ]
    assert len(day_league_observations(fixtures, samples)["corners_for"][str(GAUCHO)]) == 45


def test_half_match_metrics_and_tennis_are_not_collected() -> None:
    """Nigeria's NPFL put every goal of a 2-0-at-the-break match in the second
    half; the split sums correctly, so no check downstream can see it."""
    football = make_fixture(sofascore_event_id=1)
    tennis = make_fixture(sofascore_event_id=2, sport="tennis")
    samples = [
        _samples(1, "goals_2h_total", _obs(range(100, 140), 2.0), _obs(range(140, 180), 2.0)),
        _samples(2, "games_total", _obs(range(400, 440), 20.0), _obs(range(440, 480), 21.0)),
    ]
    assert day_league_observations([football, tennis], samples) == {}


def test_the_prior_leaves_the_priced_matchs_own_sample_out() -> None:
    fixtures = [make_fixture(sofascore_event_id=1)]
    samples = [_samples(1, "goals_total", _obs(range(100, 140), 5.0),
                        _obs(range(200, 240), 2.0))]
    day = day_league_observations(fixtures, samples)
    assert day_league_prior(day, "goals_total", GAUCHO, set()) == (3.5, 80)
    assert day_league_prior(day, "goals_total", GAUCHO, set(range(100, 140))) == (2.0, 40)
    assert day_league_prior(day, "goals_total", GAUCHO, set(range(100, 215))) is None


def test_a_fitted_league_entry_always_wins() -> None:
    fixture = make_fixture(competition_id=17)
    baselines = {"goals_total": {"17": {"mean": 2.6, "n": 300},
                                 "global": {"mean": 3.29, "n": 55282}}}
    day = {"goals_total": {"17": {(i, ""): 9.0 for i in range(40)}}}
    assert resolve_prior(baselines, day, "goals_total", fixture, [[]], set()) == (2.6, None)


def test_a_league_without_a_baseline_takes_its_day_mean() -> None:
    fixture = make_fixture(competition_id=GAUCHO)
    baselines = {"goals_total": {"global": {"mean": 3.29, "n": 55282}}}
    day = {"goals_total": {str(GAUCHO): {(i, ""): 2.1 for i in range(72)}}}
    prior, note = resolve_prior(baselines, day, "goals_total", fixture, [[]], set())
    assert prior == 2.1
    assert note is not None and note.startswith(
        f"PRIOR_FROM_DAY_SAMPLES: competition {GAUCHO} mean 2.1 over 72")


def test_a_cup_tie_takes_the_leagues_its_teams_play_in() -> None:
    """Copa Uruguay: Boston River from one league, Fénix from another."""
    cup = make_fixture(competition_id=18877)
    baselines = {"corners_total": {"278": {"mean": 9.0, "n": 200},
                                   "global": {"mean": 9.52, "n": 90000}}}
    day = {"corners_total": {"1908": {(i, ""): 8.0 for i in range(1000, 1030)}}}
    boston = _obs(range(1, 8), 9.0, comp=278) + _obs(range(8, 10), 9.0, comp=18877)
    fenix = _obs(range(20, 27), 8.0, comp=1908) + _obs(range(27, 29), 8.0, comp=18877)
    prior, note = resolve_prior(baselines, day, "corners_total", cup, [boston, fenix],
                                set(range(0, 40)))
    assert prior == 8.5
    assert note is not None and "278=9 (fitted)" in note and "1908=8 (day n=30)" in note


def test_a_cup_tie_with_one_unknown_league_falls_back_to_global() -> None:
    cup = make_fixture(competition_id=18877)
    baselines = {"corners_total": {"278": {"mean": 9.0, "n": 200},
                                   "global": {"mean": 9.52, "n": 90000}}}
    boston = _obs(range(1, 8), 9.0, comp=278)
    unknown = _obs(range(20, 27), 8.0, comp=5555)
    assert resolve_prior(baselines, {}, "corners_total", cup, [boston, unknown],
                         set()) == (9.52, None)


def test_home_competition_needs_a_majority() -> None:
    assert home_competition(_obs(range(3), 1.0, 1) + _obs(range(3, 5), 1.0, 2)) == 1
    assert home_competition(_obs(range(2), 1.0, 1) + _obs(range(2, 4), 1.0, 2)
                            + _obs(range(4, 6), 1.0, 3)) is None


def test_process_fixture_prices_on_the_days_league_and_says_so() -> None:
    fixture = make_fixture(sofascore_event_id=1, competition_id=GAUCHO)
    own = _samples(1, "goals_total", _obs(range(100, 110), 2.0), _obs(range(110, 120), 2.0))
    other = _samples(2, "goals_total", _obs(range(500, 520), 2.1), _obs(range(520, 540), 2.1))
    day = day_league_observations([fixture, make_fixture(sofascore_event_id=2)],
                                  [own, other])
    rows, _ = process_fixture(
        fixture, own,
        make_offer([rung(1.5, 1.40, 2.80), rung(2.5, 2.10, 1.70), rung(3.5, 3.60, 1.28)]),
        baselines={"goals_total": {"global": {"mean": 3.29, "n": 55282}}},
        reliability={}, engine_constants={}, vetoes=[], config=SofaConfig(), day_obs=day)
    assert rows
    for r in rows:
        assert any(n.startswith("PRIOR_FROM_DAY_SAMPLES: competition 18643 mean 2.1 "
                                "over 40") for n in r.notes)
        assert r.centre < 2.1


def test_a_total_with_one_thin_side_is_not_priced() -> None:
    samples = _samples(1, "corners_total", _obs(range(100, 102), 5.0),
                       _obs(range(200, 209), 12.0))
    rows, skipped = process_fixture(
        make_fixture(), samples,
        make_offer([rung(7.5, 1.49, 2.50, market="corners_total")]),
        baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig())
    assert rows == []
    [(_, reason, detail)] = skipped
    assert reason.value == "THIN_SAMPLE"
    assert "side_a=2" in detail and "side_b" not in detail
