"""A lost snapshot file never puts a moved game back on both days.

Basketball 15705878 (North Dakota - Montana, Sofascore 16801165): Superbet
listed it for 2026-11-14 18:00Z, then moved it to 2026-11-15 02:00Z. The
identity pass marked 11-14's record MOVED_TO:2026-11-15 (logs 11-16..11-18).
Then 11-15's snapshots.jsonl was lost with the run files deleted on
2026-11-18/19, the pass saw the event in 11-14's snapshot only, reverted the
mark, and the game was SETTLED - and in the ledger's measure:basketball rows -
on both days (audit_settle_identity ID_USED_TWICE). The pass now reads a
record its file's snapshot does not hold from the record itself, and keeps a
MOVED_TO whose target day no longer shows the event at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.sofa import settle_identity as si
from scripts.sofa import audit_settle_identity, record_results, settle_shadow

EID = "15705878"
D1, D2 = "2026-11-14", "2026-11-15"


def _graded(outcome: str) -> dict[str, Any]:
    return {
        "superbet_event_id": EID,
        "market_id": 753,
        "family": "total",
        "period": 0,
        "subject": "",
        "line": 150.5,
        "side": "OVER",
        "odds": 1.9,
        "partner_odds": 1.9,
        "fair_p": 0.5,
        "outcome": outcome,
    }


def _rec(kickoff: str, last: str, sides: int) -> dict[str, Any]:
    return {
        "match_name": "North Dakota Fighting Sioux·Montana Grizzlies",
        "team1": "North Dakota Fighting Sioux",
        "team2": "Montana Grizzlies",
        "kickoff_utc": kickoff,
        "last_snapshot_utc": last,
        "sofascore_event_id": 16801165,
        "sofascore_match": "North Dakota Fighting Sioux - Montana Grizzlies",
        "sofascore_home": "North Dakota Fighting Sioux",
        "sofascore_away": "Montana Grizzlies",
        "home_is_team1": True,
        "state": "SETTLED",
        "graded": [_graded("WIN")] * sides,
    }


def _files() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        D1: {EID: _rec("2026-11-14T18:00:00Z", "2026-11-14T08:58:00Z", 3)},
        D2: {EID: _rec("2026-11-15T02:00:00Z", "2026-11-15T01:50:39Z", 4)},
    }


def _snap(rec: dict[str, Any]) -> si.SnapInfo:
    info = si.record_snap(rec)
    assert info is not None
    return info


def test_a_record_whose_snapshot_file_is_lost_still_moves_the_earlier_one() -> None:
    files = _files()
    # D1's snapshot file holds the event, D2's file is gone (empty index).
    snaps = {D1: {EID: _snap(files[D1][EID])}, D2: {}}
    changes = si.plan_identity("shadow", files, snaps)
    assert changes == {
        (D1, EID): {
            "state": "MOVED_TO:" + D2,
            "identity_reason": f"the event's last snapshot is in {D2}'s file",
        }
    }


def test_a_moved_mark_survives_its_target_losing_every_trace() -> None:
    files = _files()
    snaps = {D1: {EID: _snap(files[D1][EID])}, D2: {EID: _snap(files[D2][EID])}}
    mark = si.plan_identity("shadow", files, snaps)[(D1, EID)]
    files[D1][EID] = si.apply_change(files[D1][EID], mark)
    # D2's snapshot gone: the record still names the later snapshot.
    assert si.plan_identity("shadow", files, {D1: snaps[D1], D2: {}}) == {}
    # D2's record gone too (only D1 loaded, D2 in the window): no evidence
    # that the doubt is gone either - the mark stays.
    alone = {D1: files[D1], D2: {}}
    assert si.plan_identity("shadow", alone, {D1: snaps[D1], D2: {}}) == {}


def test_a_snapshot_file_present_wins_over_the_record() -> None:
    files = _files()
    # The file says D1 saw the event last (a later record than the record's
    # own stamp): the file's reading decides, D2 moves to D1.
    late = si.SnapInfo(
        "2026-11-15T03:00:00Z", "2026-11-15T03:00:00Z", "2026-11-15T02:00:00Z",
        "North Dakota Fighting Sioux", "Montana Grizzlies",
    )
    snaps = {D1: {EID: late}, D2: {}}
    changes = si.plan_identity("shadow", files, snaps)
    assert set(changes) == {(D2, EID)}
    assert changes[(D2, EID)]["state"] == "MOVED_TO:" + D1


def _write_day(root: Path, date: str, events: dict[str, Any],
               snapshot: dict[str, Any] | None) -> None:
    day = root / "shadow" / "basketball" / date
    day.mkdir(parents=True, exist_ok=True)
    (day / "settled.json").write_text(
        json.dumps({"date": date, "sport": "basketball", "events": events})
    )
    if snapshot is not None:
        (day / "snapshots.jsonl").write_text(json.dumps(snapshot) + "\n")


def test_identity_only_counts_the_game_once_in_the_ledger(tmp_path: Path) -> None:
    files = _files()
    # The live state on 2026-11-24: both SETTLED, D2's snapshot file lost.
    _write_day(tmp_path, D1, files[D1], {
        "superbet_event_id": EID, "fetched_at_utc": "2026-11-14T08:58:00Z",
        "kickoff_utc": "2026-11-14T18:00:00Z",
        "team1": "North Dakota Fighting Sioux", "team2": "Montana Grizzlies",
    })
    _write_day(tmp_path, D2, files[D2], None)

    def games(date: str) -> int:
        rows = record_results.measure_rows(str(tmp_path), date)
        (row,) = [r for r in rows if r["variant"] == "measure:basketball"]
        fav = row["favourite_side"]
        return 0 if fav is None else int(fav["events"])

    assert games(D1) == 1 and games(D2) == 1  # counted on both days
    found = audit_settle_identity.audit_measured(str(tmp_path), "basketball", [D1, D2])
    checks = {f["check"] for f in found}
    assert "ID_USED_TWICE" in checks
    assert "IDENTITY_PENDING" in checks  # the audit names the repair

    settle_shadow.identity_only(str(tmp_path), D1, ("basketball",))
    recs = json.loads(
        (tmp_path / "shadow" / "basketball" / D1 / "settled.json").read_text()
    )["events"]
    assert recs[EID]["state"] == "MOVED_TO:" + D2
    assert games(D1) == 0 and games(D2) == 1  # once, on the day it was played
    found = audit_settle_identity.audit_measured(str(tmp_path), "basketball", [D1, D2])
    assert "ID_USED_TWICE" not in {f["check"] for f in found}
