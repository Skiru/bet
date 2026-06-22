from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Mapping

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
from bet.enrichment.football_data_foundation.kernel.errors import (
    CredentialsMissingError,
    ProviderCapabilityError,
)
from bet.enrichment.football_data_foundation.transport.http_json import HttpJsonTransport


class SportDBLiveClient:
    def __init__(self, transport: Any = None):
        self.transport = transport or HttpJsonTransport()
        self.source_key = "sportdb"
        self.adapter_name = "SportDBLiveClient"
        self.adapter_version = "football-foundation-pass2"

    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key=self.source_key,
            display_name="SportDB Live Client",
            role=SourceRole.CURRENT_LIVE,
            requires_credentials=True,
            supports_live=True,
            supports_historical=False,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
                ProofLevel.REAL_LIVE_API_PROOF,
            ),
            forbidden_fact_types=(
                FactType.HISTORICAL_PRIOR,
                FactType.THREE_SIXTY_FRAME,
                FactType.ODDS_REFERENCE,
            ),
        )

    def fetch_match_stats(self, fixture_id: str) -> EvidenceClaimBatch:
        api_key = os.getenv("SPORTDB_API_KEY")
        if not api_key:
            raise CredentialsMissingError("SPORTDB_API_KEY env variable is required")

        headers = {"X-API-Key": api_key, "Accept": "application/json"}
        url = f"https://api.sportdb.dev/v1/fixtures/{fixture_id}/stats"
        
        response = self.transport.get(url, headers=headers)
        
        data = response.body
        claim_value = {
            "status": data.get("status", "FT"),
            "score_home": data.get("score_home", 0),
            "score_away": data.get("score_away", 0),
            "shots_home": data.get("shots_home", 0),
            "shots_away": data.get("shots_away", 0),
        }
        
        observed_at = datetime.now(UTC)
        
        claim = EvidenceClaim(
            source=self.source_descriptor(),
            proof_level=ProofLevel.REAL_LIVE_API_PROOF,
            fact_type=FactType.MATCH_STATISTIC,
            identity=ProviderIdentity(
                source_key=self.source_key,
                provider_fixture_id=fixture_id,
                provider_home_team_id="home-1",
                provider_away_team_id="away-1",
                normalized_home_name="Home FC",
                normalized_away_name="Away FC",
                identity_confidence=0.9,
            ),
            freshness=EvidenceFreshness(
                observed_at=observed_at,
                is_current_truth_allowed=True,
                freshness_reason="shadow contract live match stats fetch",
            ),
            payload_policy=PayloadPolicy(
                payload_hash=response.body_hash,
                payload_byte_count=response.byte_count,
                payload_record_count=response.record_count,
            ),
            claim_value=claim_value,
            confidence=0.95,
        )
        
        batch_id = EvidenceClaimBatch.deterministic_id(self.source_key, self.adapter_version, (claim,))
        return EvidenceClaimBatch(
            batch_id=batch_id,
            source_key=self.source_key,
            adapter_name=self.adapter_name,
            adapter_version=self.adapter_version,
            generated_at=observed_at,
            claims=(claim,),
        )


class FootballDataOrgLiveClient:
    def __init__(self, transport: Any = None):
        self.transport = transport or HttpJsonTransport()
        self.source_key = "football-data-org"
        self.adapter_name = "FootballDataOrgLiveClient"
        self.adapter_version = "football-foundation-pass2"

    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key=self.source_key,
            display_name="football-data.org Live Client",
            role=SourceRole.CURRENT_REFERENCE,
            requires_credentials=True,
            supports_live=True,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
                ProofLevel.REAL_LIVE_API_PROOF,
            ),
            forbidden_fact_types=(
                FactType.XG,
                FactType.SHOT,
                FactType.THREE_SIXTY_FRAME,
                FactType.MATCH_EVENT,
                FactType.PLAYER_DATA_CONTEXT,
            ),
        )

    def fetch_competition_standings(self, competition_code: str) -> EvidenceClaimBatch:
        api_key = os.getenv("FOOTBALL_DATA_API_KEY")
        if not api_key:
            raise CredentialsMissingError("FOOTBALL_DATA_API_KEY env variable is required")

        headers = {"X-Auth-Token": api_key, "Accept": "application/json"}
        url = f"https://api.football-data.org/v4/competitions/{competition_code}/standings"
        
        response = self.transport.get(url, headers=headers)
        
        data = response.body
        claim_value = {
            "competition_code": competition_code,
            "standings_count": len(data.get("standings", [])),
            "season": data.get("season", {}).get("startDate", "2025-2026"),
        }
        
        observed_at = datetime.now(UTC)
        
        claim = EvidenceClaim(
            source=self.source_descriptor(),
            proof_level=ProofLevel.REAL_LIVE_API_PROOF,
            fact_type=FactType.STANDINGS,
            identity=ProviderIdentity(
                source_key=self.source_key,
                provider_competition_id=competition_code,
            ),
            freshness=EvidenceFreshness(
                observed_at=observed_at,
                is_current_truth_allowed=True,
                freshness_reason="shadow contract live standings fetch",
            ),
            payload_policy=PayloadPolicy(
                payload_hash=response.body_hash,
                payload_byte_count=response.byte_count,
                payload_record_count=response.record_count,
            ),
            claim_value=claim_value,
            confidence=0.90,
        )
        
        batch_id = EvidenceClaimBatch.deterministic_id(self.source_key, self.adapter_version, (claim,))
        return EvidenceClaimBatch(
            batch_id=batch_id,
            source_key=self.source_key,
            adapter_name=self.adapter_name,
            adapter_version=self.adapter_version,
            generated_at=observed_at,
            claims=(claim,),
        )


