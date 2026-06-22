from __future__ import annotations

from datetime import UTC, datetime

from bet.enrichment.football_data_foundation.kernel.contracts import (
    EvidenceClaim,
    EvidenceClaimBatch,
    EvidenceFreshness,
    FactType,
    PayloadPolicy,
    ProofLevel,
    ProviderIdentity,
    SourceDescriptor,
    SourceRole,
)
from bet.enrichment.football_data_foundation.shadow_certification.summary import (
    summarize_shadow_certification,
)


def test_summarize_shadow_certification() -> None:
    observed_at = datetime.now(UTC)
    
    desc_live = SourceDescriptor(
        source_key="sportdb",
        display_name="SportDB",
        role=SourceRole.CURRENT_LIVE,
        requires_credentials=True,
        supports_live=True,
        supports_historical=False,
        supports_reference=True,
        supports_replay=True,
        allowed_proof_levels=(ProofLevel.REAL_LIVE_API_PROOF,),
    )
    claim_live = EvidenceClaim(
        source=desc_live,
        proof_level=ProofLevel.REAL_LIVE_API_PROOF,
        fact_type=FactType.MATCH_STATISTIC,
        identity=ProviderIdentity(source_key="sportdb"),
        freshness=EvidenceFreshness(observed_at=observed_at, is_current_truth_allowed=True),
        payload_policy=PayloadPolicy(),
        claim_value={"score_home": 1},
        confidence=0.9,
    )
    batch_live = EvidenceClaimBatch(
        batch_id="batch-1",
        source_key="sportdb",
        adapter_name="SportDBLiveClient",
        adapter_version="football-foundation-pass2",
        generated_at=observed_at,
        claims=(claim_live,),
    )

    desc_probe = SourceDescriptor(
        source_key="fotmob-probe",
        display_name="FotMob Rich Probe",
        role=SourceRole.EXPERIMENTAL_PROBE,
        requires_credentials=False,
        supports_live=False,
        supports_historical=True,
        supports_reference=True,
        supports_replay=True,
        allowed_proof_levels=(ProofLevel.SYNTHETIC_CONTRACT_PROOF,),
    )
    claim_probe = EvidenceClaim(
        source=desc_probe,
        proof_level=ProofLevel.SYNTHETIC_CONTRACT_PROOF,
        fact_type=FactType.MATCH_STATISTIC,
        identity=ProviderIdentity(source_key="fotmob-probe"),
        freshness=EvidenceFreshness(observed_at=observed_at, is_current_truth_allowed=False),
        payload_policy=PayloadPolicy(),
        claim_value={},
        confidence=0.0,
    )
    batch_probe = EvidenceClaimBatch(
        batch_id="batch-2",
        source_key="fotmob-probe",
        adapter_name="FotMobProbe",
        adapter_version="football-foundation-pass2",
        generated_at=observed_at,
        claims=(claim_probe,),
    )

    summaries = summarize_shadow_certification([batch_live, batch_probe])

    assert "sportdb" in summaries
    summary_sdb = summaries["sportdb"]
    assert summary_sdb.real_claim_count == 1
    assert summary_sdb.docs_only_count == 0
    assert summary_sdb.synthetic_count == 0
    assert summary_sdb.selectable_for_production is False
    assert any("manual authorization" in r for r in summary_sdb.missing_authorization_reasons)

    assert "fotmob-probe" in summaries
    summary_probe = summaries["fotmob-probe"]
    assert summary_probe.real_claim_count == 0
    assert summary_probe.synthetic_count == 1
    assert summary_probe.selectable_for_production is False
    assert any("experimental" in r for r in summary_probe.missing_authorization_reasons)

