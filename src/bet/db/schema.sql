-- Schema Version: v12 (DDL-only, idempotent, regenerated 2026-06-03)
CREATE TABLE IF NOT EXISTS analysis_raw_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    team_a_l10_json TEXT NOT NULL DEFAULT '{}',
    team_b_l10_json TEXT NOT NULL DEFAULT '{}',
    h2h_meetings_json TEXT NOT NULL DEFAULT '{}',
    per_market_details_json TEXT NOT NULL DEFAULT '[]',
    safety_input_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);
CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
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
CREATE TABLE IF NOT EXISTS athletes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL,  -- ESPN athlete ID
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    team_id INTEGER REFERENCES teams(id),
    name TEXT NOT NULL,
    position TEXT,
    jersey TEXT,
    age INTEGER,
    height TEXT,
    weight TEXT,
    status TEXT DEFAULT 'active',  -- active, injured, day-to-day, out
    source TEXT DEFAULT 'espn',
    updated_at TEXT NOT NULL,
    UNIQUE(external_id, sport_id)
);
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
CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER NOT NULL REFERENCES coupons(id),
    fixture_id INTEGER REFERENCES fixtures(id),
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
    navigation_hint TEXT
, stats_detail TEXT);
CREATE TABLE IF NOT EXISTS competitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    name TEXT NOT NULL,
    country TEXT,
    importance INTEGER NOT NULL DEFAULT 3,
    season TEXT,
    UNIQUE(sport_id, name, season)
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
CREATE TABLE IF NOT EXISTS decision_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id),
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
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
CREATE TABLE IF NOT EXISTS decision_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id),
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
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
CREATE TABLE IF NOT EXISTS fixture_sources (
	id INTEGER NOT NULL, 
	fixture_id INTEGER NOT NULL, 
	source TEXT NOT NULL, 
	external_id TEXT NOT NULL, 
	confidence FLOAT NOT NULL, 
	raw_data TEXT, 
	fetched_at TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_fixture_source UNIQUE (fixture_id, source)
);
CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    competition_id INTEGER REFERENCES competitions(id),
    home_team_id INTEGER NOT NULL REFERENCES teams(id),
    away_team_id INTEGER NOT NULL REFERENCES teams(id),
    kickoff TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    score_home INTEGER,
    score_away INTEGER,
    source TEXT,
    fetched_at TEXT NOT NULL, surface TEXT DEFAULT NULL,
    UNIQUE(sport_id, home_team_id, away_team_id, kickoff)
);
CREATE TABLE IF NOT EXISTS gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
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
CREATE TABLE IF NOT EXISTS known_missing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT NOT NULL,
                sport TEXT NOT NULL,
                marked_at TEXT NOT NULL,
                reason TEXT DEFAULT '',
                source TEXT DEFAULT '',
                UNIQUE(team_name, sport)
            );
CREATE TABLE IF NOT EXISTS league_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_id INTEGER NOT NULL REFERENCES competitions(id),
    stat_key TEXT NOT NULL,
    season TEXT NOT NULL DEFAULT '',
    avg_value REAL NOT NULL,
    median_value REAL,
    std_dev REAL,
    sample_size INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(competition_id, stat_key, season)
);
CREATE TABLE IF NOT EXISTS match_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    stat_key TEXT NOT NULL,
    stat_value REAL NOT NULL,
    source TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(fixture_id, team_id, stat_key, source)
);
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
CREATE TABLE IF NOT EXISTS odds_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    odds REAL NOT NULL,
    line REAL,
    fetched_at TEXT NOT NULL,
    is_closing INTEGER NOT NULL DEFAULT 0
