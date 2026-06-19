from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from bet.enrichment.football_data_foundation.normalizers import (
    flatten_multiindex_columns,
    normalize_numeric,
    normalize_value,
)


class RecordNormalizer:
    def __init__(self, column_mappings: Mapping[str, str]):
        self.column_mappings = column_mappings

    def normalize(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        flat_df = flatten_multiindex_columns(df)
        records = []
        for _, row in flat_df.iterrows():
            record = {}
            for src_col, dest_col in self.column_mappings.items():
                if src_col in flat_df.columns:
                    val = row[src_col]
                    if isinstance(val, (int, float)) or (isinstance(val, pd.Series) and val.dtype in ("int64", "float64")):
                        record[dest_col] = normalize_numeric(val)
                    else:
                        record[dest_col] = normalize_value(val)
                else:
                    record[dest_col] = "UNKNOWN"
            records.append(record)
        return records
