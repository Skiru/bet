-- Initial SQL migration for bet repository.

-- Creates minimal tables used by the DB-first refactor.

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS fixtures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  event_time DATETIME NOT NULL,
  payload JSON NOT NULL,
  created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS market_odds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL,
  fixture_id INTEGER NOT NULL,
  odds_payload JSON NOT NULL,
  created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid TEXT NOT NULL UNIQUE,
  artifact_type TEXT NOT NULL,
  payload JSON NOT NULL,
  schema_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at DATETIME DEFAULT (datetime('now')),
  superseded_by_uuid TEXT
);

COMMIT;
