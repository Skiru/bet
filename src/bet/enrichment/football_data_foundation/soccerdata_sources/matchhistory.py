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


class MatchHistoryConnector(BaseConnector):
    provider = "soccerdata"
    source_family = "soccerdata"
    source_class = "MatchHistory"
    supported_operations = ("read_games",)
    supported_capabilities = ("h2h_head_to_head",)
    access_requirements = ()
    dependency_requirements = ("soccerdata",)
    transport_type = "metadata_api"
    pagination_model = PaginationModel.SEASON_SCOPE
    cache_policy = "negative_and_positive_cache"
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

                init_kwargs = dict(kwargs.get("init_kwargs", {}))
                leagues = init_kwargs.get("leagues")
                if leagues:
                    # Explicit alias mapping dictionary
                    mapping = {
                        "ENG-Premier League": "ENG-Premier League",
                        "Premier League": "ENG-Premier League",
                        "EPL": "ENG-Premier League",
                        "ENG-Premier": "ENG-Premier League",
                        "ESP-La Liga": "ESP-La Liga",
                        "La Liga": "ESP-La Liga",
                        "FRA-Ligue 1": "FRA-Ligue 1",
                        "Ligue 1": "FRA-Ligue 1",
                        "GER-Bundesliga": "GER-Bundesliga",
                        "Bundesliga": "GER-Bundesliga",
                        "ITA-Serie A": "ITA-Serie A",
                        "Serie A": "ITA-Serie A",
                    }
                    if isinstance(leagues, str):
                        mapped = mapping.get(leagues) or mapping.get(leagues.strip())
                        if mapped:
                            init_kwargs["leagues"] = mapped
                        else:
                            try:
                                avail = sd.MatchHistory.available_leagues()
                            except Exception:
                                avail = [
                                    "ENG-Premier League",
                                    "ESP-La Liga",
                                    "FRA-Ligue 1",
                                    "GER-Bundesliga",
                                    "ITA-Serie A",
                                ]
                            if leagues not in avail:
                                return build_status_result(
                                    self,
                                    operation,
                                    SourceResultStatus.NOT_SUPPORTED,
                                    "unresolved_league_alias",
                                    {
                                        "error": f"League alias '{leagues}' cannot be resolved safely.",
                                        "available_leagues": avail,
                                    },
                                )
                source = sd.MatchHistory(**init_kwargs)

            method = getattr(source, operation, None)
            if method is None:
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.NOT_SUPPORTED,
                    "documented_method_unavailable",
                    {"method": operation},
                )

            raw_payload = method()
            return build_success_result(
                self,
                operation,
                "h2h_head_to_head",
                raw_payload,
                request_identity=f"soccerdata.MatchHistory.{operation}",
                parser_diagnostics={"scope": kwargs.get("scope", "league")},
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "matchhistory_read_failed",
                {"error": str(exc)},
            )
