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
        # Booking points: yellows + 2 x straight reds + 1 extra for a second
        # yellow, which is what Superbet's "Liczba kartek" settles. Same
        # counting-events tolerance as the yellow-only metrics beside them --
        # the two feeds behind it differ by at most one point per untyped red.
        "cards_points_total",
        "cards_points_for",
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
    # The first leg's score, **mapped onto tonight's home and away sides**.
    #
    # Mapped at discovery, where the two fixtures' team ids are both in hand,
    # because the sides swap between legs and a raw pair here would be read the
    # wrong way round exactly half the time. None when there is no first leg,
    # or when its score could not be read.
    #
    # Why it is worth a request: a level tie going into the second leg is not
    # the same match as either side's last ten, and it is the one piece of
    # stakes context that changes an UNDER on cards or fouls. On 2026-09-03 the
    # biggest derby of the day was the second leg of a 0-0 quarter-final and
    # nothing in the pipeline knew.
    previous_leg_goals_home: int | None = None
    previous_leg_goals_away: int | None = None
    # The provider's own ids for tonight's two sides, carried so a rule can pin
    # a *pair* of clubs rather than a spelling. ``EventRecord.provider_team_ids``
    # has them, and the dossier does not carry the event record.
    home_team_id: str | None = None
    away_team_id: str | None = None


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


# Sources whose exhaustion shrinks the *slate* rather than only costing
# corroboration.
#
# ``highlightly`` is the one that matters: it drives discovery breadth, so
# running out of quota removes about 77% of the day's fixtures (memory note
# ``highlightly-drives-discovery``). On 2026-09-03 it was 101/100 before the
# run started, 20,961 of 21,925 rows came out SINGLE_SOURCE, and DISCOVER
# reported OK.
SLATE_CRITICAL_SOURCES = frozenset({"highlightly"})


class EventListV1(StrictBaseModel):
    """DISCOVER artifact: a list of events for a given date."""

    # Minted by DISCOVER and carried through ENRICH and ANALYZE, so every
    # artifact and every pipeline_runs row can be traced to one run.
    run_id: str = ""
    generated_at: str
    date: str
    sports: list[Sport] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    # Per-source diagnostics, lifted off the adapters so the step's summary can
    # act on them rather than only log them. Empty is the healthy state.
    source_errors: dict[str, list[str]] = Field(default_factory=dict)
    # Reasons this slate is smaller than the day actually is. Non-empty means
    # the run must not be read as a survey of what was available -- see
    # ``SLATE_CRITICAL_SOURCES``. Defaulted empty so an EVENT_LIST written
    # before 2026-09-03 still validates and still reads as healthy.
    degraded_reasons: list[str] = Field(default_factory=list)


