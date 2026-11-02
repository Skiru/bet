"""scripts/sofa/slip_experiment.py: the /kupon experiment harness - read set
union, the price-matched random control, the next day's grading."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from bet.sofa import slip_builder as sb
from bet.sofa.coupon_results import key_of
from scripts.sofa import slip_experiment as se

KICK = "2099-01-01T00:00:00Z"


def _leg(eid: int, odds: float, line: float = 7.5) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "group_key": f"sofa:{eid}",
        "sport": "football",
        "market": "corners_total",
        "direction": "OVER",
        "line": line,
        "offered_odds": odds,
        "confidence": 0.7,
        "kickoff_utc": KICK,
        "match": f"A{eid} - B{eid}",
        "superbet_market": "Liczba rzutów rożnych",
        "superbet_selection": f"powyżej {line}",
        "sample_size": 10,
        "sample_hit_rate": 0.8,
    }


def test_union_dedupes_and_keeps_a_match_in_one_chunk(tmp_path: Path) -> None:
    for cfg, legs in (
        ("C1", [_leg(1, 1.4), _leg(1, 1.5, 8.5)]),
        ("C2", [_leg(1, 1.4), _leg(2, 1.4), _leg(3, 1.4)]),
    ):
        d = tmp_path / "rs" / cfg
        d.mkdir(parents=True)
        (d / "read_set_slip_football.json").write_text(
            json.dumps(legs), encoding="utf-8"
        )
    written = se.union_read_sets(tmp_path, chunk=2)
    sizes = [n for _, n in written]
    assert sum(sizes) == 4  # leg (1, 7.5) read once
    first = json.loads(written[0][0].read_text(encoding="utf-8"))
    assert {g["sofascore_event_id"] for g in first} == {1}  # match 1 whole


def test_control_draw_matches_each_legs_price() -> None:
    pool = [
        sb.Leg(_leg(i, o), o, 0.7, "c")
        for i, o in enumerate([1.40, 1.41, 1.80, 1.82, 1.20, 1.95], 1)
    ]
    got = se.draw(pool, [1.40, 1.80], random.Random(1))
    assert got is not None
    assert abs(got.legs[0].odds - 1.40) <= 0.07 and abs(got.legs[1].odds - 1.80) <= 0.09
    assert len({x.match_key for x in got.legs}) == 2
    assert se.draw(pool, [3.0], random.Random(1)) is None


def test_settle_grades_slips_and_reads_the_close(tmp_path: Path) -> None:
    day = "2026-10-20"
    run = tmp_path / "runs" / day
    out = tmp_path / "exp"
    (out / "r1").mkdir(parents=True)
    run.mkdir(parents=True)
    a, b, c = _leg(1, 1.5), _leg(2, 1.4), _leg(3, 1.3)
    res = sb.Result(
        [
            sb.Slip([sb.Leg(a, 1.5, 0.66, "c"), sb.Leg(b, 1.4, 0.7, "c")]),
            sb.Slip([sb.Leg(c, 1.3, 0.7, "c")]),
        ],
        2,
        3,
    )
    rec = sb.record(
        res,
        now=sb.datetime.datetime(2026, 10, 20, tzinfo=sb.datetime.UTC),
        params={"target": 2},
    )
    (out / "r1" / "C1.json").write_text(json.dumps(rec), encoding="utf-8")
    (out / "r1" / "rs" / "C1").mkdir(parents=True)  # a read set: not a record
    (out / "r1" / "rs" / "C1" / "read_set_slip_football.json").write_text(
        json.dumps([a]), encoding="utf-8"
    )
    (run / "13_results.json").write_text(
        json.dumps(
            {
                "legs": {
                    key_of(a): {"status": "won"},
                    key_of(b): {"status": "won"},
                    key_of(c): {"status": "lost"},
                }
            }
        ),
        encoding="utf-8",
    )
    (run / "closing.jsonl").write_text(
        json.dumps(
            {
                "variant": "official",
                "leg_key": "1|corners_total||7.5|OVER",
                "odds_close": 1.25,
                "minutes_before": 5,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert (
        se.main(
            [
                "settle",
                "--date",
                day,
                "--out-dir",
                str(out),
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
        == 0
    )
    doc = json.loads((out / "settled.json").read_text(encoding="utf-8"))
    first, second = doc["graded"]
    assert first["status"] == "won" and second["status"] == "lost"
    assert abs(first["return"] - (0.88 * 1.5 * 1.4 - 1)) < 1e-9
    assert abs(first["legs"][0]["clv"] - (1.5 / 1.25 - 1)) < 1e-9
    stats = doc["summary"]["prompt (runda końcowa)"]
    assert (stats["won"], stats["lost"], stats["legs_won"], stats["legs_graded"]) == (
        1,
        1,
        2,
        3,
    )
    assert "rozliczenie" in (out / "rozliczenie.md").read_text(encoding="utf-8")


def test_prompt_legs_cover_every_config_of_the_round() -> None:
    a, b, c = _leg(1, 1.5), _leg(2, 1.4), _leg(3, 1.3)
    now = sb.datetime.datetime(2026, 10, 20, tzinfo=sb.datetime.UTC)
    r1 = sb.record(sb.Result([sb.Slip([sb.Leg(a, 1.5, 0.66, "c")])], 1, 3),
                   now=now, params={})
    r2 = sb.record(sb.Result([sb.Slip([sb.Leg(b, 1.4, 0.7, "c")])], 1, 3),
                   now=now, params={})
    # a control of C1 must not draw C2's leg either (11-01: 5 legs in both arms)
    assert se.prompt_legs([r1, r2]) == {key_of(a), key_of(b)}
    assert key_of(c) not in se.prompt_legs([r1, r2])


def _graded(eid: int, odds: float, status: str, key: str) -> dict[str, Any]:
    return {**_leg(eid, odds), "odds": odds, "status": status, "result_key": key}


def test_distinct_legs_count_a_shared_leg_once() -> None:
    lost = _graded(1, 1.5, "lost", "k1")
    rows = [{"legs": [lost, _graded(2, 1.4, "won", "k2")]}, {"legs": [lost]},
            {"legs": [lost]}]
    st = se._distinct_stats(se.distinct_legs(rows))
    assert (st["legs"], st["graded"], st["won"]) == (2, 2, 1)
    assert abs(st["excess"] - (1 - 1 / 1.5 - 1 / 1.4)) < 1e-9
    assert se._reuse(rows)["max_slips"] == 3


def test_match_bootstrap_resamples_matches_and_brackets_the_difference() -> None:
    a = [_graded(i, 2.0, "won", f"a{i}") for i in range(1, 11)]
    b = [_graded(i, 2.0, "won" if i % 2 else "lost", f"b{i}") for i in range(11, 31)]
    d = se.match_bootstrap(a, b, draws=2000)
    assert abs(d["diff"] - (0.5 - 0.0)) < 1e-9  # a: +0.5 per leg, b: 0
    assert d["lo"] <= d["diff"] <= d["hi"]
    assert d["matches"] == [10, 20]
    assert se.match_bootstrap(a, [], draws=10)["diff"] is None
