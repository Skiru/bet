-- Migration v15: Add fixture-scoped observations for temporal isolation
-- This migration creates a new table for fixture-scoped capability observations

-- Create fixture_capability_observation table
-- Each observation is immutable and tied to a specific fixture + team + capability + cutoff
CREATE TABLE IF NOT EXISTS fixture_capability_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Identity: fixture + team + capability + source + request
    canonical_fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    capability TEXT NOT NULL,
    source TEXT NOT NULL,
    request_identity TEXT NOT NULL,  -- Canonical request identity (method + url + sorted params)
    
    -- Evidence
    evidence_bundle_id TEXT NOT NULL DEFAULT '',
    native_fixture_id TEXT NOT NULL DEFAULT '',
    native_team_id TEXT NOT NULL DEFAULT '',
    
    -- Status
    status TEXT NOT NULL,  -- SourceResultStatus value
    http_status INTEGER,
    error_code TEXT NOT NULL DEFAULT '',
    retryable INTEGER NOT NULL DEFAULT 0,
    
    -- Parser metadata
    parser_version TEXT NOT NULL DEFAULT '',
    parser_diagnostics_json TEXT NOT NULL DEFAULT '{}',
    
    -- Temporal
    observed_at TEXT NOT NULL,
    valid_at TEXT NOT NULL,  -- analysis_cutoff_at
    
    -- Payload hash (for change detection)
    payload_sha256 TEXT NOT NULL DEFAULT ''
);

-- Unique constraint: one observation per fixture+team+capability+source+cutoff
-- This prevents duplicate observations for the same logical request
CREATE UNIQUE INDEX IF NOT EXISTS idx_fixture_capability_observation_identity
    ON fixture_capability_observation(
        canonical_fixture_id,
        team_id,
        capability,
        source,
        valid_at
    );

-- Lookup by fixture for downstream analysis
CREATE INDEX IF NOT EXISTS idx_fixture_capability_observation_fixture
    ON fixture_capability_observation(canonical_fixture_id, capability);

-- Lookup by team for form analysis
CREATE INDEX IF NOT EXISTS idx_fixture_capability_observation_team
    ON fixture_capability_observation(team_id, capability, valid_at);

-- Lookup by evidence bundle for replay
CREATE INDEX IF NOT EXISTS idx_fixture_capability_observation_bundle
    ON fixture_capability_observation(evidence_bundle_id);

-- Create fixture_capability_projection table
-- Selected projection for a fixture + team + capability + cutoff
-- This is mutable (can be updated when policy changes) but history is preserved
CREATE TABLE IF NOT EXISTS fixture_capability_projection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Identity: fixture + team + capability + cutoff
    canonical_fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    capability TEXT NOT NULL,
    analysis_cutoff_at TEXT NOT NULL,
    
    -- Selected result
    selected_source TEXT NOT NULL,
    selected_status TEXT NOT NULL,
    selected_observation_id INTEGER REFERENCES fixture_capability_observation(id),
    
    -- Fallback metadata
    primary_source TEXT NOT NULL DEFAULT '',
    primary_status TEXT NOT NULL DEFAULT '',
    fallback_reason TEXT NOT NULL DEFAULT '',
    
    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Unique constraint: one projection per fixture+team+capability+cutoff
CREATE UNIQUE INDEX IF NOT EXISTS idx_fixture_capability_projection_identity
    ON fixture_capability_projection(
        canonical_fixture_id,
        team_id,
        capability,
        analysis_cutoff_at
    );

-- Lookup by fixture for downstream analysis
CREATE INDEX IF NOT EXISTS idx_fixture_capability_projection_fixture
    ON fixture_capability_projection(canonical_fixture_id);

-- Update schema version
UPDATE schema_meta SET value = '15' WHERE key = 'version';
