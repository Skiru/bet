"""Tests for S7 valid no-action terminal outcome semantics."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.integration_artifacts import write_script_evidence


def _build_s7_payload(**overrides: object) -> dict[str, object]:
    payload = {
        "step_id": "S7",
        "wrapper_scripts": ["gate_checker.py"],
        "wrapper_rc": 1,
        "runtime_mode": "DRY_RUN",
        "dry_run": True,
        "allow_write": False,
        "allow_live_network": False,
        "production_write": False,
        "runtime_path_source": "orchestrator_inherited_sandbox",
        "child_run_root": "/tmp/test-run-root",
        "child_artifact_dir": "/tmp/test-run-root/artifacts",
        "s7_json_output": "/tmp/test-run-root/data/2026-06-26_s7_gate_results.json",
        "s7_markdown_output": "/tmp/test-run-root/data/2026-06-26_s7_gate_results.md",
        "total_candidates": 63,
        "approved_count": 0,
        "extended_count": 0,
        "rejected_count": 63,
        "s7_input_path": "/tmp/test-run-root/data/2026-06-26_s4_valuation_candidates.json",
        "s7_input_source_step": "S4",
        "s7_input_source_kind": "s4_evidence_payload",
        "s7_input_contains_odds": True,
        "s7_input_contains_ev": True,
        "s7_input_contains_safety": True,
        "s7_input_contains_market_count": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "no_pick_edge_stake_coupon_emitted": True,
    }
    payload.update(overrides)
    return payload


def _run_s7_with_script_evidence(
    tmp_path: Path,
    *,
    evidence_status: str,
    blocked_reasons: tuple[str, ...] = (),
    payload_overrides: dict[str, object] | None = None,
    write_evidence: bool = True,
    stop_after_step: str = "S8",
):
    orch = Orchestrator(
        betting_day="2026-06-26",
        run_id="run-s7-no-action",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "sandbox",
    )
    from bet.pipeline.integration_artifacts import write_script_evidence
    write_script_evidence(
        "S6",
        status="PASS",
        payload={},
        sources=(),
        evidence_refs=(),
        environ=orch.env,
    )

    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(*args, **kwargs):
            if write_evidence:
                write_script_evidence(
                    "S7",
                    status=evidence_status,
                    payload=_build_s7_payload(**(payload_overrides or {})),
                    sources=("scripts/gate_checker.py",),
                    evidence_refs=(),
                    environ=orch.env,
                    no_pick_edge_stake_coupon_emitted=True,
                    production_selectable=False,
                    betting_decisions_enabled=False,
                    blocked_reasons=blocked_reasons,
                )
            result = MagicMock()
            result.returncode = 0 if evidence_status == "PASS" else 1
            return result

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S7", stop_after_step=stop_after_step)

    summary_path = orch.run_root / "run_summary.json"
    summary_on_disk = json.loads(summary_path.read_text(encoding="utf-8"))
    return orch, mock_run, summary, summary_on_disk


def test_s7_hard_gate_all_rejected_classifies_as_valid_no_action_terminal(tmp_path):
    orch, mock_run, summary, summary_on_disk = _run_s7_with_script_evidence(
        tmp_path,
        evidence_status="BLOCK",
        blocked_reasons=("BLOCKED_HARD_APPROVAL_GATE",),
    )

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S7"
    assert summary["terminal_outcome"] == "NO_ACTION"
    assert summary["terminal_outcome_reason"] == "S7_HARD_GATE_NO_APPROVED_CANDIDATES"
    assert summary["valid_no_action_terminal"] is True
    assert summary["no_bet_day"] is True
    assert summary["no_action_step"] == "S7"
    assert summary["no_action_candidate_count"] == 63
    assert summary["no_action_rejected_count"] == 63
    assert summary["ready_for_human_gate_test"] is False
    assert summary["ready_for_production_execution"] is False
    assert summary["next_action"] == "NO_BET_REVIEW_OR_UPSTREAM_DATA_ENRICHMENT"
    assert summary["production_db_write"] is False
    assert summary["production_coupon_write"] is False
    assert summary_on_disk["terminal_outcome"] == "NO_ACTION"
    assert summary_on_disk["valid_no_action_terminal"] is True

    step_ids = [step["step_id"] for step in summary["steps"]]
    assert "S7b" not in step_ids
    assert "S8" not in step_ids
    assert orch.run_coupon_dir.exists()
    assert not any(orch.run_coupon_dir.iterdir())
    assert mock_run.call_count == 1


def test_s7_precondition_failed_block_is_not_no_action(tmp_path):
    _, _, summary, _ = _run_s7_with_script_evidence(
        tmp_path,
        evidence_status="BLOCK",
        blocked_reasons=("PRECONDITION_FAILED",),
    )

    assert summary["status"] == "BLOCK"
    assert summary["terminal_outcome"] is None
    assert summary["valid_no_action_terminal"] is False
    assert summary["no_bet_day"] is False


def test_s7_missing_s4_input_source_is_not_no_action(tmp_path):
    _, _, summary, _ = _run_s7_with_script_evidence(
        tmp_path,
        evidence_status="BLOCK",
        blocked_reasons=("BLOCKED_HARD_APPROVAL_GATE",),
        payload_overrides={"s7_input_source_step": None},
    )

    assert summary["terminal_outcome"] is None
    assert summary["valid_no_action_terminal"] is False


def test_s7_zero_candidates_is_not_no_action(tmp_path):
    _, _, summary, _ = _run_s7_with_script_evidence(
        tmp_path,
        evidence_status="BLOCK",
        blocked_reasons=("BLOCKED_HARD_APPROVAL_GATE",),
        payload_overrides={"total_candidates": 0, "rejected_count": 0},
    )

    assert summary["terminal_outcome"] is None
    assert summary["valid_no_action_terminal"] is False


def test_s7_missing_evidence_path_is_not_no_action(tmp_path):
    _, _, summary, _ = _run_s7_with_script_evidence(
        tmp_path,
        evidence_status="BLOCK",
        blocked_reasons=("BLOCKED_HARD_APPROVAL_GATE",),
        write_evidence=False,
    )

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S7"
    assert summary["terminal_outcome"] is None
    assert summary["valid_no_action_terminal"] is False
    s7_step = next(step for step in summary["steps"] if step["step_id"] == "S7")
    assert s7_step["evidence_path"] is None


def test_s7_pass_is_not_no_action(tmp_path):
    _, _, summary, _ = _run_s7_with_script_evidence(
        tmp_path,
        evidence_status="PASS",
        blocked_reasons=(),
        stop_after_step="S7",
    )

    assert summary["status"] == "PASS"
    assert summary["blocked_at_step"] is None
    assert summary["terminal_outcome"] is None
    assert summary["valid_no_action_terminal"] is False
