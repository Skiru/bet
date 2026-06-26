"""Focused S7 child-script evidence tests."""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.gate_checker as gate_checker


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s7-script-{tmp_path.name}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s7-script",
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


def _fake_results(approved_count: int) -> dict:
    approved = []
    if approved_count:
        approved = [
            {
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "kickoff": "2026-06-25T18:00:00+00:00",
                "best_market": {"name": "Over 2.5", "direction": "OVER", "safety_score": 0.8},
                "gate_score": "20/20",
                "risk_tier": "LOW",
                "final_confidence": "HIGH",
                "gate_details": {},
            }
        ]
    return {
        "summary": {
            "total_candidates": 1,
            "approved_count": approved_count,
            "extended_count": 0,
            "rejected_count": 1 - approved_count,
        },
        "gate_results": {
            "approved": approved,
            "extended_pool": [],
            "rejected": [] if approved_count else [{"sport": "football", "home_team": "Alpha", "away_team": "Beta", "competition": "Test League", "kickoff": "2026-06-25T18:00:00+00:00", "best_market": {"name": "Over 2.5"}, "gate_score": "0/20", "risk_tier": "HIGH", "final_confidence": "LOW", "gate_details": {}}],
            "sport_diversity": {
                "message": "ok",
                "approved_sports": ["football"] if approved_count else [],
                "sports_count": 1 if approved_count else 0,
                "key_sports_count": 1 if approved_count else 0,
                "passes_diversity": bool(approved_count),
                "missing_sports": [] if approved_count else ["football"],
            },
        },
    }


def test_gate_checker_explicit_input_writes_sandbox_outputs_and_evidence(tmp_path: Path, monkeypatch):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"analyses": [{"home_team": "Alpha", "away_team": "Beta"}]}), encoding="utf-8")

    monkeypatch.setitem(sys.modules, "db_data_loader", types.SimpleNamespace(save_gate_results_to_db=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("DB save should not run in DRY_RUN"))))
    argv = ["gate_checker.py", "--date", "2026-06-25", "--input", str(input_path)]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch.object(gate_checker, "run_gate", return_value=_fake_results(1)):
        with pytest.raises(SystemExit) as exc_info:
            gate_checker.main()

    assert exc_info.value.code == 0
    json_output = data_dir / "2026-06-25_s7_gate_results.json"
    markdown_output = data_dir / "2026-06-25_s7_gate_results.md"
    assert json_output.exists()
    assert markdown_output.exists()

    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert evidence["payload"]["s7_input_path"] == str(input_path)
    assert evidence["payload"]["s7_json_output"] == str(json_output)
    assert evidence["payload"]["s7_markdown_output"] == str(markdown_output)
    assert evidence["payload"]["approved_count"] == 1
    assert evidence["payload"]["total_candidates"] == 1
    assert evidence["no_pick_edge_stake_coupon_emitted"] is True
    assert "production_coupon_write" not in evidence
    assert "stake" not in evidence["payload"]


def test_gate_checker_empty_input_blocks_with_controlled_reason(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    input_path = tmp_path / "empty.json"
    input_path.write_text(json.dumps({"candidates": []}), encoding="utf-8")
    argv = ["gate_checker.py", "--date", "2026-06-25", "--input", str(input_path)]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            gate_checker.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S7_GATE_INPUT_EMPTY"]


def test_gate_checker_rejects_protected_output_path_in_non_production(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    environ["BET_PIPELINE_DATA_DIR"] = str(Path(__file__).resolve().parents[1] / "betting" / "data")
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"analyses": [{"home_team": "Alpha", "away_team": "Beta"}]}), encoding="utf-8")
    argv = ["gate_checker.py", "--date", "2026-06-25", "--input", str(input_path)]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            gate_checker.main()

    assert exc_info.value.code == 5


def test_gate_checker_blocks_when_approved_count_is_zero(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"analyses": [{"home_team": "Alpha", "away_team": "Beta"}]}), encoding="utf-8")
    argv = ["gate_checker.py", "--date", "2026-06-25", "--input", str(input_path)]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch.object(gate_checker, "run_gate", return_value=_fake_results(0)):
        with pytest.raises(SystemExit) as exc_info:
            gate_checker.main()

    assert exc_info.value.code == 1
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_HARD_APPROVAL_GATE"]
