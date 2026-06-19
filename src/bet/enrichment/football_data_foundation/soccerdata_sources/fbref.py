from __future__ import annotations
from typing import Any, Sequence
from datetime import datetime, timezone
import pandas as pd
from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.access import AccessRequirement
from bet.enrichment.football_data_foundation.connector_kernel.pagination import PaginationModel
from bet.enrichment.football_data_foundation.connector_kernel.evidence import EvidencePackager
from bet.enrichment.football_data_foundation.connector_kernel.normalization import RecordNormalizer
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

class FBrefConnector(BaseConnector):
    provider = "soccerdata"
    source_family = "soccerdata"
    source_class = "FBref"
    supported_operations = ("fetch_team_stats",)
    supported_capabilities = ("fixture_team_statistics",)
    access_requirements = ()
    dependency_requirements = ("soccerdata",)
    transport_type = "metadata_api"
    pagination_model = PaginationModel.SEASON_SCOPE
    cache_policy = "negative_and_positive_cache"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        if operation not in self.supported_operations:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_SUPPORTED,
                error_code="operation_not_supported"
            )
            
        try:
            import soccerdata as sd
            if kwargs.get("mock_data") is not None:
                df = kwargs["mock_data"]
            else:
                fbref = sd.FBref(**kwargs.get("init_kwargs", {}))
                # FBref read_team_season_stats expects league/season/stat_type
                df = fbref.read_team_season_stats(
                    league=kwargs.get("league", "ENG-Premier League"),
                    season=kwargs.get("season", 2024),
                    stat_type=kwargs.get("stat_type", "standard")
                )
                
            normalizer = RecordNormalizer({
                "Squad": "team_name",
                "Gls": "goals_scored",
                "Ast": "assists"
            })
            normalized_records = normalizer.normalize(df)
            
            packager = EvidencePackager()
            evidence = packager.create_package(
                provider=self.provider,
                source_family=self.source_family,
                source_class=self.source_class,
                operation=operation,
                capability="fixture_team_statistics",
                scope=kwargs.get("scope", "league"),
                request_identity="soccerdata.FBref.read_team_season_stats",
                raw_payload=df,
                normalized_records=normalized_records,
                pagination_model=str(self.pagination_model)
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=normalized_records,
                provider=self.provider,
                operation=operation,
                request_identity="soccerdata.FBref.read_team_season_stats",
                parser_version="football_foundation_v1",
                normalization_version="football_foundation_v1",
                schema_fingerprint=evidence.schema_fingerprint,
                bundle_id=evidence.evidence_id
            )
            
        except Exception as e:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                error_code="fbref_fetch_failed",
                parser_diagnostics={"error": str(e)}
            )
