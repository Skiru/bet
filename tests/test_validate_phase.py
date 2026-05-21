import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Ensure scripts dir is in path to import locally.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate_phase


DATE = "2026-05-21"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _check(checks: list[validate_phase.Check], check_id: str) -> validate_phase.Check:
    return next(check for check in checks if check.check_id == check_id)


def _init_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_results (betting_date TEXT, sport TEXT);
            CREATE TABLE fixtures (id INTEGER PRIMARY KEY, kickoff TEXT, sport_id INTEGER);
            CREATE TABLE team_form (updated_at TEXT);
            CREATE TABLE match_stats (
                fixture_id INTEGER,
                team_id INTEGER,
                stat_key TEXT,
                stat_value REAL,
                source TEXT,
                fetched_at TEXT
            );
            CREATE TABLE tipster_picks (betting_date TEXT);
            CREATE TABLE tipster_consensus (betting_date TEXT);
            CREATE TABLE scraper_runs (status TEXT, started_at TEXT, finished_at TEXT);
            CREATE TABLE source_health (source_name TEXT, consecutive_failures INTEGER);
            CREATE TABLE analysis_results (
                betting_date TEXT,
                best_market_name TEXT,
                stats_summary_json TEXT,
                fixture_id INTEGER
            );
            CREATE TABLE gate_results (betting_date TEXT, status TEXT, fixture_id INTEGER);
            CREATE TABLE coupons (
                id INTEGER PRIMARY KEY,
                created_at TEXT,
                status TEXT,
                stake_pln REAL
            );
            CREATE TABLE bets (id INTEGER PRIMARY KEY, coupon_id INTEGER, status TEXT);
            CREATE TABLE pipeline_runs (
                id INTEGER PRIMARY KEY,
                date TEXT,
                step TEXT,
                status TEXT,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                stats TEXT
            );
            CREATE TABLE decision_snapshots (
                id INTEGER PRIMARY KEY,
                bet_id INTEGER,
                betting_date TEXT
            );
            CREATE TABLE decision_outcomes (
                id INTEGER PRIMARY KEY,
                bet_id INTEGER,
                betting_date TEXT
            );
            """
        )


@pytest.fixture
def isolated_validate_phase(tmp_path, monkeypatch):
    data_dir = tmp_path / "betting" / "data"
    coupon_dir = tmp_path / "betting" / "coupons"
    journal_dir = tmp_path / "betting" / "journal"
    config_path = tmp_path / "config" / "betting_config.json"
    db_path = tmp_path / "betting" / "data" / "betting.db"

    data_dir.mkdir(parents=True, exist_ok=True)
    coupon_dir.mkdir(parents=True, exist_ok=True)
    journal_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"bankroll_pln": 1000}), encoding="utf-8")

    _init_db(db_path)

    monkeypatch.setattr(validate_phase, "DATA_DIR", data_dir)
    monkeypatch.setattr(validate_phase, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(validate_phase, "JOURNAL_DIR", journal_dir)
    monkeypatch.setattr(validate_phase, "CONFIG_PATH", config_path)
    monkeypatch.setattr(validate_phase, "_get_db", lambda: sqlite3.connect(db_path))

    return {
        "tmp_path": tmp_path,
        "data_dir": data_dir,
        "coupon_dir": coupon_dir,
        "journal_dir": journal_dir,
        "config_path": config_path,
        "db_path": db_path,
    }


def test_validator_source_drops_legacy_step_ids():
    content = (ROOT / "scripts" / "validate_phase.py").read_text(encoding="utf-8")
    for stale_id in ("s1a_discover", "s1b_parallel", "s1c_aggregate", "s10_summary"):
        assert stale_id not in content, f"Found stale legacy step id: {stale_id}"


def test_validate_data_phase_uses_live_artifacts_without_pipeline_state(isolated_validate_phase):
    data_dir = isolated_validate_phase["data_dir"]
    db_path = isolated_validate_phase["db_path"]

    _write_json(
        data_dir / f"market_matrix_{DATE}.json",
        {"events": [{"sport": "football", "market_count": 8} for _ in range(8)]},
    )
    _write_json(
        data_dir / f"{DATE}_s2_shortlist.json",
        {
            "candidates": [
                {"sport": "football", "home_team": "A", "away_team": "B"},
                {"sport": "basketball", "home_team": "C", "away_team": "D"},
                {"sport": "tennis", "home_team": "E", "away_team": "F"},
            ]
        },
    )

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO scan_results (betting_date, sport) VALUES (?, ?)",
            [(DATE, "football"), (DATE, "basketball"), (DATE, "tennis")],
        )
        conn.executemany(
            "INSERT INTO fixtures (id, kickoff, sport_id) VALUES (?, ?, ?)",
            [(1, f"{DATE}T10:00:00", 1), (2, f"{DATE}T12:00:00", 2), (3, f"{DATE}T15:00:00", 3)],
        )
        conn.execute("INSERT INTO team_form (updated_at) VALUES (?)", (f"{DATE}T08:00:00",))
        conn.execute(
            "INSERT INTO match_stats (fixture_id, team_id, stat_key, stat_value, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "shots", 10.0, "flashscore", f"{DATE}T09:00:00"),
        )
        conn.execute("INSERT INTO tipster_picks (betting_date) VALUES (?)", (DATE,))
        conn.execute(
            "INSERT INTO scraper_runs (status, started_at, finished_at) VALUES (?, ?, ?)",
            ("success", f"{DATE}T06:30:00", f"{DATE}T06:35:00"),
        )

    checks = validate_phase.validate_data_phase(DATE)

    assert not [check for check in checks if check.gate and check.status == "FAIL"]
    assert _check(checks, "D1").status == "PASS"
    assert _check(checks, "D6").status == "PASS"


def _seed_current_data_phase_readiness(data_dir: Path, db_path: Path) -> None:
    _write_json(
        data_dir / f"market_matrix_{DATE}.json",
        {"events": [{"sport": "football", "market_count": 8} for _ in range(8)]},
    )
    _write_json(
        data_dir / f"{DATE}_s2_shortlist.json",
        {
            "candidates": [
                {"sport": "football", "home_team": "A", "away_team": "B"},
                {"sport": "basketball", "home_team": "C", "away_team": "D"},
                {"sport": "tennis", "home_team": "E", "away_team": "F"},
            ]
        },
    )

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO scan_results (betting_date, sport) VALUES (?, ?)",
            [(DATE, "football"), (DATE, "basketball"), (DATE, "tennis")],
        )
        conn.executemany(
            "INSERT INTO fixtures (id, kickoff, sport_id) VALUES (?, ?, ?)",
            [(1, f"{DATE}T10:00:00", 1), (2, f"{DATE}T12:00:00", 2), (3, f"{DATE}T15:00:00", 3)],
        )
        conn.execute("INSERT INTO team_form (updated_at) VALUES (?)", (f"{DATE}T08:00:00",))
        conn.execute(
            "INSERT INTO match_stats (fixture_id, team_id, stat_key, stat_value, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "shots", 10.0, "flashscore", f"{DATE}T09:00:00"),
        )
        conn.execute("INSERT INTO tipster_picks (betting_date) VALUES (?)", (DATE,))
        conn.execute(
            "INSERT INTO scraper_runs (status, started_at, finished_at) VALUES (?, ?, ?)",
            ("success", f"{DATE}T06:30:00", f"{DATE}T06:35:00"),
        )


def test_validate_data_phase_surfaces_s0_prerequisite_failures(isolated_validate_phase, capsys):
    data_dir = isolated_validate_phase["data_dir"]
    db_path = isolated_validate_phase["db_path"]

    _seed_current_data_phase_readiness(data_dir, db_path)
    _write_json(
        data_dir / "betclic_learning_summary.json",
        {"analyzed_at": "2026-05-20T08:00:00", "total_coupons": 12, "rules": []},
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO coupons (id, created_at, status, stake_pln) VALUES (?, ?, ?, ?)",
            (1, "2026-05-20T09:00:00", "pending", 25.0),
        )
        conn.execute(
            "INSERT INTO bets (id, coupon_id, status) VALUES (?, ?, ?)",
            (1, 1, "pending"),
        )

    checks = validate_phase.validate_data_phase(DATE)
    exit_code = validate_phase.run_validation(DATE, "data", "json")
    payload = json.loads(capsys.readouterr().out)

    assert _check(checks, "S0.1").status == "FAIL"
    assert _check(checks, "S0.3").status == "FAIL"
    assert _check(checks, "D6").status == "PASS"
    assert payload["s0_prerequisite_failures"] == 2
    assert payload["execution_gate_failures"] == 0
    assert exit_code == 1


def test_validate_data_phase_blocks_on_missing_previous_day_decision_review(isolated_validate_phase, capsys):
    data_dir = isolated_validate_phase["data_dir"]
    db_path = isolated_validate_phase["db_path"]

    _seed_current_data_phase_readiness(data_dir, db_path)
    _write_json(
        data_dir / "betclic_learning_summary.json",
        {"analyzed_at": f"{DATE}T06:20:00", "total_coupons": 12, "rules": []},
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO coupons (id, created_at, status, stake_pln) VALUES (?, ?, ?, ?)",
            (1, "2026-05-20T10:00:00", "won", 25.0),
        )
        conn.execute(
            "INSERT INTO bets (id, coupon_id, status) VALUES (?, ?, ?)",
            (1, 1, "win"),
        )
        conn.execute(
            "INSERT INTO decision_snapshots (id, bet_id, betting_date) VALUES (?, ?, ?)",
            (1, 1, "2026-05-20"),
        )

    checks = validate_phase.validate_data_phase(DATE)
    exit_code = validate_phase.run_validation(DATE, "data", "json")
    payload = json.loads(capsys.readouterr().out)

    assert _check(checks, "S0.1").status == "PASS"
    assert _check(checks, "S0.2").status == "FAIL"
    assert _check(checks, "S0.3").status == "PASS"
    assert payload["s0_prerequisite_failures"] == 1
    assert payload["execution_gate_failures"] == 0
    assert exit_code == 1


def test_validate_analysis_phase_accepts_json_fallback(isolated_validate_phase):
    data_dir = isolated_validate_phase["data_dir"]

    _write_json(
        data_dir / f"{DATE}_s3_deep_stats.json",
        {
            "analyses": [
                {
                    "home_team": "A",
                    "away_team": "B",
                    "odds": {"market_best": 1.91},
                    "context_flags": [],
                    "upset_risk": {"level": "LOW"},
                },
                {
                    "home_team": "C",
                    "away_team": "D",
                    "ev": 0.08,
                    "context_flags": ["WEATHER_OK"],
                    "upset_risk": {"level": "ELEVATED"},
                },
            ]
        },
    )
    _write_json(
        data_dir / f"{DATE}_s7_gate_results.json",
        {
            "gate_results": {
                "approved": [{"fixture_id": 1}],
                "extended_pool": [{"fixture_id": 2}],
                "rejected": [],
            }
        },
    )

    checks = validate_phase.validate_analysis_phase(DATE)

    assert not [check for check in checks if check.gate and check.status == "FAIL"]
    assert _check(checks, "A1").status == "PASS"
    assert _check(checks, "A2").status == "WARN"
    assert _check(checks, "A6").status == "PASS"


def test_validate_analysis_phase_warns_on_mixed_resume_parity(isolated_validate_phase):
    data_dir = isolated_validate_phase["data_dir"]
    db_path = isolated_validate_phase["db_path"]

    _write_json(
        data_dir / f"{DATE}_s3_deep_stats.json",
        {
            "analyses": [
                {
                    "home_team": "A",
                    "away_team": "B",
                    "odds": {"market_best": 1.91},
                    "context_flags": [],
                    "upset_risk": {"level": "LOW"},
                },
                {
                    "home_team": "C",
                    "away_team": "D",
                    "ev": 0.05,
                    "context_flags": ["LINEUP_OK"],
                    "upset_risk": {"level": "LOW"},
                },
            ]
        },
    )
    _write_json(
        data_dir / f"{DATE}_s7_gate_results.json",
        {
            "gate_results": {
                "approved": [{"fixture_id": 1}],
                "extended_pool": [{"fixture_id": 2}],
                "rejected": [],
            }
        },
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO analysis_results (betting_date, best_market_name, stats_summary_json, fixture_id) VALUES (?, ?, ?, ?)",
            (
                DATE,
                "Corners Total O/U 9.5",
                json.dumps({"ev": 0.05, "context_flags": [], "upset_risk": {"level": "LOW"}}),
                1,
            ),
        )
        conn.execute(
            "INSERT INTO gate_results (betting_date, status, fixture_id) VALUES (?, ?, ?)",
            (DATE, "APPROVED", 1),
        )

    checks = validate_phase.validate_analysis_phase(DATE)

    assert not [check for check in checks if check.gate and check.status == "FAIL"]
    assert _check(checks, "A2").status == "WARN"
    assert _check(checks, "A8").status == "WARN"


def test_build_phase_missing_pdf_is_warning_only(isolated_validate_phase, monkeypatch):
    data_dir = isolated_validate_phase["data_dir"]
    coupon_dir = isolated_validate_phase["coupon_dir"]
    db_path = isolated_validate_phase["db_path"]

    coupon_file = coupon_dir / f"{DATE}-core.md"
    coupon_file.write_text(
        "# Coupon\n\n> WARUNKOWE — sprawdź kursy w Betclic przed postawieniem!\n",
        encoding="utf-8",
    )
    _write_json(
        coupon_dir / f"{DATE}.json",
        {
            "summary": {"core_coupons": 1},
            "pre_coupon_controls": {
                "betclic_market_validation": {"consumed": True, "mode": "validation"},
                "repeat_loss_handoff": {"consumed": True, "excluded_count": 0},
            },
        },
    )
    _write_json(
        data_dir / f"betclic_market_validation_{DATE}.json",
        {"validation": [], "events": [{"event": "A vs B"}]},
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at, completed_at, stats) VALUES (?, ?, ?, ?, ?, ?)",
            (
                DATE,
                "s7_6_repeat_loss_check",
                "completed",
                f"{DATE}T09:55:00",
                f"{DATE}T10:00:00",
                json.dumps(
                    {
                        "date": DATE,
                        "repeat_loss_count": 0,
                        "findings": [],
                    }
                ),
            ),
        )

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "file": str(coupon_file),
                    "coupons_found": 1,
                    "passed": 1,
                    "failed": 0,
                    "checks": [],
                    "global_errors": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(validate_phase.subprocess, "run", fake_run)

    checks = validate_phase.validate_build_phase(DATE)
    exit_code = validate_phase.run_validation(DATE, "build", "json")

    assert not [check for check in checks if check.gate and check.status == "FAIL"]
    assert _check(checks, "B3").status == "PASS"
    assert _check(checks, "B8").status == "PASS"
    assert _check(checks, "B9").status == "WARN"
    assert exit_code == 2


def test_check_structure():
    check = validate_phase.Check(
        check_id="T1",
        name="Test Check",
        status="FAIL",
        value="Tested value",
        gate=True,
        recovery="Do something",
    )
    assert check.check_id == "T1"
    assert check.status == "FAIL"

    payload = check.to_dict()
    assert payload["check"] == "T1"
    assert payload["gate"] is True

    rendered = str(check)
    assert "❌ T1: Test Check" in rendered
    assert "[GATE]" in rendered
    assert "↳ Recovery: Do something" in rendered
import pytest
from pathlib import Path
from unittest.mock import patch
import sys

# Ensure scripts dir is in path to import locally
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from validate_phase import Check, validate_data_phase

def test_no_stale_script_references():
    """Regression test: discover_fixtures.py should not be used."""
    script_path = ROOT / "scripts" / "validate_phase.py"
    content = script_path.read_text()
    assert "discover_fixtures.py" not in content, "Found stale reference to discover_fixtures.py"

def test_recovery_messages_use_discover_events():
    """Regression test: recovery messages should use discover_events.py."""
    with patch("validate_phase._load_pipeline_state", return_value={}):
        checks = validate_data_phase("2026-05-14")
        discover_refs = [c for c in checks if "discover_events.py" in c.recovery]
        assert len(discover_refs) > 0, "No recovery messages with discover_events.py found"
        stale_refs = [c for c in checks if "discover_fixtures.py" in c.recovery]
        assert len(stale_refs) == 0, "Found recovery message with discover_fixtures.py"

def test_check_structure():
    """Test the Check class structure."""
    check = Check(
        check_id="T1",
        name="Test Check",
        status="FAIL",
        value="Tested value",
        gate=True,
        recovery="Do something"
    )
    assert check.check_id == "T1"
    assert check.status == "FAIL"
    
    d = check.to_dict()
    assert d["check"] == "T1"
    assert d["gate"] is True
    
    s = str(check)
    assert "❌ T1: Test Check" in s
    assert "[GATE]" in s
    assert "↳ Recovery: Do something" in s