class ProviderValue(StrictBaseModel):
    """One raw observation of a canonical metric from a single provider."""

    provider: PROVIDER_NAMES
    match_id: str
    match_date: str
    opponent: str
    value: float
    observed_at: str
    # Which competition and which season this historical match belongs to, in
    # the *provider's* own ids -- never a name, because the name is the part
    # that drifts and the id is what the provider actually keys on.
    #
    # Both were on bzzoiro's normalised fixture row all along (`league_id`,
    # `season_id`) and were dropped on the floor here, which is what let the
    # 2026-09-01 sheet count a July club friendly and a match from the previous
    # season as equal trials to a league fixture tonight. ANALYZE reads them in
    # ``scope_values``; nothing else does, and nothing computes a statistic
    # from them.
    #
    # Optional on purpose. A provider that does not say which competition a
    # match belonged to leaves these None, and an observation with None is
    # never dropped -- the same "unknown is not degraded" rule the veto,
    # entitlement and competition-tier paths already follow.
    competition_id: str | None = None
    season_id: str | None = None
    # Whether *the team this observation belongs to* was at home or away in
    # that historical match. Carried, never interpreted here -- the same rule
    # ``competition_id`` above follows.
    #
    # Why it exists: all three per-team losses of 2026-09-01 were bets on the
    # home side of tonight's fixture, priced off a sample that mixed that
    # team's home and away matches at equal weight. Sheffield United's five
    # corner observations, Preston's five shots on target and Birmingham's
    # five shots each pooled both venues, and the pooled mean is the only
    # number the sheet had. Home/away was on every provider's fixture row all
    # along -- ``_side_of``, ``home_away``, ``home_team.provider_team_id`` --
    # and was used to split *that match's* stats between the two sides, then
    # dropped rather than recorded.
    #
    # Football only, and set only where the provider says which side the team
    # was. Tennis leaves it None on purpose: ``_side_of`` there answers which
    # participant slot a player occupied in the draw, and calling slot one
    # "home" would invent a fact -- neither player is at home at a neutral
    # tournament. H2H observations leave it None too, for the reason
    # ``_team_total_rows`` already gives for refusing to read that bucket at
    # all: an H2H value has no marker for which side it belongs to, so it has
    # no venue either.
    #
    # None means "not stated", never "away". An observation with None is
    # dropped from neither sample; it is simply absent from the venue split,
    # which then fails its own minimum-size check and stays silent.
    venue: Literal["home", "away"] | None = None
    # Which surface this historical match was played on, in the provider's own
    # spelling ("Hard", "Clay", "Grass"). Tennis only; football providers do
    # not report it and leave it None.
    #
    # Why it exists: on 2026-09-02 the only row on the whole sheet that beat
    # its price was Boulter-Muchova `aces_total` OVER 5.5 at 2.07, off a
    # sample whose median was 10.5. All eight of Muchova's observations were
    # Wimbledon and Bad Homburg -- grass -- and she had *no* hard-court match
    # in the sample at all; Boulter's was five-ninths grass. Median match-total
    # aces by surface: Boulter hard 6.0 (n=41) against grass 9.0, Muchova hard
    # 5.0 (n=60) against grass 11.0. The US Open is hard, so Superbet's 5.5 sat
    # exactly between the two players' hard-court medians and our 10.5 was an
    # artefact of a surface nobody was playing on.
    #
    # tennis_abstract.py had `surf` on every row all along and dropped it here,
    # the same way `league_id`/`season_id` were dropped before `competition_id`
    # existed. ANALYZE reads it in ``scope_values``; nothing computes a
    # statistic from it.
    #
    # Optional on the same "unknown is not degraded" rule as the two fields
    # above: an observation with None is never dropped, and a fixture whose own
    # surface cannot be established filters nothing.
    surface: str | None = None
    # Which *draw* this historical match belonged to: ``"GRAND_SLAM"``,
    # ``"TOUR"`` or None. Tennis only.
    #
    # Deliberately the draw and not the format. Men's Grand Slam main-draw
    # singles is the whole of best-of-five in professional tennis today, so
    # GRAND_SLAM means best-of-five in an ATP sample and best-of-three in a WTA
    # one -- and this field is set at ingest, where the *fixture* being priced
    # is not the thing being described. Recording "BO5" here would make every
    # WTA slam observation a lie. ``scope_values`` does the interpreting, on
    # the same "carried, never interpreted here" rule ``competition_id``
    # follows, and it has the fixture's own pinned format to interpret against.
    #
    # Why it exists: it is the discriminator the BO5 gate never had. Before it,
    # ``analyze._sample_is_best_of_five`` had to guess the draw from match
    # length -- four-or-more sets is proof of best-of-five -- and a share
    # threshold on that guess cannot distinguish a best-of-five won 3-0 from a
    # best-of-three won 2-1. Measured on the 2026-09-03 ATP slate: 225 of 474
    # ``total_sets`` observations were exactly three sets and therefore
    # unreadable either way, all 15 fixtures scored under the ⅓ threshold, and
    # the whole of ATP was suppressed -- including Fritz, whose six 2026 Grand
    # Slam wins all came in straight sets and scored zero.
    #
    # tennis-abstract has carried it as ``level`` on all 78,750 cached rows
    # ("G" = Grand Slam) and espn-tennis names the tournament, which the same
    # ``config/tennis_match_format.json`` pin resolves. Both were dropped on
    # the floor here, exactly as ``surf`` and ``league_id`` were before them.
    #
    # None means "not stated" and is never inferred from a name we do not
    # recognise: mislabelling a slam TOUR would silently delete real
    # best-of-five observations, which is worse than admitting ignorance.
    match_level: str | None = None
    # Why this observation is less than certain, in one word, or None when
    # nothing is wrong with it. Set today only by the card-points metrics,
    # where the value depends on a second endpoint that can be incomplete:
    # ``RED_TYPE_UNKNOWN`` (reds counted but not typed, so each is charged as
    # a straight red), ``RED_COUNT_CONFLICT`` (the two feeds disagree on how
    # many reds there were and the larger count was taken).
    #
    # Carried, never interpreted here, on the same rule ``competition_id`` and
    # ``surface`` follow. ANALYZE counts the flags per sample and prints them
    # on the row; nothing computes a statistic from them, and an observation
    # carrying one is never dropped -- an observation that *could not* be
    # computed at all never reaches this class.
    quality_flag: str | None = None
    # When two providers reported this one match differently, the lowest and
    # highest value any of them gave. Both None -- the common case -- means
    # every provider that saw the match agreed, or only one did.
    #
    # Set on the *representative* observation ``analyze._representative``
    # keeps, so the disagreement survives the collapse instead of being
    # silently resolved by a median. What the collapse used to do was keep the
    # lower value (median_low over a pair keeps the smaller), which favours
    # every UNDER on every conflicted match: on 2026-09-03 Náutico's 6-against-8
    # and América's 8-against-4 both entered their samples as the smaller
    # number, and every card row on the slate is an UNDER.
    conflict_low: float | None = None
    conflict_high: float | None = None


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

    # The published track record of the picks counted into ``agree``/``oppose``,
    # carried under the same rule as everything else here: read beside the
    # confidence figure, never into it.
    #
    # ``rated`` is how many counted picks came with a record at all. Only
    # ZawodTyper publishes one, so an unrated column is the normal case and not
    # a fault -- and an absent record is not a bad record, which is why nothing
    # is ever penalised for missing it.
    #
    # ``agree_record_low``/``oppose_record_low`` are the Wilson lower bound of
    # each side's stated hits over its stated bet count, pooled across the
    # tipsters on that side. The raw percentage is deliberately not carried: it
    # reads 84% from thirteen bets as better than 69% from fifty-three, the same
    # inversion ``p_low`` exists to prevent. The bound stays a floor on a
    # *self-reported, unaudited* record computed without the odds those bets
    # were taken at -- 46% at 2.50 profits and 66% at 1.30 ruins -- so it orders
    # tipsters against each other and never becomes a probability about this row.
    #
    # ``agree_unproven``/``oppose_unproven`` count the rated picks on each side
    # whose bound falls below 0.50, i.e. whose own published record does not
    # establish them as better than a coin flip. They still count into
    # ``agree``/``oppose``, because what a tipster said is a fact about the
    # fixture regardless of their record; the counts are here so "2/3" cannot
    # be read as support when both backers are 25%-from-eight-bets.
    #
    # They are split by side rather than pooled because a cell reading "0/1"
    # with one pooled unproven count cannot say whether the weak record belongs
    # to the tipster who backed the row or the one who opposed it -- and those
    # are opposite pieces of news.
    rated: int = 0
    agree_record_low: float | None = None
    oppose_record_low: float | None = None
    agree_unproven: int = 0
    oppose_unproven: int = 0


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
    # The book's own probability for this exact outcome, overround removed
    # against the opposite side of the same rung. None when the book posted
    # only one side.
    #
    # On the sheet as well as on the comparison row because the offer file is
    # the scarce input in this whole pipeline -- it is refetched every run and
    # cannot be reconstructed afterwards -- and a sheet that carries it can be
    # re-priced against a different ``k`` months later without it.
    implied_probability: float | None = None

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
    # The same probability with no conservatism in it: the count model read at
    # the sample's own centre, or the raw hit rate on a market no count model
    # is fitted to. Never a ranking key and never a floor -- it exists so the
    # sheet can be compared to a bookmaker's devigged price on equal terms.
    #
    # ``p_low`` cannot do that job. It is a lower bound with a tier margin
    # stacked on top of it downstream, so "our number minus the book's" is
    # dominated by our own conservatism: on 2026-09-01 every row that cleared
    # the price gate sat 8-13 points above devigged Superbet *by construction*,
    # whatever its sample said, and the gate meant to catch a broken sample
    # could not tell one from a good one. Defaults to ``p_low`` so a sheet
    # written before this field existed still validates.
    p_central: float | None = None
    mean: float
    median: float
    # The sample's most common value, its smallest and its largest.
    #
    # On the row because the rung scorer needs them and re-deriving them from
    # the dossier at coupon time would mean re-applying ``scope_values`` and
    # the per-day collapse -- two chances to price a rung against a different
    # sample from the one that produced its hit count.
    #
    # ``mode`` is the lowest of the tied modes, which is the same
    # ``statistics.multimode`` tie-break ``_representative`` uses for a
    # different reason: pick a value that occurred, deterministically.
    mode: float | None = None
    sample_min: float | None = None
    sample_max: float | None = None
    # The sample's standard deviation, floored at sqrt(mean) because a count
    # process cannot be tighter than Poisson and a short sample routinely
    # looks it -- Torino/Monza's six scoped corner observations on 2026-09-01
    # were {6,6,6,6,7,7}, variance 0.27 against a mean of 6.33, and the match
    # returned 16.
    #
    # It is on the row so that "this sample disagrees with the book" can be
    # asked in units of the sample's own spread rather than as a ratio. The
    # first version of that check used mean/ladder_median and fired on 29.6%
    # of one day's samples -- 53% of goals_for against 0% of corners_total,
    # entirely because a 0.3-goal gap is a third of a half-time total and a
    # thirtieth of a shots total. Normalised here it fires on 3.1%, evenly
    # across markets. 0.0 on a percentage market, which has no count model.
    dispersion: float = 0.0
    # ``mean`` pulled toward this market's pinned prior by n/(n+SHRINKAGE_K),
    # and the centre ``p_low``/``p_central`` are actually computed from. Read
    # it beside ``mean``: the gap between the two is how much of this row's
    # price is the sample's own claim, and how much is the market-wide
    # average standing in for observations the sample does not have.
    #
    # The 2026-09-01 file would have shown Sheffield United's corners at
    # mean 2.80, shrunk_mean 4.09, against a devigged ladder median of 5.76.
    # The match returned 5.
    #
    # None on a percentage market, which has no count model fitted. Equal to
    # ``mean`` when the market has no pinned prior.
    shrunk_mean: float | None = None
    # What moved ``shrunk_mean`` away from ``mean`` beyond the market prior,
    # in words. Set today only by the referee blend on card match totals, which
    # is the one adjustment that brings in a number from outside the sample
    # entirely -- so a reader who sees a centre 0.8 cards above the sample's own
    # mean can find out why without re-deriving it.
    centre_note: str | None = None
    # Which side of *tonight's* fixture this row's subject plays, when that
    # selects the shrinkage target. Football per-team rows only: a match total
    # has no venue of its own, and no tennis or player market has a measured
    # split. See analyze.shrunk_centre.
    #
    # Carried so the price is auditable from the artifact alone. Without it a
    # reader can see that ``shrunk_mean`` moved away from ``mean`` but not
    # which of the two priors it moved toward, and the home and away targets
    # differ by a full corner on ``corners_for``.
    venue: Literal["home", "away"] | None = None
    sources: list[str] = Field(default_factory=list)
    # ``PARTIAL_AGREE`` added 2026-09-03: a second provider saw some of this
    # sample but under half of it. It used to read AGREE, and ``tier_for_row``
    # reads AGREE as "corroborated" and hands out CALL -- on the 2026-09-03
    # Grenal that word covered 3 corroborated matches out of 20.
    cross_provider_agreement: Literal[
        "AGREE", "PARTIAL_AGREE", "DISAGREE", "SINGLE_SOURCE", "NOT_APPLICABLE"
    ]
    # How many distinct matches in this sample a second provider also reported.
    # Reported because ``cross_provider_agreement`` is a word and this is the
    # evidence behind it: "AGREE" used to be granted on a single corroborated
    # match out of twenty-three, and nothing on the row said so. See
    # ``analyze.MIN_CORROBORATED_MATCHES``.
    corroborated_matches: int = 0
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    # Why ``confidence`` is not HIGH, when the reason is not simply the total.
    # ``ONE_SIDED_SAMPLE`` means the observations are there but nearly all of
    # them describe one of the two participants -- an n of 14 built from 3 and
    # 11 is not the settled sample the total suggests. None when the total
    # alone explains the tier.
    confidence_reason: str | None = None
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
    # ``{reason: count}`` for observations ``scope_values`` removed from this
    # row's sample *before* hits, sample_size, mean, median and p_low were
    # computed. Empty is the common case.
    #
    # It is reported rather than merely applied because the filter changes the
    # number the operator bets against. On 2026-09-01 five of Bromley's nine
    # "matches" were July friendlies; the row said 9/9 and p_low 0.701, the
    # four competitive ones say 4/4 and 0.510, and only the second is a claim
    # about tonight. A sample that was silently cut is not more auditable than
    # one that was silently padded.
    sample_excluded: dict[str, int] = Field(default_factory=dict)
    # Structural reasons this row may not be a CALL, however large its sample.
    #
    # A *ceiling*, not a step down. ``context_flags``' ARGUES_AGAINST steps a
    # tier once and can therefore take a LEAN to WEAK; these say "this row is
    # at best a lean" and leave a row that was already weaker alone. The
    # difference matters because several of them fire together on the same
    # fixture -- a derby, in a knockout second leg, with no referee named --
    # and three reasons to doubt a fixture do not make it three tiers worse.
    #
    # Set by ANALYZE, read by ``bet_builder_draft.tier_for_row``, printed in
    # the coupon's caveats. Never touches ``p_low`` or ``p_central``.
    lean_ceiling_reasons: list[str] = Field(default_factory=list)
    # ``{reason: count}`` for observations in this row's sample that carry a
    # ``ProviderValue.quality_flag`` -- an observation that was *used* but is
    # less than certain, as opposed to ``sample_excluded``'s observations that
    # were removed. Today only the card-points metrics populate it.
    observation_flags: dict[str, int] = Field(default_factory=dict)


