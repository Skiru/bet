"""The minute-by-minute football simulator (bet.sofa.football_sim) - a
measurement only (docs/sofa/evidence/football_sim_2026-11-06.md): readers of
the incident list, the path cut, the fit, the simulation and the markets read
off it. Offline and fast."""

from __future__ import annotations

import math
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from bet.sofa.football_sim import (
    COUNT_METRICS,
    FRAILTY_KEYS,
    GOAL_STATE,
    PATH_KINDS,
    Centres,
    MarketSim,
    MinuteMatch,
    SimParams,
    added_pmf,
    centres_from,
    fit_goal_model,
    goal_cells,
    half_state_features,
    incident_slot,
    minute_bin,
    neutral_params,
    path_actual,
    path_outcomes,
    path_segments,
    poisson_irls,
    read_added_time,
    read_minute_match,
    read_timed_goals,
    read_timed_reds,
    simulate,
)

REPO = Path(__file__).resolve().parents[2]


def _goal(
    t: int, hs: int, as_: int, added: int | None = None, cls: str = "regular"
) -> dict[str, object]:
    out: dict[str, object] = {
        "incidentType": "goal",
        "incidentClass": cls,
        "time": t,
        "homeScore": hs,
        "awayScore": as_,
        "isHome": True,
    }
    if added is not None:
        out["addedTime"] = added
    return out


def _match(**kw: object) -> MinuteMatch:
    base: dict[str, object] = dict(
        event_id=1,
        ts=0,
        competition_id=17,
        home_id=10,
        away_id=20,
        women=False,
        ft=(0, 0),
        ht=(0, 0),
        goals=(),
        reds=(),
        added=(2, 4),
        halves={},
    )
    base.update(kw)
    return MinuteMatch(**base)  # type: ignore[arg-type]


# --- readers ----------------------------------------------------------------


def test_incident_slot_reads_halves_and_added_time() -> None:
    assert incident_slot({"time": 1}) == (1, 0)
    assert incident_slot({"time": 45}) == (1, 44)
    assert incident_slot({"time": 45, "addedTime": 3}) == (1, 47)
    assert incident_slot({"time": 46}) == (2, 0)
    assert incident_slot({"time": 90, "addedTime": 2}) == (2, 46)
    # the period marker's 999 is no added time; extra time and -5 are out
    assert incident_slot({"time": 45, "addedTime": 999}) == (1, 44)
    assert incident_slot({"time": 105}) is None
    assert incident_slot({"time": -5}) is None


def test_timed_goals_follow_the_running_score_own_goal_included() -> None:
    inc = {
        "incidents": [
            _goal(80, 1, 2),
            _goal(12, 1, 0, cls="ownGoal"),
            _goal(45, 1, 1, added=2),
            {"incidentType": "period", "text": "HT", "time": 45, "addedTime": 999},
        ]
    }
    assert read_timed_goals(inc, (1, 2)) == ((1, 11, 0), (1, 46, 1), (2, 34, 1))
    # the list must end on the 90-minute score
    assert read_timed_goals(inc, (2, 2)) is None
    # a skipped running score is no timing
    bad = {"incidents": [_goal(10, 2, 0), _goal(20, 1, 0)]}
    assert read_timed_goals(bad, (2, 0)) is None
    # extra-time goals do not count
    et = {"incidents": [_goal(10, 1, 0), _goal(100, 2, 0)]}
    assert read_timed_goals(et, (1, 0)) == ((1, 9, 0),)


def test_reds_need_a_full_feed_and_drop_staff_and_rescinded() -> None:
    sub = {"incidentType": "substitution", "time": 60}
    red = {
        "incidentType": "card",
        "incidentClass": "red",
        "time": 30,
        "isHome": False,
        "player": {"id": 1},
    }
    two = {
        "incidentType": "card",
        "incidentClass": "yellowRed",
        "time": 90,
        "addedTime": 1,
        "isHome": True,
        "player": {"id": 2},
    }
    staff = {
        "incidentType": "card",
        "incidentClass": "red",
        "time": -5,
        "isHome": True,
        "manager": {"id": 3},
    }
    gone = {**red, "rescinded": True}
    assert read_timed_reds({"incidents": [red]}) is None
    assert read_timed_reds({"incidents": [sub, red, two, staff, gone]}) == (
        (1, 29, 1),
        (2, 45, 0),
    )


def test_added_time_is_the_announcement_or_later_play() -> None:
    inc = {
        "incidents": [
            {"incidentType": "injuryTime", "time": 45, "length": 2},
            {"incidentType": "injuryTime", "time": 90, "length": 4},
            _goal(90, 1, 0, added=6),
        ]
    }
    assert read_added_time(inc) == (2, 6)
    assert read_added_time({"incidents": [_goal(90, 1, 0, added=6)]}) == (None, None)


