"""The families the first sport allow-list left out (operator, 2026-10-07):
quarters, second half, dnb, odd/even and player lines, from the line-evidence
epoch only."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import shadow
from bet.sofa import sport_confidence as scf
from bet.sofa import sport_day as sd
from bet.sofa.score_model import line_probability
from bet.sofa.shadow import ShadowLine
from tests.sofa.coupon_fixtures import DATE

REPO = Path(__file__).resolve().parents[2]
BASKETBALL = shadow.SPORTS["basketball"]


def _rsc() -> Any:
    spec = importlib.util.spec_from_file_location(
        "run_sport_confidence", REPO / "scripts/sofa/run_sport_confidence.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_sport_confidence"] = mod
    spec.loader.exec_module(mod)
    return mod


def _game(q1: tuple[int, int], q2: tuple[int, int], q3: tuple[int, int],
          q4: tuple[int, int]) -> shadow.GameResult:
    t1 = (q1[0], q2[0], q3[0], q4[0])
    t2 = (q1[1], q2[1], q3[1], q4[1])
    winner = "T1" if sum(t1) > sum(t2) else "T2"
    return shadow.GameResult(t1, t2, sum(t1), sum(t2), winner, False)


def test_player_lines_are_allowed_only_under_the_evidence() -> None:
    assert scf.family_of("basketball", 233565, "player_points") is None
    assert scf.family_of("basketball", 233565, "player_points",
                         extended=True) == "player_points"
    assert scf.family_of("hockey", 230026, "player_goalie_saves",
                         extended=True) == "player_goalie_saves"


def test_dnb_and_parity_have_synthetic_lines_the_model_grades() -> None:
    sims = [_game((20, 18), (22, 20), (19, 21), (20, 20)),
            _game((25, 15), (20, 22), (18, 18), (21, 19))]
    dnb = scf.synthetic_lines(BASKETBALL, 772, sims, period=4)
    assert [(ln.side, ln.line, ln.period) for ln in dnb] == [
        ("T1", None, 4), ("T2", None, 4)]
    # Q4: 20-20 (a draw, void) and 21-19 (T1)
    assert line_probability(dnb[0], sims, BASKETBALL) == 1.0
    parity = scf.synthetic_lines(BASKETBALL, 775, sims)
    assert [ln.side for ln in parity] == ["ODD", "EVEN"]
    # totals 160 and 158: both even
    assert line_probability(parity[1], sims, BASKETBALL) == 1.0
    assert scf.curve_key("odd_even", "EVEN") == "odd_even|EVEN"


def test_pregame_player_p_is_the_newest_before_the_build(tmp_path: Path) -> None:
    rsc = _rsc()
    day = shadow.shadow_day_dir(str(tmp_path), "basketball", DATE)
    day.mkdir(parents=True)
    base = {"superbet_event_id": "7", "market_id": 233565, "subject": "Doe, J",
            "line": 18.5, "side": "OVER"}
    rows = [{**base, "fetched_at_utc": "2026-10-03T08:00:00Z", "model_p": 0.61},
            {**base, "fetched_at_utc": "2026-10-03T09:00:00Z", "model_p": 0.66},
            {**base, "fetched_at_utc": "2026-10-03T11:00:00Z", "model_p": 0.70},
            {**base, "side": "UNDER", "fetched_at_utc": "2026-10-03T09:00:00Z",
             "model_p": None}]
    (day / "player_model.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    at = datetime(2026, 10, 3, 10, 0, tzinfo=UTC)
    got = rsc.pregame_player_p(str(tmp_path), "basketball", DATE, at)
    assert got == {("7", 233565, "Doe, J", 18.5, "OVER"): 0.66}


def test_a_player_leg_takes_the_settled_player_line() -> None:
    graded = [{"market_id": 233565, "family": "player_points", "subject": "Doe, J",
               "line": 18.5, "side": "OVER", "outcome": "LOSS", "odds": 1.8}]
    ev = {"state": "SETTLED", "t1_periods": [20, 20, 20, 20],
          "t2_periods": [18, 18, 18, 18], "t1_full": 80, "t2_full": 72,
          "overtime": False, "graded": graded}
    leg = {"superbet_event_id": "7", "market_id": 233565,
           "family": "player_points", "period": 0, "subject": "Doe, J",
           "line": 18.5, "side": "OVER", "odds": 1.85, "kickoff_utc":
           "2026-10-03T18:00:00Z"}
    coupon = {"sport": "basketball", "date": DATE, "legs": [leg]}
    [g] = sd.grade_legs(coupon, {DATE: {"events": {"7": ev}}})
    assert g["outcome"] == "LOSS" and g["odds"] == 1.85
    other = {**leg, "subject": "Roe, K"}
    [g] = sd.grade_legs({**coupon, "legs": [other]}, {DATE: {"events": {"7": ev}}})
    assert g["outcome"] == "UNGRADEABLE"


def test_a_q4_or_second_half_leg_grades_on_regulation_in_overtime() -> None:
    line = ShadowLine("7", 233404, "h2_total", 0, "", 80.5, "OVER", 1.9)
    result = shadow.GameResult((20, 20, 20, 20, 10), (20, 20, 20, 20, 8),
                               90, 88, "T1", True)
    # overtime does not count (operator, 2026-10-07): periods 3 + 4 only
    assert shadow.actual_value(line, result, BASKETBALL) == 80.0 + 0.0 + 40.0 - 40.0
    q4 = ShadowLine("7", 788, "quarter_total", 4, "", 30.5, "OVER", 1.9)
    assert shadow.actual_value(q4, result, BASKETBALL) == 40.0


VOLLEYBALL = shadow.SPORTS["volleyball"]


def _vb(*sets: tuple[int, int]) -> shadow.GameResult:
    t1 = tuple(a for a, _ in sets)
    t2 = tuple(b for _, b in sets)
    s1 = sum(1 for a, b in sets if a > b)
    return shadow.GameResult(t1, t2, sum(t1), sum(t2),
                             "T1" if s1 > len(sets) - s1 else "T2", False)


def test_volleyball_exact_score_and_extra_points_lines() -> None:
    sims = [_vb((25, 20), (25, 22), (25, 18)),            # 3:0
            _vb((25, 20), (23, 25), (25, 18), (26, 24)),  # 3:1, set 4 on extra points
            _vb((20, 25), (25, 22), (18, 25), (22, 25))]  # 1:3
    exact = scf.synthetic_lines(VOLLEYBALL, 785, sims)
    assert sorted(ln.side for ln in exact) == ["1:3", "3:0", "3:1"]
    p30 = line_probability(next(ln for ln in exact if ln.side == "3:0"), sims,
                           VOLLEYBALL)
    assert p30 is not None and abs(p30 - 1 / 3) < 1e-9
    extra = scf.synthetic_lines(VOLLEYBALL, 100077, sims, period=4)
    assert [ln.side for ln in extra] == ["YES", "NO"]
    # set 4 played in two of three games, on extra points in one
    assert line_probability(extra[0], sims, VOLLEYBALL) == 0.5
    assert scf.curve_key("exact_sets", "3:1") == "exact_sets|3:1"
    assert scf.curve_key("set_extra_points", "YES") == "set_extra_points|YES"
    assert {"set_points_odd_even", "set_extra_points"} <= \
        scf.SETTLED_ONLY_FAMILIES["volleyball"]
    assert "exact_sets" not in scf.SETTLED_ONLY_FAMILIES["volleyball"]


def test_shadow_reads_the_pinned_teams_of_identified_games(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "run_shadow", REPO / "scripts/sofa/run_shadow.py")
    assert spec and spec.loader
    rs = importlib.util.module_from_spec(spec)
    sys.modules["run_shadow"] = rs
    spec.loader.exec_module(rs)
    day = tmp_path / "2026-10-08"
    day.mkdir()
    (day / "sport_fixtures.json").write_text(json.dumps({"fixtures": [
        {"sport": "basketball", "superbet_event_id": "7", "status": "IDENTIFIED",
         "home_id": 11, "away_id": 22, "home_is_team1": False},
        {"sport": "basketball", "superbet_event_id": "8", "status": "NOT_IDENTIFIED"},
        {"sport": "hockey", "superbet_event_id": "9", "status": "IDENTIFIED",
         "home_id": 1, "away_id": 2, "home_is_team1": True}]}))
    # the snapshot day 10-07 reads its neighbour 10-08 (a loop pins D and D+1)
    assert rs.pinned_teams(str(tmp_path), "basketball", "2026-10-07") == {
        "7": (22, 11)}
    assert rs.pinned_teams(str(tmp_path), "hockey", "2026-10-08") == {"9": (1, 2)}


def test_a_pinned_game_is_priced_without_resolving_names() -> None:
    from bet.sofa import player_model as pm

    class NoDb:
        def execute(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("names must not be resolved for a pinned game")

    calls: list[Any] = []
    orig = pm.load_appearances
    pm.load_appearances = lambda conn, sport, teams, before, ex: (  # type: ignore[assignment]
        calls.append(teams) or [])
    try:
        rec = {"superbet_event_id": "7", "kickoff_utc": "2026-10-08T18:00:00Z",
               "fetched_at_utc": "2026-10-08T10:00:00Z", "team1": "A", "team2": "B",
               "lines": [{"market_id": 233565, "family": "player_points",
                          "subject": "Doe, J", "line": 10.5, "side": "OVER",
                          "odds": 1.9},
                         {"market_id": 233565, "family": "player_points",
                          "subject": "Doe, J", "line": 10.5, "side": "UNDER",
                          "odds": 1.9}]}
        rows = pm.forecast_records(NoDb(), "basketball", "basketball", [rec],  # type: ignore[arg-type]
                                   "x", set(), 0, None, {"7": (22, 11)})
    finally:
        pm.load_appearances = orig  # type: ignore[assignment]
    assert calls == [[22, 11]]
    assert {r["teams_source"] for r in rows} == {"pinned"}
    assert {r["teams_resolved"] for r in rows} == {2}


def test_the_stage_reads_the_extended_cs2_families_under_the_evidence() -> None:
    # e2e 2026-10-07 found _allowed dropping `extended` for CS2: 1,682 lines
    # stayed MARKET_NOT_ALLOWED although family_of allowed them.
    from bet.sofa.cs2 import Cs2Line

    rsc = _rsc()
    ln = Cs2Line("e", "map_rounds_total", 1, "", 21.5, "OVER", 1.8)
    assert rsc._allowed("cs2", ln) is None
    assert rsc._allowed("cs2", ln, True) == "map_rounds_total"
    series = Cs2Line("e", "maps_total", 0, "", 2.5, "OVER", 1.8)
    assert rsc._allowed("cs2", series, True) == "maps_total"
    rounds = Cs2Line("e", "rounds_total", 0, "", 44.5, "OVER", 1.8)
    assert rsc._allowed("cs2", rounds, True) is None



def test_basketball_aliases_checked_against_the_listing_2026_10_07() -> None:
    # each pair checked by hand against Sofascore's listing of 10-07
    from bet.sofa.names import normalize_name as n

    assert n("iLab") == n("Sigortam.net Itu BB")
    assert n("ToPo (K)") == "torpan pojat (w)"
    assert n("Marko Topo") == "marko topo"  # the tennis player keeps his name
    assert n("U BT Cluj").startswith("u banca transilvania cluj")
    assert n("TTU Korvpalliklubi") == "taltech"


def test_the_series_mixture_is_a_distribution_and_tends_to_independent_maps() -> None:
    from bet.sofa import cs2_engine as eng

    for bo in (2, 3, 5):
        mixed = eng.series_distribution_mixed(0.62, bo)
        assert abs(sum(mixed.values()) - 1.0) < 1e-9
        indep = eng.series_distribution(0.62, bo)
        far = eng.series_distribution_mixed(0.62, bo, kappa=1e7)
        assert all(abs(far[k] - indep[k]) < 1e-5 for k in indep)
    # correlated maps: fewer deciders than independent ones
    assert (eng.series_distribution_mixed(0.5, 3)[(2, 1)]
            < eng.series_distribution(0.5, 3)[(2, 1)])


def test_historical_series_rows_price_as_the_live_engine() -> None:
    from bet.sofa import cs2_engine as eng

    srow = scf.SeriesRow(1, 0, 10, 20, 2, 1, 3)
    rows = scf._cs2_series_family_rows(1, 0, srow, 0.6, "history_fit")
    by = {(r["family"], r["line"], r["side"], r["subject"]): r for r in rows}
    mixed = eng.series_distribution_mixed(0.6, 3)
    over = by[("maps_total", 2.5, "OVER", "")]
    assert over["y"] == 1 and over["p"] == round(mixed[(2, 1)] + mixed[(1, 2)], 4)
    assert by[("exact_maps", None, "2:1", "")]["y"] == 1
    assert by[("exact_maps", None, "2:0", "")]["y"] == 0
    assert by[("maps_handicap", -1.5, "T1", "")]["y"] == 0   # 2-1 does not cover -1.5
    assert by[("team_maps", 0.5, "OVER", "T2")]["y"] == 1    # team2 took a map
