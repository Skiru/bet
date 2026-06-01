"""Orchestrator library: coordinates pipeline stages and persists artifacts via repository.

Design notes:
- The orchestrator is a library; do not execute it on import.
- Writes to DB are gated behind allow_write=True and an explicit sessionmaker provided
  (for tests we pass an in-memory sessionmaker).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from bet.db.repository import insert_artifact
from bet.db.connection import get_sessionmaker
from bet.utils.time import betting_day_range
from .service import run_single_day_pipeline
from .contracts import RawEvent


def run_pipeline_for_date(run_date: date, adapter, dry_run: bool = True, allow_write: bool = False, session_maker: Optional[object] = None, agent_id: Optional[str] = None) -> dict:
    """Run the pipeline for a given date.

    - dry_run: if True, no persistence will happen.
    - allow_write: must be True to persist artifacts; used as an explicit guard.
    - session_maker: optional SQLAlchemy sessionmaker to use for persistence (for tests/in-memory DB).
    """
    results = run_single_day_pipeline(run_date, adapter)

    # Persist artifacts if allowed
    artifacts = {}
    if allow_write and not dry_run:
        if session_maker is None:
            SessionLocal = get_sessionmaker()
        else:
            SessionLocal = session_maker
        # simple persistence: store the signals and coupons as artifacts
        with SessionLocal() as db:
            sigs = [s.dict() for s in results["signals"]]
            art = insert_artifact(db, artifact_type="signals", payload={"signals": sigs})
            artifacts["signals_uuid"] = art.uuid
            cups = [c.dict() for c in results["coupons"]]
            art2 = insert_artifact(db, artifact_type="coupons", payload={"coupons": cups})
            artifacts["coupons_uuid"] = art2.uuid
    return {"results": results, "artifacts": artifacts}
