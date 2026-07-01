# UI Selected Runtime Policy Audit

- Run ID: `UI_SELECTED_RUNTIME_MODEL_INHERITANCE_REPAIR_D_20260701_134441`
- Branch: `feat/subagent-provider-model-resolution-repair-b`
- Base branch: `feat/subagent-provider-model-resolution-repair-b`
- Scope: model policy repair only

## Findings Before Repair

- `AGENTS.md`
  Classification: hardcoded Gemini-only orchestrator and subagent routing contract.
  Evidence: `bet-orchestrator` required `google-vertex/gemini-3.5-flash-flex-high`; required subagents inherited a verified Gemini model only.
- `.kilo/agents/bet-orchestrator.md`
  Classification: explicit orchestrator provider/model override and Gemini-only runtime rules.
  Evidence: frontmatter `model:` pin plus Gemini-only model policy block.
- `.kilo/agents/bet-scanner.md`, `.kilo/agents/bet-scout.md`, `.kilo/agents/bet-enricher.md`, `.kilo/agents/bet-statistician.md`, `.kilo/agents/bet-valuator.md`, `.kilo/agents/bet-challenger.md`, `.kilo/agents/bet-builder.md`, `.kilo/agents/bet-test-engineer.md`, `.kilo/agents/bet-engineer.md`
  Classification: Gemini-only runtime-policy text in required betting agent instructions.
  Evidence: runtime model locked to `gemini-3.5-flash-flex-high`; GPT/OpenAI fallback explicitly forbidden.
- `.kilo/profiles/kilo.local.jsonc`
  Classification: project-profile default model pin and explicit `bet-orchestrator` model pin.
  Evidence: top-level `model` and `agent.bet-orchestrator.model` both set to `google-vertex/gemini-3.5-flash-flex-high`.
- `scripts/audit_bet_agent_roster.py`
  Classification: audit enforced a single target provider/model and treated non-Gemini runtime as failure.
  Evidence: `TARGET_ALIAS`, `TARGET_PROVIDER`, `TARGET_MODEL_KEY`, and failure path `forbidden_non_gemini_routing`.
- `tests/test_bet_agent_roster_contract.py`
  Classification: tests required explicit Gemini resolution for orchestrator and blocked non-Gemini success cases.
- `docs/pipeline/Unified Orchestrated Analyst Session Contract.md`
  Classification: contract required Gemini inheritance and forbade OpenAI/Claude/Qwen routing.
- `docs/pipeline/Orchestrated Session Continuation Protocol.md`
  Classification: continuation gate lacked active-runtime inheritance proof and only covered partial smoke.
- `reports/pipeline_runs/SUBAGENT_RUNTIME_REFRESH_SMOKE_C1_20260701_133313/active_runtime_model_after_refresh.md`
  Classification: report treated `openai/gpt-5.4` session runtime as insufficient because betting agents targeted Gemini.
- `reports/pipeline_runs/SUBAGENT_STRICT_GEMINI_RUNTIME_SMOKE_C2_20260701_134028/active_runtime_model_strict_gemini_proof.md`
  Classification: hard block on valid OpenAI UI-selected runtime.
  Evidence: `STATUS=BLOCKED_WRONG_ACTIVE_RUNTIME_MODEL` when active runtime was `openai/gpt-5.4`.

## Repair Decision

- Adopt `USER_SELECTED_KILO_UI_RUNTIME_INHERITANCE`.
- Remove required betting-agent model pins.
- Accept any user-accessible active UI-selected model when runtime is known and smoke proves inheritance with no silent fallback and no `ProviderModelNotFoundError`.
- Preserve non-model betting safety rules unchanged.
