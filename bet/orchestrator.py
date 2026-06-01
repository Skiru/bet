"""Orchestrator library: coordinates pipeline stages and persists artifacts via repository.

Design notes:
- The orchestrator is a library; do not execute it on import.
- Writes to DB are gated behind allow_write=True and an explicit sessionmaker provided
  (for tests we pass an in-memory sessionmaker).
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Callable

from bet.db.repository import insert_artifact
from bet.db.connection import get_sessionmaker
from .service import run_single_day_pipeline


def run_pipeline_for_date(run_date: date, adapter, dry_run: bool = True, allow_write: bool = False, session_maker: Optional[Callable] = None, agent_id: Optional[str] = None) -> dict:
    """Run the pipeline for a given date.

    - dry_run: if True, no persistence will happen.
    - allow_write: must be True to persist artifacts; used as an explicit guard.
    - session_maker: optional SQLAlchemy sessionmaker factory to use for persistence (for tests/in-memory DB).
    """
    results = run_single_day_pipeline(run_date, adapter)

    # Persist artifacts if allowed
    artifacts = {}
    if allow_write and not dry_run:
        SessionLocal = session_maker if session_maker is not None else get_sessionmaker()
        db = SessionLocal()
        try:
            sigs = [s.dict() for s in results["signals"]]
            art = insert_artifact(db, artifact_type="signals", payload={"signals": sigs}, schema_version="v1")
            artifacts["signals_uuid"] = art.uuid
            cups = [c.dict() for c in results["coupons"]]
            art2 = insert_artifact(db, artifact_type="coupons", payload={"coupons": cups}, schema_version="v1")
            artifacts["coupons_uuid"] = art2.uuid
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return {"results": results, "artifacts": artifacts}
