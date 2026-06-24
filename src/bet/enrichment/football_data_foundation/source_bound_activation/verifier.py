import json
from pathlib import Path
from typing import Any

from .contracts import ACTIVATION_CANDIDATE_STATUS, ActivationVerificationResult


FORBIDDEN_TEXT = (
    "PRODUCTION_READY",
    "production_ready",
    "betting decision",
    "recommendation",
    "stake",
    "edge",
    "raw_payload",
    "raw_headers",
    "x-api-key",
    "x-rapidapi-key",
    "cookie",
    "set-cookie",
    "bearer ",
)


def _scan_forbidden(payload: Any) -> list[str]:
    text = json.dumps(payload, sort_keys=True).lower()
    return [token for token in FORBIDDEN_TEXT if token.lower() in text]


def verify_activation_candidate_payload(payload: dict[str, Any]) -> ActivationVerificationResult:
    failures: list[str] = []
    checks: dict[str, str] = {}
    decision = payload.get("decision") or {}
    provider_ids = payload.get("provider_ids") or {}
    provider_fact_counts = payload.get("provider_fact_counts") or {}
    sqlite_summary = payload.get("sqlite_summary") or {}

    if decision.get("status") != ACTIVATION_CANDIDATE_STATUS:
        failures.append("activation_status_not_shadow_only")
    if decision.get("selectable_for_production") is not False:
        failures.append("selectable_for_production_not_false")
    if decision.get("manual_authorization_required") is not True:
        failures.append("manual_authorization_required_not_true")
    if decision.get("production_db_write_allowed") is not False:
        failures.append("production_db_write_allowed_not_false")
    if decision.get("betting_decision_allowed") is not False:
        failures.append("betting_decision_allowed_not_false")
    if decision.get("live_network_allowed") is not False:
        failures.append("live_network_allowed_not_false")

    required_providers = {"api-football", "football-data-org", "espn-baseline", "sportdb", "highlightly"}
    missing_ids = required_providers - set(provider_ids)
    if missing_ids:
        failures.append("missing_provider_ids:" + ",".join(sorted(missing_ids)))
    missing_counts = [provider for provider in required_providers if int(provider_fact_counts.get(provider, 0)) <= 0]
    if missing_counts:
        failures.append("missing_provider_fact_counts:" + ",".join(sorted(missing_counts)))
    sqlite_rows = sqlite_summary.get("provider_fact_rows") or {}
    missing_sqlite_rows = [provider for provider in required_providers if int(sqlite_rows.get(provider, 0)) <= 0]
    if missing_sqlite_rows:
        failures.append("missing_sqlite_provider_rows:" + ",".join(sorted(missing_sqlite_rows)))

    if payload.get("score") != {"home": 3, "away": 2}:
        failures.append("score_mismatch")
    if payload.get("conflicts"):
        failures.append("conflicts_present")
    if payload.get("shadow_status") != "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW":
        failures.append("shadow_status_not_ready")
    if payload.get("source_bound_verifier_verdict") != "PASS":
        failures.append("source_bound_verifier_not_pass")

    forbidden = _scan_forbidden(payload)
    if forbidden:
        failures.append("forbidden_text:" + ",".join(forbidden))

    checks["shadow_status"] = "pass" if payload.get("shadow_status") == "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW" else "fail"
    checks["provider_ids"] = "pass" if not missing_ids else "fail"
    checks["provider_fact_counts"] = "pass" if not missing_counts else "fail"
    checks["sqlite_provider_rows"] = "pass" if not missing_sqlite_rows else "fail"
    checks["score"] = "pass" if payload.get("score") == {"home": 3, "away": 2} else "fail"
    checks["shadow_only_decision"] = "pass" if not failures else "fail"
    return ActivationVerificationResult(
        verdict="PASS" if not failures else "FAIL",
        failed_requirements=failures,
        checks=checks,
    )


def verify_activation_candidate_file(path: Path) -> ActivationVerificationResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return ActivationVerificationResult(verdict="FAIL", failed_requirements=["candidate_not_json_object"])
    return verify_activation_candidate_payload(payload)
