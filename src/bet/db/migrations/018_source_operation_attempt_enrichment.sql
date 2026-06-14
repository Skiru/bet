-- Migration 018: Source Operation Attempt Enrichment
-- Add columns to source_operation_attempt to reconstruct full execution details

ALTER TABLE source_operation_attempt ADD COLUMN started_at TEXT;
ALTER TABLE source_operation_attempt ADD COLUMN completed_at TEXT;
ALTER TABLE source_operation_attempt ADD COLUMN http_status INTEGER;
ALTER TABLE source_operation_attempt ADD COLUMN error_code TEXT;
ALTER TABLE source_operation_attempt ADD COLUMN retry_count INTEGER;
ALTER TABLE source_operation_attempt ADD COLUMN parser_version TEXT;
ALTER TABLE source_operation_attempt ADD COLUMN dto_version TEXT;
ALTER TABLE source_operation_attempt ADD COLUMN evidence_bundle_id TEXT;
ALTER TABLE source_operation_attempt ADD COLUMN selectable INTEGER;
ALTER TABLE source_operation_attempt ADD COLUMN diagnostics TEXT;
