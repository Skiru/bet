"""Pipeline contracts: pydantic models defining data flowing between stages."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class RawEvent(BaseModel):
    source: str
    external_id: str
    data: dict
    fetched_at: datetime


class CanonicalFixture(BaseModel):
    external_id: str
    home_team: str
    away_team: str
    event_time: datetime  # UTC-aware
    metadata: Optional[dict] = {}


class FixtureFeatures(BaseModel):
    external_id: str
    features: dict


class Signal(BaseModel):
    external_id: str
    pick: str  # 'home' | 'away' | 'draw'
    confidence: float
    score_details: dict = {}


class Coupon(BaseModel):
    id: str
    picks: List[Signal]
    stake: float = 1.0


class SettlementPlan(BaseModel):
    coupon_id: str
    expected_payout: float
    settled: bool = False
    details: Optional[dict] = {}
