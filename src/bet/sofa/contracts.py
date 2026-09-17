import enum
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
    INTERNAL_INCONSISTENT = "INTERNAL_INCONSISTENT"
    THIN_SAMPLE = "THIN_SAMPLE"
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
    has_xg: bool
    ground_type: str | None
    best_of: int | None

class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sofascore_event_id: int
    match_date_utc: datetime
    opponent: str
    value: float
    competition_id: int | None
    season_id: int | None
    venue: Literal["home", "away"] | None

class MetricSample(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    metric: str
    side_a: list[Observation]
    side_b: list[Observation]
    h2h: list[Observation]

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
    p_bar: float
    offered_odds: float
    required_odds: float
    edge: float | None
    surplus: float

class Coupon(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    created_at_utc: datetime
    singles: list[CouponRow]
