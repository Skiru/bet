# Model Resolution Audit

## Findings

- `bet-orchestrator` still declares explicit `model: google-vertex/gemini-3.5-flash-flex-high` in `.kilo/agents/bet-orchestrator.md` and `.kilo/profiles/kilo.local.jsonc`.
- Required specialist subagents no longer declare explicit `model:` fields in `.kilo/agents/*.md` or `.kilo/profiles/kilo.local.jsonc`; they are now configured to inherit the orchestrator model.
- Global Kilo config exposes `google-vertex` provider models including `gemini-3.5-flash-flex-high` mapped to API id `gemini-3.5-flash`.
- `KILO_CONFIG_CONTENT` presence: `absent`.
- `kilo debug config` reflects the inheritance repair in merged config.
- `kilo models google-vertex` lists `google-vertex/gemini-3.5-flash-flex-high`, so catalog/config visibility is present.
- Live `task` launches still fail with `ProviderModelNotFoundError`, so launchability is not yet proven.

## Config Sources Audited

- `AGENTS.md`
- `.kilo/agents/*.md`
- `.kilo/prompts/*.md`
- `.kilo/profiles/kilo.local.jsonc`
- `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/model_routing_audit.md`
- `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/model_routing_matrix.json`
- `scripts/kilo_agent_model_contract_check.py`
- `scripts/audit_bet_agent_roster.py`
- `tests/test_kilo_agent_model_contract.py`
- `tests/test_bet_agent_roster_contract.py`
- `docs/pipeline/Unified Orchestrated Analyst Session Contract.md`
- `docs/pipeline/Orchestrated Session Continuation Protocol.md`
- `~/.config/kilo/kilo.json`
- `~/.config/kilo/kilo.jsonc`
- `configs/kilo/kilo.jsonc` (project-local reference config)

## Resolver Interpretation

- `google-vertex/gemini-3.5-flash-flex-high`: resolvable in merged/global config and listed by `kilo models google-vertex`.
- `google-vertex/gemini-3.5-flash`: not a configured alias in the audited config.
- `gemini-3.5-flash-flex-high`: bare alias only; not used as the full runtime reference in the audited agent/profile config.
- `gemini-3.5-flash`: API-facing Vertex model id, not the configured Kilo alias.

## Interim Verdict

- File/config contract: repaired toward inherited-parent routing.
- Live runtime contract: still blocked by `ProviderModelNotFoundError` during subagent launch.
