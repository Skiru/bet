from __future__ import annotations

from typing import Any

from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.access import (
    has_dependency,
)
from bet.enrichment.football_data_foundation.connector_kernel.pagination import (
    PaginationModel,
)
from bet.enrichment.football_data_foundation.connector_kernel.results import (
    build_status_result,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus


class FiveThirtyEightConnector(BaseConnector):
    provider = "soccerdata"
    source_family = "soccerdata"
    source_class = "FiveThirtyEight"
    supported_operations = ()
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
        if not has_dependency("soccerdata"):
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "dependency_missing",
                {"dependency": "soccerdata"},
            )

        try:
            import soccerdata as sd

            if hasattr(sd, "FiveThirtyEight"):
                available_methods = sorted(
                    name
                    for name, value in sd.FiveThirtyEight.__dict__.items()
                    if callable(value) and name.startswith("read_")
                )
            else:
                available_methods = []
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "fivethirtyeight_introspection_failed",
                {"error": str(exc)},
            )

        return build_status_result(
            self,
            operation,
            SourceResultStatus.NOT_SUPPORTED,
            "fivethirtyeight_unavailable",
            {
                "reason": "Installed soccerdata does not expose FiveThirtyEight in this environment.",
                "available_methods": available_methods,
            },
        )
