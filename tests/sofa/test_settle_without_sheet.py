"""SETTLE and the results PDF on a day whose 05_sheet.json is gone.

2026-11-19: most 05_sheet.json since 10-10 were deleted by accident. The
morning resettle_sweep then re-settled nothing (run_settle exited 2 on the
missing sheet; 102 printed legs with late statistic gaps stayed ungraded) and
build_coupon_pdf.py --with-results crashed reading the sheet for its
UNFITTED_CONSTANTS line.

Without a sheet SETTLE re-grades the rows 07_settled.json already holds (each
is what SETTLE copied from its sheet row) and grades the printed / read-removed
legs never graded through the A4 path (07_settled_printed.json, never
sofa_settled_row: their forecast columns exist nowhere on disk). Nothing is
invented; an ungraded unprinted sheet row is lost.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.sofa import build_coupon_pdf, run_settle

DATE = "2026-11-17"


def _row(event_id: int, market: str = "goals_total") -> dict[str, Any]:
    return {
        "sofascore_event_id": event_id, "sport": "football", "market": market,
        "subject": "", "line": 2.5, "direction": "OVER",
        "sample_size": 10, "sample_mean": 2.6, "sample_sd": 1.2,
        "p_central": 0.55, "p_bar": 0.56, "market_p": 0.5,
        "offered_odds": 1.9, "verdict": "VALUE",
    }


def _leg(event_id: int) -> dict[str, Any]:
    return {
        "sofascore_event_id": event_id, "sport": "football",
        "market": "goals_total", "subject": "", "line": 2.5,
        "direction": "OVER", "offered_odds": 1.9, "confidence": 0.72,
        "unfitted_constants": ["K_PRICE"],
    }


def _event(event_id: int) -> dict[str, Any]:
    return {
        "id": event_id, "status": {"type": "finished", "code": 100},
        "homeScore": {"current": 2}, "awayScore": {"current": 1},
        "tournament": {"uniqueTournament": {"id": 17}},
    }


def _day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Event 1 unprinted, 2 printed, 3 read-removed, 4 unprinted."""
    run_dir = tmp_path / "runs" / DATE
    run_dir.mkdir(parents=True)
    sheet = [_row(i) for i in (1, 2, 3, 4)]
    (run_dir / "05_sheet.json").write_text(json.dumps(sheet), encoding="utf-8")
    (run_dir / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": i, "sport": "football",
         "home_name": f"Home {i}", "away_name": f"Away {i}"} for i in (1, 2, 3, 4)
    ]), encoding="utf-8")
    (run_dir / "11_coupon.json").write_text(json.dumps({
        "pdf_max_singles": None, "prints_builders": True,
        "legs": [_leg(2), _leg(3)], "singles": [_leg(2)], "builders": [],
        "removed_by_reads": [_leg(3) | {"reason": "WATCH"}],
    }), encoding="utf-8")
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.setenv("SOFA_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(run_settle, "SofascoreClient", lambda config: object())
    monkeypatch.setattr(run_settle, "SofaCache", lambda config: object())
    return run_dir


def _payload(unfinished: frozenset[int]) -> Any:
    def fake(client: Any, cache: Any, event_id: int, refetch: bool = False) -> Any:
        if event_id in unfinished:
            return "NOT_FINISHED"
        return _event(event_id), {"statistics": []}, {"incidents": []}
    return fake


def _run(monkeypatch: pytest.MonkeyPatch, *flags: str) -> int:
    monkeypatch.setattr(sys, "argv", ["run_settle", "--date", DATE, *flags])
    return run_settle.main()


def _db_rows(tmp_path: Path) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(tmp_path / "sofa.db")
    try:
        return conn.execute(
            "SELECT sofascore_event_id, p_central, p_bar, sample_mean, outcome "
            "FROM sofa_settled_row ORDER BY sofascore_event_id").fetchall()
    finally:
        conn.close()


def test_resettle_without_sheet_grades_printed_and_removed_legs_only_in_a4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _day(tmp_path, monkeypatch)
    # The first SETTLE: events 2-4 not finished yet.
    monkeypatch.setattr(run_settle, "_event_payload",
                        _payload(frozenset({2, 3, 4})))
    assert _run(monkeypatch) == 1
    first = json.loads((run_dir / "07_settled.json").read_text(encoding="utf-8"))
    assert [r["sofascore_event_id"] for r in first] == [1]
    assert _db_rows(tmp_path) == [(1, 0.55, 0.56, 2.6, "WIN")]

    # The sheet is deleted; the re-settle finds every match over.
    (run_dir / "05_sheet.json").unlink()
    monkeypatch.setattr(run_settle, "_event_payload", _payload(frozenset()))
    capsys.readouterr()
    assert _run(monkeypatch, "--refetch-stat-gaps") == 0
    err = capsys.readouterr().err
    assert ("SHEET_RECONSTRUCTED: 1 rows from 07_settled + 2 from 11_coupon.json"
            in err)

    # The DB holds exactly what it held: nothing invented for 2, 3 or 4.
    assert _db_rows(tmp_path) == [(1, 0.55, 0.56, 2.6, "WIN")]
    rows = json.loads((run_dir / "07_settled.json").read_text(encoding="utf-8"))
    assert [r["sofascore_event_id"] for r in rows] == [1]
    assert {k: rows[0][k] for k in ("p_central", "p_bar", "sample_sd", "verdict")} \
        == {"p_central": 0.55, "p_bar": 0.56, "sample_sd": 1.2, "verdict": "VALUE"}
    # The printed leg (2) and the read-removed one (3) graded beside it (A4);
    # the unprinted never-graded row (4) is lost.
    a4 = json.loads((run_dir / "07_settled_printed.json").read_text(encoding="utf-8"))
    assert sorted((r["sofascore_event_id"], r["outcome"]) for r in a4) == [
        (2, "WIN"), (3, "WIN")]
    assert all("p_central" not in r for r in a4)
    assert not (run_dir / "05_sheet.json").exists()


def test_no_sheet_and_no_settled_file_is_still_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _day(tmp_path, monkeypatch)
    (run_dir / "05_sheet.json").unlink()
    assert _run(monkeypatch) == 2
    assert "07_settled.json missing" in capsys.readouterr().err


def test_sheet_from_settled_drops_a_row_without_its_forecast_columns(
    tmp_path: Path,
) -> None:
    whole = _row(1) | {"actual_value": 3.0, "outcome": "WIN"}
    unpriced = _row(2) | {"offered_odds": None, "market_p": None,
                          "verdict": "NO_PRICE", "outcome": "LOSS"}
    broken = {k: v for k, v in _row(3).items() if k != "p_central"}
    nulled = _row(4) | {"sample_sd": None}
    (tmp_path / "07_settled.json").write_text(
        json.dumps([whole, unpriced, broken, nulled]), encoding="utf-8")
    got = run_settle.sheet_from_settled(tmp_path)
    assert got is not None
    assert [r["sofascore_event_id"] for r in got] == [1, 2]
    assert run_settle.sheet_from_settled(tmp_path / "nowhere") is None


def test_pdf_unfitted_constants_without_a_sheet_come_from_the_legs(
    tmp_path: Path,
) -> None:
    assert build_coupon_pdf.sheet_rows_or_empty(tmp_path) == []
    (tmp_path / "05_sheet.json").write_text(
        json.dumps([_row(1) | {"notes": ["UNFITTED_CONSTANTS: K_PRICE"]}]),
        encoding="utf-8")
    rows = build_coupon_pdf.sheet_rows_or_empty(tmp_path)
    assert build_coupon_pdf.unfitted_constants(
        rows, {(1, "goals_total", "", 2.5, "OVER")}) == ["K_PRICE"]


def test_a_results_render_without_a_sheet_keeps_the_unfitted_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pypdf = pytest.importorskip("pypdf")
    from tests.sofa import test_coupon_results as tcr

    run = tcr._day(tmp_path)
    (run / "05_sheet.json").unlink()
    coupon = json.loads((run / "11_coupon.json").read_text(encoding="utf-8"))
    coupon["singles"][0]["unfitted_constants"] = ["K_PRICE"]
    (run / "11_coupon.json").write_text(json.dumps(coupon), encoding="utf-8")
    pdf = tcr._pdf_module()
    for extra in ([], ["--with-results"]):
        monkeypatch.setattr(sys, "argv", [
            "build_coupon_pdf.py", "--date", "2026-10-16",
            "--runs-dir", str(tmp_path), *extra])
        assert pdf.main() == 0
        text = " ".join(" ".join(
            p.extract_text() for p in pypdf.PdfReader(
                run / "KUPON_2026-10-16.pdf").pages).split())
        assert "UNFITTED_CONSTANTS: K_PRICE" in text
    assert "Podsumowanie wyników" in text


def test_a_results_render_without_samples_renders_but_a_print_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """03_samples.json feeds only the own-sample k/n beside a leg: a results
    render of a day whose samples were deleted (2026-11-05) still renders; a
    print without them still fails loudly."""
    pytest.importorskip("pypdf")
    from tests.sofa import test_coupon_results as tcr

    run = tcr._day(tmp_path)
    pdf = tcr._pdf_module()
    argv = ["build_coupon_pdf.py", "--date", "2026-10-16", "--runs-dir", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", argv)
    assert pdf.main() == 0  # the print, with its samples
    (run / "03_samples.json").unlink()
    monkeypatch.setattr(sys, "argv", [*argv, "--with-results"])
    assert pdf.main() == 0
    assert (run / "KUPON_2026-10-16.pdf").exists()
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(FileNotFoundError):
        pdf.main()
