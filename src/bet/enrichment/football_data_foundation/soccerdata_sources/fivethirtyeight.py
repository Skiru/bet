from __future__ import annotations
from typing import Any, Sequence
from datetime import datetime, timezone
import pandas as pd
from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.access import AccessRequirement
from bet.enrichment.football_data_foundation.connector_kernel.pagination import PaginationModel
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

class FiveThirtyEightConnector(BaseConnector):
    provider = "soccerdata"
    source_family = "soccerdata"
    source_class = "FiveThirtyEight"
    supported_operations = ("fetch_predictions",)
    supported_capabilities = ()
    access_requirements = ()
    dependency_requirements = ("soccerdata",)
    transport_type = "official_api"
    pagination_model = PaginationModel.NO_PAGINATION
    cache_policy = "negative_and_positive_cache"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        # Return NOT_SUPPORTED / BROKEN_OR_DRIFTED with diagnostic details because FiveThirtyEight is retired/absent
        return SourceOperationResult(
            status=SourceResultStatus.NOT_SUPPORTED,
            error_code="fivethirtyeight_retired",
            parser_diagnostics={
                "reason": "FiveThirtyEight stopped sports projections and is not supported in this version of soccerdata",
                "source_state": "BROKEN_OR_DRIFTED"
            }
        )
