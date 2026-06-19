from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityTuple:
    provider: str
    source_family: str
    source_class: str
    operation: str
    capability: str
    competition_scope: str
    season_scope: str

    def to_string(self) -> str:
        return f"{self.provider}:{self.source_family}:{self.source_class}:{self.operation}:{self.capability}:{self.competition_scope}:{self.season_scope}"
