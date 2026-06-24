from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from bet.enrichment.football_data_foundation.kernel.contracts import (
    EvidenceClaimBatch,
    ProofLevel,
    SourceRole,
)


@dataclass
class ProviderCertificationSummary:
    source_key: str
    real_claim_count: int
    docs_only_count: int
    synthetic_count: int
    selectable_for_production: bool = False
    missing_authorization_reasons: list[str] = field(default_factory=list)


def summarize_shadow_certification(
    batches: Sequence[EvidenceClaimBatch],
) -> dict[str, ProviderCertificationSummary]:
    by_source: dict[str, list] = {}
    source_roles: dict[str, SourceRole] = {}

    for batch in batches:
        source_key = batch.source_key
        if source_key not in by_source:
            by_source[source_key] = []
        for claim in batch.claims:
            by_source[source_key].append(claim)
            source_roles[source_key] = claim.source.role

    summaries: dict[str, ProviderCertificationSummary] = {}
    for source_key, claims in by_source.items():
        real_count = 0
        docs_count = 0
        synth_count = 0
        for claim in claims:
            if claim.proof_level in {
                ProofLevel.REAL_LIVE_API_PROOF,
                ProofLevel.REAL_ACCEPTED_ARTIFACT_PROOF,
                ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
                ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
            }:
                real_count += 1
            elif claim.proof_level == ProofLevel.DOCS_CAPABILITY_ONLY:
                docs_count += 1
            elif claim.proof_level == ProofLevel.SYNTHETIC_CONTRACT_PROOF:
                synth_count += 1
            else:
                docs_count += 1

        role = source_roles.get(source_key)
        reasons = ["manual authorization required", "shadow-only certification phase"]
        if role in {
            SourceRole.EXPERIMENTAL_PROBE,
            SourceRole.LATER_PROVIDER_CANDIDATE,
            SourceRole.REJECTED_OR_DEFERRED,
        }:
            reasons.append(f"source role {role} is experimental, deferred or rejected")

        summaries[source_key] = ProviderCertificationSummary(
            source_key=source_key,
            real_claim_count=real_count,
            docs_only_count=docs_count,
            synthetic_count=synth_count,
            selectable_for_production=False,
            missing_authorization_reasons=reasons,
        )

    return summaries
