"""A long reader must not make a cache write fail (2026-10-01, RESOLVE).

RESOLVE died on `database is locked` in `SofaCache.save_entity_events` while
other processes were reading the database. In `journal_mode=delete` a COMMIT
needs every reader gone; these tests reproduce that and pin both defences in
bet.sofa.db: WAL, and a COMMIT that is retried while the file is busy.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

import bet.sofa.db as db


def _seed(path: Path, *, mode: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA journal_mode={mode}")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(1000)])
    conn.commit()
    conn.close()


def _open_reader(path: Path) -> sqlite3.Connection:
    """A read-only connection holding an open read transaction, like a scan."""
    reader = sqlite3.connect(
        f"file:{path}?mode=ro", uri=True, isolation_level=None, check_same_thread=False
    )
    reader.execute("BEGIN")
    reader.execute("SELECT x FROM t").fetchone()
    return reader


def test_the_incident_reproduces_in_delete_mode(tmp_path: Path) -> None:
    """The control: without the fix a reader blocks the commit outright."""
    path = tmp_path / "d.db"
    _seed(path, mode="DELETE")
    reader = _open_reader(path)
    writer = sqlite3.connect(path, timeout=0.05)
    writer.execute("INSERT INTO t VALUES (-1)")
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        writer.commit()
    reader.close()
    writer.close()


def test_migrate_switches_a_new_database_to_wal(tmp_path: Path) -> None:
    path = tmp_path / "new.db"
    db.migrate(str(path))
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.close()


def test_migrate_switches_an_existing_delete_mode_database(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    _seed(path, mode="DELETE")
    db.migrate(str(path))
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1000, (
        "switching the journal mode must not touch the data"
    )
    conn.close()


def test_in_wal_a_reader_does_not_block_the_commit(tmp_path: Path) -> None:
    path = tmp_path / "w.db"
    db.migrate(str(path))
    _seed_conn = db.get_connection(str(path))
    _seed_conn.execute("CREATE TABLE t (x INTEGER)")
    _seed_conn.execute("INSERT INTO t VALUES (1)")
    _seed_conn.commit()
    _seed_conn.close()

    reader = _open_reader(path)
    writer = db.get_connection(str(path), timeout=0.05)
    started = time.monotonic()
    writer.execute("INSERT INTO t VALUES (2)")
    writer.commit()
    assert time.monotonic() - started < 1.0
    writer.close()
    reader.close()


def test_read_only_connections_still_read_a_wal_database(tmp_path: Path) -> None:
    """football_rating / tennis_rating / score_model open the file mode=ro."""
    path = tmp_path / "ro.db"
    _seed(path, mode="DELETE")
    db.migrate(str(path))
    ro = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    assert ro.execute("SELECT count(*) FROM t").fetchone()[0] == 1000
    ro.close()


def test_a_busy_commit_is_retried_until_the_reader_leaves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even in delete mode (a file WAL could not be switched on yet)."""
    monkeypatch.setattr(db, "COMMIT_BACKOFF_S", 0.05)
    path = tmp_path / "r.db"
    _seed(path, mode="DELETE")
    reader = _open_reader(path)
    threading.Timer(0.3, reader.close).start()

    writer = db.get_connection(str(path), timeout=0.05)
    writer.execute("INSERT INTO t VALUES (-1)")
    writer.commit()  # raised "database is locked" before the fix
    writer.close()

    check = sqlite3.connect(path)
    assert check.execute("SELECT count(*) FROM t WHERE x = -1").fetchone()[0] == 1
    check.close()


def test_a_commit_that_stays_busy_still_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(db, "COMMIT_BACKOFF_S", 0.01)
    monkeypatch.setattr(db, "COMMIT_ATTEMPTS", 3)
    path = tmp_path / "s.db"
    _seed(path, mode="DELETE")
    reader = _open_reader(path)
    writer = db.get_connection(str(path), timeout=0.01)
    writer.execute("INSERT INTO t VALUES (-1)")
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        writer.commit()
    assert capsys.readouterr().err.count("DB_COMMIT_BUSY") == 2
    reader.close()
    writer.close()


def test_enable_wal_on_a_held_file_keeps_its_mode_and_does_not_raise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "h.db"
    _seed(path, mode="DELETE")
    holder = sqlite3.connect(path, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    assert db.enable_wal(str(path)) in ("delete", "busy")
    assert "DB_WAL_NOT_ENABLED" in capsys.readouterr().err
    holder.execute("ROLLBACK")
    holder.close()
    assert db.enable_wal(str(path)) == "wal", "a later call takes once the file is free"
