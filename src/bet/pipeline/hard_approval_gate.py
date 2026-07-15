"""Pure, source-bound S7 approval service.

S7 consumes only the exact S6 artifact.  It never reconstructs candidates from
S2/S3, never invents IDs, and never interprets process exit codes as domain
outcomes.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from bet.pipeline.canonical_continuity import (
    ContinuityContractError,
    file_sha256,
    validate_exact_partition,
)
from bet.pipeline.live_fixture_audit import LiveFixtureAudit


CONTEXT_CHECKS = (
    "injuries_lineups",
    "motivation_tournament_context",
    "travel_fatigue",
    "morale_recent_form",
    "upset_volatility_risk",
)
FORBIDDEN_EXECUTION_FIELDS = {
    "internal_pick",
    "recommended_pick",
    "stake",
    "staking",
    "stake_decimal",
    "coupon",
    "parlay",
    "accumulator",
    "betting_decision",
    "executable_coupon",
    "can_place_bet_now",
}
S6_TERMINAL_CATEGORIES = (
    "accepted",
    "repeat_rejected",
    "duplicate_rejected",
    "conflict_rejected",
    "correlation_rejected",
    "concentration_rejected",
    "invalid_input",
)


def strip_execution_fields(value: Any) -> Any:
    """Remove execution instructions while preserving analytical selection facts."""
    if isinstance(value, dict):
        return {
            key: strip_execution_fields(item)
            for key, item in value.items()
            if str(key).strip().casefold() not in FORBIDDEN_EXECUTION_FIELDS
        }
    if isinstance(value, list):
        return [strip_execution_fields(item) for item in value]
    return value


def _candidate_from_terminal(record: Mapping[str, Any]) -> dict[str, Any]:
    candidate = record.get("original_candidate")
    if not isinstance(candidate, dict):
        raise ContinuityContractError("S6_TERMINAL_ORIGINAL_CANDIDATE_MISSING")
    record_id = record.get("candidate_id")
    if record_id != candidate.get("selection_id") or record_id != candidate.get("candidate_id"):
        raise ContinuityContractError("S6_TERMINAL_IDENTITY_MISMATCH")
    return candidate


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_s6_output(
    s6: Mapping[str, Any],
    *,
    day: str,
    run_id: str,
) -> list[dict[str, Any]]:
    """Validate the complete immutable S6 worker boundary."""
    if (
        s6.get("schema_version") != 2
        or s6.get("artifact_type") != "S6_PORTFOLIO_REPEAT_GUARD_V2"
        or s6.get("betting_day") != day
        or s6.get("run_id") != run_id
        or s6.get("status") != "PASS"
        or s6.get("concrete_status") not in {"READY_FOR_S7", "NO_ACTION_TERMINAL"}
    ):
        raise ContinuityContractError("S7_SOURCE_S6_CONTRACT_INVALID")
    if s6.get("source_step") != "S5" or s6.get("worker_contract_version") != "1.0":
        raise ContinuityContractError("S6_WORKER_PROVENANCE_INVALID")
    source_s5_path = s6.get("source_s5_path")
    source_s5_sha = s6.get("source_s5_sha256")
    if not isinstance(source_s5_path, str) or not _sha256(source_s5_sha):
        raise ContinuityContractError("S6_SOURCE_S5_BINDING_INVALID")
    try:
        if file_sha256(Path(source_s5_path).resolve(strict=True)) != source_s5_sha:
            raise ContinuityContractError("S6_SOURCE_S5_HASH_MISMATCH")
    except OSError as exc:
        raise ContinuityContractError("S6_SOURCE_S5_MISSING") from exc
    validated = s6.get("validated_inputs")
    if not isinstance(validated, Mapping):
        raise ContinuityContractError("S6_VALIDATED_INPUTS_MISSING")
    if validated.get("s5_hash") != source_s5_sha or not all(
        _sha256(validated.get(name)) for name in ("history_hash", "policy_hash")
    ):
        raise ContinuityContractError("S6_VALIDATED_INPUT_HASHES_INVALID")
    run_as_of = s6.get("run_as_of_utc")
    try:
        parsed_as_of = datetime.fromisoformat(str(run_as_of).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuityContractError("S6_RUN_CLOCK_INVALID") from exc
    if parsed_as_of.tzinfo is None:
        raise ContinuityContractError("S6_RUN_CLOCK_INVALID")
    terminal = {
        name: s6.get(name, [])
        for name in S6_TERMINAL_CATEGORIES
    }
    if any(not isinstance(records, list) for records in terminal.values()):
        raise ContinuityContractError("S6_TERMINAL_CATEGORY_INVALID")
    all_candidates = [
        _candidate_from_terminal(record)
        for records in terminal.values()
        for record in records
    ]
    validate_exact_partition(all_candidates, terminal)
    if s6.get("input_candidate_count") != len(all_candidates):
        raise ContinuityContractError("S6_INPUT_COUNT_MISMATCH")
    accepted = [_candidate_from_terminal(record) for record in terminal["accepted"]]
    if s6.get("concrete_status") == "NO_ACTION_TERMINAL" and accepted:
        raise ContinuityContractError("S6_NO_ACTION_WITH_ACCEPTED_CANDIDATES")
    if s6.get("concrete_status") == "READY_FOR_S7" and not accepted:
        raise ContinuityContractError("S6_READY_WITHOUT_ACCEPTED_CANDIDATES")
    return accepted


def _context_failures(candidate: Mapping[str, Any]) -> tuple[list[str], list[Any], list[Any]]:
    reasons: list[str] = []
    context = candidate.get("context_checks")
    if not isinstance(context, dict):
        return ["S5_CONTEXT_CHECKS_MISSING"], [], []
    for name in CONTEXT_CHECKS:
        check = context.get(name)
        if not isinstance(check, dict):
            reasons.append(f"S5_CONTEXT_{name.upper()}_MISSING")
            continue
        status = str(check.get("status") or "").upper()
        if status not in {"CLEAR", "RISK_ACCEPTABLE", "BLOCK"}:
            reasons.append(f"S5_CONTEXT_{name.upper()}_UNKNOWN")
        elif status == "BLOCK":
            reasons.append(f"S5_CONTEXT_{name.upper()}_BLOCK")
        if not check.get("as_of_utc") or not check.get("source_refs"):
            reasons.append(f"S5_CONTEXT_{name.upper()}_UNBOUND")
    risk_flags = candidate.get("risk_flags")
    counter_evidence = candidate.get("counter_evidence")
    if not isinstance(risk_flags, list):
        reasons.append("S5_RISK_FLAGS_MISSING")
        risk_flags = []
    if not isinstance(counter_evidence, list):
        reasons.append("S5_COUNTER_EVIDENCE_MISSING")
        counter_evidence = []
    for flag in risk_flags:
        if isinstance(flag, dict) and str(flag.get("severity") or "").upper() in {"BLOCK", "CRITICAL"}:
            reasons.append(f"S5_BLOCKING_RISK:{flag.get('code') or 'UNSPECIFIED'}")
    return reasons, list(risk_flags), list(counter_evidence)


def evaluate_s7_hard_gate(
    s6: Mapping[str, Any],
    *,
    source_s6_path: Path | str,
    betting_day: str,
    run_id: str,
) -> dict[str, Any]:
    """Return the complete S7 V2 artifact or raise a contract error."""
    source_path = Path(source_s6_path).resolve(strict=True)
    hash_before = file_sha256(source_path)
    on_disk = json.loads(source_path.read_text(encoding="utf-8"))
    if on_disk != s6 or hash_before != file_sha256(source_path):
        raise ContinuityContractError("S6_HASH_CHANGED_DURING_READ")
    accepted = validate_s6_output(s6, day=betting_day, run_id=run_id)
    priced_approved: list[dict[str, Any]] = []
    analytical_approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    gate_results: dict[str, dict[str, Any]] = {}
    auditor = LiveFixtureAudit(betting_day)

    for candidate in accepted:
        candidate_id = str(candidate["selection_id"])
        reasons, risk_flags, counter_evidence = _context_failures(candidate)
        fixture_status, fixture_reason = auditor.audit_candidate(dict(candidate))
        if fixture_status != "LIVE_FIXTURE_VERIFIED_NOT_STARTED":
            reasons.append(f"{fixture_status}:{fixture_reason}")
        analytical_status = str(candidate.get("analytical_status") or "").upper()
        if analytical_status not in {"ANALYTICAL_READY", "REVIEW_ONLY_PARTIAL_DATA"}:
            reasons.append("ANALYTICAL_STATUS_NOT_READY")

        clean = strip_execution_fields(dict(candidate))
        clean["risk_flags"] = risk_flags
        clean["counter_evidence"] = counter_evidence
        if reasons:
            rejected.append(
                {
                    "candidate_id": candidate_id,
                    "selection_id": candidate_id,
                    "decision": "REJECTED",
                    "reason_codes": reasons,
                    "original_candidate": clean,
                }
            )
        elif candidate.get("odds_decimal") is not None or candidate.get("best_odds") is not None:
            priced_approved.append(clean)
        else:
            analytical_approved.append(clean)
        gate_results[candidate_id] = {
            "decision": "REJECTED" if reasons else "APPROVED_FOR_MANUAL_QUOTE_REVIEW",
            "reason_codes": reasons,
            "fixture_verification_status": fixture_status,
            "risk_flags": risk_flags,
            "counter_evidence": counter_evidence,
        }

    accounting = validate_exact_partition(
        accepted,
        {
            "priced_approved": priced_approved,
            "analytical_approved": analytical_approved,
            "rejected": rejected,
        },
    )
    approved_count = len(priced_approved) + len(analytical_approved)
    if not accepted or approved_count == 0:
        outcome = "NO_ACTION_TERMINAL"
    elif priced_approved:
        outcome = "READY_FOR_PRICED_REVIEW"
    else:
        outcome = "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"
    return {
        "schema_version": 2,
        "artifact_type": "S7_ANALYTICAL_APPROVAL_SET_V2",
        "status": "PASS",
        "outcome": outcome,
        "betting_day": betting_day,
        "run_id": run_id,
        "source_step": "S6",
        "source_s6_path": str(source_path),
        "source_s6_sha256": file_sha256(source_path),
        "input_candidate_count": len(accepted),
        "priced_approved": priced_approved,
        "analytical_approved": analytical_approved,
        "review_only": [],
        "rejected": rejected,
        "gate_results": gate_results,
        "accounting": accounting,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "no_pick_edge_stake_coupon_emitted": True,
    }
