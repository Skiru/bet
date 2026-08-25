-- Migration 022: Pipeline Runtime Launch Bridge tables

CREATE TABLE IF NOT EXISTS pipeline_runtime_event_selection (
    run_id TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    fixture_id INTEGER,
    betting_date TEXT NOT NULL,
    decision TEXT NOT NULL,
    resume_action TEXT NOT NULL,
    observed_status TEXT,
    observed_kickoff TEXT,
    observation_timestamp_utc TEXT NOT NULL,
    provider TEXT,
    provider_event_id TEXT,
    source_evidence_sha256 TEXT,
    previous_analysis_status TEXT,
    previous_analysis_sha256 TEXT,
    previous_gate_status TEXT,
    previous_gate_sha256 TEXT,
    input_fingerprint TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, canonical_event_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runtime_event_selection_run_decision
    ON pipeline_runtime_event_selection(run_id, decision);
CREATE INDEX IF NOT EXISTS idx_pipeline_runtime_event_selection_date
    ON pipeline_runtime_event_selection(betting_date);

CREATE TABLE IF NOT EXISTS pipeline_event_stage_state (
    canonical_event_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    status TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    output_sha256 TEXT,
    receipt_sha256 TEXT,
    code_head TEXT NOT NULL,
    source_manifest_sha256 TEXT NOT NULL,
    model_registry_sha256 TEXT,
    provider_config_sha256 TEXT,
    run_id TEXT NOT NULL,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(canonical_event_id, stage_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_event_stage_state_run
    ON pipeline_event_stage_state(run_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_event_stage_state_stage
    ON pipeline_event_stage_state(stage_id, status);

CREATE TABLE IF NOT EXISTS pipeline_shadow_promotions (
    promotion_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    canonical_db_sha256_before TEXT NOT NULL,
    shadow_db_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    promoted_tables_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    receipt_sha256 TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_shadow_promotions_run
    ON pipeline_shadow_promotions(run_id);
