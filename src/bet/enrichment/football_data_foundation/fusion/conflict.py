from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bet.enrichment.football_data_foundation.kernel.contracts import FactType


@dataclass(frozen=True)
class FusionConflict:
    """
    Represents a conflict between multiple evidence sources during the fusion process.
    """

    fact_type: FactType
    identity_key: str
    source_keys: tuple[str, ...]
    values_by_source: dict[str, dict[str, Any]]
    reason: str
    severity: str = "BLOCKING"

    def is_empty(self) -> bool:
        """Checks if the conflict is empty or has no sources."""
        return len(self.source_keys) == 0

    def short_description(self) -> str:
        """Returns a short description of the conflict."""
        return f"Conflict on {self.fact_type} for {self.identity_key}: {self.reason}"
