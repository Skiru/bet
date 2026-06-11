# Migration from the current mixed configuration

## Remove from active use

- The oMLX launcher.
- The Rapid-MLX 27B launcher with `--no-thinking`.
- Any launcher with a literal Hugging Face token.
- The old `start-local-model.fish` entry point.
- `kilo(3).jsonc` and competing `opencode.json(c)` during validation.
- Sequential-thinking MCP.
- `@latest` MCP package references.
- The 131K operational-context claim.

## Install

Copy the complete package into the repository root, preserving paths. Back up existing files first.

```bash
cp kilo.jsonc AGENTS.md .kilocodeignore <project>/
cp -R .kilo <project>/
cp scripts/local-llm.sh scripts/rapid_mlx_soak.py scripts/kilo_e2e_soak.py \
  scripts/kilo_context_guard_test.py scripts/kilo_compaction_soak.py \
  scripts/mac_resource_monitor.py scripts/sqlite_readonly.py scripts/prod-check.sh <project>/scripts/
chmod +x <project>/scripts/local-llm.sh <project>/scripts/*.py <project>/scripts/prod-check.sh
```

Revoke the exposed Hugging Face token before running anything.

## Documentation changes

Update the project README architecture table to:

```text
Inference server: Rapid-MLX 0.7.0
Model: Qwen3.6-35B-A3B 4-bit
Operational Kilo budget: 28,672 context / 24,576 input / 4,096 output
Reasoning: native reasoning, no required public chain-of-thought
Orchestration: Kilo agents, phase-bounded sessions, artifact handoffs
Start command: ./scripts/local-llm.sh start
```

Update the opening description so it no longer says the model is served by oMLX, and replace GitHub Copilot-specific agent terminology with Kilo agents if Kilo is now the production orchestrator.

## Database access migration

Remove `mcp-server-sqlite` from active Kilo configuration. The reference server is archived and has had unresolved security reports. Use `.kilo/tool/bet_sqlite_query.ts`, backed by `scripts/sqlite_readonly.py`, and update agent permissions/tool names accordingly.
