"""The stakes exams' replay recorder (scripts/sofa/stakes_replay_record.py):
per-month flush as the chronological replay moves past a month, the exam_y
seal at write time, the DONE marker only at a clean exit, resume from the
first unfinished month, and the live-DB refusal. Offline: fake records in a
tmp dir; calibrate_from_cache is never imported."""

from __future__ import annotations

import gzip
import pickle
import stat
from pathlib import Path

from scripts.sofa import stakes_exam_guard as guard
from scripts.sofa import stakes_replay_record as srr

JAN, FEB, MAR = 1735689600, 1738368000, 1740787200  # 2025-01/02/03-01 00:00Z
EXAM_JAN = 1767225600  # 2026-01-01


def _read(p: Path) -> list[object]:
    with gzip.open(p, "rb") as f:
        out: list[object] = pickle.load(f)
    return out


def test_months_between_is_half_open() -> None:
    assert srr.months_between("2025-01-01", "2025-03-01") == ["2025-01", "2025-02"]
    assert srr.months_between("2025-12-15", "2026-01-02") == ["2025-12", "2026-01"]


def test_a_month_is_flushed_and_marked_when_the_replay_moves_past_it(
    tmp_path: Path,
) -> None:
    rec = srr.Recorder(tmp_path, ["2025-01", "2025-02"])
    rec.add("rows", "dev", JAN, "r1")
    rec.add("y", "dev", JAN + 5, "y1")
    rec.add("rows", "dev", JAN + 9, "r2")
    assert not list(tmp_path.glob(guard.CHUNK_GLOB))  # January still running
    rec.add("rows", "dev", FEB, "r3")
    assert _read(tmp_path / "dev/rows/2025-01_000.pkl.gz") == ["r1", "r2"]
    assert _read(tmp_path / "dev/y/2025-01_000.pkl.gz") == ["y1"]
    assert (tmp_path / "months/2025-01.json").is_file()
    assert not (tmp_path / "months/2025-02.json").exists()
    assert rec.buffered == 1 and rec.max_buffered == 3


def test_a_full_buffer_is_written_as_a_numbered_part(tmp_path: Path) -> None:
    rec = srr.Recorder(tmp_path, ["2025-01"])
    rec.LIMIT = 2
    for i in range(5):
        rec.add("rows", "dev", JAN + i, i)
    assert _read(tmp_path / "dev/rows/2025-01_000.pkl.gz") == [0, 1]
    assert _read(tmp_path / "dev/rows/2025-01_001.pkl.gz") == [2, 3]
    assert rec.buffered == 1


def test_exam_outcomes_are_sealed_as_they_are_written(tmp_path: Path) -> None:
    out = tmp_path / "full" / "all"
    manifest = tmp_path / guard.MANIFEST_NAME
    rec = srr.Recorder(out, ["2026-01", "2026-02"], manifest)
    rec.add("y", "exam_y", EXAM_JAN, (1, "goals_for", 7, 1, 2.0))
    rec.add("rows", "exam", EXAM_JAN, "x")
    rec.add("rows", "exam", EXAM_JAN + 31 * 86400, "x2")
    y = out / "exam_y/y/2026-01_000.pkl.gz"
    assert stat.S_IMODE(y.stat().st_mode) == 0
    assert stat.S_IMODE((out / "exam/rows/2026-01_000.pkl.gz").stat().st_mode) != 0
    assert list(guard.load_manifest(manifest)) == [
        "full/all/exam_y/y/2026-01_000.pkl.gz"
    ]


def test_done_marker_only_at_a_clean_exit(tmp_path: Path) -> None:
    out = tmp_path / "full" / "r"
    rec = srr.Recorder(out, ["2025-01", "2025-02"])
    rec.add("rows", "dev", JAN, "r1")
    rec.add("rows", "dev", FEB, "r2")
    assert rec.finish(1, {}) is None
    assert rec.finish(None, {}) is None
    assert not (out / guard.DONE_NAME).exists()
    assert not (out / "months/2025-02.json").exists()
    doc = rec.finish(0, {"secs": 1})
    assert doc is not None and doc["counts"]["dev/rows"] == 2
    # January left the buffer before February's record entered it
    assert doc["counts"]["max_buffered_records"] == 1
    assert guard.replay_problems(tmp_path / "full") == []


def test_resume_replays_from_the_first_unfinished_month(tmp_path: Path) -> None:
    out = tmp_path / "full" / "c1"
    manifest = tmp_path / guard.MANIFEST_NAME
    window = ["2025-12", "2026-01", "2026-02"]
    rec = srr.Recorder(out, window, manifest)
    rec.add("rows", "dev", EXAM_JAN - 86400, "dec")
    rec.LIMIT = 1  # January's parts reach the disk before the month ends
    rec.add("y", "exam_y", EXAM_JAN, "jan_y")
    rec.add("rows", "exam", EXAM_JAN + 1, "jan_part")
    # the process dies here: no finish
    first, stale = srr.plan_resume(out, window)
    assert first == "2026-01"
    assert sorted(p.relative_to(out).as_posix() for p in stale) == [
        "exam/rows/2026-01_000.pkl.gz",
        "exam_y/y/2026-01_000.pkl.gz",
    ]
    assert (out / "dev/rows/2025-12_000.pkl.gz").is_file()
    srr.apply_resume(out, stale, manifest)
    assert not list(out.glob("exam*/*/*"))
    assert guard.load_manifest(manifest) == {}
    assert (out / "dev/rows/2025-12_000.pkl.gz").is_file()


def test_every_month_complete_means_nothing_to_replay(tmp_path: Path) -> None:
    rec = srr.Recorder(tmp_path, ["2025-01"])
    rec.add("rows", "dev", JAN, "r")
    rec.finish(0, {})
    assert srr.plan_resume(tmp_path, ["2025-01"]) == (None, [])
    (tmp_path / guard.DONE_NAME).unlink()
    assert srr.main([str(tmp_path), "--db", str(tmp_path / "copy.db"),
                     "--from", "2025-01-01", "--to", "2025-02-01"]) == 0
    assert (tmp_path / guard.DONE_NAME).is_file()


def test_the_live_database_is_refused(tmp_path: Path) -> None:
    assert srr.main([str(tmp_path / "o"), "--db", str(srr.LIVE_DB),
                     "--from", "2025-01-01", "--to", "2025-02-01"]) == 2
