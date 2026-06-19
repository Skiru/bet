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


class ScraperFCSofascoreBridge(BaseConnector):
    provider = "scraperfc"
    source_family = "rich_unofficial"
    source_class = "ScraperFCSofascore"
    supported_operations = ("read_match_stats",)
    supported_capabilities = ()
    access_requirements = ()
    dependency_requirements = ("ScraperFC",)
    transport_type = "browser_scraper"
    pagination_model = PaginationModel.NO_PAGINATION
    cache_policy = "positive_only_cache"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        if not has_dependency("ScraperFC"):
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "dependency_missing",
                {
                    "dependency": "ScraperFC",
                    "reason": (
                        "ScraperFC is an optional dependency and is currently absent."
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

        return build_status_result(
            self,
            operation,
            SourceResultStatus.NOT_SUPPORTED,
            "safe_client_unavailable",
            {
                "reason": (
                    "ScraperFC execution is intentionally disabled in this foundation."
                )
            },
        )
