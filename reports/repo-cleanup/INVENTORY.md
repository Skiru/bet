# Repository Cleanup Inventory

**Generated:** 2026-06-12T13:45:00Z
**Workspace:** /Users/mkoziol/projects/bet/.kilo/worktrees/cherry-juice
**Branch:** cherry-juice
**HEAD:** 3c8c2f3c49d3ec19772907f730b6e2c7c905f6c0

## Repository Identity

- **Root:** /Users/mkoziol/projects/bet/.kilo/worktrees/cherry-juice
- **Branch:** cherry-juice
- **Linked worktrees:**
  - /Users/mkoziol/projects/bet (776fef6, repair/rem-002b-closure)
  - /Users/mkoziol/projects/bet/.kilo/worktrees/cherry-juice (3c8c2f3, cherry-juice)

## Staged Files (A)

| Path | Classification |
|------|----------------|
| `.kilo/agents/bet-builder.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-challenger.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-db-analyst.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-engineer.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-enricher.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-orchestrator.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-reconciler.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-scanner.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-scout.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-settler.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-statistician.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-test-engineer.md` | ACTIVE_CONFIGURATION |
| `.kilo/agents/bet-valuator.md` | ACTIVE_CONFIGURATION |
| `.kilo/docs/phase-4b-unattended-gate.md` | ACTIVE_CONFIGURATION |
| `.kilo/skills/betting-evidence-contract/SKILL.md` | ACTIVE_CONFIGURATION |
| `.kilo/skills/betting-pipeline-contract/SKILL.md` | ACTIVE_CONFIGURATION |
| `.kilo/tool/bet_artifact_write.ts` | ACTIVE_SOURCE |
| `archive/deferred-kilo-tools/bet_sqlite_query.ts` | DEFERRED_ARCHIVE |
| `AGENTS.md` | ACTIVE_CONFIGURATION |
| `kilo.jsonc` | ACTIVE_CONFIGURATION |
| `reports/agent-config/*` | DURABLE_EVIDENCE |
| `scripts/test-bet-artifact-write-runner.ts` | ACTIVE_SOURCE |
| `scripts/test-bet-artifact-write.py` | ACTIVE_SOURCE |
| `scripts/validate-bet-agent-config.py` | ACTIVE_SOURCE |
| `scripts/validate-unattended-permissions.py` | ACTIVE_SOURCE |

## Deleted Files (D)

| Path | Classification | Status |
|------|----------------|--------|
| `.kilo/tool/bet_sqlite_query.ts` | DEFERRED_ARCHIVE | Moved to archive/ |

## Untracked Files (??)

| Path | Classification | Action |
|------|----------------|--------|
| `.kilo/tool/bet_script_run.ts` | ACTIVE_SOURCE | Stage |
| `config/bet-script-operations.json` | ACTIVE_CONFIGURATION | Stage |
| `kilo.jsonc.backup-20260612-090524` | SUPERSEDED_RETAINED | Retain as historical |
| `kilo.jsonc.phase1-backup` | SUPERSEDED_RETAINED | Retain as historical |
| `reports/bet-script-executor/*` | DURABLE_EVIDENCE | Stage |
| `reports/kilo-rapidmlx-baseline/*` | DURABLE_EVIDENCE | Stage |
| `reports/rapidmlx-baseline/*` | DURABLE_EVIDENCE | Stage |
| `scripts/fixtures/*` | ACTIVE_SOURCE | Stage |
| `scripts/generate-fingerprint.py` | ACTIVE_SOURCE | Stage |
| `scripts/test-bet-script-executor.py` | ACTIVE_SOURCE | Stage |
| `scripts/test-closure-*.py` | ACTIVE_SOURCE | Stage |
| `scripts/test-idempotency-*.py` | ACTIVE_SOURCE | Stage |
| `scripts/test-kilo-*.py` | ACTIVE_SOURCE | Stage |
| `scripts/test-p2-regression.py` | ACTIVE_SOURCE | Stage |
| `scripts/test-prompt-injection-resistance.py` | ACTIVE_SOURCE | Stage |

## Ignored Files (!!)

| Path | Classification | Action |
|------|----------------|--------|
| `.env` | UNRELATED_USER_CHANGE | Preserve (ignored) |
| `.kilo/.gitignore` | GENERATED_CACHE | Preserve |
| `.kilo/logs/` | EPHEMERAL_RUNTIME | Preserve (ignored) |
| `.kilo/node_modules/` | GENERATED_CACHE | Preserve (ignored) |
| `.kilo/package*.json` | GENERATED_CACHE | Preserve (ignored) |
| `.kilocode/*` | GENERATED_CACHE | Preserve (ignored) |
| `scripts/__pycache__/` | GENERATED_CACHE | Safe to remove |
| `var/` | EPHEMERAL_RUNTIME | Preserve (ignored) |

## Active Kilo Surfaces

### Agents (13 canonical betting agents)
- bet-builder
- bet-challenger
- bet-db-analyst
- bet-engineer
- bet-enricher
- bet-orchestrator
- bet-reconciler
- bet-scanner
- bet-scout
- bet-settler
- bet-statistician
- bet-test-engineer
- bet-valuator

### Non-betting agents (staged but not part of betting pipeline)
- code-simplifier.md (present in .kilo/agents/ but not referenced in kilo.jsonc)

### Skills (2 project skills)
- betting-evidence-contract
- betting-pipeline-contract

### Additional skills (runtime support, not auto-loaded)
- betting-pipeline-runtime
- context-safe-agentics

### Tools (2 active custom tools)
- bet_artifact_write.ts
- bet_script_run.ts

### Deferred Tools
- bet_sqlite_query.ts (moved to archive/deferred-kilo-tools/)

## MCP Status

All MCP servers disabled:
- memory: disabled
- brave-search: disabled
- context7: disabled
- playwright: disabled

## Validation Results

| Check | Status |
|-------|--------|
| Kilo config check | PASS |
| Agent validator | PASS (13 agents, 2 skills) |
| Unattended validator | PASS (183/183) |
| Git diff check | PASS (no trailing whitespace) |
| Python syntax validators | PASS |
| Bash syntax rapidmlx-baseline.sh | PASS |

## Rapid-MLX Status

- **Status:** Not running (stale PID file)
- **Model:** mlx-community/Qwen3.6-35B-A3B-4bit
- **Port:** 8000 (FREE)
- **Binary:** /Users/mkoziol/.venvs/rapid-mlx-0.7.1/bin/rapid-mlx

## Classification Summary

| Classification | Count |
|----------------|-------|
| ACTIVE_SOURCE | 25 |
| ACTIVE_CONFIGURATION | 18 |
| DURABLE_EVIDENCE | 60+ |
| DEFERRED_ARCHIVE | 1 |
| SUPERSEDED_RETAINED | 2 |
| EPHEMERAL_RUNTIME | 3 |
| GENERATED_CACHE | 5+ |
| UNRELATED_USER_CHANGE | 1 |
