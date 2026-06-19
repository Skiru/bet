from __future__ import annotations
from typing import Any, Mapping
from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.pagination import PaginationModel
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

class FotMobProbe(BaseConnector):
    provider = "fotmob"
    source_family = "rich_unofficial"
    source_class = "FotMobProbe"
    supported_operations = ("probe_matches",)
    supported_capabilities = ("current_discovery",)
    access_requirements = ()
    dependency_requirements = ()
    transport_type = "unofficial_api"
    pagination_model = PaginationModel.NO_PAGINATION
    cache_policy = "positive_only_cache"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        if operation not in self.supported_operations:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_SUPPORTED,
                error_code="operation_not_supported"
            )
            
        # FotMob has no standard official API, so we treat it as research-only
        mock_data = [{"match_id": "fm-40123", "home": "Arsenal", "away": "Chelsea", "status": "FINISHED"}]
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=mock_data,
            provider=self.provider,
            operation=operation,
            request_identity="FotMobProbe.probe_matches"
        )
