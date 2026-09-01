"""StrictBaseModel contracts for EVENT_LIST_V1, EVENT_DOSSIER_V1 and STATS_SHEET_V1.

Field definitions and enums follow docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2.
"""
from __future__ import annotations

from typing import Any, Literal

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
        "goals_total",
        # One team's own contribution to a match, rather than both sides summed.
        # Same tolerance as a match total: these are counts of the same events.
        "corners_for",
        "cards_for",
        "shots_for",
        "shots_on_target_for",
        "fouls_for",
        "goals_for",
        "goals_against",
        # Faza 2: offsides and red cards priced for the first time, same
        # counting-events tolerance as everything else in this set.
        "offsides_total",
        "offsides_for",
        "red_cards_total",
        # Faza 3: half-time splits, derived from the fixture's own
        # home_score_ht/away_score_ht rather than /stats/.
        "goals_1h_total",
        "goals_2h_total",
        "goals_1h_for",
        "goals_2h_for",
        # One player's line in a match.
        "player_total_shots",
        "player_shots_on_target",
        "player_fouls",
        "player_was_fouled",
        # Yellows and reds summed: the prop settles on any card.
        "player_cards",
        # Faza 2 (docs/PLAN_RYNKI_SUPERBET.md): props Superbet prices and this
        # pipeline did not, all three counts of discrete events like the rest.
        "player_tackles",
        "player_assists",
        "player_offsides",
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


class FixtureContext(StrictBaseModel):
    """Circumstances of one fixture, as bzzoiro's own ``/events/`` row states them.

    Every field here arrives inside a page the discovery adapter already fetches,
    so this block costs **no request at all** -- it used to be parsed and thrown
    away in ``_normalize_event_row``.

    ``referee_id`` is the field that earns the block. It is the address for
    ``/referees/{id}/``, and cards and fouls are the two markets where the
    pipeline has no corroborating provider and nothing but the two clubs' own
    histories to go on -- while the man who actually shows the cards varies by
    roughly a third of a cards line between officials in the same competition.

    The rest is context a human would ask for and the pipeline could not
    previously answer: a derby is a cards fixture, a neutral ground removes the
    home crowd a referee responds to, and rain suppresses shot counts. **None of
    it is a sample and none of it may enter ``p_low``** -- it is read beside the
    numbers, exactly like ``tipster`` and ``market_signal``.
    """

    referee_id: str | None = None
    venue_id: str | None = None
    # The competition's native id, kept so ENRICH can address
    # ``/leagues/{id}/standings/`` without re-resolving a name it already had.
    league_id: str | None = None
    is_local_derby: bool = False
    is_neutral_ground: bool = False
    travel_distance_km: float | None = None
    # {"code": 51, "description": null, "wind_speed": 8.2, "temperature_c": 13}
    # Kept as the provider's own object: it is reported verbatim, never computed
    # with, so imposing a schema on it would only create a second thing to keep
    # in step with an upstream that owes us no stability here.
    weather: dict[str, Any] | None = None
    # Stakes context. round_name/group_name are bzzoiro's own free-text label
    # (empty on every plain league fixture verified live 2026-08-31 -- no
    # cup/knockout fixture has been observed yet, so no automatic tier flag
    # is built on this string until one has: see context_flags.py's own
    # comment on why). previous_leg_event_id names the first leg of a
    # two-legged tie; this pipeline does not resolve it (that needs a
    # follow-up call to see who is trailing on aggregate), it only carries
    # the pointer so bet-analyst can.
    round_name: str | None = None
    group_name: str | None = None
    previous_leg_event_id: str | None = None


class RefereeProfile(StrictBaseModel):
    """One referee's discipline averages, resolved at ENRICH from ``referee_id``.

    Costs one call per *referee*, not per fixture -- an official works many
    matches in a season, so a day's slate resolves from a handful of requests
    against an uncapped football product.

    **Read ``matches`` before believing any average.** It is the season sample,
    and a referee two games in has averages built on two games; the career
    totals are carried alongside so that thinness is visible rather than hidden
    behind a confident-looking float. This is context, never a sample: it
    describes the official, not this fixture, and must not reach ``p_low``.
    """

    provider_referee_id: str
    name: str = ""
    country: str | None = None
    matches: int | None = None
    avg_yellow_per_match: float | None = None
    avg_red_per_match: float | None = None
    avg_fouls_per_match: float | None = None
    avg_goals_per_match: float | None = None
    career_games: int | None = None
    career_yellow_cards: int | None = None
    career_red_cards: int | None = None


