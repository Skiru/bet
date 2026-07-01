#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path("/Users/mkoziol/projects/bet")
PROMPT_PATH = PROJECT_ROOT / ".kilo" / "prompts" / "bet-orchestrator-v2.md"
PROTOCOL_DOC_PATH = PROJECT_ROOT / "docs" / "pipeline" / "Orchestrated Session Continuation Protocol.md"
SESSION_CONTRACT_PATH = PROJECT_ROOT / "docs" / "pipeline" / "Unified Orchestrated Analyst Session Contract.md"
PROTOCOL_ARTIFACT_MD_PATH = PROJECT_ROOT / ".kilo" / "artifacts" / "orchestrated_session_continuation_protocol.md"
PROTOCOL_ARTIFACT_JSON_PATH = PROJECT_ROOT / ".kilo" / "artifacts" / "orchestrated_session_continuation_protocol.json"
ROOT_CAUSE_PATH = PROJECT_ROOT / ".kilo" / "artifacts" / "orchestrated_session_max_steps_root_cause_review.md"
REPORT_JSON_PATH = PROJECT_ROOT / ".kilo" / "artifacts" / "orchestrated_session_continuation_audit_report.json"
REPORT_MD_PATH = PROJECT_ROOT / ".kilo" / "artifacts" / "orchestrated_session_continuation_audit_report.md"
PIPELINE_RUNS_DIR = PROJECT_ROOT / "reports" / "pipeline_runs"

REQUIRED_STATUSES = [
    "PASS_PHASE_COMPLETE",
    "PASS_CONTINUATION_REQUIRED",
    "PASS_FINAL",
    "BLOCKED_MODEL_ROUTING",
    "BLOCKED_SUBAGENT_NOT_RUN",
    "BLOCKED_MISSING_ARTIFACT",
    "BLOCKED_MAX_STEPS_RISK",
    "BLOCKED_CODE_BUG",
]

REQUIRED_SUBAGENTS = [
    "bet-scanner",
    "bet-scout",
    "bet-enricher",
    "bet-statistician",
    "bet-valuator",
    "bet-challenger",
    "bet-builder",
    "bet-test-engineer",
]

PHASE_REQUIREMENTS = {
    "J1": {
        "subagents": ["bet-scanner", "bet-scout"],
        "artifacts": ["scanner_event_universe.json", "scout_tipster_opinion_layer.json"],
    },
    "J2": {
        "subagents": ["bet-enricher", "bet-statistician"],
        "artifacts": ["enricher_context_layer.json", "statistician_market_analysis.json"],
    },
    "J3": {
        "subagents": ["bet-valuator", "bet-challenger", "bet-builder"],
        "artifacts": ["valuator_reference_odds_layer.json", "challenger_adversarial_review.json", "builder_package.json"],
    },
    "J4": {
        "subagents": ["bet-test-engineer"],
        "artifacts": ["package_quality_review.md", "status_safety_review.md", "omission_ledger.json"],
    },
}

