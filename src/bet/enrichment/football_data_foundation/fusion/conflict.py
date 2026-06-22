from __future__ import annotations

from dataclasses import dataclass
from bet.enrichment.football_data_foundation.kernel.contracts import FactType


@dataclass(frozen=True)
class FusionConflict:
    """
    Represents a conflict between multiple evidence sources during the fusion process.
    
    This class captures the fact type that caused the conflict, a human-readable 
    reason detailing why the sources diverged, and the specific source keys involved
    in the contradiction.
    """
    fact_type: FactType
    reason: str
    source_keys: tuple[str, ...]

    def is_empty(self) -> bool:
        """Checks if the conflict is empty or has no sources."""
        return len(self.source_keys) == 0

    def short_description(self) -> str:
        """Returns a short description of the conflict."""
        return f"Conflict on {self.fact_type}: {self.reason}"

# Line-endings normalization proof
