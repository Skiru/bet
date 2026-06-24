from __future__ import annotations

from importlib import import_module
from typing import Any

# Keep football-era exports backwards-compatible without eagerly importing
# football_data_foundation. The football package imports optional heavy deps
# such as pandas, while multisport foundation tests must remain importable
# in a lean Pass B environment.
_FOOTBALL_EXPORTS: tuple[str, ...] = (
    "RawFootballDataBundle",
    "NormalizedFootballDataRecord",
    "compute_schema_fingerprint",
    "compute_data_fingerprint",
    "flatten_multiindex_columns",
    "normalize_value",
    "normalize_numeric",
)

__all__ = list(_FOOTBALL_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _FOOTBALL_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    football_data_foundation = import_module("bet.enrichment.football_data_foundation")
    value = getattr(football_data_foundation, name)
    globals()[name] = value
    return value
