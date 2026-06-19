from __future__ import annotations
from typing import Any, Mapping
from pathlib import Path
import json
from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.pagination import PaginationModel
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

class OpenFootballConnector(BaseConnector):
    provider = "openfootball"
    source_family = "open_reference"
    source_class = "OpenFootball"
    supported_operations = ("fetch_worldcup_matches",)
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
            return SourceOperationResult(
                status=SourceResultStatus.NOT_SUPPORTED,
                error_code="operation_not_supported"
            )
            
        try:
            file_path = kwargs.get("file_path")
            if not file_path:
                # Return static simulation/fallback world cup matches
                raw_data = {
                    "name": "World Cup 2022",
                    "rounds": [
                        {
                            "name": "Matchday 1",
                            "matches": [
                                {
                                    "date": "2022-11-20",
                                    "team1": "Qatar",
                                    "team2": "Ecuador",
                                    "score": {"ft": [0, 2]}
                                }
                            ]
                        }
                    ]
                }
            else:
                p = Path(file_path)
                if not p.exists():
                    return SourceOperationResult(
                        status=SourceResultStatus.NOT_FOUND,
                        error_code="file_not_found"
                    )
                with open(p, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    
            # Parse round-based matches into a flat list of normalized records
            normalized_records = []
            rounds = raw_data.get("rounds", [])
            for r in rounds:
                round_name = r.get("name", "UNKNOWN")
                for m in r.get("matches", []):
                    score_ft = m.get("score", {}).get("ft", [0, 0]) if m.get("score") else [0, 0]
                    normalized_records.append({
                        "round": round_name,
                        "date": m.get("date", "UNKNOWN"),
                        "team1": m.get("team1", "UNKNOWN"),
                        "team2": m.get("team2", "UNKNOWN"),
                        "score1": score_ft[0],
                        "score2": score_ft[1]
                    })
                    
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=normalized_records,
                provider=self.provider,
                operation=operation,
                request_identity=f"OpenFootball.parse:{file_path or 'inline'}"
            )
            
        except Exception as e:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                error_code="openfootball_parse_failed",
                parser_diagnostics={"error": str(e)}
            )
