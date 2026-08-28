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
    # sports.bzzoiro.com. The only provider that keeps the home/away split all
    # the way to the dossier (hence the "_for" metrics) and the only one that
    # serves per-player history, so both of those data paths exist because this
    # name does. Adding it here is what makes ProviderValue(provider="bzzoiro")
    # constructible at all: PROVIDER_NAMES is a Literal under pydantic strict
    # mode, so an unlisted provider is a ValidationError, not a warning.
    "bzzoiro",
    # The same account as bzzoiro behind a different product
    # (sports.bzzoiro.com/tennis/api/v2), with its own resource model and its own
    # 100-a-day quota bucket, so it is its own provider and its own counter.
    # The first tennis source with native player ids rather than name matching.
    "bzzoiro-tennis",
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
        # One team's own contribution to a match, rather than both sides summed.
        # Same tolerance as a match total: these are counts of the same events.
        "corners_for",
        "cards_for",
        "shots_for",
        "shots_on_target_for",
        "fouls_for",
        # One player's line in a match.
        "player_total_shots",
        "player_shots_on_target",
        "player_fouls",
        "player_was_fouled",
        # Yellows and reds summed: the prop settles on any card.
        "player_cards",
        "aces_total",
        "double_faults_total",
        "total_games",
        "total_sets",
        # Breaks of serve in a match: each side's lost service games, summed.
        "breaks_total",
        # One player's own line, where the match total is both players summed.
        "aces_for",
        "double_faults_for",
        "games_won",
    }
)

# Canonical metric names that represent a percentage (0-100) statistic (used
# by the cross_provider_agreement rule: a difference <= 5 points counts as
# agreement for these metrics).
PERCENTAGE_METRICS = frozenset(
    {
        "possession",
        "first_serve_pct",
        "second_serve_pct",
        # Serve and break-point rates, all reported 0-100 by bzzoiro-tennis.
        # Listed here so cross_provider_agreement compares them on the +/-5
        # point tolerance a percentage needs rather than the +/-1 a count needs.
        "first_serve_won_pct",
        "break_points_saved_pct",
        "break_points_converted_pct",
    }
)


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


class PlayerMetricObservation(StrictBaseModel):
    """One player's history of one metric, for a player prop.

    Parallel to ``MetricObservation`` rather than folded into it, because the two
    answer different questions and are sampled differently. A team metric has
    three buckets that overlap (team A's last ten, team B's last ten, their H2H)
    and must be deduplicated across them; a player has exactly one history, and
    the thing that thins it is not duplication but bench time -- which is why
    ``l10`` here holds only appearances with minutes on the pitch.
    """

    player_id: str
    player_name: str
    team_side: Literal["home", "away"]
    canonical_name: str
    l10: list[ProviderValue] = Field(default_factory=list)


class EventDossierV1(StrictBaseModel):
    """ENRICH artifact for a single event."""

    event_id: str
    sport: Sport
    metrics: dict[str, MetricObservation] = Field(default_factory=dict)
    # Carried here, not looked up later, because ANALYZE's only input is this
    # file (scripts/simple/run_analyze.py takes --dossier and nothing else). A
    # per-team row that cannot name its team is not a row anyone can bet, so the
    # names have to travel with the observations that need them.
    team_a_name: str | None = None
    team_b_name: str | None = None
    # Empty on a run without --player-props, and on any event whose lineup the
    # provider would not give up.
    player_metrics: list[PlayerMetricObservation] = Field(default_factory=list)
    # "confirmed" | "predicted" | "" -- which XI the player props were built
    # from. A prop off a predicted XI is a weaker claim than the same prop off a
    # confirmed one, and the difference is invisible in the numbers themselves,
    # so it is recorded rather than inferred.
    lineup_status: str = ""
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


