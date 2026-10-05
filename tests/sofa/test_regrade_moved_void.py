"""regrade_settled.py --moved-void (A1 back-data, plan 2026-10-05).

A live row of a match Sofascore started more than 48 h from its day's
earliest clock was a void bet. The row moves to the day the match was played
when that day's sheet priced the key, else it is deleted (with a copy); the
original day's skips get MOVED_BEYOND_VOID so 7c and the ledger read the
printed leg as a refund.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.db import migrate
from scripts.sofa import audit_settlement

REPO = Path(__file__).resolve().parents[2]
DAY = "2026-09-24"
PLAYED = "2026-09-27"
KICKOFF = datetime(2026, 9, 24, 18, 0, tzinfo=UTC)
MOVED = KICKOFF + timedelta(hours=66)  # 2026-09-27 12:00Z


def _z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _fixture(eid: int, kickoff: datetime) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "sport": "football", "kickoff_utc": _z(kickoff),
            "home_name": f"H{eid}", "away_name": f"A{eid}"}


def _sheet_row(eid: int) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "market": "goals_total", "subject": "",
            "line": 2.5, "direction": "OVER", "offered_odds": 1.9}


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    runs = tmp_path / "runs"
    for day in (DAY, PLAYED):
        (runs / day).mkdir(parents=True)
    # 1: moved, played on 09-27 and priced there -> move.
    # 2: moved, nobody priced it on the played day -> delete.
    # 3: played on its day -> untouched.
    (runs / DAY / "02_fixtures.json").write_text(json.dumps(
        [_fixture(1, KICKOFF), _fixture(2, KICKOFF), _fixture(3, KICKOFF)]))
    (runs / PLAYED / "02_fixtures.json").write_text(json.dumps([_fixture(1, MOVED)]))
    (runs / PLAYED / "05_sheet.json").write_text(json.dumps([_sheet_row(1)]))
    single = {**_sheet_row(1), "sport": "football", "confidence": 0.8}
    (runs / DAY / "08_confidence.json").write_text(json.dumps({
        "created_at_utc": _z(KICKOFF - timedelta(hours=6)), "profile": "standard",
        "pdf_max_singles": None, "prints_builders": True, "min_ev": 0.9,
        "legs": [single], "singles": [single], "builders": []}))
    db = tmp_path / "s.db"
    migrate(str(db))
    con = sqlite3.connect(db)
    for eid, start in ((1, MOVED), (2, MOVED), (3, KICKOFF)):
        event = {"id": eid, "startTimestamp": int(start.timestamp()),
                 "status": {"type": "finished", "code": 100}}
        con.execute(
            "insert into sofa_event_detail (sofascore_event_id, fetched_at,"
            " status_type, detail_json) values (?, ?, 'finished', ?)",
            (eid, _z(MOVED), json.dumps({"event": event})),
        )
        con.execute(
            "insert into sofa_settled_row (run_date, sofascore_event_id, sport,"
            " competition_id, market, subject, line, direction, sample_size,"
            " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
            " outcome, settled_at, offered_odds, verdict) values"
            " (?, ?, 'football', 1, 'goals_total', '', 2.5, 'OVER', 10, 2.6, 1.2,"
            " 0.6, 0.6, 0.5, 1.0, 'LOSS', ?, 1.9, 'VALUE')",
            (DAY, eid, _z(MOVED)),
        )
    con.commit()
    con.close()
    return runs, db


def _run(runs: Path, db: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/sofa/regrade_settled.py", "--moved-void", *flags],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin",
             "SOFA_RUNS_DIR": str(runs), "SOFA_DB_PATH": str(db)},
    )


def _rows(db: Path) -> list[tuple[Any, ...]]:
    con = sqlite3.connect(db)
    try:
        return con.execute(
            "select sofascore_event_id, run_date from sofa_settled_row order by 1"
        ).fetchall()
    finally:
        con.close()


def test_dry_run_reports_and_writes_nothing(tmp_path: Path) -> None:
    runs, db = _setup(tmp_path)
    out = _run(runs, db, "--dry-run")
    assert out.returncode == 0, out.stderr
    assert f"PRINTED {DAY} event=1 goals_total" in out.stdout
    assert "moved to 2026-09-27" in out.stdout
    summary = json.loads(out.stdout.split("SOFA_SUMMARY: ", 1)[1])
    assert summary["metrics"]["tally"] == {"move": 1, "delete": 1}
    assert summary["metrics"]["printed_changed"] == 1
    assert _rows(db) == [(1, DAY), (2, DAY), (3, DAY)]
    assert not list(runs.glob("regrade_*.json"))
    assert not (runs / DAY / "07_settle_skips.json").exists()


def test_apply_moves_or_deletes_with_a_copy_and_marks_the_refund(
    tmp_path: Path,
) -> None:
    runs, db = _setup(tmp_path)
    out = _run(runs, db, "--apply")
    assert out.returncode == 0, out.stderr
    assert _rows(db) == [(1, PLAYED), (3, DAY)]
    [log] = list(runs.glob("regrade_*.json"))
    copy = json.loads(log.read_text())
    assert {a["event_id"]: a["action"] for a in copy["actions"]} == {
        1: "move", 2: "delete"}
    assert copy["actions"][1]["row"]["outcome"] == "LOSS", "the full row is kept"
    skips = json.loads((runs / DAY / "07_settle_skips.json").read_text())
    assert {e["sofascore_event_id"]: e["skipped"] for e in skips["skipped_events"]} == {
        1: {"MOVED_BEYOND_VOID": 1}, 2: {"MOVED_BEYOND_VOID": 1}}

    # 7c now reads the printed leg as a refund, not as the 09-27 row's LOSS.
    single = json.loads((runs / DAY / "08_confidence.json").read_text())["singles"]
    by_key = audit_settlement.coupon_settled_by_key(
        str(db), runs / DAY, DAY, {audit_settlement._key(s) for s in single})
    res = audit_settlement.settle_singles(single, by_key)
    assert (res["refunded"], res["lost"], res["units"]) == (1, 0, 0.0)
