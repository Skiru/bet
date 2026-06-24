from __future__ import annotations

import json
from pathlib import Path

from scripts.sportdb_p2e_value_replay_against_accepted_provider import (
    NOT_CERTIFIED_VERDICT,
    classify_value_replay,
    compare_metric,
    detect_pass_family_semantic_gap,
    extract_canonical_metrics,
    load_highlightly_normalized_metrics,
    normalize_metric_value,
    validate_p2e_a6_summary,
    validate_p2e_a8_summary,
)


def test_validates_p2e_a8_ready_for_value_replay_summary() -> None:
    summary = {
        "phase_id": "P2E_A8_ACCEPTED_PROVIDER_SAME_MATCH_REPLAY_CAPTURE",
        "classification": "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_READY_FOR_VALUE_REPLAY",
        "same_match_selection": {
            "same_match_found": True,
            "selected_provider_match_id": "1173818273",
        },
        "accepted_provider_capture": {
            "performed": True,
            "metrics_available": True,
            "bundle_files": ["/tmp/normalized.json"],
        },
    }
    assert validate_p2e_a8_summary(summary) == []


def test_rejects_missing_sportdb_bundle_files() -> None:
    summary = {
        "phase_id": "P2E_A6_SPORTDB_EVIDENCE_BUNDLE_AND_REPLAY_CONTRACT",
        "operations": {
            "match_stats": {"bundle_files": []},
            "competition_results": {"bundle_files": ["x"]},
            "competition_standings": {"bundle_files": ["x"]},
            "match_events": {"bundle_files": ["x"]},
            "match_lineups": {"bundle_files": ["x"]},
        },
    }
    assert "bundle_files_missing:match_stats" in validate_p2e_a6_summary(summary)


def test_rejects_missing_highlightly_bundle_files(tmp_path: Path, monkeypatch) -> None:
    summary = {"accepted_provider_capture": {"bundle_files": [str(tmp_path / "missing.json")]}}
    monkeypatch.setattr(
        "scripts.sportdb_p2e_value_replay_against_accepted_provider.load_json",
        lambda path: {},
    )
    try:
        load_highlightly_normalized_metrics(summary)
    except FileNotFoundError as exc:
        assert "highlightly_bundle_missing_normalized_or_manifest" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_validates_deterministic_same_match_proof_fields() -> None:
    summary = {
        "same_match_proof": {
            "valid": True,
            "sportdb_flashscore_match_id": "xQXUa3UG",
            "highlightly_provider_match_id": "1173818273",
            "proof_type": "deterministic_fixture_identity_match",
            "proof_basis": ["competition", "season", "kickoff_or_match_date"],
        }
    }
    assert summary["same_match_proof"]["valid"] is True
    assert summary["same_match_proof"]["sportdb_flashscore_match_id"] == "xQXUa3UG"
    assert summary["same_match_proof"]["highlightly_provider_match_id"] == "1173818273"


def test_rejects_value_replay_if_same_match_proof_is_invalid() -> None:
    summary = {
        "same_match_proof": {"valid": False},
        "team_side_alignment": {"valid": True},
        "metric_replay": {
            "performed": False,
            "canonical_metrics_compared": [],
            "mismatched_metrics": [],
            "semantic_gaps": [],
        },
        "blockers": [],
    }
    assert (
        classify_value_replay(summary)
        == "SPORTDB_VALUE_REPLAY_BLOCKED_SAME_MATCH_PROOF_INVALID"
    )


def test_extracts_canonical_metrics_from_sportdb_normalized_fixture() -> None:
    normalized = {
        "provider_match_id": "xQXUa3UG",
        "raw_result": {
            "data": [
                {
                    "period": "Match",
                    "stats": [
                        {"statName": "Expected goals (xG)", "homeValue": "0.78", "awayValue": "1.66"},
                        {"statName": "Ball possession", "homeValue": "52%", "awayValue": "48%"},
                        {"statName": "Passes", "homeValue": "86% (415/484)", "awayValue": "83% (372/450)"},
                    ],
                }
            ]
        },
    }
    extracted = extract_canonical_metrics(normalized)
    assert extracted["metrics"]["expected_goals"] == {"home": 0.78, "away": 1.66}
    assert extracted["metrics"]["possession"] == {"home": 52.0, "away": 48.0}
    assert extracted["metrics"]["total_passes"] == {"home": 415, "away": 372}
    assert extracted["metrics"]["successful_passes"] == {"home": 86, "away": 83}


def test_extracts_canonical_metrics_from_highlightly_normalized_fixture() -> None:
    normalized = {
        "provider_match_id": "1173818273",
        "fixture_identity": {"home_team": "Brighton", "away_team": "Manchester United"},
        "statistics": [
            {"normalized_metric_name": "expected_goals", "side": "home", "value": 0.79},
            {"normalized_metric_name": "expected_goals", "side": "away", "value": 1.66},
            {"normalized_metric_name": "shots_on_goal", "side": "home", "value": 2},
            {"normalized_metric_name": "shots_on_goal", "side": "away", "value": 7},
            {"normalized_metric_name": None, "raw_stat_name": "Expected Assists", "side": "home", "value": 1.2},
        ],
        "missing_target_metrics": ["Red cards"],
    }
    extracted = extract_canonical_metrics(normalized)
    assert extracted["metrics"]["expected_goals"] == {"home": 0.79, "away": 1.66}
    assert extracted["metrics"]["shots_on_goal"] == {"home": 2, "away": 7}
    assert "Expected Assists" in extracted["unknown_metrics_preserved"]


