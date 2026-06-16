from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal


class FootballSide(str, Enum):
    HOME = "HOME"
    AWAY = "AWAY"

class FootballProviderStatus(str, Enum):
    FT = "FT"
    AET = "AET"
    PEN = "PEN"

class FootballFactCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    SCORE_ONLY = "SCORE_ONLY"

@dataclass(frozen=True, slots=True)
class FootballFixtureIdentity:
    provider_fixture_id: str
    provider_competition_id: str
    competition_name: str
    country: str | None
    season: int
    round_name: str | None
    kickoff_at: datetime
    provider_status: FootballProviderStatus
    canonical_status: Literal['finished']
    home_provider_team_id: str
    away_provider_team_id: str
    home_team_name: str
    away_team_name: str
    home_score: int
    away_score: int
    home_penalty_score: int | None
    away_penalty_score: int | None
    parser_version: str
    schema_version: str

@dataclass(frozen=True, slots=True)
class FootballTeamMatchFacts:
    provider_fixture_id: str
    provider_team_id: str
    side: FootballSide
    goals: int
    shots: int | None
    shots_on_target: int | None
    possession_pct: float | None
    fouls: int | None
    yellow_cards: int | None
    red_cards: int | None
    offsides: int | None
    corners: int | None
    goalkeeper_saves: int | None
    available_metrics: tuple[str, ...]
    missing_metrics: tuple[str, ...]
    completeness: FootballFactCompleteness

@dataclass(frozen=True, slots=True)
class FootballCompletedMatchFacts:
    fixture: FootballFixtureIdentity
    home: FootballTeamMatchFacts
    away: FootballTeamMatchFacts
    fixture_evidence_bundle_id: str
    statistics_evidence_bundle_id: str | None
    normalization_version: str

@dataclass(frozen=True, slots=True)
class FootballMetricSample:
    provider_fixture_id: str
    provider_opponent_team_id: str
    kickoff_at: datetime
    side: FootballSide
    metric: str
    value: float
    observation_logical_identity: str
    evidence_bundle_ids: tuple[str, ...]
    observed_at: datetime

@dataclass(frozen=True, slots=True)
class FootballMetricWindow:
    metric: str
    scope: str
    requested_count: int
    available_count: int
    samples: tuple[FootballMetricSample, ...]
    mean: float | None
    median: float | None
    missing_reason: str | None

@dataclass(frozen=True, slots=True)
class FootballFeatureSnapshotPayload:
    schema_version: str
    sport: Literal['football']
    primary_provider: Literal['api-football']
    target_provider_fixture_id: str
    analysis_cutoff_at: datetime
    policy_version: str
    policy_config_hash: str
    home_provider_team_id: str
    away_provider_team_id: str
    metric_windows: tuple[FootballMetricWindow, ...]
    source_provider_fixture_ids: tuple[str, ...]
    observation_logical_identities: tuple[str, ...]
    evidence_bundle_ids: tuple[str, ...]
    missingness: tuple[str, ...]
    data_as_of_at: datetime

@dataclass(frozen=True, slots=True)
class FootballSnapshotRecord:
    local_snapshot_id: int
    local_run_id: int
    local_canonical_fixture_id: int
    local_home_team_id: int
    local_away_team_id: int
    payload: FootballFeatureSnapshotPayload
    snapshot_hash: str
