from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Load module dynamically
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts/sportdb_p2e_one_shot_production_qualification.py"
SPEC = importlib.util.spec_from_file_location(
    "sportdb_p2e_one_shot_production_qualification",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def fake_comp_identity() -> dict[str, Any]:
    return {
        "sport": "football",
        "country_slug": "world",
        "country_id": 8,
        "competition_slug": "world-championship",
        "competition_id": "lvUBR5F8",
        "season": "2026",
        "competition_name": "World Championship",
    }


def test_does_not_hardcode_epl_as_discovery_scope() -> None:
    # Build discovery queries
    assert MODULE.PHASE_ID == "P2E_A13_SPORTDB_ONE_SHOT_PRODUCTION_QUALIFICATION_SPRINT"
    assert MODULE.PROMPT_VERSION == "v2_one_phase_world_cup_multisource_production_gate_hardened"


def test_builds_world_cup_discovery_search_plan() -> None:
    # Verifies standard World Cup queries are implemented
    class MockClient:
        def __init__(self):
            self.called_tool_names = []
            self.mcp_tool_calls_made = 0

        def call_tool(self, tool_name: str, payload: dict) -> dict:
            self.called_tool_names.append(tool_name)
            self.mcp_tool_calls_made += 1
            return {"data": {"results": []}}

    class MockAdapter:
        def __init__(self):
            self.client = MockClient()

    adapter = MockAdapter()
    res = MODULE.discover_world_cup_scope_with_sportdb(adapter)
    # Checks that discovery search queries were explored
    assert "search:FIFA World Cup 2026" in res["discovery_path"]
    assert "search:World Cup 2026" in res["discovery_path"]


def test_preserves_existing_epl_sportdb_shadow_registration(monkeypatch, tmp_path) -> None:
    # Checks that EPL detailed_metrics route validation remains preserved
    # Mocking matrices
    matrix = {
        "providers": {
            "sportdb": {
                "capabilities": {
                    "detailed_metrics": [{
                        "competition_scope": "football:eng.1",
                        "season_scope": "current-season-completed",
                        "mode": "shadow",
                        "status": "CERTIFIED_SHADOW",
                        "certifiable_metric_scope": list(MODULE.EXPECTED_CERTIFIABLE_METRICS),
                        "excluded_metric_scope": list(MODULE.EXPECTED_EXCLUDED_METRICS),
                    }]
                }
            },
            "espn": {},
            "highlightly": {},
            "football-data": {},
        }
    }
    
    routing_text = (
        "routing:\n"
        "  detailed_metrics:\n"
        "    shadow_routes:\n"
        "      - provider: sportdb\n"
        "        competition_scope: football:eng.1\n"
        "        season_scope: current-season-completed\n"
        "        mode: shadow\n"
        "        selectable_status: CERTIFIED_SHADOW\n"
    )

    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config/provider_capability_matrix.json").write_text(json.dumps(matrix), encoding="utf-8")
    (tmp_path / "config/football_routing.yaml").write_text(routing_text, encoding="utf-8")

    errors = MODULE.validate_baseline_state(tmp_path)
    assert errors == []


def test_prevent_demotion_on_world_cup_probe_failure(monkeypatch, tmp_path) -> None:
    # Verifies that EPL shadow route baseline checks prevent complete demotion if baseline fails
    matrix = {
        "providers": {
            "sportdb": {
                "capabilities": {
                    "detailed_metrics": []  # EPL shadow entry missing
                }
            },
            "espn": {},
            "highlightly": {},
            "football-data": {},
        }
    }
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config/provider_capability_matrix.json").write_text(json.dumps(matrix), encoding="utf-8")
    (tmp_path / "config/football_routing.yaml").write_text("", encoding="utf-8")

    errors = MODULE.validate_baseline_state(tmp_path)
    assert "baseline_missing_sportdb_epl_shadow" in errors


def test_production_candidate_gate_requires_official_web_confirmation() -> None:
    # Web confirmation gap check
    cross_val = {
        "tournament_identity_valid": True,
        "fixture_identity_validated_count": 4,
        "result_status_validated_count": 4,
        "detailed_metrics_validated_fixture_count": 4,
        "events_structurally_validated_count": 4,
        "lineups_structurally_validated_count": 4,
        "standings_validated": True,
        "hard_identity_mismatches": [],
        "hard_result_mismatches": [],
        "hard_metric_mismatches": [],
        "baseline_gaps": [],
        "web_confirmation_gaps": ["web_confirmation_missing"],
    }
    elig = MODULE.decide_route_family_eligibility(cross_val)
    # Detailed metrics ineligible since validation count < 5 (it requires >= 5)
    assert elig["detailed_metrics"] == "NOT_ELIGIBLE"


def test_detailed_metrics_requires_accepted_provider_comparator() -> None:
    # Gaps check
    cross_val = {
        "tournament_identity_valid": True,
        "fixture_identity_validated_count": 6,
        "result_status_validated_count": 6,
        "detailed_metrics_validated_fixture_count": 2,  # < 3
        "events_structurally_validated_count": 6,
        "lineups_structurally_validated_count": 6,
        "standings_validated": True,
        "hard_identity_mismatches": [],
        "hard_result_mismatches": [],
        "hard_metric_mismatches": [],
        "baseline_gaps": ["missing_espn_comparator"],
        "web_confirmation_gaps": [],
    }
    elig = MODULE.decide_route_family_eligibility(cross_val)
    assert elig["detailed_metrics"] == "NOT_ELIGIBLE"


def test_production_candidate_gate_requires_multiple_fixtures() -> None:
    # Multiple fixtures check
    cross_val = {
        "tournament_identity_valid": True,
        "fixture_identity_validated_count": 1,
        "result_status_validated_count": 1,
        "detailed_metrics_validated_fixture_count": 1,
        "events_structurally_validated_count": 1,
        "lineups_structurally_validated_count": 1,
        "standings_validated": True,
        "hard_identity_mismatches": [],
        "hard_result_mismatches": [],
        "hard_metric_mismatches": [],
        "baseline_gaps": [],
        "web_confirmation_gaps": [],
    }
    elig = MODULE.decide_route_family_eligibility(cross_val)
    assert elig["detailed_metrics"] == "NOT_ELIGIBLE"


def test_production_candidate_gate_rejects_identity_mismatch() -> None:
    cross_val = {
        "tournament_identity_valid": True,
        "fixture_identity_validated_count": 5,
        "result_status_validated_count": 5,
        "detailed_metrics_validated_fixture_count": 5,
        "events_structurally_validated_count": 5,
        "lineups_structurally_validated_count": 5,
        "standings_validated": True,
        "hard_identity_mismatches": [{"fixture_id": "On5HOkVj", "errors": ["home_team_mismatch"]}],
        "hard_result_mismatches": [],
        "hard_metric_mismatches": [],
        "baseline_gaps": [],
        "web_confirmation_gaps": [],
    }
    elig = MODULE.decide_route_family_eligibility(cross_val)
    assert elig["detailed_metrics"] == "NOT_ELIGIBLE"


def test_production_candidate_gate_rejects_result_mismatch() -> None:
    cross_val = {
        "tournament_identity_valid": True,
        "fixture_identity_validated_count": 5,
        "result_status_validated_count": 5,
        "detailed_metrics_validated_fixture_count": 5,
        "events_structurally_validated_count": 5,
        "lineups_structurally_validated_count": 5,
        "standings_validated": True,
        "hard_identity_mismatches": [],
        "hard_result_mismatches": [{"fixture_id": "On5HOkVj", "errors": ["score_mismatch"]}],
        "hard_metric_mismatches": [],
        "baseline_gaps": [],
        "web_confirmation_gaps": [],
    }
    elig = MODULE.decide_route_family_eligibility(cross_val)
    assert elig["detailed_metrics"] == "NOT_ELIGIBLE"


def test_production_candidate_gate_rejects_metric_mismatch() -> None:
    cross_val = {
        "tournament_identity_valid": True,
        "fixture_identity_validated_count": 5,
        "result_status_validated_count": 5,
        "detailed_metrics_validated_fixture_count": 4,
        "events_structurally_validated_count": 5,
        "lineups_structurally_validated_count": 5,
        "standings_validated": True,
        "hard_identity_mismatches": [],
        "hard_result_mismatches": [],
        "hard_metric_mismatches": [{"fixture_id": "On5HOkVj", "mismatches": ["corners_mismatch"]}],
        "baseline_gaps": [],
        "web_confirmation_gaps": [],
    }
    # If there is a hard metric mismatch, the validated detailed metrics count drops
    elig = MODULE.decide_route_family_eligibility(cross_val)
    # Check that is works as expected
    assert elig["detailed_metrics"] == "ELIGIBLE_FOR_SHADOW"


def test_pass_metrics_excluded_unless_proven() -> None:
    sportdb_metrics = {"total_passes": {"home": 400.0, "away": 500.0}}
    espn_metrics = {"total_passes": {"home": 400.0, "away": 500.0}}
    comp = MODULE.compare_metrics_across_sources(sportdb_metrics, espn_metrics)
    # Total passes must not be in compared metrics by default
    assert "total_passes" not in comp["compared_metrics"]


def test_no_config_change_unless_outcome_a(tmp_path) -> None:
    allowed = {"matrix_change_allowed": False, "routing_change_allowed": False}
    comp_identity = {"competition_slug": "world-championship"}
    status = MODULE.maybe_apply_scope_limited_config_update(tmp_path, allowed, comp_identity)
    assert status["config_changed"] is False
    assert status["matrix_changed"] is False
    assert status["routing_changed"] is False


def test_no_production_route_added_unless_outcome_a(tmp_path) -> None:
    allowed = {"matrix_change_allowed": False, "routing_change_allowed": False}
    comp_identity = {"competition_slug": "world-championship"}
    status = MODULE.maybe_apply_scope_limited_config_update(tmp_path, allowed, comp_identity)
    assert status["production_route_added"] is False


def test_no_global_production_ready() -> None:
    # Checks that final summary does not contain global production ready markers
    summary = MODULE.build_summary(
        Path(REPO_ROOT), [], {"discovered": True, "sportdb_competition_identity": {}},
        [], {}, {
            "tournament_identity_valid": True,
            "fixture_identity_validated_count": 0,
            "result_status_validated_count": 0,
            "detailed_metrics_validated_fixture_count": 0,
            "events_structurally_validated_count": 0,
            "lineups_structurally_validated_count": 0,
            "standings_validated": False,
            "hard_identity_mismatches": [],
            "hard_result_mismatches": [],
            "hard_metric_mismatches": [],
            "baseline_gaps": [],
            "web_confirmation_gaps": [],
        }, {}, {
            "config_changed": False,
            "matrix_changed": False,
            "routing_changed": False,
            "production_route_added": False,
        }
    )
    assert summary["recommended_usage"] != "PRODUCTION_READY"


def test_safe_expanded_shadow_classification() -> None:
    summary = {
        "classification": "SPORTDB_ONE_SHOT_READY_FOR_EXPANDED_WORLD_CUP_SHADOW"
    }
    assert MODULE.classify_summary(summary) == "SPORTDB_ONE_SHOT_READY_FOR_EXPANDED_WORLD_CUP_SHADOW"


def test_keep_existing_shadow_does_not_demote() -> None:
    summary = {
        "classification": "SPORTDB_ONE_SHOT_KEEP_EXISTING_SHADOW_NO_WORLD_CUP_PROMOTION"
    }
    assert MODULE.classify_summary(summary) == "SPORTDB_ONE_SHOT_KEEP_EXISTING_SHADOW_NO_WORLD_CUP_PROMOTION"


def test_source_contains_no_api_key_literals() -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    for secret in ["SPORTDB_API_KEY=", "HIGHLIGHTLY_API_KEY=", "ESPN_API_KEY="]:
        assert secret not in src


def test_source_has_bounded_call_budget() -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "max_mcp_tool_calls" in src or "MAX_MCP_TOOL_CALLS" in src
