-- Migration 017: Sports Enrichment Foundation
-- Additive schema changes for generic sports kernel and atomic snapshots

-- 1. Generic sports entity supertype table
CREATE TABLE IF NOT EXISTS sports_entity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    entity_type TEXT NOT NULL, -- EVENT, PARTICIPANT, COMPETITION, SEASON, ATHLETE, VENUE, OFFICIAL
    domain_table TEXT NOT NULL,
    domain_entity_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(sport, entity_type, domain_table, domain_entity_id)
);

-- 2. Generic source entity reference table
CREATE TABLE IF NOT EXISTS source_entity_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    canonical_entity_id INTEGER NOT NULL REFERENCES sports_entity(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_entity_id TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    verification_status TEXT NOT NULL, -- UNVERIFIED, QUALIFIED, PENDING_REQUALIFICATION, EXPIRED, REJECTED
    verification_method TEXT NOT NULL,
    evidence_bundle_id TEXT,
    UNIQUE(sport, entity_type, canonical_entity_id, provider, provider_entity_id)
);

-- 3. Evidence package revision table
CREATE TABLE IF NOT EXISTS evidence_package_revision (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id TEXT NOT NULL UNIQUE,
    source_key TEXT NOT NULL,
    operation_name TEXT NOT NULL,
    request_identity TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    dto_version TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    member_count INTEGER NOT NULL,
    completeness_state TEXT NOT NULL, -- COMPLETE, PARTIAL, INCOMPLETE
    created_at TEXT NOT NULL
);

-- 4. Sports enrichment run table
CREATE TABLE IF NOT EXISTS sports_enrichment_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_identity TEXT NOT NULL UNIQUE,
    sport TEXT NOT NULL,
    canonical_event_id INTEGER NOT NULL,
    analysis_cutoff_at TEXT NOT NULL,
    status TEXT NOT NULL, -- RUNNING, COMPLETE, DEGRADED, FAILED, ABANDONED
    started_at TEXT NOT NULL,
    completed_at TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    policy_config_hash TEXT NOT NULL,
    requested_capabilities TEXT NOT NULL,
    completion_summary TEXT,
    failure_reason TEXT
);

-- 5. Source operation attempt table
CREATE TABLE IF NOT EXISTS source_operation_attempt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_identity TEXT NOT NULL UNIQUE,
    run_id INTEGER NOT NULL REFERENCES sports_enrichment_run(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_identity TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, IN_FLIGHT, SUCCEEDED, FAILED, ABANDONED
    lease_owner TEXT,
    lease_expires_at TEXT
);

-- 6. Capability selection history table
CREATE TABLE IF NOT EXISTS capability_selection_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_fixture_id INTEGER NOT NULL,
    team_id INTEGER,
    capability TEXT NOT NULL,
    analysis_cutoff_at TEXT NOT NULL,
    selected_observation_id INTEGER,
    selected_source TEXT NOT NULL,
    selected_status TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

-- 7. Analysis snapshot table
CREATE TABLE IF NOT EXISTS analysis_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version TEXT NOT NULL,
    run_id INTEGER NOT NULL REFERENCES sports_enrichment_run(id) ON DELETE CASCADE,
    canonical_fixture_id INTEGER NOT NULL,
    analysis_cutoff_at TEXT NOT NULL,
    status TEXT NOT NULL, -- COMPLETE, DEGRADED, BLOCKED
    snapshot_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT
);

-- 8. Add columns to existing tables for compatibility and integration
-- Note: SQLite ALTER TABLE ADD COLUMN is safe and idempotent if we check in Python,
-- but in SQL we just define them. The schema.py will run them safely.
