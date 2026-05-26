"""Migration script for market_matrix_events + market_matrix_runs tables.

Usage:
    python scripts/migrate_market_matrix.py              # Create tables only
    python scripts/migrate_market_matrix.py --migrate    # Also import historical JSON files
"""

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(SCRIPTS_DIR))

DATA_DIR = ROOT_DIR / "betting" / "data"


def create_tables():
    """Create market_matrix_events and market_matrix_runs tables."""
    from bet.db.connection import get_db

    with get_db() as conn:
        conn.execute("""
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
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_matrix_date ON market_matrix_events(betting_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_matrix_sport ON market_matrix_events(betting_date, sport)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_matrix_tier ON market_matrix_events(betting_date, data_tier)")
        conn.execute("""
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
            )
        """)
        conn.commit()
        print("✓ market_matrix_events + market_matrix_runs tables created")


def migrate_json_files():
    """Import existing market_matrix_*.json files into DB."""
    from bet.db.connection import get_db
    from bet.db.repositories import MarketMatrixRepo, FixtureRepo

    json_files = sorted(DATA_DIR.glob("market_matrix_*.json"))
    if not json_files:
        print("  No market_matrix JSON files found to migrate.")
        return

    with get_db() as conn:
        repo = MarketMatrixRepo(conn)
        fixture_repo = FixtureRepo(conn)

        for path in json_files:
            # Extract date from filename: market_matrix_2026-05-20.json
            stem = path.stem  # market_matrix_2026-05-20
            parts = stem.split("_")
            if len(parts) < 3:
                print(f"  ⚠ Skipping unrecognized filename: {path.name}")
                continue
            date = parts[-1]  # last part is date
            if len(date) != 10 or date[4] != "-":
                # Try joining last parts
                date = "_".join(parts[2:])
                if len(date) != 10:
                    print(f"  ⚠ Cannot extract date from: {path.name}")
                    continue

            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"  ⚠ Error reading {path.name}: {e}")
                continue

            events = raw.get("events", [])
            if not events:
                print(f"  ⚠ No events in {path.name}, skipping")
                continue

            # Resolve fixture_ids
            resolved_events = []
            for ev in events:
                home = ev.get("home_team", "")
                away = ev.get("away_team", "")
                sport = ev.get("sport", "")
                fixture_id = ev.get("fixture_id")

                if not fixture_id:
                    # Try to find fixture in DB
                    fixtures = fixture_repo.get_by_date(date)
                    for f in fixtures:
                        if f.home_team == home and f.away_team == away and f.sport == sport:
                            fixture_id = f.id
                            break

                if not fixture_id:
                    # Create minimal fixture
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO fixtures (sport, home_team, away_team, kickoff, betting_date) VALUES (?, ?, ?, ?, ?)",
                        (sport, home, away, ev.get("kickoff", ""), date),
                    )
                    if cursor.lastrowid:
                        fixture_id = cursor.lastrowid
                    else:
                        row = conn.execute(
                            "SELECT id FROM fixtures WHERE sport=? AND home_team=? AND away_team=? AND betting_date=?",
                            (sport, home, away, date),
                        ).fetchone()
                        fixture_id = row["id"] if row else None

                if fixture_id:
                    ev["fixture_id"] = fixture_id
                    resolved_events.append(ev)

            if resolved_events:
                saved = repo.save_events(date, resolved_events)
                # Save run metadata if available
                meta = raw.get("metadata", raw.get("summary", {}))
                if meta:
                    repo.save_run(date, meta)
                print(f"  ✓ {path.name}: migrated {saved}/{len(events)} events")
            else:
                print(f"  ⚠ {path.name}: no events resolved to fixtures")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate market matrix to DB")
    parser.add_argument("--migrate", action="store_true", help="Import historical JSON files")
    args = parser.parse_args()

    create_tables()
    if args.migrate:
        migrate_json_files()


if __name__ == "__main__":
    main()
