-- Migration 024: registry bindings required for cryptographic event-stage reuse.

CREATE TABLE IF NOT EXISTS pipeline_event_stage_artifacts (
    canonical_event_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    output_path TEXT NOT NULL,
    output_sha256 TEXT NOT NULL,
    receipt_path TEXT NOT NULL,
    receipt_sha256 TEXT NOT NULL,
    artifact_root TEXT NOT NULL,
    stage_contract_version TEXT NOT NULL,
    policy_config_sha256 TEXT,
    producer TEXT NOT NULL,
    dependency_output_hashes_json TEXT NOT NULL DEFAULT '{}',
    dependency_status TEXT NOT NULL DEFAULT 'CURRENT'
        CHECK(dependency_status IN ('CURRENT', 'STALE', 'INVALIDATED')),
    registered_at TEXT NOT NULL,
    PRIMARY KEY(canonical_event_id, stage_id),
    FOREIGN KEY(canonical_event_id, stage_id)
        REFERENCES pipeline_event_stage_state(canonical_event_id, stage_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pipeline_event_stage_artifacts_run
    ON pipeline_event_stage_artifacts(run_id);
