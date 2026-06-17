from collections.abc import Mapping

# ruff: noqa: E501
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol


class FootballSide(StrEnum):
    HOME = "HOME"
    AWAY = "AWAY"

class FootballProviderStatus(StrEnum):
    FT = "FT"
    AET = "AET"
    PEN = "PEN"

class FootballFactCompleteness(StrEnum):
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

    def __post_init__(self) -> None:
        if not self.provider_fixture_id:
            raise ValueError("provider_fixture_id must be non-empty")
        if not self.provider_competition_id:
            raise ValueError("provider_competition_id must be non-empty")
        if not self.competition_name:
            raise ValueError("competition_name must be non-empty")
        if not self.home_provider_team_id:
            raise ValueError("home_provider_team_id must be non-empty")
        if not self.away_provider_team_id:
            raise ValueError("away_provider_team_id must be non-empty")
        if not self.home_team_name:
            raise ValueError("home_team_name must be non-empty")
        if not self.away_team_name:
            raise ValueError("away_team_name must be non-empty")
        if self.home_provider_team_id == self.away_provider_team_id:
            raise ValueError("home_provider_team_id and away_provider_team_id must be distinct")
        if self.kickoff_at.tzinfo is None or self.kickoff_at.utcoffset() is None:
            raise ValueError("kickoff_at must be timezone-aware")
        if self.kickoff_at.utcoffset().total_seconds() != 0:
            raise ValueError("kickoff_at must be in UTC timezone")
        if self.home_score < 0:
            raise ValueError("home_score must be non-negative")
        if self.away_score < 0:
            raise ValueError("away_score must be non-negative")
        if (self.home_penalty_score is None) != (self.away_penalty_score is None):
            raise ValueError("Penalty scores must be either both present or both absent")
        if self.home_penalty_score is not None and self.home_penalty_score < 0:
            raise ValueError("home_penalty_score must be non-negative")
        if self.away_penalty_score is not None and self.away_penalty_score < 0:
            raise ValueError("away_penalty_score must be non-negative")

@dataclass(frozen=True, slots=True)
class FootballTeamMatchFacts:
    provider_fixture_id: str
    provider_team_id: str
    provider_opponent_team_id: str
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

    def __post_init__(self) -> None:
        if not self.provider_fixture_id:
            raise ValueError("provider_fixture_id must be non-empty")
        if not self.provider_team_id:
            raise ValueError("provider_team_id must be non-empty")
        if not self.provider_opponent_team_id:
            raise ValueError("provider_opponent_team_id must be non-empty")
        if self.provider_team_id == self.provider_opponent_team_id:
            raise ValueError("provider_team_id and provider_opponent_team_id must be distinct")
        if self.goals < 0:
            raise ValueError("goals must be non-negative")

        # Check count metrics
        for name in ["shots", "shots_on_target", "fouls", "yellow_cards", "red_cards", "offsides", "corners", "goalkeeper_saves"]:
            val = getattr(self, name)
            if val is not None and val < 0:
                raise ValueError(f"{name} must be non-negative")

        if self.possession_pct is not None and not (0.0 <= self.possession_pct <= 100.0):
            raise ValueError("possession_pct must be between 0 and 100")

        # Verify available and missing metrics
        all_opts = ("shots", "shots_on_target", "possession_pct", "fouls", "yellow_cards", "red_cards", "offsides", "corners", "goalkeeper_saves")

        expected_avail = []
        expected_miss = []
        for m in all_opts:
            if getattr(self, m) is not None:
                expected_avail.append(m)
            else:
                expected_miss.append(m)

        expected_avail = tuple(sorted(expected_avail))
        expected_miss = tuple(sorted(expected_miss))

        if self.available_metrics != expected_avail:
            raise ValueError(f"available_metrics mismatch. Expected: {expected_avail}, Got: {self.available_metrics}")
        if self.missing_metrics != expected_miss:
            raise ValueError(f"missing_metrics mismatch. Expected: {expected_miss}, Got: {self.missing_metrics}")

        # Sorted
        if list(self.available_metrics) != sorted(self.available_metrics):
            raise ValueError("available_metrics must be sorted")
        if list(self.missing_metrics) != sorted(self.missing_metrics):
            raise ValueError("missing_metrics must be sorted")

        # Completeness
        num_avail = len(self.available_metrics)
        if num_avail == 9:
            expected_completeness = FootballFactCompleteness.COMPLETE
        elif num_avail == 0:
            expected_completeness = FootballFactCompleteness.SCORE_ONLY
        else:
            expected_completeness = FootballFactCompleteness.PARTIAL

        if self.completeness != expected_completeness:
            raise ValueError(f"completeness mismatch. Expected {expected_completeness}, Got: {self.completeness}")

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
    evidence_fingerprint_hashes: tuple[str, ...]
    missingness: tuple[str, ...]
    data_as_of_at: datetime | None = None

@dataclass(frozen=True, slots=True)
class FootballSnapshotRecord:
    local_snapshot_id: int
    local_run_id: int
    local_canonical_fixture_id: int
    local_home_team_id: int
    local_away_team_id: int
    payload: FootballFeatureSnapshotPayload
    snapshot_hash: str

