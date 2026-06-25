from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SUMMARY_PATH = REPO_ROOT / "certification/football/p2e_sportdb_one_shot_production_qualification_summary.json"
MATRIX_PATH = REPO_ROOT / "config/provider_capability_matrix.json"
ROUTING_PATH = REPO_ROOT / "config/football_routing.yaml"


def test_source_summary_classification() -> None:
    """Verifies the retained source summary classification remains world-cup shadow ready."""
    assert SOURCE_SUMMARY_PATH.is_file(), f"Source summary not found at {SOURCE_SUMMARY_PATH}"
    data = json.loads(SOURCE_SUMMARY_PATH.read_text(encoding="utf-8"))

    assert data.get("classification") == "SPORTDB_ONE_SHOT_READY_FOR_EXPANDED_WORLD_CUP_SHADOW"
    assert data.get("recommended_usage") == "shadow_monitoring"


def test_current_matrix_keeps_sportdb_not_implemented() -> None:
    """Verifies the current branch leaves SportDB fail-closed and unregistered."""
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    sportdb_matrix = matrix.get("providers", {}).get("sportdb", {})

    assert sportdb_matrix.get("classification") == "NOT_IMPLEMENTED"
    assert sportdb_matrix.get("capabilities", {}).get("detailed_metrics", []) == []
    current_discovery = sportdb_matrix.get("capabilities", {}).get("current_discovery", [])
    assert len(current_discovery) == 1
    assert current_discovery[0].get("status") == "NOT_IMPLEMENTED"
    assert current_discovery[0].get("selectable_as_projection") is False


def test_current_routing_has_no_sportdb_shadow_routes() -> None:
    """Verifies default routing contains no SportDB entries in any route family."""
    with open(ROUTING_PATH, "r", encoding="utf-8") as f:
        routing = yaml.safe_load(f)

    routing_data = routing.get("routing", {})
    sportdb_routes = []
    for family_name, family_routes in routing_data.items():
        for bucket in ["production_routes", "shadow_routes", "candidate_routes"]:
            for route in family_routes.get(bucket, []):
                if route.get("provider") == "sportdb":
                    sportdb_routes.append((family_name, bucket, route))

    assert sportdb_routes == []


def test_world_cup_sportdb_shadow_route_is_absent_in_current_branch() -> None:
    """Verifies no World Cup SportDB registration is exposed in matrix or routing."""
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    detailed_metrics_caps = (
        matrix.get("providers", {}).get("sportdb", {}).get("capabilities", {}).get("detailed_metrics", [])
    )
    assert [
        cap
        for cap in detailed_metrics_caps
        if cap.get("competition_scope") == "football:world:8/world-championship:lvUBR5F8"
    ] == []

    with open(ROUTING_PATH, "r", encoding="utf-8") as f:
        routing = yaml.safe_load(f)
    shadow_routes = routing.get("routing", {}).get("detailed_metrics", {}).get("shadow_routes", [])
    assert [
        route
        for route in shadow_routes
        if route.get("provider") == "sportdb"
        and route.get("competition_scope") == "football:world:8/world-championship:lvUBR5F8"
    ] == []


def test_sportdb_is_never_production_and_no_unsupported_promotions() -> None:
    """Rejects production-ready SportDB promotion in the current config state."""
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    sportdb_matrix = matrix.get("providers", {}).get("sportdb", {})

    assert sportdb_matrix.get("classification") != "PRODUCTION_READY"
    assert sportdb_matrix.get("classification") == "NOT_IMPLEMENTED"

    capabilities = sportdb_matrix.get("capabilities", {})
    for cap_name, caps in capabilities.items():
        for cap in caps:
            assert cap.get("status") != "CERTIFIED_SELECTABLE", f"Disallowed status in capability {cap_name}"
            assert cap.get("selectable_as_projection") is not True, f"Disallowed selectable_as_projection=true in capability {cap_name}"

    with open(ROUTING_PATH, "r", encoding="utf-8") as f:
        routing = yaml.safe_load(f)

    routing_data = routing.get("routing", {})
    for family_name, family_routes in routing_data.items():
        production_routes = family_routes.get("production_routes", [])
        for route in production_routes:
            assert route.get("provider") != "sportdb", f"SportDB incorrectly placed in production_routes under {family_name}"


def test_accepted_production_providers_not_weakened() -> None:
    """Verifies accepted production providers remain present and unchanged."""
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    providers = matrix.get("providers", {})

    for prov in ["espn", "football-data", "highlightly"]:
        assert prov in providers, f"Required provider '{prov}' was removed from matrix"

    espn_detailed_metrics = providers["espn"].get("capabilities", {}).get("detailed_metrics", [])
    assert any(
        cap.get("competition_scope") == "football:eng.1"
        and cap.get("status") == "CERTIFIED_SELECTABLE"
        and cap.get("selectable_as_projection") is True
        for cap in espn_detailed_metrics
    )
