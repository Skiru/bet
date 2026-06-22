from __future__ import annotations

from pathlib import Path
from bet.enrichment.football_data_foundation.fixture_context.loader import load_fixture_context_fixture
from bet.enrichment.football_data_foundation.fusion.fuser import ShadowFactFuser
from bet.enrichment.football_data_foundation.kernel.contracts import FactType, ProofLevel, SourceRole


def test_fusion_policy_success() -> None:
    fixture_path = Path("tests/fixtures/enrichment/football_data_foundation/pass3/generic_club_match_shadow.json")
    claims = load_fixture_context_fixture(fixture_path)
    
    fuser = ShadowFactFuser()
    summary = fuser.fuse(claims)
    
    assert summary is not None
    assert summary.run_id.startswith("run_")
    assert len(summary.fused_facts) == 3
    assert not summary.conflicts
    assert not summary.missing_fact_types
    assert summary.selectable_for_production is False
    assert summary.manual_authorization_required is True
    
    # Assert selectable_for_production is False on each fused fact
    for f in summary.fused_facts:
        assert f.selectable_for_production is False


def test_fusion_policy_conflicts() -> None:
    fixture_path = Path("tests/fixtures/enrichment/football_data_foundation/pass3/conflicting_current_status_shadow.json")
    claims = load_fixture_context_fixture(fixture_path)
    
    fuser = ShadowFactFuser()
    summary = fuser.fuse(claims)
    
    assert summary is not None
    assert len(summary.conflicts) == 1
    conflict = summary.conflicts[0]
    assert conflict.fact_type == FactType.MATCH_STATUS
    assert conflict.reason == "disagreement in values for MATCH_STATUS"
    assert set(conflict.source_keys) == {"highlightly", "sportdb"}
    
    # MATCH_STATUS is not successfully fused due to the conflict
    fused_types = {f.fact_type for f in summary.fused_facts}
    assert FactType.MATCH_STATUS not in fused_types
    assert FactType.SCORE in fused_types


def test_fusion_policy_exclusions_and_roles() -> None:
    # Let's verify that DOCS_CAPABILITY_ONLY and deferred/experimental are excluded
    fixture_path = Path("tests/fixtures/enrichment/football_data_foundation/pass3/generic_club_match_shadow.json")
    claims = list(load_fixture_context_fixture(fixture_path))
    
    # Let's add a claim with DOCS_CAPABILITY_ONLY proof level
    import copy
    bad_claim_1 = copy.deepcopy(claims[0])
    object.__setattr__(bad_claim_1, "proof_level", ProofLevel.DOCS_CAPABILITY_ONLY)
    # Docs-only proof cannot carry claim_value
    object.__setattr__(bad_claim_1, "claim_value", {})
    object.__setattr__(bad_claim_1, "confidence", 0.0)
    
    # Let's add a claim from an experimental probe
    bad_claim_2 = copy.deepcopy(claims[0])
    new_source = copy.deepcopy(bad_claim_2.source)
    object.__setattr__(new_source, "role", SourceRole.EXPERIMENTAL_PROBE)
    object.__setattr__(new_source, "allowed_proof_levels", (ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,))
    object.__setattr__(bad_claim_2, "source", new_source)
    object.__setattr__(bad_claim_2.identity, "source_key", "sportdb")
    object.__setattr__(bad_claim_2, "proof_level", ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF)
    
    all_claims = claims + [bad_claim_1, bad_claim_2]
    
    fuser = ShadowFactFuser()
    summary = fuser.fuse(all_claims)
    
    # Both extra claims should be in excluded_claims list
    assert len(summary.excluded_claims) == 2
    excluded_proofs = {c.proof_level for c in summary.excluded_claims}
    excluded_roles = {c.source.role for c in summary.excluded_claims}
    
    assert ProofLevel.DOCS_CAPABILITY_ONLY in excluded_proofs
    assert SourceRole.EXPERIMENTAL_PROBE in excluded_roles

# Line-endings normalization proof
