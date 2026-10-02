"""A re-settle of a day merges into the day's files (2026-10-02).

* The D-5 `--refetch-stat-gaps` re-settle wrote 07_settled.json and
  07_settle_skips.json with only its own rows: 09-29, settled
  --include-unpriced, shrank to its priced rows.
* One ProviderError on /lineups escaped the main loop and ended SETTLE FAILED
  with neither file written.
* A tripped breaker reported PARTIAL with zero rows and replaced both files
  with the thin view, so stat_gap_events lost the day's gaps for good.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.errors import CircuitOpenError, ProviderError
from scripts.sofa import run_settle

DATE = "2026-09-29"


def _row(event_id: int, market: str = "goals_total", *, priced: bool = True,
         subject: str = "", line: float = 2.5) -> dict[str, Any]:
    return {
        "sofascore_event_id": event_id, "sport": "football", "market": market,
        "subject": subject, "line": line, "direction": "OVER",
        "sample_size": 10, "sample_mean": 2.6, "sample_sd": 1.2,
        "p_central": 0.55, "p_bar": 0.55, "market_p": 0.5 if priced else None,
        "offered_odds": 1.9 if priced else None,
        "verdict": "VALUE" if priced else "NO_PRICE",
    }


def _event(event_id: int) -> dict[str, Any]:
    return {
        "id": event_id, "status": {"type": "finished", "code": 100},
        "homeScore": {"current": 2}, "awayScore": {"current": 1},
        "tournament": {"uniqueTournament": {"id": 17}},
    }


def _day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
         sheet: list[dict[str, Any]]) -> Path:
    run_dir = tmp_path / "runs" / DATE
    run_dir.mkdir(parents=True)
    ids = sorted({r["sofascore_event_id"] for r in sheet})
    (run_dir / "05_sheet.json").write_text(json.dumps(sheet), encoding="utf-8")
    (run_dir / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": i, "sport": "football",
         "home_name": f"Home {i}", "away_name": f"Away {i}"} for i in ids
    ]), encoding="utf-8")
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.setenv("SOFA_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(run_settle, "SofascoreClient", lambda config: object())
    monkeypatch.setattr(run_settle, "SofaCache", lambda config: object())
    return run_dir


def _payload(fail_from: int | None = None, gaps: frozenset[int] = frozenset()):
    def fake(client: Any, cache: Any, event_id: int, refetch: bool = False) -> Any:
        if fail_from is not None and event_id >= fail_from:
            raise CircuitOpenError("open")
        stats = None if event_id in gaps else {"statistics": []}
        return _event(event_id), stats, {"incidents": []}
    return fake


def _run(monkeypatch: pytest.MonkeyPatch, *flags: str) -> int:
    monkeypatch.setattr(sys, "argv", ["run_settle", "--date", DATE, *flags])
    return run_settle.main()


def _files(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = json.loads((run_dir / "07_settled.json").read_text(encoding="utf-8"))
    skips = json.loads((run_dir / "07_settle_skips.json").read_text(encoding="utf-8"))
    return rows, skips


def test_merge_settled_replaces_regraded_rows_and_keeps_the_rest() -> None:
    old = [_row(1) | {"outcome": "LOSS"}, _row(2, priced=False) | {"outcome": "WIN"}]
    new = [_row(1) | {"outcome": "WIN"}, _row(3) | {"outcome": "WIN"}]
    got = run_settle.merge_settled(old, new)
    assert [(r["sofascore_event_id"], r["outcome"]) for r in got] == [
        (1, "WIN"), (2, "WIN"), (3, "WIN")]


def test_a_narrower_resettle_does_not_shrink_the_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = [_row(1), _row(1, "corners_total"), _row(2, priced=False)]
    run_dir = _day(tmp_path, monkeypatch, sheet)
    monkeypatch.setattr(run_settle, "_event_payload", _payload())
    assert _run(monkeypatch, "--include-unpriced") == 1  # corners: NO_STATISTICS
    rows, skips = _files(run_dir)
    assert len(rows) == 2 and skips["include_unpriced"] is True
    assert run_settle.stat_gap_events(run_dir / "07_settle_skips.json") == {1}

    # The morning D-5 re-settle, without --include-unpriced.
    assert _run(monkeypatch, "--refetch-stat-gaps") == 1
    rows, skips = _files(run_dir)
    assert {r["sofascore_event_id"] for r in rows} == {1, 2}
    assert len(rows) == 2
    assert skips["include_unpriced"] is True, "the day's scope is inherited"
    assert skips["skipped"] == {"corners_total:NO_STATISTICS": 1}


def test_a_lineups_error_skips_the_player_rows_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = [_row(1), _row(2), _row(2, "player_shots_for", subject="Some Player",
                                     line=0.5), _row(3)]
    run_dir = _day(tmp_path, monkeypatch, sheet)
    monkeypatch.setattr(run_settle, "_event_payload", _payload())

    def lineups(client: Any, cache: Any, event: dict[str, Any]) -> Any:
        raise ProviderError("lineups 500")

    monkeypatch.setattr(run_settle, "fetch_lineups", lineups)
    assert _run(monkeypatch) == 1
    rows, skips = _files(run_dir)
    assert sorted(r["sofascore_event_id"] for r in rows) == [1, 2, 3]
    assert skips["skipped"] == {"PROVIDER_ERROR": 1}
    assert [e["sofascore_event_id"] for e in skips["skipped_events"]] == [2]


def test_a_breaker_on_lineups_stops_the_run_but_keeps_what_was_graded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = [_row(1, "player_shots_for", subject="P", line=0.5), _row(1), _row(2)]
    run_dir = _day(tmp_path, monkeypatch, sheet)
    monkeypatch.setattr(run_settle, "_event_payload", _payload())

    def lineups(client: Any, cache: Any, event: dict[str, Any]) -> Any:
        raise CircuitOpenError("open")

    monkeypatch.setattr(run_settle, "fetch_lineups", lineups)
    assert _run(monkeypatch) == 1
    rows, skips = _files(run_dir)
    assert [r["sofascore_event_id"] for r in rows] == [1]
    assert skips["breaker_open"] is True
    # Event 2 was never asked for, and the record says so.
    assert skips["skipped"] == {"PROVIDER_ERROR": 2}


def test_a_tripped_breaker_fails_and_loses_nothing_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = [_row(i) for i in (1, 2, 3)] + [_row(i, "corners_total") for i in (1, 2, 3)]
    run_dir = _day(tmp_path, monkeypatch, sheet)
    monkeypatch.setattr(run_settle, "_event_payload", _payload())
    assert _run(monkeypatch) == 1
    rows_before, _ = _files(run_dir)
    gaps_before = run_settle.stat_gap_events(run_dir / "07_settle_skips.json")
    assert len(rows_before) == 3 and gaps_before == {1, 2, 3}

    # Breaker open from the first event: nothing graded -> FAILED, files kept.
    monkeypatch.setattr(run_settle, "_event_payload", _payload(fail_from=1))
    assert _run(monkeypatch, "--refetch-stat-gaps") == 2
    rows, _ = _files(run_dir)
    assert len(rows) == 3
    assert run_settle.stat_gap_events(run_dir / "07_settle_skips.json") == gaps_before

    # Breaker after one event: that event is re-graded, the others keep theirs.
    monkeypatch.setattr(run_settle, "_event_payload", _payload(fail_from=2))
    assert _run(monkeypatch, "--refetch-stat-gaps") == 1
    rows, skips = _files(run_dir)
    assert len(rows) == 3
    assert run_settle.stat_gap_events(run_dir / "07_settle_skips.json") == gaps_before
    assert skips["breaker_open"] is True
