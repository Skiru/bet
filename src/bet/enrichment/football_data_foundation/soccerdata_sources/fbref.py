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


class FBrefConnector(BaseConnector):
    provider = "soccerdata"
    source_family = "soccerdata"
    source_class = "FBref"
    supported_operations = (
        "read_leagues",
        "read_seasons",
        "read_schedule",
        "read_team_season_stats",
        "read_team_match_stats",
        "read_player_season_stats",
        "read_player_match_stats",
        "read_lineup",
        "read_events",
    )
    supported_capabilities = (
        "current_discovery",
        "standings_competition_context",
        "fixture_team_statistics",
        "confirmed_lineups",
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
        "read_leagues": "standings_competition_context",
        "read_seasons": "standings_competition_context",
        "read_schedule": "current_discovery",
        "read_team_season_stats": "fixture_team_statistics",
        "read_team_match_stats": "fixture_team_statistics",
        "read_player_season_stats": "fixture_team_statistics",
        "read_player_match_stats": "fixture_team_statistics",
        "read_lineup": "confirmed_lineups",
        "read_events": "fixture_team_statistics",
    }
    _ALLOWED_STAT_TYPES = {
        "read_team_season_stats": {
            "standard",
            "keeper",
            "shooting",
            "playing_time",
            "misc",
        },
        "read_team_match_stats": {"schedule", "keeper", "shooting", "misc"},
        "read_player_season_stats": {
            "standard",
            "shooting",
            "playing_time",
            "keeper",
            "misc",
        },
        "read_player_match_stats": {"summary", "keepers"},
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
            init_kwargs = dict(kwargs.get("init_kwargs", {}))
            if "leagues" in kwargs and "leagues" not in init_kwargs:
                init_kwargs["leagues"] = kwargs["leagues"]
            if "seasons" in kwargs and "seasons" not in init_kwargs:
                init_kwargs["seasons"] = kwargs["seasons"]

            if "source_factory" in kwargs:
                source = kwargs["source_factory"](**init_kwargs)
            elif "source" in kwargs:
                source = kwargs["source"]
            else:
                import soccerdata as sd

                source = sd.FBref(**init_kwargs)

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
                "split_up_big5",
                "force_cache",
                "stat_type",
                "opponent_stats",
                "team",
                "match_id",
            ):
                if key in kwargs:
                    method_kwargs[key] = kwargs[key]

            if operation in self._ALLOWED_STAT_TYPES:
                stat_type = method_kwargs.get(
                    "stat_type",
                    "summary" if operation == "read_player_match_stats" else "standard",
                )
                if stat_type not in self._ALLOWED_STAT_TYPES[operation]:
                    return build_status_result(
                        self,
                        operation,
                        SourceResultStatus.NOT_SUPPORTED,
                        "invalid_stat_type",
                        {
                            "stat_type": stat_type,
                            "allowed_stat_types": sorted(
                                self._ALLOWED_STAT_TYPES[operation]
                            ),
                        },
                    )

            raw_payload = method(**method_kwargs)
            return build_success_result(
                self,
                operation,
                self._CAPABILITIES[operation],
                raw_payload,
                request_identity=f"soccerdata.FBref.{operation}",
                parser_diagnostics={"scope": kwargs.get("scope", "league")},
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "fbref_read_failed",
                {"error": str(exc)},
            )
