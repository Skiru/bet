from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = (
    REPO_ROOT / "scripts/sportdb_p2e_scope_limited_shadow_registration_validate.py"
)
SPEC = importlib.util.spec_from_file_location(
    "sportdb_p2e_scope_limited_shadow_registration_validate",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _load_a10() -> dict:
    return MODULE.load_json(
        REPO_ROOT
        / (
            "certification/football/"
            "p2e_sportdb_semantic_gap_review_certification_plan_summary.json"
        )
    )


def _load_matrix() -> dict:
    return MODULE.load_json(REPO_ROOT / "config/provider_capability_matrix.json")


def _load_routing_text() -> str:
    return MODULE.load_text(REPO_ROOT / "config/football_routing.yaml")


def test_validates_a10_plan_fixture() -> None:
    assert MODULE.validate_a10_plan(_load_a10()) == []


def test_current_repo_blocks_sportdb_scope_limited_registration() -> None:
    errors = MODULE.validate_sportdb_matrix_entry(_load_matrix(), _load_a10())
    assert "sportdb_matrix_classification_mismatch" in errors
    assert "sportdb_matrix_capability_family_mismatch" in errors
    assert "sportdb_matrix_detailed_metrics_entry_count_mismatch" in errors


def test_current_repo_blocks_sportdb_routing_registration() -> None:
    errors = MODULE.validate_sportdb_routing_entry(_load_routing_text(), _load_a10())
    assert errors == ["sportdb_routing_entry_count_mismatch"]


def test_detect_forbidden_status_values_still_flags_production_ready() -> None:
    entry = {
        "status": "PRODUCTION_READY",
        "competition_scope": "football:eng.1",
        "season_scope": "current-season-completed",
        "mode": "shadow",
        "selectable_as_projection": False,
    }
    assert "PRODUCTION_READY_detected" in MODULE.detect_forbidden_status_values(entry)


def test_current_matrix_has_no_sportdb_detailed_metrics_registration() -> None:
    sportdb = _load_matrix()["providers"]["sportdb"]
    assert sportdb["classification"] == "NOT_IMPLEMENTED"
    assert "detailed_metrics" not in sportdb["capabilities"]
    assert sportdb["capabilities"]["current_discovery"][0]["status"] == "NOT_IMPLEMENTED"


def test_current_routing_has_no_sportdb_routes() -> None:
    routing = MODULE.parse_routing_text(_load_routing_text())
    sportdb_routes = []
    for family, buckets in routing.items():
        for bucket, entries in buckets.items():
            for entry in entries:
                if entry.get("provider") == "sportdb":
                    sportdb_routes.append((family, bucket, entry))
    assert sportdb_routes == []


def test_current_repo_still_rejects_disallowed_capability_families() -> None:
    matrix = copy.deepcopy(_load_matrix())
    matrix["providers"]["sportdb"]["capabilities"]["current_form"] = [
        {
            "status": "CERTIFIED_SHADOW",
            "competition_scope": "football:eng.1",
            "season_scope": "current-season-completed",
            "mode": "shadow",
            "selectable_as_projection": False,
            "evidence_replay": True,
        }
    ]
    errors = MODULE.validate_sportdb_matrix_entry(matrix, _load_a10())
    assert "sportdb_matrix_capability_family_mismatch" in errors


def test_summary_verdict_remains_not_certified_when_registration_missing() -> None:
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
        matrix_drift=[],
        routing_drift=[],
        forbidden_status_values=[],
    )
    assert summary["classification"] == "SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION_BLOCKED_SCRIPT_OR_PARSER_DEFECT"
    assert summary["certification"]["verdict"] == "NOT_CERTIFIED_SCOPE_LIMITED_SHADOW_REGISTRATION_ONLY"
    assert summary["registration"]["applied"] is False
    assert summary["registration"]["status"] == "UNKNOWN"
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
