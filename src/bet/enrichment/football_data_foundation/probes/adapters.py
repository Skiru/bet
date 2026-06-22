from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from bet.enrichment.football_data_foundation.kernel import (
    EvidenceClaimBatch,
    FactType,
    ProofLevel,
    ProviderCapabilityError,
    SourceDescriptor,
    SourceRole,
)
from bet.enrichment.football_data_foundation.providers._helpers import docs_only_batch


class ExperimentalProbeAdapter:
    VERSION = "prototype-v2"
    source_key = "experimental-probe"
    display_name = "Experimental Probe"
    fact_type = FactType.MATCH_STATISTIC

    def adapter_name(self) -> str:
        return self.__class__.__name__

    def adapter_version(self) -> str:
        return self.VERSION

    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key=self.source_key,
            display_name=self.display_name,
            role=SourceRole.EXPERIMENTAL_PROBE,
            requires_credentials=False,
            supports_live=False,
            supports_historical=False,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(ProofLevel.DOCS_CAPABILITY_ONLY, ProofLevel.SYNTHETIC_CONTRACT_PROOF, ProofLevel.NO_PROOF, ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF),
            forbidden_fact_types=(),
            notes=("Deferred experimental probe; never production/selectable without explicit replay proof and certification.",),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"experimental": True, "blind_live_scraping": False, "production_selectable": False}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return docs_only_batch(self, self.fact_type)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        raise ProviderCapabilityError(f"{self.source_key} has no real replay proof in Pass 1")

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        raise ProviderCapabilityError(f"{self.source_key} cannot fetch live in Pass 1")


class FotMobProbeAdapter(ExperimentalProbeAdapter):
    source_key = "fotmob-probe"
    display_name = "FotMob rich unofficial probe"
    fact_type = FactType.MATCH_STATISTIC


class SofascoreRichProbeAdapter(ExperimentalProbeAdapter):
    source_key = "sofascore-rich-probe"
    display_name = "SofaScore rich unofficial probe"
    fact_type = FactType.MATCH_STATISTIC


class ScraperFCSofascoreBridgeAdapter(ExperimentalProbeAdapter):
    source_key = "scraperfc-sofascore-bridge"
    display_name = "ScraperFC SofaScore bridge"
    fact_type = FactType.MATCH_STATISTIC


def all_probe_adapters() -> tuple[ExperimentalProbeAdapter, ...]:
    return (FotMobProbeAdapter(), SofascoreRichProbeAdapter(), ScraperFCSofascoreBridgeAdapter())
