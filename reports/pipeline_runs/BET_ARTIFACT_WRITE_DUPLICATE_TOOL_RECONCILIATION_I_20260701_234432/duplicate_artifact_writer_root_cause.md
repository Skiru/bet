# Duplicate Artifact Writer Root Cause

- Run ID: `BET_ARTIFACT_WRITE_DUPLICATE_TOOL_RECONCILIATION_I_20260701_234432`
- Root cause classification: `DUPLICATE_STANDALONE_TOOL_OVERRIDES_PLUGIN`
- Expected classification confirmed: `true`
- Likely active runtime source before repair: `.kilo/tool/bet_artifact_write.ts`

## Findings

- `.kilo/tool/bet_artifact_write.ts` existed as a standalone tool and registered `bet_artifact_write` via `export default tool(...)`.
- The standalone tool exposed legacy behavior before repair: `schema_version=1`, `REPORT_ROOTS=["reports/betting-demo", "reports/betting"]`, and no provenance fields.
- `.kilo/plugin/bet_artifact_write.ts` also existed and registered `bet_artifact_write` before repair, but contained the newer contract: `schema_version=2`, `reports/pipeline_runs`, `allowed_report_roots`, and `supports_reports_pipeline_runs`.
- Prior runtime smoke proved the live session was serving the legacy response shape and rejecting `reports/pipeline_runs`, which matches the stale standalone tool rather than the plugin implementation.
- No alternate `.kilo/tools`, `.kilocode/*`, or `~/.config/kilo/*` same-name sources were present.

## Verdicts By Source

- `.kilo/tool/bet_artifact_write.ts`: `UPDATE`
- `.kilo/plugin/bet_artifact_write.ts`: `REMOVE_OR_RENAME` from active registration path; preserved as provenance-only metadata
- `.kilo/tools/bet_artifact_write.ts`: `KEEP` as absent
- `.kilocode/tool/bet_artifact_write.ts`: `KEEP` as absent
- `.kilocode/plugin/bet_artifact_write.ts`: `KEEP` as absent
- `~/.config/kilo/tool/bet_artifact_write.ts`: `KEEP` as absent
- `~/.config/kilo/tools/bet_artifact_write.ts`: `KEEP` as absent
- `~/.config/kilo/plugin/bet_artifact_write.ts`: `KEEP` as absent
- `~/.config/kilo/plugins/bet_artifact_write.ts`: `KEEP` as absent

## Conclusion

A duplicate same-name project standalone tool overrode or shadowed the updated plugin implementation at runtime. Repair requires a single authoritative project source with the v2 allowlist/security contract and removal of duplicate same-name registration from the plugin path.