class MarketSignalColumn(StrictBaseModel):
    """A price and a model read for one stats-sheet row. Never a probability we computed.

    Same structural boundary as ``TipsterColumn``, drawn against a different
    temptation. Tipster opinion is obviously not a sample and the danger is that
    it *looks* like corroboration. These numbers are the opposite: a
    market-implied probability is genuinely well-calibrated -- better calibrated
    than anything in this sheet -- which makes averaging it into ``p_low`` feel
    like an improvement. It would end the one property ``p_low`` has, which is
    that you can ask which matches produced it. A price has none behind it.

    So this is a nested object rather than loose fields, and every number a row
    uses to make its claim (``hits``, ``sample_size``, ``hit_rate``, ``p_low``,
    ``confidence``) is computed with no knowledge that this object exists.

    Named generically rather than for corners because a later goals or BTTS
    activation should need no new contract field -- only a wider activation list
    in the pure function that fills it. Today that function refuses every market
    except ``corners_total``: bzzoiro publishes no odds and no model probability
    for cards, fouls or shots on target, so those rows can never get a real
    signal and must never be handed a fabricated one.

    ``model_probability`` and ``market_implied_probability`` are both the
    probability of **this row's own direction at this row's own line**, on a 0-1
    scale, and are populated only when the source covers that exact line. Nothing
    is ever interpolated across lines: over 9.5 corners and over 10.5 corners
    settle differently, and a probability moved between them is a fabrication
    wearing a real number's clothes.
    """

    verdict: Literal["CONFIRMS", "CONTRADICTS", "SPLIT", "NO_MARKET_DATA"]
    model_probability: float | None = None
    # De-vigged: the two legs of a line are normalized against each other, so
    # this is a probability rather than the bookmaker's 1/odds, which carries the
    # overround and would systematically overstate whichever side is being read.
    market_implied_probability: float | None = None
    # The best decimal price available for this row's direction and line across
    # every bookmaker bzzoiro tracks. **Not necessarily the operator's own
    # bookmaker's price** -- there is no Superbet among the 88 books in the feed
    # (checked live 2026-08-28), so this is a market reference point and never a
    # quote to bet off.
    market_price: float | None = None
    market_bookmaker: str | None = None
    sources: list[str] = Field(default_factory=list)
    # Why the column is empty, when it is: "no model probability at line 11.5",
    # "market quotes exist only at other lines", "market not covered by provider".
    # Present so an absent signal is auditable rather than merely absent.
    reason: str = ""


class StatsSheetRow(StrictBaseModel):
    """One row of STATS_SHEET_V1: event x market x line x direction."""

    event_id: str
    sport: Sport
    market: str
    line: float
    direction: Literal["OVER", "UNDER"]
    # Set on a per-team row (market ending in "_for"), None on a match total.
    # Without it a "corners_for OVER 4.5" row names no subject and two rows of
    # the same event are indistinguishable.
    team_name: str | None = None
    # Set on a player-prop row. ``lineup_status`` says whether the XI this
    # player was drawn from was confirmed or predicted.
    player_id: str | None = None
    player_name: str | None = None
    lineup_status: str | None = None
    hits: int
    # Observations that actually settle: values exactly on the line are pushes,
    # which can never be a hit in either direction, so counting them here would
    # deflate hit_rate on both sides while buying a _confidence tier with
    # observations that resolve no bet.
    sample_size: int
    pushes: int = 0
    hit_rate: float
    # Wilson lower bound at 95% on hits/sample_size. The one number a row is
    # ranked by, computed here rather than by whoever writes the summary: a
    # sort key that lives only in prose cannot be audited or reproduced. It
    # penalises thin samples on its own, which is why it -- and never
    # hit_rate -- orders the sheet: 4/4 lands near 0.51, below a 9/12 at 0.58.
    p_low: float
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
    # The same contract, one stage later: a sheet produced without a
    # MARKET_CONTEXT run is a valid sheet, and nothing above reads this either.
    market_signal: MarketSignalColumn | None = None


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


# Every market code bzzoiro's odds feed can emit, closed to the provider's own
# enum (verified live 2026-08-28 against sports.bzzoiro.com/api/schema/, which
# publishes it as an OpenAPI enum on both /api/v2/odds/ and OddsItemV2Schema),
# plus tennis's "match_winner".
#
# Unlike PROVIDER_NAMES -- a human's config-time decision, so an unlisted value
# is genuinely a mistake -- this list belongs to the live API, which may add to
# it at any time. So it is never validated against directly: MARKET_NAME_MAP in
# api_clients/bzzoiro.py filters raw codes *before* a MarketOddsLine is
# constructed, and anything unmapped is reported in ``unknown_markets`` rather
# than raising. A provider adding a market must never fail a betting day.
#
# Note what is absent: there is no cards, fouls or shots-on-target market
# anywhere in this list. Three of the five markets this pipeline prices can
# therefore never receive a real price or a real model probability, which is why
# market_signal_for_row refuses to attach a signal to them.
MARKET_CODES = Literal[
    "1x2",
    "btts",
    "over_under_05",
    "over_under_15",
    "over_under_25",
    "over_under_35",
    "double_chance",
    "draw_no_bet",
    "european_handicap",
    "asian_handicap",
    "total_corners",
    "corners_1x2",
    "total_red_cards",
    "red_card",
    # Tennis (sports.bzzoiro.com/tennis/api/v2). Listed so the contract can
    # express a tennis quote at all; no tennis market context is collected in
    # this pipeline yet, because those calls would spend the same 95/day bucket
    # ENRICH already spends.
    "match_winner",
]

OUTCOME_CODES = Literal["HOME", "DRAW", "AWAY", "over", "under", "yes", "no", "1X", "12", "X2"]


