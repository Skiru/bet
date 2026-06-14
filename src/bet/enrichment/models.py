from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

class NormalizedEventStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    POSTPONED = "POSTPONED"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"
    LIVE = "LIVE"
    HALFTIME = "HALFTIME"
    EXTRA_TIME = "EXTRA_TIME"
    PENALTIES = "PENALTIES"
    FINAL = "FINAL"
    AWARDED = "AWARDED"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class NormalizedVenueContext:
    schema_version: str = "1.0"
    canonical_id: int | None = None
    native_id: str | None = None
    name: str = ""
    city: str | None = None

@dataclass(frozen=True)
class NormalizedOfficialContext:
    schema_version: str = "1.0"
    canonical_id: int | None = None
    native_id: str | None = None
    name: str = ""
    role: str | None = None

@dataclass(frozen=True)
class NormalizedParticipant:
    schema_version: str = "1.0"
    canonical_id: int | None = None
    native_id: str | None = None
    provider: str = ""
    source_timestamp: datetime | None = None
    name: str = ""
    role: str = ""  # "HOME", "AWAY", "SIDE_A", "SIDE_B", "NEUTRAL"
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class NormalizedEvent:
    schema_version: str = "1.0"
    canonical_id: int | None = None
    native_id: str | None = None
    provider: str = ""
    source_timestamp: datetime | None = None
    sport: str = ""
    competition_canonical_id: int | None = None
    competition_native_id: str | None = None
    season_canonical_id: int | None = None
    season_native_id: str | None = None
    kickoff_at: datetime | None = None
    status: NormalizedEventStatus = NormalizedEventStatus.UNKNOWN
    participants: tuple[NormalizedParticipant, ...] = field(default_factory=tuple)
    venue: NormalizedVenueContext | None = None
    official: NormalizedOfficialContext | None = None
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class NormalizedMetricSet:
    schema_version: str = "1.0"
    provider: str = ""
    source_timestamp: datetime | None = None
    values: dict[str, Any] = field(default_factory=dict)
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class NormalizedTeamMatch:
    schema_version: str = "1.0"
    canonical_fixture_id: int | None = None
    native_fixture_id: str | None = None
    provider: str = ""
    source_timestamp: datetime | None = None
    team_canonical_id: int | None = None
    team_native_id: str | None = None
    opponent_canonical_id: int | None = None
    opponent_native_id: str | None = None
    kickoff_at: datetime | None = None
    metrics: NormalizedMetricSet = field(default_factory=NormalizedMetricSet)
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class NormalizedStandingRow:
    schema_version: str = "1.0"
    team_canonical_id: int | None = None
    team_native_id: str | None = None
    rank: int = 0
    points: int = 0
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_diff: int = 0
    form: str = ""

@dataclass(frozen=True)
class NormalizedStandingTable:
    schema_version: str = "1.0"
    competition_canonical_id: int | None = None
    competition_native_id: str | None = None
    season_canonical_id: int | None = None
    season_native_id: str | None = None
    provider: str = ""
    source_timestamp: datetime | None = None
    rows: tuple[NormalizedStandingRow, ...] = field(default_factory=tuple)
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class NormalizedLineupState:
    schema_version: str = "1.0"
    provider: str = ""
    source_timestamp: datetime | None = None
    is_confirmed: bool = False
    players: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class NormalizedAvailabilityState:
    schema_version: str = "1.0"
    provider: str = ""
    source_timestamp: datetime | None = None
    injuries: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    suspensions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class NormalizedRoster:
    schema_version: str = "1.0"
    provider: str = ""
    source_timestamp: datetime | None = None
    players: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class NormalizedPlayerMetricSet:
    schema_version: str = "1.0"
    provider: str = ""
    source_timestamp: datetime | None = None
    player_canonical_id: int | None = None
    player_native_id: str | None = None
    values: dict[str, Any] = field(default_factory=dict)
    data_completeness: str = "COMPLETE"
    validation_diagnostics: dict[str, Any] = field(default_factory=dict)
