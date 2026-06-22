from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from bet.enrichment.football_data_foundation.kernel import (
    EvidenceClaimBatch,
    FactType,
    ProviderCapabilityError,
    SourceDescriptor,
    SourceRole,
    ProofLevel,
)
from bet.enrichment.football_data_foundation.providers._helpers import (
    docs_only_batch,
    read_json,
    replay_claim,
    synthetic_batch,
)


class SoccerDataReplayAdapter:
    VERSION = "football-foundation-pass2"
    source_key = "soccerdata-generic"
    display_name = "soccerdata generic"
    fact_type = FactType.HISTORICAL_PRIOR
    docs_only = False

    def adapter_name(self) -> str:
        return self.__class__.__name__

    def adapter_version(self) -> str:
        return self.VERSION

    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key=self.source_key,
            display_name=self.display_name,
            role=SourceRole.DEPENDENCY_REPLAY,
            requires_credentials=False,
            supports_live=False,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
                ProofLevel.NO_PROOF,
            ),
            forbidden_fact_types=(),
            notes=(
                "soccerdata is replay/cached dependency layer only; no blind live scraping.",
            ),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "library": "soccerdata",
            "blind_live_scraping": False,
            "hard_dependency": False,
            "source": self.source_key,
        }

    def build_contract_probe(self) -> EvidenceClaimBatch:
        if self.docs_only:
            return docs_only_batch(self, self.fact_type)
        return synthetic_batch(self, self.fact_type)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        if self.docs_only:
            raise ProviderCapabilityError(
                f"{self.source_key} is docs-only until sanitized replay fixture exists"
            )
        data = read_json(input_path)
        if not data.get("sanitized"):
            raise ProviderCapabilityError("soccerdata replay fixture must be sanitized")
        value = dict(data.get("claim", {}))
        if self.source_key == "soccerdata-matchhistory":
            value["odds_reference_not_decision"] = True
        if self.source_key == "soccerdata-fivethirtyeight":
            value["staleness_risk"] = "legacy_or_provider_deprecated_check_required"
        return replay_claim(self, self.fact_type, value)

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        raise ProviderCapabilityError(
            "soccerdata wrappers are replay-only in this workflow"
        )


class SoccerDataClubEloAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-clubelo"
    display_name = "soccerdata ClubElo"
    fact_type = FactType.TEAM_RATING


class SoccerDataESPNAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-espn"
    display_name = "soccerdata ESPN"
    fact_type = FactType.REFERENCE_RESULT


class SoccerDataFBrefAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-fbref"
    display_name = "soccerdata FBref"
    fact_type = FactType.MATCH_STATISTIC


class SoccerDataFiveThirtyEightAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-fivethirtyeight"
    display_name = "soccerdata FiveThirtyEight"
    fact_type = FactType.HISTORICAL_PRIOR


class SoccerDataMatchHistoryAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-matchhistory"
    display_name = "soccerdata MatchHistory / Football-Data.co.uk"
    fact_type = FactType.ODDS_REFERENCE


class SoccerDataSofascoreAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-sofascore"
    display_name = "soccerdata Sofascore"
    fact_type = FactType.MATCH_STATISTIC


class SoccerDataSoFIFAAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-sofifa"
    display_name = "soccerdata SoFIFA"
    fact_type = FactType.PLAYER_DATA_CONTEXT


class SoccerDataUnderstatAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-understat"
    display_name = "soccerdata Understat"
    fact_type = FactType.XG


class SoccerDataWhoScoredAdapter(SoccerDataReplayAdapter):
    source_key = "soccerdata-whoscored"
    display_name = "soccerdata WhoScored"
    fact_type = FactType.MATCH_STATISTIC
    docs_only = True


def all_soccerdata_adapters() -> tuple[SoccerDataReplayAdapter, ...]:
    return (
        SoccerDataClubEloAdapter(),
        SoccerDataESPNAdapter(),
        SoccerDataFBrefAdapter(),
        SoccerDataFiveThirtyEightAdapter(),
        SoccerDataMatchHistoryAdapter(),
        SoccerDataSofascoreAdapter(),
        SoccerDataSoFIFAAdapter(),
        SoccerDataUnderstatAdapter(),
        SoccerDataWhoScoredAdapter(),
    )
