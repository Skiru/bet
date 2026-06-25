import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from scripts.pipeline_steps._runner import _init_temp_db

# ROOT
ROOT = Path(__file__).resolve().parents[1]

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


def test_generator_respects_pipeline_data_dir(tmp_path):
    # 1. Generator respects BET_PIPELINE_DATA_DIR
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _init_temp_db(db_path)
    insert_test_fixture(db_path, "2026-06-25")
    
    data_dir = tmp_path / "custom_data_dir"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["BET_DB_PATH"] = db_path
    env["BET_PIPELINE_DATA_DIR"] = str(data_dir)
    env["BET_PIPELINE_RUNTIME_MODE"] = "LIVE_SHADOW"
    
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "generate_market_matrix.py"),
        "--date", "2026-06-25",
        "--pipeline-safe",
        "--json-only"
    ]
    
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    
    matrix_file = data_dir / "market_matrix_2026-06-25.json"
    assert matrix_file.exists()
    
    # Clean up DB
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_explicit_output_dir_overrides(tmp_path):
    # 2. Explicit --output-dir overrides legacy path / env
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _init_temp_db(db_path)
    insert_test_fixture(db_path, "2026-06-25")
    
    env_dir = tmp_path / "env_dir"
    cli_dir = tmp_path / "cli_dir"
    
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["BET_DB_PATH"] = db_path
    env["BET_PIPELINE_DATA_DIR"] = str(env_dir)
    env["BET_PIPELINE_RUNTIME_MODE"] = "LIVE_SHADOW"
    
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "generate_market_matrix.py"),
        "--date", "2026-06-25",
        "--output-dir", str(cli_dir),
        "--pipeline-safe",
        "--json-only"
    ]
    
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0
    
    # Assert cli_dir has the file and env_dir does not
    assert (cli_dir / "market_matrix_2026-06-25.json").exists()
    assert not (env_dir / "market_matrix_2026-06-25.json").exists()
    
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_sandbox_prevents_repo_local_writes(tmp_path):
    # 3. LIVE_SHADOW/DRY_RUN generator never writes to repo-local betting/data
    env = os.environ.copy()
    env["BET_PIPELINE_RUNTIME_MODE"] = "LIVE_SHADOW"
    env.pop("BET_DB_PATH", None)
    # Do not set BET_PIPELINE_DATA_DIR or --output-dir, it must reject fallback
    
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "generate_market_matrix.py"),
        "--date", "2026-06-25",
        "--pipeline-safe",
        "--json-only"
    ]
    
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 6  # Failed matrix generation code (rejected fallback)
    assert "forbidden" in res.stdout or "Repo-local fallback is forbidden" in res.stdout


def test_json_only_writes_only_json(tmp_path):
    # 4. --pipeline-safe --json-only writes only the JSON matrix
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _init_temp_db(db_path)
    insert_test_fixture(db_path, "2026-06-25")
    
    cli_dir = tmp_path / "cli_dir"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["BET_DB_PATH"] = db_path
    env["BET_PIPELINE_RUNTIME_MODE"] = "LIVE_SHADOW"
    
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "generate_market_matrix.py"),
        "--date", "2026-06-25",
        "--output-dir", str(cli_dir),
        "--pipeline-safe",
        "--json-only"
    ]
    
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0
    
    files = list(cli_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "market_matrix_2026-06-25.json"
    
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_pipeline_safe_fields_and_no_decisions(tmp_path):
    # 5. Pipeline-safe matrix contains all required safety fields.
    # 6. Pipeline-safe matrix contains no picks, edges, stakes or coupons.
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _init_temp_db(db_path)
    insert_test_fixture(db_path, "2026-06-25")
    
    cli_dir = tmp_path / "cli_dir"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["BET_DB_PATH"] = db_path
    env["BET_PIPELINE_RUNTIME_MODE"] = "LIVE_SHADOW"
    
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "generate_market_matrix.py"),
        "--date", "2026-06-25",
        "--output-dir", str(cli_dir),
        "--pipeline-safe",
        "--json-only"
    ]
    
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0
    
    matrix = json.loads((cli_dir / "market_matrix_2026-06-25.json").read_text(encoding="utf-8"))
    
    assert matrix["schema_version"] == 1
    assert matrix["artifact_type"] == "MARKET_MATRIX"
    assert matrix["pipeline_safe"] is True
    assert matrix["production_selectable"] is False
    assert matrix["betting_decisions_enabled"] is False
    assert matrix["no_pick_edge_stake_coupon_emitted"] is True
    assert "source_summary" in matrix
    assert matrix["source_summary"]["fixtures"] == 1
    
    for e in matrix["events"]:
        assert "sport" in e
        assert "home_team" in e
        assert "away_team" in e
        assert "kickoff" in e
        assert "data_tier" in e
        
        # Check no forbidden keys exist in the events
        forbidden_keys = {"recommended_pick", "internal_pick", "edge", "stake", "coupon", "parlay", "accumulator"}
        for fk in forbidden_keys:
            assert fk not in e
            for sub_list in ("odds_markets", "safety_markets"):
                if sub_list in e:
                    for item in e[sub_list]:
                        assert fk not in item
                        
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_zero_fixtures_produces_block(tmp_path):
    # 8. Zero fixtures produce BLOCKED_NO_DISCOVERY_EVENTS
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _init_temp_db(db_path)
    
    cli_dir = tmp_path / "cli_dir"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["BET_DB_PATH"] = db_path
    env["BET_PIPELINE_RUNTIME_MODE"] = "LIVE_SHADOW"
    
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "generate_market_matrix.py"),
        "--date", "2026-06-25",
        "--output-dir", str(cli_dir),
        "--pipeline-safe",
        "--json-only"
    ]
    
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 3
    assert "BLOCKED_NO_DISCOVERY_EVENTS" in res.stdout
    
    try:
        os.unlink(db_path)
    except OSError:
        pass
