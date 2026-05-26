#!/usr/bin/env python3
"""Create pipeline_candidates and market_matrix tables in the DB.

Usage:
    python3 scripts/migrate_pipeline_tables.py
    python3 scripts/migrate_pipeline_tables.py --migrate-shortlists --date 2026-05-20
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

DATA_DIR = ROOT_DIR / "betting" / "data"

PIPELINE_CANDIDATES_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL DEFAULT 0.0,
    sport TEXT NOT NULL,
    competition TEXT,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    kickoff TEXT,
    data_tier TEXT NOT NULL DEFAULT 'FIXTURE_ONLY',
    comp_score INTEGER NOT NULL DEFAULT 3,
    n_odds_markets INTEGER NOT NULL DEFAULT 0,
    n_safety_markets INTEGER NOT NULL DEFAULT 0,
    odds_markets_json TEXT NOT NULL DEFAULT '[]',
    safety_markets_json TEXT NOT NULL DEFAULT '[]',
    fixture_verified INTEGER NOT NULL DEFAULT 0,
    verification_sources_json TEXT NOT NULL DEFAULT '[]',
    tipster_count INTEGER DEFAULT 0,
    tipster_support_json TEXT,
    source TEXT NOT NULL DEFAULT 'build_shortlist',
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_candidates_date ON pipeline_candidates(betting_date);
CREATE INDEX IF NOT EXISTS idx_pipeline_candidates_date_rank ON pipeline_candidates(betting_date, rank);
CREATE INDEX IF NOT EXISTS idx_pipeline_candidates_sport ON pipeline_candidates(betting_date, sport);
"""

MARKET_MATRIX_DDL = """
CREATE TABLE IF NOT EXISTS market_matrix_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    competition TEXT,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    kickoff TEXT,
    data_tier TEXT NOT NULL DEFAULT 'FIXTURE_ONLY',
    fixture_source TEXT,
    odds_markets_json TEXT NOT NULL DEFAULT '[]',
    safety_markets_json TEXT NOT NULL DEFAULT '[]',
    suggested_json TEXT,
    total_markets_available INTEGER NOT NULL DEFAULT 0,
    scores24_h2h_json TEXT,
    scores24_form_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);

CREATE INDEX IF NOT EXISTS idx_market_matrix_date ON market_matrix_events(betting_date);
CREATE INDEX IF NOT EXISTS idx_market_matrix_sport ON market_matrix_events(betting_date, sport);
CREATE INDEX IF NOT EXISTS idx_market_matrix_tier ON market_matrix_events(betting_date, data_tier);

CREATE TABLE IF NOT EXISTS market_matrix_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    betting_date TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    total_fixtures INTEGER NOT NULL DEFAULT 0,
    total_events_in_matrix INTEGER NOT NULL DEFAULT 0,
    events_with_odds INTEGER NOT NULL DEFAULT 0,
    events_with_safety_data INTEGER NOT NULL DEFAULT 0,
    sport_breakdown_json TEXT NOT NULL DEFAULT '{}',
    market_type_counts_json TEXT NOT NULL DEFAULT '{}',
    data_tier_breakdown_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(betting_date)
);
"""


def create_tables():
    """Create the new pipeline tables if they don't exist."""
    from bet.db.connection import get_db

    with get_db() as conn:
        conn.executescript(PIPELINE_CANDIDATES_DDL)
        conn.executescript(MARKET_MATRIX_DDL)
        print("✓ Created pipeline_candidates table")
        print("✓ Created market_matrix_events table")
        print("✓ Created market_matrix_runs table")


def migrate_shortlists(date: str | None = None):
    """Import existing shortlist JSON files into pipeline_candidates table."""
    from bet.db.connection import get_db
    from bet.db.repositories import PipelineCandidateRepo
    from db_data_loader import _resolve_fixture_id, _create_minimal_fixture

    pattern = f"{date}_s2_shortlist.json" if date else "*_s2_shortlist.json"
    files = sorted(DATA_DIR.glob(pattern))
    if not files:
        print(f"No shortlist files found matching {pattern}")
        return

    with get_db() as conn:
        repo = PipelineCandidateRepo(conn)
        total_imported = 0

        for f in files:
            # Extract date from filename
            fname = f.stem
            file_date = fname.split("_s2_shortlist")[0]
            if not file_date or len(file_date) != 10:
                print(f"  Skipping {f.name} (can't parse date)")
                continue

            data = json.loads(f.read_text(encoding="utf-8"))
            candidates = data if isinstance(data, list) else data.get("candidates", data.get("shortlist", []))

            if not candidates:
                print(f"  {f.name}: no candidates")
                continue

            # Resolve fixture_ids
            resolved = []
            for i, c in enumerate(candidates):
                fixture_id = c.get("fixture_id")
                if not fixture_id:
                    fixture_id = _resolve_fixture_id(
                        conn,
                        c.get("sport", ""),
                        c.get("home_team", ""),
                        c.get("away_team", ""),
                        c.get("kickoff", file_date),
                    )
                if not fixture_id:
                    fixture_id = _create_minimal_fixture(
                        conn,
                        c.get("sport", ""),
                        c.get("home_team", ""),
                        c.get("away_team", ""),
                        c.get("kickoff", file_date),
                        c.get("competition", ""),
                    )
                if fixture_id:
                    c["fixture_id"] = fixture_id
                    c.setdefault("rank", i + 1)
                    resolved.append(c)

            if resolved:
                saved = repo.save_candidates(file_date, resolved)
                total_imported += saved
                print(f"  {f.name}: imported {saved} candidates")
            else:
                print(f"  {f.name}: 0 resolved fixtures")

        print(f"\nTotal: imported {total_imported} candidates from {len(files)} files")


def main():
    parser = argparse.ArgumentParser(description="Create/migrate pipeline DB tables")
    parser.add_argument("--migrate-shortlists", action="store_true",
                        help="Import existing shortlist JSON files into DB")
    parser.add_argument("--date", help="Filter migration to specific date (YYYY-MM-DD)")
    args = parser.parse_args()

    create_tables()

    if args.migrate_shortlists:
        migrate_shortlists(args.date)


if __name__ == "__main__":
    main()
