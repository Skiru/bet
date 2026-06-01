"""Repository layer: canonical DB access functions.

All DB interactions should be performed through functions in this module. Keep
transactional boundaries clear and return ORM objects or simple serializable
structures suitable for tests.
"""
from __future__ import annotations

from typing import Optional, List
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select

from .models import Fixture, MarketOdds, Artifact


def upsert_fixture(db: Session, external_id: str, event_time: datetime, payload: dict) -> Fixture:
    stmt = select(Fixture).where(Fixture.external_id == external_id)
    res = db.execute(stmt).scalars().first()
    if res:
        res.event_time = event_time
        res.payload = payload
        db.add(res)
        db.flush()
        return res
    fixture = Fixture(external_id=external_id, event_time=event_time, payload=payload)
    db.add(fixture)
    db.flush()
    return fixture


def insert_market_odds(db: Session, market_id: str, fixture_id: int, odds_payload: dict) -> MarketOdds:
    mo = MarketOdds(market_id=market_id, fixture_id=fixture_id, odds_payload=odds_payload)
    db.add(mo)
    db.flush()
    return mo


def insert_artifact(db: Session, artifact_type: str, payload: dict, schema_version: str = "v1", superseded_by_uuid: Optional[str] = None) -> Artifact:
    art = Artifact(artifact_type=artifact_type, payload=payload, schema_version=schema_version, superseded_by_uuid=superseded_by_uuid)
    db.add(art)
    db.flush()
    return art


def mark_artifact_superseded(db: Session, uuid: str, superseded_by_uuid: str) -> Optional[Artifact]:
    stmt = select(Artifact).where(Artifact.uuid == uuid)
    art = db.execute(stmt).scalars().first()
    if not art:
        return None
    art.status = "superseded"
    art.superseded_by_uuid = superseded_by_uuid
    db.add(art)
    db.flush()
    return art


def list_artifacts_for_day(db: Session, day_start: datetime, day_end: datetime) -> List[Artifact]:
    stmt = select(Artifact).where(Artifact.created_at >= day_start).where(Artifact.created_at < day_end)
    res = db.execute(stmt).scalars().all()
    return res
