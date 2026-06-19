from __future__ import annotations

import json
from typing import Any

import pandas as pd


class Deserializer:
    def deserialize(self, raw: Any) -> Any:
        if isinstance(raw, (bytes, bytearray)):
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return raw

class PandasDeserializer(Deserializer):
    def to_dataframe(self, raw: Any) -> pd.DataFrame:
        if isinstance(raw, pd.DataFrame):
            return raw
        data = self.deserialize(raw)
        if isinstance(data, list):
            return pd.DataFrame(data)
        if isinstance(data, dict):
            return pd.DataFrame([data])
        return pd.DataFrame()
