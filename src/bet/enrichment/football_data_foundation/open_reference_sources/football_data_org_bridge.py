from __future__ import annotations

from typing import Any

from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.pagination import (
    PaginationModel,
)
from bet.enrichment.football_data_foundation.connector_kernel.results import (
    build_status_result,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus


class FootballDataOrgBridge(BaseConnector):
    provider = "football-data"
    source_family = "open_reference"
    source_class = "FootballDataOrg"
    supported_operations = ("get_fixtures_result",)
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
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "operation_not_supported",
            )

        try:
            client = kwargs.get("client")
            if client is None:
                from bet.api_clients.football_data_org import FootballDataOrgClient
                from bet.api_clients.rate_limiter import RateLimiter

                api_key = kwargs.get("api_key")
                if not api_key:
                    return build_status_result(
                        self,
                        operation,
                        SourceResultStatus.AUTHENTICATION_ERROR,
                        "missing_api_key",
                    )
                client = FootballDataOrgClient(rate_limiter=RateLimiter())
                client.api_key = api_key

            if not hasattr(client, "get_fixtures_result"):
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.NOT_SUPPORTED,
                    "client_method_missing",
                )

            date_str = kwargs.get("date")
            if not date_str:
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.PARSE_ERROR,
                    "missing_required_parameter",
                    {"required_parameter": "date"},
                )

            result = client.get_fixtures_result(date_str, kwargs.get("competition"))
            if not isinstance(result, SourceOperationResult):
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.PARSE_ERROR,
                    "unexpected_client_result_type",
                    {"result_type": type(result).__name__},
                )

            merged_diagnostics = dict(result.parser_diagnostics)
            merged_diagnostics.setdefault("bridge", self.source_class)
            merged_diagnostics.setdefault("wrapped_method", operation)
            return SourceOperationResult(
                status=result.status,
                value=result.value,
                provider=self.provider,
                operation=operation,
                request_identity=result.request_identity or f"FootballDataOrgClient.{operation}",
                evidence_refs=result.evidence_refs,
                bundle_id=result.bundle_id,
                retrieved_at=result.retrieved_at,
                provider_updated_at=result.provider_updated_at,
                valid_from=result.valid_from,
                valid_to=result.valid_to,
                http_status=result.http_status,
                error_code=result.error_code,
                retry_after_seconds=result.retry_after_seconds,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
                parser_diagnostics=merged_diagnostics,
                schema_fingerprint=result.schema_fingerprint,
                parser_version=result.parser_version,
                normalization_version=result.normalization_version,
                retryable=result.retryable,
            )
        except ImportError as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "bridge_dependency_unavailable",
                {"error": str(exc)},
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "football_data_org_bridge_failed",
                {"error": str(exc)},
            )
