"""Source-specific contracts for S2 tipster ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class TipsterSourceContract:
    name: str
    parser: str
    transport: str
    language: str
    sports: tuple[str, ...]
    accuracy_tracked: bool
    timeout_seconds: int = 30
    wait_after_load_ms: int = 3000


TIPSTER_PICK_REQUIRED_FIELDS: tuple[str, ...] = (
    "source_site",
    "tipster_name",
    "sport",
    "event",
    "home_team",
    "away_team",
    "market",
    "market_type",
    "direction",
    "reasoning",
    "confidence",
    "fetch_time",
)


def validate_tipster_pick(pick: Mapping[str, object]) -> list[str]:
    missing = [field for field in TIPSTER_PICK_REQUIRED_FIELDS if not pick.get(field)]
    if pick.get("market_type") not in {"statistical", "outcome"}:
        missing.append("market_type")
    if pick.get("confidence") not in {"high", "medium", "low"}:
        missing.append("confidence")
    return missing