class SquadAvailability(StrictBaseModel):
    """Who cannot play for one side, from ``/teams/{id}/squad/``.

    The only structured absence feed in this API. It matters twice: a player
    prop on somebody who is injured is **void, not losing**, and a side missing
    its usual takers is a different team than its last ten matches describe.

    ``availability_unknown`` counts players the provider published no report
    for. It is kept separate from ``unavailable`` on purpose -- an empty
    ``availability`` string is not evidence of fitness, and collapsing the two
    would let a thinly-covered squad read as a fully fit one.
    """

    provider_team_id: str
    side: Literal["home", "away"]
    squad_size: int = 0
    unavailable_count: int = 0
    availability_unknown_count: int = 0
    # [{"provider_player_id", "player_name", "position", "availability",
    #   "injury_type", "injury_expected_return"}]
    unavailable: list[dict[str, Any]] = Field(default_factory=list)


class TeamSeasonForm(StrictBaseModel):
    """One side's league-table row: season expected goals and recent results.

    The only season-level xG in this API. Every other number the pipeline holds
    is per finished match, so without this a team's underlying quality can only
    be re-derived from the same ten observations the hit rate already counts --
    the same opinion twice, not a second one.

    **Read ``xg_games`` before believing ``xgf``/``xga``.** Two matches into a
    season these are two-match figures wearing a decimal point, exactly like a
    referee's averages at ``matches: 2``.

    ``form`` is the provider's own recent-results string (``"WWLDW"``), newest
    first. Context throughout: none of it is an observation of a market this
    pipeline prices, and none of it may reach ``p_low``.
    """

    provider_team_id: str
    side: Literal["home", "away"]
    team_name: str = ""
    # Set only in competitions played in groups, where ``position`` is a rank
    # within this group and not within the competition.
    group: str | None = None
    position: int | None = None
    played: int | None = None
    points: int | None = None
    xgf: float | None = None
    xga: float | None = None
    xgd: float | None = None
    xg_games: int | None = None
    form: str | None = None


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
    # Only bzzoiro publishes this, and only for events it discovered itself, so
    # it is None on any fixture another source found alone. Defaulted rather
    # than required because every EVENT_LIST written before 2026-08-30 lacks it.
    fixture_context: FixtureContext | None = None


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
    # Context, deliberately kept out of `metrics`. Everything in `metrics` is an
    # observation of a past match that a hit rate is counted from; these two
    # describe the fixture's circumstances instead. Mixing them would let a
    # referee's season average be counted as if it were a match this pipeline
    # watched, which is exactly the error `p_low` exists to make impossible.
    fixture_context: FixtureContext | None = None
    referee: RefereeProfile | None = None
    squad_availability: list[SquadAvailability] = Field(default_factory=list)
    season_form: list[TeamSeasonForm] = Field(default_factory=list)


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
    # How many of ``agree``/``oppose`` were claims on this row's exact line
    # rather than on a line that merely entails it. A tipster on over 13.5
    # fouls does settle a bet on over 8.5, so it counts -- but it is a claim
    # about a different number, and an operator comparing the column to
    # ``p_low`` should be able to see which kind of support a row has.
    exact: int = 0
    considered: int = 0
    sources: list[str] = Field(default_factory=list)
    # The fixture's 1X2/BTTS tally, copied from the signal so a caller holding
    # only the sheet can still say what the public thinks of the match. It is a
    # *different market* from this row and can never be converted into one --
    # it is carried here to be read beside the row, never counted into it.
    lean: dict[str, int] = Field(default_factory=dict)
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