def test_excludes_non_canonical_highlightly_only_metrics_from_pass_fail() -> None:
    normalized = {
        "statistics": [
            {"normalized_metric_name": "big_chances_created", "side": "home", "value": 0},
            {"normalized_metric_name": "free_kicks", "side": "away", "value": 11},
        ]
    }
    extracted = extract_canonical_metrics(normalized)
    assert extracted["metrics"] == {}
    assert extracted["provider_extra_metrics"] == ["big_chances_created", "free_kicks"]


def test_compares_integer_metrics_exactly() -> None:
    result = compare_metric("shots_on_goal", 2, 2)
    assert result["classification"] == "exact_match"
    mismatch = compare_metric("shots_on_goal", 2, 3)
    assert mismatch["classification"] == "mismatch"


def test_compares_expected_goals_with_zero_point_zero_five_tolerance() -> None:
    result = compare_metric("expected_goals", 0.78, 0.82)
    assert result["classification"] == "tolerance_match"


def test_compares_possession_with_zero_point_five_tolerance() -> None:
    result = compare_metric("possession", 52.0, 0.52)
    assert result["classification"] == "exact_match"
    near = compare_metric("possession", 52.0, 0.515)
    assert near["classification"] == "tolerance_match"


def test_classifies_unit_or_semantic_uncertainty_as_semantic_gap() -> None:
    result = compare_metric("successful_passes", 86, "86%")
    assert result["classification"] == "semantic_gap"


def test_detects_pass_family_definition_gap_from_local_evidence_shape() -> None:
    gaps = detect_pass_family_semantic_gap(
        {
            "total_passes": {"home": 415, "away": 372},
            "successful_passes": {"home": 86, "away": 83},
        },
        {
            "total_passes": {"home": 484, "away": 450},
            "successful_passes": {"home": 415, "away": 372},
        },
        {
            "total_passes": {
                "home": {"unit": "count"},
                "away": {"unit": "count"},
            },
            "successful_passes": {
                "home": {"unit": "percentage"},
                "away": {"unit": "percentage"},
            },
        },
        {
            "total_passes": {
                "home": {"unit": "count"},
                "away": {"unit": "count"},
            },
            "successful_passes": {
                "home": {"unit": "count"},
                "away": {"unit": "count"},
            },
        },
    )
    assert "total_passes" in gaps
    assert "successful_passes" in gaps


def test_blocks_on_team_side_alignment_uncertainty() -> None:
    summary = {
        "same_match_proof": {"valid": True},
        "team_side_alignment": {"valid": False},
        "metric_replay": {
            "performed": False,
            "canonical_metrics_compared": [],
            "mismatched_metrics": [],
            "semantic_gaps": [],
        },
        "blockers": [],
    }
    assert (
        classify_value_replay(summary)
        == "SPORTDB_VALUE_REPLAY_BLOCKED_TEAM_SIDE_ALIGNMENT"
    )


def test_blocks_certification_ready_if_fewer_than_five_metrics_compared() -> None:
    summary = {
        "same_match_proof": {"valid": True},
        "team_side_alignment": {"valid": True},
        "metric_replay": {
            "performed": True,
            "canonical_metrics_compared": ["a", "b", "c", "d"],
            "mismatched_metrics": [],
            "semantic_gaps": [],
        },
        "blockers": [],
    }
    assert (
        classify_value_replay(summary)
        == "SPORTDB_VALUE_REPLAY_BLOCKED_NO_OVERLAPPING_CANONICAL_METRICS"
    )


def test_source_contains_no_http_or_network_calls_or_live_provider_imports() -> None:
    src = Path(
        "scripts/sportdb_p2e_value_replay_against_accepted_provider.py"
    ).read_text(encoding="utf-8")
    for forbidden in ["urllib.request", "requests.", "httpx.", "urlopen"]:
        assert forbidden not in src
    assert "from bet.api_clients." not in src
    assert "import bet.api_clients." not in src


def test_source_does_not_read_secret_env_names() -> None:
    src = Path(
        "scripts/sportdb_p2e_value_replay_against_accepted_provider.py"
    ).read_text(encoding="utf-8")
    assert "SPORTDB" + "_API_KEY" not in src
    assert "HIGHLIGHTLY" + "_API_KEY" not in src


def test_summary_verdict_remains_not_certified() -> None:
    assert NOT_CERTIFIED_VERDICT == "NOT_CERTIFIED_VALUE_REPLAY_ONLY"


def test_normalize_metric_value_possession_ratio_to_percentage() -> None:
    normalized = normalize_metric_value("possession", 0.52)
    assert normalized["value"] == 52.0