def test_read_minute_match_rejects_a_half_time_contradiction() -> None:
    result = SimpleNamespace(
        event_id=5,
        ts=1,
        competition_id=17,
        home_id=1,
        away_id=2,
        women=False,
        values={"goals_for": (1.0, 0.0), "goals_1h_for": (0.0, 0.0)},
    )
    inc = {"incidents": [_goal(20, 1, 0)]}
    m = read_minute_match(result, None, inc)
    assert m is not None and m.goals is None and m.ft == (1, 0) and m.ht == (0, 0)


# --- path cut and features ---------------------------------------------------


def test_path_segments_cut_at_each_event_and_keep_added_time() -> None:
    m = _match(
        ft=(1, 1),
        ht=(1, 0),
        goals=((1, 9, 0), (2, 30, 1)),
        reds=((2, 10, 1),),
        added=(2, 4),
    )
    segs = path_segments(m)
    assert [(s.half, s.start, s.end, s.goals, s.reds) for s in segs] == [
        (1, 0, 10, (0, 0), (0, 0)),
        (1, 10, 47, (1, 0), (0, 0)),
        (2, 0, 11, (1, 0), (0, 0)),
        (2, 11, 31, (1, 0), (0, 1)),
        (2, 31, 49, (1, 1), (0, 1)),
    ]
    f = half_state_features(m)
    # home led 37 of 47 first-half minutes
    assert f[0, 0, 1] == pytest.approx(37 / 47)
    assert f[0, 1, 0] == pytest.approx(37 / 47)
    assert f[1, 0, 3] == pytest.approx(38 / 49)  # away's red for 38 of 49
    assert f[1, 1, 4] == 1 and f[1, 0, 5] == 1  # goals for / against in 2H


def test_minute_bins() -> None:
    assert [minute_bin(1, m) for m in (0, 14, 15, 44, 45, 50)] == [0, 0, 1, 2, 3, 3]
    assert [minute_bin(2, m) for m in (0, 29, 30, 46)] == [4, 5, 6, 7]


# --- fit ---------------------------------------------------------------------


def test_poisson_irls_recovers_coefficients() -> None:
    rng = np.random.default_rng(3)
    x = np.column_stack([np.ones(20000), rng.integers(0, 2, 20000)])
    off = np.log(rng.uniform(0.5, 2.0, 20000))
    y = rng.poisson(np.exp(off + x @ np.array([0.3, -0.4])))
    beta, se = poisson_irls(x, y.astype(float), off)
    assert beta[0] == pytest.approx(0.3, abs=4 * se[0])
    assert beta[1] == pytest.approx(-0.4, abs=4 * se[1])


def test_goal_cells_count_every_goal_at_its_pre_goal_state() -> None:
    m = _match(
        ft=(2, 0), ht=(1, 0), goals=((1, 5, 0), (2, 40, 0)), reds=(), added=(0, 0)
    )
    cells = goal_cells([(m, (1.8, 0.9))])
    assert sum(cells.events.values()) == 2
    # the first at 0-0, the second with home a goal up after the 70th minute
    assert cells.events[(0, 0, 0, 0, 0)] == 1
    assert cells.events[(6, 1, 1, 0, 0)] == 1
    # exposure: 90 minutes a side at mu / 90
    home = sum(v for k, v in cells.exposure.items())
    assert home == pytest.approx((1.8 + 0.9) / 90 * 90)
    prof, state, _ = fit_goal_model(cells)
    assert len(prof) == 8 and set(state) == set(GOAL_STATE)


def test_added_pmf_caps_and_normalises() -> None:
    ms = [_match(added=(1, 30)), _match(added=(None, 4))]
    first, second = added_pmf(ms)
    assert sum(first) == pytest.approx(1.0) and first[1] == 1.0
    assert second[4] == pytest.approx(0.5) and second[-1] == pytest.approx(0.5)


def test_params_round_trip() -> None:
    p = neutral_params()
    assert SimParams.from_json(p.to_json()) == p
    assert len(p.frailty_cov) == len(FRAILTY_KEYS) == 2 * len(COUNT_METRICS)


# --- simulation --------------------------------------------------------------


def _centres() -> Centres:
    return Centres(
        goals=(1.6, 1.0),
        halves={
            "corners": ((2.5, 2.0), (2.8, 2.2)),
            "cards_points": ((1.0, 1.1), (1.4, 1.5)),
        },
        cards=(2.4, 2.6),
    )


