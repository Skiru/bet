"""Tests for S5 pricing-aware validation."""
from __future__ import annotations

import pytest

from bet.pipeline.agent_artifact_contracts import validate_s5_artifact_v2
from bet.pipeline.canonical_continuity import bind_candidate_identity


def _candidate() -> dict:
    return bind_candidate_identity(
        {
            "home_team": "France",
            "away_team": "Spain",
            "kickoff": "2026-07-14T18:00:00Z",
            "market": "Match Winner",
            "market_family": "RESULT",
            "market_type": "ml",
            "selection": "France",
            "sport": "football",
            "competition": "World Cup",
            "safety_score": 0.85,
            "risk_flags": [],
            "counter_evidence": [],
            "context_checks": {
                name: {
                    "status": "CLEAR",
                    "as_of_utc": "2026-07-14T12:00:00Z",
                    "source_refs": ["fixture:pricing-contract"],
                }
                for name in (
                    "injuries_lineups",
                    "motivation_tournament_context",
                    "travel_fatigue",
                    "morale_recent_form",
                    "upset_volatility_risk",
                )
            },
            "analytical_status": "ANALYTICAL_READY",
            "pricing_status": "PRICED",
            "odds_decimal": 1.95,
            "odds_source": "Superbet",
            "odds_as_of": "2026-07-14T12:00:00Z",
        }
    )


@pytest.fixture
def base_s5_payload():
    return {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S5",
        "status": "PASS",
        "betting_day": "2026-07-14",
        "run_id": "TEST_RUN_ID",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "payload": {
            "work_order_id": "WO-TEST_RUN_ID-S5",
            "agent_id": "bet-risk-gatekeeper",
            "source_git_sha": "8092f9575362521ac06e3026c2ad67a33f542b7f",
            "manifest_sha": "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08",
            "source_s4_path": "/tmp/mock_s4.json",
            "source_s4_sha256": "dummy_s4_sha",
            "input_candidate_count": 1,
            "candidates": [_candidate()],
            "rejected_candidates": [],
            "accounting": {
                "unaccounted_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "overlapping_terminal_categories": [],
            },
        }
    }

@pytest.fixture
def mock_s4_file(tmp_path):
    # Create artifacts and data directories under tmp_path
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    s4_path = data_dir / "2026-07-14_s4_valuation_candidates.json"
    s4_content = {
        "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
        "candidates": [_candidate()]
    }
    import json
    s4_path.write_text(json.dumps(s4_content))

    s4_evidence_path = artifacts_dir / "S4.json"
    s4_evidence = {
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S4",
        "status": "PASS",
        "betting_day": "2026-07-14",
        "run_id": "TEST_RUN_ID",
        "payload": {
            "s4_valuation_output_path": str(s4_path),
            "s4_valuation_output_sha256": "dummy_s4_sha"
        }
    }
    s4_evidence_path.write_text(json.dumps(s4_evidence))
    return s4_path

@pytest.fixture
def mock_manifest():
    return {
        "steps": [
            {
                "id": "S4",
                "name": "s4_valuation_candidates",
                "output": "s4_valuation_candidates"
            }
        ]
    }


def test_valid_priced_candidate(base_s5_payload, mock_s4_file, mock_manifest, monkeypatch):
    """Positive test for valid PRICED candidate."""
    from bet.pipeline import run_evidence
    monkeypatch.setattr(run_evidence, "sha256_file", lambda p: "dummy_s4_sha")
    monkeypatch.setattr(run_evidence, "repo_head_sha", lambda r: "8092f9575362521ac06e3026c2ad67a33f542b7f")
    monkeypatch.setattr(run_evidence, "manifest_hash", lambda r: "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08")

    payload = base_s5_payload
    payload["payload"]["source_s4_path"] = str(mock_s4_file)

    validate_s5_artifact_v2(payload, mock_s4_file.parent.parent, "2026-07-14", "TEST_RUN_ID", manifest=mock_manifest)


def test_valid_price_pending_candidate(base_s5_payload, mock_s4_file, mock_manifest, monkeypatch):
    """Positive test for valid PRICE_PENDING candidate with no odds."""
    from bet.pipeline import run_evidence
    monkeypatch.setattr(run_evidence, "sha256_file", lambda p: "dummy_s4_sha")
    monkeypatch.setattr(run_evidence, "repo_head_sha", lambda r: "8092f9575362521ac06e3026c2ad67a33f542b7f")
    monkeypatch.setattr(run_evidence, "manifest_hash", lambda r: "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08")

    payload = base_s5_payload
    payload["payload"]["source_s4_path"] = str(mock_s4_file)
    cand = payload["payload"]["candidates"][0]
    cand["pricing_status"] = "PRICE_PENDING"
    cand["odds_decimal"] = None
    cand["odds_source"] = None
    cand["odds_as_of"] = None
    cand["ev"] = None
    cand["bettable"] = False

    validate_s5_artifact_v2(payload, mock_s4_file.parent.parent, "2026-07-14", "TEST_RUN_ID", manifest=mock_manifest)


