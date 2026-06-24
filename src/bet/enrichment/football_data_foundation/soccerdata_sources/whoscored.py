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


class WhoScoredConnector(BaseConnector):
    provider = "soccerdata"
    source_family = "soccerdata"
    source_class = "WhoScored"
    supported_operations = (
        "read_schedule",
        "read_missing_players",
        "read_events",
    )
    supported_capabilities = (
        "current_discovery",
        "injuries_suspensions",
        "fixture_team_statistics",
    )
    access_requirements = ()
    dependency_requirements = ("soccerdata",)
    transport_type = "browser_scraper"
    pagination_model = PaginationModel.SEASON_SCOPE
    cache_policy = "negative_and_positive_cache"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    _CAPABILITIES = {
        "read_schedule": "current_discovery",
        "read_missing_players": "injuries_suspensions",
        "read_events": "fixture_team_statistics",
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

                source = sd.WhoScored(**dict(kwargs.get("init_kwargs", {})))

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
            for key in (
                "match_id",
                "force_cache",
                "live",
                "output_fmt",
                "retry_missing",
                "on_error",
            ):
                if key in kwargs:
                    method_kwargs[key] = kwargs[key]

            raw_payload = method(**method_kwargs)
            return build_success_result(
                self,
                operation,
                self._CAPABILITIES[operation],
                raw_payload,
                request_identity=f"soccerdata.WhoScored.{operation}",
                parser_diagnostics={"scope": kwargs.get("scope", "league")},
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "whoscored_read_failed",
                {"error": str(exc)},
            )