def serialize_fixture_identity(identity: FootballFixtureIdentity) -> dict:
    from bet.enrichment.football.time import format_utc
    return {
        "provider_fixture_id": identity.provider_fixture_id,
        "provider_competition_id": identity.provider_competition_id,
        "competition_name": identity.competition_name,
        "country": identity.country,
        "season": identity.season,
        "round_name": identity.round_name,
        "kickoff_at": format_utc(identity.kickoff_at),
        "provider_status": identity.provider_status.value,
        "canonical_status": identity.canonical_status,
        "home_provider_team_id": identity.home_provider_team_id,
        "away_provider_team_id": identity.away_provider_team_id,
        "home_team_name": identity.home_team_name,
        "away_team_name": identity.away_team_name,
        "home_score": identity.home_score,
        "away_score": identity.away_score,
        "home_penalty_score": identity.home_penalty_score,
        "away_penalty_score": identity.away_penalty_score,
        "parser_version": identity.parser_version,
        "schema_version": identity.schema_version,
    }

def serialize_team_match_facts(facts: FootballTeamMatchFacts) -> dict:
    return {
        "provider_fixture_id": facts.provider_fixture_id,
        "provider_team_id": facts.provider_team_id,
        "provider_opponent_team_id": facts.provider_opponent_team_id,
        "side": facts.side.value,
        "goals": facts.goals,
        "shots": facts.shots,
        "shots_on_target": facts.shots_on_target,
        "possession_pct": facts.possession_pct,
        "fouls": facts.fouls,
        "yellow_cards": facts.yellow_cards,
        "red_cards": facts.red_cards,
        "offsides": facts.offsides,
        "corners": facts.corners,
        "goalkeeper_saves": facts.goalkeeper_saves,
        "available_metrics": list(facts.available_metrics),
        "missing_metrics": list(facts.missing_metrics),
        "completeness": facts.completeness.value,
    }

def round_float_six(v):
    import math
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise ValueError("NaN and Infinity are not allowed in snapshot payload")
        if v == 0.0 or v == -0.0:
            return 0.0
        return round(v, 6)
    if isinstance(v, dict):
        return {k: round_float_six(val) for k, val in v.items()}
    if isinstance(v, list):
        return [round_float_six(val) for val in v]
    if isinstance(v, tuple):
        return tuple(round_float_six(val) for val in v)
    return v

def serialize_snapshot_payload(payload: FootballFeatureSnapshotPayload) -> dict:
    from bet.enrichment.football.time import format_utc
    d = {
        "schema_version": payload.schema_version,
        "sport": payload.sport,
        "primary_provider": payload.primary_provider,
        "target_provider_fixture_id": payload.target_provider_fixture_id,
        "analysis_cutoff_at": format_utc(payload.analysis_cutoff_at),
        "policy_version": payload.policy_version,
        "policy_config_hash": payload.policy_config_hash,
        "home_provider_team_id": payload.home_provider_team_id,
        "away_provider_team_id": payload.away_provider_team_id,
        "metric_windows": [
            {
                "metric": w.metric,
                "scope": w.scope,
                "requested_count": w.requested_count,
                "available_count": w.available_count,
                "samples": [
                    {
                        "provider_fixture_id": s.provider_fixture_id,
                        "provider_opponent_team_id": s.provider_opponent_team_id,
                        "kickoff_at": format_utc(s.kickoff_at),
                        "side": s.side.value,
                        "metric": s.metric,
                        "value": s.value,
                        "observation_logical_identity": s.observation_logical_identity,
                        "evidence_bundle_ids": list(s.evidence_bundle_ids),
                        "observed_at": format_utc(s.observed_at),
                    }
                    for s in w.samples
                ],
                "mean": w.mean,
                "median": w.median,
                "missing_reason": w.missing_reason,
            }
            for w in payload.metric_windows
        ],
        "source_provider_fixture_ids": sorted(list(payload.source_provider_fixture_ids)),
        "observation_logical_identities": sorted(list(payload.observation_logical_identities)),
        "evidence_fingerprint_hashes": sorted(list(payload.evidence_fingerprint_hashes)),
        "missingness": sorted(list(payload.missingness)),
        "data_as_of_at": format_utc(payload.data_as_of_at) if payload.data_as_of_at else None,
    }
    return round_float_six(d)

# CP3 additions
from datetime import date

from bet.integration.evidence import EvidenceRef


class BatchIdsCapability(StrEnum):
    UNKNOWN = "UNKNOWN"
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"

class AcquisitionMode(StrEnum):
    DISCOVERY_ENVELOPE = "DISCOVERY_ENVELOPE"
    BATCH_IDS = "BATCH_IDS"
    PER_FIXTURE_STATS = "PER_FIXTURE_STATS"
    REPLAY = "REPLAY"
    TRANSIENT_FAILED = "TRANSIENT_FAILED"
    RATE_LIMITED = "RATE_LIMITED"

@dataclass(frozen=True, slots=True)
class BootstrapCommand:
    competition_provider_id: str
    season: int
    from_date: date
    to_date: date
    max_fixtures: int
    max_http_attempts: int
    max_fallback_stats_calls: int

