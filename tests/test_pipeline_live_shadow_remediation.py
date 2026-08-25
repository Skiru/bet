"""Tests for live shadow certification remediation fixes (FIX 1, FIX 2, FIX 3)."""
from __future__ import annotations

import os
import json
import subprocess
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.runtime_modes import RuntimeMode, LIVE_ACK_KEY, LIVE_ACK_VALUE
from bet.pipeline.integration_artifacts import write_script_evidence, script_evidence_path
from bet.pipeline.run_evidence import sha256_file
from scripts.pipeline_steps import _runner, s4_valuator


@pytest.fixture
def clean_env(monkeypatch):
    """Clean live ack and mode env vars."""
    monkeypatch.delenv(LIVE_ACK_KEY, raising=False)
    monkeypatch.delenv("BET_PIPELINE_RUNTIME_MODE", raising=False)


# ===========================================================================
# FIX 1: DRY_RUN LIVE GUARD SEMANTICS
# ===========================================================================

def test_dry_run_s0_does_not_block_due_live_ack(tmp_path, clean_env, monkeypatch):
    """Verify that DRY_RUN S0 does not block due to missing live network ACK."""
    # We want to run S0 in DRY_RUN. S0 is a live-capable step (wrapper is s0_settler.py, which runs settle_on_finish.py).
    # Since we are mocking subprocess, we expect it to succeed or fail normally but NOT block on live ack.
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-remediation-dry",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
        allow_live_network=False,
    )

    with patch("subprocess.run") as mock_run:
        def side_effect(*args, **kwargs):
            # Write expected script evidence for S0
            write_script_evidence(
                "S0",
                status="PASS",
                payload={"test": True},
                sources=(),
                evidence_refs=(),
                environ=orch.env,
            )
            m = MagicMock()
            m.returncode = 0
            return m
        mock_run.side_effect = side_effect

        summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S0"


def test_live_shadow_s1_without_ack_still_blocks(tmp_path, clean_env):
    """Verify that LIVE_SHADOW S1 without live network ACK blocks before execution."""
    from bet.pipeline.integration_artifacts import write_script_evidence
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-remediation-live-s1-no-ack",
        runtime_mode="LIVE_SHADOW",
        base_run_dir=tmp_path / "reports",
        allow_live_network=False,
    )
    write_script_evidence(
        "S0",
        status="PASS",
        payload={"test": True},
        sources=(),
        evidence_refs=(),
        environ=orch.env,
    )
    summary = orch.run(start_step="S1", stop_after_step="S1")
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S1"
    assert any("live network acknowledgment missing" in b for b in summary["blockers"])


def test_live_shadow_s4_without_ack_still_blocks(tmp_path, clean_env):
    """Verify that LIVE_SHADOW S4 without live network ACK blocks before execution."""
    from bet.pipeline.integration_artifacts import write_script_evidence
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-remediation-live-s4-no-ack",
        runtime_mode="LIVE_SHADOW",
        base_run_dir=tmp_path / "reports",
        allow_live_network=False,
    )
    write_script_evidence(
        "S3",
        status="PASS",
        payload={"test": True},
        sources=(),
        evidence_refs=(),
        environ=orch.env,
    )
    summary = orch.run(start_step="S4", stop_after_step="S4")
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S4"
    assert any("live network acknowledgment missing" in b for b in summary["blockers"])


def test_certification_live_target_blocks(tmp_path, clean_env, monkeypatch):
    """Verify that CERTIFICATION runtime mode blocks live targets before execution."""
    fixture_root = Path(__file__).parent / "fixtures" / "pipeline_wrappers"
    live_script = fixture_root / "scripts" / "settle_on_finish.py"
    live_script.parent.mkdir(parents=True, exist_ok=True)
    live_script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    try:
        monkeypatch.setattr(_runner, "ROOT", fixture_root)
        # Even with live ACK present, CERTIFICATION mode must block live target scripts
        monkeypatch.setenv(LIVE_ACK_KEY, LIVE_ACK_VALUE)

        rc = _runner.run_scripts(["settle_on_finish.py"], dry_run=True, allow_live_network=True, runtime_mode="CERTIFICATION")
        assert rc == 5
    finally:
        if live_script.exists():
            live_script.unlink()