class ResultMarketConsensus(StrictBaseModel):
    """What ~26 bookmakers and one model think about a fixture's *result*.

    A different market from every row on this sheet, carried next to them for
    the same reason ``TipsterEventSignal.public_lean`` is carried next to the
    tipster column: it is real information about the fixture, it is information
    about a bet this pipeline does not price, and the two must never be summed.
    Nothing here has a ``p_low``, because nothing here has a sample -- these are
    a snapshot of prices and a model's forecast, and MARKET_CONTEXT's whole
    docstring is about why a price may not become an observation.

    Why it is on the sheet at all. MARKET_CONTEXT has been downloading this
    block since 2026-08-28 and paying for it -- 26 bookmakers on most fixtures
    -- and until 2026-09-03 not one number in it reached any artifact a reader
    opens. ``market_signal_for_row`` is per-row and per-market, and its
    ``SIGNAL_MARKETS`` gate covers exactly ``corners_total`` and
    ``goals_total``, so the 1X2, double chance and BTTS quotes were fetched,
    parsed, validated and dropped. The cost was measured on the 2026-09-03
    SUPERBETS board: five of fourteen legs across six slips were result-family
    bets, the sheet had no VALUE rows on any of those six fixtures, and there
    was no way to tell "we priced this and it was not worth it" from "we have
    never looked at this market".

    **De-vigged, and from one bookmaker's own complete market.** The same rule
    ``_same_bookmaker_probability`` applies to totals, for the same reason: the
    best price on each outcome taken from a different book is a synthetic
    market with an overround near zero, and normalising that reports a
    confidence no bookmaker actually holds. Pinnacle first when it prices the
    whole market, otherwise the first book that does.
    """

    event_id: str
    # Copied from the event list so the block reads standalone. Empty when
    # ANALYZE ran without --event-list; the probabilities are still correct,
    # because the quotes carry HOME/DRAW/AWAY themselves and never need a name
    # to be computed -- only to be read.
    home_team: str = ""
    away_team: str = ""
    # De-vigged 1X2. All three or none: two thirds of a market cannot be
    # normalised, and reporting the raw 1/odds instead would hand the reader
    # the bookmaker's margin as if it were probability.
    p_home: float | None = None
    p_draw: float | None = None
    p_away: float | None = None
    # Derived from the de-vigged 1X2 above by addition, never read from the
    # feed's own double_chance quotes. Those carry a second, independent
    # overround, so a 1X taken from them and a p_home taken from the 1X2 would
    # not be two views of one market -- they would disagree by the difference
    # between two margins and look like a signal.
    p_1x: float | None = None
    p_12: float | None = None
    p_x2: float | None = None
    p_btts_yes: float | None = None
    p_btts_no: float | None = None
    # Which book each de-vig came from, because "de-vigged" is only meaningful
    # with the source attached.
    result_bookmaker: str | None = None
    btts_bookmaker: str | None = None
    bookmakers_count: int = 0
    # The CatBoost model's own read, for the same three outcomes. Kept beside
    # the market rather than blended into it: two numbers that disagree are the
    # useful output, and an average of them hides exactly the case worth seeing.
    model_p_home: float | None = None
    model_p_draw: float | None = None
    model_p_away: float | None = None
    model_p_btts_yes: float | None = None
    model_version: str | None = None
    # Why a field above is None, when it is. Empty when everything resolved.
    reasons: list[str] = Field(default_factory=list)


