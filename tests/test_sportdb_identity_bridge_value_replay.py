from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.sportdb_p2e_identity_bridge_value_replay import (
    NOT_CERTIFIED_VERDICT,
    build_identity_bridge_assessment,
    build_value_replay,
    compare_identity,
    extract_sportdb_match_identity,
    load_sportdb_operation_bundles,
    normalize_team_name,
    validate_p2e_a6_summary,
)


def test_validates_p2e_a6_summary_with_all_five_operations() -> None:
    summary = {
        "phase_id": "P2E_A6_SPORTDB_EVIDENCE_BUNDLE_AND_REPLAY_CONTRACT",
        "operations": {
            name: {
                "bundle_id": f"{name}-bundle",
                "request_identity": f"sportdb:{name}:football:england:premier-league:2025-2026:xQXUa3UG",
                "bundle_files": [f"/tmp/{name}.json"],
            }
            for name in (
                "competition_results",
                "competition_standings",
                "match_events",
                "match_lineups",
                "match_stats",
            )
        },
    }
    assert validate_p2e_a6_summary(summary) == []


def test_rejects_missing_local_bundle_file_paths(tmp_path: Path) -> None:
    summary = {
        "operations": {
            "match_stats": {
                "bundle_id": "bundle",
                "request_identity": "sportdb:match_stats:football:england:premier-league:2025-2026:xQXUa3UG",
                "bundle_files": [str(tmp_path / "missing.json")],
            }
        }
    }
    with pytest.raises(FileNotFoundError):
        load_sportdb_operation_bundles(summary)


def test_extracts_sportdb_match_identity_from_fixture_bundles() -> None:
    bundles = {
        "match_events": {
            "files": {
                "normalized.json": {
                    "provider_match_id": "xQXUa3UG",
                    "raw_result": {
                        "data": {
                            "homeName": "Brighton",
                            "awayName": "Manchester Utd",
                        }
                    },
                }
            },
            "meta": {
                "request_identity": "sportdb:match_events:football:england:premier-league:2025-2026:xQXUa3UG"
            },
        },
        "match_stats": {
            "files": {
                "manifest.json": {
                    "request_identity": "sportdb:match_stats:football:england:premier-league:2025-2026:xQXUa3UG"
                }
            }
        },
        "competition_results": {
            "files": {
                "normalized.json": [
                    {
                        "provider_match_id": "xQXUa3UG",
                        "score": "0-3",
                        "status": "FINISHED",
                    }
                ]
            }
        },
        "__aux__": {
            "mapping_summary": {
                "finished_match_probe": {
                    "selected_match_raw": {
                        "startDateTimeUtc": "2026-05-24T15:00:00.000Z",
                        "tournamentName": "ENGLAND: Premier League",
                    }
                }
            }
        },
    }
    identity = extract_sportdb_match_identity(bundles)
    assert identity["match_id"] == "xQXUa3UG"
    assert identity["competition"] == "ENGLAND: Premier League"
    assert identity["season"] == "2025-2026"
    assert identity["kickoff_or_match_date"] == "2026-05-24T15:00:00.000Z"
    assert identity["home_team_normalized"] == "brighton"
    assert identity["away_team_normalized"] == "manchester united"
    assert identity["score"] == "0-3"


def test_normalizes_team_names_deterministically() -> None:
    assert normalize_team_name("Manchester Utd") == "manchester united"
    assert normalize_team_name("Brighton & Hove Albion") == "brighton and hove albion"
    assert normalize_team_name("Paris-Saint Germain FC") == "paris saint germain"


def test_rejects_fuzzy_only_identity_as_same_match_proof() -> None:
    sportdb_identity = {
        "match_id": "xQXUa3UG",
        "competition": "ENGLAND: Premier League",
        "season": "2025-2026",
        "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
        "home_team_normalized": "brighton",
        "away_team_normalized": "manchester united",
        "score": "0-3",
        "status": "FINISHED",
    }
    candidate = {
        "path": "reports/example.json",
        "provider": "highlightly",
        "competition": "Premier League",
        "season": "2025",
        "kickoff_or_match_date": None,
        "home_team_normalized": "brighton and hove albion",
        "away_team_normalized": "manchester united",
        "score": None,
        "status": None,
    }
    comparison = compare_identity(sportdb_identity, candidate)
    assert comparison["same_match_proof_available"] is False
    assert comparison["proof_type"] == "none"


