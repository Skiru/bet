from __future__ import annotations

from dataclasses import dataclass

from bet.enrichment.football_data_foundation.kernel.contracts import (
    FactType,
    ProofLevel,
    SourceRole,
)


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
    current_fact_types: tuple[FactType, ...] = (
        FactType.MATCH_STATUS,
        FactType.SCORE,
        FactType.STANDINGS,
    )
    source_role_priority: tuple[SourceRole, ...] = (
        SourceRole.CURRENT_LIVE_BENCHMARK,
        SourceRole.CURRENT_LIVE,
        SourceRole.CURRENT_REFERENCE,
        SourceRole.CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW,
        SourceRole.REFERENCE_METADATA_SHADOW,
        SourceRole.REFERENCE_IDENTITY,
        SourceRole.HISTORICAL_DEEP,
        SourceRole.DEPENDENCY_REPLAY,
        SourceRole.OPTIONAL_LIBRARY_BRIDGE,
    )
    proof_level_priority: tuple[ProofLevel, ...] = (
        ProofLevel.REAL_ACCEPTED_ARTIFACT_PROOF,
        ProofLevel.REAL_LIVE_API_PROOF,
        ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
        ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
    )
    context_fact_types: tuple[FactType, ...] = (
        FactType.FIXTURE_IDENTITY,
        FactType.TEAM_FORM,
        FactType.HISTORICAL_FORM_H2H,
        FactType.PLAYER_AVAILABILITY,
        FactType.LINEUP,
        FactType.MATCH_EVENT,
        FactType.MATCH_STATISTIC,
        FactType.XG,
        FactType.SHOT,
        FactType.THREE_SIXTY_FRAME,
        FactType.ODDS_REFERENCE,
        FactType.TEAM_RATING,
        FactType.PLAYER_DATA_CONTEXT,
        FactType.HIGHLIGHT,
        FactType.PREDICTION_REFERENCE,
        FactType.HISTORICAL_PRIOR,
        FactType.REFERENCE_SCHEDULE,
        FactType.REFERENCE_RESULT,
        FactType.METADATA,
    )
