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
    betting_date TEXT NOT NULL UNIQUE,
    generated_at TEXT NOT NULL,
    total_fixtures INTEGER NOT NULL DEFAULT 0,
    total_events_in_matrix INTEGER NOT NULL DEFAULT 0,
    events_with_odds INTEGER NOT NULL DEFAULT 0,
    events_with_safety_data INTEGER NOT NULL DEFAULT 0,
    sport_breakdown_json TEXT NOT NULL DEFAULT '{}',
    market_type_counts_json TEXT NOT NULL DEFAULT '{}',
    data_tier_breakdown_json TEXT NOT NULL DEFAULT '{}'
);
