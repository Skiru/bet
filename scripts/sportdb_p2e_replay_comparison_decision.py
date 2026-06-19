#!/usr/bin/env python3
"""Record the P2E_A5 SportDB replay-comparison decision from local evidence only."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PHASE_ID = "P2E_A5_SPORTDB_REPLAY_COMPARISON_AGAINST_ACCEPTED_PROVIDERS"
PROMPT_VERSION = "v2_masterpiece_decision_summary_with_repo_hygiene_lifecycle"
PREVIOUS_ACCEPTED_SHA = "c5d0bd0ea7208e1042075060d3479ea2304648cb"
MAIN_CLASSIFICATION = "SPORTDB_SHADOW_ONLY_NOT_REPLAY_EQUIVALENT_TO_ACCEPTED_PROVIDERS"
NEXT_STEP = "P2E_A6_SPORTDB_EVIDENCE_BUNDLE_AND_REPLAY_CONTRACT"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_sportdb_shadow_adapter_summary(data: dict[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    call_budget = data.get("call_budget") if isinstance(data.get("call_budget"), dict) else {}
    certification = data.get("certification") if isinstance(data.get("certification"), dict) else {}

    def expect(condition: bool, message: str) -> None:
        if not condition:
            blockers.append(message)

    expect(
        data.get("classification") == "SPORTDB_SHADOW_ADAPTER_READY_FOR_REPLAY_COMPARISON",
        "shadow_summary_classification_mismatch",
    )
    expect(call_budget.get("mcp_tool_calls_made") == 5, "shadow_summary_mcp_tool_calls_made_invalid")
    expect(call_budget.get("mcp_session_calls_made") in {0, 1}, "shadow_summary_mcp_session_calls_made_invalid")
    expect(call_budget.get("mcp_session_calls_made") != 5, "shadow_summary_mcp_session_calls_made_equals_tool_count")
    expect(call_budget.get("rest_calls_made") == 0, "shadow_summary_rest_calls_made_invalid")
    expect(bool(((data.get("stats_probe") or {}).get("available"))) is True, "shadow_summary_stats_unavailable")
    expect(bool(((data.get("events_probe") or {}).get("available"))) is True, "shadow_summary_events_unavailable")
    expect(bool(((data.get("lineups_probe") or {}).get("available"))) is True, "shadow_summary_lineups_unavailable")
    expect(bool(((data.get("standings_probe") or {}).get("available"))) is True, "shadow_summary_standings_unavailable")
    expect(certification.get("certified_routes") == [], "shadow_summary_certified_routes_not_empty")
    expect(certification.get("production_routing_changed") is False, "shadow_summary_production_routing_changed")
    expect(certification.get("selectable_status_changed") is False, "shadow_summary_selectable_status_changed")
    expect(
        certification.get("verdict") == "NOT_CERTIFIED_SHADOW_ADAPTER_ONLY",
        "shadow_summary_verdict_mismatch",
    )
    return not blockers, blockers


def _contains_sportdb_bundle_writer(service_text: str) -> bool:
    tokens = (
        'registered_source_key="sportdb"',
        "registered_source_key='sportdb'",
        'provider="sportdb"',
        "provider='sportdb'",
    )
    if any(token in service_text for token in tokens):
        return True
    return bool(re.search(r"sportdb.{0,200}write_source_operation_bundle", service_text, re.DOTALL | re.IGNORECASE))


def detect_sportdb_replay_contract(root: Path) -> dict[str, Any]:
    service_text = load_text(root / "src/bet/enrichment/football_service.py")
    source_result_text = load_text(root / "src/bet/integration/source_result.py")
    evidence_text = load_text(root / "src/bet/integration/evidence.py")

    candidate_not_implemented = all(
        token in service_text
        for token in (
            '"sportdb": CandidateRecord(',
            'implementation_state="NOT_IMPLEMENTED"',
            "replay_capabilities=()",
        )
    )
    source_operation_result_available = "class SourceOperationResult" in source_result_text
    bundle_writer_available = "def write_source_operation_bundle" in evidence_text
    sportdb_writer_detected = _contains_sportdb_bundle_writer(service_text)
    source_operation_result_artifacts_detected = sportdb_writer_detected and not candidate_not_implemented

    blocking_gaps: list[str] = []
    if candidate_not_implemented:
        blocking_gaps.append("sportdb_candidate_record_not_implemented_in_football_service")
    if source_operation_result_available and not source_operation_result_artifacts_detected:
        blocking_gaps.append("sportdb_source_operation_result_artifacts_missing")
    if bundle_writer_available and not sportdb_writer_detected:
        blocking_gaps.append("sportdb_evidence_bundle_writer_missing")

    return {
        "sportdb_replay_contract_status": "missing" if blocking_gaps else "present",
        "source_operation_result_artifacts_detected": source_operation_result_artifacts_detected,
        "evidence_bundle_writer_detected_for_sportdb": sportdb_writer_detected,
        "blocking_gaps": blocking_gaps,
    }


def validate_accepted_provider_baseline(root: Path) -> tuple[bool, list[str], dict[str, Any]]:
    blockers: list[str] = []
    highlightly_summary_path = root / "certification/football/p2d_highlightly_certification_summary.json"
    probe_report_path = root / "reports/football_p2d_all_candidates_probe_report.json"
    highlightly_source_path = root / "src/bet/api_clients/highlightly.py"
    api_football_source_path = root / "src/bet/api_clients/api_football.py"

    highlightly_summary = load_json(highlightly_summary_path)
    probe_report = load_json(probe_report_path)
    highlightly_source = load_text(highlightly_source_path)
    api_football_source = load_text(api_football_source_path)

    accepted_highlightly_verdicts = {
        "PRODUCTION_READY_MULTI_SOURCE_SCOPE_LIMITED",
        "CERTIFIED_SELECTABLE",
    }
    highlightly_remains_accepted = (
        highlightly_summary.get("provider") == "highlightly"
        and highlightly_summary.get("verdict") in accepted_highlightly_verdicts
        and bool(highlightly_summary.get("certified_routes"))
        and "class HighlightlyClient" in highlightly_source
    )
    if not highlightly_remains_accepted:
        blockers.append("highlightly_certified_baseline_missing")

    api_provider = ((probe_report.get("providers") or {}).get("api-football") or {})
    api_football_remains_historical_fallback = (
        highlightly_summary.get("api_football_strategy") == "historical_fallback_only"
        and api_provider.get("status") == "PROBE_SUCCESS_HISTORICAL"
        and api_provider.get("replay_readiness")
        == "existing_repository_client_with_evidence_capture_and_offline_replay"
        and "class APIFootballClient" in api_football_source
        and "write_source_operation_bundle" in api_football_source
    )
    if not api_football_remains_historical_fallback:
        blockers.append("api_football_historical_fallback_baseline_missing")

    details = {
        "highlightly_remains_accepted": highlightly_remains_accepted,
        "api_football_remains_historical_fallback": api_football_remains_historical_fallback,
        "accepted_provider_evidence_files": [
            "certification/football/p2d_highlightly_certification_summary.json",
            "reports/football_p2d_all_candidates_probe_report.json",
            "src/bet/api_clients/highlightly.py",
            "src/bet/api_clients/api_football.py",
        ],
    }
    return not blockers, blockers, details


def detect_sportdb_routing_or_matrix_promotion(root: Path) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    matrix = load_json(root / "config/provider_capability_matrix.json")
    routing_text = load_text(root / "config/football_routing.yaml")

    provider_entry = ((matrix.get("providers") or {}).get("sportdb") or {})
    capabilities = provider_entry.get("capabilities") if isinstance(provider_entry.get("capabilities"), dict) else {}
    for capability_name, entries in capabilities.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("selectable_as_projection") is True:
                blockers.append(f"sportdb_matrix_selectable_detected:{capability_name}")
            if str(entry.get("status") or "") in {"CERTIFIED_SELECTABLE", "CERTIFIED_SHADOW", "PRODUCTION_ALLOWED"}:
                blockers.append(f"sportdb_matrix_promoted_status_detected:{capability_name}")

    bucket = ""
    for raw_line in routing_text.splitlines():
        stripped = raw_line.strip()
        if stripped.endswith(":"):
            bucket = stripped[:-1]
        if stripped in {"production_routes:", "candidate_routes:", "shadow_routes:", "routes:", "precedence:"}:
            bucket = stripped[:-1]
            continue
        if stripped.startswith("- provider:") or stripped.startswith("provider:"):
            provider = stripped.split(":", 1)[1].strip()
            if provider != "sportdb":
                continue
            if bucket in {"production_routes", "routes", "precedence"}:
                blockers.append(f"sportdb_routing_bucket_detected:{bucket}")

    seen: set[str] = set()
    deduped = []
    for blocker in blockers:
        if blocker in seen:
            continue
        seen.add(blocker)
        deduped.append(blocker)
    return bool(deduped), deduped


def build_decision_summary(
    *,
    root: Path,
    shadow_data: dict[str, Any],
    shadow_valid: bool,
    shadow_blockers: list[str],
    replay_assessment: dict[str, Any],
    baseline_valid: bool,
    baseline_blockers: list[str],
    baseline_details: dict[str, Any],
    promotion_detected: bool,
    promotion_blockers: list[str],
) -> dict[str, Any]:
    call_budget = shadow_data.get("call_budget") if isinstance(shadow_data.get("call_budget"), dict) else {}
    shadow_summary = {
        "summary_path": "certification/football/p2e_sportdb_shadow_adapter_summary.json",
        "valid": shadow_valid,
        "classification": shadow_data.get("classification"),
        "mcp_tool_calls_made": call_budget.get("mcp_tool_calls_made"),
        "mcp_session_calls_made": call_budget.get("mcp_session_calls_made"),
        "rest_calls_made": call_budget.get("rest_calls_made"),
        "stats_available": bool(((shadow_data.get("stats_probe") or {}).get("available"))),
        "events_available": bool(((shadow_data.get("events_probe") or {}).get("available"))),
        "lineups_available": bool(((shadow_data.get("lineups_probe") or {}).get("available"))),
        "standings_available": bool(((shadow_data.get("standings_probe") or {}).get("available"))),
    }

    summary: dict[str, Any] = {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
        "evidence_level": "TRACKED_REPLAY_COMPARISON_DECISION_SUMMARY",
        "provider": "sportdb",
        "mode": "decision_summary_only_no_live_provider_calls",
        "sportdb_shadow_adapter": shadow_summary,
        "replay_contract_assessment": replay_assessment,
        "accepted_provider_baseline": baseline_details,
        "decision": {
            "promotion_allowed": False,
            "certification_rerun_allowed": False,
            "reason": "UNKNOWN",
        },
        "classification": "UNKNOWN",
        "certification": {
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
            "verdict": "NOT_CERTIFIED_REPLAY_COMPARISON_DECISION_ONLY",
        },
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "next_step": "UNKNOWN",
        "blockers": [],
        "secret_safe": True,
        "final_review": "FAIL",
    }

    if shadow_blockers:
        summary["blockers"].extend(shadow_blockers)
    if promotion_blockers:
        summary["blockers"].extend(promotion_blockers)
    if baseline_blockers:
        summary["blockers"].extend(baseline_blockers)

    summary["classification"] = classify_decision(summary)

    if summary["classification"] == MAIN_CLASSIFICATION:
        summary["decision"] = {
            "promotion_allowed": False,
            "certification_rerun_allowed": False,
            "reason": "SportDB shadow evidence is live, but SportDB does not yet emit replayable evidence bundles or SourceOperationResult-backed certification artifacts.",
        }
        summary["next_step"] = NEXT_STEP
        summary["final_review"] = "PASS"
        summary["blockers"] = []
    elif summary["classification"] == "SPORTDB_REPLAY_DECISION_BLOCKED_SPORTDB_SHADOW_SUMMARY_INVALID":
        summary["decision"]["reason"] = "SportDB shadow adapter summary failed required local validation checks."
        summary["next_step"] = "blocked_or_retry_after_review"
    elif summary["classification"] == "SPORTDB_REPLAY_DECISION_BLOCKED_ROUTING_OR_MATRIX_PROMOTION_DETECTED":
        summary["decision"]["reason"] = "SportDB routing or provider matrix promotion was detected in committed local configuration."
        summary["next_step"] = "blocked_or_retry_after_review"
    elif summary["classification"] == "SPORTDB_REPLAY_DECISION_BLOCKED_ACCEPTED_PROVIDER_BASELINE_MISSING":
        summary["decision"]["reason"] = "Accepted provider baseline evidence for Highlightly or API-Football is missing or invalid."
        summary["next_step"] = "blocked_or_retry_after_review"
    else:
        summary["decision"]["reason"] = "Local decision builder could not classify the committed evidence set safely."
        summary["next_step"] = "blocked_or_retry_after_review"

    return summary


def classify_decision(summary: dict[str, Any]) -> str:
    shadow = summary.get("sportdb_shadow_adapter") or {}
    replay = summary.get("replay_contract_assessment") or {}
    baseline = summary.get("accepted_provider_baseline") or {}
    blockers = summary.get("blockers") or []

    if shadow.get("valid") is not True:
        return "SPORTDB_REPLAY_DECISION_BLOCKED_SPORTDB_SHADOW_SUMMARY_INVALID"
    if any("sportdb_matrix_" in blocker or "sportdb_routing_" in blocker for blocker in blockers):
        return "SPORTDB_REPLAY_DECISION_BLOCKED_ROUTING_OR_MATRIX_PROMOTION_DETECTED"
    if not baseline.get("highlightly_remains_accepted") or not baseline.get("api_football_remains_historical_fallback"):
        return "SPORTDB_REPLAY_DECISION_BLOCKED_ACCEPTED_PROVIDER_BASELINE_MISSING"
    if (
        shadow.get("classification") == "SPORTDB_SHADOW_ADAPTER_READY_FOR_REPLAY_COMPARISON"
        and shadow.get("stats_available") is True
        and shadow.get("events_available") is True
        and shadow.get("lineups_available") is True
        and shadow.get("standings_available") is True
        and replay.get("sportdb_replay_contract_status") == "missing"
        and replay.get("source_operation_result_artifacts_detected") is False
        and replay.get("evidence_bundle_writer_detected_for_sportdb") is False
        and bool(replay.get("blocking_gaps"))
    ):
        return MAIN_CLASSIFICATION
    return "SPORTDB_REPLAY_DECISION_BLOCKED_SCRIPT_OR_PARSER_DEFECT"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the SportDB replay-comparison decision summary from local files.")
    parser.add_argument(
        "--out",
        default="certification/football/p2e_sportdb_replay_comparison_summary.json",
        help="Output summary file path",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        shadow_data = load_json(root / "certification/football/p2e_sportdb_shadow_adapter_summary.json")
        shadow_valid, shadow_blockers = validate_sportdb_shadow_adapter_summary(shadow_data)
        replay_assessment = detect_sportdb_replay_contract(root)
        promotion_detected, promotion_blockers = detect_sportdb_routing_or_matrix_promotion(root)
        baseline_valid, baseline_blockers, baseline_details = validate_accepted_provider_baseline(root)
        summary = build_decision_summary(
            root=root,
            shadow_data=shadow_data,
            shadow_valid=shadow_valid,
            shadow_blockers=shadow_blockers,
            replay_assessment=replay_assessment,
            baseline_valid=baseline_valid,
            baseline_blockers=baseline_blockers,
            baseline_details=baseline_details,
            promotion_detected=promotion_detected,
            promotion_blockers=promotion_blockers,
        )
        if promotion_detected and summary["classification"] != "SPORTDB_REPLAY_DECISION_BLOCKED_ROUTING_OR_MATRIX_PROMOTION_DETECTED":
            summary["classification"] = "SPORTDB_REPLAY_DECISION_BLOCKED_ROUTING_OR_MATRIX_PROMOTION_DETECTED"
            summary["decision"]["reason"] = "SportDB routing or provider matrix promotion was detected in committed local configuration."
            summary["next_step"] = "blocked_or_retry_after_review"
            summary["final_review"] = "FAIL"
    except Exception as exc:
        summary = {
            "phase_id": PHASE_ID,
            "prompt_version": PROMPT_VERSION,
            "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
            "evidence_level": "TRACKED_REPLAY_COMPARISON_DECISION_SUMMARY",
            "provider": "sportdb",
            "mode": "decision_summary_only_no_live_provider_calls",
            "sportdb_shadow_adapter": {
                "summary_path": "certification/football/p2e_sportdb_shadow_adapter_summary.json",
                "valid": False,
                "classification": None,
                "mcp_tool_calls_made": None,
                "mcp_session_calls_made": None,
                "rest_calls_made": None,
                "stats_available": False,
                "events_available": False,
                "lineups_available": False,
                "standings_available": False,
            },
            "replay_contract_assessment": {
                "sportdb_replay_contract_status": "unknown",
                "source_operation_result_artifacts_detected": False,
                "evidence_bundle_writer_detected_for_sportdb": False,
                "blocking_gaps": [],
            },
            "accepted_provider_baseline": {
                "highlightly_remains_accepted": False,
                "api_football_remains_historical_fallback": False,
                "accepted_provider_evidence_files": [],
            },
            "decision": {
                "promotion_allowed": False,
                "certification_rerun_allowed": False,
                "reason": "Local decision builder could not classify the committed evidence set safely.",
            },
            "classification": "SPORTDB_REPLAY_DECISION_BLOCKED_SCRIPT_OR_PARSER_DEFECT",
            "certification": {
                "certified_routes": [],
                "production_routing_changed": False,
                "selectable_status_changed": False,
                "verdict": "NOT_CERTIFIED_REPLAY_COMPARISON_DECISION_ONLY",
            },
            "impact_on_p2d": "none_highlightly_remains_accepted",
            "next_step": "blocked_or_retry_after_review",
            "blockers": [f"script_or_parser_defect:{type(exc).__name__}:{exc}"],
            "secret_safe": True,
            "final_review": "FAIL",
        }

    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
