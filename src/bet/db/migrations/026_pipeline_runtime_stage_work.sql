CREATE TABLE IF NOT EXISTS pipeline_runtime_event_stage_work (
    plan_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    selection_run_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    fixture_id INTEGER,
    action TEXT NOT NULL CHECK(action IN ('EXECUTE', 'REUSE')),
    reason_code TEXT NOT NULL,
    stage_input_fingerprint TEXT NOT NULL,
    dependency_set_sha256 TEXT NOT NULL,
    required_chain_digest TEXT NOT NULL,
    selection_ledger_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(plan_id, stage_id, canonical_event_id)
);
CREATE TABLE IF NOT EXISTS pipeline_runtime_run_stage_work (
    plan_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action = 'EXECUTE'),
    input_event_set_sha256 TEXT NOT NULL,
    dependency_stage_set_sha256 TEXT NOT NULL,
    selection_ledger_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(plan_id, stage_id)
);
CREATE TABLE IF NOT EXISTS pipeline_runtime_run_stage_inputs (
    plan_id TEXT NOT NULL,
    run_stage_id TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    required_source_stage_id TEXT NOT NULL,
    expected_output_fingerprint TEXT NOT NULL,
    expected_output_sha256 TEXT,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(plan_id, run_stage_id, canonical_event_id, required_source_stage_id)
);