def test_neutral_simulation_is_poisson_at_the_centres() -> None:
    res = simulate(neutral_params(), _centres(), n=20000, seed=7)
    fh = res.goals[0, 0] + res.goals[1, 0]
    fa = res.goals[0, 1] + res.goals[1, 1]
    assert fh.mean() == pytest.approx(1.6, abs=0.04)
    assert fa.mean() == pytest.approx(1.0, abs=0.03)
    assert (fh == 0).mean() == pytest.approx(math.exp(-1.6), abs=0.01)
    assert res.counts["corners"][1, 0].mean() == pytest.approx(2.8, abs=0.06)
    again = simulate(neutral_params(), _centres(), n=20000, seed=7)
    assert np.array_equal(res.goals, again.goals)


def test_a_red_card_moves_the_goals() -> None:
    p = neutral_params()
    hot = SimParams.from_json(
        {
            **p.to_json(),
            "red_profile": [math.log(0.2)] * 8,
            "goal_state": {**p.goal_state, "own_red": -1.0, "opp_red": 0.5},
        }
    )
    res = simulate(hot, _centres(), n=4000, seed=1)
    assert res.reds.sum() > 0
    reds_home = res.reds[:, 0].sum(axis=0) > 0
    assert 0.2 < reds_home.mean() < 0.8
    fh = res.goals[0, 0] + res.goals[1, 0]
    assert fh[reds_home].mean() < fh[~reds_home].mean()


def test_card_points_carry_two_per_dismissal() -> None:
    p = neutral_params()
    no_cards = SimParams.from_json({**p.to_json(), "red_profile": [math.log(3.0)] * 8})
    c = Centres(
        goals=(1.0, 1.0),
        halves={"cards_points": ((1e-9, 1e-9), (1e-9, 1e-9))},
        cards=(2.0, 2.0),
    )
    res = simulate(no_cards, c, n=2000, seed=2)
    assert np.array_equal(res.counts["cards_points"], 2 * res.reds)


def test_centres_from_needs_goals_and_splits_match_centres() -> None:
    assert centres_from({"corners_1h_for": (2.0, 2.0)}) is None
    c = centres_from(
        {
            "goals_for": (1.2, 0.8),
            "fouls_for": (12.0, 10.0),
            "corners_1h_for": (2.0, 1.5),
            "corners_2h_for": (2.4, 1.8),
        }
    )
    assert c is not None
    assert c.halves["fouls"] == ((6.0, 5.0), (6.0, 5.0))
    assert c.halves["corners"] == ((2.0, 1.5), (2.4, 1.8))
    assert c.cards is None


# --- markets -------------------------------------------------------------------


def test_market_selections_are_consistent() -> None:
    ms = MarketSim(simulate(neutral_params(), _centres(), n=4000, seed=3))
    p1 = ms.p(ms.selection("result_1x2", "1", 0.5, "OVER", None))
    px = ms.p(ms.selection("result_1x2", "X", 0.5, "OVER", None))
    p2 = ms.p(ms.selection("result_1x2", "2", 0.5, "OVER", None))
    assert p1 is not None and px is not None and p2 is not None
    assert p1 + px + p2 == pytest.approx(1.0)
    assert ms.p(
        ms.selection("double_chance", "X2", 0.5, "OVER", None)
    ) == pytest.approx(px + p2)
    over = ms.p(ms.selection("goals_total", "", 2.5, "OVER", None))
    under = ms.p(ms.selection("goals_total", "", 2.5, "UNDER", None))
    assert over is not None and under is not None and over + under == pytest.approx(1.0)
    # a team market needs its side
    assert ms.selection("corners_for", "x", 2.5, "OVER", None) is None
    hcp = ms.p(ms.selection("handicap_corners", "x", 1.5, "OVER", 1))
    v = ms.value("corners", 2, 0)
    w = ms.value("corners", 2, 1)
    assert (
        v is not None
        and w is not None
        and hcp == pytest.approx(float(np.mean(w + 1.5 > v)))
    )
    ev = ms.selection("draw_no_bet", "1", 0.5, "OVER", None)
    assert ev is not None
    assert ms.conditional_p("draw_no_bet", ev) == pytest.approx(p1 / (p1 + p2))
    btts = ms.p(ms.selection("both_over_goals", "", 0.5, "OVER", None))
    fh, fa = ms.ft()
    assert btts == pytest.approx(float(np.mean((fh > 0) & (fa > 0))))
    # SHEET's first_goal rows name the side "1" / "2" (or "nikt")
    first = [
        ms.p(ms.selection("first_goal", s, 0.5, "OVER", None))
        for s in ("1", "2", "nikt")
    ]
    assert all(x is not None for x in first)
    assert sum(x or 0.0 for x in first) == pytest.approx(1.0)
    assert first[2] == pytest.approx(float(np.mean((fh == 0) & (fa == 0))))


