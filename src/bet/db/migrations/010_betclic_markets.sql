-- Betclic market availability tables (2026-05-18)
-- Stores observed market availability per event and aggregated per competition.

-- Per-event market observations
CREATE TABLE IF NOT EXISTS betclic_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER REFERENCES fixtures(id) ON DELETE SET NULL,
    betclic_event_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    event_url TEXT NOT NULL,
    sport TEXT NOT NULL,
    competition_id TEXT NOT NULL,
    competition_name TEXT NOT NULL,
    match_date TEXT,
    -- Market availability flags
    open_market_count INTEGER DEFAULT 0,
    has_statistics_tab INTEGER DEFAULT 0,
    has_corners INTEGER DEFAULT 0,
    has_cards INTEGER DEFAULT 0,
    has_shots INTEGER DEFAULT 0,
    has_fouls INTEGER DEFAULT 0,
    -- Detailed data
    tabs_json TEXT DEFAULT '[]',
    market_names_json TEXT DEFAULT '[]',
    -- Metadata
    fetched_at TEXT NOT NULL,
    betting_date TEXT NOT NULL,
    UNIQUE(betclic_event_id, betting_date)
);

CREATE INDEX IF NOT EXISTS idx_betclic_markets_sport ON betclic_markets(sport);
CREATE INDEX IF NOT EXISTS idx_betclic_markets_comp ON betclic_markets(competition_id);
CREATE INDEX IF NOT EXISTS idx_betclic_markets_date ON betclic_markets(betting_date);
CREATE INDEX IF NOT EXISTS idx_betclic_markets_event ON betclic_markets(betclic_event_id);

-- Competition-level market profile (aggregated from observations)
CREATE TABLE IF NOT EXISTS betclic_competition_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    competition_id TEXT NOT NULL,
    competition_name TEXT NOT NULL,
    -- Observed market availability (from most recent scans)
    typically_has_statistics INTEGER DEFAULT 0,
    typically_has_corners INTEGER DEFAULT 0,
    typically_has_cards INTEGER DEFAULT 0,
    typically_has_shots INTEGER DEFAULT 0,
    typically_has_fouls INTEGER DEFAULT 0,
    avg_open_markets INTEGER DEFAULT 0,
    typical_tabs_json TEXT DEFAULT '[]',
    -- Evidence
    observations_count INTEGER DEFAULT 0,
    last_observed_at TEXT,
    last_betting_date TEXT,
    -- URL pattern for competition page
    competition_url TEXT,
    UNIQUE(sport, competition_id)
);

CREATE INDEX IF NOT EXISTS idx_betclic_comp_profiles_sport ON betclic_competition_profiles(sport);
