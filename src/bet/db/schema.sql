-- Betting system schema v6

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    tier INTEGER NOT NULL DEFAULT 1,
    stat_keys TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS competitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    country TEXT,
    importance INTEGER NOT NULL DEFAULT 3,
    season TEXT,
    UNIQUE(sport_id, name, season)
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    country TEXT,
    venue TEXT,
    style_tags TEXT NOT NULL DEFAULT '[]',
    UNIQUE(sport_id, name)
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    sport_id INTEGER NOT NULL REFERENCES sports(id) ON DELETE CASCADE,
    competition_id INTEGER REFERENCES competitions(id) ON DELETE SET NULL,
    home_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    away_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    kickoff TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    score_home INTEGER,
    score_away INTEGER,
    source TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(sport_id, home_team_id, away_team_id, kickoff)
);

CREATE TABLE IF NOT EXISTS match_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    stat_key TEXT NOT NULL,
    stat_value REAL NOT NULL,
    source TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(fixture_id, team_id, stat_key, source)
);

CREATE TABLE IF NOT EXISTS team_form (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    sport_id INTEGER NOT NULL REFERENCES sports(id) ON DELETE CASCADE,
    stat_key TEXT NOT NULL,
    l10_values TEXT NOT NULL DEFAULT '[]',
    l5_values TEXT NOT NULL DEFAULT '[]',
    l10_avg REAL,
    l5_avg REAL,
    h2h_values TEXT NOT NULL DEFAULT '[]',
    h2h_opponent_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    trend TEXT,
    updated_at TEXT NOT NULL,
    source TEXT,
    UNIQUE(team_id, stat_key, h2h_opponent_id)
);

-- Expression-based unique index to handle NULL h2h_opponent_id correctly.
-- SQLite treats NULLs as distinct in plain UNIQUE constraints, so ON CONFLICT
-- would never fire for non-H2H rows. This index uses COALESCE to treat NULL as 0.
CREATE UNIQUE INDEX IF NOT EXISTS idx_team_form_upsert
    ON team_form(team_id, stat_key, COALESCE(h2h_opponent_id, 0));

CREATE TABLE IF NOT EXISTS odds_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    odds REAL NOT NULL,
    line REAL,
    fetched_at TEXT NOT NULL,
    is_closing INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id TEXT NOT NULL UNIQUE,
    coupon_type TEXT NOT NULL DEFAULT 'AKO',
    total_odds REAL,
    stake_pln REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    pnl_pln REAL,
    placed_at TEXT,
    settled_at TEXT,
    betclic_ref TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
    fixture_id INTEGER REFERENCES fixtures(id) ON DELETE SET NULL,
    sport TEXT NOT NULL,
    event_name TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    odds REAL NOT NULL,
    min_odds REAL,
    safety_score REAL,
    hit_rate REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    pnl_pln REAL,
    settled_at TEXT,
    market_pl TEXT,
    navigation_hint TEXT,
    stats_detail TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    stats TEXT,
    UNIQUE(date, step)
);

CREATE TABLE IF NOT EXISTS source_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    last_success TEXT,
    last_failure TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    total_requests INTEGER NOT NULL DEFAULT 0,
    total_failures INTEGER NOT NULL DEFAULT 0,
    avg_response_ms REAL,
    UNIQUE(source_name)
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    betting_date TEXT NOT NULL,
    has_data INTEGER NOT NULL DEFAULT 0,
    best_market_name TEXT,
    best_market_line REAL,
    best_market_direction TEXT,
    best_safety_score REAL,
    markets_evaluated INTEGER NOT NULL DEFAULT 0,
    ranking_json TEXT NOT NULL DEFAULT '[]',
    three_way_check_json TEXT,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    stats_summary_json TEXT,
    source TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);

