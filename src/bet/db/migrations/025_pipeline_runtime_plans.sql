-- Migration 025: immutable runtime plans and continuation state machine.

CREATE TABLE IF NOT EXISTS pipeline_runtime_plans (
    plan_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    betting_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'CREATING', 'PLANNED', 'VALIDATING', 'READY', 'INVALIDATED',
        'EXECUTING', 'CONSUMED', 'FAILED'
    )),
    created_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL,
    canonical_db_path TEXT NOT NULL,
    canonical_db_sha256_at_snapshot TEXT NOT NULL,
    run_root_path TEXT NOT NULL,
    shadow_db_path TEXT NOT NULL,
    shadow_db_initial_sha256 TEXT NOT NULL,
    shadow_db_identity TEXT NOT NULL,
    selection_ledger_path TEXT NOT NULL,
    selection_ledger_sha256 TEXT NOT NULL,
    provider_observation_set_sha256 TEXT NOT NULL,
    runtime_s1e_path TEXT NOT NULL,
    runtime_s1e_sha256 TEXT NOT NULL,
    plan_checkpoint_path TEXT NOT NULL,
    plan_checkpoint_sha256 TEXT NOT NULL,
    plan_snapshot_path TEXT NOT NULL,
    plan_snapshot_sha256 TEXT NOT NULL,
    selected_event_set_sha256 TEXT NOT NULL,
    selected_event_count INTEGER NOT NULL CHECK(selected_event_count >= 0),
    minimum_lead_minutes INTEGER NOT NULL CHECK(minimum_lead_minutes >= 0),
    classification_policy_sha256 TEXT NOT NULL,
    code_head TEXT,
    code_tree TEXT,
    source_manifest_sha256 TEXT,
    continuation_started_at_utc TEXT,
    continuation_completed_at_utc TEXT,
    invalidated_at_utc TEXT,
    invalidated_reason TEXT,
    execution_started_at_utc TEXT,
    consumed_at_utc TEXT,
    validation_result_json TEXT,
    created_by TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runtime_plans_status
    ON pipeline_runtime_plans(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runtime_plans_date
    ON pipeline_runtime_plans(betting_date);
