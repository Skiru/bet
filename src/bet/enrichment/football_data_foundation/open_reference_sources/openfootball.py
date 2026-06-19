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


class OpenFootballConnector(BaseConnector):
    provider = "openfootball"
    source_family = "open_reference"
    source_class = "OpenFootball"
    supported_operations = ("read_matches",)
    supported_capabilities = ("current_recent_form",)
    access_requirements = ()
    dependency_requirements = ()
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

        try:
            file_path = kwargs.get("file_path")
            if not file_path:
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.NOT_FOUND,
                    "fixture_path_required",
                )

            path = Path(file_path)
            if not path.exists():
                return build_status_result(
                    self,
                    operation,
                    SourceResultStatus.NOT_FOUND,
                    "file_not_found",
                    {"file_path": str(path)},
                )

            payload = json.loads(path.read_text(encoding="utf-8"))
            retrieved_at = (
                payload.get("retrieved_at") if isinstance(payload, dict) else None
            )
            raw_data = (
                payload.get("competition", payload)
                if isinstance(payload, dict)
                else payload
            )

            normalized_records = []
            rounds = raw_data.get("rounds", []) if isinstance(raw_data, dict) else []
            for r in rounds:
                round_name = r.get("name", "UNKNOWN")
                for m in r.get("matches", []):
                    score_ft = (
                        m.get("score", {}).get("ft", []) if m.get("score") else []
                    )
                    normalized_records.append(
                        {
                            "round": round_name,
                            "date": m.get("date", "UNKNOWN"),
                            "team1": m.get("team1", "UNKNOWN"),
                            "team2": m.get("team2", "UNKNOWN"),
                            "score1": score_ft[0] if len(score_ft) > 0 else "UNKNOWN",
                            "score2": score_ft[1] if len(score_ft) > 1 else "UNKNOWN",
                        }
                    )

            return build_success_result(
                self,
                operation,
                "current_recent_form",
                normalized_records,
                request_identity=f"OpenFootball.{operation}:{path.as_posix()}",
                parser_diagnostics={"scope": kwargs.get("scope", "fixture")},
                retrieved_at=retrieved_at,
            )
        except Exception as exc:
            return build_status_result(
                self,
                operation,
                SourceResultStatus.PARSE_ERROR,
                "openfootball_parse_failed",
                {"error": str(exc)},
            )