class StatsSheetV1(StrictBaseModel):
    """ANALYZE artifact: all stats-sheet rows for a dossier collection."""

    run_id: str = ""
    date: str = ""
    generated_at: str
    rows: list[StatsSheetRow] = Field(default_factory=list)
    # One entry per fixture MARKET_CONTEXT could read a result market for.
    # Deliberately a sibling of ``rows`` and not a column on them: it is
    # per-fixture, not per-(market, line, direction), and putting it on a row
    # would invite exactly the arithmetic it must never take part in -- a
    # corners row's p_low multiplied by a 1X2 price.
    result_markets: list[ResultMarketConsensus] = Field(default_factory=list)


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

    # A tennis block lived here between 2026-08-30 and 2026-09-02
    # (prob_games_over_*, prob_sets_over_25, expected_total_*,
    # prob_player_*_wins). It was filled by exactly one provider, bzzoiro's
    # tennis product, and was removed with it: MARKET_CONTEXT is football-only
    # now, so every one of those fields could only ever have been None. A
    # contract field no producer can fill is a promise the artifact keeps
    # making and never keeps.


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


# The result family: markets Superbet offers, this pipeline does not price, and
# which are nonetheless most of what a SUPERBETS slip is built from.
#
# Named for the quantity they settle on rather than for Superbet's Polish, so a
# reader can tell at a glance which of them a totals row could ever have spoken
# to. None of them can: a total counts events inside a match, and every code
# here settles on who was ahead when a whistle went.
RESULT_MARKET_FAMILIES = Literal[
    "1x2",
    "1x2_1h",
    "1x2_2h",
    "double_chance",
    "double_chance_1h",
    "double_chance_2h",
    "btts",
    "btts_1h",
    "btts_2h",
    "draw_no_bet",
    "draw_no_bet_1h",
    "draw_no_bet_2h",
]


