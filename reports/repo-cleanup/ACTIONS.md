# Repository Cleanup Actions

**Generated:** 2026-06-12T13:45:00Z

## Safe Cleanup Actions

### Generated Cache Files (EPHEMERAL_RUNTIME)

| Path | Classification | Action | Reason |
|------|----------------|--------|--------|
| `scripts/__pycache__/` | GENERATED_CACHE | REMOVE | Python bytecode cache, regenerated on demand |
| `scripts/__pycache__/test-rapidmlx-baseline.cpython-312.pyc` | GENERATED_CACHE | REMOVE | Python bytecode |
| `scripts/__pycache__/test-rapidmlx-baseline.cpython-314.pyc` | GENERATED_CACHE | REMOVE | Python bytecode |

### macOS Metadata (GENERATED_CACHE)

| Path | Classification | Action | Reason |
|------|----------------|--------|--------|
| `./.DS_Store` | GENERATED_CACHE | REMOVE | macOS folder metadata |
| `./betting/.DS_Store` | GENERATED_CACHE | REMOVE | macOS folder metadata |
| `./.implementation/.DS_Store` | GENERATED_CACHE | REMOVE | macOS folder metadata |
| `./.implementation/kilo_rapidmlx_production_v2/.DS_Store` | GENERATED_CACHE | REMOVE | macOS folder metadata |
| `./.kilocode/.DS_Store` | GENERATED_CACHE | REMOVE | macOS folder metadata |

### Stale PID Files (EPHEMERAL_RUNTIME)

| Path | Classification | Action | Reason |
|------|----------------|--------|--------|
| `./.kilo/runtime/rapid-mlx.pid` | EPHEMERAL_RUNTIME | REMOVE | Stale PID (server not running) |
| `./reports/rapidmlx-baseline/runtime/rapid-mlx.pid` | EPHEMERAL_RUNTIME | REMOVE | Stale PID (server not running) |

---

## Files Retained

### Active Source (ACTIVE_SOURCE)

All source files retained:
- `.kilo/tool/bet_artifact_write.ts`
- `.kilo/tool/bet_script_run.ts`
- `scripts/fixtures/*`
- `scripts/validate-bet-agent-config.py`
- `scripts/validate-unattended-permissions.py`
- `scripts/test-bet-*.py`
- `scripts/test-closure-*.py`
- `scripts/test-kilo-*.py`
- `scripts/test-idempotency-*.py`
- `scripts/test-p2-regression.py`
- `scripts/test-prompt-injection-resistance.py`
- `scripts/generate-fingerprint.py`

### Active Configuration (ACTIVE_CONFIGURATION)

All configuration files retained:
- `kilo.jsonc`
- `AGENTS.md`
- `.kilo/agents/bet-*.md`
- `.kilo/skills/*/SKILL.md`
- `.kilo/docs/phase-4b-unattended-gate.md`
- `config/bet-script-operations.json`

### Durable Evidence (DURABLE_EVIDENCE)

All reports retained:
- `reports/agent-config/*`
- `reports/bet-script-executor/*`
- `reports/kilo-rapidmlx-baseline/*`
- `reports/rapidmlx-baseline/*`

### Deferred Archive (DEFERRED_ARCHIVE)

- `archive/deferred-kilo-tools/bet_sqlite_query.ts`

### Superseded Retained (SUPERSEDED_RETAINED)

- `kilo.jsonc.backup-20260612-090524`
- `kilo.jsonc.phase1-backup`

---

## Files Staged for Commit

### New Files (A)

- `.kilo/agents/bet-*.md` (13 files)
- `.kilo/docs/phase-4b-unattended-gate.md`
- `.kilo/skills/betting-evidence-contract/SKILL.md`
- `.kilo/skills/betting-pipeline-contract/SKILL.md`
- `.kilo/tool/bet_artifact_write.ts`
- `archive/deferred-kilo-tools/bet_sqlite_query.ts`
- `AGENTS.md` (modified)
- `kilo.jsonc` (modified)
- `reports/agent-config/*`
- `scripts/test-bet-artifact-write-runner.ts`
- `scripts/test-bet-artifact-write.py`
- `scripts/validate-bet-agent-config.py`
- `scripts/validate-unattended-permissions.py`

### Deleted Files (D)

- `.kilo/tool/bet_sqlite_query.ts` (moved to archive)

### Untracked Files to Stage

- `.kilo/tool/bet_script_run.ts`
- `config/bet-script-operations.json`
- `reports/bet-script-executor/*`
- `reports/kilo-rapidmlx-baseline/*`
- `reports/rapidmlx-baseline/*`
- `scripts/fixtures/*`
- `scripts/generate-fingerprint.py`
- `scripts/test-bet-script-executor.py`
- `scripts/test-closure-*.py`
- `scripts/test-idempotency-*.py`
- `scripts/test-kilo-*.py`
- `scripts/test-p2-regression.py`
- `scripts/test-prompt-injection-resistance.py`

### Untracked Files to Retain (Not Staged)

- `kilo.jsonc.backup-20260612-090524` (historical)
- `kilo.jsonc.phase1-backup` (historical)

---

## Ignore Rules

### Existing Ignore Patterns (Verified)

- `.venv/`
- `.env`
- `betting/data/`
- `__pycache__/`
- `*.pyc`
- `.kilo/artifacts/tool-output/`
- `.kilo/runtime/`
- `.kilo/logs/`
- `var/local-llm/`
- `/tmp/rapid-mlx.pid`
- `/tmp/rapid-mlx.log`

### Recommended Additions (Conservative)

None required. Existing `.gitignore` adequately covers generated files.

---

## Cleanup Execution

### Phase 1: Remove Generated Cache

```bash
rm -rf scripts/__pycache__
rm -f ./.DS_Store
rm -f ./betting/.DS_Store
rm -f ./.implementation/.DS_Store
rm -f ./.implementation/kilo_rapidmlx_production_v2/.DS_Store
rm -f ./.kilocode/.DS_Store
```

### Phase 2: Remove Stale PID Files

```bash
rm -f ./.kilo/runtime/rapid-mlx.pid
rm -f ./reports/rapidmlx-baseline/runtime/rapid-mlx.pid
```

### Phase 3: Stage Untracked Files

```bash
git add .kilo/tool/bet_script_run.ts
git add config/bet-script-operations.json
git add reports/bet-script-executor/
git add reports/kilo-rapidmlx-baseline/
git add reports/rapidmlx-baseline/
git add scripts/fixtures/
git add scripts/generate-fingerprint.py
git add scripts/test-bet-script-executor.py
git add scripts/test-closure-*.py
git add scripts/test-idempotency-*.py
git add scripts/test-kilo-*.py
git add scripts/test-p2-regression.py
git add scripts/test-prompt-injection-resistance.py
```

---

## Summary

| Category | Count |
|----------|-------|
| Files removed | 8 |
| Files retained | 100+ |
| Files staged | 80+ |
| Files not staged (historical) | 2 |
