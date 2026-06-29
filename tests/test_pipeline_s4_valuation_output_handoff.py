"""Focused S4 valuation output handoff tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import odds_evaluator
from scripts.pipeline_steps import s4_valuator, s5_gate, s8_build_coupons


def _runtime_environ() -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s4-valuation-{uuid.uuid4().hex}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s4-valuation",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _canonical_evidence_path(environ: dict[str, str], step_id: str) -> Path:
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / f"{step_id}.json"
    )


def _input_payload() -> dict:
    return {
        "analyses": [
            {
                "fixture_id": 10,
                "sport": "football",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Test League",
                "kickoff": "2026-06-25T18:00:00+00:00",
                "best_market": {
                    "name": "Over 2.5",
                    "direction": "OVER",
                    "probability": 0.62,
                    "safety_score": 0.82,
                },
                "markets_evaluated": 4,
                "hit_rate_l10": 0.6,
                "hit_rate_l5": 0.8,
                "warnings": [],
            }
        ]
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_s4_pass_evidence(environ: dict[str, str], valuation_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S4",
        "status": "PASS",
        "payload": {
            "step_id": "S4",
            "s4_valuation_output_path": str(valuation_path),
        },
    }
    for path in (
        Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / "S4.json",
        _canonical_evidence_path(environ, "S4"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_odds_evaluator_explicit_input_output_writes_s4_contract(tmp_path, monkeypatch):
    input_path = _write_json(tmp_path / "input.json", _input_payload())
    output_path = tmp_path / "2026-06-25_s4_valuation_candidates.json"

    def _inject(candidates, _date):
        for candidate in candidates:
            candidate["odds"] = {"market_best": 1.91}
            candidate["odds_source"] = "test"
            candidate["ev"] = 0.11
            candidate["ev_source"] = "test"

    monkeypatch.setattr(odds_evaluator, "_inject_ev_from_odds", _inject)
    ok, msg = odds_evaluator.run_odds_eval(
        "2026-06-25",
        {},
        input_path=input_path,
        output_path=output_path,
        runtime_mode="DRY_RUN",
    )

    assert ok is True
    assert "with EV data" in msg
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "S4_VALUATION_CANDIDATES"
    assert payload["candidate_count"] > 0
    assert payload["contains_odds"] is True
    assert payload["contains_ev"] is True
    assert payload["contains_safety"] is True
    assert payload["contains_market_count"] is True
    assert payload["production_selectable"] is False
    assert payload["betting_decisions_enabled"] is False
    assert payload["no_pick_edge_stake_coupon_emitted"] is True


def test_odds_evaluator_rejects_protected_repo_output_in_non_production(tmp_path):
    input_path = _write_json(tmp_path / "input.json", _input_payload())
    output_path = Path(__file__).resolve().parents[1] / "betting" / "data" / "forbidden_s4.json"

    ok, msg = odds_evaluator.run_odds_eval(
        "2026-06-25",
        {},
        input_path=input_path,
        output_path=output_path,
        runtime_mode="DRY_RUN",
    )

    assert ok is False
    assert "Protected non-production valuation path rejected" in msg


def test_s4_wrapper_passes_explicit_input_output_and_writes_evidence():
    environ = _runtime_environ()
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    input_path = _write_json(data_dir / "2026-06-25_s3_deep_stats.json", _input_payload())
    recorded: dict[str, object] = {}

    def fake_run(cmd, env=None, capture_output=None, text=None):
        recorded.setdefault("cmds", []).append(list(cmd))
        if len(cmd) > 1 and "odds_evaluator.py" in cmd[1]:
            recorded["eval_cmd"] = list(cmd)
            output_path = Path(cmd[cmd.index("--output") + 1])
            output_payload = {
                "schema_version": 1,
                "artifact_type": "S4_VALUATION_CANDIDATES",
                "betting_day": "2026-06-25",
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "created_at_utc": "2026-06-25T00:00:00+00:00",
                "runtime_mode": "DRY_RUN",
                "source_input_path": cmd[cmd.index("--input") + 1],
                "odds_snapshot_paths": [str(data_dir / "odds_api_snapshot.json")],
                "candidate_count": 1,
                "contains_odds": True,
                "contains_ev": True,
                "contains_safety": True,
                "contains_market_count": True,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": True,
                "candidates": [
                    {
                        "fixture_key": "alpha|beta",
                        "fixture_id": 10,
                        "home_team": "Alpha",
                        "away_team": "Beta",
                        "competition": "Test League",
                        "scheduled_time": "2026-06-25T18:00:00+00:00",
                        "source_steps": ["S3", "S4"],
                        "probability": 0.62,
                        "hit_rate_l10": 0.6,
                        "hit_rate_l5": 0.8,
                        "best_market": {"name": "Over 2.5", "safety_score": 0.82},
                        "market_count": 4,
                        "markets_evaluated": 4,
                        "odds": {"market_best": 1.91},
                        "odds_source": "test",
                        "ev": 0.11,
                        "ev_source": "test",
                        "safety_score": 0.82,
                        "safety_markets": [],
                        "valuation_warnings": [],
                        "valuation_status": "VALUED",
                    }
                ],
            }
            output_path.write_text(json.dumps(output_payload), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    _write_json(data_dir / "odds_api_snapshot.json", {"events": []})
    argv = ["s4_valuator.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 0
    eval_cmd = recorded["eval_cmd"]
    assert "--input" in eval_cmd
    assert Path(eval_cmd[eval_cmd.index("--input") + 1]).resolve() == input_path.resolve()
    assert "--output" in eval_cmd
    evidence = json.loads(_canonical_evidence_path(environ, "S4").read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert evidence["payload"]["s4_valuation_output_path"].startswith("/tmp/")
    assert evidence["payload"]["s4_candidate_count"] == 1
    assert evidence["payload"]["s4_contains_odds"] is True
    assert evidence["payload"]["s4_contains_ev"] is True
    assert evidence["payload"]["s4_contains_safety"] is True
    assert evidence["payload"]["s4_contains_market_count"] is True


def test_s4_wrapper_blocks_when_input_missing():
    environ = _runtime_environ()
    argv = ["s4_valuator.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 1
    evidence = json.loads(_canonical_evidence_path(environ, "S4").read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S4_VALUATION_INPUT_MISSING"]


def test_s4_wrapper_blocks_when_evaluator_does_not_write_output():
    environ = _runtime_environ()
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    _write_json(data_dir / "2026-06-25_s3_deep_stats.json", _input_payload())

    def fake_run(cmd, env=None, capture_output=None, text=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    argv = ["s4_valuator.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 1
    evidence = json.loads(_canonical_evidence_path(environ, "S4").read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S4_VALUATION_OUTPUT_MISSING"]


def test_s7_prefers_s4_valuation_output_and_no_missing_block():
    environ = _runtime_environ()
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    valuation_path = _write_json(
        data_dir / "2026-06-25_s4_valuation_candidates.json",
        {
            "artifact_type": "S4_VALUATION_CANDIDATES",
            "candidate_count": 1,
            "contains_odds": True,
            "contains_ev": True,
            "contains_safety": True,
            "contains_market_count": True,
            "candidates": [
                {
                    "fixture_id": 10,
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "best_market": {"name": "Over 2.5", "safety_score": 0.82},
                    "market_count": 4,
                    "odds": {"market_best": 1.91},
                    "ev": 0.11,
                }
            ],
        },
    )
    _write_s4_pass_evidence(environ, valuation_path)

    recorded: dict[str, object] = {}

    def fake_run(cmd, env=None, capture_output=None, text=None):
        recorded["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 0
    assert recorded["cmd"][-2] == "--input"
    assert Path(recorded["cmd"][-1]).resolve() == valuation_path.resolve()
    evidence = json.loads(_canonical_evidence_path(environ, "S7").read_text(encoding="utf-8"))
    assert evidence["payload"]["s7_input_source_step"] == "S4"
    assert Path(evidence["payload"]["s7_input_path"]).resolve() == valuation_path.resolve()
    assert evidence["payload"]["s7_input_contains_odds"] is True
    assert evidence["payload"]["s7_input_contains_ev"] is True
    assert evidence["payload"]["s7_input_contains_safety"] is True
    assert "BLOCKED_S7_S4_VALUATION_INPUT_MISSING" not in evidence.get("blocked_reasons", [])


def test_s8_reads_analytical_handoff_without_s7_approved_picks():
    environ = _runtime_environ()
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    handoff_path = _write_json(
        data_dir / "analytical_candidate_handoff.json",
        {
            "artifact_type": "ANALYTICAL_CANDIDATE_HANDOFF",
            "analytical_ready": [],
            "blocked_probability_missing": [{"candidate_id": "fixture:10", "analytical_status": "INSUFFICIENT_MODEL_PROBABILITY"}],
            "blocked_stats_missing": [],
            "blocked_identity_missing": [],
            "priced_candidates": [],
            "counts": {"analytical_ready": 0, "blocked_probability_missing": 1, "blocked_stats_missing": 0, "blocked_identity_missing": 0, "priced_candidates": 0},
        },
    )

    argv = ["s8_build_coupons.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s8_build_coupons.main()

    assert exc_info.value.code == 0
    output_path = data_dir / "2026-06-25_s8_coupon_drafts.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["package_type"] == "RESEARCH_GAP_PACKAGE"
    assert Path(payload["analytical_candidate_handoff_path"]).resolve() == handoff_path.resolve()
    evidence = json.loads(_canonical_evidence_path(environ, "S8").read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert evidence["payload"]["package_type"] == "RESEARCH_GAP_PACKAGE"


def test_s7_resolution_prefers_s4_output_not_s3_when_run_root_contains_candidate_token():
    environ = _runtime_environ()
    environ["BET_PIPELINE_RUN_ROOT"] = str(Path("/tmp") / "analytical_candidate_bridge_resolution_case")
    environ["BET_PIPELINE_DATA_DIR"] = str(Path(environ["BET_PIPELINE_RUN_ROOT"]) / "data")
    environ["BET_PIPELINE_ARTIFACT_DIR"] = str(Path(environ["BET_PIPELINE_RUN_ROOT"]) / "artifacts")
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    s3_path = _write_json(data_dir / "2026-06-25_s3_deep_stats.json", _input_payload())
    s4_path = _write_json(
        data_dir / "2026-06-25_s4_valuation_candidates.json",
        {
            "artifact_type": "S4_VALUATION_CANDIDATES",
            "source_input_path": str(s3_path),
            "candidates": [
                {
                    "fixture_id": 10,
                    "sport": "football",
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "competition": "Test League",
                    "best_market": {"name": "Over 2.5", "safety_score": 0.82},
                    "markets_evaluated": 4,
                    "odds": {"market_best": 1.91},
                }
            ],
        },
    )
    _write_s4_pass_evidence(environ, s4_path)

    resolution = s5_gate.resolve_s7_input(environ, "2026-06-25", environ["BET_PIPELINE_RUN_ID"])

    assert Path(resolution["path"]).resolve() == s4_path.resolve()
    assert resolution["source_step"] == "S4"
