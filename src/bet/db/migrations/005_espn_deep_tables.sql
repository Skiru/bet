-- ESPN Deep Integration Tables (2026-05-07)
-- Stores data from all ESPN API domains

-- Athletes/Players — individual athlete data for prop analysis
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

-- Player gamelogs — game-by-game stats for L5/L10 player form
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

-- Player splits — home/away/conference performance splits
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

-- League standings — full enriched standings with form data
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

-- Team ATS (Against The Spread) records — historical cover rates
CREATE TABLE IF NOT EXISTS team_ats_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    sport_id INTEGER NOT NULL REFERENCES sports(id),
    season TEXT NOT NULL,
    season_type INTEGER DEFAULT 2,  -- 1=pre, 2=regular, 3=post
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

-- Team O/U (Over/Under) records — historical totals performance
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

-- ESPN win probabilities per event — ESPN's model predictions
CREATE TABLE IF NOT EXISTS espn_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    home_win_pct REAL,
    away_win_pct REAL,
    tie_pct REAL,
    predictor_json TEXT,  -- full predictor factors
    power_index_home REAL,
    power_index_away REAL,
    source TEXT DEFAULT 'espn',
    fetched_at TEXT NOT NULL,
    UNIQUE(fixture_id)
);

-- Team roster snapshots — track squad composition over time
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

-- Team transactions — trades, signings, waivers that affect roster
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    athlete_id INTEGER REFERENCES athletes(id),
    transaction_type TEXT NOT NULL,  -- 'trade', 'sign', 'waive', 'call-up', 'injury'
    description TEXT,
    transaction_date TEXT NOT NULL,
    source TEXT DEFAULT 'espn',
    fetched_at TEXT NOT NULL
);

-- ESPN Power Index — team power ratings (BPI, FPI, etc.)
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

-- Indexes for performance
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
