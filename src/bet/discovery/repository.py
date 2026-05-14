"""SQLAlchemy ORM repository for fixture source cross-references.

Uses SQLAlchemy session-based operations (not raw sqlite3).
Compatible with bet.scrapers.engine session factory.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FixtureSourceModel

logger = logging.getLogger(__name__)


class FixtureSourceRepo:
    """Repository for fixture_sources table via SQLAlchemy ORM."""

    def __init__(self, session: Session):
        self.session = session

    def upsert(
        self,
        fixture_id: int,
        source: str,
        external_id: str,
        confidence: float = 1.0,
        raw_data: dict | None = None,
    ) -> FixtureSourceModel:
        """Insert or update a fixture-source mapping. Returns the model instance."""
        now = datetime.now(timezone.utc).isoformat()
        raw_json = json.dumps(raw_data) if raw_data else None

        existing = self.session.execute(
            select(FixtureSourceModel).where(
                FixtureSourceModel.fixture_id == fixture_id,
                FixtureSourceModel.source == source,
            )
        ).scalar_one_or_none()

        if existing:
            existing.external_id = external_id
            existing.confidence = confidence
            existing.raw_data = raw_json
            existing.fetched_at = now
            return existing

        obj = FixtureSourceModel(
            fixture_id=fixture_id,
            source=source,
            external_id=external_id,
            confidence=confidence,
            raw_data=raw_json,
            fetched_at=now,
        )
        self.session.add(obj)
        self.session.flush()
        return obj

    def get_by_fixture(self, fixture_id: int) -> list[FixtureSourceModel]:
        """Get all source references for a fixture."""
        return list(
            self.session.execute(
                select(FixtureSourceModel).where(
                    FixtureSourceModel.fixture_id == fixture_id
                )
            ).scalars().all()
        )

    def get_by_source_id(self, source: str, external_id: str) -> FixtureSourceModel | None:
        """Look up fixture by source-specific external ID."""
        return self.session.execute(
            select(FixtureSourceModel).where(
                FixtureSourceModel.source == source,
                FixtureSourceModel.external_id == external_id,
            )
        ).scalar_one_or_none()

    def bulk_upsert(self, records: list[tuple]) -> int:
        """Batch upsert source references.

        Each record: (fixture_id, source, external_id, confidence, raw_data)
        Returns count written.
        """
        count = 0
        for fixture_id, source, external_id, confidence, raw_data in records:
            self.upsert(fixture_id, source, external_id, confidence, raw_data)
            count += 1
        return count
