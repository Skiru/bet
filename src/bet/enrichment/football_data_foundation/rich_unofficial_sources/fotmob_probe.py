from __future__ import annotations

from typing import Any

from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.pagination import (
    PaginationModel,
)
from bet.enrichment.football_data_foundation.connector_kernel.results import (
    build_status_result,
    normalize_payload_records,
)
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
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "operation_not_supported",
            )

        fixture_data = kwargs.get("fixture_data")
        if fixture_data is not None:
            return SourceOperationResult(
                status=SourceResultStatus.VALID_EMPTY,
                provider=self.provider,
                operation=operation,
                request_identity="FotMobProbe.fixture_only_normalizer",
                parser_diagnostics={
                    "reason": "fixture_only_probe_not_selectable",
                    "normalized_preview_rows": len(normalize_payload_records(fixture_data)),
                },
            )

        return build_status_result(
            self,
            operation,
            SourceResultStatus.NOT_SUPPORTED,
            "safe_client_unavailable",
            {"reason": "No safe installed dependency or existing client is available."},
        )
