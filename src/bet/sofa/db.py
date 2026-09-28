import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    # `timeout` is what a writer waits for another writer's lock instead of
    # raising "database is locked" immediately. It was the default 5 s while
    # the pipeline was single-threaded and nothing ever contended; SAMPLES now
    # runs a thread pool, and every worker writes cached statistics. 30 s is
    # far longer than any write here takes and turns a lost fixture into a
    # pause nobody notices.
    conn = sqlite3.connect(db_path, timeout=30.0)
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
        # A name Sofascore has no match for. Deliberately NOT a row in
        # sofa_entity with status='rejected': a miss has no id, no name and no
        # country, and forcing it into that table would mean a sentinel id in a
        # NOT NULL column. Kept separate and honest, with its own TTL.
        """
        CREATE TABLE IF NOT EXISTS sofa_entity_miss (
            sport     TEXT NOT NULL,
            query_key TEXT NOT NULL,
            missed_at TEXT NOT NULL,
            PRIMARY KEY (sport, query_key)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS sofa_event_detail (
            sofascore_event_id INTEGER PRIMARY KEY,
            fetched_at         TEXT    NOT NULL,
            status_type        TEXT,
            detail_json        TEXT    NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS sofa_listing_miss (
            sofascore_entity_id INTEGER NOT NULL,
            kind                TEXT    NOT NULL,
            page                INTEGER NOT NULL,
            missed_at           TEXT    NOT NULL,
            PRIMARY KEY (sofascore_entity_id, kind, page)
        );
        """,
        # CS2 history (src/bet/sofa/cs2_store.py). One row per series, per map
        # and per player-map, as Sofascore reports them - home/away as
        # Sofascore has them, not oriented to any bookmaker. Written by
        # backfill_cs2.py and CS2_SETTLE; read by nothing that builds a coupon.
        """
        CREATE TABLE IF NOT EXISTS cs2_series (
            sofascore_event_id   INTEGER PRIMARY KEY,
            start_ts             INTEGER NOT NULL,
            tournament           TEXT,
            unique_tournament_id INTEGER,
            season_id            INTEGER,
            home_id              INTEGER NOT NULL,
            home_name            TEXT    NOT NULL,
            away_id              INTEGER NOT NULL,
            away_name            TEXT    NOT NULL,
            home_maps            INTEGER,
            away_maps            INTEGER,
            best_of              INTEGER,
            status_type          TEXT    NOT NULL,
            status_description   TEXT,
            complete             INTEGER NOT NULL DEFAULT 0,
            fetched_at           TEXT    NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS cs2_map (
            game_id             INTEGER PRIMARY KEY,
            sofascore_event_id  INTEGER NOT NULL,
            map_order           INTEGER NOT NULL,
            map_name            TEXT,
            start_ts            INTEGER,
            length_s            INTEGER,
            status_type         TEXT    NOT NULL,
            home_rounds         INTEGER,
            away_rounds         INTEGER,
            home_period1        INTEGER,
            home_period2        INTEGER,
            home_overtime       INTEGER,
            away_period1        INTEGER,
            away_period2        INTEGER,
            away_overtime       INTEGER,
            home_starting_side  INTEGER,
            winner_code         INTEGER,
            has_complete_stats  INTEGER NOT NULL DEFAULT 0,
            has_player_rows     INTEGER NOT NULL DEFAULT 0,
            fetched_at          TEXT    NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS cs2_player_map (
            game_id          INTEGER NOT NULL,
            side             TEXT    NOT NULL,
            player_id        INTEGER NOT NULL,
            player_name      TEXT    NOT NULL,
            kills            INTEGER,
            deaths           INTEGER,
            assists          INTEGER,
            headshots        INTEGER,
            flash_assists    INTEGER,
            first_kills_diff INTEGER,
            kd_diff          INTEGER,
            adr              REAL,
            kast             REAL,
            PRIMARY KEY (game_id, side, player_id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS cs2_series_home ON cs2_series (home_id, start_ts);",
        "CREATE INDEX IF NOT EXISTS cs2_series_away ON cs2_series (away_id, start_ts);",
        "CREATE INDEX IF NOT EXISTS cs2_map_event ON cs2_map (sofascore_event_id);",
    ]

    # Columns added after the first schema shipped. ALTER TABLE ADD COLUMN is
    # not idempotent in SQLite, so each one is guarded on the live column list.
    added_columns = [
        # MAX_LADDER_SIGMA can only be fitted from rows that recorded a ladder
        # sigma, and the backfill cannot produce one (there are no historical
        # Superbet ladders). Live settlement can, so the column exists for it.
        ("sofa_settled_row", "ladder_sigma", "REAL"),
        # Which version of the matching logic recorded this miss (F34).
        ("sofa_entity_miss", "match_logic_version", "INTEGER"),
        # What the row was offered at, and what the sheet called it. Without
        # the price a settled row answers "was the forecast right" and cannot
        # answer "was the bet worth taking", which is the only question the
        # coupon actually asks (F53).
        ("sofa_settled_row", "offered_odds", "REAL"),
        ("sofa_settled_row", "verdict", "TEXT"),
        # F54. Per-player statistics, one payload for both squads. Lives
        # alongside statistics and incidents because it is the same fact about
        # the same finished event and expires on the same schedule: never.
        ("sofa_event_stats", "lineups_json", "TEXT"),
    ]

    with get_connection(db_path) as conn:
        for q in queries:
            conn.execute(q)
        for table, column, column_type in added_columns:
            existing = {
                row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        conn.commit()
