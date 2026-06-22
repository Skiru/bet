from __future__ import annotations

from dataclasses import dataclass
from bet.enrichment.football_data_foundation.kernel.contracts import FactType


@dataclass(frozen=True)
class FusionConflict:
    fact_type: FactType
    reason: str
    source_keys: tuple[str, ...]
