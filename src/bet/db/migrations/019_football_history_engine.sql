-- 4.6 Snapshot integrity
CREATE UNIQUE INDEX IF NOT EXISTS analysis_snapshot_run_id_idx ON analysis_snapshot(run_id);

-- 4.5 Provider mapping integrity
-- Conflict detection logic handled in the python runner or here by creating an index that fails if conflicts exist.
CREATE UNIQUE INDEX IF NOT EXISTS source_entity_reference_active_api_football_idx ON source_entity_reference(sport, entity_type, provider, provider_entity_id) WHERE provider = 'api-football' AND valid_to IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS fixture_sources_api_football_idx ON fixture_sources(source, external_id) WHERE source = 'api-football';

-- 4.1 sports_sync_cursor
CREATE TABLE IF NOT EXISTS sports_sync_cursor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    sport TEXT NOT NULL,
    operation TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    cursor_version INTEGER NOT NULL DEFAULT 1,
    committed_through_date TEXT,
    correction_lookback_days INTEGER NOT NULL DEFAULT 3,
    coverage_json TEXT NOT NULL DEFAULT '{}',
    coverage_checked_at TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    lock_version INTEGER NOT NULL DEFAULT 0,
    last_success_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, sport, operation, scope_key)
);

-- 4.2 sports_sync_run
CREATE TABLE IF NOT EXISTS sports_sync_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_identity TEXT NOT NULL UNIQUE,
    cursor_id INTEGER NOT NULL REFERENCES sports_sync_cursor(id),
    provider TEXT NOT NULL,
    sport TEXT NOT NULL,
    operation TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    mode TEXT NOT NULL,
    window_from TEXT NOT NULL,
    window_to TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    cursor_before_json TEXT NOT NULL,
    cursor_after_json TEXT,
    physical_http_attempts INTEGER NOT NULL DEFAULT 0,
    fallback_stats_calls INTEGER NOT NULL DEFAULT 0,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    complete_count INTEGER NOT NULL DEFAULT 0,
    partial_count INTEGER NOT NULL DEFAULT 0,
    score_only_count INTEGER NOT NULL DEFAULT 0,
    permanently_unavailable_count INTEGER NOT NULL DEFAULT 0,
    transient_failed_count INTEGER NOT NULL DEFAULT 0,
    quota_json TEXT NOT NULL DEFAULT '{}',
    diagnostics_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT
);

-- 4.3 sports_sync_item
CREATE TABLE IF NOT EXISTS sports_sync_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    sport TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    provider_fixture_id TEXT NOT NULL,
    canonical_fixture_id INTEGER REFERENCES fixtures(id),
    state TEXT NOT NULL,
    normalized_payload_sha256 TEXT,
    fixture_evidence_bundle_id TEXT,
    statistics_evidence_bundle_id TEXT,
    first_seen_at TEXT NOT NULL,
    last_checked_at TEXT NOT NULL,
    last_success_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT,
    last_sync_run_id INTEGER REFERENCES sports_sync_run(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, sport, scope_key, provider_fixture_id)
);

-- 4.4 Observation logical identity

CREATE UNIQUE INDEX IF NOT EXISTS fixture_capability_observation_logical_identity_idx ON fixture_capability_observation(logical_identity) WHERE logical_identity IS NOT NULL AND logical_identity != '';
