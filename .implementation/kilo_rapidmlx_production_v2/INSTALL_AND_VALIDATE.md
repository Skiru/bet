# Installation and Validation — Production v2

## 1. Credential cleanup and prerequisites

Revoke the Hugging Face token that appeared in the old launcher. Public Rapid-MLX aliases should not need a token.

```bash
brew install jq lsof uv node
npm install -g @kilocode/cli@7.3.41
python3 -m venv ~/.venvs/rapid-mlx-0.7.0
source ~/.venvs/rapid-mlx-0.7.0/bin/activate
python -m pip install --upgrade pip
python -m pip install 'rapid-mlx==0.7.0'
```

Fish configuration:

```fish
set -gx RAPID_MLX_BIN "$HOME/.venvs/rapid-mlx-0.7.0/bin/rapid-mlx"
set -gx RAPID_MLX_PROFILE production
set -gx RAPID_MLX_TELEMETRY 0
```

## 2. Eliminate configuration ambiguity

From the repository root:

```bash
find . -maxdepth 3 -type f \
  \( -name 'kilo.json' -o -name 'kilo.jsonc' \
     -o -name 'opencode.json' -o -name 'opencode.jsonc' \
     -o -name 'kilo(*).jsonc' \) -print
```

During baseline validation, the project must have one active root configuration: `kilo.jsonc`. Temporarily move competing project-level configs out of the repository. Also inspect global resolution with `kilo debug paths` and `kilo debug config`.

## 3. Install the package

Back up current files, then copy this package into the repository root.

```bash
chmod +x scripts/local-llm.sh \
  scripts/rapid_mlx_soak.py \
  scripts/kilo_e2e_soak.py \
  scripts/kilo_context_guard_test.py \
  scripts/kilo_compaction_soak.py \
  scripts/mac_resource_monitor.py \
  scripts/sqlite_readonly.py \
  scripts/prod-check.sh

mkdir -p .kilo/artifacts/tool-output .kilo/state .kilo/runtime .kilo/logs reports
```

Kilo auto-loads `.kilo/plugin/*.ts` and `.kilo/tool/*.ts`. It will install the pinned `@kilocode/plugin` development dependency from `.kilo/package.json` using Bun.

## 4. Start with the safe profile

```bash
RAPID_MLX_PROFILE=safe ./scripts/local-llm.sh start
./scripts/local-llm.sh doctor
./scripts/local-llm.sh smoke
./scripts/local-llm.sh tool-smoke
./scripts/local-llm.sh multitool-smoke
./scripts/local-llm.sh stream-smoke
./scripts/local-llm.sh context-smoke
./scripts/local-llm.sh manifest
./scripts/local-llm.sh model-info
```

Run a raw server soak:

```bash
./scripts/rapid_mlx_soak.py \
  --rounds 60 \
  --pause 2 \
  --report reports/raw-safe-60.json
```

Monitor the Mac in a second terminal:

```bash
./scripts/mac_resource_monitor.py \
  --duration 7200 \
  --interval 5 \
  --output reports/mac-safe-2h.csv
```

## 5. Inspect Kilo's effective configuration

```bash
kilo --version
kilo config check
kilo debug paths
kilo debug config
kilo debug agent bet-orchestrator
kilo debug skill
kilo mcp list
kilo roll-call '^openai-compatible/qwen36-local-35b$' \
  --parallel 1 \
  --timeout 180000 \
  --output json
```

Expected versions are Kilo 7.3.41 and Rapid-MLX 0.7.0. Set version-drift environment variables only for an explicitly named compatibility experiment. The detached `kilo daemon` is not required for the VS Code extension: the extension owns a separate `kilo serve` process. Use daemon mode only for a separately designed headless workflow.

## 6. Deterministic custom-tool test

The production baseline does not use the archived SQLite reference MCP server. Test the hardened custom tool directly:

```bash
kilo debug agent bet-db-analyst \
  --tool bet_sqlite_query \
  --params '{"sql":"SELECT name, type FROM sqlite_master WHERE type = ''table'' ORDER BY name LIMIT 5","limit":5}'
```

The database is opened in `mode=ro`; the helper denies write opcodes and PRAGMA, bounds VM work, returns at most 200 rows and caps JSON output.

## 7. Kilo end-to-end and context tests

```bash
./scripts/kilo_e2e_soak.py \
  --turns 12 \
  --report reports/kilo-e2e-12.json

./scripts/kilo_context_guard_test.py \
  --report reports/kilo-context-guard.json

./scripts/kilo_compaction_soak.py \
  --turns 10 \
  --payload-chars 7000 \
  --report reports/kilo-compaction.json
```

The context-guard test must create a full output artifact, log a truncation and complete a subsequent turn. The compaction-pressure test must continue without `Compaction exhausted` even when its export does not expose an explicit compaction event.

For plugin isolation:

```bash
KILO_PURE=1 kilo config check
KILO_PURE=1 kilo debug config
```

## 8. Promote to the production profile

Only after all safe tests pass:

```bash
./scripts/local-llm.sh stop
RAPID_MLX_PROFILE=production ./scripts/local-llm.sh start
./scripts/prod-check.sh
```

Run the same raw soak and resource monitor under `production`, keeping separate reports. Compare p50/p95, maximum RSS, final swap and tool success rather than only tokens/second.

## 9. Phase lifecycle

1. Start a fresh session with `/start-phase A` (or B–E).
2. Load only `CURRENT_HANDOFF.md`, the phase handoff and exact required artifacts.
3. Keep one subagent active at a time.
4. Redirect verbose tool output to files; rely on the context guard as a last defense, not a normal workflow.
5. Before exit, invoke `/phase-handoff`.
6. Start the next phase in a new session.

Do not run the entire betting day A→E in one chat. Do not use sequential-thinking MCP or require public `<think>` output.

## 10. Acceptance criteria

- Zero `Compaction exhausted`, `ContextOverflowError`, crash or OOM.
- Raw chat/tool/multi-tool/streaming success is 100% in the baseline.
- Resolved limits are 28672/24576/4096.
- The custom SQLite tool is read-only and bounded.
- The context guard creates an artifact for deliberately oversized output and the next turn succeeds.
- The 60-round server soak and 12-turn Kilo session pass.
- Compaction-pressure continuation passes.
- One real phase-sized workload passes and writes a handoff.
- RSS plateaus and swap is not monotonically increasing.

## 11. Tuning sequence

Change one variable per run:

1. `safe`: prefill 1024, GPU utilization 0.66.
2. `production`: prefill 2048, GPU utilization 0.70.
3. `benchmark`: prefill 4096, GPU utilization 0.74.

Reject a faster profile if tool-call success decreases, p95 latency worsens after warm-up, memory pressure stays elevated, swap rises continuously or Kilo compaction becomes unreliable. Follow `BENCHMARK_AND_TUNING.md`; stock 4-bit is the certified baseline and OptiQ is promoted only after the identical tool/context/domain suite passes.