class SuperbetResultLine(StrictBaseModel):
    """One offered outcome in a market this pipeline deliberately does not price.

    This exists because "no VALUE rows on this fixture" and "nobody looked at
    the market this fixture is actually bet on" were indistinguishable in the
    artifact, and on 2026-09-03 they were the same six fixtures: every leg of
    the day's six SUPERBETS slips that was not a total -- match result, double
    chance, both-teams-to-score, a double chance on a single half -- was dropped
    by ``normalize_lines`` before it could even be counted as unmapped, because
    ``parse_outcome`` only recognises "powyżej"/"poniżej" and returns None for
    "1X". Five of the fourteen legs on the operator's screen were invisible to
    the whole pipeline, and the sheet said nothing at all rather than saying so.

    **A price and never a probability, and never a row.** These carry no
    ``p_low``, no sample and no tier, because nothing in this pipeline measures
    what they settle on: ENRICH's samples are counts of corners, cards, fouls,
    shots and goals, and no arithmetic over those produces P(the home side is
    ahead at full time). They are recorded so the operator can see what he is
    being offered and compare it himself against
    ``ResultMarketConsensus`` -- the 1X2/BTTS read from bzzoiro's ~26-bookmaker
    grid, which reaches the sheet for exactly this purpose. Wiring either into
    a row, a tier or a coupon leg would be inventing the estimate this field
    exists to admit is missing.
    """

    family: RESULT_MARKET_FAMILIES
    # HOME/DRAW/AWAY for a 1X2 and a draw-no-bet, 1X/X2/12 for a double chance,
    # YES/NO for both-teams-to-score. Superbet writes the same three outcomes
    # four different ways -- "1"/"X"/"2" on the match, the club's own name on a
    # half, "remis" for the draw -- and the code here is the normalised form so
    # a reader is not comparing spellings.
    outcome: Literal["HOME", "DRAW", "AWAY", "1X", "X2", "12", "YES", "NO"]
    price: float
    status: str = "active"
    # Superbet's own strings, verbatim, for the same reason ``SuperbetLine``
    # keeps them: the mapping from Polish prose to a family code is the part
    # most likely to be wrong and cannot be audited once the source is gone.
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
    # Offered, understood, and deliberately not priced. Distinct from
    # ``unmapped_markets`` in the way that matters to a reader: that list means
    # "Superbet published something we could not identify", this one means "we
    # identified it exactly and this pipeline has no sample that speaks to it".
    # Only the first reading is a mapping bug.
    result_market_lines: list[SuperbetResultLine] = Field(default_factory=list)


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
    # Fixtures Superbet *did* match but whose lines were never fetched, because
    # ``max_events`` cut the list short. They land in
    # ``our_events_without_offer`` alongside genuine absences and are
    # indistinguishable there -- which stopped being a reporting nuisance and
    # became a correctness problem on 2026-09-02, when ENRICH started reading
    # this artifact as a slate gate. A truncated board cannot tell a fixture
    # the book declines to price from one nobody asked about, so
    # ``enrich.build_slate_gate`` switches that rule off entirely when this is
    # non-zero. Measured on the live 2026-09-03 slate: a cap of 30 made 9
    # priced fixtures read as unpriced.
    events_capped: int = 0
    events: list[SuperbetEventOffer] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    # How many fixtures were named by a Betradar id rather than by comparing
    # spellings, and what the OddsPapi bridge cost to find out. Separate from
    # ``data_gaps`` on purpose: a bridge that did not run is a missed
    # optimisation, not a degraded betting day, and must not make the step
    # PARTIAL.
    events_matched_by_id: int = 0
    identity_bridge: dict[str, Any] = Field(default_factory=dict)
    # Every fixture on the board, in a sport this pipeline reads, that did not
    # join to one of our events. Identity only; see ``SuperbetBoardEvent``.
    #
    # Bounded by the sports filter, which is what keeps it small: the
    # 2026-09-03 board carried 4,041 events in window and 3,402 of them were
    # esports, simulated football and sports with no reader here.
    unmatched_events: list[SuperbetBoardEvent] = Field(default_factory=list)


