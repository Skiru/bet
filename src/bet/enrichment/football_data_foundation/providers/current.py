from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from bet.enrichment.football_data_foundation.kernel import (
    CredentialsMissingError,
    EvidenceClaimBatch,
    FactType,
    ProofLevel,
    ProviderCapabilityError,
    SourceDescriptor,
    SourceRole,
)
from bet.enrichment.football_data_foundation.providers._helpers import (
    docs_only_batch,
    read_json,
    replay_claim,
    require_env,
    synthetic_batch,
)


class BaseAdapter:
    VERSION = "football-foundation-pass2"

    def adapter_name(self) -> str:
        return self.__class__.__name__

    def adapter_version(self) -> str:
        return self.VERSION


class ESPNAcceptedBaselineAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="espn-accepted-baseline",
            display_name="ESPN Accepted Live Baseline",
            role=SourceRole.CURRENT_LIVE_BENCHMARK,
            requires_credentials=False,
            supports_live=True,
            supports_historical=False,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(ProofLevel.REAL_ACCEPTED_ARTIFACT_PROOF, ProofLevel.SYNTHETIC_CONTRACT_PROOF),
            forbidden_fact_types=(FactType.XG, FactType.THREE_SIXTY_FRAME, FactType.ODDS_REFERENCE),
            notes=("Anchor/benchmark only; do not confuse with soccerdata-espn.",),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"role": "accepted baseline", "shadow_only": True, "do_not_reimplement_in_pass1": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return synthetic_batch(self, FactType.MATCH_STATUS)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        data = read_json(input_path)
        if not data.get("accepted_artifact"):
            raise ProviderCapabilityError("ESPN baseline replay requires accepted_artifact marker")
        return replay_claim(
            self,
            FactType.MATCH_STATUS,
            {"status": data["status"], "baseline_scope": data.get("baseline_scope", "accepted-live")},
            proof_level=ProofLevel.REAL_ACCEPTED_ARTIFACT_PROOF,
            confidence=0.9,
            freshness_reason="accepted artifact replay",
        )

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        raise ProviderCapabilityError("ESPN accepted baseline is not re-fetched in this shadow contract")


class HighlightlyAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="highlightly",
            display_name="Highlightly",
            role=SourceRole.CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW,
            requires_credentials=True,
            supports_live=True,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(ProofLevel.SYNTHETIC_CONTRACT_PROOF, ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF, ProofLevel.REAL_LIVE_API_PROOF),
            forbidden_fact_types=(FactType.THREE_SIXTY_FRAME,),
            notes=("Detailed current/recent shadow source; no production selection without certification.",),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"fact_scope": ["live_scores", "statistics", "lineups", "odds", "events", "player_data"], "credential_env": "HIGHLIGHTLY_API_KEY", "shadow_only": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return synthetic_batch(self, FactType.MATCH_STATISTIC)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        data = read_json(input_path)
        if not data.get("sanitized"):
            raise ProviderCapabilityError("Highlightly replay fixture must be sanitized")
        return replay_claim(self, FactType.MATCH_STATISTIC, {"stat_count": data.get("stat_count", 0), "has_odds_reference": bool(data.get("has_odds_reference"))})

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        require_env("HIGHLIGHTLY_API_KEY")
        raise ProviderCapabilityError("Network live fetch is credential-gated and intentionally not implemented in this pass2 implementation")


class SportDBFootballAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="sportdb",
            display_name="SportDB",
            role=SourceRole.CURRENT_LIVE,
            requires_credentials=True,
            supports_live=True,
            supports_historical=False,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(ProofLevel.DOCS_CAPABILITY_ONLY, ProofLevel.SYNTHETIC_CONTRACT_PROOF, ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF, ProofLevel.REAL_LIVE_API_PROOF),
            forbidden_fact_types=(FactType.HISTORICAL_PRIOR, FactType.THREE_SIXTY_FRAME, FactType.ODDS_REFERENCE),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"auth_header": "X-API-Key", "credential_env": "SPORTDB_API_KEY", "mcp_endpoint": "https://api.sportdb.dev/mcp/", "shadow_only": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return synthetic_batch(self, FactType.MATCH_STATUS)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        data = read_json(input_path)
        if not data.get("sanitized"):
            raise ProviderCapabilityError("SportDB replay fixture must be sanitized")
        return replay_claim(self, FactType.MATCH_STATUS, {"status": data["status"], "score_home": data.get("score_home"), "score_away": data.get("score_away")}, fixture_id=str(data.get("fixture_id", "fixture-1")))

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        require_env("SPORTDB_API_KEY")
        raise ProviderCapabilityError("Network live fetch is credential-gated and intentionally not implemented in this pass2 implementation")


class FootballDataOrgAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="football-data-org",
            display_name="football-data.org",
            role=SourceRole.CURRENT_REFERENCE,
            requires_credentials=True,
            supports_live=True,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(ProofLevel.DOCS_CAPABILITY_ONLY, ProofLevel.SYNTHETIC_CONTRACT_PROOF, ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF, ProofLevel.REAL_LIVE_API_PROOF),
            forbidden_fact_types=(FactType.XG, FactType.SHOT, FactType.THREE_SIXTY_FRAME, FactType.MATCH_EVENT, FactType.PLAYER_DATA_CONTEXT),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"auth_header": "X-Auth-Token", "credential_env": "FOOTBALL_DATA_API_KEY", "fact_scope": ["matches", "standings", "teams"], "shadow_only": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return synthetic_batch(self, FactType.STANDINGS)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        data = read_json(input_path)
        return replay_claim(self, FactType.STANDINGS, {"competition_id": data["competition_id"], "table_count": len(data.get("table", []))}, fixture_id=None)

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        require_env("FOOTBALL_DATA_API_KEY")
        raise ProviderCapabilityError("Network live fetch is credential-gated and intentionally not implemented in this pass2 implementation")


class APIFootballDeferredAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="api-football",
            display_name="API-Football / API-Sports",
            role=SourceRole.LATER_PROVIDER_CANDIDATE,
            requires_credentials=True,
            supports_live=True,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(ProofLevel.DOCS_CAPABILITY_ONLY, ProofLevel.SYNTHETIC_CONTRACT_PROOF, ProofLevel.NO_PROOF),
            forbidden_fact_types=(),
            notes=("Deferred production candidate; no real live proof allowed before its own certification pass.",),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"deferred": True, "credential_env": "API_FOOTBALL_KEY", "shadow_only": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return docs_only_batch(self, FactType.MATCH_STATUS)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        raise ProviderCapabilityError("API-Football replay is deferred to a later certified phase")

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        raise ProviderCapabilityError("API-Football is deferred; do not fetch in Pass 1")


class TheSportsDBMetadataAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="thesportsdb",
            display_name="TheSportsDB",
            role=SourceRole.REFERENCE_METADATA_SHADOW,
            requires_credentials=True,
            supports_live=False,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(ProofLevel.DOCS_CAPABILITY_ONLY, ProofLevel.SYNTHETIC_CONTRACT_PROOF, ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF),
            forbidden_fact_types=(FactType.XG, FactType.SHOT, FactType.THREE_SIXTY_FRAME, FactType.MATCH_STATISTIC),
            notes=("Metadata/reference shadow only until real replay/live proof exists.",),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"auth_header": "X-API-KEY", "metadata_reference_only": True, "shadow_only": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return synthetic_batch(self, FactType.METADATA)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        data = read_json(input_path)
        return replay_claim(self, FactType.METADATA, {"team_count": len(data.get("teams", []))}, fixture_id=None)

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        raise ProviderCapabilityError("TheSportsDB is metadata/reference shadow only in this shadow contract")
