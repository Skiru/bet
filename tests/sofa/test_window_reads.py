"""The operator's kickoff window as read requests (`/sofa-analyze ... okno`):
the window's best-value matches, every one when fewer than `top`, written as
whole-match requests that C3 then requires (operator, 2026-10-27)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from bet.sofa.confidence import legs_requiring_read, load_read_requests
from bet.sofa.window_reads import window_events, window_requests
from scripts.sofa import window_reads as script

UTC = datetime.UTC
NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
LO = datetime.datetime(2026, 10, 27, 13, 0, tzinfo=UTC)
HI = datetime.datetime(2026, 10, 27, 16, 0, tzinfo=UTC)


def leg(eid: int, conf: float, odds: float, ko: str, *, locked: bool = False,
        market: str = "corners_total", pos: int | None = 1) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "group_key": f"sofa:{eid}", "sport": "football",
            "kickoff_utc": ko, "market": market, "subject": "", "line": 5.5,
            "direction": "OVER", "confidence": conf, "offered_odds": odds,
            "match": f"M{eid}", "locked": locked, "position": None if locked else pos}


def artifact(singles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"singles": singles, "legs": singles, "positions": len(singles),
            "pdf_max_singles": None, "builders": [], "read_unit": "event",
            "read_order": "value"}


def test_window_ranks_by_value_and_drops_outside_started_and_locked() -> None:
    doc = artifact([
        leg(1, 0.80, 1.20, "2026-10-27T14:00:00Z"),            # x 0.96
        leg(2, 0.75, 1.50, "2026-10-27T15:00:00Z"),            # x 1.125, best
        leg(3, 0.90, 1.50, "2026-10-27T17:00:00Z"),            # after the window
        leg(4, 0.90, 1.50, "2026-10-27T12:05:00Z"),            # before it
        leg(5, 0.90, 1.50, "2026-10-27T13:05:00Z", locked=True),  # nothing to read
        leg(6, 0.90, 1.50, "2026-10-27T12:09:00Z"),            # inside the margin
    ])
    events = window_events(doc, LO, HI, NOW)
    assert [g for g, _, _ in events] == ["sofa:2", "sofa:1"]
    early = window_events(doc, NOW, HI, NOW)
    assert "sofa:6" not in [g for g, _, _ in early]


def test_a_match_the_analysts_could_not_read_in_time_is_not_asked() -> None:
    # 15 min kickoff margin + 15 min to read (10-27: 13:00Z matches asked at
    # 12:48Z came back unread)
    doc = artifact([leg(1, 0.80, 1.30, "2026-10-27T12:29:00Z"),
                    leg(2, 0.80, 1.30, "2026-10-27T12:31:00Z")])
    assert [g for g, _, _ in window_events(doc, NOW, HI, NOW)] == ["sofa:2"]


def test_a_match_counts_once_by_its_best_leg_and_top_cuts() -> None:
    doc = artifact([
        leg(1, 0.80, 1.20, "2026-10-27T14:00:00Z"),
        leg(1, 0.72, 1.60, "2026-10-27T14:00:00Z", market="goals_total"),
        leg(2, 0.80, 1.30, "2026-10-27T14:00:00Z"),
    ])
    events = window_events(doc, LO, HI, NOW, top=1)
    # 0.72 capped at 1/1.6 + 0.03 (read_value)
    assert [(g, round(v, 3)) for g, v, _ in events] == [("sofa:1", 1.048)]
    assert len(window_events(doc, LO, HI, NOW, top=20)) == 2  # fewer: all


def test_requests_cover_every_market_and_skip_a_match_already_asked() -> None:
    doc = artifact([
        leg(1, 0.80, 1.20, "2026-10-27T14:00:00Z", pos=1),
        leg(1, 0.75, 1.30, "2026-10-27T14:00:00Z", market="goals_total", pos=2),
        leg(2, 0.80, 1.30, "2026-10-27T14:00:00Z", pos=3),
    ])
    events = window_events(doc, LO, HI, NOW)
    existing = [{"group_key": "sofa:2", "requested_by": "operator", "at_utc": "x"}]
    new = window_requests(events, existing, NOW, "14:00-17:00 Europe/Warsaw")
    assert [r["group_key"] for r in new] == ["sofa:1"]
    assert new[0]["at_utc"] == "2026-10-27T12:00:00Z" and "market" not in new[0]
    # a request for one rung of a match does not count as the whole match
    rung = [{"group_key": "sofa:1", "market": "goals_total", "requested_by": "o",
             "at_utc": "x"}]
    assert {r["group_key"] for r in window_requests(events, rung, NOW, "w")} == {
        "sofa:1", "sofa:2"}
    # C3 then requires both legs of match 1
    doc["read_unit"] = None
    required = legs_requiring_read({**doc, "positions": 3}, new)
    assert {(s["sofascore_event_id"], s["market"]) for s in required} >= {
        (1, "corners_total"), (1, "goals_total")}


def test_script_appends_requests(tmp_path: Path, monkeypatch: Any) -> None:
    run = tmp_path / "2026-10-27"
    run.mkdir()
    doc = artifact([leg(1, 0.80, 1.20, "2026-10-27T14:00:00Z")])
    (run / "11_coupon.json").write_text(json.dumps(doc), encoding="utf-8")
    old = [{"position": 7, "requested_by": "operator", "at_utc": "x"}]
    (run / "read_requests.json").write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(script, "utc_now", lambda: NOW)
    monkeypatch.delenv("SOFA_NOW", raising=False)
    argv = ["--date", "2026-10-27", "--start-from", "14:00", "--start-to", "17:00",
            "--runs-dir", str(tmp_path)]
    assert script.main([*argv, "--dry-run"]) == 0
    assert len(load_read_requests(run / "read_requests.json")) == 1
    assert script.main(argv) == 0
    got = load_read_requests(run / "read_requests.json")
    assert got[0] == old[0] and got[1]["group_key"] == "sofa:1"
    assert got[1]["window"] == "14:00-17:00 Europe/Warsaw"
    assert script.main(argv) == 0  # again: nothing new
    assert len(load_read_requests(run / "read_requests.json")) == 2
    assert script.main([*argv[:2], "--start-from", "20:00", "--start-to", "21:00",
                        "--runs-dir", str(tmp_path)]) == 1