def test_accepts_deterministic_fixture_identity_match_only_with_required_fields() -> None:
    sportdb_identity = {
        "match_id": "xQXUa3UG",
        "competition": "ENGLAND: Premier League",
        "season": "2025-2026",
        "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
        "home_team_normalized": "brighton",
        "away_team_normalized": "manchester united",
        "score": "0-3",
        "status": "FINISHED",
    }
    candidate = {
        "path": "reports/example.json",
        "provider": "highlightly",
        "competition": "ENGLAND: Premier League",
        "season": "2025-2026",
        "kickoff_or_match_date": "2026-05-24T19:00:00+04:00",
        "home_team_normalized": "brighton",
        "away_team_normalized": "manchester united",
        "score": "0-3",
        "status": "FINISHED",
    }
    comparison = compare_identity(sportdb_identity, candidate)
    assert comparison["same_match_proof_available"] is True
    assert comparison["proof_type"] == "deterministic_fixture_identity_match"

    missing_score = dict(candidate)
    missing_score["score"] = None
    missing_score["status"] = None
    comparison = compare_identity(sportdb_identity, missing_score)
    assert comparison["same_match_proof_available"] is False


def test_disallows_value_replay_when_same_match_proof_is_false() -> None:
    assessment = {
        "direct_value_replay_allowed": False,
        "selected_candidate_path": None,
    }
    replay = build_value_replay({}, {"expected_goals": {"home": 1.0, "away": 2.0}}, ["Big chances"], [], assessment)
    assert replay["performed"] is False
    assert replay["metrics_compared"] == []
    assert replay["unknown_metrics_preserved"] == ["Big chances"]


def test_compares_integer_metrics_exactly() -> None:
    candidate = {
        "path": "reports/example.json",
        "provider": "highlightly",
        "metrics": {
            "shots_on_goal": {"home": 2, "away": 7},
        },
        "unknown_metrics": [],
        "semantics": {},
    }
    assessment = {
        "direct_value_replay_allowed": True,
        "selected_candidate_path": "reports/example.json",
    }
    replay = build_value_replay({}, {"shots_on_goal": {"home": 2, "away": 8}}, [], [candidate], assessment)
    assert replay["performed"] is True
    assert replay["metrics_compared"] == ["shots_on_goal"]
    assert replay["metric_mismatches"][0]["metric"] == "shots_on_goal"


def test_compares_decimal_metrics_with_point_zero_one_tolerance() -> None:
    candidate = {
        "path": "reports/example.json",
        "provider": "highlightly",
        "metrics": {
            "expected_goals": {"home": 0.79, "away": 1.65},
        },
        "unknown_metrics": [],
        "semantics": {},
    }
    assessment = {
        "direct_value_replay_allowed": True,
        "selected_candidate_path": "reports/example.json",
    }
    replay = build_value_replay({}, {"expected_goals": {"home": 0.78, "away": 1.66}}, [], [candidate], assessment)
    assert replay["performed"] is True
    assert replay["metrics_matched"] == ["expected_goals"]


def test_preserves_unknown_metrics_without_pass_fail() -> None:
    candidate = {
        "path": "reports/example.json",
        "provider": "highlightly",
        "metrics": {},
        "unknown_metrics": ["Successful passes"],
        "semantics": {},
    }
    assessment = {
        "direct_value_replay_allowed": False,
        "selected_candidate_path": None,
    }
    replay = build_value_replay({}, {}, ["Big chances"], [candidate], assessment)
    assert replay["unknown_metrics_preserved"] == ["Big chances"]
    assert replay["metric_mismatches"] == []


def test_source_contains_no_http_or_network_calls() -> None:
    src = Path("scripts/sportdb_p2e_identity_bridge_value_replay.py").read_text(encoding="utf-8")
    for forbidden in ["urllib.request", "requests.", "httpx.", "urlopen"]:
        assert forbidden not in src


def test_source_does_not_read_env_key_or_import_live_provider_clients() -> None:
    src = Path("scripts/sportdb_p2e_identity_bridge_value_replay.py").read_text(encoding="utf-8")
    for forbidden in ["SPORTDB_API_KEY", "from bet.api_clients.", "import bet.api_clients."]:
        assert forbidden not in src


def test_summary_verdict_remains_not_certified() -> None:
    assert NOT_CERTIFIED_VERDICT == "NOT_CERTIFIED_IDENTITY_BRIDGE_VALUE_REPLAY_ONLY"


def test_identity_assessment_blocks_without_same_match_proof() -> None:
    sportdb_identity = {
        "match_id": "xQXUa3UG",
        "home_team_normalized": "brighton",
        "away_team_normalized": "manchester united",
        "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
    }
    candidate = {
        "path": "reports/example.json",
        "provider": "highlightly",
        "competition": None,
        "season": None,
        "kickoff_or_match_date": None,
        "home_team_normalized": None,
        "away_team_normalized": None,
        "score": None,
        "status": None,
    }
    assessment = build_identity_bridge_assessment(sportdb_identity, [candidate])
    assert assessment["same_match_proof_available"] is False
    assert assessment["direct_value_replay_allowed"] is False
