# E Runtime Smoke Blocker Root Cause

Run ID: `AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050`

## Summary

- E was blocked by a mix of invalid smoke assumptions and real role-local smoke prompt gaps.
- The strongest blocker was an invalid proof model that tried to test `bet-orchestrator` as a subagent even though `.kilo/agents/bet-orchestrator.md:2` defines `mode: primary`.
- The previous smoke also treated child self-introspection as mandatory proof of inheritance even though no reliable Kilo runtime API is documented for that in `docs/pipeline/UI Selected Runtime Model Inheritance Policy.md:17-33`.

## Blocker Classification

1. `bet-orchestrator` cannot be smoke-launched through subagent interface
- Classification: `INVALID_PRIMARY_AS_SUBAGENT_SMOKE_TEST`
- Evidence: `.kilo/agents/bet-orchestrator.md:2` sets `mode: primary`.
- Evidence: prior smoke report marked `bet-orchestrator` blocked because it was "not invokable through the task subagent interface" in `reports/pipeline_runs/AGENT_SYSTEM_BATTLE_TESTED_PRODUCTION_AUDIT_E_20260701_140823/agent_system_runtime_smoke.md:15-18`.

2. Runtime smoke could not prove `inherited_parent_model=true`
- Classification: `INVALID_SELF_INTROSPECTION_REQUIREMENT`
- Evidence: the active UI runtime policy documents runtime source-of-truth and hard failures, but it does not expose a reliable child self-introspection API for inheritance proof in `docs/pipeline/UI Selected Runtime Model Inheritance Policy.md:17-33`.
- Evidence: the prior smoke report failed multiple agents because they returned `UNKNOWN`, not because any real override was found in `agent_system_runtime_smoke.md:19-78`.

3. `bet-valuator` reported `ACTIVE_RUNTIME_MODEL=UNKNOWN`
- Classification: `PROMPT_SMOKE_PROTOCOL_MISSING`
- Evidence: `.kilo/prompts/bet-valuator.md:1-47` had no runtime-smoke section, no tiny-artifact rule, and no instruction to return `UNKNOWN_NOT_INTROSPECTABLE` instead of fabricating a model.
- Evidence against override risk: `.kilo/agents/bet-valuator.md:1-33` contains no `model:` frontmatter override.
- Secondary note: introspection may also be unavailable, but the blocking defect was the missing prompt protocol for handling that case safely.

4. `bet-challenger` reported `CONFLICTING_EXPLICIT_OVERRIDE=true`
- Classification: `UNKNOWN_UNSUPPORTED_CONFLICT_CLAIM`
- Exact source: `UNKNOWN`
- Evidence: `.kilo/agents/bet-challenger.md:1-31` contains no `model:` frontmatter override.
- Evidence: `.kilo/prompts/bet-challenger.md:1-42` contained no runtime-smoke override logic and no explicit provider/model pin.
- Evidence: the only runtime smoke artifact for challenger was a 3-line generic file with no override proof in `.kilo/artifacts/bet_challenger_runtime_smoke.md:1-3`.
- Conclusion: the recorded conflict claim is unsupported by current file evidence and was most likely produced by the prior smoke path, not by a real checked override.

5. `bet-builder` wrote no smoke artifact
- Classification: `PROMPT_MISSING_SMOKE_ARTIFACT_RULE`
- Evidence: `.kilo/prompts/bet-builder.md:1-46` contained no runtime-smoke section and no explicit launch-only tiny-artifact requirement.
- Prior result: `artifact_written: false` in `agent_system_runtime_smoke.json:52-60`.

6. `bet-test-engineer` wrote no artifact and reported unknown model
- Classification: `PROMPT_MISSING_SMOKE_ARTIFACT_RULE`
- Evidence: `.kilo/prompts/bet-test-engineer.md:24-27` previously hard-failed unknown active runtime and `.kilo/prompts/bet-test-engineer.md:1-46` had no runtime-smoke section or role-local tiny-artifact rule.
- Prior result: `active_runtime_model: UNKNOWN` and `artifact_written: false` in `agent_system_runtime_smoke.json:62-70`.

## Real Fixes Required

- Add an explicit runtime smoke contract with separate primary, delegated, and direct-role smoke types.
- Teach smoke prompts to write exactly one tiny role-local artifact and to return `UNKNOWN_NOT_INTROSPECTABLE` when child model introspection is unavailable.
- Make the production audit accept `PASS_BY_CONTRACT` inheritance proof when parent runtime is known, no explicit override exists, delegated launch smoke passed, and `ProviderModelNotFoundError=false`.
