"""CONFIDENCE in the stats-only epoch (plan 2026-10-05: K0, K2, K3, K5, K6,
K10). A day after the cutover, built after STATS_ONLY_FROM_UTC."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import (
    Calibration,
    coupon_order,
    coupon_sort_key,
    is_stakeable,
)
from bet.sofa.epochs import STATS_ONLY_FROM_UTC

DAY = "2026-10-07"
T0 = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
assert T0 > STATS_ONLY_FROM_UTC


def _z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _fixture(eid: int, kickoff: str) -> dict[str, Any]:
    from tests.sofa.test_locked_print import _fixture as base

    return {**base(1), "sofascore_event_id": eid, "superbet_event_ids": [f"s{eid}"],
            "kickoff_utc": kickoff, "superbet_kickoff_utc": kickoff,
            "home_name": f"Home {eid}", "away_name": f"Away {eid}",
            "home_entity_id": eid * 10, "away_entity_id": eid * 10 + 1}


def _samples(eid: int) -> dict[str, Any]:
    from tests.sofa.test_locked_print import _samples as base

    doc = base(1)
    doc["sofascore_event_id"] = eid
    for side in ("side_a", "side_b"):
        for i, o in enumerate(doc["metrics"]["goals_total"][side]):
            o["sofascore_event_id"] = eid * 1000 + i + (0 if side == "side_a" else 500)
            o["match_date_utc"] = _z(T0 - timedelta(days=3 + i))
    return doc


def _row(
    eid: int, p: float, odds: float, market_p: float, **extra: Any
) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "sport": "football", "market": "goals_total",
        "subject": "", "line": 1.5, "direction": "OVER", "sample_size": 20,
        "sample_mean": 2.6, "sample_sd": 1.2, "centre": 2.6, "p_central": p,
        "market_p": market_p, "ladder_centre": None, "ladder_sigma": None,
        "p_bar": p - 0.02, "bar_reason": "none", "required_odds": 1.3,
        "offered_odds": odds, "edge": 0.0, "surplus": 0.0, "verdict": "BELOW_BAR",
        "notes": [], "epoch": "stats_only", "forecast_p": 0.61,
        "forecast_source": "football_rating", **extra,
    }


def _day(tmp_path: Path, rows: list[dict[str, Any]], kickoffs: dict[int, str],
         offer_odds: dict[int, tuple[float, float]]) -> Path:
    run = tmp_path / DAY
    run.mkdir(exist_ok=True)
    eids = sorted(kickoffs)
    (run / "02_fixtures.json").write_text(json.dumps(
        [_fixture(e, kickoffs[e]) for e in eids]))
    (run / "03_samples.json").write_text(json.dumps([_samples(e) for e in eids]))
    (run / "05_sheet.json").write_text(json.dumps(rows))
    (run / "vetoes.json").write_text("[]")
    (run / "04_offer.json").write_text(json.dumps([
        {"sofascore_event_id": e, "status": "PRICED", "unmapped_markets": [],
         "price_collisions": [],
         "rungs": [{"market": "goals_total", "subject": "", "line": 1.5,
                    "over_odds": offer_odds[e][0], "under_odds": offer_odds[e][1],
                    "fetched_at_utc": _z(T0 - timedelta(minutes=1))}]}
        for e in eids]))
    return tmp_path


def _under(over: float) -> float:
    """The other side of a rung with a 5% margin."""
    return round(1.0 / (1.05 - 1.0 / over), 2)


def _run(runs: Path, monkeypatch: pytest.MonkeyPatch, profile: str = "standard") -> int:
    from scripts.sofa import run_confidence

    monkeypatch.setenv("SOFA_NOW", _z(T0))
    monkeypatch.setattr(sys, "argv", [
        "run_confidence.py", "--date", DAY, "--runs-dir", str(runs),
        "--profile", profile])
    return int(run_confidence.main())


def _doc(runs: Path) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((runs / DAY / "08_confidence.json").read_text())
    return out


KO = {1: "2026-10-07T18:00:00Z", 2: "2026-10-07T15:00:00Z"}


def _conf(p: float) -> float:
    got = Calibration.load().realised("goals_total", p, "football", "OVER")
    assert got is not None
    return float(got[0])


def test_a_sheet_from_the_old_rule_is_refused(tmp_path, monkeypatch, capsys):
    row = _row(1, 0.72, 1.30, 0.69)
    del row["epoch"]
    runs = _day(tmp_path, [row], {1: KO[1]}, {1: (1.30, 3.30)})
    assert _run(runs, monkeypatch) == 2
    assert "starts at SHEET" in capsys.readouterr().err


def test_the_wariant_is_retired(tmp_path, monkeypatch, capsys):
    runs = _day(tmp_path, [_row(1, 0.72, 1.30, 0.69)], {1: KO[1]}, {1: (1.30, 3.30)})
    assert _run(runs, monkeypatch, "wariant") == 2
    assert "retired" in capsys.readouterr().err


def test_a_model_far_above_the_price_is_not_refused(tmp_path, monkeypatch):
    # K2/D1: MAX_DISAGREEMENT and UNREACHABLE_BAR are off; x decides.
    p = 0.75
    odds = round(0.95 / _conf(p), 2)
    row = _row(1, p, odds, 0.60, notes=["UNREACHABLE_BAR: test"])
    runs = _day(tmp_path, [row], {1: KO[1]}, {1: (odds, _under(odds))})
    assert _run(runs, monkeypatch) == 0
    doc = _doc(runs)
    assert [s["sofascore_event_id"] for s in doc["singles"]] == [1]
    single = doc["singles"][0]
    assert single["epoch"] == "stats_only" and doc["epoch"] == "stats_only"
    assert single["forecast_p"] == 0.61 and single["model_p"] == p


def test_a_moved_price_is_judged_at_the_fresh_price(tmp_path, monkeypatch):
    p = 0.75
    good = round(0.95 / _conf(p), 2)
    bad = round(0.88 / _conf(p), 2)  # x < 0.90 at the fresh price
    runs = _day(tmp_path, [_row(1, p, good, 0.60), _row(2, p, bad, 0.60)],
                KO, {1: (bad, _under(bad)), 2: (good, _under(good))})
    assert _run(runs, monkeypatch) == 0
    doc = _doc(runs)
    assert [s["sofascore_event_id"] for s in doc["singles"]] == [2]
    assert doc["singles"][0]["offered_odds"] == good
    assert doc["singles"][0]["sheet_odds"] == bad


def test_a_watched_leg_is_removed_by_reads_with_its_author(tmp_path, monkeypatch):
    p = 0.75
    odds = round(0.95 / _conf(p), 2)
    runs = _day(tmp_path, [_row(1, p, odds, 0.70), _row(2, p, odds, 0.70)],
                KO, {1: (odds, _under(odds)), 2: (odds, _under(odds))})
    (runs / DAY / "reads.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "market": "goals_total", "subject": None,
        "line": None, "direction": None, "verdict": "WATCH",
        "author": "analyst", "reason": "test"}]))
    assert _run(runs, monkeypatch) == 0
    doc = _doc(runs)
    assert [s["sofascore_event_id"] for s in doc["singles"]] == [2]
    removed = doc["removed_by_reads"]
    assert [(r["sofascore_event_id"], r["refusal"], r["reason"]) for r in removed] == [
        (1, "WATCHED", "analyst")]
    assert removed[0]["offered_odds"] == odds


def test_equal_confidence_puts_the_earlier_start_first(tmp_path, monkeypatch):
    p = 0.75
    odds = round(0.95 / _conf(p), 2)
    runs = _day(tmp_path, [_row(1, p, odds, 0.70), _row(2, p, odds + 0.05, 0.70)],
                KO, {1: (odds, _under(odds)), 2: (odds + 0.05, _under(odds + 0.05))})
    assert _run(runs, monkeypatch) == 0
    # fixture 2 starts at 15:00, fixture 1 at 18:00; the price plays no part
    assert [s["sofascore_event_id"] for s in _doc(runs)["singles"]] == [2, 1]


def _leg(eid: int, conf: float, ko: str, market: str = "goals_total",
         line: float = 1.5) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "confidence": conf, "kickoff_utc": ko,
            "market": market, "subject": "", "line": line, "direction": "OVER"}


def test_coupon_order_keeps_a_match_together_at_its_best_legs_place():
    legs = [
        _leg(1, 0.80, "2026-10-07T18:00:00Z"),
        _leg(2, 0.90, "2026-10-07T20:00:00Z"),
        _leg(1, 0.95, "2026-10-07T18:00:00Z", "corners_total", 8.5),
        _leg(3, 0.90, "2026-10-07T12:00:00Z"),
    ]
    blocks = coupon_order(legs)
    assert [b.group_key for b in blocks] == ["sofa:1", "sofa:3", "sofa:2"]
    assert [x["confidence"] for x in blocks[0].legs] == [0.95, 0.80]
    assert coupon_sort_key(legs[3]) < coupon_sort_key(legs[1])


def test_a_stats_only_builder_is_stakeable_on_x_not_on_ev():
    base = {"best_for_fixture": True, "stakeable_rule": "x>=0.90",
            "ev_after_haircut": -0.05}
    assert is_stakeable({**base, "combined_probability": 0.75,
                         "odds_after_haircut": 1.20})
    assert not is_stakeable({**base, "combined_probability": 0.70,
                             "odds_after_haircut": 1.20})
    # an older builder keeps its EV predicate
    assert not is_stakeable({"best_for_fixture": True, "ev_after_haircut": -0.05,
                             "combined_probability": 0.9, "odds_after_haircut": 1.2})
