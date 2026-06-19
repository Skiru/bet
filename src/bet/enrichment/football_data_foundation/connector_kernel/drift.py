from __future__ import annotations
from typing import Any, Mapping, Sequence

class DriftClassification:
    NO_DRIFT = "NO_DRIFT"
    ADDITIVE_SCHEMA_DRIFT = "ADDITIVE_SCHEMA_DRIFT"
    BREAKING_SCHEMA_DRIFT = "BREAKING_SCHEMA_DRIFT"
    STALE_DATA_DRIFT = "STALE_DATA_DRIFT"
    BROKEN_OR_DRIFTED = "BROKEN_OR_DRIFTED"

def evaluate_drift(
    current_columns: Sequence[str],
    historical_columns: Sequence[str]
) -> str:
    if not historical_columns:
        return DriftClassification.NO_DRIFT
        
    current_set = set(current_columns)
    historical_set = set(historical_columns)
    
    missing_cols = historical_set - current_set
    new_cols = current_set - historical_set
    
    if missing_cols:
        return DriftClassification.BREAKING_SCHEMA_DRIFT
    elif new_cols:
        # Additive schema drift must not demote an operation.
        return DriftClassification.ADDITIVE_SCHEMA_DRIFT
    return DriftClassification.NO_DRIFT
