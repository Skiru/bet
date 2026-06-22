from __future__ import annotations

from dataclasses import dataclass
from bet.enrichment.football_data_foundation.kernel.contracts import ProofLevel, SourceRole, FactType


@dataclass(frozen=True)
class FusionPolicy:
    excluded_proof_levels: tuple[ProofLevel, ...] = (
        ProofLevel.DOCS_CAPABILITY_ONLY,
        ProofLevel.SYNTHETIC_CONTRACT_PROOF,
        ProofLevel.NO_PROOF,
    )
    excluded_source_roles: tuple[SourceRole, ...] = (
        SourceRole.EXPERIMENTAL_PROBE,
        SourceRole.LATER_PROVIDER_CANDIDATE,
        SourceRole.REJECTED_OR_DEFERRED,
    )
    required_fact_types: tuple[FactType, ...] = (
        FactType.FIXTURE_IDENTITY,
        FactType.MATCH_STATUS,
        FactType.SCORE,
    )

# Line-endings normalization proof