, source TEXT NOT NULL DEFAULT 'unknown');
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
CREATE TABLE IF NOT EXISTS player_gamelogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id),
    fixture_id INTEGER REFERENCES fixtures(id),
    game_date TEXT NOT NULL,
    opponent TEXT,
    result TEXT,  -- W/L
    stats_json TEXT NOT NULL DEFAULT '{}',  -- full stat line as JSON
    source TEXT DEFAULT 'espn',
    UNIQUE(athlete_id, game_date)
);
CREATE TABLE IF NOT EXISTS player_season_stats (
	id INTEGER NOT NULL, 
	athlete_id INTEGER NOT NULL, 
	competition_id INTEGER, 
	season VARCHAR NOT NULL, 
	games_played INTEGER, 
	games_started INTEGER, 
	minutes_played FLOAT, 
	stats_json VARCHAR NOT NULL, 
	per_game_json VARCHAR NOT NULL, 
	advanced_json VARCHAR NOT NULL, 
	source VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id) ON DELETE CASCADE, 
	FOREIGN KEY(competition_id) REFERENCES competitions (id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS player_splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id),
    split_type TEXT NOT NULL,  -- 'home', 'away', 'vs_conference', 'last5', 'last10'
    stats_json TEXT NOT NULL DEFAULT '{}',  -- stat averages for this split
    season TEXT NOT NULL DEFAULT '',
    source TEXT DEFAULT 'espn',
    updated_at TEXT NOT NULL,
    UNIQUE(athlete_id, split_type, season)
);
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
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS scraper_runs (
	id INTEGER NOT NULL, 
	scraper_name VARCHAR NOT NULL, 
	sport VARCHAR NOT NULL, 
	target VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	records_scraped INTEGER, 
	records_inserted INTEGER, 
	records_updated INTEGER, 
	error_message VARCHAR, 
	started_at VARCHAR NOT NULL, 
	finished_at VARCHAR, 
	duration_seconds FLOAT, 
	PRIMARY KEY (id)
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
CREATE TABLE IF NOT EXISTS sports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    tier INTEGER NOT NULL DEFAULT 1,
    stat_keys TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS standings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_id INTEGER NOT NULL REFERENCES competitions(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    season TEXT NOT NULL DEFAULT '',
    rank INTEGER,
    wins INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goal_diff INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    form TEXT,  -- e.g. 'WWDLW'
    home_wins INTEGER DEFAULT 0,
    home_draws INTEGER DEFAULT 0,
    home_losses INTEGER DEFAULT 0,
    away_wins INTEGER DEFAULT 0,
    away_draws INTEGER DEFAULT 0,
    away_losses INTEGER DEFAULT 0,
    streak TEXT,  -- e.g. 'W3', 'L2'
    source TEXT DEFAULT 'espn',
    updated_at TEXT NOT NULL,
    UNIQUE(competition_id, team_id, season)
);
CREATE TABLE IF NOT EXISTS team_ats_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    season TEXT NOT NULL,
    season_type INTEGER DEFAULT 2,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    pushes INTEGER DEFAULT 0,
    home_wins INTEGER DEFAULT 0,
    home_losses INTEGER DEFAULT 0,
    home_pushes INTEGER DEFAULT 0,
    away_wins INTEGER DEFAULT 0,
    away_losses INTEGER DEFAULT 0,
    away_pushes INTEGER DEFAULT 0,
    source TEXT DEFAULT 'espn',
    updated_at TEXT NOT NULL,
    UNIQUE(team_id, season, season_type)
);
CREATE TABLE IF NOT EXISTS team_ou_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    season TEXT NOT NULL,
    season_type INTEGER DEFAULT 2,
    overs INTEGER DEFAULT 0,
    unders INTEGER DEFAULT 0,
    pushes INTEGER DEFAULT 0,
    home_overs INTEGER DEFAULT 0,
    home_unders INTEGER DEFAULT 0,
    home_pushes INTEGER DEFAULT 0,
    away_overs INTEGER DEFAULT 0,
    away_unders INTEGER DEFAULT 0,
    away_pushes INTEGER DEFAULT 0,
    source TEXT DEFAULT 'espn',
    updated_at TEXT NOT NULL,
    UNIQUE(team_id, season, season_type)
);
CREATE TABLE IF NOT EXISTS espn_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    home_win_pct REAL,
    away_win_pct REAL,
    tie_pct REAL,
    predictor_json TEXT,
    power_index_home REAL,
    power_index_away REAL,
    source TEXT DEFAULT 'espn',
    fetched_at TEXT NOT NULL,
    UNIQUE(fixture_id)
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    athlete_id INTEGER REFERENCES athletes(id),
    transaction_type TEXT NOT NULL,
    description TEXT,
    transaction_date TEXT NOT NULL,
    source TEXT DEFAULT 'espn',
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS power_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    season TEXT NOT NULL,
    rating REAL NOT NULL,
    offensive_rating REAL,
    defensive_rating REAL,
    rank INTEGER,
    source TEXT DEFAULT 'espn',
    updated_at TEXT NOT NULL,
    UNIQUE(team_id, season)
);
CREATE TABLE IF NOT EXISTS team_form (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    stat_key TEXT NOT NULL,
    l10_values TEXT NOT NULL DEFAULT '[]',
    l5_values TEXT NOT NULL DEFAULT '[]',
    l10_avg REAL,
    l5_avg REAL,
    h2h_values TEXT NOT NULL DEFAULT '[]',
    h2h_opponent_id INTEGER REFERENCES teams(id),
    trend TEXT,
    updated_at TEXT NOT NULL,
    source TEXT,
    UNIQUE(team_id, stat_key, h2h_opponent_id)
);
CREATE TABLE IF NOT EXISTS team_rosters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    athlete_id INTEGER NOT NULL REFERENCES athletes(id),
    position TEXT,
    jersey TEXT,
    status TEXT DEFAULT 'active',
    depth_rank INTEGER,  -- 1 = starter, 2 = backup, etc.
    season TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE(team_id, athlete_id, season)
);
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    country TEXT,
    venue TEXT,
    style_tags TEXT NOT NULL DEFAULT '[]',
    UNIQUE(sport_id, name)
);
CREATE TABLE IF NOT EXISTS team_source_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    source TEXT NOT NULL,
    provider_team_name TEXT NOT NULL,
    provider_team_id TEXT,
    provider_slug TEXT,
    provider_competition_hint TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    verified_at TEXT,
    last_used_at TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    UNIQUE(team_id, source, provider_team_name, provider_competition_hint)
);
CREATE INDEX IF NOT EXISTS idx_team_source_aliases_lookup
    ON team_source_aliases(team_id, source, status, provider_competition_hint);
