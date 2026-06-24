from __future__ import annotations

import json
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SUMMARY_PATH = REPO_ROOT / "certification/football/p2e_sportdb_one_shot_production_qualification_summary.json"
MATRIX_PATH = REPO_ROOT / "config/provider_capability_matrix.json"
ROUTING_PATH = REPO_ROOT / "config/football_routing.yaml"

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


def test_source_summary_classification() -> None:
    """Verifies that the source summary classification is expanded World Cup shadow."""
    assert SOURCE_SUMMARY_PATH.is_file(), f"Source summary not found at {SOURCE_SUMMARY_PATH}"
    data = json.loads(SOURCE_SUMMARY_PATH.read_text(encoding="utf-8"))
    
    assert data.get("classification") == "SPORTDB_ONE_SHOT_READY_FOR_EXPANDED_WORLD_CUP_SHADOW"
    assert data.get("recommended_usage") == "shadow_monitoring"


def test_epl_sportdb_shadow_matrix_and_routing_preserved() -> None:
    """Verifies that the existing EPL SportDB shadow route remains in matrix and routing."""
    # Matrix check
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    sportdb_matrix = matrix.get("providers", {}).get("sportdb", {})
    detailed_metrics_caps = sportdb_matrix.get("capabilities", {}).get("detailed_metrics", [])
    
    epl_caps = [
        cap for cap in detailed_metrics_caps
        if cap.get("competition_scope") == "football:eng.1"
        and cap.get("season_scope") == "current-season-completed"
    ]
    assert len(epl_caps) == 1, "EPL matrix capability is missing or duplicated"
    assert epl_caps[0].get("status") == "CERTIFIED_SHADOW"
    assert epl_caps[0].get("mode") == "shadow"

    # Routing check
    with open(ROUTING_PATH, "r", encoding="utf-8") as f:
        routing = yaml.safe_load(f)
    detailed_metrics_routes = routing.get("routing", {}).get("detailed_metrics", {})
    shadow_routes = detailed_metrics_routes.get("shadow_routes", [])
    
    epl_routes = [
        r for r in shadow_routes
        if r.get("provider") == "sportdb"
        and r.get("competition_scope") == "football:eng.1"
        and r.get("season_scope") == "current-season-completed"
    ]
    assert len(epl_routes) == 1, "EPL routing route is missing or duplicated"
    assert epl_routes[0].get("selectable_status") == "CERTIFIED_SHADOW"
    assert epl_routes[0].get("mode") == "shadow"


def test_world_cup_sportdb_shadow_matrix_and_routing_exist() -> None:
    """Verifies that the new World Cup SportDB shadow route exists in matrix and routing."""
    # Matrix check
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    sportdb_matrix = matrix.get("providers", {}).get("sportdb", {})
    detailed_metrics_caps = sportdb_matrix.get("capabilities", {}).get("detailed_metrics", [])
    
    wc_caps = [
        cap for cap in detailed_metrics_caps
        if cap.get("competition_scope") == "football:world:8/world-championship:lvUBR5F8"
        and str(cap.get("season_scope")) == "2026"
    ]
    assert len(wc_caps) == 1, "World Cup matrix capability is missing or duplicated"
    wc_cap = wc_caps[0]
    assert wc_cap.get("status") == "CERTIFIED_SHADOW"
    assert wc_cap.get("mode") == "shadow"
    assert wc_cap.get("selectable_as_projection") is False
    assert wc_cap.get("evidence_replay") is True
    assert wc_cap.get("evidence_source") == "p2e_sportdb_one_shot_production_qualification_summary.json"

    # Routing check
    with open(ROUTING_PATH, "r", encoding="utf-8") as f:
        routing = yaml.safe_load(f)
    detailed_metrics_routes = routing.get("routing", {}).get("detailed_metrics", {})
    shadow_routes = detailed_metrics_routes.get("shadow_routes", [])
    
    wc_routes = [
        r for r in shadow_routes
        if r.get("provider") == "sportdb"
        and r.get("competition_scope") == "football:world:8/world-championship:lvUBR5F8"
        and str(r.get("season_scope")) == "2026"
    ]
    assert len(wc_routes) == 1, "World Cup routing route is missing or duplicated"
    wc_route = wc_routes[0]
    assert wc_route.get("selectable_status") == "CERTIFIED_SHADOW"
    assert wc_route.get("mode") == "shadow"


