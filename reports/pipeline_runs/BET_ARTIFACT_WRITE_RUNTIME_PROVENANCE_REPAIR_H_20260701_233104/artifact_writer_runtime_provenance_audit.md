# Artifact Writer Runtime Provenance Audit

## Scope

- Task: `BET_ARTIFACT_WRITE_RUNTIME_PROVENANCE_REPAIR_H`
- Run: `BET_ARTIFACT_WRITE_RUNTIME_PROVENANCE_REPAIR_H_20260701_233104`
- Branch at audit time: `feat/bet-artifact-write-runtime-provenance-repair-h`
- Base verification SHA: `a1a00ff04352addaec063ae1c5821cb47cb218fc`

## Runtime Facts

- `KILO_PURE` present: `false`
- Current working directory: `/Users/mkoziol/projects/bet`
- Git worktree root: `/Users/mkoziol/projects/bet`
- Duplicate `bet_artifact_write` definitions detected: `true`
- Malformed path hypothesis: `false`

The blocked live path was a normal relative JSON path under `reports/pipeline_runs/...` and did not contain traversal, absolute path segments, encoding tricks, or an extension mismatch.

## Inventory

| Artifact | exists | contains_reports_pipeline_runs | report_roots_detected | plugin_id_or_tool_name_if_detectable | likely_load_order | risk |
|---|---:|---:|---|---|---|---|
| `.kilo/plugin/bet_artifact_write.ts` | true | true | `reports/betting-demo`, `reports/betting`, `reports/pipeline_runs` | `bet_artifact_write` | `project_plugin_dir` | `DUPLICATE_TOOL` |
| `.kilo/tool/bet_artifact_write.ts` | true | false | `reports/betting-demo`, `reports/betting` | `bet_artifact_write` | `unknown` | `ACTIVE_STALE_PLUGIN` |
| `.kilocode/plugin/bet_artifact_write.ts` | false | false | none | unknown | `unknown` | `OK` |
| `~/.config/kilo/plugin/` | false | false | none | unknown | `global_plugin_dir` | `OK` |
| `~/.config/kilo/plugins/` | false | false | none | unknown | `global_plugin_dir` | `OK` |
| `~/.config/kilo/kilo.json` | true | false | none | no direct `bet_artifact_write` registration found | `global_config` | `OK` |
| `~/.config/kilo/kilo.jsonc` | true | false | none | no direct `bet_artifact_write` registration found | `global_config` | `OK` |
| `configs/kilo/kilo.jsonc` | true | false | none | no direct `bet_artifact_write` registration found | `project_config` | `OK` |
| `.implementation/kilo_rapidmlx_production_v2/kilo.jsonc` | true | false | none | no direct `bet_artifact_write` registration found | `project_config` | `OK` |
| `kilo.jsonc.project-backup-20260615-133003` | true | false | none | permission references only | `project_config` | `OK` |
| `kilo.jsonc.phase1-backup` | true | false | none | not active in current root | `project_config` | `OK` |
| `kilo.jsonc.backup-20260612-090524` | true | false | none | not active in current root | `project_config` | `OK` |

## Key Evidence

1. Static project plugin now includes `reports/pipeline_runs`:
   - `.kilo/plugin/bet_artifact_write.ts`
   - `REPORT_ROOTS = ["reports/betting-demo", "reports/betting", "reports/pipeline_runs"]`

2. Duplicate project-local tool still excludes `reports/pipeline_runs`:
   - `.kilo/tool/bet_artifact_write.ts`
   - `REPORT_ROOTS = ["reports/betting-demo", "reports/betting"]`

3. Project documentation explicitly identifies `.kilo/tool/*.ts` as active at startup in this repo:
   - `reports/agent-config/ACTIVE_SURFACE_INVENTORY.md`
   - `.implementation/kilo_rapidmlx_production_v2/INSTALL_AND_VALIDATE.md`

4. Live session smoke still returned the old schema and old allowlist behavior:
   - direct `bet_artifact_write` canary to `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/artifact_writer_runtime_canary.json`
   - result: `schema_version=1`, `status=blocked`, `error_code=PATH_NOT_ALLOWED`

## Conclusion

Most likely active runtime condition:

1. Duplicate same-name project-local tool exists.
2. The current live session is not using the updated `.kilo/plugin/bet_artifact_write.ts` response shape.
3. The live tool response matches the legacy schema and legacy allowlist, which is consistent with `.kilo/tool/bet_artifact_write.ts` and/or a pre-reload cached copy of that older implementation.
4. Global plugin/tool shadowing was not supported by the discovered filesystem/config inventory.
5. Different worktree/project-root mismatch was not supported: `pwd` and `git rev-parse --show-toplevel` both resolved to `/Users/mkoziol/projects/bet`.

## Verdict

- `PROJECT_PLUGIN_SUPPORTS_REPORTS_PIPELINE_RUNS=true`
- `DUPLICATE_ARTIFACT_WRITER_DETECTED=true`
- `GLOBAL_STALE_ARTIFACT_WRITER_DETECTED=false`
- `LIVE_RUNTIME_STALE_OR_SHADOWED=true`
- `MOST_LIKELY_ACTIVE_SOURCE=.kilo/tool/bet_artifact_write.ts`
