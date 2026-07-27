"""Programmatic registry for all 8 supported sport protocols."""
from __future__ import annotations

from src.bet.pipeline.sports.protocols import (
    BaseSportProtocol,
    FootballProtocol,
    TennisProtocol,
    BasketballProtocol,
    HockeyProtocol,
    VolleyballProtocol,
    CS2Protocol,
    ValorantProtocol,
    Dota2Protocol,
)


class SportProtocolRegistry:
    """Registry managing sport intelligence protocols."""

    def __init__(self) -> None:
        self._protocols: dict[str, BaseSportProtocol] = {}

    def register(self, protocol: BaseSportProtocol) -> None:
        self._protocols[protocol.sport_id.lower()] = protocol

    def get(self, sport: str) -> BaseSportProtocol | None:
        return self._protocols.get(sport.lower())

    def get_strict(self, sport: str) -> BaseSportProtocol:
        prot = self.get(sport)
        if prot is None:
            raise KeyError(f"No sport protocol registered for sport: {sport}")
        return prot

    def list_sports(self) -> list[str]:
        return sorted(self._protocols.keys())


GLOBAL_SPORT_PROTOCOL_REGISTRY = SportProtocolRegistry()


def register_all_sport_protocols() -> None:
    protocols = [
        FootballProtocol(),
        TennisProtocol(),
        BasketballProtocol(),
        HockeyProtocol(),
        VolleyballProtocol(),
        CS2Protocol(),
        ValorantProtocol(),
        Dota2Protocol(),
    ]
    for p in protocols:
        GLOBAL_SPORT_PROTOCOL_REGISTRY.register(p)


register_all_sport_protocols()
