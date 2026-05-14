import json
import sqlite3
from datetime import datetime, timezone

class FixtureSourceRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
    
    def upsert(self, fixture_id, source, external_id, confidence=1.0, raw_data=None):
        now = datetime.now(timezone.utc).isoformat()
        raw_json = json.dumps(raw_data) if raw_data else None
        self.conn.execute(
            """INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, raw_data, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(fixture_id, source) DO UPDATE SET
                   external_id = excluded.external_id,
                   confidence = excluded.confidence,
                   raw_data = excluded.raw_data,
                   fetched_at = excluded.fetched_at""",
            (fixture_id, source, external_id, confidence, raw_json, now)
        )
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_by_fixture(self, fixture_id):
        rows = self.conn.execute(
            "SELECT * FROM fixture_sources WHERE fixture_id = ?", (fixture_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_source_id(self, source, external_id):
        row = self.conn.execute(
            "SELECT * FROM fixture_sources WHERE source = ? AND external_id = ?",
            (source, external_id)
        ).fetchone()
        return dict(row) if row else None

    def bulk_upsert(self, records):
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        for fixture_id, source, external_id, confidence, raw_data in records:
            raw_json = json.dumps(raw_data) if raw_data else None
            self.conn.execute(
                """INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, raw_data, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(fixture_id, source) DO UPDATE SET
                       external_id = excluded.external_id,
                       confidence = excluded.confidence,
                       raw_data = excluded.raw_data,
                       fetched_at = excluded.fetched_at""",
                (fixture_id, source, external_id, confidence, raw_json, now)
            )
            count += 1
        return count
