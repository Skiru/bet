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


class SofascoreConnector(BaseConnector):
    provider = "soccerdata"
    source_family = "soccerdata"
    source_class = "Sofascore"
    supported_operations = (
        "read_leagues",
        "read_seasons",
        "read_league_table",
        "read_schedule",
    )
    supported_capabilities = (
        "current_discovery",
        "standings_competition_context",
    )
    access_requirements = ()
    dependency_requirements = ("soccerdata",)
    transport_type = "metadata_api"
    pagination_model = PaginationModel.SEASON_SCOPE
    cache_policy = "negative_and_positive_cache"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    _CAPABILITIES = {
        "read_leagues": "current_discovery",
        "read_seasons": "current_discovery",
        "read_league_table": "standings_competition_context",
        "read_schedule": "current_discovery",
    }

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        if operation not in self.supported_operations:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "operation_not_supported",
            )

        if not has_dependency("soccerdata"):
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "dependency_missing",
                {"dependency": "soccerdata"},
            )

        try:
            if "source" in kwargs:
                source = kwargs["source"]
            else:
                import soccerdata as sd

                source = sd.Sofascore(**dict(kwargs.get("init_kwargs", {})))

            method = getattr(source, operation, None)
            if method is None:
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.NOT_SUPPORTED,
                    "documented_method_unavailable",
                    {"method": operation},
                )

            method_kwargs = {}
            if "force_cache" in kwargs:
                method_kwargs["force_cache"] = kwargs["force_cache"]

            raw_payload = method(**method_kwargs)
            return build_success_result(
                self,
                operation,
                self._CAPABILITIES[operation],
                raw_payload,
                request_identity=f"soccerdata.Sofascore.{operation}",
                parser_diagnostics={"scope": kwargs.get("scope", "league")},
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "sofascore_read_failed",
                {"error": str(exc)},
            )
