from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts/sportdb_p2e_replay_comparison_decision.py"
SPEC = importlib.util.spec_from_file_location("sportdb_p2e_replay_comparison_decision", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _base_shadow_summary() -> dict:
    return {
        "classification": "SPORTDB_SHADOW_ADAPTER_READY_FOR_REPLAY_COMPARISON",
        "call_budget": {
            "mcp_tool_calls_made": 5,
            "mcp_session_calls_made": 0,
            "rest_calls_made": 0,
        },
        "stats_probe": {"available": True},
        "events_probe": {"available": True},
        "lineups_probe": {"available": True},
        "standings_probe": {"available": True},
        "certification": {
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
            "verdict": "NOT_CERTIFIED_SHADOW_ADAPTER_ONLY",
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_repo(root: Path, *, promote_sportdb: bool = False) -> None:
    _write_json(root / "certification/football/p2e_sportdb_shadow_adapter_summary.json", _base_shadow_summary())
    _write_json(
        root / "certification/football/p2d_highlightly_certification_summary.json",
        {
            "provider": "highlightly",
            "verdict": "PRODUCTION_READY_MULTI_SOURCE_SCOPE_LIMITED",
            "certified_routes": [
                "current_form/highlightly/football:eng.1/current-season-completed/shadow"
            ],
            "api_football_strategy": "historical_fallback_only",
        },
    )
    _write_json(
        root / "reports/football_p2d_all_candidates_probe_report.json",
        {
            "providers": {
                "api-football": {
                    "status": "PROBE_SUCCESS_HISTORICAL",
                    "replay_readiness": "existing_repository_client_with_evidence_capture_and_offline_replay",
                }
            }
        },
    )
    _write_json(
        root / "config/provider_capability_matrix.json",
        {
            "providers": {
                "sportdb": {
                    "capabilities": {
                        "current_discovery": [
                            {
                                "status": "CERTIFIED_SELECTABLE" if promote_sportdb else "NOT_IMPLEMENTED",
                                "selectable_as_projection": promote_sportdb,
                                "evidence_replay": promote_sportdb,
                            }
                        ]
                    }
                }
            }
        },
    )
    routing_provider = "sportdb" if promote_sportdb else "espn"
    _write_text(
        root / "config/football_routing.yaml",
        "routing:\n"
        "  current_form:\n"
        "    production_routes:\n"
        f"      - provider: {routing_provider}\n"
        "        selectable_status: CERTIFIED_SELECTABLE\n",
    )
    _write_text(
        root / "src/bet/enrichment/football_service.py",
        "from bet.integration.source_result import SourceOperationResult\n"
        "from bet.integration.evidence import write_source_operation_bundle\n"
        'CANDIDATES = {"sportdb": CandidateRecord(implementation_state="NOT_IMPLEMENTED", replay_capabilities=())}\n',
    )
    _write_text(root / "src/bet/integration/source_result.py", "class SourceOperationResult: ...\n")
    _write_text(root / "src/bet/integration/evidence.py", "def write_source_operation_bundle(*args, **kwargs):\n    return '', None\n")
    _write_text(root / "src/bet/api_clients/highlightly.py", "class HighlightlyClient:\n    pass\n")
    _write_text(
        root / "src/bet/api_clients/api_football.py",
        "from bet.integration.evidence import write_source_operation_bundle\n"
        "class APIFootballClient:\n    pass\n",
    )


def test_validates_corrected_sportdb_shadow_adapter_summary() -> None:
    valid, blockers = MODULE.validate_sportdb_shadow_adapter_summary(_base_shadow_summary())
    assert valid is True
    assert blockers == []


def test_rejects_zero_mcp_tool_calls() -> None:
    summary = _base_shadow_summary()
    summary["call_budget"]["mcp_tool_calls_made"] = 0
    valid, blockers = MODULE.validate_sportdb_shadow_adapter_summary(summary)
    assert valid is False
    assert "shadow_summary_mcp_tool_calls_made_invalid" in blockers


def test_rejects_mcp_session_calls_equal_five() -> None:
    summary = _base_shadow_summary()
    summary["call_budget"]["mcp_session_calls_made"] = 5
    valid, blockers = MODULE.validate_sportdb_shadow_adapter_summary(summary)
    assert valid is False
    assert "shadow_summary_mcp_session_calls_made_invalid" in blockers
    assert "shadow_summary_mcp_session_calls_made_equals_tool_count" in blockers


def test_detects_missing_replay_contract_as_non_promotable(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    replay = MODULE.detect_sportdb_replay_contract(tmp_path)
    assert replay["sportdb_replay_contract_status"] == "missing"
    assert replay["source_operation_result_artifacts_detected"] is False
    assert replay["evidence_bundle_writer_detected_for_sportdb"] is False
    assert replay["blocking_gaps"]


def test_decision_blocks_promotion_when_shadow_exists_without_replay_bundle(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    shadow_data = MODULE.load_json(tmp_path / "certification/football/p2e_sportdb_shadow_adapter_summary.json")
    shadow_valid, shadow_blockers = MODULE.validate_sportdb_shadow_adapter_summary(shadow_data)
    replay = MODULE.detect_sportdb_replay_contract(tmp_path)
    promotion_detected, promotion_blockers = MODULE.detect_sportdb_routing_or_matrix_promotion(tmp_path)
    baseline_valid, baseline_blockers, baseline_details = MODULE.validate_accepted_provider_baseline(tmp_path)
    summary = MODULE.build_decision_summary(
        root=tmp_path,
        shadow_data=shadow_data,
        shadow_valid=shadow_valid,
        shadow_blockers=shadow_blockers,
        replay_assessment=replay,
        baseline_valid=baseline_valid,
        baseline_blockers=baseline_blockers,
        baseline_details=baseline_details,
        promotion_detected=promotion_detected,
        promotion_blockers=promotion_blockers,
    )
    assert summary["classification"] == "SPORTDB_SHADOW_ONLY_NOT_REPLAY_EQUIVALENT_TO_ACCEPTED_PROVIDERS"
    assert summary["decision"]["promotion_allowed"] is False
    assert summary["decision"]["certification_rerun_allowed"] is False


def test_summary_verdict_remains_not_certified_replay_comparison_only(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    shadow_data = MODULE.load_json(tmp_path / "certification/football/p2e_sportdb_shadow_adapter_summary.json")
    shadow_valid, shadow_blockers = MODULE.validate_sportdb_shadow_adapter_summary(shadow_data)
    replay = MODULE.detect_sportdb_replay_contract(tmp_path)
    promotion_detected, promotion_blockers = MODULE.detect_sportdb_routing_or_matrix_promotion(tmp_path)
    baseline_valid, baseline_blockers, baseline_details = MODULE.validate_accepted_provider_baseline(tmp_path)
    summary = MODULE.build_decision_summary(
        root=tmp_path,
        shadow_data=shadow_data,
        shadow_valid=shadow_valid,
        shadow_blockers=shadow_blockers,
        replay_assessment=replay,
        baseline_valid=baseline_valid,
        baseline_blockers=baseline_blockers,
        baseline_details=baseline_details,
        promotion_detected=promotion_detected,
        promotion_blockers=promotion_blockers,
    )
    assert summary["certification"]["verdict"] == "NOT_CERTIFIED_REPLAY_COMPARISON_DECISION_ONLY"
    assert summary["next_step"] == "P2E_A6_SPORTDB_EVIDENCE_BUNDLE_AND_REPLAY_CONTRACT"


def test_detects_sportdb_routing_or_matrix_promotion_as_blocked(tmp_path: Path) -> None:
    _make_repo(tmp_path, promote_sportdb=True)
    detected, blockers = MODULE.detect_sportdb_routing_or_matrix_promotion(tmp_path)
    assert detected is True
    assert blockers


def test_source_contains_no_network_calls_api_key_reads_or_live_provider_imports() -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in [
        "urllib.request",
        "requests.",
        "httpx.",
        "urlopen",
        "SPORTDB_API_KEY",
        "from bet.api_clients.",
        "import bet.api_clients.",
    ]:
        assert forbidden not in src
