"""StrictBaseModel contracts for EVENT_LIST_V1, EVENT_DOSSIER_V1 and STATS_SHEET_V1.

Field definitions and enums follow docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from bet.strict_model import StrictBaseModel

Sport = Literal["football", "tennis"]

PROVIDER_NAMES = Literal[
    "espn-football",
    "highlightly",
    "sportdb",
    "api-football",
    "understat",
    "tennis-abstract",
    "sackmann",
    "espn-tennis",
    "google-sports",
]

# The threshold for readiness=READY is identical across sports: at least 3
# priority metrics with 2+ independent providers. Each sport's priority list
# must therefore have exactly 3 entries or the threshold is unreachable.
PRIORITY_METRICS: dict[str, tuple[str, str, str]] = {
    "football": ("corners_total", "cards_total", "shots_total"),
    "tennis": ("total_games", "aces_total", "double_faults_total"),
}

# Canonical metric names in dossier/stats-sheet keys that represent a
# count-of-events statistic (used by the cross_provider_agreement rule: a
# difference <= 1 counts as agreement for these metrics).
COUNT_METRICS = frozenset(
    {
        "corners_total",
        "cards_total",
        "shots_total",
        "shots_on_target_total",
        "fouls_total",
        "aces_total",
        "double_faults_total",
        "total_games",
        "total_sets",
    }
)

# Canonical metric names that represent a percentage (0-100) statistic (used
# by the cross_provider_agreement rule: a difference <= 5 points counts as
# agreement for these metrics).
PERCENTAGE_METRICS = frozenset({"possession", "first_serve_pct", "second_serve_pct"})


class EventRecord(StrictBaseModel):
    """One row of EVENT_LIST_V1."""

    event_id: str
    sport: Sport
    competition: str
    home_team: str | None = None
    away_team: str | None = None
    player_one: str | None = None
    player_two: str | None = None
    start_time: str
    source_ids: dict[str, str] = Field(default_factory=dict)
    # Extension beyond the plan's section-2 field table, required in
    # production: Highlightly's /statistics/{match_id} endpoint hard-fails
    # with schema error "unexpected_team_id" unless it is handed that
    # provider's *native* team ids (api_clients/highlightly.py:601-607 matches
    # them against the payload's team.id to assign home/away sides). Capturing
    # them at discovery is the only way ENRICH can call that provider at all.
    # Shape: {"highlightly": {"home": "3662637", "away": "16819097"}}.
    provider_team_ids: dict[str, dict[str, str]] = Field(default_factory=dict)
    identity_confidence: Literal["CONFIRMED", "FUZZY_MATCHED", "AMBIGUOUS"]
    status: Literal["ACTIVE", "BLOCKED_IDENTITY"]
    terminal_reason: str | None = None


class EventListV1(StrictBaseModel):
    """DISCOVER artifact: a list of events for a given date."""

    # Minted by DISCOVER and carried through ENRICH and ANALYZE, so every
    # artifact and every pipeline_runs row can be traced to one run.
    run_id: str = ""
    generated_at: str
    date: str
    sports: list[Sport] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)


class ProviderValue(StrictBaseModel):
    """One raw observation of a canonical metric from a single provider."""

    provider: PROVIDER_NAMES
    match_id: str
    match_date: str
    opponent: str
    value: float
    observed_at: str


class MetricObservation(StrictBaseModel):
    canonical_name: str
    team_a_l10: list[ProviderValue] = Field(default_factory=list)
    team_b_l10: list[ProviderValue] = Field(default_factory=list)
    h2h: list[ProviderValue] = Field(default_factory=list)


class EventDossierV1(StrictBaseModel):
    """ENRICH artifact for a single event."""

    event_id: str
    sport: Sport
    metrics: dict[str, MetricObservation] = Field(default_factory=dict)
    readiness: Literal["READY", "PARTIAL", "BLOCKED"]
    data_gaps: list[str] = Field(default_factory=list)


class EventDossierListV1(StrictBaseModel):
    """ENRICH artifact wrapper: dossiers for every processed event."""

    run_id: str = ""
    # Copied from EVENT_LIST_V1 so ANALYZE, whose only input is this file, can
    # still name the betting date without a --date flag or filename parsing.
    date: str = ""
    generated_at: str
    dossiers: list[EventDossierV1] = Field(default_factory=list)


class StatsSheetRow(StrictBaseModel):
    """One row of STATS_SHEET_V1: event x market x line x direction."""

    event_id: str
    sport: Sport
    market: str
    line: float
    direction: Literal["OVER", "UNDER"]
    hits: int
    sample_size: int
    hit_rate: float
    mean: float
    median: float
    sources: list[str] = Field(default_factory=list)
    cross_provider_agreement: Literal["AGREE", "DISAGREE", "SINGLE_SOURCE", "NOT_APPLICABLE"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    data_quality: Literal["READY", "PARTIAL", "BLOCKED"]


class StatsSheetV1(StrictBaseModel):
    """ANALYZE artifact: all stats-sheet rows for a dossier collection."""

    run_id: str = ""
    date: str = ""
    generated_at: str
    rows: list[StatsSheetRow] = Field(default_factory=list)
