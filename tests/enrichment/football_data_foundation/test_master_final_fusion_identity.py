from __future__ import annotations

import copy
from pathlib import Path

from bet.enrichment.football_data_foundation.fixture_context.loader import (
    load_fixture_context_fixture,
)
from bet.enrichment.football_data_foundation.fusion.fuser import (
    ShadowFactFuser,
)
from bet.enrichment.football_data_foundation.kernel.contracts import (
    FactType,
    ProofLevel,
    SourceRole,
)


def test_generator_input_safety() -> None:
    # Generator input instead of list should not break run_id or missing facts
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/generic_club_shadow_fixture.json"
    )
    claims = load_fixture_context_fixture(fixture_path)

    # We pass a generator
    claims_gen = (c for c in claims)
    fuser = ShadowFactFuser()
    summary = fuser.fuse(claims_gen)

    assert summary is not None
    assert summary.run_id.startswith("run_")
    assert not summary.conflicts
    assert not summary.missing_fact_types


def test_two_different_fixtures_do_not_conflict() -> None:
    # Two different fixtures with same fact type (e.g. SCORE) do not conflict
    fixture_1_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/worldcup_2026_shadow_fixture.json"
    )
    fixture_2_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/generic_club_shadow_fixture.json"
    )

    claims_1 = load_fixture_context_fixture(fixture_1_path)
    claims_2 = load_fixture_context_fixture(fixture_2_path)

    all_claims = list(claims_1) + list(claims_2)
    fuser = ShadowFactFuser()
    summary = fuser.fuse(all_claims)

    # Since they are different matches (different identity keys), they don't conflict
    assert not summary.conflicts
    # We should have fused facts for both matches
    assert len(summary.fused_facts) == 6


def test_same_fixture_score_disagreement_creates_conflict() -> None:
    # Same fixture current SCORE disagreement creates conflict with values_by_source
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/current_score_conflict_fixture.json"
    )
    claims = load_fixture_context_fixture(fixture_path)

    fuser = ShadowFactFuser()
    summary = fuser.fuse(claims)

    assert len(summary.conflicts) == 1
    conflict = summary.conflicts[0]
    assert conflict.fact_type == FactType.SCORE
    assert conflict.reason == "current_fact_value_disagreement"
    assert "sportdb" in conflict.values_by_source
    assert "highlightly" in conflict.values_by_source
    assert conflict.values_by_source["sportdb"] == {"score_home": 3, "score_away": 2}
    assert conflict.values_by_source["highlightly"] == {
        "score_home": 1,
        "score_away": 1,
    }


def test_historical_cannot_override_current() -> None:
    # Historical/open-data/soccerdata cannot override current MATCH_STATUS/SCORE/STANDINGS
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/generic_club_shadow_fixture.json"
    )
    claims = list(load_fixture_context_fixture(fixture_path))

    # Let's add an open data claim with HISTORICAL_DEEP role for SCORE
    hist_claim = copy.deepcopy(claims[0])
    object.__setattr__(hist_claim, "fact_type", FactType.SCORE)
    object.__setattr__(hist_claim.source, "role", SourceRole.HISTORICAL_DEEP)
    object.__setattr__(hist_claim, "proof_level", ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF)
    object.__setattr__(hist_claim, "claim_value", {"score_home": 9, "score_away": 9})
    object.__setattr__(hist_claim.freshness, "is_current_truth_allowed", False)

    all_claims = claims + [hist_claim]
    fuser = ShadowFactFuser()
    summary = fuser.fuse(all_claims)

    # HISTORICAL_DEEP is excluded during eligibility check for SCORE, so it does not conflict
    # and the fused score remains the current one (3-2)
    assert not summary.conflicts
    fused_score = [f for f in summary.fused_facts if f.fact_type == FactType.SCORE][0]
    assert fused_score.value == {"score_home": 3, "score_away": 2}


def test_context_facts_do_not_block_as_current_conflict() -> None:
    # Context facts with different values do not create blocking current conflict
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/generic_club_shadow_fixture.json"
    )
    claims = list(load_fixture_context_fixture(fixture_path))

    # Add a conflicting FIXTURE_IDENTITY claim (which is a context fact type)
    conflict_identity = copy.deepcopy(claims[0])
    object.__setattr__(conflict_identity.source, "source_key", "highlightly")
    object.__setattr__(
        conflict_identity,
        "claim_value",
        {
            "competition_name": "Champions League Conflicting Name",
            "home_team": "Manchester City FC",
            "away_team": "Real Madrid CF",
        },
    )

    all_claims = claims + [conflict_identity]
    fuser = ShadowFactFuser()
    summary = fuser.fuse(all_claims)

    # Should not block or create a conflict
    assert not summary.conflicts
    # The primary source should be selected deterministically
    fused_identity = [
        f for f in summary.fused_facts if f.fact_type == FactType.FIXTURE_IDENTITY
    ][0]
    assert fused_identity.primary_source_key in {"sportdb", "highlightly"}


def test_deterministic_source_priority() -> None:
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/generic_club_shadow_fixture.json"
    )
    claims = list(load_fixture_context_fixture(fixture_path))

    # We have a sportdb claim with CURRENT_LIVE (rank 9 since proof level is REAL_LIVE_API_PROOF)
    # Let's add a highlightly claim with CURRENT_LIVE_BENCHMARK + REAL_ACCEPTED_ARTIFACT_PROOF (rank 10)
    best_claim = copy.deepcopy(claims[2])  # SCORE claim
    object.__setattr__(best_claim.source, "source_key", "highlightly")
    object.__setattr__(best_claim.source, "role", SourceRole.CURRENT_LIVE_BENCHMARK)
    object.__setattr__(
        best_claim, "proof_level", ProofLevel.REAL_ACCEPTED_ARTIFACT_PROOF
    )
    object.__setattr__(best_claim, "confidence", 0.99)
    object.__setattr__(
        best_claim, "claim_value", {"score_home": 3, "score_away": 2}
    )  # Same value to avoid conflict

    all_claims = claims + [best_claim]
    fuser = ShadowFactFuser()
    summary = fuser.fuse(all_claims)

    fused_score = [f for f in summary.fused_facts if f.fact_type == FactType.SCORE][0]
    # highlightly has rank 10, so it must be selected as primary
    assert fused_score.primary_source_key == "highlightly"
    assert "sportdb" in fused_score.supporting_source_keys
    assert fused_score.selectable_for_production is False