SESSION_STATE_REQUIRED_KEYS = [
    "task_id",
    "run_id",
    "status",
    "current_phase",
    "completed_phases",
    "pending_phases",
    "required_subagents",
    "completed_subagents",
    "artifact_manifest",
    "omission_ledger_path",
    "model_routing_status",
    "next_resume_prompt",
    "next_phase",
    "final_verdict_allowed",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def _latest_proof_run() -> Path | None:
    candidates = sorted(PIPELINE_RUNS_DIR.glob("ORCHESTRATED_SESSION_CONTINUATION_PROTOCOL_J0_*"))
    return candidates[-1] if candidates else None


def run_audit(write_reports: bool = True) -> dict:
    prompt_text = _read_text(PROMPT_PATH)
    protocol_doc_text = _read_text(PROTOCOL_DOC_PATH)
    session_contract_text = _read_text(SESSION_CONTRACT_PATH)
    protocol_artifact_text = _read_text(PROTOCOL_ARTIFACT_MD_PATH)
    root_cause_text = _read_text(ROOT_CAUSE_PATH)
    protocol_json = _load_json(PROTOCOL_ARTIFACT_JSON_PATH)

    combined_contract_text = "\n".join(
        [prompt_text, protocol_doc_text, session_contract_text, protocol_artifact_text, root_cause_text]
    )

    phase_budget_terms = [
        "J1",
        "J2",
        "J3",
        "J4",
        "bet-scanner",
        "bet-scout",
        "bet-enricher",
        "bet-statistician",
        "bet-valuator",
        "bet-challenger",
        "bet-builder",
        "bet-test-engineer",
    ]

    final_pass_terms = REQUIRED_SUBAGENTS + [
        "PASS_FINAL",
        "omission_ledger.json",
        "package_quality_review.md",
        "status_safety_review.md",
    ]

    false_pass_terms = ["pass_final", "review-only", "forbidden"]

    schema = protocol_json.get("session_state_schema", {})
    schema_required = schema.get("required", [])
    schema_properties = schema.get("properties", {})

    latest_run = _latest_proof_run()
    proof = {
        "proof_run_found": latest_run is not None,
        "proof_run_id": latest_run.name if latest_run else None,
        "proof_session_state_valid": False,
    }

    if latest_run is not None:
        session_state = _load_json(latest_run / "session_state.json")
        proof["proof_session_state_valid"] = (
            session_state.get("current_phase") == "J0"
            and session_state.get("completed_phases") == ["J0"]
            and session_state.get("pending_phases") == ["J1", "J2", "J3", "J4"]
            and session_state.get("status") == "PASS_CONTINUATION_REQUIRED"
            and session_state.get("final_verdict_allowed") is False
            and session_state.get("next_phase") == "J1"
            and bool(session_state.get("next_resume_prompt"))
        )

    results = {
        "protocol_files_exist": all(
            path.exists()
            for path in [
                PROTOCOL_DOC_PATH,
                PROTOCOL_ARTIFACT_MD_PATH,
                PROTOCOL_ARTIFACT_JSON_PATH,
                ROOT_CAUSE_PATH,
            ]
        ),
        "orchestrator_prompt_mentions_pass_continuation_required": "PASS_CONTINUATION_REQUIRED" in prompt_text,
        "orchestrator_prompt_mentions_max_steps_guard": "step budget risk" in prompt_text.lower()
        and "pass_continuation_required" in prompt_text.lower(),
        "full_session_pass_requires_all_subagent_artifacts": _contains_all(combined_contract_text, final_pass_terms),
        "resume_prompt_required_when_phases_pending": _contains_all(
            combined_contract_text,
            ["next_resume_prompt", "pending_phases", "PASS_CONTINUATION_REQUIRED"],
        ),
        "false_pass_after_review_only_forbidden": _contains_all(combined_contract_text.lower(), false_pass_terms),
        "phase_budgets_documented": _contains_all(combined_contract_text, phase_budget_terms),
        "session_state_schema_exists": all(key in schema_required and key in schema_properties for key in SESSION_STATE_REQUIRED_KEYS),
        "required_statuses_documented": protocol_json.get("required_statuses") == REQUIRED_STATUSES,
        "proof_run_found": proof["proof_run_found"],
        "proof_session_state_valid": proof["proof_session_state_valid"],
    }
    results["audit_script_verdict"] = "PASS" if all(results.values()) else "FAIL"
    results["proof_run_id"] = proof["proof_run_id"]

    if write_reports:
        REPORT_JSON_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        report_lines = [
            "# Orchestrated Session Continuation Audit Report",
            "",
            f"- protocol_files_exist: `{results['protocol_files_exist']}`",
            f"- orchestrator_prompt_mentions_pass_continuation_required: `{results['orchestrator_prompt_mentions_pass_continuation_required']}`",
            f"- orchestrator_prompt_mentions_max_steps_guard: `{results['orchestrator_prompt_mentions_max_steps_guard']}`",
            f"- full_session_pass_requires_all_subagent_artifacts: `{results['full_session_pass_requires_all_subagent_artifacts']}`",
            f"- resume_prompt_required_when_phases_pending: `{results['resume_prompt_required_when_phases_pending']}`",
            f"- false_pass_after_review_only_forbidden: `{results['false_pass_after_review_only_forbidden']}`",
            f"- phase_budgets_documented: `{results['phase_budgets_documented']}`",
            f"- session_state_schema_exists: `{results['session_state_schema_exists']}`",
            f"- required_statuses_documented: `{results['required_statuses_documented']}`",
            f"- proof_run_found: `{results['proof_run_found']}`",
            f"- proof_session_state_valid: `{results['proof_session_state_valid']}`",
            f"- audit_script_verdict: `{results['audit_script_verdict']}`",
        ]
        REPORT_MD_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return results


if __name__ == "__main__":
    result = run_audit(write_reports=True)
    print(json.dumps(result, indent=2))
