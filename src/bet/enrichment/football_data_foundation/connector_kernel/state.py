from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CapabilityState:
    provider: str
    source_family: str
    source_class: str
    operation: str
    capability: str
    competition_scope: str
    season_scope: str
    status: str = "PENDING"
    is_active: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)