CREATE TABLE IF NOT EXISTS gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    betting_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    gate_score INTEGER NOT NULL DEFAULT 0,
    gate_details_json TEXT NOT NULL DEFAULT '{}',
    best_market_name TEXT,
    best_market_line REAL,
    best_market_direction TEXT,
    best_safety_score REAL,
    ev REAL,
    risk_tier TEXT,
    rejection_reasons_json TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff);
CREATE INDEX IF NOT EXISTS idx_fixtures_sport_status ON fixtures(sport_id, status);

CREATE TABLE IF NOT EXISTS league_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    stat_key TEXT NOT NULL,
    season TEXT NOT NULL DEFAULT '',
    avg_value REAL NOT NULL,
    median_value REAL,
    std_dev REAL,
    sample_size INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(competition_id, stat_key, season)
);

CREATE INDEX IF NOT EXISTS idx_league_profiles_comp ON league_profiles(competition_id);
CREATE INDEX IF NOT EXISTS idx_match_stats_team_key ON match_stats(team_id, stat_key);
CREATE INDEX IF NOT EXISTS idx_match_stats_fixture ON match_stats(fixture_id);
CREATE INDEX IF NOT EXISTS idx_team_form_team_stat ON team_form(team_id, stat_key);
CREATE INDEX IF NOT EXISTS idx_odds_history_fixture ON odds_history(fixture_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_history_upsert ON odds_history(fixture_id, bookmaker, market, selection, fetched_at);
CREATE INDEX IF NOT EXISTS idx_bets_coupon ON bets(coupon_id);
CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status);
CREATE INDEX IF NOT EXISTS idx_bets_fixture ON bets(fixture_id);
CREATE INDEX IF NOT EXISTS idx_teams_sport ON teams(sport_id);
CREATE INDEX IF NOT EXISTS idx_teams_aliases ON teams(aliases);
CREATE INDEX IF NOT EXISTS idx_analysis_results_date ON analysis_results(betting_date);
CREATE INDEX IF NOT EXISTS idx_analysis_results_fixture ON analysis_results(fixture_id);
CREATE INDEX IF NOT EXISTS idx_gate_results_date ON gate_results(betting_date);
CREATE INDEX IF NOT EXISTS idx_gate_results_status ON gate_results(betting_date, status);

-- Decision Learning System (v4)
CREATE TABLE IF NOT EXISTS analysis_raw_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    betting_date TEXT NOT NULL,
    team_a_l10_json TEXT NOT NULL DEFAULT '{}',
    team_b_l10_json TEXT NOT NULL DEFAULT '{}',
    h2h_meetings_json TEXT NOT NULL DEFAULT '{}',
    per_market_details_json TEXT NOT NULL DEFAULT '[]',
    safety_input_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);

CREATE TABLE IF NOT EXISTS decision_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id) ON DELETE CASCADE,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    betting_date TEXT NOT NULL,
    chosen_market TEXT NOT NULL,
    chosen_line REAL,
    chosen_direction TEXT NOT NULL,
    safety_score REAL,
    all_markets_considered_json TEXT NOT NULL DEFAULT '[]',
    reasoning_json TEXT NOT NULL DEFAULT '{}',
    thresholds_json TEXT NOT NULL DEFAULT '{}',
    flip_conditions_json TEXT NOT NULL DEFAULT '{}',
    team_a_snapshot_json TEXT NOT NULL DEFAULT '{}',
    team_b_snapshot_json TEXT NOT NULL DEFAULT '{}',
    h2h_snapshot_json TEXT NOT NULL DEFAULT '{}',
    three_way_check_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(bet_id)
);

