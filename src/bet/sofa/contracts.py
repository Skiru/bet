from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    required_odds: float
    offered_odds: float | None
    edge: float | None
    surplus: float | None
    verdict: Literal["VALUE", "LEAN", "BELOW_BAR", "NO_PRICE", "BLOCKED"]
    notes: list[str]


class Veto(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    market: str | None
    subject: str | None
    line: float | None
    direction: Direction | None
    reason_class: Literal["SAMPLE_UNINFORMATIVE", "CONTEXT", "PRICE", "OTHER"]
    reason: str


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
