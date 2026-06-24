from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScannerEventCandidate:
    scanner_event_id: str
    profile_id: str
    sport: str
    canonical_competition_scope: str
    canonical_season_scope: str
    kickoff_local: str
    kickoff_utc: str
    home_team_name: str
    home_team_code: str | None
    away_team_name: str
    away_team_code: str | None
    group_label: str | None
    scanner_source: str
    scanner_truth_kind: str
    scanner_confidence: str
    raw_refs: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ScannerEventCandidate:
        return cls(
            scanner_event_id=str(data["scanner_event_id"]),
            profile_id=str(data["profile_id"]),
            sport=str(data["sport"]),
            canonical_competition_scope=str(data["canonical_competition_scope"]),
            canonical_season_scope=str(data["canonical_season_scope"]),
            kickoff_local=str(data["kickoff_local"]),
            kickoff_utc=str(data["kickoff_utc"]),
            home_team_name=str(data["home_team_name"]),
            home_team_code=data.get("home_team_code"),
            away_team_name=str(data["away_team_name"]),
            away_team_code=data.get("away_team_code"),
            group_label=data.get("group_label"),
            scanner_source=str(data["scanner_source"]),
            scanner_truth_kind=str(data["scanner_truth_kind"]),
            scanner_confidence=str(data["scanner_confidence"]),
            raw_refs=tuple(data.get("raw_refs") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw_refs"] = list(self.raw_refs)
        return payload


@dataclass(frozen=True)
class ScannerEventBatch:
    profile_id: str
    generated_at: str
    events: tuple[ScannerEventCandidate, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ScannerEventBatch:
        return cls(
            profile_id=str(data["profile_id"]),
            generated_at=str(data["generated_at"]),
            events=tuple(
                ScannerEventCandidate.from_dict(e) for e in data.get("events") or []
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "generated_at": self.generated_at,
            "events": [e.to_dict() for e in self.events],
        }
