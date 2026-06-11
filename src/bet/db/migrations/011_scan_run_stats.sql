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

CREATE INDEX IF NOT EXISTS idx_scan_run_stats_date ON scan_run_stats(betting_date);
CREATE INDEX IF NOT EXISTS idx_scan_run_stats_sport ON scan_run_stats(betting_date, sport);
