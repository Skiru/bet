from __future__ import annotations

import csv
import sqlite3
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


class KaggleEuropeanSoccerConnector(BaseConnector):
    provider = "kaggle"
    source_family = "open_reference"
    source_class = "KaggleEuropeanSoccer"
    supported_operations = ("read_matches",)
    supported_capabilities = ("h2h_head_to_head",)
    access_requirements = ()
    dependency_requirements = ("sqlite3",)
    transport_type = "file_system"
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

        db_path = kwargs.get("db_path")
        csv_path = kwargs.get("csv_path")
        if not db_path and not csv_path:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_FOUND,
                "fixture_path_required",
            )

        path = Path(db_path or csv_path)
        if not path.exists():
            return build_status_result(
                self,
                operation,
                SourceResultStatus.NOT_FOUND,
                "fixture_not_found",
                {"file_path": str(path)},
            )

        try:
            if db_path:
                conn = sqlite3.connect(path)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT match_api_id, home_team_api_id, away_team_api_id, "
                    "home_team_goal, away_team_goal FROM Match LIMIT 50"
                ).fetchall()
                conn.close()
                records = [dict(row) for row in rows]
            else:
                with path.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    records = list(reader)

            return build_success_result(
                self,
                operation,
                "h2h_head_to_head",
                records,
                request_identity=f"KaggleEuropeanSoccer.{operation}:{path.as_posix()}",
                parser_diagnostics={"scope": kwargs.get("scope", "fixture")},
                retrieved_at=kwargs.get("retrieved_at"),
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "kaggle_read_failed",
                {"error": str(exc)},
            )
