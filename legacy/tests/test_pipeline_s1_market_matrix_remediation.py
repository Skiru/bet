import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from scripts.pipeline_steps import s1_discover
from scripts.pipeline_steps._runner import _init_temp_db

ROOT = Path(__file__).resolve().parents[1]
original_run = s1_discover.run_bounded_process

def _runtime_environ(tmp_path: Path, run_id: str, db_path: str) -> dict[str, str]:
    run_root = tmp_path / "sandbox"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "LIVE_SHADOW",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": run_id,
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
        "DATABASE_URL": f"sqlite:///{db_path}",
        "BET_DB_PATH": db_path,
    }

def _evidence_path(tmp_path: Path, run_id: str) -> Path:
    return tmp_path / "sandbox" / "pipeline_runs" / "2026-06-25" / run_id / "artifacts" / "S1.json"

def insert_test_fixture(db_path: str, date: str = "2026-06-25"):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO sports (name) VALUES ('football')")
        sport_id = conn.execute("SELECT id FROM sports WHERE name='football'").fetchone()[0]

        conn.execute("INSERT INTO teams (name, sport_id) VALUES ('Team A', ?)", (sport_id,))
        conn.execute("INSERT INTO teams (name, sport_id) VALUES ('Team B', ?)", (sport_id,))
        ht_id = conn.execute("SELECT id FROM teams WHERE name='Team A'").fetchone()[0]
        at_id = conn.execute("SELECT id FROM teams WHERE name='Team B'").fetchone()[0]

        conn.execute("INSERT INTO competitions (name, sport_id) VALUES ('English Premier League', ?)", (sport_id,))
        comp_id = conn.execute("SELECT id FROM competitions WHERE name='English Premier League'").fetchone()[0]

        conn.execute(
            "INSERT INTO fixtures (sport_id, competition_id, home_team_id, away_team_id, kickoff, status, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, 'scheduled', 'api', '2026-06-25T12:00:00Z')",
            (sport_id, comp_id, ht_id, at_id, f"{date}T18:00:00Z")
        )
        conn.commit()
    finally:
        conn.close()


def test_deterministic_s1_fixture_reaches_pass(tmp_path, capsys):
    # Test successful S1 fixture run reaches S1 PASS
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _init_temp_db(db_path)

    run_id = "run-s1-deterministic-pass"
    environ = _runtime_environ(tmp_path, run_id, db_path)

    # Make sure subdirectories exist
    Path(environ["BET_PIPELINE_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(environ["BET_PIPELINE_COUPON_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(environ["BET_PIPELINE_ARTIFACT_DIR"]).mkdir(parents=True, exist_ok=True)

    argv = [
        "s1_discover.py",
        "--date", "2026-06-25",
        "--run-id", run_id,
        "--runtime-mode", "LIVE_SHADOW",
        "--allow-live-network",
        "--allow-write",
    ]

    def _mock_run(cmd, *args, **kwargs):
        if any("discover_events.py" in arg for arg in cmd):
            insert_test_fixture(db_path, "2026-06-25")
            res = MagicMock()
            res.returncode = 0
            res.stdout = "AGENT_SUMMARY:{}"
            res.stderr = ""
            return res
        return original_run(cmd, *args, **kwargs)

    # Set the mock live ack
    with patch.dict(os.environ, {**environ, "BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS"}, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s1_discover.run_bounded_process", side_effect=_mock_run):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 0

    evidence_file = _evidence_path(tmp_path, run_id)
    assert evidence_file.exists()

    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert evidence["payload"]["discovery_rc"] == 0
    assert evidence["payload"]["market_matrix_rc"] == 0
    assert evidence["payload"]["shortlist_rc"] == 0
    assert evidence["payload"]["market_matrix_validated"] is True
    assert evidence["payload"]["market_matrix_event_count"] == 1
    assert "market_matrix_path" in evidence["payload"]

    matrix_path = Path(evidence["payload"]["market_matrix_path"])
    assert matrix_path.exists()
    matrix_data = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert all(e["data_tier"] == "FIXTURE_ONLY" for e in matrix_data.get("events", []))

    # Ensure no reports writes
    assert "reports" not in str(evidence_file)

    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_no_fixture_reaches_block(tmp_path):
    # Test controlled no-fixture run reaches S1 BLOCK with BLOCKED_NO_DISCOVERY_EVENTS
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _init_temp_db(db_path) # no fixture inserted

    run_id = "run-s1-deterministic-block"
    environ = _runtime_environ(tmp_path, run_id, db_path)

    Path(environ["BET_PIPELINE_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(environ["BET_PIPELINE_COUPON_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(environ["BET_PIPELINE_ARTIFACT_DIR"]).mkdir(parents=True, exist_ok=True)

    argv = [
        "s1_discover.py",
        "--date", "2026-06-25",
        "--run-id", run_id,
        "--runtime-mode", "LIVE_SHADOW",
        "--allow-live-network",
        "--allow-write",
    ]

    def _mock_run(cmd, *args, **kwargs):
        if any("discover_events.py" in arg for arg in cmd):
            # Write nothing
            res = MagicMock()
            res.returncode = 0
            res.stdout = "AGENT_SUMMARY:{}"
            res.stderr = ""
            return res
        return original_run(cmd, *args, **kwargs)

    with patch.dict(os.environ, {**environ, "BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS"}, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s1_discover.run_bounded_process", side_effect=_mock_run):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 3

    evidence_file = _evidence_path(tmp_path, run_id)
    assert evidence_file.exists()

    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert "BLOCKED_NO_DISCOVERY_EVENTS" in evidence["blocked_reasons"]

    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_invalid_matrix_cannot_start_shortlist(tmp_path):
    # Empty matrix cannot be treated as PASS.
    # Invalid matrix cannot start build_shortlist.
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _init_temp_db(db_path)
    insert_test_fixture(db_path, "2026-06-25")

    run_id = "run-s1-invalid-matrix"
    environ = _runtime_environ(tmp_path, run_id, db_path)

    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    Path(environ["BET_PIPELINE_COUPON_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(environ["BET_PIPELINE_ARTIFACT_DIR"]).mkdir(parents=True, exist_ok=True)

    # Write an invalid matrix JSON file
    matrix_file = data_dir / "market_matrix_2026-06-25.json"
    matrix_file.write_text("INVALID JSON CONTENT", encoding="utf-8")

    argv = [
        "s1_discover.py",
        "--date", "2026-06-25",
        "--run-id", run_id,
        "--runtime-mode", "LIVE_SHADOW",
        "--allow-live-network",
        "--allow-write",
    ]

    # We patch generate_market_matrix so it returns 0 (simulating generator "succeeded" but wrote invalid matrix somehow,
    # or the matrix validation intercepts and blocks shortlist)
    with patch.dict(os.environ, {**environ, "BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS"}, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s1_discover.run_bounded_process") as mock_run:

        # mock discover_events and generate_market_matrix to succeed (return code 0)
        # but build_shortlist won't even be called because matrix is invalid
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="", timed_out=False)

        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 2  # blocked code from validation

    evidence_file = _evidence_path(tmp_path, run_id)
    assert evidence_file.exists()

    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert "BLOCKED_MARKET_MATRIX_INVALID" in evidence["blocked_reasons"]

    try:
        os.unlink(db_path)
    except OSError:
        pass
