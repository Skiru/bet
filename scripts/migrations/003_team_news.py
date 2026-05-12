"""Migration 003: Add team_news table."""
import sqlite3
from pathlib import Path

def up(db_path: Path):
    """Run the migration."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            sport_id INTEGER NOT NULL,
            betting_date TEXT NOT NULL,
            injuries_json TEXT NOT NULL DEFAULT '[]',
            news_json TEXT NOT NULL DEFAULT '[]',
            coaching_json TEXT NOT NULL DEFAULT '[]',
            morale_json TEXT NOT NULL DEFAULT '[]',
            sources_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL DEFAULT 0.0,
            fetched_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'gemini',
            UNIQUE(team_id, betting_date)
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"Migration 003 applied successfully to {db_path}")

def down(db_path: Path):
    """Revert the migration."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS team_news")
    conn.commit()
    conn.close()
    print(f"Migration 003 reverted successfully on {db_path}")

if __name__ == "__main__":
    db_path = Path(__file__).parent.parent.parent / "betting" / "data" / "betting.db"
    up(db_path)
