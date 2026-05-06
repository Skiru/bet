-- Migration 003: Decision Learning System
-- Adds tables for storing full analysis context and learning from outcomes

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

CREATE INDEX IF NOT EXISTS idx_analysis_raw_fixture ON analysis_raw_data(fixture_id);
CREATE INDEX IF NOT EXISTS idx_analysis_raw_date ON analysis_raw_data(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_snapshots_fixture ON decision_snapshots(fixture_id);
CREATE INDEX IF NOT EXISTS idx_decision_snapshots_date ON decision_snapshots(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_sport ON decision_outcomes(sport);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_market ON decision_outcomes(market);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_date ON decision_outcomes(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_result ON decision_outcomes(result);