class ContextFlag(StrictBaseModel):
    """One circumstance's opinion of a row, from ``context_flags.py``.

    Same structural boundary as ``TipsterColumn`` and ``MarketSignalColumn``: a
    referee's discipline average, an injury count, a form/xG gap, a derby, or
    wind speed are all circumstances a human would weigh, and previously lived
    only in the analyst's prose -- invisible to anything downstream that reads
    the sheet, and not reliably re-checked before a coupon was built from it.

    ``direction`` is deliberately one-way in practice, not just in name:
    ``tier_for_row`` only ever acts on ``ARGUES_AGAINST`` (stepping a tier down
    once, never past WEAK) and never on ``SUPPORTS`` -- the same "context may
    downgrade, never promote" rule this pipeline already enforces for evidence
    a human writes in prose, now enforced in code for evidence attached here.
    ``magnitude`` is carried for the reader (a note); it plays no role in the
    one-step-regardless-of-magnitude rule ``tier_for_row`` applies.
    """

    source: str
    direction: Literal["SUPPORTS", "ARGUES_AGAINST"]
    magnitude: float
    note: str



class SuperbetColumn(StrictBaseModel):
    """What the operator's own book says about this exact row.

    Attached by ANALYZE when a SUPERBET offer artifact is passed, and by
    ``build_coupons`` when one is passed there. Optional and always last, for
    the same reason ``tipster`` and ``market_signal`` are: a sheet produced
    without a Superbet run is a valid sheet, and nothing that computes
    ``p_low`` reads this.

    The field that earns this column's existence is ``availability``, not
    ``price``. A row whose line is absent from the book is not a cheap bet or
    an expensive one -- it is not a bet, and before this column existed there
    was no way to say so.
    """

    # Mirrors SUPERBET_VERDICTS minus the two that are properties of the
    # comparison run rather than of the row (VALUE / PRICED_BELOW_THRESHOLD are
    # recomputed wherever a threshold is known, since the threshold depends on
    # the tier and the tier can be downgraded after this column is written).
    availability: Literal[
        "OFFERED", "LINE_NOT_OFFERED", "MARKET_NOT_OFFERED", "SUSPENDED",
        "EVENT_NOT_MATCHED", "OFFER_EMPTY", "SCOPE_NOT_SUPPORTED",
        "PLAYER_NOT_MATCHED",
    ]
    price: float | None = None
    status: str | None = None
    source_market_name: str | None = None
    nearest_offered_line: float | None = None
    nearest_offered_price: float | None = None
    # Superbet's own fixture id, so a disputed price can be re-fetched.
    superbet_event_id: str | None = None

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
    # Populated by context_flags.py from the same dossier this row was already
    # built from -- no new provider call. Empty is the common case and a valid
    # sheet. Read by tier_for_row (ARGUES_AGAINST only, one step down); never
    # read by anything that computes p_low.
    context_flags: list[ContextFlag] = Field(default_factory=list)
    # The operator's own book, attached last of all (SUPERBET, 2026-08-31).
    # A price here is the price on the screen; every other price in this
    # pipeline is a reference from a bookmaker the operator does not use.
    superbet: SuperbetColumn | None = None


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
    # Which team or player the claim is about. Empty on a match total; one entry
    # on a per-team or per-player claim; two when the tipster wrote "obie
    # drużyny" and meant the same line for each side. A ``*_for`` or
    # ``player_*`` claim only corroborates the row whose subject it names, so
    # this is what the column joins on besides market and line.
    subjects: list[str] = Field(default_factory=list)
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

    # --- tennis (bzzoiro-tennis /predictions/), added 2026-08-30 -------------
    #
    # One contract for both sports rather than two, because every consumer of
    # this object -- the artifact, the signal function, the analyst -- would
    # otherwise need a branch on sport to read a field that means the same
    # thing. Football fixtures leave these null and tennis leaves the block
    # above null; nothing is ever populated for the wrong sport.
    #
    # ``prob_games_over_215`` and ``prob_games_over_225`` land on two of the
    # four ``total_games`` lines this pipeline prices, and ``prob_sets_over_25``
    # is the whole ``total_sets`` market. 19.5 and 23.5 get nothing: the model
    # does not publish them, and 20.5 is carried only because it arrives free --
    # no row is priced at that line, and it is never interpolated onto one.
    prob_games_over_205: float | None = None
    prob_games_over_215: float | None = None
    prob_games_over_225: float | None = None
    prob_sets_over_25: float | None = None
    expected_total_games: float | None = None
    expected_total_sets: float | None = None
    prob_player_one_wins: float | None = None
    prob_player_two_wins: float | None = None


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


