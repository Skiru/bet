"""measure_price_edge.py (edge / CLV pockets, 2026-11-20): the fair price at the
taken odds, the frozen bands, the match bootstrap, the dev-candidate ->
Bonferroni hold-out rule, BH, the closing key, a day's legs joined from day
files, and the protocol seal. Report:
docs/sofa/evidence/przewaga_nad_cena_2026-11-20.md."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from bet.sofa.coupon_results import key_of
from bet.sofa.engine import devig
from scripts.sofa import capture_closing
from scripts.sofa import measure_price_edge as m


def test_bands_and_tts() -> None:
    assert m.band(-0.2) == "<-0.05"
    assert m.band(-0.05) == "-0.05..-0.02"
    assert m.band(0.0) == "0..0.03"
    assert m.band(0.06) == ">=0.06"
    assert m.tts_bucket(None) is None
    assert m.tts_bucket(0.5) == "<1"
    assert m.tts_bucket(12.0) == ">=12"
    assert m.hours_to_start("2026-11-10T10:00:00+00:00", "2026-11-10T13:30:00Z") == 3.5


def test_split() -> None:
    assert m.split_of("2026-10-13") == "dev"
    assert m.split_of("2026-11-09") == "dev"
    assert m.split_of("2026-11-10") == "hold"
    assert m.split_of("2026-11-20") is None


def test_fair_football_moves_to_taken_price() -> None:
    assert m.fair_football(0.80, 1.20, 1.20) == pytest.approx(0.80)
    # the fair / implied ratio is kept when the taken price differs
    assert m.fair_football(0.80, 1.20, 1.25) == pytest.approx(0.80 * 1.20 / 1.25)
    assert m.fair_football(None, 1.20, 1.2) is None
    assert m.fair_football(0.8, 1.0, 1.2) is None


def test_fair_two_way_rebuilds_the_partner() -> None:
    odds, partner = 1.20, 4.10
    ov = 1 / odds + 1 / partner - 1
    pair = devig(odds, partner)
    assert pair is not None
    assert m.fair_two_way(odds, ov) == pytest.approx(pair[0], abs=1e-9)
    assert m.fair_two_way(1.2, None) is None
    assert m.fair_two_way(1.2, 1.0) is None  # partner implied >= 1


def test_closing_key_matches_capture_closing() -> None:
    leg = {
        "sofascore_event_id": 5,
        "market": "goals_total",
        "subject": None,
        "line": 2.5,
        "direction": "OVER",
    }
    assert m.closing_leg_key(leg) == capture_closing.leg_key(leg)


def test_print_file_timestamp() -> None:
    ts = m.ts_of_print_file("20261020T063446.785577Z.json")
    assert ts == "2026-10-20T06:34:46+00:00"
    assert m.ts_of_print_file("junk.json") is None


def test_cell_key_needs_every_dimension() -> None:
    leg = {"priced": "fair", "sport": "football", "md": "x|OVER", "tts": None}
    assert m.cell_key(leg, ("sport", "md")) == ("fair", "football", "x|OVER")
    assert m.cell_key(leg, ("sport", "tts")) is None


def test_bootstrap_is_cluster_weighted_and_seeded() -> None:
    vals = [1.0, 1.0, 0.0, 0.0]
    cl = ["a", "a", "b", "b"]
    b1 = m.bootstrap(vals, cl, 500, np.random.default_rng(1))
    b2 = m.bootstrap(vals, cl, 500, np.random.default_rng(1))
    assert np.array_equal(b1, b2)
    # whole matches only: a resample holds 0, 1 or 2 copies of "a"
    assert set(np.round(b1, 6)) <= {0.0, 0.5, 1.0}


def test_bh() -> None:
    assert m.bh([0.001, 0.2, 0.03, 0.5], 0.10) == [True, False, True, False]
    assert m.bh([0.9, 0.8], 0.10) == [False, False]


def _leg(
    i: int, split: str, edge: float, sport: str = "football", md: str = "a|OVER"
) -> dict[str, Any]:
    return {
        "split": split,
        "eid": i,
        "sport": sport,
        "md": md,
        "comp": "L",
        "band": "0..0.03",
        "tts": "3-6",
        "priced": "fair",
        "over": "tak",
        "edge": edge,
        "win": 1,
        "conf": 0.8,
        "odds": 1.2,
        "fair_p": 0.8,
        "roi": 0.2,
    }


def test_evaluate_candidate_then_bonferroni() -> None:
    rng = np.random.default_rng(0)
    legs = []
    for i in range(400):  # a clearly positive cell in both splits
        legs.append(_leg(i, "dev", 0.3 if i % 5 else -0.7, md="good|OVER"))
        legs.append(_leg(10_000 + i, "hold", 0.3 if i % 5 else -0.7, md="good|OVER"))
    for i in range(400):  # noise around zero
        e = 0.2 if i % 2 else -0.2
        legs.append(_leg(20_000 + i, "dev", e, md="noise|OVER"))
        legs.append(_leg(30_000 + i, "hold", e, md="noise|OVER"))
    out = m.evaluate(legs, "edge", rng)
    passed = {tuple(r["cell"]) for r in out["passed"]}
    assert ("fair", "football", "good|OVER") in passed
    assert all("noise|OVER" not in r["cell"] for r in out["passed"])
    assert out["candidates_tested_hold"] >= 1
    k = out["candidates_tested_hold"]
    assert out["bonferroni_level"] == pytest.approx(1 - 0.05 / k)


def test_evaluate_needs_300_on_holdout() -> None:
    rng = np.random.default_rng(0)
    legs = [_leg(i, "dev", 0.2) for i in range(400)]
    legs += [_leg(10_000 + i, "hold", 0.2) for i in range(100)]
    out = m.evaluate(legs, "edge", rng)
    assert out["candidates_dev"] > 0
    assert out["candidates_tested_hold"] == 0
    assert out["passed"] == []


def test_load_day_joins_results_coupon_and_close(tmp_path: Path) -> None:
    day = "2026-11-12"
    d = tmp_path / day
    (d / "printed").mkdir(parents=True)
    fb = {
        "sofascore_event_id": 7,
        "sport": "football",
        "market": "goals_total",
        "subject": "",
        "line": 2.5,
        "direction": "OVER",
        "confidence": 0.8,
        "offered_odds": 1.25,
        "market_p": 0.76,
        "competition": "Liga",
        "kickoff_utc": "2026-11-12T18:00:00Z",
    }
    one = {
        **fb,
        "market": "player_shots",
        "subject": "x",
        "line": 0.5,
        "market_p": None,
    }
    k1, k2 = key_of(fb), key_of(one)
    (d / "11_coupon.json").write_text(json.dumps({"singles": [fb, one]}))
    (d / "printed" / "20261112T120000.000000Z.json").write_text(
        json.dumps({"singles": [fb]})
    )
    (d / "13_results.json").write_text(
        json.dumps(
            {
                "legs": {
                    k1: {
                        "status": "won",
                        "sport": "football",
                        "confidence": 0.8,
                        "odds": 1.25,
                    },
                    k2: {
                        "status": "lost",
                        "sport": "football",
                        "confidence": 0.75,
                        "odds": 1.4,
                    },
                }
            }
        )
    )
    close = {
        "variant": "official",
        "leg_key": m.closing_leg_key(fb),
        "sofascore_event_id": 7,
        "odds_taken": 1.25,
        "odds_close": 1.20,
        "partner_close": 4.2,
        "fetched_at_utc": "2026-11-12T17:50:00+00:00",
        "minutes_before": 10.0,
    }
    (d / "closing.jsonl").write_text(json.dumps(close) + "\n")
    stats: dict[str, Any] = {
        "days_with_11_coupon": [],
        "days_without_11_coupon": [],
        "results_status": defaultdict(int),
        "no_leg_fields": defaultdict(int),
        "no_odds_or_conf": defaultdict(int),
    }
    legs = {r["md"]: r for r in m.load_day(tmp_path, day, stats)}
    a = legs["goals_total|OVER"]
    assert a["priced"] == "fair" and a["fair_p"] == pytest.approx(0.76)
    assert a["edge"] == pytest.approx(1 - 0.76)
    assert a["tts"] == "6-12" and a["band"] == "0..0.03"
    pair = devig(1.20, 4.2)
    assert pair is not None
    assert a["clv"] == pytest.approx(1.25 * pair[0] - 1)
    b = legs["player_shots|OVER"]
    assert b["priced"] == "raw" and b["edge"] == pytest.approx(0 - 1 / 1.4)
    assert b["over"] is None and "clv" not in b


def test_protocol_seal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m, "PROTOCOL_SHA256", "0" * 64)
    with pytest.raises(SystemExit):
        m.check_protocol()


def test_forward_cells_are_well_formed() -> None:
    assert len(m.FORWARD_CELLS) == 20
    for spec in m.FORWARD_CELLS:
        fam = spec[0]
        assert fam in m.FAMILIES
        assert len(spec) == 2 + len(m.FAMILIES[fam])  # family, priced, dims
    assert m.FORWARD_CELLS_LEVEL == pytest.approx(1 - 0.05 / 20)


def _fwd(i: int, edge: float, kickoff: str) -> dict[str, Any]:
    return {
        **_leg(i, "x", edge),
        "kickoff": kickoff,
        "day": kickoff[:10],
        "split": None,
    }


def test_forward_judges_once_on_the_first_300_in_kickoff_order() -> None:
    rng = np.random.default_rng(0)
    few = [_fwd(i, 0.3, "2026-11-21T12:00:00Z") for i in range(299)]
    assert m.judge(few, "edge", 0.95, rng)["status"] == "PENDING"
    good = [_fwd(i, 0.3 if i % 5 else -0.7, "2026-11-21T12:00:00Z") for i in range(300)]
    # later legs, all lost, never change the verdict
    late = [_fwd(10_000 + i, -1.0, "2026-12-01T12:00:00Z") for i in range(300)]
    res = m.judge(late + good, "edge", 0.95, rng)
    assert res["status"] == "PASSED" and res["n_seen"] == 600
    assert res["last_kickoff"] == "2026-11-21T12:00:00Z"
    assert res["roi_after_tax"] == pytest.approx(
        sum(0.88 * r["odds"] * r["win"] - 1 for r in good) / 300
    )


def test_forward_volleyball_reads_the_raw_price() -> None:
    rng = np.random.default_rng(0)
    legs = [
        {
            **_fwd(i, 0.0, "2026-11-22T10:00:00Z"),
            "sport": "volleyball",
            "odds": 1.25,
            "win": 1 if i % 5 else 0,
        }
        for i in range(300)
    ]
    out = m.forward_volleyball(legs, rng)
    assert out["mean"] == pytest.approx(0.8 - 1 / 1.25)
    assert out["verdict"] == "NOT_PASSED"


def test_forward_refuses_data_before_registration(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        m.run_forward(tmp_path, "cells", "2026-11-20", "2026-11-20")
