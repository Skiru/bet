#!/usr/bin/env python3
"""Create name_mappings table for the betting pipeline infrastructure.

Idempotent — safe to run multiple times.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from bet.db.connection import get_db


def migrate():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS name_mappings (
            id INTEGER PRIMARY KEY,
            sport TEXT NOT NULL,
            source TEXT NOT NULL,
            db_team_id INTEGER REFERENCES teams(id),
            source_name TEXT NOT NULL,
            db_name TEXT NOT NULL,
            match_score REAL,
            verified BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sport, source, source_name)
        );
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name_mappings_sport_source ON name_mappings(sport, source);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name_mappings_team_id ON name_mappings(db_team_id);")
        
        conn.commit()
        print("[migration] Ensure 'name_mappings' table and indexes exist")


if __name__ == "__main__":
    migrate()
