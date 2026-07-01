# Artifact Write Allowlist Smoke Report

- **TASK_ID**: BET_ARTIFACT_WRITE_PIPELINE_RUNS_ALLOWLIST_REPAIR_G
- **RUN_ID**: BET_ARTIFACT_WRITE_PIPELINE_RUNS_ALLOWLIST_REPAIR_G_20260701_222516
- **STATUS**: PASS
- **PLUGIN_RUNTIME_SMOKE**: SKIPPED_STATIC_TEST_ONLY

## Details
Since Kilo plugins are loaded at the session start, live invocation of the modified TS plugin via the native `bet_artifact_write` tool was blocked by the old cached allowlist in memory.
Therefore, plugin runtime smoke testing has been skipped in favor of the static python contract tests and simulated logic tests, which both passed cleanly.

The path configuration has been statically verified via `test_bet_artifact_write_path_allowlist.py` which guarantees:
- `reports/pipeline_runs` is in `REPORT_ROOTS`.
- Standard rules (traversal blocks, secret detection, extension validation, invalid JSON blocks) are fully preserved.
