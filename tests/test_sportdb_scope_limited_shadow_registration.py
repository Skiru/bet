from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts/sportdb_p2e_scope_limited_shadow_registration_validate.py"
SPEC = importlib.util.spec_from_file_location(
    "sportdb_p2e_scope_limited_shadow_registration_validate",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _load_a10() -> dict:
    return MODULE.load_json(
        REPO_ROOT / "certification/football/p2e_sportdb_semantic_gap_review_certification_plan_summary.json"
    )


def _load_matrix() -> dict:
    return MODULE.load_json(REPO_ROOT / "config/provider_capability_matrix.json")


def _load_routing_text() -> str:
    return MODULE.load_text(REPO_ROOT / "config/football_routing.yaml")


def test_validates_a10_plan_fixture() -> None:
    assert MODULE.validate_a10_plan(_load_a10()) == []


def test_validates_sportdb_matrix_detailed_metrics_entry() -> None:
    assert MODULE.validate_sportdb_matrix_entry(_load_matrix(), _load_a10()) == []


def test_rejects_sportdb_certified_selectable() -> None:
    matrix = copy.deepcopy(_load_matrix())
    matrix["providers"]["sportdb"]["capabilities"]["detailed_metrics"][0]["status"] = "CERTIFIED_SELECTABLE"
    errors = MODULE.validate_sportdb_matrix_entry(matrix, _load_a10())
    assert "sportdb_matrix_status_mismatch" in errors
    assert any("CERTIFIED_SELECTABLE_detected" in error for error in errors)


def test_rejects_sportdb_selectable_as_projection_true() -> None:
    matrix = copy.deepcopy(_load_matrix())
    matrix["providers"]["sportdb"]["capabilities"]["detailed_metrics"][0]["selectable_as_projection"] = True
    errors = MODULE.validate_sportdb_matrix_entry(matrix, _load_a10())
    assert "sportdb_matrix_selectable_as_projection_invalid" in errors


def test_rejects_production_ready_status_value() -> None:
    entry = copy.deepcopy(_load_matrix()["providers"]["sportdb"]["capabilities"]["detailed_metrics"][0])
    entry["status"] = "PRODUCTION_READY"
    assert "PRODUCTION_READY_detected" in MODULE.detect_forbidden_status_values(entry)


def test_rejects_sportdb_production_routes() -> None:
    routing_text = _load_routing_text().replace("shadow_routes:\n      - provider: sportdb", "production_routes:\n      - provider: sportdb")
    errors = MODULE.validate_sportdb_routing_entry(routing_text, _load_a10())
    assert "sportdb_routing_bucket_invalid" in errors or "sportdb_routing_production_route_detected" in errors


def test_rejects_sportdb_current_live_scope() -> None:
    routing_text = _load_routing_text().replace(
        "      - provider: sportdb\n"
        "        competition_scope: football:eng.1\n"
        "        season_scope: current-season-completed\n"
        "        mode: shadow\n"
        "        selectable_status: CERTIFIED_SHADOW",
        "      - provider: sportdb\n"
        "        competition_scope: football:eng.1\n"
        "        season_scope: current\n"
        "        mode: shadow\n"
        "        selectable_status: CERTIFIED_SHADOW",
    )
    errors = MODULE.validate_sportdb_routing_entry(routing_text, _load_a10())
    assert "sportdb_routing_season_scope_mismatch" in errors
    assert "sportdb_routing_current_live_scope_detected" in errors


def test_rejects_sportdb_registration_in_disallowed_families() -> None:
    matrix = copy.deepcopy(_load_matrix())
    matrix["providers"]["sportdb"]["capabilities"]["current_form"] = [
        copy.deepcopy(matrix["providers"]["sportdb"]["capabilities"]["detailed_metrics"][0])
    ]
    errors = MODULE.validate_sportdb_matrix_entry(matrix, _load_a10())
    assert "sportdb_matrix_capability_family_mismatch" in errors


def test_verifies_pass_metrics_excluded() -> None:
    entry = _load_matrix()["providers"]["sportdb"]["capabilities"]["detailed_metrics"][0]
    assert sorted(entry["excluded_metric_scope"]) == MODULE.EXPECTED_EXCLUDED_METRICS
    assert "total_passes" not in entry["certifiable_metric_scope"]
    assert "successful_passes" not in entry["certifiable_metric_scope"]


def test_verifies_at_least_eight_certifiable_metrics_remain() -> None:
    entry = _load_matrix()["providers"]["sportdb"]["capabilities"]["detailed_metrics"][0]
    assert len(entry["certifiable_metric_scope"]) >= 8


def test_verifies_accepted_provider_entries_are_not_rewritten() -> None:
    matrix = _load_matrix()
    routing = MODULE.parse_routing_text(_load_routing_text())
    assert MODULE.detect_forbidden_provider_drift({"providers": MODULE.EXPECTED_ACCEPTED_PROVIDER_MATRIX}, matrix) == []
    assert MODULE.detect_forbidden_provider_drift(MODULE.EXPECTED_ACCEPTED_ROUTING, routing) == []


def test_validates_routing_contains_detailed_metrics_shadow_route_only() -> None:
    routing = MODULE.parse_routing_text(_load_routing_text())
    sportdb_routes = []
    for family, buckets in routing.items():
        for bucket, entries in buckets.items():
            for entry in entries:
                if entry.get("provider") == "sportdb":
                    sportdb_routes.append((family, bucket, entry))
    assert len(sportdb_routes) == 1
    family, bucket, entry = sportdb_routes[0]
    assert family == "detailed_metrics"
    assert bucket == "shadow_routes"
    assert entry["competition_scope"] == "football:eng.1"
    assert entry["season_scope"] == "current-season-completed"


def test_summary_verdict_remains_not_certified_scope_limited_shadow_only() -> None:
    a10 = _load_a10()
    matrix = _load_matrix()
    routing_text = _load_routing_text()
    summary = MODULE.build_summary(
        matrix=matrix,
        routing_text=routing_text,
        a10=a10,
        a10_errors=MODULE.validate_a10_plan(a10),
        matrix_errors=MODULE.validate_sportdb_matrix_entry(matrix, a10),
        routing_errors=MODULE.validate_sportdb_routing_entry(routing_text, a10),
        matrix_drift=MODULE.detect_forbidden_provider_drift({"providers": MODULE.EXPECTED_ACCEPTED_PROVIDER_MATRIX}, matrix),
        routing_drift=MODULE.detect_forbidden_provider_drift(MODULE.EXPECTED_ACCEPTED_ROUTING, MODULE.parse_routing_text(routing_text)),
        forbidden_status_values=[],
    )
    assert summary["classification"] == "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_APPLIED"
    assert summary["certification"]["verdict"] == "NOT_CERTIFIED_SCOPE_LIMITED_SHADOW_REGISTRATION_ONLY"
    assert summary["certification"]["certified_routes"] == []


def test_source_contains_no_http_network_calls_or_api_key_reads() -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in [
        "urllib.request",
        "requests.",
        "httpx.",
        "urlopen",
        "SPORTDB_API_KEY",
        "HIGHLIGHTLY_API_KEY",
        "from bet.api_clients.",
        "import bet.api_clients.",
    ]:
        assert forbidden not in src
