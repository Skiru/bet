"""11_coupon.json (plan 2026-10-05, K3/K4): build_coupon.py assembles the one
coupon of a stats-only day; every reader of "what was printed" reads it on a
day that has it and 08_confidence.json on a day that does not."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import (
    PROFILES,
    coupon_artifact,
    legs_requiring_read,
    printed_singles,
    profile_artifact_path,
    request_covers,
)
from scripts.sofa.build_coupon import assemble
from tests.sofa.test_stats_only_confidence import (
    DAY,
    KO,
    T0,
    _conf,
    _day,
    _row,
    _run,
    _under,
    _z,
)


def _three_matches(tmp_path: Path) -> Path:
    p = 0.75
    odds = round(0.95 / _conf(p), 2)
    kickoffs = {**KO, 3: "2026-10-07T13:00:00Z"}
    rows = [_row(e, p, odds, 0.70) for e in (1, 2, 3)]
    return _day(tmp_path, rows, kickoffs, {e: (odds, _under(odds)) for e in (1, 2, 3)})


def _build_coupon(runs: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    from scripts.sofa import build_coupon

    monkeypatch.setenv("SOFA_NOW", _z(T0))
    monkeypatch.setattr(sys, "argv", [
        "build_coupon.py", "--date", DAY, "--runs-dir", str(runs)])
    return int(build_coupon.main())


def _coupon(runs: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((runs / DAY / "11_coupon.json").read_text())
    return doc


def test_the_coupon_numbers_positions_in_coupon_order(tmp_path, monkeypatch):
    runs = _three_matches(tmp_path)
    assert _run(runs, monkeypatch) == 0
    # no sports artifact yet: assembled, PARTIAL
    assert _build_coupon(runs, monkeypatch) == 1
    doc = _coupon(runs)
    assert doc["epoch"] == "stats_only" and doc["coupon"] == "11_coupon.json"
    # equal confidence: the earlier start first (13:00, 15:00, 18:00)
    assert [(s["position"], s["sofascore_event_id"]) for s in doc["singles"]] == [
        (1, 3), (2, 2), (3, 1)]
    assert [b["group_key"] for b in doc["blocks"]] == ["sofa:3", "sofa:2", "sofa:1"]
    assert doc["positions"] == 3 and doc["pdf_max_singles"] is None
    # a reader of "what was printed" reads 11 the way it read 08
    assert len(printed_singles(doc)) == 3


def test_the_pdf_prints_the_coupon_artifact(tmp_path, monkeypatch):
    from scripts.sofa import build_coupon_pdf

    runs = _three_matches(tmp_path)
    assert _run(runs, monkeypatch) == 0
    monkeypatch.setattr(sys, "argv", [
        "build_coupon_pdf.py", "--date", DAY, "--runs-dir", str(runs)])
    # a stats-only 08 is not the coupon
    assert build_coupon_pdf.main() == 2
    assert _build_coupon(runs, monkeypatch) == 1
    monkeypatch.setattr(sys, "argv", [
        "build_coupon_pdf.py", "--date", DAY, "--runs-dir", str(runs)])
    assert build_coupon_pdf.main() == 0
    assert (runs / DAY / f"KUPON_{DAY}.pdf").stat().st_size > 1000
    # a CONFIDENCE rebuild after the assembly makes the coupon stale
    conf = runs / DAY / "08_confidence.json"
    t = (runs / DAY / "11_coupon.json").stat().st_mtime + 5
    os.utime(conf, (t, t))
    monkeypatch.setattr(sys, "argv", [
        "build_coupon_pdf.py", "--date", DAY, "--runs-dir", str(runs)])
    assert build_coupon_pdf.main() == 2


def test_readers_switch_to_11_only_where_it_exists(tmp_path):
    run = tmp_path / DAY
    run.mkdir()
    (run / "08_confidence.json").write_text("{}")
    assert coupon_artifact(run).name == "08_confidence.json"
    assert profile_artifact_path(run, PROFILES["wariant"]).name == (
        "08_confidence_wariant.json")
    (run / "11_coupon.json").write_text("{}")
    assert coupon_artifact(run).name == "11_coupon.json"
    assert profile_artifact_path(run, PROFILES["standard"]).name == "11_coupon.json"
    assert profile_artifact_path(run, PROFILES["wariant"]).name == (
        "08_confidence_wariant.json")


def test_an_old_day_is_not_assembled(tmp_path, monkeypatch, capsys):
    run = tmp_path / DAY
    run.mkdir()
    (run / "08_confidence.json").write_text(json.dumps(
        {"profile": "standard", "singles": [], "legs": [], "builders": []}))
    assert _build_coupon(tmp_path, monkeypatch) == 2
    assert "stats-only" in capsys.readouterr().err


def _single(eid: int, conf: float, ko: str, **extra: Any) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "confidence": conf, "kickoff_utc": ko,
            "market": "goals_total", "subject": "", "line": 1.5,
            "direction": "OVER", "offered_odds": 1.3, "match": f"M{eid}", **extra}


def _conf_doc(singles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": [],
            "removed_by_reads": [{"sofascore_event_id": 9}]}


def test_k4_reads_the_first_30_fresh_positions_plus_the_requests():
    singles = [_single(1000 + i, 0.9 - i * 0.001, "2026-10-07T12:00:00Z")
               for i in range(40)]
    locked = _single(1, 0.95, "2026-10-07T08:00:00Z", locked=True)
    requests = [
        {"position": 35, "requested_by": "operator", "at_utc": "t"},
        {"group_key": "sofa:1039", "market": "goals_total",
         "requested_by": "operator", "at_utc": "t"},
    ]
    doc = assemble(_conf_doc([locked, *singles]), None, requests, {}, "now")
    assert doc["locked_singles"] == 1 and doc["singles"][0]["locked"]
    assert doc["singles"][0].get("position") is None
    required = legs_requiring_read(doc)
    positions = sorted(int(x["position"]) for x in required if x.get("position"))
    assert positions == [*range(1, 31), 35, 40]
    assert all(not x.get("locked") for x in required)
    assert doc["read_requests"][0]["covers"] == [35]
    assert doc["removed_by_reads"] == [{"sofascore_event_id": 9}]


def test_a_request_covers_by_group_key_and_rung():
    leg = _single(5, 0.8, "2026-10-07T12:00:00Z", position=7)
    assert request_covers({"group_key": "sofa:5"}, leg)
    assert request_covers({"group_key": "sofa:5", "line": 1.5}, leg)
    assert not request_covers({"group_key": "sofa:5", "line": 2.5}, leg)
    assert not request_covers({"group_key": "sofa:6"}, leg)
    assert request_covers({"position": 7}, leg)


def test_a_match_block_names_its_printed_builder():
    singles = [_single(1, 0.8, "2026-10-07T12:00:00Z")]
    conf = _conf_doc(singles)
    conf["builders"] = [{
        "sofascore_event_id": 1, "match": "M1", "kickoff_utc": "2026-10-07T12:00:00Z",
        "best_for_fixture": True, "stakeable_rule": "x>=0.90",
        "combined_probability": 0.7, "odds_after_haircut": 1.5, "legs": [],
        "n_legs": 2}]
    doc = assemble(conf, None, [], {}, "now")
    assert doc["builders"][0]["builder_no"] == "B1"
    assert doc["blocks"][0]["builders"] == ["B1"]


def test_a_makeup_fixture_carries_its_original():
    singles = [_single(1, 0.8, "2026-10-07T12:00:00Z")]
    samples = {1: {"schedule": {"makeup_of": 15458084,
                                "makeup_postponed_utc": "2026-10-02T15:00:00Z"}}}
    doc = assemble(_conf_doc(singles), None, [], samples, "now")
    assert doc["singles"][0]["makeup_of"] == {
        "sofascore_event_id": 15458084, "postponed_utc": "2026-10-02T15:00:00Z"}


def test_a_locked_leg_loses_its_old_position():
    locked = _single(1, 0.95, "2026-10-07T08:00:00Z", locked=True, position=1, block=1)
    fresh = _single(2, 0.90, "2026-10-07T12:00:00Z")
    doc = assemble(_conf_doc([locked, fresh]), None,
                   [{"position": 1, "requested_by": "operator", "at_utc": "t"}],
                   {}, "now")
    assert "position" not in doc["singles"][0] and "block" not in doc["singles"][0]
    assert doc["read_requests"][0]["covers"] == [1]
    assert [x["sofascore_event_id"] for x in legs_requiring_read(doc)] == [2]


def test_a_fresh_leg_outside_the_utc_day_is_not_on_the_days_coupon():
    legs = [_single(1, 0.9, "2026-10-07T23:30:00Z"),
            _single(2, 0.9, "2026-10-08T00:30:00Z"),
            _single(3, 0.9, "2026-10-06T23:00:00Z", locked=True)]
    doc = assemble(_conf_doc(legs), None, [], {}, "now", "2026-10-07")
    assert [s["sofascore_event_id"] for s in doc["singles"]] == [3, 1]
    assert doc["outside_day_window"] == 1


def test_the_last_printed_coupon_is_carried_over_past_an_unprinted_build():
    """Review of K3 (2026-10-05): a leg the PDF printed whose match starts
    while an unprinted rebuild is the newest artifact still locks."""
    from datetime import UTC, datetime

    from bet.sofa.locked_print import carry_over, merge_locked

    printed = {"profile": "standard", "created_at_utc": "2026-10-07T08:00:00Z",
               "pdf_rendered_at_utc": "2026-10-07T08:01:00Z", "epoch": "stats_only",
               "singles": [_single(1, 0.9, "2026-10-07T09:00:00Z")], "legs": [],
               "builders": [], "pdf_max_singles": None}
    unprinted = {**printed, "created_at_utc": "2026-10-07T08:30:00Z", "singles": []}
    now = datetime(2026, 10, 7, 9, 5, tzinfo=UTC)
    started = lambda eid, ko: True  # noqa: E731
    newest_only = carry_over(unprinted, "standard", now, started, pdf_printed=False)
    assert not newest_only.singles
    both = merge_locked(
        carry_over(printed, "standard", now, started, pdf_printed=True), newest_only)
    assert [s["sofascore_event_id"] for s in both.singles] == [1]
    assert both.singles[0]["printed_at_utc"] == "2026-10-07T08:01:00Z"
    assert both.singles[0]["printed_under"]["epoch"] == "stats_only"


def test_u1_u2_hold_on_an_assembled_coupon_and_catch_a_shuffle():
    from scripts.sofa.audit_variants import audit_coupon_order

    legs = [_single(1, 0.80, "2026-10-07T12:00:00Z", epoch="stats_only"),
            _single(2, 0.90, "2026-10-07T13:00:00Z", epoch="stats_only"),
            _single(3, 0.95, "2026-10-07T08:00:00Z", locked=True)]
    doc = assemble(_conf_doc(legs), None, [], {}, "now")
    assert audit_coupon_order(doc, "official") == []
    shuffled = {**doc, "singles": [doc["singles"][0], doc["singles"][2],
                                   doc["singles"][1]]}
    found = audit_coupon_order(shuffled, "official")
    assert any(f.startswith("U1") for f in found)
    old = {**doc, "singles": [{**s, "epoch": None} for s in doc["singles"]]}
    assert any(f.startswith("U2") for f in audit_coupon_order(old, "official"))
