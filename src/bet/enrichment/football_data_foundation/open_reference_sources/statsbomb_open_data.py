from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.pagination import (
    PaginationModel,
)
from bet.enrichment.football_data_foundation.connector_kernel.results import (
    build_status_result,
    build_success_result,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus


class StatsBombOpenDataConnector(BaseConnector):
    provider = "statsbomb-open-data"
    source_family = "open_reference"
    source_class = "StatsBombOpenData"
    supported_operations = (
        "read_competitions",
        "read_matches",
        "read_events",
        "read_lineups",
        "read_360",
    )
    supported_capabilities = (
        "canonical_event_team_identity",
        "current_discovery",
        "fixture_team_statistics",
        "confirmed_lineups",
    )
    access_requirements = ()
    dependency_requirements = ()
    transport_type = "file_system"
    pagination_model = PaginationModel.FILE_TREE
    cache_policy = "always_cached"
    state_model = "stateless"
    evidence_policy = "deterministic_fingerprinting"
    drift_policy = "schema_drift_detection"

    _CAPABILITIES = {
        "read_competitions": "canonical_event_team_identity",
        "read_matches": "current_discovery",
        "read_events": "fixture_team_statistics",
        "read_lineups": "confirmed_lineups",
        "read_360": "fixture_team_statistics",
    }

    def _resolve_file_path(self, operation: str, **kwargs: Any) -> Path | None:
        if kwargs.get("file_path"):
            return Path(kwargs["file_path"])

        root_path = kwargs.get("root_path")
        if not root_path:
            return None

        root = Path(root_path)
        if operation == "read_competitions":
            return root / "competitions.json"
        if operation == "read_matches":
            competition_id = kwargs.get("competition_id")
            season_id = kwargs.get("season_id")
            if competition_id is None or season_id is None:
                return None
            return root / "matches" / str(competition_id) / f"{season_id}.json"
        if operation == "read_events":
            match_id = kwargs.get("match_id")
            return None if match_id is None else root / "events" / f"{match_id}.json"
        if operation == "read_lineups":
            match_id = kwargs.get("match_id")
            return None if match_id is None else root / "lineups" / f"{match_id}.json"
        if operation == "read_360":
            match_id = kwargs.get("match_id")
            return (
                None
                if match_id is None
                else root / "three-sixty" / f"{match_id}.json"
            )
        return None

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        if operation not in self.supported_operations:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_SUPPORTED,
                "operation_not_supported",
            )

        try:
            file_path = self._resolve_file_path(operation, **kwargs)
            if file_path is None:
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.NOT_FOUND,
                    "fixture_path_required",
                    {
                        "required_inputs": {
                            "root_path": "directory containing fixture tree",
                            "file_path": "explicit fixture file path",
                        }
                    },
                )

            if not file_path.exists():
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.NOT_FOUND,
                    "file_not_found",
                    {"file_path": str(file_path)},
                )

            payload = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                records = payload.get("records", [])
                retrieved_at = payload.get("retrieved_at")
            elif isinstance(payload, list):
                records = payload
                retrieved_at = kwargs.get("retrieved_at")
            else:
                records = []
                retrieved_at = kwargs.get("retrieved_at")

            return build_success_result(
                self,
                operation,
                self._CAPABILITIES[operation],
                records,
                request_identity=f"StatsBombOpenData.{operation}:{file_path.as_posix()}",
                parser_diagnostics={"scope": kwargs.get("scope", "fixture")},
                retrieved_at=retrieved_at,
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "statsbomb_open_data_parse_failed",
                {"error": str(exc)},
            )
