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


def test_a_q4_or_second_half_leg_says_overtime_is_unknown() -> None:
    line = ShadowLine("7", 233404, "h2_total", 0, "", 80.5, "OVER", 1.9)
    result = shadow.GameResult((20, 20, 20, 20, 10), (20, 20, 20, 20, 8),
                               90, 88, "T1", True)
    assert shadow.actual_value(line, result, BASKETBALL) is None
    assert scf.ot_rule_unknown("basketball", "h2_total", 0)
