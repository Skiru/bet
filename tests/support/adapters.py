from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class Clock:
    def __init__(self, fixed_now: datetime | None = None):
        self._fixed_now = fixed_now or datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)

    def now_utc(self) -> datetime:
        return self._fixed_now


class FixtureScanner:
    def __init__(self, fixtures: list[dict[str, Any]] | None = None):
        self._fixtures = fixtures if fixtures is not None else [
            {
                "fixture_id": "football-unicode",
                "sport": "football",
                "competition": "Integration League",
                "home_team": "ŁKS Łódź",
                "away_team": "KS D",
                "kickoff": "2026-07-16T12:00:00Z",
            }
        ]

    def scan(self, sport: str, date: str) -> list[dict[str, Any]]:
        return [f for f in self._fixtures if f.get("sport") == sport]


class TipsterProvider:
    def __init__(self, picks: list[dict[str, Any]] | None = None):
        self._picks = picks or []

    def get_picks(self, date: str) -> list[dict[str, Any]]:
        return self._picks


class AgentArtifactProducer:
    def produce_artifact(self, step_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return payload


class ProbabilityEngine:
    def calculate_probabilities(self, fixture: dict[str, Any]) -> dict[str, Any]:
        return {"home_win": 0.5, "away_win": 0.3, "draw": 0.2}


class OddsProvider:
    def __init__(self, odds: list[dict[str, Any]] | None = None):
        self._odds = odds or []

    def get_odds(self, sport: str, date_from: str, date_to: str) -> list[dict[str, Any]]:
        return self._odds


class CommandExecutor:
    def execute(self, cmd: list[str]) -> tuple[int, str, str]:
        return 0, "", ""


class DatabaseTargetPolicy:
    def __init__(self, production_write: bool = False):
        self._production_write = production_write

    def is_production_write_allowed(self) -> bool:
        return self._production_write
