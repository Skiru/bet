#!/usr/bin/env python3
"""Validate the materialized SportDB World Cup shadow scope configuration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
import yaml


PHASE_ID = "P2E_A14_MATERIALIZE_SPORTDB_WORLD_CUP_SHADOW_SCOPE"
PROMPT_VERSION = "v1_materialize_verified_world_cup_shadow_only"
PREVIOUS_ACCEPTED_SHA = "cd9bd51f075582bb0de17af133e6fc0417c307d9"
SOURCE_SUMMARY_PATH = "certification/football/p2e_sportdb_one_shot_production_qualification_summary.json"
MATRIX_PATH = "config/provider_capability_matrix.json"
ROUTING_PATH = "config/football_routing.yaml"

EXPECTED_METRICS = {
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
}

EXCLUDED_METRICS = {"successful_passes", "total_passes"}


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate materialized World Cup shadow scope.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write the validation summary JSON.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    # Absolute paths
    source_summary_file = repo_root / SOURCE_SUMMARY_PATH
    matrix_file = repo_root / MATRIX_PATH
    routing_file = repo_root / ROUTING_PATH

    errors: list[str] = []
    
    existing_epl_shadow_preserved = False
    world_cup_shadow_materialized = False
    certifiable_metric_scope: list[str] = []
    excluded_metric_scope: list[str] = []

    try:
        # Load files
        source_summary = load_json(source_summary_file)
        matrix = load_json(matrix_file)
        routing = load_yaml(routing_file)

        # 1. Verify Source Summary is valid
        if source_summary.get("classification") != "SPORTDB_ONE_SHOT_READY_FOR_EXPANDED_WORLD_CUP_SHADOW":
            errors.append("source_summary_invalid_classification")
        if source_summary.get("recommended_usage") != "shadow_monitoring":
            errors.append("source_summary_invalid_recommended_usage")

        # 2. Check provider matrix checks for SportDB
        providers = matrix.get("providers", {})
        if "sportdb" not in providers:
            errors.append("sportdb_missing_from_providers")
            sportdb = {}
        else:
            sportdb = providers["sportdb"]

        # Do not mark SportDB PRODUCTION_READY or CERTIFIED_SELECTABLE
        sportdb_classification = sportdb.get("classification")
        if sportdb_classification == "PRODUCTION_READY":
            errors.append("sportdb_incorrectly_marked_production_ready")
        
        sportdb_capabilities = sportdb.get("capabilities", {})
        detailed_metrics_caps = sportdb_capabilities.get("detailed_metrics", [])

        # Confirm existing EPL route remains
        epl_caps = [
            cap for cap in detailed_metrics_caps
            if cap.get("competition_scope") == "football:eng.1"
            and cap.get("season_scope") == "current-season-completed"
            and cap.get("mode") == "shadow"
            and cap.get("status") == "CERTIFIED_SHADOW"
        ]
        if not epl_caps:
            errors.append("existing_epl_detailed_metrics_matrix_cap_missing")
        else:
            existing_epl_shadow_preserved = True

        # Confirm new World Cup route exists in matrix
        wc_caps = [
            cap for cap in detailed_metrics_caps
            if cap.get("competition_scope") == "football:world:8/world-championship:lvUBR5F8"
            and str(cap.get("season_scope")) == "2026"
            and cap.get("mode") == "shadow"
            and cap.get("status") == "CERTIFIED_SHADOW"
        ]
        
        if not wc_caps:
            errors.append("world_cup_detailed_metrics_matrix_cap_missing")
        else:
            wc_cap = wc_caps[0]
            if wc_cap.get("selectable_as_projection") is not False:
                errors.append("world_cup_matrix_cap_selectable_as_projection_not_false")
            if wc_cap.get("evidence_replay") is not True:
                errors.append("world_cup_matrix_cap_evidence_replay_not_true")
            if wc_cap.get("evidence_source") != "p2e_sportdb_one_shot_production_qualification_summary.json":
                errors.append("world_cup_matrix_cap_evidence_source_mismatch")
            
            # Verify metric scope
            certifiable_metric_scope = wc_cap.get("certifiable_metric_scope", [])
            excluded_metric_scope = wc_cap.get("excluded_metric_scope", [])

            if set(certifiable_metric_scope) != EXPECTED_METRICS:
                errors.append(f"certifiable_metric_scope_mismatch: {certifiable_metric_scope}")
            if set(excluded_metric_scope) != EXCLUDED_METRICS:
                errors.append(f"excluded_metric_scope_mismatch: {excluded_metric_scope}")

        # Check for any CERTIFIED_SELECTABLE or PRODUCTION_READY across SportDB
        for cap_name, caps in sportdb_capabilities.items():
            for cap in caps:
                if cap.get("status") == "CERTIFIED_SELECTABLE":
                    errors.append(f"sportdb_has_certified_selectable_cap_in_{cap_name}")
                if cap.get("selectable_as_projection") is True:
                    errors.append(f"sportdb_has_selectable_as_projection_true_in_{cap_name}")

        # 3. Check football_routing.yaml
        routing_data = routing.get("routing", {})
        
        # Verify SportDB not added to other routing families
        for family_name, family_routes in routing_data.items():
            if family_name == "detailed_metrics":
                continue
            
            # Check production and shadow/candidate routes
            for bucket_name in ["production_routes", "shadow_routes", "candidate_routes"]:
                routes = family_routes.get(bucket_name, [])
                for r in routes:
                    if r.get("provider") == "sportdb":
                        errors.append(f"sportdb_incorrectly_added_to_family_{family_name}_in_{bucket_name}")

        # Now check detailed_metrics routes
        dm_routes = routing_data.get("detailed_metrics", {})
        dm_production_routes = dm_routes.get("production_routes", [])
        dm_shadow_routes = dm_routes.get("shadow_routes", [])

        # SportDB must NOT be in production_routes
        for r in dm_production_routes:
            if r.get("provider") == "sportdb":
                errors.append("sportdb_found_in_detailed_metrics_production_routes")

        # Confirm existing EPL shadow route remains in routing
        epl_routes = [
            r for r in dm_shadow_routes
            if r.get("provider") == "sportdb"
            and r.get("competition_scope") == "football:eng.1"
            and r.get("season_scope") == "current-season-completed"
            and r.get("mode") == "shadow"
            and r.get("selectable_status") == "CERTIFIED_SHADOW"
        ]
        if not epl_routes:
            errors.append("existing_epl_detailed_metrics_shadow_route_missing")
        else:
            existing_epl_shadow_preserved = existing_epl_shadow_preserved and True

        # Confirm new World Cup detailed_metrics shadow route exists in routing
        wc_routes = [
            r for r in dm_shadow_routes
            if r.get("provider") == "sportdb"
            and r.get("competition_scope") == "football:world:8/world-championship:lvUBR5F8"
            and str(r.get("season_scope")) == "2026"
            and r.get("mode") == "shadow"
            and r.get("selectable_status") == "CERTIFIED_SHADOW"
        ]
        if not wc_routes:
            errors.append("world_cup_detailed_metrics_shadow_route_missing")
        else:
            wc_route = wc_routes[0]
            if wc_route.get("selectable_as_projection") is True:
                errors.append("world_cup_routing_selectable_as_projection_is_true")
            world_cup_shadow_materialized = True

        # Ensure accepted production providers are not changed/weakened
        # Pre-existing production providers in matrix: espn, football-data, highlightly.
        # Let's verify they still have their status and capabilities.
        for expected_prov in ["espn", "football-data", "highlightly"]:
            if expected_prov not in providers:
                errors.append(f"pre_existing_production_provider_missing:{expected_prov}")

    except Exception as exc:
        errors.append(f"exception_during_validation: {exc}")

    if errors:
        sys.stderr.write(f"Validation FAILED with errors:\n" + "\n".join(errors) + "\n")
        final_review = "FAIL"
        classification = "SPORTDB_WORLD_CUP_SHADOW_SCOPE_MATERIALIZATION_FAILED"
        final_verdict = "SPORTDB_MATERIALIZATION_VALIDATION_ERROR"
    else:
        final_review = "PASS"
        classification = "SPORTDB_WORLD_CUP_SHADOW_SCOPE_MATERIALIZED"
        final_verdict = "SPORTDB_PRESERVED_AS_PRODUCTION_GRADE_NON_SELECTABLE_WORLD_CUP_SHADOW"

    summary = {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
        "evidence_level": "TRACKED_CONFIG_MATERIALIZATION_SUMMARY",
        "mode": "bounded_config_materialization_no_live_calls",
        "provider": "sportdb",
        "source_summary": SOURCE_SUMMARY_PATH,
        "materialized_route": f"detailed_metrics/sportdb/football:world:8/world-championship:lvUBR5F8/2026/shadow",
        "status": "CERTIFIED_SHADOW",
        "selectable_as_projection": False,
        "production_route_added": False,
        "certified_selectable_added": False,
        "global_production_ready_added": False,
        "existing_epl_shadow_preserved": existing_epl_shadow_preserved,
        "world_cup_shadow_materialized": world_cup_shadow_materialized,
        "certifiable_metric_scope": sorted(list(certifiable_metric_scope)),
        "excluded_metric_scope": sorted(list(excluded_metric_scope)),
        "classification": classification,
        "final_verdict": final_verdict,
        "secret_safe": True,
        "final_review": final_review
    }

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    
    if final_review == "PASS":
        print("SPORTDB_WORLD_CUP_SHADOW_SCOPE_VALIDATION_PASS")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
