"""Source adapter protocol and factory for event discovery."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import DiscoveredEvent


@runtime_checkable
class SourceAdapter(Protocol):
    """Protocol for event discovery source adapters."""

    name: str
    priority: int
    supported_sports: list[str]

    def fetch_events(self, date: str, sport: str) -> list[DiscoveredEvent]:
        """Fetch events for a single sport on a date."""
        ...

    def is_available(self) -> bool:
        """Check if this source can make requests."""
        ...
