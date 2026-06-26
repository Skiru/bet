"""S7 valuation input provenance regression tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pipeline_steps import s5_gate


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s7-valuation-{tmp_path.name}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s7-valuation",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _canonical_evidence_path(environ: dict[str, str]) -> Path:
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / "S7.json"
    )


def _write_s4_pass_evidence(environ: dict[str, str]) -> None:
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S4",
        "status": "PASS",
        "payload": {
            "step_id": "S4",
        },
    }
    for path in (
        artifact_dir / "S4.json",
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / "S4.json",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _s4_candidate_payload() -> dict:
    return {
        "candidates": [
            {
                "fixture_id": 10,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "best_market": {
                    "name": "Over 2.5",
                    "direction": "OVER",
                    "safety_score": 0.82,
                },
                "market_count": 4,
                "ev": 0.11,
                "odds": {"market_best": 1.91},
            }
        ]
    }


def test_s7_prefers_s4_valuation_input_over_s3_and_records_evidence(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_s4_pass_evidence(environ)

    s4_path = _write_json(data_dir / "2026-06-25_s4_valuation_candidates.json", _s4_candidate_payload())
    _write_json(data_dir / "2026-06-25_s3_deep_stats.json", {"analyses": [{"home_team": "Gamma", "away_team": "Delta"}]})

    recorded: dict[str, object] = {}

    def fake_run(cmd, env=None, capture_output=None, text=None):
        recorded["cmd"] = cmd
        recorded["env"] = env
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 0
    assert recorded["cmd"][-2] == "--input"
    assert Path(recorded["cmd"][-1]).resolve() == s4_path.resolve()

    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert Path(evidence["payload"]["s7_input_path"]).resolve() == s4_path.resolve()
    assert evidence["payload"]["s7_input_source_step"] == "S4"
    assert evidence["payload"]["s7_input_source_kind"] == "s4_data_file"
    assert evidence["payload"]["s7_input_contains_odds"] is True
    assert evidence["payload"]["s7_input_contains_ev"] is True
    assert evidence["payload"]["s7_input_contains_safety"] is True
    assert evidence["payload"]["s7_input_contains_market_count"] is True


def test_s7_blocks_when_s4_pass_has_no_valuation_candidate_universe(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_s4_pass_evidence(environ)

    _write_json(data_dir / "2026-06-25_s3_deep_stats.json", {"analyses": [{"home_team": "Gamma", "away_team": "Delta"}]})
    _write_json(data_dir / "odds_api_snapshot.json", {"events": [{"home_team": "Alpha", "away_team": "Beta", "bookmakers": []}]})

    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S7_S4_VALUATION_INPUT_MISSING"]
    assert evidence["payload"]["s7_input_path"] is None
    assert evidence["payload"]["s7_input_source_step"] == "UNKNOWN"
    assert evidence["payload"]["s7_input_source_kind"] == "missing_expected_s4"


def test_s7_allows_s3_fallback_only_without_s4_pass(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    s3_path = _write_json(data_dir / "2026-06-25_s3_deep_stats.json", {"analyses": [{"home_team": "Gamma", "away_team": "Delta"}]})

    resolution = s5_gate.resolve_s7_input(
        environ,
        environ["BET_PIPELINE_BETTING_DAY"],
        environ["BET_PIPELINE_RUN_ID"],
    )

    assert Path(resolution["path"]).resolve() == s3_path.resolve()
    assert resolution["source_step"] == "S3"
    assert resolution["source_kind"] == "legacy_s3_fallback"


def test_s7_does_not_silently_fallback_to_s3_after_s4_pass(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_s4_pass_evidence(environ)
    _write_json(data_dir / "2026-06-25_s3_deep_stats.json", {"analyses": [{"home_team": "Gamma", "away_team": "Delta"}]})

    resolution = s5_gate.resolve_s7_input(
        environ,
        environ["BET_PIPELINE_BETTING_DAY"],
        environ["BET_PIPELINE_RUN_ID"],
    )

    assert resolution["path"] is None
    assert resolution["blocked_reason"] == "BLOCKED_S7_S4_VALUATION_INPUT_MISSING"
