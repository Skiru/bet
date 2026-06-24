from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts/sportdb_p2e_final_shadow_registration_audit.py"
SPEC = importlib.util.spec_from_file_location(
    "sportdb_p2e_final_shadow_registration_audit",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _load_matrix_at(revision: str) -> dict:
    return MODULE.load_json_at_revision(REPO_ROOT, revision, MODULE.MATRIX_PATH)


def _load_routing_at(revision: str) -> str:
    return MODULE.load_text_at_revision(REPO_ROOT, revision, MODULE.ROUTING_PATH)


def _metric_scope_jsons(
    certifiable: list[str],
    *,
    excluded: list[str] | None = None,
    a10_certifiable: list[str] | None = None,
    a11_certifiable: list[str] | None = None,
) -> dict[str, dict]:
    excluded = excluded or list(MODULE.EXPECTED_EXCLUDED_METRICS)
    return {
        MODULE.A10_SUMMARY_PATH: {
            "certification_plan": {
                "certifiable_metric_scope": list(a10_certifiable or MODULE.EXPECTED_CERTIFIABLE_METRICS),
                "excluded_metric_scope": list(excluded),
            }
        },
        MODULE.A11_SUMMARY_PATH: {
            "metric_scope": {
                "certifiable_metric_scope": list(a11_certifiable or MODULE.EXPECTED_CERTIFIABLE_METRICS),
                "excluded_metric_scope": list(excluded),
            }
        },
        MODULE.MATRIX_PATH: {
            "providers": {
                "sportdb": {
                    "capabilities": {
                        "detailed_metrics": [
                            {
                                "status": "CERTIFIED_SHADOW",
                                "mode": "shadow",
                                "certifiable_metric_scope": list(certifiable),
                                "excluded_metric_scope": list(excluded),
                            }
                        ]
                    }
                }
            }
        },
    }


def _patch_metric_scope_sources(monkeypatch, payloads: dict[str, dict]) -> None:
    def fake_load_json(path: Path) -> dict:
        relative = path.relative_to(REPO_ROOT).as_posix()
        return payloads[relative]

    monkeypatch.setattr(MODULE, "load_json", fake_load_json)


def test_validate_a11_commit_identity_accepts_current_repo() -> None:
    assert MODULE.validate_a11_commit_identity(REPO_ROOT) == []


def test_rejects_a11_if_parent_is_not_a10_sha(monkeypatch) -> None:
    def fake_git_text(repo_root: Path, *args: str) -> str:
        if args == ("rev-parse", f"{MODULE.a11_sha()}^"):
            return "deadbeef\n"
        if args == ("log", "-1", "--format=%s", MODULE.a11_sha()):
            return MODULE.EXPECTED_A11_SUBJECT + "\n"
        raise AssertionError(args)

    monkeypatch.setattr(MODULE, "git_text", fake_git_text)
    errors = MODULE.validate_a11_commit_identity(REPO_ROOT)
    assert any(error.startswith("a11_parent_mismatch:") for error in errors)


def test_rejects_a11_if_changed_paths_are_not_exact_expected_five_files(monkeypatch) -> None:
    monkeypatch.setattr(
        MODULE,
        "git_text",
        lambda repo_root, *args: "config/football_routing.yaml\nconfig/provider_capability_matrix.json\n",
    )
    errors = MODULE.validate_a11_changed_paths(REPO_ROOT)
    assert errors == ["a11_changed_paths_mismatch"]


def test_rejects_matrix_diff_if_any_provider_other_than_sportdb_changes(monkeypatch) -> None:
    before = _load_matrix_at(MODULE.a10_sha())
    after = copy.deepcopy(_load_matrix_at(MODULE.a11_sha()))
    after["providers"]["espn"]["classification"] = "DRIFTED"

    def fake_load_json_at_revision(repo_root: Path, revision: str, relative_path: str) -> dict:
        return before if revision == MODULE.a10_sha() else after

    monkeypatch.setattr(MODULE, "load_json_at_revision", fake_load_json_at_revision)
    errors = MODULE.validate_a11_matrix_diff_no_accepted_provider_drift(REPO_ROOT)
    assert any(error.startswith("a11_matrix_changed_providers_invalid:") for error in errors)


def test_rejects_routing_diff_if_sportdb_added_under_production_routes(monkeypatch) -> None:
    before = _load_routing_at(MODULE.a10_sha())
    after = before + (
        "  detailed_metrics:\n"
        "    production_routes:\n"
        "      - provider: sportdb\n"
        "        competition_scope: football:eng.1\n"
        "        season_scope: current-season-completed\n"
        "        mode: shadow\n"
        "        selectable_status: CERTIFIED_SHADOW\n"
    )
    diff = (
        "+  detailed_metrics:\n"
        "+    production_routes:\n"
        "+      - provider: sportdb\n"
        "+        competition_scope: football:eng.1\n"
        "+        season_scope: current-season-completed\n"
        "+        mode: shadow\n"
        "+        selectable_status: CERTIFIED_SHADOW\n"
    )

    monkeypatch.setattr(
        MODULE,
        "load_text_at_revision",
        lambda repo_root, revision, relative_path: before if revision == MODULE.a10_sha() else after,
    )
    monkeypatch.setattr(MODULE, "git_text", lambda repo_root, *args: diff)
    errors = MODULE.validate_a11_routing_diff_no_production_promotion(REPO_ROOT)
    assert any(error.startswith("a11_routing_diff_production_route_detected:") for error in errors)


def test_accepts_routing_diff_only_for_detailed_metrics_shadow_or_candidate_route(monkeypatch) -> None:
    before = _load_routing_at(MODULE.a10_sha())
    after = before + (
        "  detailed_metrics:\n"
        "    candidate_routes:\n"
        "      - provider: sportdb\n"
        "        competition_scope: football:eng.1\n"
        "        season_scope: current-season-completed\n"
        "        mode: shadow\n"
        "        selectable_status: CERTIFIED_SHADOW\n"
    )
    diff = (
        "+  detailed_metrics:\n"
        "+    candidate_routes:\n"
        "+      - provider: sportdb\n"
        "+        competition_scope: football:eng.1\n"
        "+        season_scope: current-season-completed\n"
        "+        mode: shadow\n"
        "+        selectable_status: CERTIFIED_SHADOW\n"
    )

    monkeypatch.setattr(
        MODULE,
        "load_text_at_revision",
        lambda repo_root, revision, relative_path: before if revision == MODULE.a10_sha() else after,
    )
    monkeypatch.setattr(MODULE, "git_text", lambda repo_root, *args: diff)
    assert MODULE.validate_a11_routing_diff_no_production_promotion(REPO_ROOT) == []


def test_accepts_matrix_diff_only_for_shadow_non_selectable_eng1_completed_scope(monkeypatch) -> None:
    before = _load_matrix_at(MODULE.a10_sha())
    after = _load_matrix_at(MODULE.a11_sha())

    def fake_load_json_at_revision(repo_root: Path, revision: str, relative_path: str) -> dict:
        return before if revision == MODULE.a10_sha() else after

    monkeypatch.setattr(MODULE, "load_json_at_revision", fake_load_json_at_revision)
    assert MODULE.validate_a11_matrix_diff_no_accepted_provider_drift(REPO_ROOT) == []


def test_rejects_final_audit_if_certifiable_metric_scope_has_only_five_metrics(monkeypatch) -> None:
    payloads = _metric_scope_jsons(["corners", "fouls", "offsides", "shots", "shots_on_target"])
    _patch_metric_scope_sources(monkeypatch, payloads)

    registered_scope, errors = MODULE.validate_metric_scope(REPO_ROOT)

    assert registered_scope["certifiable_metric_scope"] == sorted(
        ["corners", "fouls", "offsides", "shots", "shots_on_target"]
    )
    assert any(error.startswith("matrix_certifiable_metric_scope_mismatch:") for error in errors)
    assert "certifiable_metric_scope_cross_source_mismatch" in errors
    assert "matrix_certifiable_metric_scope_too_small:count=5" in errors


def test_rejects_generic_collapsed_metrics_that_replace_canonical_names(monkeypatch) -> None:
    collapsed = [
        "blocked_shots",
        "corners",
        "expected_goals",
        "fouls",
        "goalkeeper_saves",
        "offsides",
        "possession",
        "shots",
        "shots_on_target",
        "yellow_cards",
    ]
    payloads = _metric_scope_jsons(collapsed)
    _patch_metric_scope_sources(monkeypatch, payloads)

    _, errors = MODULE.validate_metric_scope(REPO_ROOT)

    assert any(error.startswith("matrix_certifiable_metric_scope_mismatch:") for error in errors)


def test_rejects_missing_required_canonical_metrics(monkeypatch) -> None:
    certifiable = [
        "corners",
        "fouls",
        "offsides",
        "shots",
        "shots_on_target",
        "total_passes",
        "successful_passes",
    ]
    payloads = _metric_scope_jsons(certifiable)
    _patch_metric_scope_sources(monkeypatch, payloads)

    _, errors = MODULE.validate_metric_scope(REPO_ROOT)

    assert any(error.startswith("matrix_certifiable_metric_scope_mismatch:") for error in errors)
    assert "excluded_metric_present_in_certifiable:total_passes" in errors
    assert "excluded_metric_present_in_certifiable:successful_passes" in errors
    for metric in [
        "blocked_shots",
        "expected_goals",
        "goalkeeper_saves",
        "possession",
        "shots_off_target",
        "shots_on_goal",
        "yellow_cards",
    ]:
        assert metric not in certifiable


def test_accepts_exact_a10_a11_ten_metric_set(monkeypatch) -> None:
    payloads = _metric_scope_jsons(list(MODULE.EXPECTED_CERTIFIABLE_METRICS))
    _patch_metric_scope_sources(monkeypatch, payloads)

    registered_scope, errors = MODULE.validate_metric_scope(REPO_ROOT)

    assert errors == []
    assert registered_scope["certifiable_metric_scope"] == sorted(MODULE.EXPECTED_CERTIFIABLE_METRICS)
    assert len(registered_scope["certifiable_metric_scope"]) == 10


def test_rejects_cross_source_mismatch_even_if_matrix_has_ten_metrics(monkeypatch) -> None:
    payloads = _metric_scope_jsons(
        list(MODULE.EXPECTED_CERTIFIABLE_METRICS),
        a11_certifiable=[
            "blocked_shots",
            "corners",
            "expected_goals",
            "fouls",
            "goalkeeper_saves",
            "offsides",
            "possession",
            "shots",
            "shots_on_target",
            "yellow_cards",
        ],
    )
    _patch_metric_scope_sources(monkeypatch, payloads)

    _, errors = MODULE.validate_metric_scope(REPO_ROOT)

    assert any(error.startswith("a11_certifiable_metric_scope_mismatch:") for error in errors)
    assert "certifiable_metric_scope_cross_source_mismatch" in errors


def test_summary_registered_scope_has_exactly_ten_metrics() -> None:
    summary = MODULE.audit_repository(REPO_ROOT)
    assert summary["registered_scope"]["certifiable_metric_scope"] == sorted(
        MODULE.EXPECTED_CERTIFIABLE_METRICS
    )
    assert len(summary["registered_scope"]["certifiable_metric_scope"]) == 10


def test_metric_scope_valid_cannot_be_true_when_metric_count_below_eight(monkeypatch) -> None:
    payloads = _metric_scope_jsons(
        [
            "blocked_shots",
            "corners",
            "expected_goals",
            "fouls",
            "goalkeeper_saves",
            "offsides",
            "possession",
        ]
    )
    _patch_metric_scope_sources(monkeypatch, payloads)

    summary = MODULE.audit_repository(REPO_ROOT)

    assert summary["audit"]["metric_scope_valid"] is False
    assert summary["classification"] == "SPORTDB_P2E_FINAL_AUDIT_BLOCKED_METRIC_SCOPE_INVALID"


def test_summary_verdict_passes_with_hardened_a11_diff_checks() -> None:
    summary = MODULE.audit_repository(REPO_ROOT)
    audit = summary["audit"]
    assert summary["classification"] == MODULE.PASS_CLASSIFICATION
    assert summary["previous_accepted_sha"] == MODULE.a11_sha()
    assert summary["final_verdict"] == MODULE.PASS_FINAL_VERDICT
    assert summary["registered_scope"]["route"] == MODULE.REGISTERED_ROUTE
    assert summary["registered_scope"]["status"] == "CERTIFIED_SHADOW"
    assert summary["registered_scope"]["mode"] == "shadow"
    assert summary["registered_scope"]["certifiable_metric_scope"] == sorted(
        MODULE.EXPECTED_CERTIFIABLE_METRICS
    )
    assert len(summary["registered_scope"]["certifiable_metric_scope"]) == 10
    assert "total_passes" not in summary["registered_scope"]["certifiable_metric_scope"]
    assert "successful_passes" not in summary["registered_scope"]["certifiable_metric_scope"]
    assert "total_passes" in summary["registered_scope"]["excluded_metric_scope"]
    assert "successful_passes" in summary["registered_scope"]["excluded_metric_scope"]
    assert summary["certification"]["verdict"] == "NOT_CERTIFIED_FINAL_SHADOW_REGISTRATION_AUDIT_ONLY"
    assert summary["next_step"] == MODULE.PASS_NEXT_STEP
    assert summary["secret_safe"] is True
    assert summary["final_review"] == "PASS"
    assert audit["evidence_chain_complete"] is True
    assert audit["matrix_state_valid"] is True
    assert audit["routing_state_valid"] is True
    assert audit["metric_scope_valid"] is True
    assert audit["metric_scope_errors"] == []
    assert audit["accepted_provider_drift_detected"] is False
    assert audit["forbidden_promotion_detected"] is False
    assert audit["production_route_added"] is False
    assert audit["certified_selectable_added"] is False
    assert audit["selectable_as_projection"] is False
    assert audit["current_live_scope_added"] is False
    assert audit["a11_commit_identity_valid"] is True
    assert audit["a11_changed_paths_valid"] is True
    assert audit["a11_matrix_diff_valid"] is True
    assert audit["a11_routing_diff_valid"] is True
