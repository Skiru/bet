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


class TipsterColumn(StrictBaseModel):
    """Public-tipster agreement for one stats-sheet row. Never a probability.

    This exists as its own nested object rather than as loose fields on
    ``StatsSheetRow`` so the boundary is structural instead of a convention
    somebody has to remember. Every number a row uses to make a claim about a
    fixture -- ``hits``, ``sample_size``, ``hit_rate``, ``confidence`` -- is
    derived from provider observations that can be traced back to specific
    matches. A tipster pick has no sample behind it; it is one person's opinion,
    often computed from the same public data and sometimes attached to a
    bookmaker affiliation. Averaging the two would destroy the only property
    ``p_low`` has, which is that you can ask where it came from and get an
    answer.

    So this column is read *beside* the confidence figure and never into it:
    it tells you whether the public agrees with a read you arrived at
    independently, which is a genuinely different question from whether the read
    is right.

    ``agree`` and ``oppose`` count only claims addressing this exact market,
    line and side. ``considered`` is how many tipster picks existed for the
    fixture at all, so a ``0/0`` verdict is distinguishable from "nobody covered
    this fixture" -- the difference between no opinion and no data.
    """

    verdict: Literal["CONFIRMS", "CONTRADICTS", "SPLIT", "NO_COVERAGE"]
    agree: int = 0
    oppose: int = 0
    considered: int = 0
    sources: list[str] = Field(default_factory=list)
    # Why the fixture's other picks did not qualify, e.g.
    # {"outcome_market_not_a_total": 4, "team_total_not_a_match_total": 2}.
    # Present so an empty column is auditable rather than merely empty.
    excluded: dict[str, int] = Field(default_factory=dict)


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
    # Optional and always last: a sheet produced without a tipster run is a
    # valid sheet, and every field above it is computed with no knowledge that
    # this one exists.
    tipster: TipsterColumn | None = None


class StatsSheetV1(StrictBaseModel):
    """ANALYZE artifact: all stats-sheet rows for a dossier collection."""

    run_id: str = ""
    date: str = ""
    generated_at: str
    rows: list[StatsSheetRow] = Field(default_factory=list)


class TipsterPickRef(StrictBaseModel):
    """One tipster claim, kept verbatim next to what we made of it.

    ``claim`` is the source's own text and is never rewritten, because the
    classification is a judgement and the operator must be able to check it.
    ``reject_reason`` is empty exactly when ``countable`` is True.
    """

    source_id: str
    source_name: str
    tipster_name: str | None = None
    claim: str
    market: str | None = None
    line: float | None = None
    direction: str
    countable: bool
    reject_reason: str = ""
    odds: float | None = None
    tipster_accuracy_pct: int | None = None
    tipster_bet_count: int | None = None
    match_date: str | None = None
    source_url: str | None = None


class TipsterEventSignal(StrictBaseModel):
    """Every tipster pick matched to one discovered event.

    ``public_lean`` summarises the 1X2/BTTS picks -- by far the bulk of what
    these sources publish. They are reported because "eleven of thirteen
    tipsters back the home side" is real information about public sentiment, and
    withheld from ``TipsterColumn`` because it is information about a *different
    market* than the total this pipeline analyses. One cannot be converted into
    the other, so they are shown separately and never summed.
    """

    event_id: str
    home_team: str
    away_team: str
    match_quality: Literal["EXACT", "FUZZY"]
    match_score: int
    picks: list[TipsterPickRef] = Field(default_factory=list)
    public_lean: dict[str, int] = Field(default_factory=dict)


class TipsterSignalV1(StrictBaseModel):
    """TIPSTERS artifact: public-opinion coverage of one betting day.

    Separate from STATS_SHEET_V1 on purpose. It is produced by a different
    stage, from different sources, with a different trust level, and the
    pipeline must run to completion without it.
    """

    run_id: str = ""
    date: str = ""
    generated_at: str
    sources_attempted: list[str] = Field(default_factory=list)
    sources_with_picks: list[str] = Field(default_factory=list)
    sources_blocked: list[dict[str, str]] = Field(default_factory=list)
    picks_ingested: int = 0
    picks_matched: int = 0
    picks_unmatched: int = 0
    countable_claims: int = 0
    date_filter: dict[str, int] = Field(default_factory=dict)
    # Kept so a thin day is diagnosable: which fixtures the sources talked about
    # that our own discovery never found.
    unmatched_events: list[str] = Field(default_factory=list)
    events: list[TipsterEventSignal] = Field(default_factory=list)