# ===========================================================================
# FIX 2: S1 MISSING MARKET MATRIX EVIDENCE
# ===========================================================================

def test_missing_market_matrix_returns_controlled_block(tmp_path, clean_env, monkeypatch):
    """Verify that missing market matrix causes build_shortlist.py to fail closed with S1 BLOCK evidence."""
    # Ensure sandboxed path doesn't have the matrix file
    data_dir = tmp_path / "betting" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    environ = {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-999",
        "BET_PIPELINE_RUN_ROOT": str(tmp_path),
        "BET_PIPELINE_DATA_DIR": str(data_dir),
        "BET_PIPELINE_COUPON_DIR": str(tmp_path / "betting" / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(tmp_path / "artifacts"),
    }

    from scripts import build_shortlist

    monkeypatch.setattr(build_shortlist, "DATA_DIR", data_dir)

    # We mock sys.exit to raise SystemExit so execution terminates immediately on error
    with patch.dict(os.environ, environ), patch("argparse.ArgumentParser.parse_args") as mock_args, pytest.raises(SystemExit) as exc_info:
        mock_args.return_value = MagicMock(
            date="2026-06-25",
            top=100,
            stats_first=False,
            min_sports=5,
            betclic_filter=False,
            allow_fixture_only_fallback=False,
            verbose=False,
            stop_on_error=False,
        )

        build_shortlist.main()

    assert exc_info.value.code == 2

    # Check that S1.json script evidence exists and has status BLOCK with BLOCKED_MISSING_MARKET_MATRIX
    ev_path = tmp_path / "pipeline_runs" / "2026-06-25" / "run-999" / "artifacts" / "S1.json"
    assert ev_path.exists()

    ev_data = json.loads(ev_path.read_text(encoding="utf-8"))
    assert ev_data["status"] == "BLOCK"
    assert "BLOCKED_MISSING_MARKET_MATRIX" in ev_data["blocked_reasons"]

    # Ensure no outputs were written to betting/data/ or betting/coupons/ (other than S1.json in artifacts)
    # The data directory shouldn't have any shortlist JSON or coupons
    shortlist_json = data_dir / "shortlist_2026-06-25.json"
    assert not shortlist_json.exists()


# ===========================================================================
# FIX 3: S4 CANONICAL SCRIPT EVIDENCE
# ===========================================================================

def test_s4_wrapper_with_mocked_successful_target_scripts_writes_s4_pass_evidence(tmp_path, clean_env, monkeypatch):
    """Verify that S4 wrapper writes S4 PASS evidence when both target scripts succeed and output exists."""
    run_root = Path("/tmp") / f"bet-s4-pass-{tmp_path.name}"
    data_dir = run_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    s3_path = data_dir / "2026-06-25_s3_deep_stats.json"
    s3_path.write_text(json.dumps({"schema_version": 1, "artifact_type": "S3_DEEP_STATS", "analyses": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta", "best_market": {"name": "Over 2.5", "safety_score": 0.82}, "markets_evaluated": 4}]}), encoding="utf-8")

    environ = {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-999",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(data_dir),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "S3.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S3",
                "status": "PASS",
                "betting_day": "2026-06-25",
                "run_id": "run-999",
                "payload": {
                    "s3_output_path": str(s3_path),
                    "s3_output_sha256": sha256_file(s3_path),
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_run_scripts(scripts, **_kwargs):
        for invocation in scripts:
            if getattr(invocation, "script", invocation) != "odds_evaluator.py":
                continue
            cmd = invocation.argv
            output_path = Path(cmd[cmd.index("--output") + 1])
            output_path.write_text(json.dumps({
                "schema_version": 2,
                "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
                "betting_day": "2026-06-25",
                "run_id": "run-999",
                "created_at_utc": "2026-06-25T00:00:00+00:00",
                "runtime_mode": "DRY_RUN",
                "source_s3_path": cmd[cmd.index("--input") + 1],
                "source_s3_sha256": sha256_file(Path(cmd[cmd.index("--input") + 1])),
                "odds_snapshot_paths": [],
                "candidate_count": 1,
                "contains_odds": True,
                "contains_ev": True,
                "contains_safety": True,
                "contains_market_count": True,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": True,
                "candidates": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta", "best_market": {"name": "Over 2.5", "safety_score": 0.82}, "market_count": 4, "markets_evaluated": 4, "odds": {"market_best": 1.91}, "ev": 0.11, "safety_score": 0.82, "safety_markets": [], "valuation_warnings": [], "valuation_status": "VALUED"}],
            }), encoding="utf-8")
        return 0

    with patch("argparse.ArgumentParser.parse_args") as mock_args, \
          pytest.raises(SystemExit) as exc_info, \
         patch.dict(os.environ, environ), \
         patch.object(s4_valuator, "run_scripts", side_effect=fake_run_scripts):

        mock_args.return_value = MagicMock(
            date="2026-06-25",
            run_id="run-999",
            runtime_mode="DRY_RUN",
            allow_live_network=False,
            allow_write=False,
            dry_run=True,
        )

        s4_valuator.main()

    assert exc_info.value.code == 0

    ev_path = run_root / "pipeline_runs" / "2026-06-25" / "run-999" / "artifacts" / "S4.json"
    assert ev_path.exists()
    ev_data = json.loads(ev_path.read_text(encoding="utf-8"))
    assert ev_data["status"] == "PASS"


def test_s4_wrapper_with_missing_odds_snapshot_writes_s4_block_evidence(tmp_path, clean_env, monkeypatch):
    """Verify that S4 wrapper writes S4 BLOCK evidence when evaluator produces no valuation output."""
    run_root = Path("/tmp") / f"bet-s4-missing-{tmp_path.name}"
    data_dir = run_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    s3_path = data_dir / "2026-06-25_s3_deep_stats.json"
    s3_path.write_text(json.dumps({"schema_version": 1, "artifact_type": "S3_DEEP_STATS", "analyses": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta"}]}), encoding="utf-8")

    environ = {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-999",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(data_dir),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "S3.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S3",
                "status": "PASS",
                "betting_day": "2026-06-25",
                "run_id": "run-999",
                "payload": {
                    "s3_output_path": str(s3_path),
                    "s3_output_sha256": sha256_file(s3_path),
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_run_scripts(_scripts, **_kwargs):
        return 0

    with patch("argparse.ArgumentParser.parse_args") as mock_args, \
          pytest.raises(SystemExit) as exc_info, \
         patch.dict(os.environ, environ), \
         patch.object(s4_valuator, "run_scripts", side_effect=fake_run_scripts):

        mock_args.return_value = MagicMock(
            date="2026-06-25",
            run_id="run-999",
            runtime_mode="DRY_RUN",
            allow_live_network=False,
            allow_write=False,
            dry_run=True,
        )

        s4_valuator.main()

    assert exc_info.value.code == 1

    ev_path = run_root / "pipeline_runs" / "2026-06-25" / "run-999" / "artifacts" / "S4.json"
    assert ev_path.exists()
    ev_data = json.loads(ev_path.read_text(encoding="utf-8"))
    assert ev_data["status"] == "BLOCK"
    assert "BLOCKED_S4_VALUATION_OUTPUT_MISSING" in ev_data["blocked_reasons"]


def test_s4_wrapper_with_target_failure_writes_s4_failed_evidence(tmp_path, clean_env, monkeypatch):
    """Verify that S4 wrapper writes S4 FAILED evidence when a subprocess fails unexpectedly."""
    run_root = Path("/tmp") / f"bet-s4-fail-{tmp_path.name}"
    data_dir = run_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    s3_path = data_dir / "2026-06-25_s3_deep_stats.json"
    s3_path.write_text(json.dumps({"schema_version": 1, "artifact_type": "S3_DEEP_STATS", "analyses": [{"fixture_id": 10, "home_team": "Alpha", "away_team": "Beta"}]}), encoding="utf-8")

    environ = {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-999",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(data_dir),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "S3.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S3",
                "status": "PASS",
                "betting_day": "2026-06-25",
                "run_id": "run-999",
                "payload": {
                    "s3_output_path": str(s3_path),
                    "s3_output_sha256": sha256_file(s3_path),
                },
            }
        ),
        encoding="utf-8",
    )

    with patch("scripts.pipeline_steps.s4_valuator.run_scripts") as mock_run_scripts, \
         patch("argparse.ArgumentParser.parse_args") as mock_args, \
         pytest.raises(SystemExit) as exc_info, \
         patch.dict(os.environ, environ):

        mock_args.return_value = MagicMock(
            date="2026-06-25",
            run_id="run-999",
            runtime_mode="DRY_RUN",
            allow_live_network=False,
            allow_write=False,
            dry_run=True,
        )

        # Subprocess fails unexpectedly with 99
        mock_run_scripts.return_value = 99

        s4_valuator.main()

    assert exc_info.value.code == 99

    ev_path = run_root / "pipeline_runs" / "2026-06-25" / "run-999" / "artifacts" / "S4.json"
    assert ev_path.exists()
    ev_data = json.loads(ev_path.read_text(encoding="utf-8"))
    assert ev_data["status"] == "FAILED"
    assert "FAILED_UNEXPECTED_SUBPROCESS_ERROR" in ev_data["blocked_reasons"]
    assert ev_data["status"] == "FAILED"
    assert "FAILED_UNEXPECTED_SUBPROCESS_ERROR" in ev_data["blocked_reasons"]


def test_orchestrator_s4_with_ack_no_longer_blocks_when_wrapper_writes_evidence(tmp_path, clean_env):
    """Verify that orchestrator running S4 step with live network ACK passes cleanly and records evidence path."""
    with patch.dict(os.environ, {"BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS"}):
        orch = Orchestrator(
            betting_day="2026-06-25",
            run_id="run-remediation-live-s4-ack",
            runtime_mode="LIVE_SHADOW",
            base_run_dir=tmp_path / "reports",
            allow_live_network=True,
        )

        # Pre-populate dummy S3.json PASS evidence so S4 gate checks pass
        write_script_evidence(
            "S2.9",
            status="PASS",
            payload={},
            sources=(),
            evidence_refs=(),
            environ=orch.env,
        )
        # Create a dummy S3.json since it's required as well
        write_script_evidence(
            "S3",
            status="PASS",
            payload={},
            sources=(),
            evidence_refs=(),
            environ=orch.env,
        )

        # Mock execution of the wrapper to write successful S4 evidence
        with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
            def side_effect(*args, **kwargs):
                write_script_evidence(
                    "S4",
                    status="PASS",
                    payload={"test": True},
                    sources=(),
                    evidence_refs=(),
                    environ=orch.env,
                )
                m = MagicMock()
                m.returncode = 0
                return m
            mock_run.side_effect = side_effect

            summary = orch.run(start_step="S4", stop_after_step="S4")

        assert summary["status"] == "PASS"
        s4_step = next(s for s in summary["steps"] if s["step_id"] == "S4")
        assert s4_step["status"] == "PASS"
        assert s4_step["evidence_path"] is not None
        assert "S4.json" in s4_step["evidence_path"]
        assert summary["last_completed_step"] == "S4"
