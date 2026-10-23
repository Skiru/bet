"""Coverage audit 2026-10-23, wiring of P9 into refresh_sport_history.py: the
missing list sides (kind `last_side`, sport_history.list_both_sides) are
written after the refresh and by `--both-sides-only` (offline, no bridge),
committed, idempotent; `--dry-run` writes nothing. Nothing reading `last`
sees them."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import sport_history as sh
from tests.sofa.test_audit1023_p9_both_sides import START, VANCOUVER, _db


def _main(monkeypatch: pytest.MonkeyPatch, db: Path, runs: Path,
          *argv: str) -> tuple[int, dict[str, Any]]:
    from scripts.sofa import refresh_sport_history as rsh

    monkeypatch.setenv("SOFA_DB_PATH", str(db))
    monkeypatch.setenv("SOFA_RUNS_DIR", str(runs))
    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setattr(sys, "argv", ["refresh_sport_history.py", *argv])
    out: list[str] = []
    monkeypatch.setattr("builtins.print",
                        lambda *a, **k: out.append(" ".join(map(str, a))))
    code = rsh.main()
    summary = next(line for line in out if line.startswith("SOFA_SUMMARY: "))
    return code, json.loads(summary.split(": ", 1)[1])


def _side_rows(db: Path) -> list[tuple[int, str, int]]:
    with sqlite3.connect(db) as con:
        return [tuple(r) for r in con.execute(
            "SELECT entity_id, kind, event_id FROM sofa_listing_event "
            "WHERE kind = ? ORDER BY entity_id", (sh.OPPONENT_KIND,))]


def test_both_sides_only_writes_the_missing_side_once(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _db(tmp_path).close()
    db = tmp_path / "sofa.db"
    code, summary = _main(monkeypatch, db, tmp_path / "runs", "--both-sides-only")
    assert code == 0 and summary["both_sides_written"] == 1
    assert _side_rows(db) == [(VANCOUVER, sh.OPPONENT_KIND, 16546356)]
    with sqlite3.connect(db) as con:  # `last` readers see nothing new
        assert con.execute(
            "SELECT COUNT(*) FROM sofa_listing_event WHERE entity_id = ? "
            "AND kind = 'last'", (VANCOUVER,)).fetchone()[0] == 0
        assert sh.listed_rows(con, VANCOUVER, START + 86400, 10) == []
    code, summary = _main(monkeypatch, db, tmp_path / "runs", "--both-sides-only")
    assert code == 0 and summary["both_sides_written"] == 0


def test_dry_run_writes_nothing(monkeypatch: pytest.MonkeyPatch,
                                tmp_path: Path) -> None:
    _db(tmp_path).close()
    db = tmp_path / "sofa.db"
    code, summary = _main(monkeypatch, db, tmp_path / "runs", "--dry-run")
    assert code == 0 and "both_sides_written" not in summary
    assert _side_rows(db) == []


def test_the_refresh_lists_both_sides_after_its_own_writes(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from bet.sofa import client as client_mod

    _db(tmp_path).close()
    db = tmp_path / "sofa.db"

    class NoClient:
        def __init__(self, config: Any) -> None:
            pass

        def event(self, eid: int) -> Any:
            raise AssertionError("nothing to ask")

    monkeypatch.setattr(client_mod, "SofascoreClient", NoClient)
    code, summary = _main(monkeypatch, db, tmp_path / "runs", "--days", "1")
    assert code == 0 and summary["both_sides_written"] == 1
    assert _side_rows(db) == [(VANCOUVER, sh.OPPONENT_KIND, 16546356)]
