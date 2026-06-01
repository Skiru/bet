"""Test that CLI refuses to run without --adapter and that orchestrator persistence works."""
from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bet.db.models import Base
from bet.orchestrator import run_pipeline_for_date
from bet.adapters.base import BookmakerAdapter


def test_cli_requires_adapter():
    # simulate running script without args
    p = subprocess.Popen([sys.executable, "scripts/pipeline_orchestrator.py", "--date", "2026-06-01"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    assert p.returncode != 0


class MockAdapter(BookmakerAdapter):
    def fetch_events(self, date):
        return [{"id": "m1", "home": "Alpha", "away": "Beta", "event_time": datetime(2026,6,1,18,0,tzinfo=timezone.utc)}]


def test_orchestrator_persistence(tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    adapter = MockAdapter()
    res = run_pipeline_for_date(date(2026,6,1), adapter, dry_run=True, allow_write=False, session_maker=SessionLocal)
    assert res["artifacts"] == {}
    res2 = run_pipeline_for_date(date(2026,6,1), adapter, dry_run=False, allow_write=True, session_maker=SessionLocal)
    assert "signals_uuid" in res2["artifacts"]
    assert "coupons_uuid" in res2["artifacts"]