class HighlightlyLiveClient:
    def __init__(self, transport: Any = None):
        self.transport = transport or HttpJsonTransport()
        self.source_key = "highlightly"
        self.adapter_name = "HighlightlyLiveClient"
        self.adapter_version = "football-foundation-pass2"

    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key=self.source_key,
            display_name="Highlightly Live Client",
            role=SourceRole.CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW,
            requires_credentials=True,
            supports_live=True,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
                ProofLevel.REAL_LIVE_API_PROOF,
            ),
            forbidden_fact_types=(FactType.THREE_SIXTY_FRAME,),
        )

    def fetch_match_statistics(self, fixture_id: str) -> EvidenceClaimBatch:
        api_key = os.getenv("HIGHLIGHTLY_API_KEY")
        if not api_key:
            raise CredentialsMissingError("HIGHLIGHTLY_API_KEY env variable is required")

        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        url = f"https://api.highlightly.com/v1/matches/{fixture_id}/stats"
        
        response = self.transport.get(url, headers=headers)
        
        data = response.body
        stats_list = data.get("stats", [])
        claim_value = {
            "stat_count": len(stats_list),
            "has_odds_reference": "odds" in data,
            "has_player_data_context": "player_stats" in data,
        }
        
        observed_at = datetime.now(UTC)
        
        claim = EvidenceClaim(
            source=self.source_descriptor(),
            proof_level=ProofLevel.REAL_LIVE_API_PROOF,
            fact_type=FactType.MATCH_STATISTIC,
            identity=ProviderIdentity(
                source_key=self.source_key,
                provider_fixture_id=fixture_id,
            ),
            freshness=EvidenceFreshness(
                observed_at=observed_at,
                is_current_truth_allowed=True,
                freshness_reason="shadow contract live match stats fetch",
            ),
            payload_policy=PayloadPolicy(
                payload_hash=response.body_hash,
                payload_byte_count=response.byte_count,
                payload_record_count=response.record_count,
            ),
            claim_value=claim_value,
            confidence=0.85,
        )
        
        batch_id = EvidenceClaimBatch.deterministic_id(self.source_key, self.adapter_version, (claim,))
        return EvidenceClaimBatch(
            batch_id=batch_id,
            source_key=self.source_key,
            adapter_name=self.adapter_name,
            adapter_version=self.adapter_version,
            generated_at=observed_at,
            claims=(claim,),
        )


class APIFootballDeferredClient:
    def __init__(self, transport: Any = None):
        self.transport = transport or HttpJsonTransport()
        self.source_key = "api-football"
        self.adapter_name = "APIFootballDeferredClient"
        self.adapter_version = "football-foundation-pass2"

    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key=self.source_key,
            display_name="API-Football Deferred Client",
            role=SourceRole.LATER_PROVIDER_CANDIDATE,
            requires_credentials=True,
            supports_live=True,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.NO_PROOF,
            ),
        )

    def fetch_match_stats(self, fixture_id: str) -> EvidenceClaimBatch:
        raise ProviderCapabilityError("API-Football live fetch is deferred and not allowed in Pass 2")


class TheSportsDBMetadataClient:
    def __init__(self, transport: Any = None):
        self.transport = transport or HttpJsonTransport()
        self.source_key = "thesportsdb"
        self.adapter_name = "TheSportsDBMetadataClient"
        self.adapter_version = "football-foundation-pass2"

    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key=self.source_key,
            display_name="TheSportsDB Metadata Client",
            role=SourceRole.REFERENCE_METADATA_SHADOW,
            requires_credentials=True,
            supports_live=False,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
            ),
            forbidden_fact_types=(
                FactType.XG,
                FactType.SHOT,
                FactType.THREE_SIXTY_FRAME,
                FactType.MATCH_STATISTIC,
            ),
        )

    def fetch_metadata(self) -> EvidenceClaimBatch:
        raise ProviderCapabilityError("TheSportsDB is metadata/reference shadow only; no live fetch allowed")

# Line-endings normalization proof
