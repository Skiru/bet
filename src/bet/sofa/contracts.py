import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bet.sofa.schedule import FixtureSchedule

Sport = Literal["football", "tennis"]
Direction = Literal["OVER", "UNDER"]
Readiness = Literal["READY", "PARTIAL", "BLOCKED"]


class GapReason(StrEnum):
    NO_ENTITY_FOUND = "NO_ENTITY_FOUND"
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    NO_MATCHING_EVENT = "NO_MATCHING_EVENT"
    EVENT_NOT_FINISHED = "EVENT_NOT_FINISHED"
    NO_STATISTICS = "NO_STATISTICS"
    NO_INCIDENTS = "NO_INCIDENTS"
    STAT_KEY_ABSENT = "STAT_KEY_ABSENT"
    ALL_ZERO_SAMPLE = "ALL_ZERO_SAMPLE"
    OUTSIDE_MODEL_RESOLUTION = "OUTSIDE_MODEL_RESOLUTION"
    INTERNAL_INCONSISTENT = "INTERNAL_INCONSISTENT"
    # One Sofascore entity id carrying two squads (2026-10-01): a side that
    # "played" twice within a day. Its sample describes nobody, so it is empty.
    ENTITY_CONFLICT = "ENTITY_CONFLICT"
    # A club's second squad filed under the first team's id (2026-10-02,
    # reserve_squads): its matches are out of the first team's sample, or the
    # side is empty when the fixture itself is the second squad's.
    RESERVE_SQUAD = "RESERVE_SQUAD"
    # A full-match 0-0 the same payload shows was not counted (2026-10-03,
    # metrics.zero_pair_not_recorded): not an observation, and not a grade.
    ZERO_NOT_RECORDED = "ZERO_NOT_RECORDED"
    # An incident list that is no card record (2026-10-04, metrics.
    # cards_not_recorded): a goals-and-dismissals feed - no substitution, no
    # yellow - read as card points would count the red cards only.
    CARDS_NOT_RECORDED = "CARDS_NOT_RECORDED"
    THIN_SAMPLE = "THIN_SAMPLE"
    SURFACE_UNKNOWN = "SURFACE_UNKNOWN"
    NO_PRICE = "NO_PRICE"
    STALE_PRICE = "STALE_PRICE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


class BoardFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    superbet_event_id: str
    sport: Sport
    match_name: str
    side_a: str
    side_b: str
    kickoff_utc: datetime
    # Superbet's own competition ids. It sends no competition *name* at all, so
    # these are the only handle the board has on "which competition is this"
    # before RESOLVE. Kept so the question "is this slate descending into
    # competitions with no data" can be answered from the artifact instead of
    # a live probe, and so BOARD can exclude by id (F12).
    tournament_id: int | None = None
    category_id: int | None = None


class RefereeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    games: int
    yellow_cards: int
    red_cards: int
    yellow_red_cards: int


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    superbet_event_ids: list[str]
    sport: Sport
    kickoff_utc: datetime
    home_name: str
    away_name: str
    home_entity_id: int
    away_entity_id: int
    competition_name: str
    competition_id: int
    season_id: int
    category_name: str
    identity: Literal["CONFIRMED", "FUZZY"]
    round_number: int | None
    round_name: str | None
    cup_round_type: int | None
    previous_leg_event_id: int | None
    venue_name: str | None
    referee: RefereeRecord | None
    ground_type: str | None
    # Sofascore's defaultPeriodCount. For tennis this is the real best-of
    # (3 or 5) and is worth having; for football it is the number of halves,
    # which is why the old name `best_of` said something untrue about every
    # football fixture in the artifact. Renamed rather than removed because the
    # tennis value is correct and becomes load-bearing at a Grand Slam.
    #
    # `has_xg` is gone. It read hasXg off a match that had not been played, so
    # it was False for the whole of the Bundesliga, and nothing consumed it —
    # the xG gate lives in metrics.py and asks the right question of each
    # historical match separately. A field that lies and nobody reads is a trap
    # for whoever reads it next.
    default_period_count: int | None
    # Superbet's own kickoff, and how far it is from Sofascore's.
    #
    # The two sources disagree by a whole timezone for ITF tournaments —
    # Sofascore appears to publish the tournament's local time as though it
    # were UTC, a signature confirmed on 12 of 12 cases where the city's offset
    # could be assigned. The error runs the wrong way: a finished match looks
    # upcoming. Superbet's clock is the one that decides whether a market is
    # open, because Superbet is who accepts the bet (F26).
    superbet_kickoff_utc: datetime | None = None
    kickoff_disagreement_h: float | None = None
    # Sofascore's status.type when RESOLVE read /event/{id} (K14, 2026-10-05):
    # "postponed" / "canceled" here refuses the fixture in a stats-only
    # CONFIDENCE as FIXTURE_NOT_AS_SCHEDULED. Absent before 10-05.
    sofascore_status: str | None = None
    # Both sides national teams (Sofascore's homeTeam/awayTeam `national`),
    # read by RESOLVE from 2026-10-06; None when the payload did not say
    # (older days). CONFIDENCE judges such a sample by count, not by age
    # (epochs.NATIONAL_SAMPLE_AGE_FROM_UTC).
    national_teams: bool | None = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    match_date_utc: datetime
    opponent: str
    value: float
    # Minutes the subject was on the pitch, for a per-player observation only
    # (F54); None for every team and tennis metric, where it has no meaning.
    #
    # Carried because a substitute's twelve minutes and a starter's ninety are
    # not the same observation of the same quantity, and the sheet has no
    # other way to say so. It does not filter anything here — Superbet pays a
    # player market out on a cameo — but the row reports the profile so a
    # sample made of cameos cannot look like a sample made of starts.
    minutes: float | None = None
    competition_id: int | None
    season_id: int | None
    venue: Literal["home", "away"] | None


