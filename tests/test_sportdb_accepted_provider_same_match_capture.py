from __future__ import annotations

import json
from pathlib import Path

from scripts.sportdb_p2e_accepted_provider_same_match_capture import (
    NOT_CERTIFIED_VERDICT,
    build_highlightly_search_plan,
    classify_capture_summary,
    extract_sportdb_target_identity,
    normalize_team_name,
    score_candidate_identity,
    select_exact_same_match_candidate,
    write_highlightly_capture_bundle,
)


def test_validates_a7_summary_requires_same_match_proof_absent() -> None:
    summary = json.loads(
        Path(
            "certification/football/p2e_sportdb_identity_bridge_value_replay_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        summary["classification"]
        == "SPORTDB_IDENTITY_BRIDGE_READY_BUT_VALUE_REPLAY_BLOCKED_NO_ACCEPTED_SAME_MATCH_EVIDENCE"
    )
    assert summary["identity_bridge_assessment"]["same_match_proof_available"] is False
    assert summary["identity_bridge_assessment"]["direct_value_replay_allowed"] is False


def test_extracts_sportdb_target_identity_from_summary_and_bundles() -> None:
    a7 = {
        "sportdb_identity": {
            "match_id": "xQXUa3UG",
            "competition": "ENGLAND: Premier League",
            "season": "2025-2026",
            "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
            "home_team": "Brighton",
            "away_team": "Manchester Utd",
            "home_team_normalized": "brighton",
            "away_team_normalized": "manchester united",
            "score": "0-3",
            "status": "Finished",
        }
    }
    a6 = {
        "operations": {
            name: {
                "bundle_id": f"{name}-bundle",
                "request_identity": (
                    "sportdb:match_events:football:england:premier-league:2025-2026:xQXUa3UG"
                    if name == "match_events"
                    else "sportdb:match_stats:football:england:premier-league:2025-2026:xQXUa3UG"
                ),
                "bundle_files": [],
            }
            for name in (
                "competition_results",
                "competition_standings",
                "match_events",
                "match_lineups",
                "match_stats",
            )
        }
    }
    tmp_dir = Path("/tmp")
    bundle_root = tmp_dir / "p2e_a8_test_extract"
    bundle_root.mkdir(parents=True, exist_ok=True)
    files = {
        "competition_results": [
            {
                "provider_match_id": "xQXUa3UG",
                "score": "0-3",
                "status": "Finished",
            }
        ],
        "competition_standings": {},
        "match_events": {
            "provider_match_id": "xQXUa3UG",
            "raw_result": {
                "data": {
                    "homeName": "Brighton",
                    "awayName": "Manchester Utd",
                }
            },
        },
        "match_lineups": {},
        "match_stats": {},
    }
    for op_name, normalized in files.items():
        op_dir = bundle_root / op_name
        op_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = op_dir / "normalized.json"
        manifest_path = op_dir / "manifest.json"
        normalized_path.write_text(json.dumps(normalized), encoding="utf-8")
        manifest_path.write_text(
            json.dumps(
                {
                    "request_identity": "sportdb:match_stats:football:england:premier-league:2025-2026:xQXUa3UG"
                }
            ),
            encoding="utf-8",
        )
        a6["operations"][op_name]["bundle_files"] = [
            str(normalized_path),
            str(manifest_path),
        ]
    identity = extract_sportdb_target_identity(a7, a6)
    assert identity["match_id"] == "xQXUa3UG"
    assert identity["home_team_normalized"] == "brighton"
    assert identity["away_team_normalized"] == "manchester united"
    assert identity["score"] == "0-3"


def test_normalizes_team_names_deterministically() -> None:
    assert normalize_team_name("Manchester Utd") == "manchester united"
    assert normalize_team_name("Brighton & Hove Albion FC") == "brighton and hove albion"
    assert normalize_team_name("Paris-Saint Germain") == "paris saint germain"


def test_builds_highlightly_search_plan_from_identity() -> None:
    plan = build_highlightly_search_plan(
        {
            "competition": "ENGLAND: Premier League",
            "season": "2025-2026",
            "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
            "home_team_normalized": "brighton",
            "away_team_normalized": "manchester united",
            "score": "0-3",
            "match_id": "xQXUa3UG",
        }
    )
    assert plan["league_name"] == "Premier League"
    assert plan["country_name"] == "England"
    assert plan["season_start_year"] == 2025
    assert plan["target_date"] == "2026-05-24"


def test_exact_same_match_requires_competition_season_date_teams_and_score_status() -> None:
    identity = {
        "competition": "ENGLAND: Premier League",
        "season": "2025-2026",
        "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
        "home_team_normalized": "brighton",
        "away_team_normalized": "manchester united",
        "score": "0-3",
        "status": "Finished",
    }
    candidate = {
        "provider_match_id": "1028343227",
        "competition": "Premier League",
        "season": "2025",
        "kickoff_or_match_date": "2026-05-24T20:00:00+05:00",
        "home_team_normalized": "brighton",
        "away_team_normalized": "manchester united",
        "score": "0-3",
        "status": "Finished",
    }
    score = score_candidate_identity(identity, candidate)
    assert score["exact_same_match"] is True
    missing = dict(candidate)
    missing["score"] = None
    missing["status"] = None
    assert score_candidate_identity(identity, missing)["exact_same_match"] is False


def test_rejects_fuzzy_only_candidate() -> None:
    identity = {
        "competition": "ENGLAND: Premier League",
        "season": "2025-2026",
        "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
        "home_team_normalized": "brighton",
        "away_team_normalized": "manchester united",
        "score": "0-3",
        "status": "Finished",
    }
    fuzzy = {
        "provider_match_id": "1",
        "competition": "Premier League",
        "season": "2025",
        "kickoff_or_match_date": None,
        "home_team_normalized": "brighton and hove albion",
        "away_team_normalized": "manchester united",
        "score": None,
        "status": None,
    }
    assert score_candidate_identity(identity, fuzzy)["exact_same_match"] is False


def test_rejects_ambiguous_exact_candidates() -> None:
    identity = {
        "competition": "ENGLAND: Premier League",
        "season": "2025-2026",
        "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
        "home_team_normalized": "brighton",
        "away_team_normalized": "manchester united",
        "score": "0-3",
        "status": "Finished",
    }
    candidates = [
        {
            "type": "candidate",
            "provider_match_id": "1",
            "competition": "Premier League",
            "season": "2025",
            "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
            "home_team_normalized": "brighton",
            "away_team_normalized": "manchester united",
            "score": "0-3",
            "status": "Finished",
        },
        {
            "type": "candidate",
            "provider_match_id": "2",
            "competition": "Premier League",
            "season": "2025",
            "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
            "home_team_normalized": "brighton",
            "away_team_normalized": "manchester united",
            "score": "0-3",
            "status": "Finished",
        },
    ]
    scores = [score_candidate_identity(identity, candidate) for candidate in candidates]
    assert select_exact_same_match_candidate(candidates, scores) is None


def test_returns_no_exact_match_classification_when_proof_is_missing() -> None:
    summary = {
        "accepted_provider_capture": {"performed": False, "metrics_available": False},
        "same_match_selection": {"same_match_found": False},
        "blockers": [],
    }
    assert (
        classify_capture_summary(summary)
        == "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_NO_EXACT_MATCH_FOUND"
    )


def test_writes_highlightly_capture_bundle_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.sportdb_p2e_accepted_provider_same_match_capture.EVIDENCE_ROOT",
        tmp_path,
    )
    capture = {
        "provider_match_id": "1028343227",
        "request": {
            "search_request_identity": "GET https://soccer.highlightly.net/matches?leagueId=33973&season=2025&limit=380",
            "statistics_request_identity": "GET https://soccer.highlightly.net/statistics/1028343227",
        },
        "fixture_identity": {
            "competition": "ENGLAND: Premier League",
            "season": "2025-2026",
            "kickoff_or_match_date": "2026-05-24T15:00:00.000Z",
            "home_team": "Brighton",
            "away_team": "Manchester Utd",
            "score": "0-3",
            "status": "Finished",
        },
        "sportdb_target_identity": {"match_id": "xQXUa3UG"},
        "response_sha256": "a" * 64,
        "parser_version": "highlightly-statistics-v1",
        "safe_preview": {"selected_candidate": {"provider_match_id": "1028343227"}},
        "normalized": {
            "provider_match_id": "1028343227",
            "fixture_identity": {"score": "0-3"},
            "statistics": [],
            "unknown_metrics": [],
        },
    }
    bundle = write_highlightly_capture_bundle(capture)
    manifest = json.loads((tmp_path / bundle["bundle_id"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "highlightly"
    assert manifest["operation"] == "accepted_provider_same_match_capture"
    assert manifest["bundle_id"] == bundle["bundle_id"]
    assert manifest["provider_match_id"] == "1028343227"
    assert manifest["sportdb_flashscore_match_id"] == "xQXUa3UG"
    assert manifest["response_sha256"] == "a" * 64
    assert manifest["normalized_sha256"] == bundle["normalized_sha256"]
    assert manifest["secret_safe"] is True


def test_source_contains_no_sportdb_live_call_route_or_matrix_mutation_or_secret_write() -> None:
    src = Path("scripts/sportdb_p2e_accepted_provider_same_match_capture.py").read_text(
        encoding="utf-8"
    )
    forbidden_secret_markers = [
        "SPORTDB_API_KEY" + "=",
        "HIGHLIGHTLY_API_KEY" + "=",
        "X" + "-API-Key" + ":",
    ]
    assert "from bet.api_clients.sportdb" not in src
    assert "import bet.api_clients.sportdb" not in src
    assert "sportdb_mcp" not in src
    assert "config/football_routing.yaml" not in src
    assert "config/provider_capability_matrix.json" not in src
    for marker in forbidden_secret_markers:
        assert marker not in src


def test_summary_verdict_remains_not_certified() -> None:
    assert NOT_CERTIFIED_VERDICT == "NOT_CERTIFIED_ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_ONLY"
