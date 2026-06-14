from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from bet.enrichment.models import (
    NormalizedEvent,
    NormalizedParticipant,
    NormalizedTeamMatch,
    NormalizedStandingTable,
    NormalizedLineupState,
    NormalizedAvailabilityState,
    NormalizedRoster,
    NormalizedVenueContext,
    NormalizedOfficialContext,
)

@dataclass(frozen=True)
class FootballEnrichmentSnapshot:
    schema_version: str = "1.0"
    run_id: str = ""
    snapshot_id: str = ""
    snapshot_state: str = "COMPLETE" # COMPLETE, DEGRADED, BLOCKED
    canonical_fixture_id: int = 0
    analysis_cutoff_at: datetime | None = None
    
    # Event metadata
    kickoff_at: datetime | None = None
    event_status: str = ""
    competition_canonical_id: int | None = None
    season_canonical_id: int | None = None
    
    # Participants
    home_participant: NormalizedParticipant | None = None
    away_participant: NormalizedParticipant | None = None
    
    # Form and H2H
    home_form: tuple[NormalizedTeamMatch, ...] = field(default_factory=tuple)
    away_form: tuple[NormalizedTeamMatch, ...] = field(default_factory=tuple)
    h2h_records: tuple[NormalizedTeamMatch, ...] = field(default_factory=tuple)
    
    # Standings
    standings: NormalizedStandingTable | None = None
    
    # Lineups and availability
    home_lineup: NormalizedLineupState | None = None
    away_lineup: NormalizedLineupState | None = None
    home_availability: NormalizedAvailabilityState | None = None
    away_availability: NormalizedAvailabilityState | None = None
    home_roster: NormalizedRoster | None = None
    away_roster: NormalizedRoster | None = None
    
    # Context
    venue: NormalizedVenueContext | None = None
    official: NormalizedOfficialContext | None = None
    
    # Metrics and advanced metrics
    selected_metrics: dict[str, Any] = field(default_factory=dict)
    advanced_metrics: dict[str, Any] = field(default_factory=dict)
    
    # Provenance and metadata
    selected_provider_ids: dict[str, str] = field(default_factory=dict)
    attempt_summaries: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    bundle_ids: tuple[str, ...] = field(default_factory=tuple)
    freshness_staleness: dict[str, Any] = field(default_factory=dict)
    confidence_components: dict[str, float] = field(default_factory=dict)
    missing_fields: tuple[str, ...] = field(default_factory=tuple)
