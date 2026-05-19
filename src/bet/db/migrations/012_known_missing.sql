-- Known missing teams/players cache (replaces betting/data/known_missing_teams.json)
-- Teams that consistently 404 across all enrichment sources.
-- Entries expire after 7 days (enforced in application code).

CREATE TABLE IF NOT EXISTS known_missing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    sport TEXT NOT NULL,
    marked_at TEXT NOT NULL,
    reason TEXT DEFAULT '',
    source TEXT DEFAULT '',
    UNIQUE(team_name, sport)
);

CREATE INDEX IF NOT EXISTS idx_known_missing_sport ON known_missing(sport);
CREATE INDEX IF NOT EXISTS idx_known_missing_marked_at ON known_missing(marked_at);
