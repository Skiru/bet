from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import pandas as pd


def compute_dataframe_schema_fingerprint(df: pd.DataFrame) -> str:
    if isinstance(df.columns, pd.MultiIndex):
        columns = [list(map(str, col)) for col in df.columns]
    else:
        columns = [str(col) for col in df.columns]

    index_names = (
        [str(name) if name is not None else "" for name in df.index.names]
        if df.index is not None
        else []
    )
    dtypes = {str(col): str(dtype) for col, dtype in df.dtypes.items()}

    schema_info = {"columns": columns, "index_names": index_names, "dtypes": dtypes}

    serialized = json.dumps(schema_info, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_dataframe_data_fingerprint(df: pd.DataFrame) -> str:
    df_clean = df.copy()
    if isinstance(df_clean.columns, pd.MultiIndex):
        df_clean.columns = [
            "_".join(map(str, col)).strip("_") for col in df_clean.columns
        ]

    df_clean = df_clean.reset_index()

    records = []
    for _, row in df_clean.iterrows():
        record = {}
        for col, val in row.items():
            if pd.isna(val):
                record[str(col)] = None
            elif isinstance(val, (datetime, pd.Timestamp)):
                record[str(col)] = val.isoformat()
            else:
                record[str(col)] = val
        records.append(record)

    serialized = json.dumps(records, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_schema_fingerprint(data: Any) -> str:
    if isinstance(data, pd.DataFrame):
        return compute_dataframe_schema_fingerprint(data)
    if isinstance(data, dict):
        schema_info = {str(k): type(v).__name__ for k, v in data.items()}
    elif isinstance(data, list):
        if data and isinstance(data[0], dict):
            schema_info = {
                "type": "list_of_dict",
                "fields": {str(k): type(v).__name__ for k, v in data[0].items()},
            }
        else:
            schema_info = {
                "type": "list",
                "elements": [type(x).__name__ for x in data[:10]],
            }
    else:
        schema_info = {"type": type(data).__name__}

    serialized = json.dumps(schema_info, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_data_fingerprint(data: Any) -> str:
    if isinstance(data, pd.DataFrame):
        return compute_dataframe_data_fingerprint(data)

    def json_serializer(obj: Any) -> str:
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        return str(obj)

    serialized = json.dumps(
        data, sort_keys=True, separators=(",", ":"), default=json_serializer
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
