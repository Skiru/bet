"""Abstract base for source adapters with shared error handling."""

import logging
import time
from abc import ABC, abstractmethod

from ..models import DiscoveredEvent


class AbstractSourceAdapter(ABC):
    """Base class for discovery source adapters."""

    name: str
    priority: int
    supported_sports: list[str]

    def __init__(self):
        self.logger = logging.getLogger(f"bet.discovery.sources.{self.name}")
        self.last_errors: list[str] = []

    @abstractmethod
    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        """Subclass implementation. May raise exceptions."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if source can make requests (API key present, etc.)."""
        ...

    def fetch_events(self, date: str, sport: str) -> list[DiscoveredEvent]:
        """Fetch events with error handling and timing."""
        self.last_errors = []
        if sport not in self.supported_sports:
            return []

        if not self.is_available():
            self.logger.warning("%s is not available — skipping", self.name)
            return []

        start = time.monotonic()
        try:
            events = self._fetch_events_impl(date, sport)
            elapsed = time.monotonic() - start
            self.logger.info(
                "%s fetched %d %s events in %.1fs",
                self.name, len(events), sport, elapsed,
            )
            return events
        except Exception as e:
            elapsed = time.monotonic() - start
            self.last_errors.append(str(e))
            self.logger.warning(
                "%s failed for %s after %.1fs: %s",
                self.name, sport, elapsed, e,
            )
            return []

    def _record_error(self, message: str) -> None:
        """Store recoverable adapter diagnostics for coordinator summaries."""
        self.last_errors.append(message)
