import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(db_path: str) -> None:
    """Create all sofa_ tables if they do not exist. Idempotent."""
    queries = [
        """
        CREATE TABLE IF NOT EXISTS sofa_entity (
            sport          TEXT    NOT NULL,
            query_key      TEXT    NOT NULL,
            sofascore_id   INTEGER NOT NULL,
            sofascore_name TEXT    NOT NULL,
            entity_type    TEXT    NOT NULL,
            country        TEXT,
            status         TEXT    NOT NULL DEFAULT 'candidate',
            verified_at    TEXT,
            last_used_at   TEXT,
            hit_count      INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (sport, query_key)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS sofa_event_stats (
            sofascore_event_id INTEGER PRIMARY KEY,
            fetched_at         TEXT NOT NULL,
            statistics_json    TEXT,
            incidents_json     TEXT,
            status_type        TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS sofa_entity_events (
            sofascore_entity_id INTEGER NOT NULL,
            kind                TEXT    NOT NULL,
            page                INTEGER NOT NULL,
            fetched_at          TEXT    NOT NULL,
            events_json         TEXT    NOT NULL,
            PRIMARY KEY (sofascore_entity_id, kind, page)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS sofa_settled_row (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date           TEXT    NOT NULL,
            sofascore_event_id INTEGER NOT NULL,
            sport              TEXT    NOT NULL,
            competition_id     INTEGER,
            market             TEXT    NOT NULL,
            subject            TEXT    NOT NULL,
            line               REAL    NOT NULL,
            direction          TEXT    NOT NULL,
            sample_size        INTEGER NOT NULL,
            sample_mean        REAL    NOT NULL,
            sample_sd          REAL    NOT NULL,
            p_central          REAL    NOT NULL,
            p_bar              REAL    NOT NULL,
            market_p           REAL,
            actual_value       REAL    NOT NULL,
            outcome            TEXT    NOT NULL,
            settled_at         TEXT    NOT NULL,
            UNIQUE(sofascore_event_id, market, subject, line, direction)
        );
        """,
    ]

    with get_connection(db_path) as conn:
        for q in queries:
            conn.execute(q)
        conn.commit()
