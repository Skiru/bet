ALTER TABLE pipeline_runtime_plans ADD COLUMN stage_work_plan_path TEXT;
ALTER TABLE pipeline_runtime_plans ADD COLUMN stage_work_plan_sha256 TEXT;
ALTER TABLE pipeline_runtime_plans ADD COLUMN required_manifest_digest TEXT;