# --- Superbet offer (SUPERBET step, added 2026-08-31) ----------------------
#
# Every other price in this pipeline is a *reference*: bzzoiro's grid holds
# ~88 bookmakers and Superbet is not one of them. These contracts hold the
# book the operator actually bets into, which answers a question a reference
# price structurally cannot -- **is this line on the screen at all**.
#
# That turned out to be the dominant failure mode rather than a footnote. On
# the 2026-08-31 night slate, eight of fifteen singles were on lines Superbet
# does not list, and every ATP fixture was quoted best-of-five against a stats
# sheet that only emits best-of-three lines.


SUPERBET_VERDICTS = Literal[
    # Price is at or above the row's min_acceptable_odds. The only verdict that
    # says "this is a bet at the operator's book".
    "VALUE",
    # The line is on the screen and priced below the bar. A real answer about a
    # real market, not a gap.
    "PRICED_BELOW_THRESHOLD",
    # Superbet lists this market for this fixture but not at our line. Carries
    # nearest_offered_line so the operator can see how far off the ladder is.
    "LINE_NOT_OFFERED",
    # Superbet lists the fixture but not this market family at all.
    "MARKET_NOT_OFFERED",
    # Matched fixture, matched line, outcome suspended/blocked at fetch time.
    "OUTCOME_SUSPENDED",
    # No Superbet fixture could be matched to this event. Never silently the
    # same as "no market": one is our matcher's failure, the other is the book.
    "EVENT_NOT_MATCHED",
    # The fixture is on the book and the book is pricing nothing on it -- it
    # has kicked off, or the offer has been pulled. Distinct from
    # MARKET_NOT_OFFERED because "no market on this fixture at all" is a fact
    # about the clock, and reading it as a market-coverage gap made 52 finished
    # fixtures look like 12,000 missing markets on the first live run.
    "OFFER_EMPTY",
    # A market family this pipeline knowingly does not read from Superbet.
    # Until 2026-09-01 player props were the whole of it, which overstated the
    # book's coverage gap by a factor of three; they are read now. What is left
    # is the genuinely unreadable: shot sub-populations Superbet splits by body
    # part and bzzoiro does not, and markets whose settlement rule is unknown.
    "SCOPE_NOT_SUPPORTED",
    # Superbet prices this prop but its player string could not be joined to one
    # of ours, or joined to two of ours equally well. Our failure, not the
    # book's, and separated from SCOPE_NOT_SUPPORTED because this one is fixable
    # per fixture and shows up as a name in the artifact.
    "PLAYER_NOT_MATCHED",
]


class SuperbetLine(StrictBaseModel):
    """One priced outcome on Superbet, normalised into this pipeline's terms.

    ``price`` is decimal and verbatim. ``status`` is Superbet's own
    (``active`` / ``block`` / ...): a blocked outcome still has a price
    attached and quoting it as bettable is how a coupon acquires a number
    nobody can take.
    """

    market: str
    line: float
    direction: Literal["OVER", "UNDER"]
    # Set when this is a per-team line ("Remo - liczba kartek"), None on a
    # match total and on a player prop.
    team_name: str | None = None
    # Set on a player prop, and holding **Superbet's own spelling** verbatim
    # ("Lodi, Renan"), never ours. The join to our player ids is a fuzzy,
    # refusable operation and it happens once, in ``offered_lines``, where both
    # squads are in hand -- storing a resolved name here would bake one run's
    # guess into the artifact with no way to audit it afterwards.
    player_name: str | None = None
    price: float
    status: str = "active"
    # Superbet's own market name, kept verbatim. The mapping from Polish prose
    # to a market code is the part most likely to be wrong, and it cannot be
    # audited if the source string is thrown away.
    source_market_name: str
    source_outcome_name: str