def test_sportdb_is_never_production_and_no_unsupported_promotions() -> None:
    """Rejects PRODUCTION_READY, CERTIFIED_SELECTABLE, selectable_as_projection true for SportDB."""
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    sportdb_matrix = matrix.get("providers", {}).get("sportdb", {})
    
    # 1. Rejects PRODUCTION_READY classification
    assert sportdb_matrix.get("classification") != "PRODUCTION_READY"
    assert sportdb_matrix.get("classification") == "SCOPE_LIMITED_SHADOW_REGISTERED"
    
    # 2. Rejects CERTIFIED_SELECTABLE status or selectable_as_projection True in matrix
    capabilities = sportdb_matrix.get("capabilities", {})
    for cap_name, caps in capabilities.items():
        for cap in caps:
            assert cap.get("status") != "CERTIFIED_SELECTABLE", f"Disallowed status in capability {cap_name}"
            assert cap.get("selectable_as_projection") is not True, f"Disallowed selectable_as_projection=true in capability {cap_name}"

    # 3. Routing checks
    with open(ROUTING_PATH, "r", encoding="utf-8") as f:
        routing = yaml.safe_load(f)
    
    routing_data = routing.get("routing", {})
    for family_name, family_routes in routing_data.items():
        # Confirm SportDB not in any production_routes
        production_routes = family_routes.get("production_routes", [])
        for r in production_routes:
            assert r.get("provider") != "sportdb", f"SportDB incorrectly placed in production_routes under {family_name}"

        # Confirm selectable_as_projection is false or absent (never true)
        for bucket in ["production_routes", "shadow_routes", "candidate_routes"]:
            for r in family_routes.get(bucket, []):
                if r.get("provider") == "sportdb":
                    assert r.get("selectable_as_projection") is not True, f"SportDB route has selectable_as_projection=true under {family_name}"


def test_sportdb_world_cup_metrics() -> None:
    """Verifies that the World Cup shadow matrix cap has the exact 10 metrics, and pass counts are excluded."""
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    sportdb_matrix = matrix.get("providers", {}).get("sportdb", {})
    detailed_metrics_caps = sportdb_matrix.get("capabilities", {}).get("detailed_metrics", [])
    
    wc_caps = [
        cap for cap in detailed_metrics_caps
        if cap.get("competition_scope") == "football:world:8/world-championship:lvUBR5F8"
    ]
    assert len(wc_caps) == 1
    wc_cap = wc_caps[0]
    
    assert set(wc_cap.get("certifiable_metric_scope", [])) == EXPECTED_METRICS
    assert set(wc_cap.get("excluded_metric_scope", [])) == EXCLUDED_METRICS


def test_unsupported_route_families_not_added() -> None:
    """Verifies that standings, events, lineups, current_form, and historical_form_h2h were not added for SportDB."""
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    sportdb_matrix = matrix.get("providers", {}).get("sportdb", {})
    capabilities = sportdb_matrix.get("capabilities", {})
    
    disallowed_caps = {"current_form", "historical_form_h2h", "standings", "events", "lineups"}
    for cap in disallowed_caps:
        assert cap not in capabilities, f"Disallowed capability family '{cap}' found in SportDB matrix capabilities"

    with open(ROUTING_PATH, "r", encoding="utf-8") as f:
        routing = yaml.safe_load(f)
    
    routing_data = routing.get("routing", {})
    for family_name, family_routes in routing_data.items():
        if family_name in disallowed_caps:
            for bucket in ["production_routes", "shadow_routes", "candidate_routes"]:
                routes = family_routes.get(bucket, [])
                for r in routes:
                    assert r.get("provider") != "sportdb", f"SportDB found in disallowed route family '{family_name}' in routing file"


def test_accepted_production_providers_not_weakened() -> None:
    """Verifies that accepted production providers (espn, football-data, highlightly) are not reordered or weakened."""
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    providers = matrix.get("providers", {})
    
    for prov in ["espn", "football-data", "highlightly"]:
        assert prov in providers, f"Required provider '{prov}' was removed from matrix"

    # Verify ESPN has its existing capabilities
    espn_detailed_metrics = providers["espn"].get("capabilities", {}).get("detailed_metrics", [])
    assert any(
        cap.get("competition_scope") == "football:eng.1"
        and cap.get("status") == "CERTIFIED_SELECTABLE"
        and cap.get("selectable_as_projection") is True
        for cap in espn_detailed_metrics
    )
