"""Integration test that runs the orchestrator in dry-run and allow-write modes."""
from __future__ import annotations

from datetime import date, datetime, timezone
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bet.db.models import Base
from bet.orchestrator import run_pipeline_for_date
from bet.adapters.base import BookmakerAdapter


class MockAdapter(BookmakerAdapter):
    def fetch_events(self, date):
        return [{"id": "m1", "home": "Alpha", "away": "Beta", "event_time": datetime(2026,6,1,18,0,tzinfo=timezone.utc)}]


def test_orchestrator_dry_run_and_write(tmp_path, monkeypatch):
    # Setup in-memory sqlite and sessionmaker
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    adapter = MockAdapter()
    # Dry run should not persist artifacts
    res = run_pipeline_for_date(date(2026,6,1), adapter, dry_run=True, allow_write=False, session_maker=SessionLocal)
    assert res["artifacts"] == {}

    # Now allow write but still dry_run False
    res2 = run_pipeline_for_date(date(2026,6,1), adapter, dry_run=False, allow_write=True, session_maker=SessionLocal)
    assert "signals_uuid" in res2["artifacts"]
    assert "coupons_uuid" in res2["artifacts"]
