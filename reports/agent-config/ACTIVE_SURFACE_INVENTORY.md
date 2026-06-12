# Active Surface Inventory

## Auto-loaded project surfaces

- `kilo.jsonc` — project root Kilo configuration and project-level overrides.
- `AGENTS.md` — root instruction file automatically loaded for project sessions.
- `.kilo/agents/*.md` — canonical project-local betting agents.
- `.kilo/skills/**/SKILL.md` — project-local skills.
- `.kilo/tool/*.ts` — active custom tools auto-loaded at Kilo startup.
- `.kilo/plugin/` — no active project plugins present.
- `.kilo/command/`, `.kilo/workflow/` — no active project command/workflow files present in this worktree.
- Global config: `/Users/mkoziol/.config/kilo/kilo.json` plus global agents; project config overrides it for Phase 4A betting agents.

## Explicitly non-active surfaces

- `.implementation/**`
- `archive/**`
- historical reports, backups, recovery directories, and documentation examples

## Active custom tools

| Tool | Active source path | Load mechanism | Intended agents | Resolved phase permission | Runtime load status | Dependency status |
|---|---|---|---|---|---|---|
| `bet_artifact_write` | `.kilo/tool/bet_artifact_write.ts` | Auto-loaded from `.kilo/tool/` at startup | `bet-orchestrator`, `bet-builder` | allow for orchestrator/builder; denied or unavailable elsewhere | ACTIVE_CERTIFIED | self-contained; depends only on Node stdlib and `@kilocode/plugin/tool` |
| `bet_script_run` | `.kilo/tool/bet_script_run.ts` | Auto-loaded from `.kilo/tool/` at startup | `bet-engineer` only | FIXTURE_ONLY | active | depends on `config/bet-script-operations.json` fixture manifest only |
| `bet_sqlite_query` | `archive/deferred-kilo-tools/bet_sqlite_query.ts` | not auto-loaded | none in Phase 4A | DEFERRED | inactive | missing helper/runtime intentionally quarantined |

## Notes

- No active project plugin extends permissions for betting agents.
- Active betting-agent runtime is offline: MCP servers disabled and betting agents deny web/MCP/database access.
- The quarantined database tool remains preserved under `archive/deferred-kilo-tools/` and is not part of the startup tool catalog.
