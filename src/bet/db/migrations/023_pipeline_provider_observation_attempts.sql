-- Migration 023: Add pipeline_provider_observation_attempts table

CREATE TABLE IF NOT EXISTS pipeline_provider_observation_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    run_id TEXT NOT NULL,
    phase TEXT NOT NULL CHECK(phase IN ('PLAN', 'CONTINUATION')),
    attempt_number INTEGER NOT NULL CHECK(attempt_number >= 1),

    canonical_event_id TEXT NOT NULL,
    fixture_id INTEGER REFERENCES fixtures(id) ON DELETE SET NULL,

    provider TEXT NOT NULL,
    provider_event_id TEXT,

    attempted_at_utc TEXT NOT NULL,
    request_status TEXT NOT NULL CHECK(request_status IN (
        'SUCCESS',
        'FAILED',
        'UNSUPPORTED',
        'IDENTITY_MISSING',
        'IDENTITY_CONFLICT'
    )),

    raw_provider_status TEXT,
    canonical_event_status TEXT NOT NULL CHECK(canonical_event_status IN (
        'SCHEDULED',
        'LIVE',
        'FINISHED',
        'POSTPONED',
        'CANCELLED',
        'ABANDONED',
        'SUSPENDED',
        'WALKOVER',
        'AWARDED_TERMINAL',
        'UNKNOWN'
    )),

    raw_observed_kickoff TEXT,
    observed_kickoff_utc TEXT,

    observed_home_name TEXT,
    observed_away_name TEXT,
    participant_identity_sha256 TEXT,

    competition_identity_sha256 TEXT,

    upstream_evidence_bundle_id TEXT,
    upstream_evidence_refs_json TEXT,

    observation_envelope_sha256 TEXT,
    evidence_path TEXT,

    error_code TEXT,
    error_detail TEXT,

    created_at TEXT NOT NULL,

    UNIQUE(
        run_id,
        phase,
        canonical_event_id,
        provider,
        attempt_number
    )
);

CREATE INDEX IF NOT EXISTS idx_obs_attempts_run_phase
    ON pipeline_provider_observation_attempts(run_id, phase);

CREATE INDEX IF NOT EXISTS idx_obs_attempts_event_phase
    ON pipeline_provider_observation_attempts(canonical_event_id, phase);

CREATE INDEX IF NOT EXISTS idx_obs_attempts_fixture
    ON pipeline_provider_observation_attempts(fixture_id);

CREATE INDEX IF NOT EXISTS idx_obs_attempts_provider_ext
    ON pipeline_provider_observation_attempts(provider, provider_event_id);

CREATE INDEX IF NOT EXISTS idx_obs_attempts_request_status
    ON pipeline_provider_observation_attempts(request_status);

CREATE INDEX IF NOT EXISTS idx_obs_attempts_canonical_status
    ON pipeline_provider_observation_attempts(canonical_event_status);

CREATE INDEX IF NOT EXISTS idx_obs_attempts_attempted_at
    ON pipeline_provider_observation_attempts(attempted_at_utc);
