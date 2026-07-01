# Runtime Reload Instructions

- Kilo loads `.ts` / `.js` plugins from `.kilo/plugin/` at startup.
- In this repository, project documentation also states that `.kilo/tool/*.ts` is auto-loaded at startup, so duplicate same-name tool files can shadow or override the plugin copy.
- After changing `.kilo/plugin/bet_artifact_write.ts`, the user must fully restart Kilo/IDE or start a fresh Kilo runtime before trusting live tool behavior.
- A fresh smoke must call either `bet_artifact_write_capabilities` or a tiny write to `reports/pipeline_runs/...`.
- If live capability output does not show `plugin_version=pipeline-runs-allowlist-a1a00ff` or newer, runtime is stale.
- If a fresh live write still returns `schema_version=1` or `PATH_NOT_ALLOWED`, inspect and reconcile `.kilo/tool/bet_artifact_write.ts` before rerunning blocked pipeline work.
