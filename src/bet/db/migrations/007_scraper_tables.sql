-- Scraper infrastructure tables (2026-05-14)

CREATE TABLE IF NOT EXISTS scraper_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scraper_name TEXT NOT NULL,
    sport TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    records_scraped INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_seconds REAL,
    UNIQUE(scraper_name, sport, target, started_at)
);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_name ON scraper_runs(scraper_name);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_sport ON scraper_runs(sport);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_status ON scraper_runs(status);

CREATE TABLE IF NOT EXISTS player_season_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
    competition_id INTEGER REFERENCES competitions(id) ON DELETE SET NULL,
    season TEXT NOT NULL,
    games_played INTEGER DEFAULT 0,
    games_started INTEGER DEFAULT 0,
    minutes_played REAL DEFAULT 0,
    stats_json TEXT NOT NULL DEFAULT '{}',
    per_game_json TEXT NOT NULL DEFAULT '{}',
    advanced_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(athlete_id, competition_id, season, source)
);

CREATE INDEX IF NOT EXISTS idx_player_season_stats_athlete ON player_season_stats(athlete_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_competition ON player_season_stats(competition_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_season ON player_season_stats(season);
