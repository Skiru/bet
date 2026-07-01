# Runtime Tool Smoke Report

## Result

- `LIVE_TOOL_SMOKE=FAIL`

## Live Call

- Tool: `bet_artifact_write`
- Path: `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/artifact_writer_runtime_canary.json`
- Content type: `json`
- Purpose: canary write only; no J2A2 rerun

## Response

- `schema_version=1`
- `status=blocked`
- `error_code=PATH_NOT_ALLOWED`
- `plugin_version` field absent
- `allowed_report_roots` field absent
- `supports_reports_pipeline_runs` field absent

## Interpretation

- The currently loaded runtime is stale relative to the updated `.kilo/plugin/bet_artifact_write.ts`.
- The response shape matches the legacy implementation rather than the new provenance-bearing response schema.
- Because `.kilo/tool/bet_artifact_write.ts` still exists with the old allowlist, duplicate same-name sources remain the highest-probability explanation.