def test_valid_pricing_degraded_candidate(base_s5_payload, mock_s4_file, mock_manifest, monkeypatch):
    """Positive test for valid PRICING_DEGRADED candidate (e.g. after 401/429)."""
    from bet.pipeline import run_evidence
    monkeypatch.setattr(run_evidence, "sha256_file", lambda p: "dummy_s4_sha")
    monkeypatch.setattr(run_evidence, "repo_head_sha", lambda r: "8092f9575362521ac06e3026c2ad67a33f542b7f")
    monkeypatch.setattr(run_evidence, "manifest_hash", lambda r: "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08")

    payload = base_s5_payload
    payload["payload"]["source_s4_path"] = str(mock_s4_file)
    cand = payload["payload"]["candidates"][0]
    cand["pricing_status"] = "PRICING_DEGRADED"
    cand["odds_decimal"] = None
    cand["ev"] = None
    cand["bettable"] = False

    validate_s5_artifact_v2(payload, mock_s4_file.parent.parent, "2026-07-14", "TEST_RUN_ID", manifest=mock_manifest)


def test_priced_candidate_without_odds_fails(base_s5_payload, mock_s4_file, mock_manifest, monkeypatch):
    """Negative test: PRICED candidate missing odds throws ValueError."""
    from bet.pipeline import run_evidence
    monkeypatch.setattr(run_evidence, "sha256_file", lambda p: "dummy_s4_sha")
    monkeypatch.setattr(run_evidence, "repo_head_sha", lambda r: "8092f9575362521ac06e3026c2ad67a33f542b7f")
    monkeypatch.setattr(run_evidence, "manifest_hash", lambda r: "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08")

    payload = base_s5_payload
    payload["payload"]["source_s4_path"] = str(mock_s4_file)
    cand = payload["payload"]["candidates"][0]
    cand["pricing_status"] = "PRICED"
    cand["odds_decimal"] = None

    with pytest.raises(ValueError, match="missing valid odds"):
        validate_s5_artifact_v2(payload, mock_s4_file.parent.parent, "2026-07-14", "TEST_RUN_ID", manifest=mock_manifest)


def test_unpriced_candidate_with_ev_fails(base_s5_payload, mock_s4_file, mock_manifest, monkeypatch):
    """Negative test: unpriced candidate with non-null EV throws ValueError."""
    from bet.pipeline import run_evidence
    monkeypatch.setattr(run_evidence, "sha256_file", lambda p: "dummy_s4_sha")
    monkeypatch.setattr(run_evidence, "repo_head_sha", lambda r: "8092f9575362521ac06e3026c2ad67a33f542b7f")
    monkeypatch.setattr(run_evidence, "manifest_hash", lambda r: "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08")

    payload = base_s5_payload
    payload["payload"]["source_s4_path"] = str(mock_s4_file)
    cand = payload["payload"]["candidates"][0]
    cand["pricing_status"] = "PRICE_PENDING"
    cand["odds_decimal"] = None
    cand["ev"] = 0.15

    with pytest.raises(ValueError, match="must have null/unavailable EV"):
        validate_s5_artifact_v2(payload, mock_s4_file.parent.parent, "2026-07-14", "TEST_RUN_ID", manifest=mock_manifest)


def test_unpriced_candidate_with_stake_fails(base_s5_payload, mock_s4_file, mock_manifest, monkeypatch):
    """Negative test: unpriced candidate with non-null stake throws ValueError."""
    from bet.pipeline import run_evidence
    monkeypatch.setattr(run_evidence, "sha256_file", lambda p: "dummy_s4_sha")
    monkeypatch.setattr(run_evidence, "repo_head_sha", lambda r: "8092f9575362521ac06e3026c2ad67a33f542b7f")
    monkeypatch.setattr(run_evidence, "manifest_hash", lambda r: "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08")

    payload = base_s5_payload
    payload["payload"]["source_s4_path"] = str(mock_s4_file)
    cand = payload["payload"]["candidates"][0]
    cand["pricing_status"] = "PRICE_PENDING"
    cand["odds_decimal"] = None
    cand["stake"] = 100.0

    with pytest.raises(ValueError, match="must have null/unavailable stake"):
        validate_s5_artifact_v2(payload, mock_s4_file.parent.parent, "2026-07-14", "TEST_RUN_ID", manifest=mock_manifest)


def test_unpriced_candidate_with_bettable_true_fails(base_s5_payload, mock_s4_file, mock_manifest, monkeypatch):
    """Negative test: unpriced candidate with bettable=True throws ValueError."""
    from bet.pipeline import run_evidence
    monkeypatch.setattr(run_evidence, "sha256_file", lambda p: "dummy_s4_sha")
    monkeypatch.setattr(run_evidence, "repo_head_sha", lambda r: "8092f9575362521ac06e3026c2ad67a33f542b7f")
    monkeypatch.setattr(run_evidence, "manifest_hash", lambda r: "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08")

    payload = base_s5_payload
    payload["payload"]["source_s4_path"] = str(mock_s4_file)
    cand = payload["payload"]["candidates"][0]
    cand["pricing_status"] = "PRICE_PENDING"
    cand["odds_decimal"] = None
    cand["bettable"] = True

    with pytest.raises(ValueError, match="must have bettable=False"):
        validate_s5_artifact_v2(payload, mock_s4_file.parent.parent, "2026-07-14", "TEST_RUN_ID", manifest=mock_manifest)
