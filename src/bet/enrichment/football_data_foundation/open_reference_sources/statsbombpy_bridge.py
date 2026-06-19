from __future__ import annotations
from typing import Any, Mapping
from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.access import AccessRequirement, has_dependency
from bet.enrichment.football_data_foundation.connector_kernel.pagination import PaginationModel
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

class StatsBombPyBridge(BaseConnector):
    provider = "statsbombpy"
    source_family = "statsbomb"
    source_class = "statsbombpy_bridge"
    supported_operations = ("fetch_competitions",)
    supported_capabilities = ()
    access_requirements = ()
    dependency_requirements = ("statsbombpy",)
    transport_type = "official_api"
    pagination_model = PaginationModel.NO_PAGINATION
    cache_policy = "positive_only_cache"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        if not has_dependency("statsbombpy"):
            return SourceOperationResult(
                status=SourceResultStatus.NOT_SUPPORTED,
                error_code="DEPENDENCY_MISSING",
                parser_diagnostics={"dependency": "statsbombpy", "reason": "statsbombpy is an optional dependency and is currently absent."}
            )
            
        if operation not in self.supported_operations:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_SUPPORTED,
                error_code="operation_not_supported"
            )
            
        try:
            from statsbombpy import sb
            # Use mock_data if provided
            if kwargs.get("mock_data") is not None:
                raw_data = kwargs["mock_data"]
            else:
                raw_data = sb.competitions(fmt="dict")
                
            # Convert to normalized records list
            normalized_records = []
            for comp_id, item in raw_data.items():
                normalized_records.append({
                    "competition_id": str(comp_id),
                    "country_name": str(item.get("country_name", "UNKNOWN")),
                    "competition_name": str(item.get("competition_name", "UNKNOWN")),
                    "season_name": str(item.get("season_name", "UNKNOWN"))
                })
                
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=normalized_records,
                provider=self.provider,
                operation=operation,
                request_identity="statsbombpy.sb.competitions"
            )
        except Exception as e:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                error_code="statsbombpy_bridge_failed",
                parser_diagnostics={"error": str(e)}
            )
