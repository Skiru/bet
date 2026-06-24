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
    build_success_result,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus


class StatsBombPyBridge(BaseConnector):
    provider = "statsbombpy"
    source_family = "open_reference"
    source_class = "StatsBombPy"
    supported_operations = ("competitions",)
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
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "dependency_missing",
                {
                    "dependency": "statsbombpy",
                    "reason": (
                        "statsbombpy is an optional dependency and is currently absent."
                    ),
                },
            )

        if operation not in self.supported_operations:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "operation_not_supported",
            )

        try:
            from statsbombpy import sb

            raw_payload = sb.competitions(fmt=kwargs.get("fmt", "dict"))
            return build_success_result(
                self,
                operation,
                "canonical_event_team_identity",
                raw_payload,
                request_identity="statsbombpy.sb.competitions",
                parser_diagnostics={"scope": kwargs.get("scope", "global")},
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "statsbombpy_bridge_failed",
                {"error": str(exc)},
            )
