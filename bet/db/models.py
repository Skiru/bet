"""SQLAlchemy models and pydantic schemas for bet repo (minimal initial set).

This file contains ORM models used by the repository layer. Keep them small and
add fields as the schema evolves. All write operations should go through
bet.db.repository to centralize business rules.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Integer, DateTime, Text, JSON
from sqlalchemy.dialects.sqlite import BLOB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True, nullable=False)
    event_time = Column(DateTime, index=True, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MarketOdds(Base):
    __tablename__ = "market_odds"

    id = Column(Integer, primary_key=True, index=True)
    market_id = Column(String, index=True, nullable=False)
    fixture_id = Column(Integer, nullable=False)
    odds_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, index=True, default=gen_uuid)
    artifact_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    schema_version = Column(String, nullable=False, default="v1")
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    supersedes_uuid = Column(String, nullable=True)