@pytest.mark.parametrize(
    "kind,param",
    [
        ("htft", None),
        ("half_result", 1),
        ("half_result", 2),
        ("higher_half", None),
        ("team_both_halves", 0),
        ("btts_halves", None),
        ("btts_any_half", None),
        ("half_totals", (0.5, 1.5)),
        ("first_goal_band15", None),
        ("first_goal_1h", None),
        ("last_goal", None),
        ("odd_even", None),
        ("exact_goals", None),
        ("correct_score", 0),
    ],
)
def test_path_outcomes_are_exclusive_and_exhaustive(kind: str, param: object) -> None:
    assert kind in PATH_KINDS
    ms = MarketSim(simulate(neutral_params(), _centres(), n=3000, seed=4))
    out = path_outcomes(ms, kind, param)
    total = np.zeros(3000, dtype=np.int64)
    for v in out.values():
        total += v.astype(np.int64)
    assert np.all(total == 1)


def test_path_actual_grades_a_finished_match() -> None:
    m = _match(
        ft=(2, 1),
        ht=(0, 1),
        goals=((1, 20, 1), (2, 10, 0), (2, 46, 0)),
        reds=(),
        added=(1, 5),
    )
    assert path_actual(m, "htft") == "2/1"
    assert path_actual(m, "half_result", 1) == "2"
    assert path_actual(m, "half_result", 2) == "1"
    assert path_actual(m, "higher_half") == "2H"
    assert path_actual(m, "team_both_halves", 0) == "nie"
    assert path_actual(m, "btts_halves") == "Nie/Nie"
    assert path_actual(m, "half_totals", (0.5, 1.5)) == "O/O"
    assert path_actual(m, "first_goal_band15") == "1"
    assert path_actual(m, "first_goal_1h") == "2"
    assert path_actual(m, "last_goal") == "1"
    assert path_actual(m, "exact_goals") == "3"
    assert path_actual(m, "correct_score", 2) == "2:1"
    # second-half added time stays in the last band
    late = _match(ft=(1, 0), ht=(0, 0), goals=((2, 47, 0),), added=(0, 6))
    assert path_actual(late, "first_goal_band15") == "5"
    # without timed goals the timing kinds are not graded
    untimed = _match(ft=(1, 0), ht=(1, 0), goals=None)
    assert path_actual(untimed, "first_goal_band15") is None
    assert path_actual(untimed, "htft") == "1/1"


def test_simulated_first_goal_band_matches_the_reader() -> None:
    """The simulator's band of a first-half added-time goal is band 2, as the
    reader grades it."""
    p = neutral_params()
    pmf = tuple(1.0 if k == 10 else 0.0 for k in range(len(p.added_pmf[0])))
    params = SimParams.from_json({**p.to_json(), "added_pmf": [list(pmf), list(pmf)]})
    res = simulate(
        params, Centres(goals=(4.0, 4.0), halves={}, cards=None), n=500, seed=9
    )
    fm = res.first_goal_minute
    first_half = res.goals[0].sum(axis=0) > 0
    # a first goal of the first half (added time included) stays below 45
    assert np.all(fm[first_half] < 45)
    assert np.nanmax(fm) < 90


def test_no_pipeline_stage_reads_the_simulator() -> None:
    """A measurement only: nothing but its own measurement script and this
    test imports bet.sofa.football_sim."""
    pat = re.compile(r"\bfootball_sim\b")
    allowed = {
        REPO / "src/bet/sofa/football_sim.py",
        REPO / "scripts/sofa/measure_football_sim.py",
    }
    hits = [
        p
        for root in (REPO / "src/bet/sofa", REPO / "scripts/sofa")
        for p in root.rglob("*.py")
        if p not in allowed
        and pat.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert hits == []


def test_measurement_reads_team_markets_only_and_skips_a_scoreless_result() -> None:
    from scripts.sofa import measure_football_sim as msr

    # a player prop is not a team count ("player_shots_for" holds "shots")
    assert msr.live_family("player_shots_for") is None
    assert msr.live_family("player_fouls_drawn_for") is None
    assert msr.live_family("shots_for") == "c8_shots"
    assert msr.live_family("corners_1h_total") == "c5_corners"
    # a result parsed from /event without a 90-minute score has no path
    r = SimpleNamespace(
        event_id=1,
        ts=0,
        competition_id=1,
        home_id=1,
        away_id=2,
        women=False,
        values={},
    )
    assert msr.minute_match_of(r, {}) is None