CREATE TABLE IF NOT EXISTS tipster_consensus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        betting_date TEXT NOT NULL,
        event TEXT,
        sport TEXT,
        competition TEXT,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        total_tipsters INTEGER,
        consensus_market TEXT,
        consensus_direction TEXT,
        agreement_pct REAL,
        statistical_picks INTEGER,
        outcome_picks INTEGER,
        has_reasoning INTEGER DEFAULT 0,
        tipster_sources TEXT,
        confidence_adj REAL DEFAULT 0.0,
        created_at TEXT DEFAULT (datetime('now'))
    );
CREATE TABLE IF NOT EXISTS tipster_picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        betting_date TEXT NOT NULL,
        source_site TEXT NOT NULL,
        tipster_name TEXT,
        sport TEXT,
        event TEXT,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        competition TEXT,
        market TEXT,
        market_type TEXT,
        direction TEXT,
        odds REAL,
        reasoning TEXT,
        accuracy_pct REAL,
        confidence REAL,
        stats_cited TEXT,
        fetch_time TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
CREATE TABLE IF NOT EXISTS scan_run_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    betting_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    scanner_group TEXT NOT NULL,
    events_found INTEGER NOT NULL DEFAULT 0,
    sources_ok INTEGER NOT NULL DEFAULT 0,
    sources_failed INTEGER NOT NULL DEFAULT 0,
    deep_links_found INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL NOT NULL DEFAULT 0,
    validation_passed INTEGER NOT NULL DEFAULT 1,
    gaps_description TEXT NOT NULL DEFAULT '[]',
    scan_timestamp TEXT NOT NULL,
    UNIQUE(betting_date, sport, scanner_group)
);
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff);
CREATE INDEX IF NOT EXISTS idx_fixtures_sport_status ON fixtures(sport_id, status);
CREATE INDEX IF NOT EXISTS idx_league_profiles_comp ON league_profiles(competition_id);
CREATE INDEX IF NOT EXISTS idx_match_stats_team_key ON match_stats(team_id, stat_key);
CREATE INDEX IF NOT EXISTS idx_match_stats_fixture ON match_stats(fixture_id);
CREATE INDEX IF NOT EXISTS idx_market_matrix_date ON market_matrix_events(betting_date);
CREATE INDEX IF NOT EXISTS idx_market_matrix_sport ON market_matrix_events(betting_date, sport);
CREATE INDEX IF NOT EXISTS idx_market_matrix_tier ON market_matrix_events(betting_date, data_tier);
CREATE INDEX IF NOT EXISTS idx_team_form_team_stat ON team_form(team_id, stat_key);
CREATE INDEX IF NOT EXISTS idx_odds_history_fixture ON odds_history(fixture_id);
CREATE INDEX IF NOT EXISTS idx_bets_coupon ON bets(coupon_id);
CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status);
CREATE INDEX IF NOT EXISTS idx_teams_sport ON teams(sport_id);
CREATE INDEX IF NOT EXISTS idx_teams_aliases ON teams(aliases);
CREATE UNIQUE INDEX IF NOT EXISTS idx_team_form_upsert ON team_form(team_id, stat_key, COALESCE(h2h_opponent_id, 0));
CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_history_upsert ON odds_history(fixture_id, bookmaker, market, selection, fetched_at);
CREATE INDEX IF NOT EXISTS idx_analysis_results_date ON analysis_results(betting_date);
CREATE INDEX IF NOT EXISTS idx_analysis_results_fixture ON analysis_results(fixture_id);
CREATE INDEX IF NOT EXISTS idx_gate_results_date ON gate_results(betting_date);
CREATE INDEX IF NOT EXISTS idx_gate_results_status ON gate_results(betting_date, status);
CREATE INDEX IF NOT EXISTS idx_analysis_raw_fixture ON analysis_raw_data(fixture_id);
CREATE INDEX IF NOT EXISTS idx_analysis_raw_date ON analysis_raw_data(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_snapshots_fixture ON decision_snapshots(fixture_id);
CREATE INDEX IF NOT EXISTS idx_decision_snapshots_date ON decision_snapshots(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_sport ON decision_outcomes(sport);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_market ON decision_outcomes(market);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_date ON decision_outcomes(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_result ON decision_outcomes(result);
CREATE INDEX IF NOT EXISTS idx_scan_results_date_sport ON scan_results(betting_date, sport);
CREATE INDEX IF NOT EXISTS idx_scan_results_event_key ON scan_results(event_key);
CREATE INDEX IF NOT EXISTS idx_athletes_team ON athletes(team_id);
CREATE INDEX IF NOT EXISTS idx_athletes_sport ON athletes(sport_id);
CREATE INDEX IF NOT EXISTS idx_athletes_external ON athletes(external_id);
CREATE INDEX IF NOT EXISTS idx_player_gamelogs_athlete ON player_gamelogs(athlete_id);
CREATE INDEX IF NOT EXISTS idx_player_gamelogs_date ON player_gamelogs(game_date);
CREATE INDEX IF NOT EXISTS idx_player_splits_athlete ON player_splits(athlete_id);
CREATE INDEX IF NOT EXISTS idx_standings_competition ON standings(competition_id);
CREATE INDEX IF NOT EXISTS idx_standings_team ON standings(team_id);
CREATE INDEX IF NOT EXISTS idx_team_ats_team ON team_ats_records(team_id);
CREATE INDEX IF NOT EXISTS idx_team_ou_team ON team_ou_records(team_id);
CREATE INDEX IF NOT EXISTS idx_espn_predictions_fixture ON espn_predictions(fixture_id);
CREATE INDEX IF NOT EXISTS idx_team_rosters_team ON team_rosters(team_id);
CREATE INDEX IF NOT EXISTS idx_transactions_team ON transactions(team_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_power_index_team ON power_index(team_id);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_sport_market ON decision_outcomes(sport, market);
CREATE INDEX IF NOT EXISTS idx_odds_history_lookup ON odds_history(fixture_id, market, selection);
CREATE INDEX IF NOT EXISTS idx_bets_fixture ON bets(fixture_id);
CREATE INDEX IF NOT EXISTS idx_tipster_picks_date ON tipster_picks(betting_date);
CREATE INDEX IF NOT EXISTS idx_tipster_picks_teams ON tipster_picks(home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_tipster_consensus_date ON tipster_consensus(betting_date);
CREATE INDEX IF NOT EXISTS idx_tipster_consensus_teams ON tipster_consensus(home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_name ON scraper_runs(scraper_name);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_sport ON scraper_runs(sport);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_status ON scraper_runs(status);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_athlete ON player_season_stats(athlete_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_competition ON player_season_stats(competition_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_season ON player_season_stats(season);
CREATE INDEX IF NOT EXISTS idx_fixture_sources_fixture ON fixture_sources(fixture_id);
CREATE INDEX IF NOT EXISTS idx_fixture_sources_source_ext ON fixture_sources(source, external_id);
CREATE INDEX IF NOT EXISTS idx_tipster_picks_sport ON tipster_picks(betting_date, sport);
CREATE INDEX IF NOT EXISTS idx_tipster_picks_source ON tipster_picks(source_site);
CREATE INDEX IF NOT EXISTS idx_tipster_consensus_sport ON tipster_consensus(betting_date, sport);
CREATE INDEX IF NOT EXISTS idx_betclic_markets_sport ON betclic_markets(sport);
CREATE INDEX IF NOT EXISTS idx_betclic_markets_comp ON betclic_markets(competition_id);
CREATE INDEX IF NOT EXISTS idx_betclic_markets_date ON betclic_markets(betting_date);
CREATE INDEX IF NOT EXISTS idx_betclic_markets_event ON betclic_markets(betclic_event_id);
CREATE INDEX IF NOT EXISTS idx_betclic_comp_profiles_sport ON betclic_competition_profiles(sport);
CREATE INDEX IF NOT EXISTS idx_pipeline_candidates_date ON pipeline_candidates(betting_date);
CREATE INDEX IF NOT EXISTS idx_pipeline_candidates_date_rank ON pipeline_candidates(betting_date, rank);
CREATE INDEX IF NOT EXISTS idx_pipeline_candidates_sport ON pipeline_candidates(betting_date, sport);
DELETE FROM "sqlite_sequence";
