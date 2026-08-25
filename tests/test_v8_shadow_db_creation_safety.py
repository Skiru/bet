import sqlite3
from pathlib import Path

import pytest

from bet.db.schema import init_db
from bet.pipeline.launch_bridge import create_runtime_analysis_shadow_db


def _canonical(path: Path) -> Path:
    conn = sqlite3.connect(path)
    init_db(conn)
    conn.close()
    return path


def test_existing_shadow_is_never_unlinked(tmp_path):
    canonical = _canonical(tmp_path / "canonical.db")
    run_root = tmp_path / "run"
    shadow = run_root / "data" / "runtime_analysis_shadow.db"
    shadow.parent.mkdir(parents=True)
    shadow.write_bytes(b"existing-plan")
    with pytest.raises(FileExistsError, match="PLAN_RUN_COLLISION"):
        create_runtime_analysis_shadow_db(
            canonical, run_root, "run-1", allow_overwrite=True
        )
    assert shadow.read_bytes() == b"existing-plan"


def test_symlink_shadow_target_is_rejected(tmp_path):
    canonical = _canonical(tmp_path / "canonical.db")
    run_root = tmp_path / "run"
    real_run = tmp_path / "real-run"
    real_run.mkdir()
    run_root.symlink_to(real_run, target_is_directory=True)
    with pytest.raises(ValueError, match="SYMLINK"):
        create_runtime_analysis_shadow_db(canonical, run_root, "run-1")


def test_canonical_and_shadow_same_file_is_rejected(tmp_path):
    run_root = tmp_path / "run"
    canonical = run_root / "data" / "runtime_analysis_shadow.db"
    canonical.parent.mkdir(parents=True)
    _canonical(canonical)
    with pytest.raises(ValueError, match="CANONICAL_SHADOW_SAME_FILE"):
        create_runtime_analysis_shadow_db(canonical, run_root, "run-1")


def test_failed_backup_does_not_publish_partial_shadow(tmp_path):
    canonical = tmp_path / "invalid.db"
    canonical.write_bytes(b"not sqlite")
    run_root = tmp_path / "run"
    with pytest.raises(sqlite3.DatabaseError):
        create_runtime_analysis_shadow_db(canonical, run_root, "run-1")
    assert not run_root.exists()


def test_successful_shadow_uses_sqlite_backup_and_is_integral(tmp_path):
    canonical = _canonical(tmp_path / "canonical.db")
    result = create_runtime_analysis_shadow_db(canonical, tmp_path / "run", "run-1")
    assert result["status"] == "PASS"
    shadow = sqlite3.connect(result["shadow_db_path"])
    assert shadow.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    shadow.close()


def test_existing_run_root_is_rejected_before_partial_mutation(tmp_path):
    canonical = _canonical(tmp_path / "canonical.db")
    run_root = tmp_path / "run"
    run_root.mkdir()
    sentinel = run_root / "owned.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    with pytest.raises(FileExistsError, match="PLAN_RUN_COLLISION"):
        create_runtime_analysis_shadow_db(canonical, run_root, "run-1")
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(run_root.iterdir()) == [sentinel]


def test_failed_backup_does_not_change_canonical_bytes(tmp_path):
    canonical = tmp_path / "invalid.db"
    canonical.write_bytes(b"not sqlite")
    before = canonical.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        create_runtime_analysis_shadow_db(canonical, tmp_path / "run", "run-1")
    assert canonical.read_bytes() == before
