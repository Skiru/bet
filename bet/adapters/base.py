"""Adapter base interfaces for bookmakers and other data sources."""
from __future__ import annotations

from typing import List


class BookmakerAdapter:
    """Base adapter. Implementors must provide fetch_events(date) -> List[dict]."""

    def fetch_events(self, date) -> List[dict]:
        raise NotImplementedError("Adapter must implement fetch_events(date) -> List[dict]")
