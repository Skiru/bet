#!/usr/bin/env python3
"""Validate and summarize the SportDB scope-limited shadow registration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PHASE_ID = "P2E_A11_SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION"
PROMPT_VERSION = "v1_masterpiece_minimal_shadow_registration_copy_safe"
PREVIOUS_ACCEPTED_SHA = "a54bbf1fee0942821dc4ebe03f3ac3a65fd79543"
PROTECTED_WORKTREE = "/Users/mkoziol/projects/bet-multisport-enrichment-v1"
DEFAULT_SUMMARY_PATH = Path(
    "certification/football/p2e_sportdb_scope_limited_shadow_registration_summary.json"
)
EXPECTED_ROUTE = "detailed_metrics/sportdb/football:eng.1/current-season-completed/shadow"
EXPECTED_CERTIFIABLE_METRICS = [
    "blocked_shots",
    "corners",
    "expected_goals",
    "fouls",
    "goalkeeper_saves",
    "offsides",
    "possession",
    "shots_off_target",
    "shots_on_goal",
    "yellow_cards",
]
EXPECTED_EXCLUDED_METRICS = ["successful_passes", "total_passes"]
EXPECTED_ACCEPTED_PROVIDER_MATRIX = {
    "api-football": {
        "classification": "MIXED",
        "provenance_family": "api-football",
        "transport_type": "official_api",
        "capabilities": {
            "current_discovery": [
                {
                    "status": "PLAN_RESTRICTED_CURRENT",
                    "competition_scope": "football:*",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": False,
                    "evidence_replay": True,
                    "exact_reason": "APIFootballAdapter current discovery returns PLAN_RESTRICTED in the truthful live proof, so the current tuple remains observable but not production-selectable.",
                }
            ],
            "detailed_metrics": [
                {
                    "status": "HISTORICAL_ONLY",
                    "competition_scope": "football:*",
                    "season_scope": "historical",
                    "mode": "shadow",
                    "selectable_as_projection": False,
                    "evidence_replay": True,
                    "exact_reason": "Historical API-Football fixture-stat evidence replay exists, but current-season production projection is not certified in this corrective scope.",
                }
            ],
        },
        "risks": [
            "current fixture discovery is plan-restricted on the observed free-plan path",
            "current-season standings and recent-form projections are not certified selectable in this correction",
        ],
    },
    "espn": {
        "classification": "SINGLE_SOURCE_SCOPE_LIMITED",
        "provenance_family": "espn-football",
        "transport_type": "unofficial_api",
        "capabilities": {
            "current_discovery": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "ESPNDiscoveryAdapter is hardcoded to league=eng.1 and retained live+replay proof exists for that exact scope.",
                }
            ],
            "current_form": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "The truthful football vertical has retained replay coverage for ESPN recent-form enrichment on the hardcoded eng.1 scope.",
                }
            ],
            "detailed_metrics": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "Fixture statistics are replay-backed through the truthful football vertical for the ESPN eng.1 scope.",
                }
            ],
            "historical_form_h2h": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "Head-to-head enrichment is implemented and replay-backed only for the ESPN eng.1 scope.",
                }
            ],
            "standings": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "Standings enrichment is only qualified on the ESPN eng.1 route and must not be widened beyond that exact scope.",
                }
            ],
        },
        "risks": [
            "single-source risk remains across the proven football eng.1 scope",
            "adapter is hardcoded to eng.1 and must not be treated as football:*",
        ],
    },
    "football-data": {
        "classification": "CERTIFICATION_CANDIDATE",
        "provenance_family": "football-data-org",
        "transport_type": "official_api",
        "capabilities": {
            "current_discovery": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "Discovery adapter and evidence-capturing fixture client are certified selectable for Premier League (eng.1) scope. Retained live+replay proof exists with evidence bundle id 9ab0469ce90eba19e9c9dec4c74e25333493a6b5ccc26672d966267f194fc618 and replay proof id 50177dc029bd5c7729f8c7da6f785d919fec96f19464a1f68cdb111c4ef3b9e5.",
                }
            ],
            "standings": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "Standings adapter is certified selectable for Premier League (eng.1) scope. Retained live+replay proof exists with evidence bundle id 8ce145b68667362bce214cd27fb0d8110416687f9e85208fabed009b5a8538ad and replay proof id 50177dc029bd5c7729f8c7da6f785d919fec96f19464a1f68cdb111c4ef3b9e5.",
                }
            ],
        },
        "risks": [
            "no per-match detailed statistics endpoint in current client",
            "recent-form helper is not yet normalized for truthful production routing",
            "retained replay certification remains outstanding",
        ],
    },
    "highlightly": {
        "classification": "CERTIFICATION_CANDIDATE",
        "provenance_family": "highlightly",
        "transport_type": "unofficial_api",
        "capabilities": {
            "current_discovery": [
                {
                    "status": "NOT_IMPLEMENTED",
                    "competition_scope": "football:*",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": False,
                    "evidence_replay": False,
                    "exact_reason": "No Highlightly implementation exists in the repository; defer to a later bounded provider-specific change.",
                }
            ],
            "current_form": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current-season-completed",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "Highlightly completed-season current_form is replay-backed for football:eng.1 only. Evidence bundle ids 1a8de5e28225fd5507ff6e548af406412dd598c404840f694d0026768148e126 and 368b08db99edbd38ee464380109a1b65c08365526a2cd77d7e4566e1a9c95eb5 plus replay proof id cc9ca253e5a210160b8aa719ffa7bdcde22165a0fd27735c058f14474785d511 certify this exact tuple.",
                },
                {
                    "status": "NOT_TESTED",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": False,
                    "evidence_replay": False,
                    "exact_reason": "Completed-season Highlightly proof does not certify current-live current_form selection.",
                },
            ],
            "detailed_metrics": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current-season-completed",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "Highlightly completed-season detailed_metrics is replay-backed for football:eng.1 only. Evidence bundle id 6f4f9c027675ba0b3b7246b8994e3ce984d6a990f6c152bf6bdcbc106a88c290 plus replay proof id cc9ca253e5a210160b8aa719ffa7bdcde22165a0fd27735c058f14474785d511 certify this exact tuple.",
                },
                {
                    "status": "NOT_TESTED",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": False,
                    "evidence_replay": False,
                    "exact_reason": "Completed-season Highlightly proof does not certify current-live detailed_metrics selection.",
                },
            ],
            "historical_form_h2h": [
                {
                    "status": "CERTIFIED_SELECTABLE",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current-season-completed",
                    "mode": "shadow",
                    "selectable_as_projection": True,
                    "evidence_replay": True,
                    "exact_reason": "Highlightly completed-season historical_form_h2h is replay-backed for football:eng.1 only. Evidence bundle id cc4c2646f19379233f3aa6d28c29e614de9c495c129fe4993aa0c6f54f5f2526 plus replay proof id cc9ca253e5a210160b8aa719ffa7bdcde22165a0fd27735c058f14474785d511 certify this exact tuple.",
                },
                {
                    "status": "NOT_TESTED",
                    "competition_scope": "football:eng.1",
                    "season_scope": "current",
                    "mode": "shadow",
                    "selectable_as_projection": False,
                    "evidence_replay": False,
                    "exact_reason": "Completed-season Highlightly proof does not certify current-live historical_form_h2h selection.",
                },
            ],
        },
        "risks": [
            "current-live certification is still absent across all Highlightly football routes",
            "detailed metrics intentionally preserve Red cards as missing until a payload proves it",
        ],
    },
}
EXPECTED_ACCEPTED_ROUTING = {
    "current_discovery": {
        "production_routes": [
            {
                "provider": "espn",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
            {
                "provider": "football-data",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
        ],
        "candidate_routes": [
            {
                "provider": "api-football",
                "competition_scope": "football:*",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "PLAN_RESTRICTED_CURRENT",
            }
        ],
    },
    "current_form": {
        "production_routes": [
            {
                "provider": "espn",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
            {
                "provider": "highlightly",
                "competition_scope": "football:eng.1",
                "season_scope": "current-season-completed",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
        ]
    },
    "historical_form_h2h": {
        "production_routes": [
            {
                "provider": "espn",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
            {
                "provider": "highlightly",
                "competition_scope": "football:eng.1",
                "season_scope": "current-season-completed",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
        ]
    },
    "standings": {
        "production_routes": [
            {
                "provider": "espn",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
            {
                "provider": "football-data",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
        ],
        "candidate_routes": [],
    },
    "detailed_metrics": {
        "production_routes": [
            {
                "provider": "espn",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
            {
                "provider": "highlightly",
                "competition_scope": "football:eng.1",
                "season_scope": "current-season-completed",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            },
        ]
    },
    "advanced_xg": {
        "shadow_routes": [
            {
                "provider": "understat",
                "competition_scope": "football:Premier League|La Liga|Bundesliga|Serie A|Ligue 1|RFPL",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SHADOW",
            }
        ]
    },
}


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "[]":
        return []
    return value


def parse_routing_text(text: str) -> dict[str, dict[str, list[dict[str, Any]]]]:
    routing: dict[str, dict[str, list[dict[str, Any]]]] = {}
    current_family = ""
    current_bucket = ""
    current_entry: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if stripped == "routing:":
            continue
        if indent == 2 and stripped.endswith(":"):
            current_family = stripped[:-1]
            routing.setdefault(current_family, {})
            current_bucket = ""
            current_entry = None
            continue
        if indent == 4 and stripped.endswith(":"):
            current_bucket = stripped[:-1]
            routing.setdefault(current_family, {})[current_bucket] = []
            current_entry = None
            continue
        if indent == 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            current_bucket = key.strip()
            parsed_value = parse_scalar(value)
            routing.setdefault(current_family, {})[current_bucket] = parsed_value if isinstance(parsed_value, list) else []
            current_entry = None
            continue
        if indent == 6 and stripped == "[]":
            routing.setdefault(current_family, {})[current_bucket] = []
            current_entry = None
            continue
        if indent == 6 and stripped.startswith("- "):
            key, value = stripped[2:].split(":", 1)
            current_entry = {key.strip(): parse_scalar(value)}
            routing.setdefault(current_family, {}).setdefault(current_bucket, []).append(current_entry)
            continue
        if indent >= 8 and current_entry is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current_entry[key.strip()] = parse_scalar(value)

    return routing


def validate_a10_plan(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    plan = data.get("certification_plan") if isinstance(data.get("certification_plan"), dict) else {}
    certification = data.get("certification") if isinstance(data.get("certification"), dict) else {}
    if data.get("classification") != "SPORTDB_SEMANTIC_GAP_REVIEW_READY_FOR_SCOPE_LIMITED_SHADOW_REGISTRATION":
        errors.append("a10_classification_mismatch")
    if plan.get("plan_allowed") is not True:
        errors.append("a10_plan_not_allowed")
    if plan.get("planned_routes") != [EXPECTED_ROUTE]:
        errors.append("a10_planned_route_mismatch")
    if sorted(plan.get("certifiable_metric_scope") or []) != EXPECTED_CERTIFIABLE_METRICS:
        errors.append("a10_certifiable_metric_scope_mismatch")
    if sorted(plan.get("excluded_metric_scope") or []) != EXPECTED_EXCLUDED_METRICS:
        errors.append("a10_excluded_metric_scope_mismatch")
    if certification.get("certified_routes") != []:
        errors.append("a10_certified_routes_not_empty")
    if certification.get("production_routing_changed") is not False:
        errors.append("a10_production_routing_changed")
    if certification.get("selectable_status_changed") is not False:
        errors.append("a10_selectable_status_changed")
    return errors


def detect_forbidden_status_values(text_or_json: Any) -> list[str]:
    text = text_or_json if isinstance(text_or_json, str) else json.dumps(text_or_json, sort_keys=True)
    issues: list[str] = []
    if "PRODUCTION_READY" in text:
        issues.append("PRODUCTION_READY_detected")
    if "CERTIFIED_SELECTABLE" in text:
        issues.append("CERTIFIED_SELECTABLE_detected")
    if '"selectable_as_projection": true' in text:
        issues.append("selectable_as_projection_true_detected")
    return issues


def validate_sportdb_matrix_entry(matrix: dict[str, Any], a10: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    providers = matrix.get("providers") if isinstance(matrix.get("providers"), dict) else {}
    sportdb = providers.get("sportdb") if isinstance(providers.get("sportdb"), dict) else {}
    capabilities = sportdb.get("capabilities") if isinstance(sportdb.get("capabilities"), dict) else {}
    plan = a10.get("certification_plan") if isinstance(a10.get("certification_plan"), dict) else {}

    if sportdb.get("classification") != "SCOPE_LIMITED_SHADOW_REGISTERED":
        errors.append("sportdb_matrix_classification_mismatch")
    if sportdb.get("provenance_family") != "sportdb.dev":
        errors.append("sportdb_matrix_provenance_family_mismatch")
    if sportdb.get("transport_type") != "metadata_api":
        errors.append("sportdb_matrix_transport_type_mismatch")
    if set(capabilities) != {"detailed_metrics"}:
        errors.append("sportdb_matrix_capability_family_mismatch")

    entries = capabilities.get("detailed_metrics") if isinstance(capabilities.get("detailed_metrics"), list) else []
    if len(entries) != 1:
        errors.append("sportdb_matrix_detailed_metrics_entry_count_mismatch")
        return errors
    entry = entries[0]
    if not isinstance(entry, dict):
        errors.append("sportdb_matrix_detailed_metrics_entry_invalid")
        return errors

    if entry.get("status") != "CERTIFIED_SHADOW":
        errors.append("sportdb_matrix_status_mismatch")
    if entry.get("competition_scope") != "football:eng.1":
        errors.append("sportdb_matrix_competition_scope_mismatch")
    if entry.get("season_scope") != "current-season-completed":
        errors.append("sportdb_matrix_season_scope_mismatch")
    if entry.get("mode") != "shadow":
        errors.append("sportdb_matrix_mode_mismatch")
    if entry.get("selectable_as_projection") is not False:
        errors.append("sportdb_matrix_selectable_as_projection_invalid")
    if entry.get("evidence_replay") is not True:
        errors.append("sportdb_matrix_evidence_replay_invalid")

    exact_reason = str(entry.get("exact_reason") or "")
    for phrase, code in [
        ("A10 semantic-gap review accepted reduced scope", "sportdb_matrix_reason_missing_a10_scope"),
        (
            "A9 value replay had 10 canonical metrics, 0 hard mismatches, and 2 pass semantic gaps",
            "sportdb_matrix_reason_missing_a9_replay",
        ),
        (
            "certifiable metrics exclude total_passes and successful_passes",
            "sportdb_matrix_reason_missing_pass_exclusion",
        ),
        ("not production-selectable", "sportdb_matrix_reason_missing_non_selectable"),
        ("not a current-live certification", "sportdb_matrix_reason_missing_not_current_live"),
    ]:
        if phrase not in exact_reason:
            errors.append(code)

    if sorted(entry.get("certifiable_metric_scope") or []) != sorted(plan.get("certifiable_metric_scope") or []):
        errors.append("sportdb_matrix_certifiable_metric_scope_mismatch")
    if sorted(entry.get("excluded_metric_scope") or []) != sorted(plan.get("excluded_metric_scope") or []):
        errors.append("sportdb_matrix_excluded_metric_scope_mismatch")
    if not isinstance(entry.get("evidence_basis"), list) or len(entry.get("evidence_basis") or []) < 8:
        errors.append("sportdb_matrix_evidence_basis_missing")
    if entry.get("registration_phase") != PHASE_ID:
        errors.append("sportdb_matrix_registration_phase_mismatch")

    for issue in detect_forbidden_status_values(entry):
        errors.append(f"sportdb_matrix_forbidden_status:{issue}")
    return errors


def validate_sportdb_routing_entry(routing_text: str, a10: dict[str, Any]) -> list[str]:
    _ = a10
    errors: list[str] = []
    routing = parse_routing_text(routing_text)
    sportdb_locations: list[tuple[str, str, dict[str, Any]]] = []
    for family, buckets in routing.items():
        for bucket, entries in buckets.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and entry.get("provider") == "sportdb":
                    sportdb_locations.append((family, bucket, entry))

    if len(sportdb_locations) != 1:
        errors.append("sportdb_routing_entry_count_mismatch")
        return errors

    family, bucket, entry = sportdb_locations[0]
    if family != "detailed_metrics":
        errors.append("sportdb_routing_family_mismatch")
    if bucket not in {"shadow_routes", "candidate_routes"}:
        errors.append("sportdb_routing_bucket_invalid")
    if entry.get("competition_scope") != "football:eng.1":
        errors.append("sportdb_routing_competition_scope_mismatch")
    if entry.get("season_scope") != "current-season-completed":
        errors.append("sportdb_routing_season_scope_mismatch")
    if entry.get("mode") != "shadow":
        errors.append("sportdb_routing_mode_mismatch")
    if entry.get("selectable_status") != "CERTIFIED_SHADOW":
        errors.append("sportdb_routing_selectable_status_mismatch")
    if entry.get("selectable_as_projection") is True:
        errors.append("sportdb_routing_selectable_as_projection_invalid")

    if "production_routes" in routing.get("detailed_metrics", {}):
        production_entries = routing["detailed_metrics"].get("production_routes") or []
        for prod_entry in production_entries:
            if isinstance(prod_entry, dict) and prod_entry.get("provider") == "sportdb":
                errors.append("sportdb_routing_production_route_detected")

    for disallowed in ["current_discovery", "current_form", "historical_form_h2h", "standings", "advanced_xg"]:
        for bucket_name, entries in routing.get(disallowed, {}).items():
            if isinstance(entries, list) and any(
                isinstance(item, dict) and item.get("provider") == "sportdb" for item in entries
            ):
                errors.append(f"sportdb_routing_disallowed_family_detected:{disallowed}:{bucket_name}")

    if entry.get("season_scope") == "current":
        errors.append("sportdb_routing_current_live_scope_detected")
    for issue in detect_forbidden_status_values(entry):
        errors.append(f"sportdb_routing_forbidden_status:{issue}")
    return errors


def detect_forbidden_provider_drift(before_or_expected: dict[str, Any], current: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected_value in before_or_expected.items():
        current_value = current.get(key)
        if isinstance(expected_value, dict) and isinstance(current_value, dict):
            nested = detect_forbidden_provider_drift(expected_value, current_value)
            errors.extend([f"{key}.{item}" for item in nested])
            continue
        if current_value != expected_value:
            errors.append(f"{key}_drift")
    return errors


def build_summary(
    *,
    matrix: dict[str, Any],
    routing_text: str,
    a10: dict[str, Any],
    a10_errors: list[str],
    matrix_errors: list[str],
    routing_errors: list[str],
    matrix_drift: list[str],
    routing_drift: list[str],
    forbidden_status_values: list[str],
) -> dict[str, Any]:
    sportdb_entry = (
        ((matrix.get("providers") or {}).get("sportdb") or {}).get("capabilities") or {}
    ).get("detailed_metrics", [{}])[0]
    plan = a10.get("certification_plan") if isinstance(a10.get("certification_plan"), dict) else {}
    routing = parse_routing_text(routing_text)
    sportdb_routes = [
        entry
        for bucket in routing.get("detailed_metrics", {}).values()
        if isinstance(bucket, list)
        for entry in bucket
        if isinstance(entry, dict) and entry.get("provider") == "sportdb"
    ]
    sportdb_route = sportdb_routes[0] if sportdb_routes else {}
    production_route_added = any(
        isinstance(entry, dict) and entry.get("provider") == "sportdb"
        for entry in routing.get("detailed_metrics", {}).get("production_routes", [])
    )
    certified_selectable_added = any(
        "CERTIFIED_SELECTABLE" in item for item in [*matrix_errors, *routing_errors, *forbidden_status_values]
    ) or any(
        entry.get("status") == "CERTIFIED_SELECTABLE"
        for entry in (((matrix.get("providers") or {}).get("sportdb") or {}).get("capabilities") or {}).get(
            "detailed_metrics", []
        )
        if isinstance(entry, dict)
    )
    current_live_scope_added = any(
        isinstance(entry, dict) and entry.get("provider") == "sportdb" and entry.get("season_scope") == "current"
        for family in routing.values()
        if isinstance(family, dict)
        for bucket in family.values()
        if isinstance(bucket, list)
        for entry in bucket
    ) or any(
        isinstance(entry, dict) and entry.get("season_scope") == "current"
        for entry in (((matrix.get("providers") or {}).get("sportdb") or {}).get("capabilities") or {}).get(
            "detailed_metrics", []
        )
    )
    blockers = [
        *a10_errors,
        *matrix_errors,
        *routing_errors,
        *matrix_drift,
        *routing_drift,
        *forbidden_status_values,
    ]
    summary = {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
        "evidence_level": "TRACKED_SCOPE_LIMITED_SHADOW_REGISTRATION_SUMMARY",
        "protected_worktree": PROTECTED_WORKTREE,
        "mode": "config_registration_only_no_live_calls",
        "provider": "sportdb",
        "registration": {
            "applied": False,
            "status": str(sportdb_entry.get("status") or "UNKNOWN"),
            "matrix_path": "config/provider_capability_matrix.json",
            "routing_path": "config/football_routing.yaml",
            "route": EXPECTED_ROUTE,
            "production_route_added": production_route_added,
            "certified_selectable_added": certified_selectable_added,
            "selectable_as_projection": bool(sportdb_entry.get("selectable_as_projection")),
            "current_live_scope_added": current_live_scope_added,
        },
        "metric_scope": {
            "certifiable_metric_scope": list(plan.get("certifiable_metric_scope") or []),
            "excluded_metric_scope": list(plan.get("excluded_metric_scope") or []),
            "excluded_reason": {
                "successful_passes": "A10 accepted semantic gap exclusion for reduced certification scope.",
                "total_passes": "A10 accepted semantic gap exclusion for reduced certification scope.",
            },
        },
        "evidence_basis": list(sportdb_entry.get("evidence_basis") or plan.get("minimum_evidence_basis") or []),
        "drift_checks": {
            "accepted_provider_drift_detected": bool(matrix_drift) or bool(routing_drift),
            "routing_production_drift_detected": production_route_added,
            "forbidden_status_values_detected": forbidden_status_values,
        },
        "classification": "UNKNOWN",
        "certification": {
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
            "verdict": "NOT_CERTIFIED_SCOPE_LIMITED_SHADOW_REGISTRATION_ONLY",
        },
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "next_step": "UNKNOWN",
        "blockers": blockers,
        "secret_safe": True,
        "final_review": "FAIL",
        "routing_snapshot": sportdb_route,
    }
    summary["classification"] = classify_summary(summary)
    summary["registration"]["applied"] = (
        summary["classification"] == "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_APPLIED"
    )
    summary["next_step"] = (
        "P2E_A12_FINAL_SPORTDB_SHADOW_REGISTRATION_AUDIT"
        if summary["classification"] == "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_APPLIED"
        else "blocked_or_retry_after_review"
    )
    summary["final_review"] = (
        "PASS" if summary["classification"] == "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_APPLIED" else "FAIL"
    )
    summary.pop("routing_snapshot", None)
    return summary


def classify_summary(summary: dict[str, Any]) -> str:
    if summary.get("blockers") is None:
        return "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_SCRIPT_OR_PARSER_DEFECT"
    if any(str(item).startswith("a10_") for item in summary.get("blockers", [])):
        return "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_A10_PLAN_INVALID"
    if summary.get("drift_checks", {}).get("accepted_provider_drift_detected") is True:
        return "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_ACCEPTED_PROVIDER_DRIFT"
    if summary.get("drift_checks", {}).get("routing_production_drift_detected") is True or summary.get(
        "drift_checks", {}
    ).get("forbidden_status_values_detected"):
        return "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_FORBIDDEN_PRODUCTION_PROMOTION"
    if any(
        token in summary.get("blockers", [])
        for token in [
            "sportdb_matrix_competition_scope_mismatch",
            "sportdb_matrix_season_scope_mismatch",
            "sportdb_routing_competition_scope_mismatch",
            "sportdb_routing_season_scope_mismatch",
            "sportdb_routing_family_mismatch",
            "sportdb_routing_disallowed_family_detected:current_discovery:production_routes",
        ]
    ) or summary.get("registration", {}).get("current_live_scope_added") is True:
        return "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_ROUTE_SCOPE_TOO_BROAD"
    if sorted(summary.get("metric_scope", {}).get("excluded_metric_scope") or []) != EXPECTED_EXCLUDED_METRICS:
        return "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_PASS_METRICS_NOT_EXCLUDED"

    registration = summary.get("registration", {})
    if (
        registration.get("status") == "CERTIFIED_SHADOW"
        and registration.get("route") == EXPECTED_ROUTE
        and registration.get("production_route_added") is False
        and registration.get("certified_selectable_added") is False
        and registration.get("selectable_as_projection") is False
        and registration.get("current_live_scope_added") is False
        and summary.get("certification", {}).get("certified_routes") == []
        and summary.get("certification", {}).get("production_routing_changed") is False
        and summary.get("certification", {}).get("selectable_status_changed") is False
        and not summary.get("blockers")
    ):
        return "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_APPLIED"
    return "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_SCRIPT_OR_PARSER_DEFECT"


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SportDB scope-limited shadow registration.")
    parser.add_argument("--out", type=Path, default=DEFAULT_SUMMARY_PATH)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    try:
        a10 = load_json(root / "certification/football/p2e_sportdb_semantic_gap_review_certification_plan_summary.json")
        matrix = load_json(root / "config/provider_capability_matrix.json")
        routing_text = load_text(root / "config/football_routing.yaml")

        a10_errors = validate_a10_plan(a10)
        matrix_errors = validate_sportdb_matrix_entry(matrix, a10)
        routing_errors = validate_sportdb_routing_entry(routing_text, a10)
        matrix_drift = detect_forbidden_provider_drift(
            {"providers": EXPECTED_ACCEPTED_PROVIDER_MATRIX},
            matrix,
        )
        routing_drift = detect_forbidden_provider_drift(EXPECTED_ACCEPTED_ROUTING, parse_routing_text(routing_text))
        sportdb = ((matrix.get("providers") or {}).get("sportdb") or {})
        sportdb_entry = ((sportdb.get("capabilities") or {}).get("detailed_metrics") or [{}])[0]
        routing = parse_routing_text(routing_text)
        sportdb_route = {}
        for entries in routing.get("detailed_metrics", {}).values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and entry.get("provider") == "sportdb":
                    sportdb_route = entry
                    break
        forbidden_status_values = [
            *detect_forbidden_status_values(sportdb_entry),
            *detect_forbidden_status_values(sportdb_route),
        ]
        summary = build_summary(
            matrix=matrix,
            routing_text=routing_text,
            a10=a10,
            a10_errors=a10_errors,
            matrix_errors=matrix_errors,
            routing_errors=routing_errors,
            matrix_drift=matrix_drift,
            routing_drift=routing_drift,
            forbidden_status_values=forbidden_status_values,
        )
    except Exception as exc:
        summary = {
            "phase_id": PHASE_ID,
            "prompt_version": PROMPT_VERSION,
            "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
            "evidence_level": "TRACKED_SCOPE_LIMITED_SHADOW_REGISTRATION_SUMMARY",
            "protected_worktree": PROTECTED_WORKTREE,
            "mode": "config_registration_only_no_live_calls",
            "provider": "sportdb",
            "registration": {
                "applied": False,
                "status": "UNKNOWN",
                "matrix_path": "config/provider_capability_matrix.json",
                "routing_path": "config/football_routing.yaml",
                "route": EXPECTED_ROUTE,
                "production_route_added": False,
                "certified_selectable_added": False,
                "selectable_as_projection": False,
                "current_live_scope_added": False,
            },
            "metric_scope": {
                "certifiable_metric_scope": [],
                "excluded_metric_scope": [],
                "excluded_reason": {},
            },
            "evidence_basis": [],
            "drift_checks": {
                "accepted_provider_drift_detected": False,
                "routing_production_drift_detected": False,
                "forbidden_status_values_detected": [],
            },
            "classification": "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_SCRIPT_OR_PARSER_DEFECT",
            "certification": {
                "certified_routes": [],
                "production_routing_changed": False,
                "selectable_status_changed": False,
                "verdict": "NOT_CERTIFIED_SCOPE_LIMITED_SHADOW_REGISTRATION_ONLY",
            },
            "impact_on_p2d": "none_highlightly_remains_accepted",
            "next_step": "blocked_or_retry_after_review",
            "blockers": [f"script_or_parser_defect:{exc}"],
            "secret_safe": True,
            "final_review": "FAIL",
        }

    out_path = args.out if args.out.is_absolute() else root / args.out
    write_summary(out_path, summary)
    sys.stdout.write(json.dumps(summary, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