class MarketOddsLine(StrictBaseModel):
    """One bookmaker's price for one (market, outcome, line) at one moment.

    A price, and never a probability this pipeline computed. ``implied_probability``
    is the provider's own 1/decimal_odds and therefore carries the bookmaker's
    overround: the over and under legs of the same line sum to more than 1. It is
    stored raw rather than de-vigged here so the artifact records what the market
    actually quoted; removing the overround is a modelling decision and is made
    where the comparison happens, not in the parser.

    ``line`` is None for every market that has no line (1x2, btts, double_chance,
    draw_no_bet, red_card) -- not 0.0, which would read as a real line of zero.
    """

    market: MARKET_CODES
    outcome: OUTCOME_CODES
    line: float | None = None
    price: float
    implied_probability: float | None = None
    bookmaker_slug: str | None = None
    bookmaker_name: str | None = None
    # Best price across every bookmaker quoting this exact (market, outcome,
    # line), computed by this pipeline rather than read from the provider's
    # ``is_max_quote`` flag -- that flag came back unset on every event-scoped
    # corners quote surveyed live on 2026-08-28, so trusting it would have
    # silently reported no best price at all.
    is_best: bool = False
    updated_at: str | None = None


class ModelPrediction(StrictBaseModel):
    """Bzzoiro's CatBoost forecast for one event: a second opinion, not a price.

    Every probability field is independently ``| None``. The model publishes
    nulls where it has too little history, and the whole ``corners`` block is
    null when neither team history nor a market line exists. A null defaulted to
    0.5 would be indistinguishable from a genuine coin-flip read, so nothing is
    ever filled in.

    **Probabilities are stored 0-1 here, and the provider serves them 0-100.**
    The conversion happens once, in the client parser. This matters because the
    only thing these numbers are ever compared against is a market-implied
    probability, which the same API serves as a 0-1 fraction -- so leaving the
    two on different scales would make a 58.9% model read look like a 5890%
    disagreement with a 0.625 price.
    """

    prob_home: float | None = None
    prob_draw: float | None = None
    prob_away: float | None = None
    predicted: Literal["H", "D", "A"] | None = None
    xg_home: float | None = None
    xg_away: float | None = None
    prob_goals_over_15: float | None = None
    prob_goals_over_25: float | None = None
    prob_goals_over_35: float | None = None
    prob_btts_yes: float | None = None
    prob_dnb_home: float | None = None
    most_likely_score: str | None = None
    # The one model block that overlaps a market this pipeline actually prices.
    # Exactly three lines, and no others: a row on 6.5 or 11.5 corners has no
    # model probability and must be told so rather than handed an interpolation.
    prob_corners_over_85: float | None = None
    prob_corners_over_95: float | None = None
    prob_corners_over_105: float | None = None
    model_version: str | None = None
    # The provider's own confidence in its top 1X2 outcome, served 0-1.
    model_confidence: float | None = None
    created_at: str | None = None


class EventMarketContext(StrictBaseModel):
    """Everything MARKET_CONTEXT learned about one event's prices and model."""

    event_id: str
    provider_event_id: str
    # Per-bookmaker quotes for the markets this pipeline can use, from
    # /api/v2/odds/?event_id=. The uniform corners price path: it answers
    # identically whether or not the account holds Football Unlimited, so the
    # one signal that can promote a row never changes provenance with a billing
    # state.
    odds: list[MarketOddsLine] = Field(default_factory=list)
    # /api/v2/events/{id}/odds/ -- the provider's own consensus block. Carries
    # 1x2, goals over/under and BTTS only; it has no corners market at all
    # (verified live 2026-08-28), which is why it is context and never the
    # corners signal source.
    consensus_odds: dict[str, float] = Field(default_factory=dict)
    # Full per-bookmaker grid from /odds/comparison/, which requires the
    # "Football Unlimited" entitlement. NOT_ENTITLED is a recorded fact about
    # the account, not a failure of the run and not a data gap.
    bookmaker_comparison: list[MarketOddsLine] = Field(default_factory=list)
    comparison_entitlement: Literal["ENTITLED", "NOT_ENTITLED", "NOT_ATTEMPTED", "ERROR"] = "NOT_ATTEMPTED"
    bookmakers_count: int = 0
    predictions: ModelPrediction | None = None
    # Market codes the live API returned that this pipeline does not map. Present
    # so a provider adding a market surfaces as a diagnostic instead of vanishing.
    unknown_markets: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


class MarketContextV1(StrictBaseModel):
    """MARKET_CONTEXT artifact: point-in-time prices and model reads for a day.

    Deliberately not folded into EVENT_DOSSIER_V1. A dossier is sample
    arithmetic over historical matches -- ``ProviderValue`` after
    ``ProviderValue``, each traceable to a specific played fixture. These are a
    single snapshot of what a market and a model currently think, which is a
    structurally different claim. Mixing them would let a price be counted as an
    observation, and there would then be no way to ask which matches a
    probability came from.
    """

    run_id: str = ""
    date: str = ""
    generated_at: str
    # Probed once per run against a real discovered event, never assumed from
    # the plan the account is believed to be on.
    football_unlimited_entitled: bool | None = None
    events_considered: int = 0
    provider_calls: int = 0
    events: list[EventMarketContext] = Field(default_factory=list)


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
