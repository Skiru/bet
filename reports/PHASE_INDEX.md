# Phase Index — Canonical Results

**Generated:** 2026-06-12T13:45:00Z
**Workspace:** cherry-juice worktree

---

## Phase 1 — Rapid-MLX Raw Baseline

| Attribute | Value |
|-----------|-------|
| **Status** | PASS |
| **Fingerprint** | `reports/rapidmlx-baseline/runtime/manifest.json` |
| **Canonical Report** | `reports/rapidmlx-baseline/REPORT.md` |
| **Canonical Result JSON** | `reports/rapidmlx-baseline/results.json` |
| **Acceptance Matrix** | N/A (baseline qualification) |
| **Source Files** | `scripts/rapidmlx-baseline.sh`, `scripts/test-rapidmlx-baseline.py` |
| **Deferred Capabilities** | None |

### Key Metrics
- Model: `mlx-community/Qwen3.6-35B-A3B-4bit`
- Decode tok/s: 71.94
- E2E tok/s: 67.67
- Warm TTFT: 277ms
- Tool reliability: 100%

---

## Phase 2 — Minimal Kilo Integration

| Attribute | Value |
|-----------|-------|
| **Status** | PASS |
| **Fingerprint** | `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/results.json` |
| **Canonical Report** | `reports/kilo-rapidmlx-baseline/REPORT.md` |
| **Canonical Result JSON** | `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/results.json` |
| **Acceptance Matrix** | `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/KILO_BASELINE_ACCEPTANCE_MATRIX.md` |
| **Source Files** | `kilo.jsonc`, `.kilo/prompts/rapid-smoke.md`, `.kilo/prompts/mcp-smoke.md` |
| **Deferred Capabilities** | MCP servers disabled, web search disabled |

### Key Results
- Context prefix cache: 12.4x speedup
- Kilo config check: PASS
- Model route: `openai-compatible/qwen36-local-35b`

---

## Phase 3 — Script Executor Closure

| Attribute | Value |
|-----------|-------|
| **Status** | PASS |
| **Fingerprint** | `reports/bet-script-executor/fingerprint.json` |
| **Canonical Report** | `reports/bet-script-executor/REPORT.md` |
| **Canonical Result JSON** | `reports/bet-script-executor/results.json` |
| **Acceptance Matrix** | `reports/bet-script-executor/SCRIPT_EXECUTOR_ACCEPTANCE_MATRIX.md` |
| **Source Files** | `.kilo/tool/bet_script_run.ts`, `config/bet-script-operations.json`, `scripts/fixtures/*` |
| **Deferred Capabilities** | Real scripts disabled, fixture-only mode |

### Key Results
- Fixture executor: Active
- Real scripts: DEFERRED
- Cancellation tests: PASS
- Redaction tests: PASS
- Timeout tests: PASS

---

## Phase 4A — Unattended Agent Configuration

| Attribute | Value |
|-----------|-------|
| **Status** | PASS (AGENT_CONFIG_PASS) |
| **Fingerprint** | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/SHA256SUMS.txt` |
| **Canonical Report** | `reports/agent-config/REPORT.md` |
| **Canonical Result JSON** | `reports/agent-config/results.json` |
| **Acceptance Matrix** | `reports/agent-config/AGENT_CONFIG_ACCEPTANCE_MATRIX.md` |
| **Source Files** | `.kilo/agents/bet-*.md`, `.kilo/skills/betting-*-contract/SKILL.md`, `.kilo/tool/bet_artifact_write.ts`, `scripts/validate-bet-agent-config.py`, `scripts/validate-unattended-permissions.py` |
| **Deferred Capabilities** | Database (bet_sqlite_query), Web/MCP, Real scripts |

### Key Results
- Agents validated: 13
- Skills validated: 2
- Zero ask permissions: PASS
- Question denied: PASS
- MCP disabled: PASS
- Artifact writer qualification: 21/21 PASS

---

## Phase 4B — Unattended Synthetic Specialist Demonstration

| Attribute | Value |
|-----------|-------|
| **Status** | NOT STARTED |
| **Input Manifest** | `reports/agent-config/PHASE4B_INPUT_MANIFEST.json` |
| **Gate Document** | `.kilo/docs/phase-4b-unattended-gate.md` |
| **Deferred Capabilities** | TBD |

---

## Deferred Capabilities Summary

| Capability | Status | Evidence |
|------------|--------|----------|
| Database (bet_sqlite_query) | DEFERRED | `archive/deferred-kilo-tools/bet_sqlite_query.ts` |
| Real Scripts | DEFERRED | `config/bet-script-operations.json` (fixture-only) |
| Web Search | DISABLED | `kilo.jsonc` (MCP disabled) |
| Brave Search | DISABLED | `kilo.jsonc` (MCP disabled) |
| Context7 | DISABLED | `kilo.jsonc` (MCP disabled) |
| Playwright | DISABLED | `kilo.jsonc` (MCP disabled) |

---

## Superseded Reports (Historical)

The following reports are retained as historical evidence but are not current authority:

- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/` — SUPERSEDED by closure-20260612T080400Z
- `reports/agent-config/artifact-writer-qualification-20260612T111117Z.json` — SUPERSEDED by qualification-20260612T111336Z.json
- `reports/agent-config/artifact-writer-qualification-20260612T111204Z.json` — SUPERSEDED
- `reports/agent-config/artifact-writer-qualification-20260612T111241Z.json` — SUPERSEDED
- `reports/agent-config/artifact-writer-qualification-20260612T111319Z.json` — SUPERSEDED