@dataclass(frozen=True, slots=True)
class IncrementalCommand:
    competition_provider_id: str
    season: int
    correction_lookback_days: int
    max_fixtures: int
    max_http_attempts: int
    max_fallback_stats_calls: int
    daily_quota_reserve: int
    minute_quota_reserve: int

@dataclass(frozen=True, slots=True)
class ReplayCommand:
    evidence_bundle_ids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class BuildSnapshotCommand:
    canonical_target_fixture_id: int
    analysis_cutoff_at: datetime
    policy_version: str

@dataclass(frozen=True, slots=True)
class InspectCommand:
    fixture_id: int | None
    team_id: int | None

@dataclass(frozen=True, slots=True)
class AcquiredFixture:
    fixture: FootballFixtureIdentity
    statistics_by_provider_team_id: dict[str, dict[str, Any]]
    fixture_evidence_refs: tuple[EvidenceRef, ...]
    statistics_evidence_refs: tuple[EvidenceRef, ...]
    observed_at: datetime
    acquisition_mode: AcquisitionMode
    warnings: tuple[str, ...]
    originating_bundle_id: str | None = None

@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    fixtures: tuple[AcquiredFixture, ...]
    physical_attempts: int
    retry_attempts: int
    discovery_calls: int
    ids_calls: int
    statistics_calls: int
    quota_metadata: dict[str, Any]
    ids_capability: BatchIdsCapability
    terminal_status: str

@dataclass(frozen=True, slots=True)
class PersistFixtureResult:
    canonical_fixture_id: int
    canonical_event_entity_id: int
    canonical_home_team_id: int
    canonical_away_team_id: int
    observations_inserted: int
    observations_reused: int
    corrections_appended: int
    projections_updated: int
    sync_item_state: str
    fixture_bundle_id: str

@dataclass(frozen=True, slots=True)
class SyncResult:
    sync_run_id: int
    scope_key: str
    cursor_before: dict[str, Any] | None
    cursor_after: dict[str, Any] | None
    actual_counters: dict[str, int]
    acquisition_result: AcquisitionResult | None
    final_status: str
    warnings: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class SnapshotResult:
    run_id: int
    snapshot_id: int
    snapshot_hash: str
    created_or_reused: str
    deterministic_drift: bool

@dataclass(frozen=True, slots=True)
class FixtureInspectData:
    id: int
    provider_id: str | None
    status: str
    score: dict[str, Any]
    kickoff: str
    observations: tuple[dict[str, Any], ...]
    projections: tuple[dict[str, Any], ...]

@dataclass(frozen=True, slots=True)
class TeamInspectData:
    id: int
    name: str
    completed_fixtures_count: int
    latest_observations: tuple[dict[str, Any], ...]

@dataclass(frozen=True, slots=True)
class InspectResult:
    status: str
    actual_data: FixtureInspectData | TeamInspectData | None = None


class Clock(Protocol):
    def now_utc(self) -> datetime:
        ...
    def today_utc(self) -> datetime.date:
        ...


class SystemClock:
    def now_utc(self) -> datetime:
        from datetime import UTC
        return datetime.now(UTC)
    def today_utc(self) -> datetime.date:
        from datetime import UTC
        return datetime.now(UTC).date()


@dataclass(frozen=True, slots=True)
class DiscoveredFixtureRecord:
    fixture: FootballFixtureIdentity | None
    provider_fixture_id: str | None
    state: Literal["VALID", "INVALID"]
    error_code: str | None
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    valid_fixtures: tuple[FootballFixtureIdentity, ...]
    invalid_records: tuple[DiscoveredFixtureRecord, ...]
    discovery_evidence_refs: tuple[EvidenceRef, ...]
    paging_completed: bool
    physical_attempts: int
    retry_attempts: int
    quota_metadata: dict[str, Any]
    terminal_status: str

    @property
    def completed_fixtures(self) -> tuple[FootballFixtureIdentity, ...]:
        return self.valid_fixtures


class NoReplayableFixturesError(ValueError):
    """Raised when replay has zero parsed fixtures."""
    pass


FootballTeamStatistics = dict[str, Any]

def compute_normalized_match_payload_hash(
    fixture: FootballFixtureIdentity,
    statistics_by_provider_team_id: Mapping[str, FootballTeamStatistics],
) -> str:
    import hashlib
    import json

    from bet.enrichment.football.parser import merge_completed_match_facts

    completed_facts = merge_completed_match_facts(
        fixture,
        dict(statistics_by_provider_team_id),
        "",
        ""
    )
    sorted_facts = sorted([completed_facts.home, completed_facts.away], key=lambda f: str(f.provider_team_id))
    facts_list = [serialize_team_match_facts(f) for f in sorted_facts]
    normalized_payload_json = json.dumps(facts_list, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(normalized_payload_json.encode("utf-8")).hexdigest().lower()


class ProvenanceIntegrityError(ValueError):
    """Raised when snapshot provenance fails closed."""
    pass


class CursorCorruptionError(ValueError):
    """Raised when coverage_json is corrupted."""
    pass
