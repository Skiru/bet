from datetime import datetime, UTC
from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import OfficialFixtureContext
from bet.enrichment.football_data_foundation.live_shadow_canary.official_context import build_official_context_claim_batch
from bet.enrichment.football_data_foundation.kernel.contracts import FactType, ProofLevel


def test_build_official_context_claims() -> None:
    context = OfficialFixtureContext(
        fixture_slug="worldcup2026-norway-senegal",
        competition_name="FIFA World Cup 2026",
        official_source_url="https://www.fifa.com/en/match-centre/match/17/285023/289273/400021491",
        official_source_name="FIFA Official Website",
        match_id="400021491",
        home_team="Norway",
        away_team="Senegal",
        kickoff_at="2026-06-22T20:00:00Z",
        venue="Ullevaal Stadion",
        city="Oslo",
    )

    batch = build_official_context_claim_batch(context)
    
    assert batch.source_key == "fifa-official-match-centre"
    assert len(batch.claims) == 2
    
    # Assert fact types
    fact_types = {c.fact_type for c in batch.claims}
    assert FactType.FIXTURE_IDENTITY in fact_types
    assert FactType.REFERENCE_SCHEDULE in fact_types
    
    for c in batch.claims:
        assert c.proof_level == ProofLevel.REAL_LIVE_API_PROOF
        assert c.selectable_for_production is False
        assert c.payload_policy.raw_payload_stored is False
        assert c.confidence == 1.0


def test_build_official_context_claims_synthetic() -> None:
    # Simulated non-safely fetched context
    context = OfficialFixtureContext(
        fixture_slug="worldcup2026-norway-senegal",
        competition_name="FIFA World Cup 2026",
        official_source_url="not-fetched-live",
        official_source_name="Local Cache",
        match_id="400021491",
        home_team=None,
        away_team=None,
        kickoff_at=None,
    )

    batch = build_official_context_claim_batch(context)
    
    assert len(batch.claims) == 1
    claim = batch.claims[0]
    assert claim.fact_type == FactType.FIXTURE_IDENTITY
    assert claim.proof_level == ProofLevel.SYNTHETIC_CONTRACT_PROOF
    assert claim.selectable_for_production is False