class SuperbetEventOffer(StrictBaseModel):
    """One Superbet fixture, matched to one of our events (or to none)."""

    superbet_event_id: str
    superbet_match_name: str
    sport: Sport
    kickoff: str
    # None when this Superbet fixture matched nothing we discovered. Kept
    # anyway: a fixture on the book that our DISCOVER never found is the single
    # most actionable coverage gap there is.
    event_id: str | None = None
    # ID_MATCHED means the pairing came from a Betradar id shared by OddsPapi
    # and Superbet, so it involved no name comparison and no kickoff window.
    # It outranks EXACT: EXACT still means "two names and two clocks agreed".
    match_quality: Literal["ID_MATCHED", "EXACT", "FUZZY", "UNMATCHED"] = "UNMATCHED"
    # Superbet's kickoff minus ours, in minutes. Tennis is scheduled by court
    # order, so its published time is an estimate and drifts by an hour or more
    # without the fixture being a different match.
    kickoff_delta_minutes: float | None = None
    market_count: int = 0
    status: str | None = None
    lines: list[SuperbetLine] = Field(default_factory=list)
    # Market names the feed returned that this pipeline does not map, deduped.
    # Present so Superbet adding a market surfaces as a diagnostic rather than
    # vanishing -- and so the reverse, a mapping that stops matching, does too.
    unmapped_markets: list[str] = Field(default_factory=list)


class SuperbetOfferV1(StrictBaseModel):
    """SUPERBET artifact: what the operator's book is actually offering."""

    run_id: str = ""
    date: str = ""
    generated_at: str
    source: str = "superbet.pl public prematch offer"
    window_start: str = ""
    window_end: str = ""
    requests_made: int = 0
    events_on_offer: int = 0
    events_matched: int = 0
    events_unmatched: int = 0
    # Our events that Superbet does not carry at all. The other half of the
    # coverage picture from ``events_unmatched``.
    our_events_without_offer: list[str] = Field(default_factory=list)
    # The subset of the above whose kickoff had already passed when the offer
    # was fetched. ``offerState=prematch`` stops carrying a fixture the moment
    # it goes live, so a late run legitimately reports Barcelona-Rayo as absent
    # from the book. Separated because "the book dropped it because it started"
    # and "our matcher failed" are different problems and only one is ours.
    our_events_kicked_off: list[str] = Field(default_factory=list)
    events: list[SuperbetEventOffer] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    # How many fixtures were named by a Betradar id rather than by comparing
    # spellings, and what the OddsPapi bridge cost to find out. Separate from
    # ``data_gaps`` on purpose: a bridge that did not run is a missed
    # optimisation, not a degraded betting day, and must not make the step
    # PARTIAL.
    events_matched_by_id: int = 0
    identity_bridge: dict[str, Any] = Field(default_factory=dict)


class SuperbetComparisonRow(StrictBaseModel):
    """One stats-sheet row judged against the operator's own book.

    ``min_acceptable_odds`` is copied from the same formula the coupon uses
    (1/p_low x tier margin) rather than recomputed with a different constant --
    a threshold that disagrees with the coupon's is worse than no threshold.
    """

    event_id: str
    match: str
    kickoff: str
    sport: Sport
    market: str
    line: float
    direction: Literal["OVER", "UNDER"]
    team_name: str | None = None
    p_low: float
    hits: int
    sample_size: int
    median: float
    tier: str
    min_acceptable_odds: float
    verdict: SUPERBET_VERDICTS
    superbet_price: float | None = None
    superbet_status: str | None = None
    superbet_market_name: str | None = None
    # Set on LINE_NOT_OFFERED: the closest line Superbet does quote for this
    # market and direction, and how far it is. This is the field that turns
    # "no bet" into "your line generator is off by four goals-worth of shots".
    nearest_offered_line: float | None = None
    nearest_offered_price: float | None = None
    # price - min_acceptable_odds. Positive is value, and it is stated in odds
    # rather than probability because that is what the operator compares
    # against on the screen.
    odds_surplus: float | None = None


class SuperbetComparisonV1(StrictBaseModel):
    """SUPERBET comparison artifact: our sheet vs the book, row by row."""

    run_id: str = ""
    date: str = ""
    generated_at: str
    rows_considered: int = 0
    rows_compared: int = 0
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    # Aggregated diagnosis of the line-ladder mismatch, keyed
    # "<sport>:<market>". This is the artifact's most useful output when
    # nothing clears the bar: it names the markets whose generated lines never
    # appear on the book at all.
    line_coverage: dict[str, dict[str, Any]] = Field(default_factory=dict)
    rows: list[SuperbetComparisonRow] = Field(default_factory=list)
