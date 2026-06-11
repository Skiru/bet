# Kilo Code + Rapid-MLX Production Integration v2

Canonical integration for Kilo Code 7.3.41, Rapid-MLX 0.7.0 and Qwen3.6-35B-A3B 4-bit on an Apple M4 Pro with 48 GB unified memory.

Start here:

1. `PRODUCTION_REVIEW.md`
2. `MIGRATION_FROM_CURRENT.md`
3. `INSTALL_AND_VALIDATE.md`
4. `BENCHMARK_AND_TUNING.md`
5. `OPERATIONS_RUNBOOK.md`
6. `VALIDATION_REPORT.md`

Core files:

- `kilo.jsonc` — provider, model limits, agents, MCP and compaction.
- `AGENTS.md` — durable runtime and phase policy.
- `.kilo/plugin/production-context-guard.ts` — pre-history output truncation and compaction guard.
- `.kilo/tool/bet_sqlite_query.ts` — hardened read-only database tool.
- `scripts/local-llm.sh` — sole Rapid-MLX launcher.
- `scripts/prod-check.sh` — production gate runner.
- `BENCHMARK_AND_TUNING.md` — fixed A/B protocol for stock 4-bit, production profile and OptiQ.
- `OPERATIONS_RUNBOOK.md` — normal operation, Kilo CLI controls and incident recovery.

The package is production-designed, but it becomes production-qualified only after the target-Mac acceptance gates pass.
