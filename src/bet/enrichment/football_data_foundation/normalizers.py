from __future__ import annotations
from typing import Any, Mapping
import pandas as pd

def flatten_multiindex_columns(df: pd.DataFrame) -> pd.DataFrame:
    df_new = df.copy()
    if isinstance(df_new.columns, pd.MultiIndex):
        df_new.columns = ["_".join(map(str, col)).strip("_") for col in df_new.columns]
    return df_new

def normalize_value(val: Any) -> Any:
    if val is None or pd.isna(val) or str(val).strip().lower() in ("none", "null", ""):
        return "UNKNOWN"
    return val

def normalize_numeric(val: Any) -> Any:
    if val is None or pd.isna(val) or str(val).strip().lower() in ("none", "null", ""):
        return "UNKNOWN"
    try:
        # Avoid casting to float if it can be an int
        if isinstance(val, (int, float)):
            return val
        s = str(val).strip()
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return "UNKNOWN"

def normalize_record(record: Mapping[str, Any], schema_mappings: Mapping[str, str]) -> dict[str, Any]:
    normalized = {}
    for src_col, dest_col in schema_mappings.items():
        val = record.get(src_col)
        normalized[dest_col] = normalize_value(val)
    return normalized
