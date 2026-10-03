"""The cache replay streams its rows into the DB (2026-10-04).

The 2026-10-03 refit held 56.2M replay rows in memory at once; the per-half
markets add ~31.5M more (measured offline that night). main() now writes the
team rows from a generator and measures the reliability curve on the way
through, and `--halves skip` replays exactly as before the halves.
"""

from __future__ import annotations

import json
import random
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

import pytest

import scripts.sofa.calibrate_from_cache as cfc
from bet.sofa.db import migrate


def _reference_curve(rows: list[cfc.SettledRow]) -> dict[str, Any]:
    """reliability_curve as it was written before it streamed."""
    out: dict[str, Any] = {}
    buckets: dict[str, dict[str, list[cfc.SettledRow]]] = {}
    pooled: dict[str, list[cfc.SettledRow]] = {}
    for row in rows:
        i = min(9, int(row.p_central * 10))
        key = f"{i / 10.0:.1f}-{(i + 1) / 10.0:.1f}"
        buckets.setdefault(row.market, {}).setdefault(key, []).append(row)
        pooled.setdefault(key, []).append(row)

    def entry(rs: list[cfc.SettledRow], always: bool) -> dict[str, Any]:
        predicted = statistics.mean(r.p_central for r in rs)
        realised = sum(1 for r in rs if r.won) / len(rs)
        enough = len(rs) >= 150
        return {
            "rows": len(rs), "predicted": round(predicted, 4),
            "realised": round(realised, 4),
            "correction": round(max(0.0, predicted - realised), 4)
            if (enough or always) else 0.0,
            "status": "MEASURED" if enough else "TOO_FEW_ROWS",
        }

    out["_pooled"] = {k: entry(v, True) for k, v in sorted(pooled.items())}
    for market, by in sorted(buckets.items()):
        out[market] = {k: entry(v, False) for k, v in sorted(by.items())}
    return out


def _row(eid: int, market: str, p: float, win: bool) -> cfc.SettledRow:
    return cfc.SettledRow(
        event_id=eid, sport="football", competition_id=17, market=market,
        subject="", line=1.5, direction="UNDER", sample_size=10,
        sample_mean=1.0, sample_sd=1.0, p_central=p, actual=1.0 if win else 2.0,
        outcome="WIN" if win else "LOSS")


def test_streamed_reliability_curve_is_the_old_one() -> None:
    rng = random.Random(3)
    rows = [_row(i, rng.choice(["goals_1h_total", "corners_total"]),
                 round(rng.random(), 6), rng.random() < 0.6) for i in range(2000)]
    got = cfc.reliability_curve(iter(rows))
    want = _reference_curve(rows)
    assert set(got) - {"_doc", "_min_rows"} == set(want)
    for key, value in want.items():
        assert got[key] == value, key


def test_write_settled_takes_a_generator_and_still_drops_only_stale_ids(
    tmp_path: Path,
) -> None:
    db = tmp_path / "sofa.db"
    migrate(str(db))
    cfc.write_settled(
        (r for r in [_row(10, "goals_1h_total", 0.8, True),
                     _row(20, "goals_1h_total", 0.8, True)]), db)
    written = cfc.write_settled(
        (r for r in [_row(10, "goals_1h_total", 0.7, False)]), db,
        drop_event_ids={10, 20})
    assert written == 1
    with sqlite3.connect(db) as conn:
        left = conn.execute(
            "SELECT sofascore_event_id, p_central FROM sofa_settled_row").fetchall()
    assert left == [(10, 0.7)]  # 20 dropped; 10 is being written, kept


def _history() -> list[cfc.Played]:
    played: list[cfc.Played] = []
    for i in range(cfc.MIN_SAMPLE + 1):
        values = {"goals": (float(i % 3), 1.0), "goals_1h": (float(i % 2), 0.0)}
        played.append(cfc.Played(i, 1_000 + i, 1, 100 + i, "football", 17, values))
        played.append(cfc.Played(500 + i, 1_000 + i, 200 + i, 2, "football", 17,
                                 dict(values)))
    played.append(cfc.Played(9999, 2_000, 1, 2, "football", 17,
                             {"goals": (1.0, 1.0), "goals_1h": (0.0, 1.0)}))
    return played


def _run_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, halves: str | None,
              capsys: pytest.CaptureFixture[str]) -> list[tuple[Any, ...]]:
    db = tmp_path / f"{halves}.db"
    migrate(str(db))
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("SOFA_CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(cfc, "load_cache", lambda path, dropped=None: _history())
    monkeypatch.setattr(sys, "argv", [
        "calibrate_from_cache", "--db-path", str(db), "--players", "skip",
        *(["--halves", halves] if halves else [])])
    assert cfc.main() == 0
    summary = json.loads(capsys.readouterr().out.split("SOFA_SUMMARY: ", 1)[1])
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT sofascore_event_id, market, subject, line, direction, "
            "p_central, outcome FROM sofa_settled_row ORDER BY 1, 2, 3, 4, 5"
        ).fetchall()
    half_rows = summary["metrics"]["half_rows_by_market"]
    assert sum(half_rows.values()) == sum(1 for r in rows if "_1h_" in r[1])
    assert summary["metrics"]["settled_rows"] == len(rows)
    assert summary["metrics"]["team_rows"] == len(rows)
    return rows


def test_main_streams_the_halves_and_skip_leaves_the_rest_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with_halves = _run_main(monkeypatch, tmp_path, "include", capsys)
    without = _run_main(monkeypatch, tmp_path, "skip", capsys)
    default = _run_main(monkeypatch, tmp_path, None, capsys)
    assert {r[1] for r in with_halves} >= {"goals_1h_total", "goals_1h_for"}
    assert not any("_1h_" in r[1] for r in without)
    assert [r for r in with_halves if "_1h_" not in r[1]] == without
    assert default == without, "the halves are opt-in"


def test_halves_are_opt_in_and_prepare_refit_passes_them_only_when_asked(
    tmp_path: Path,
) -> None:
    from collections.abc import Sequence

    from scripts.sofa import prepare_refit as pr
    from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths

    for halves in (False, True):
        where = tmp_path / str(halves)
        where.mkdir()
        paths = _paths(where)
        _db(paths.db_path)
        seen: list[list[str]] = []
        inner = _fake_calibrate(paths.db_path)

        def runner(cmd: Sequence[str], env: dict[str, str], log: Path | None,
                   seen: list[list[str]] = seen, inner: pr.Runner = inner
                   ) -> tuple[int, list[str]]:
            seen.append(list(cmd))
            return inner(cmd, env, log)

        report = pr.rebuild_cache_rows(
            paths, dry_run=False, confirm=True, runner=runner,
            require_db_backup=False, halves=halves)
        assert report["halves"] is halves
        cmd = seen[0]
        if halves:
            assert cmd[cmd.index("--halves") + 1] == "include"
        else:
            assert "--halves" not in cmd  # calibrate_from_cache's default: skip
