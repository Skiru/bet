import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime

from bet.enrichment.football.contracts import (
    FootballFeatureSnapshotPayload,
    serialize_snapshot_payload,
)
from bet.enrichment.football.time import format_utc

logger = logging.getLogger(__name__)

class SnapshotService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def build_and_persist(self, payload: FootballFeatureSnapshotPayload, run_id: int, canonical_fixture_id: int) -> dict:
        payload_dict = serialize_snapshot_payload(payload)
        payload_json = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
        snapshot_hash = hashlib.sha256(payload_json.encode('utf-8')).hexdigest()

        # Check if run_id already has a snapshot
        row = self.conn.execute("SELECT id, snapshot_hash FROM analysis_snapshot WHERE run_id = ?", (run_id,)).fetchone()

        now_str = format_utc(datetime.now(UTC))

        if row:
            existing_id, existing_hash = row
            if existing_hash != snapshot_hash:
                raise ValueError("DETERMINISTIC_DRIFT")
            return {"snapshot_id": existing_id, "snapshot_hash": existing_hash}

        res = self.conn.execute(
            """INSERT INTO analysis_snapshot
            (schema_version, run_id, canonical_fixture_id, analysis_cutoff_at, status, snapshot_hash, payload_json, created_at)
            VALUES (?, ?, ?, ?, 'DRAFT', ?, ?, ?)""",
            (payload.schema_version, run_id, canonical_fixture_id, format_utc(payload.analysis_cutoff_at), snapshot_hash, payload_json, now_str)
        )
        return {"snapshot_id": res.lastrowid, "snapshot_hash": snapshot_hash}
