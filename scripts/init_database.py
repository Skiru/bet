#!/usr/bin/env python3
"""Initialize the betting SQLite database.

Creates betting/data/betting.db with full schema and seeds 14 sports.
Idempotent — safe to run multiple times.
"""
import sys
from pathlib import Path

# Add both src/ and scripts/ to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bet.db.connection import get_db, DEFAULT_DB_PATH
from bet.db.schema import init_db
from bet.db.repositories import SportRepo


def main():
    db_path = DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Initializing database at: {db_path}")

    with get_db(db_path) as conn:
        init_db(conn)

        sport_repo = SportRepo(conn)
        sport_repo.seed_defaults()

        # Verify
        sports = sport_repo.get_all()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        print(f"Created {len(tables)} tables: {', '.join(r['name'] for r in tables)}")
        print(f"Seeded {len(sports)} sports:")
        for s in sports:
            print(f"  - {s.name} (tier {s.tier}, {len(s.stat_keys)} stat keys)")

    print("✓ Database initialized successfully")


if __name__ == "__main__":
    main()
