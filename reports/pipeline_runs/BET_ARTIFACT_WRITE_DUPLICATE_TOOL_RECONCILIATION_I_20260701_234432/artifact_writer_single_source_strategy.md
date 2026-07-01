# Single Source Strategy

- Selected strategy: `STANDALONE_TOOL_SINGLE_SOURCE`
- Active source: `.kilo/tool/bet_artifact_write.ts`
- Reason: prior live smoke matched the standalone tool's legacy schema and allowlist, so the safest repair is to update the standalone source to the v2 contract and disable duplicate same-name plugin registration.

## Applied Changes

- Updated `.kilo/tool/bet_artifact_write.ts` to the v2 contract.
- Added `SCHEMA_VERSION = 2` and `TOOL_VERSION = "standalone-pipeline-runs-v2"`.
- Expanded the standalone tool allowlist to include `reports/pipeline_runs` while keeping `reports/betting` and `reports/betting-demo`.
- Preserved path traversal, encoded traversal, absolute-path, symlink-escape, extension, secret-content, JSON validation, and CAS overwrite protections.
- Added runtime provenance fields on success and blocked responses: `tool`, `tool_version`, `allowed_report_roots`, `supports_reports_pipeline_runs`, and `security`.
- Converted `.kilo/plugin/bet_artifact_write.ts` into provenance-only metadata so it no longer registers `bet_artifact_write`.

## Alternatives Rejected

- `PLUGIN_TOOL_SINGLE_SOURCE`: rejected because runtime behavior had already proven `.kilo/tool` was the most likely active source.
- `EQUIVALENT_DUPLICATE_TEMPORARY`: rejected because a true single registration is safer and simpler than carrying two active implementations.