class SuperbetBoardEvent(StrictBaseModel):
    """One fixture Superbet listed and this pipeline did not price.

    Identity only -- no lines, because lines cost one request per fixture and
    the whole point of recording these is that they were *not* worth one.

    They used to be counted and discarded (``events_unmatched``), which made
    the single most important question about a betting day unanswerable from
    the artifact: how much of what the operator can actually bet on does this
    pipeline reach, and what is in the way. On 2026-09-03 the answer turned out
    to be 24 of 150 offered football fixtures, and the obstacle was not the
    matcher -- see ``resolve_board_to_reference`` -- but that is not something
    anybody could have read off the file.
    """

    superbet_event_id: str
    match_name: str = ""
    sport: str = ""
    kickoff: str = ""
    betradar_id: str | None = None


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
    # The prop's subject. Two players' VALUE rows on the same market and line
    # differ in nothing but price without it, and a subject the operator
    # cannot identify is not a bet.
    player_name: str | None = None
    player_id: str | None = None
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
    # Superbet's own probability for this exact outcome, overround removed
    # against the opposite side of the same rung.
    #
    # Recorded on every two-sided row, whatever the verdict, because it is the
    # scarce input: the offer file is refetched every run and cannot be
    # reconstructed afterwards, and this is the number the bar now shrinks
    # toward (``bet_builder_draft.bar_components``) and the number the ladder
    # centre is read from. Before 2026-09-03 it was computed inside
    # ``build_coupons``, used for one threshold, and thrown away.
    #
    # None when the book posted only one side of the line. That is common on
    # one-way markets and it disables the market prior for the row rather than
    # defaulting it: we cannot shrink toward a price we cannot read.
    superbet_implied_probability: float | None = None


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
