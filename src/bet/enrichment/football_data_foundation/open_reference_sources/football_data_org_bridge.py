from __future__ import annotations
from typing import Any, Mapping
from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.pagination import PaginationModel
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

class FootballDataOrgBridge(BaseConnector):
    provider = "football-data"
    source_family = "open_reference"
    source_class = "FootballDataOrg"
    supported_operations = ("fetch_fixtures",)
    supported_capabilities = ("current_discovery",)
    access_requirements = ()
    dependency_requirements = ()
    transport_type = "official_api"
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
            
        try:
            from bet.api_clients.football_data_org import FootballDataOrgClient
            from bet.api_clients.rate_limiter import RateLimiter
            
            # Retrieve or instantiate the existing client
            client = kwargs.get("client")
            if not client:
                client = FootballDataOrgClient(rate_limiter=RateLimiter())
                client.api_key = kwargs.get("api_key", "dummy_key")
                
            date_str = kwargs.get("date", "2026-05-24")
            res = client.get_fixtures_result(date_str)
            return res
            
        except Exception as e:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                error_code="football_data_org_bridge_failed",
                parser_diagnostics={"error": str(e)}
            )
