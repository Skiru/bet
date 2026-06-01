"""Pipeline contracts: pydantic models defining data flowing between stages."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Dict, Literal

from pydantic import BaseModel, Field, validator, confloat


class RawEvent(BaseModel):
    source: str
    external_id: str
    data: Dict
    fetched_at: datetime


class CanonicalFixture(BaseModel):
    external_id: str
    home_team: str
    away_team: str
    event_time: datetime  # must be timezone-aware UTC
    metadata: Dict = Field(default_factory=dict)

    @validator("event_time", pre=True)
    def ensure_dt_utc(cls, v):
        # accept datetime, ISO string, or epoch; ensure timezone-aware UTC
        from datetime import datetime, timezone
        try:
            from dateutil import parser
        except Exception as e:
            raise RuntimeError("dateutil is required for parsing event_time strings; add python-dateutil to dependencies") from e

        if isinstance(v, datetime):
            if v.tzinfo is None:
                # interpret naive as UTC
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        if isinstance(v, str):
            dt = parser.isoparse(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc)
        raise ValueError("Unsupported event_time type")


class FixtureFeatures(BaseModel):
    external_id: str
    features: Dict = Field(default_factory=dict)


class Signal(BaseModel):
    external_id: str
    pick: Literal["home", "away", "draw"]
    confidence: confloat(ge=0.0, le=1.0)
    score_details: Dict = Field(default_factory=dict)


class Coupon(BaseModel):
    id: str
    picks: List[Signal] = Field(default_factory=list)
    stake: float = 1.0


class SettlementPlan(BaseModel):
    coupon_id: str
    expected_payout: float
    settled: bool = False
    details: Dict = Field(default_factory=dict)
