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


class MplSoccerBridge(BaseConnector):
    provider = "mplsoccer"
    source_family = "event_model"
    source_class = "mplsoccer_bridge"
    supported_operations = ("draw_pitch",)
    supported_capabilities = ()
    access_requirements = ()
    dependency_requirements = ("mplsoccer",)
    transport_type = "computation"
    pagination_model = PaginationModel.NO_PAGINATION
    cache_policy = "always_cached"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        if operation not in self.supported_operations:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "operation_not_supported",
            )

        if not has_dependency("mplsoccer"):
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "dependency_missing",
                {"dependency": "mplsoccer"},
            )

        return build_status_result(
            self,
            operation,
            SourceResultStatus.NOT_SUPPORTED,
            "safe_execution_not_implemented",
            {
                "reason": (
                    "Bridge execution is intentionally fail-closed without a "
                    "verified adapter path."
                )
            },
        )
