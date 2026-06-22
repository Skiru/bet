from __future__ import annotations

import csv
import json
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
from bet.enrichment.football_data_foundation.providers._helpers import (
    docs_only_batch,
    replay_claim,
    synthetic_batch,
)


class BaseAdapter:
    VERSION = "football-foundation-pass2"

    def adapter_name(self) -> str:
        return self.__class__.__name__

    def adapter_version(self) -> str:
        return self.VERSION

    def fetch_shadow_live(self, query: Mapping[str, Any]) -> EvidenceClaimBatch:
        raise ProviderCapabilityError(
            f"{self.source_descriptor().source_key} is not a live source"
        )


class StatsBombOpenDataAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="statsbomb-open-data",
            display_name="StatsBomb Open Data",
            role=SourceRole.HISTORICAL_DEEP,
            requires_credentials=False,
            supports_live=False,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
            ),
            forbidden_fact_types=(),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "local_files": [
                "competitions.json",
                "events/*.json",
                "lineups",
                "three-sixty",
            ],
            "current_truth": False,
        }

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return synthetic_batch(self, FactType.MATCH_EVENT)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        events = []
        for path in sorted((input_path / "events").glob("*.json")):
            events.extend(json.loads(path.read_text()))
        shot_count = sum(1 for event in events if event.get("type") == "Shot")
        xg_sum = round(
            sum(
                float(event.get("xg", 0.0))
                for event in events
                if event.get("type") == "Shot"
            ),
            4,
        )
        has_360 = (input_path / "three-sixty").exists()
        return replay_claim(
            self,
            FactType.MATCH_EVENT,
            {
                "event_count": len(events),
                "shot_count": shot_count,
                "xg_sum": xg_sum,
                "has_three_sixty": has_360,
            },
            proof_level=ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
            confidence=0.8,
            freshness_reason="local open data historical proof",
        )


class StatsBombPyBridgeAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="statsbombpy",
            display_name="statsbombpy optional bridge",
            role=SourceRole.OPTIONAL_LIBRARY_BRIDGE,
            requires_credentials=False,
            supports_live=False,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.NO_PROOF,
            ),
            forbidden_fact_types=(),
            notes=("Optional bridge only; no hard dependency in Pass 1.",),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"optional_import": "statsbombpy", "hard_dependency": False}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return docs_only_batch(self, FactType.MATCH_EVENT)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        raise ProviderCapabilityError(
            "statsbombpy bridge is optional/docs-only in Pass 1"
        )


class OpenFootballAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="openfootball",
            display_name="OpenFootball / football.db",
            role=SourceRole.REFERENCE_IDENTITY,
            requires_credentials=False,
            supports_live=False,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
            ),
            forbidden_fact_types=(
                FactType.XG,
                FactType.SHOT,
                FactType.LINEUP,
                FactType.MATCH_STATISTIC,
                FactType.THREE_SIXTY_FRAME,
            ),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"format": "Football.TXT-like", "reference_only": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return synthetic_batch(self, FactType.REFERENCE_RESULT)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        lines = [
            line
            for line in input_path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        return replay_claim(
            self,
            FactType.REFERENCE_RESULT,
            {"result_line_count": len(lines)},
            proof_level=ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
            fixture_id=None,
        )


class KaggleEuropeanSoccerAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="kaggle-european-soccer",
            display_name="Kaggle European Soccer Database",
            role=SourceRole.HISTORICAL_DEEP,
            requires_credentials=False,
            supports_live=False,
            supports_historical=True,
            supports_reference=True,
            supports_replay=True,
            allowed_proof_levels=(
                ProofLevel.DOCS_CAPABILITY_ONLY,
                ProofLevel.SYNTHETIC_CONTRACT_PROOF,
                ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
            ),
            forbidden_fact_types=(FactType.THREE_SIXTY_FRAME,),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"historical_prior": True, "temporal_decay_required": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return synthetic_batch(self, FactType.HISTORICAL_PRIOR)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        rows = list(csv.DictReader(input_path.read_text().splitlines()))
        return replay_claim(
            self,
            FactType.HISTORICAL_PRIOR,
            {"match_count": len(rows), "temporal_decay_required": True},
            proof_level=ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
            fixture_id=None,
        )


class SportDBOpenSourceToolingAdapter(BaseAdapter):
    def source_descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_key="sportdb-open-source-tooling",
            display_name="sport.db open-source tooling",
            role=SourceRole.OPTIONAL_LIBRARY_BRIDGE,
            requires_credentials=False,
            supports_live=False,
            supports_historical=True,
            supports_reference=True,
            supports_replay=False,
            allowed_proof_levels=(ProofLevel.DOCS_CAPABILITY_ONLY, ProofLevel.NO_PROOF),
            forbidden_fact_types=(
                FactType.XG,
                FactType.SHOT,
                FactType.MATCH_STATISTIC,
                FactType.THREE_SIXTY_FRAME,
            ),
            notes=(
                "Do not confuse with SportDB.dev API; optional tooling for Football.TXT style datasets.",
            ),
        )

    def capabilities(self) -> Mapping[str, Any]:
        return {"optional_tooling": True, "not_provider_api": True}

    def build_contract_probe(self) -> EvidenceClaimBatch:
        return docs_only_batch(self, FactType.METADATA)

    def normalize_replay_fixture(self, input_path: Path) -> EvidenceClaimBatch:
        raise ProviderCapabilityError("sport.db tooling is docs-only in Pass 1")