CREATE TABLE IF NOT EXISTS decision_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id) ON DELETE CASCADE,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    betting_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    competition TEXT,
    market TEXT NOT NULL,
    line REAL,
    direction TEXT NOT NULL,
    predicted_value REAL,
    actual_value REAL,
    deviation REAL,
    deviation_pct REAL,
    result TEXT NOT NULL,
    prediction_accuracy_json TEXT NOT NULL DEFAULT '{}',
    pattern_tags_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(bet_id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_raw_fixture ON analysis_raw_data(fixture_id);
CREATE INDEX IF NOT EXISTS idx_analysis_raw_date ON analysis_raw_data(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_snapshots_fixture ON decision_snapshots(fixture_id);
CREATE INDEX IF NOT EXISTS idx_decision_snapshots_date ON decision_snapshots(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_sport ON decision_outcomes(sport);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_market ON decision_outcomes(market);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_date ON decision_outcomes(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_result ON decision_outcomes(result);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_sport_market ON decision_outcomes(sport, market);
CREATE INDEX IF NOT EXISTS idx_odds_history_lookup ON odds_history(fixture_id, market, selection);

-- Scan results (per-event data from sport scanners)
CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    betting_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    event_key TEXT NOT NULL,
    home_team TEXT,
    away_team TEXT,
    competition TEXT,
    kickoff TEXT,
    raw_data TEXT,
    scan_timestamp TEXT NOT NULL,
    UNIQUE(betting_date, sport, source_domain, event_key)
);

CREATE INDEX IF NOT EXISTS idx_scan_results_date_sport ON scan_results(betting_date, sport);
CREATE INDEX IF NOT EXISTS idx_scan_results_event_key ON scan_results(event_key);

-- Scan run statistics (per-sport scan metadata)
CREATE TABLE IF NOT EXISTS scan_run_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    betting_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    scanner_group TEXT NOT NULL,
    events_found INTEGER DEFAULT 0,
    sources_ok INTEGER DEFAULT 0,
    sources_failed INTEGER DEFAULT 0,
    deep_links_found INTEGER DEFAULT 0,
    duration_seconds REAL,
    validation_passed INTEGER DEFAULT 1,
    gaps_description TEXT,
    scan_timestamp TEXT NOT NULL,
    UNIQUE(betting_date, sport)
);

CREATE INDEX IF NOT EXISTS idx_scan_run_stats_date ON scan_run_stats(betting_date);

-- Deep data tables (injuries, H2H stats, coach history, web research cache)
CREATE TABLE IF NOT EXISTS injuries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER,
    athlete_name TEXT NOT NULL,
    sport TEXT NOT NULL,
    status TEXT NOT NULL,  -- OUT, DOUBTFUL, QUESTIONABLE, PROBABLE
    injury_type TEXT,
    expected_return TEXT,
    source TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS h2h_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team1_id INTEGER,
    team2_id INTEGER,
    sport TEXT NOT NULL,
    stat_key TEXT NOT NULL,  -- corners, fouls, goals, etc.
    values_json TEXT,  -- JSON array of per-match values
    avg_value REAL,
    match_count INTEGER,
    source TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coach_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER,
    coach_name TEXT NOT NULL,
    sport TEXT NOT NULL,
    appointed_date TEXT,
    left_date TEXT,
    is_current BOOLEAN DEFAULT 1,
    source TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS web_research_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT UNIQUE NOT NULL,
    query_text TEXT NOT NULL,
    data_type TEXT NOT NULL,  -- h2h, injuries, form, coach
    result_json TEXT,
    source_urls TEXT,
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_injuries_team ON injuries(team_id);
CREATE INDEX IF NOT EXISTS idx_injuries_sport ON injuries(sport);
CREATE INDEX IF NOT EXISTS idx_h2h_stats_teams ON h2h_stats(team1_id, team2_id);
CREATE INDEX IF NOT EXISTS idx_h2h_stats_sport ON h2h_stats(sport);
CREATE INDEX IF NOT EXISTS idx_coach_history_team ON coach_history(team_id);
CREATE INDEX IF NOT EXISTS idx_web_research_cache_hash ON web_research_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_web_research_cache_expires ON web_research_cache(expires_at);

-- Schema metadata (version tracking, migration log)
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
