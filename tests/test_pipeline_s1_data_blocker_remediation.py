"""Focused tests for S1 duplicate fixture-source remediation behavior."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.pipeline_steps import s1_discover


def _runtime_environ(tmp_path: Path, run_id: str = "run-s1-remediation") -> dict[str, str]:
    run_root = tmp_path / "sandbox"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "LIVE_SHADOW",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": run_id,
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _evidence_path(tmp_path: Path, run_id: str = "run-s1-remediation") -> Path:
    return tmp_path / "sandbox" / "pipeline_runs" / "2026-06-25" / run_id / "artifacts" / "S1.json"


def test_s1_live_shadow_blocker_remediation_avoids_duplicate_mapping_signal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    environ = _runtime_environ(tmp_path)
    argv = [
        "s1_discover.py",
        "--date",
        "2026-06-25",
        "--run-id",
        "run-s1-remediation",
        "--runtime-mode",
        "LIVE_SHADOW",
        "--allow-live-network",
        "--dry-run",
    ]

    def _next_blocker(*args, **kwargs):
        print("BLOCKED_MISSING_MARKET_MATRIX")
        return 2

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch(
        "scripts.pipeline_steps.s1_discover._run_s1_scripts", side_effect=_next_blocker
    ):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "BLOCKED_MISSING_MARKET_MATRIX" in captured.out
    assert "Duplicate fixture_sources mapping" not in captured.out

    evidence_path = _evidence_path(tmp_path)
    assert evidence_path.exists()
    assert str(evidence_path).startswith(str(tmp_path / "sandbox"))
    assert "/reports/" not in str(evidence_path)

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["artifact_type"] == "SCRIPT_EVIDENCE"
    assert evidence["step_id"] == "S1"
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_MISSING_MARKET_MATRIX"]
    assert "BLOCKED_FIXTURE_SOURCE_DUPLICATE_MAPPING" not in json.dumps(evidence)


def test_s1_wrapper_maps_real_shortlist_market_matrix_message_to_controlled_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    environ = _runtime_environ(tmp_path, run_id="run-s1-real-market-matrix")
    argv = [
        "s1_discover.py",
        "--date",
        "2026-06-25",
        "--run-id",
        "run-s1-real-market-matrix",
        "--runtime-mode",
        "LIVE_SHADOW",
        "--allow-live-network",
        "--dry-run",
    ]

    def _shortlist_message(*args, **kwargs):
        print(
            "[s1e_shortlist] ERROR: PRECONDITION_FAILED: market_matrix_{date}.json not found. "
            "Run generate_market_matrix.py first."
        )
        return 2

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch(
        "scripts.pipeline_steps.s1_discover._run_s1_scripts", side_effect=_shortlist_message
    ):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "market_matrix_{date}.json not found" in captured.out

    evidence = json.loads(_evidence_path(tmp_path, run_id="run-s1-real-market-matrix").read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_MISSING_MARKET_MATRIX"]


def test_s1_remediation_keeps_writes_inside_tmp_runtime_root(tmp_path: Path):
    environ = _runtime_environ(tmp_path, run_id="run-s1-pass")
    argv = [
        "s1_discover.py",
        "--betting-day",
        "2026-06-25",
        "--run-id",
        "run-s1-pass",
        "--runtime-mode",
        "LIVE_SHADOW",
        "--allow-live-network",
        "--dry-run",
    ]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch(
        "scripts.pipeline_steps.s1_discover._run_s1_scripts", return_value=0
    ):
        with pytest.raises(SystemExit) as exc_info:
            s1_discover.main()

    assert exc_info.value.code == 0
    evidence_path = _evidence_path(tmp_path, run_id="run-s1-pass")
    assert evidence_path.exists()
    assert str(evidence_path).startswith(str(tmp_path / "sandbox"))
    assert "/reports/" not in str(evidence_path)
    if (tmp_path / "reports").exists():
        assert not list((tmp_path / "reports").rglob("*"))
    if (tmp_path / "betting").exists():
        assert not list((tmp_path / "betting").rglob("*"))


def test_s1_wrapper_passes_temp_db_path_to_discover_events(tmp_path: Path, monkeypatch):
    environ = _runtime_environ(tmp_path, run_id="run-s1-db-path")
    environ["BET_PIPELINE_LIVE_ACK"] = "I_UNDERSTAND_LIVE_PROVIDER_CALLS"
    calls: list[tuple[list[str], dict[str, str]]] = []

    def _fake_init_db(path: str) -> None:
        Path(path).touch()

    def _fake_run(cmd, env, capture_output, text):
        calls.append((cmd, env.copy()))
        if "generate_market_matrix.py" in cmd[1]:
            data_dir = env.get("BET_PIPELINE_DATA_DIR")
            if data_dir:
                matrix_path = Path(data_dir) / "market_matrix_2026-06-25.json"
                matrix_path.parent.mkdir(parents=True, exist_ok=True)
                matrix_path.write_text(json.dumps({
                    "schema_version": 1,
                    "artifact_type": "MARKET_MATRIX",
                    "date": "2026-06-25",
                    "pipeline_safe": True,
                    "production_selectable": False,
                    "betting_decisions_enabled": False,
                    "no_pick_edge_stake_coupon_emitted": True,
                    "events": [
                        {
                            "sport": "football",
                            "home_team": "Team A",
                            "away_team": "Team B",
                            "kickoff": "2026-06-25T18:00:00Z",
                            "data_tier": "FIXTURE_ONLY"
                        }
                    ]
                }), encoding="utf-8")
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr(s1_discover, "_init_temp_db", _fake_init_db)
    monkeypatch.setattr(s1_discover.subprocess, "run", _fake_run)

    run_metrics = {
        "discovery_rc": -1,
        "market_matrix_rc": -1,
        "shortlist_rc": -1,
        "market_matrix_path": "",
        "market_matrix_event_count": 0,
        "market_matrix_schema_version": 1,
        "market_matrix_pipeline_safe": False,
        "market_matrix_validated": False,
        "shortlist_started": False
    }

    rc = s1_discover._run_s1_scripts(
        date="2026-06-25",
        dry_run=True,
        allow_write=False,
        allow_live_network=True,
        runtime_mode="LIVE_SHADOW",
        child_env=environ,
        run_metrics=run_metrics,
    )

    assert rc == 0
    assert len(calls) == 3
    discover_cmd, discover_env = calls[0]
    assert discover_cmd[1].endswith("scripts/discover_events.py")
    assert "--db-path" in discover_cmd
    db_path = discover_cmd[discover_cmd.index("--db-path") + 1]
    assert Path(db_path).name.startswith("bet_dryrun_")
    assert not db_path.endswith("betting/data/betting.db")
    assert discover_env["DATABASE_URL"] == f"sqlite:///{db_path}"
