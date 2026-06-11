# Operations Runbook

## Normal start

```fish
cd /Users/mkoziol/projects/bet
set -gx RAPID_MLX_PROFILE production
./scripts/local-llm.sh start
./scripts/local-llm.sh health
./scripts/prod-check.sh
```

Open a new Kilo session only after the gates pass.

## Kilo CLI role

Use Kilo CLI as the deterministic control plane for the same configuration used by the VS Code extension:

```fish
kilo --version
kilo config check
kilo debug paths
kilo debug config
kilo debug agent bet-orchestrator
kilo debug skill
kilo mcp list
kilo roll-call '^openai-compatible/qwen36-local-35b$' --parallel 1 --timeout 180000 --output json
kilo stats --project '' --models 10 --tools 20
```

The detached `kilo daemon` is optional and is not a stability fix for the VS Code extension. The extension owns a separate `kilo serve` child process. Use the daemon only for an explicitly designed headless/Console workflow, not in the baseline path.

## Start a phase

Create a new session for each phase group and use the `/start-phase` command. The canonical state is `.kilo/state/CURRENT_HANDOFF.md`, not the transcript.

Phase groups:

- A: S0 settlement and readiness;
- B: S1–S1e discovery and shortlist;
- C: S2 tipster acquisition;
- D: S2.3–S7 enrichment, analysis and gates;
- E: S8 construction and final validation.

Before moving to another phase, run `/phase-handoff`, verify the artifact, then start a new session.

## Recovery decision tree

### `Compaction exhausted`

1. Stop using the affected session.
2. Export it safely:

```fish
kilo export SESSION_ID --sanitize > reports/failed-session.json
```

3. Inspect `.kilo/runtime/context-guard.jsonl` and the latest handoff.
4. Confirm the context guard loaded:

```fish
./scripts/kilo_context_guard_test.py
```

5. Retry a minimal session with plugins disabled:

```fish
KILO_PURE=1 kilo run --agent rapid-smoke 'Reply with exactly PURE_OK.'
```

6. If pure mode succeeds, diagnose the plugin/custom-tool layer. If it fails, diagnose model metadata, provider limits and Rapid-MLX.
7. Resume in a new session from the handoff; do not continue the poisoned session.

### Rapid-MLX OOM or macOS stalls

```fish
./scripts/local-llm.sh stop
set -gx RAPID_MLX_PROFILE safe
./scripts/local-llm.sh start
./scripts/prod-check.sh
```

Do not run `sudo purge` as routine memory management. Close competing memory-heavy applications and let macOS manage unified memory.

### Tool call missing or malformed

1. Run `tool-smoke`, `multitool-smoke`, and `stream-smoke` directly against Rapid-MLX.
2. Run Kilo `roll-call` and the eight-turn Kilo E2E test.
3. Disable optional MCPs and retry.
4. Compare stock 4-bit and OptiQ only through the fixed benchmark suite.

### Unexpected config

```fish
kilo debug paths
kilo debug config
find . -maxdepth 3 -type f \( -name 'kilo*.json*' -o -name 'opencode*.json*' \) -print
```

Keep only one active project `kilo.jsonc` during qualification.

## Evidence collection

For every incident retain:

- `.kilo/runtime/rapid-mlx-8000.manifest.json`;
- `.kilo/runtime/rapid-mlx-8000.models.json`;
- `.kilo/runtime/rapid-mlx-8000.model-info.txt`;
- current Rapid-MLX log;
- sanitized Kilo session export;
- context-guard audit log;
- `prod-check` and soak reports;
- macOS resource CSV.

Never publish an unsanitized session, `.env`, API key or full betting database.