class MetricSample(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    metric: str
    side_a: list[Observation]
    side_b: list[Observation]
    h2h: list[Observation]


class PlayerSample(BaseModel):
    """F54. One footballer's own history of one metric.

    A third axis, alongside `_total` and `_for`. It cannot be folded into
    MetricSample: that model's two buckets are the two *sides*, and a fixture
    carries as many player samples as Superbet quotes players — 47 on one
    2026-09-24 MLS fixture.

    `side` is which of the two squads the player was matched in, kept so a row
    can be checked against the side it claims without re-running the name
    match, and so a coupon can say whose player it is.

    `appearances` is len(observations) by construction, but `squad_matches` is
    not: it is how many of the side's sampled matches carried a squad list at
    all. The difference is the honest denominator for "he played 6 of the last
    10", and without it a six-match sample from a ten-match history is
    indistinguishable from a six-match sample from a six-match one.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    metric: str
    player: str
    matched_name: str
    side: Literal["side_a", "side_b"]
    squad_matches: int
    observations: list[Observation]


class GapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reason: GapReason
    metric: str
    detail: str


class FixtureSamples(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    readiness: Readiness
    metrics: dict[str, MetricSample]
    gaps: list[GapEntry]
    # F54. Keyed "<metric>|<player as Superbet writes him>", which is exactly
    # the (market, subject) pair a rung carries, so SHEET looks a player rung
    # up without re-running the name match SAMPLES already did.
    players: dict[str, PlayerSample] = {}
    # bet.sofa.schedule (2026-10-04): make-up fixture, rest, congestion.
    # Absent on a fixture sampled before that day.
    schedule: FixtureSchedule | None = None


class PricedRung(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    market: str
    subject: str
    line: float
    over_odds: float | None
    under_odds: float | None
    fetched_at_utc: datetime


class FixtureOffer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    status: Literal["PRICED", "NO_PRICE"] | None = None
    rungs: list[PricedRung]
    unmapped_markets: list[str]
    # Where two Superbet listings of the same match quoted one rung
    # differently. Empty is the normal case; a non-empty list means the price
    # we used was chosen, not inherited from whichever listing came last (F27).
    price_collisions: list[str] = []
    # When a fetch first found Superbet reporting the match under way or over
    # (superbet.event_started). None = never seen started. A third start
    # signal beside the two clocks, which can both be late (2026-10-04).
    superbet_started_utc: datetime | None = None
    # Superbet's start time as the payload gave it at fetch (`utcDate`, the
    # earliest over the listings that still quote). RESOLVE froze the board's
    # clock in the morning; Superbet moves it, and an earlier move (six
    # fixtures on 2026-10-04, Seggerman - Tajima 08:00 -> 07:20) was invisible
    # to every kickoff gate. A third clock: the gates take the earliest.
    superbet_kickoff_seen_utc: datetime | None = None


class SheetRow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    sport: Sport
    market: str
    subject: str
    line: float
    direction: Direction
    sample_size: int
    sample_mean: float
    sample_sd: float
    centre: float
    p_central: float
    market_p: float | None
    ladder_centre: float | None
    ladder_sigma: float | None
    p_bar: float
    bar_reason: str | None
    # F48. The calibration correction subtracted from p_central before the
    # price blend. Without it published, p_bar cannot be re-derived from this
    # row's own fields and audit_coupon reports an arithmetic failure — which
    # is exactly what happened the moment the correction stopped being dead
    # code. A row has to describe its own arithmetic.
    calibration_correction: float = 0.0
    # Age in days of the NEWEST observation behind this row, or None when the
    # sample carried no usable date. The coupon gates on it: until 2026-09-21
    # only the price had a freshness limit, so the day's highest-surplus
    # single rested on a sample whose most recent match was 105 days old, and
    # nothing said so. Staleness and surplus are not independent — a sample
    # that has stopped tracking a player disagrees with the current price more
    # often, and the coupon sorts on exactly that disagreement.
    sample_newest_days: int | None = None
    # The sample's own frequency at this rung (hits/n), for empirical-frequency
    # metrics only. A tennis row is priced 75% from the price at n=10
    # (p_empirical_shrunk_to_price), so p_central - market_p shows a quarter of
    # the disagreement MAX_DISAGREEMENT was measured on; both disagreement
    # gates read this instead. On 2026-09-23 all 13 printed tennis singles
    # passed the gate only because it read p_central.
    sample_frequency: float | None = None
    required_odds: float
    offered_odds: float | None
    edge: float | None
    surplus: float | None
    verdict: Literal["VALUE", "LEAN", "BELOW_BAR", "NO_PRICE", "BLOCKED"]
    notes: list[str]
    # bet.sofa.epochs: "stats_only" on a row built under the 2026-10-05 rule
    # (the price is not in p_central); absent on an older sheet.
    epoch: str | None = None
    # K11: the rating's own forecast (football_rating / tennis_rating), never
    # blended with the price and never calibrated - shown beside the
    # confidence, never a gate. Stats-only rows only.
    forecast_p: float | None = None
    forecast_source: str | None = None
    # bet.sofa.epochs.LINK_SHARED_LEAGUE: the rating linked pairs only through
    # a league both sides call home (epochs.link_shared_league); absent on a
    # sheet built under the old link rule. rebuild_plan re-runs SHEET when a
    # build's rule and the sheet's differ.
    link_rule: str | None = None
    # bet.sofa.epochs.COUNT_DISPERSION: football counts priced with the
    # dispersion fitted on the history (bet.sofa.count_dispersion); absent on a
    # sheet built under the sample variance. rebuild_plan re-runs SHEET when a
    # build's rule and the sheet's differ.
    dispersion_rule: str | None = None
    # bet.sofa.epochs.TENNIS_SCOPED_TABLE: a tennis row priced from the
    # neighbour table cut by tier x gender (and the V5 rating start); absent
    # on a sheet built from the pooled table. rebuild_plan re-runs SHEET when
    # a build's rule and the sheet's differ.
    tennis_table_rule: str | None = None
    # bet.sofa.epochs.CARDS_CORRELATION: the cards joints' sides correlated at
    # the measured residual instead of independent; absent on a sheet built
    # without it. rebuild_plan re-runs SHEET when a build's rule and the
    # sheet's differ.
    cards_rule: str | None = None
    # bet.sofa.epochs.PER_MARKET_K: the football centres shrunk with the K of
    # their own market (bet.sofa.per_market_k); absent on a sheet built with
    # the sport's K. rebuild_plan re-runs SHEET when the rules differ.
    k_rule: str | None = None


ContextSignal = Literal[
    "MOTIVATION",  # stakes: dead rubber, must-win, relegation, points to defend
    "ROTATION",  # a rested or reserve XI, a cup tie between two league fixtures
    "ABSENCES",  # named starters out, injury or suspension
    "DERBY",  # rivalry, grudge or revenge match
    "SCHEDULE",  # fatigue, travel, back-to-back days, a long previous match
    "CONDITIONS",  # weather, pitch, altitude, indoor/outdoor switch
]


class Veto(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    market: str | None
    subject: str | None
    line: float | None
    direction: Direction | None
    reason_class: Literal["SAMPLE_UNINFORMATIVE", "CONTEXT", "PRICE", "OTHER"]
    reason: str
    # Which kind of CONTEXT, so the settlement audit can ask whether one kind
    # of read removes losers and another removes winners. Until 2026-09-23 a
    # "the world has changed" veto carried only free text, and 93 of the 102
    # vetoes of 2026-09-22 were filed as OTHER: nothing could say whether the
    # analysts' context read was worth anything.
    context: ContextSignal | None = None

    @model_validator(mode="after")
    def _context_only_on_context(self) -> "Veto":
        if self.context is not None and self.reason_class != "CONTEXT":
            raise ValueError(
                f"context={self.context!r} needs reason_class='CONTEXT', "
                f"got {self.reason_class!r}"
            )
        return self


LegVerdict = Literal["KEEP", "WATCH", "NO_BET"]
READ_SIDES = frozenset(
    {"OVER", "UNDER", "T1", "T2", "DRAW", "ODD", "EVEN", "YES", "NO"})
_EXACT_SCORE = re.compile(r"^\d+[:-]\d+$")
ReadAuthor = Literal["analyst", "verifier"]


class LegRead(BaseModel):
    """One person's read of a row: what the analyst or the verifier said.

    2026-10-04, SC Farense - Chaves goals_total UNDER 3.5: the analyst read
    the leg as WATCH (Chaves' matches 4/5/4/5 goals, two cup observations)
    and the verifier put it among the rows it would not stake (model 9 pp
    above its own sample's hit rate, 153 days over three competitions). The
    schema had no field for either, so the leg stayed in the PDF and lost.

    A read is persisted in ``runs/sofa/<date>/reads.json`` beside the
    vetoes, matched like a veto (a None field covers every value), and is
    consequential:

    * NO_BET and WATCH remove the row from the coupon (a veto by another
      name); the ledger grades the removed legs apart (removed:reads);
    * KEEP removes nothing; it records that the row was read.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    # For a measured sport's leg on the coupon (plan 2026-10-05, F7) `market`
    # is the leg's family (total, team_total, handicap, winner, ...).
    market: str | None
    subject: str | None
    line: float | None
    # OVER / UNDER, or a measured sport's side: T1 / T2 / DRAW / ODD / EVEN /
    # YES / NO / an exact score ("3:1"). See READ_SIDES.
    direction: str | None
    verdict: LegVerdict
    author: ReadAuthor
    reason: str = Field(min_length=1)
    context: ContextSignal | None = None
    # A measured sport's period (a hockey period, a quarter, a set, a CS2
    # map); None covers every period, as a None field always does.
    period: int | None = None

    @model_validator(mode="after")
    def _known_side(self) -> "LegRead":
        d = self.direction
        if d is not None and d not in READ_SIDES and not _EXACT_SCORE.match(d):
            raise ValueError(f"unknown direction {d!r}")
        return self


class CouponRow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    match_name: str
    kickoff_utc: datetime
    sport: Sport
    market: str
    subject: str
    line: float
    direction: Direction
    sample_size: int
    centre: float
    p_central: float
    market_p: float | None
    # Carried through from the sheet so the coupon row describes its own
    # arithmetic. `p_bar = w·(p_central − calibration_correction) + (1−w)·
    # market_p`, and without the correction three of 2026-09-21's 63 rows
    # could not be re-derived from the file the operator actually opens.
    calibration_correction: float = 0.0
    sample_newest_days: int | None = None
    p_bar: float
    offered_odds: float
    required_odds: float
    edge: float | None
    surplus: float


class Coupon(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    created_at_utc: datetime
    singles: list[CouponRow]
