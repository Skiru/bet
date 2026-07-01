# Betting Agent Runtime Smoke Contract

## Scope

- This contract defines valid runtime smoke proof for the betting agent system without weakening no-false-PASS, no-silent-omission, anti-loop, role-boundary, or Superbet safety gates.
- The active Kilo UI runtime model remains the source of truth for the parent session.

## Smoke Types

### PRIMARY_AGENT_CONFIG_SMOKE

- Applies to agents with `mode=primary` or `mode=all` when used as primary.
- `bet-orchestrator` must be evaluated this way.
- Do not launch a primary agent through the subagent task interface.
- Verify config, permissions, prompt coverage, no explicit provider/model override, and output schema.
- Verify the agent can write a tiny smoke artifact when a direct primary session is available.
- If the internal runtime cannot launch the primary agent programmatically, the smoke may still PASS on config evidence alone.

### DELEGATED_SUBAGENT_LAUNCH_SMOKE

- Applies to required specialist agents launched through parent delegation.
- The delegated smoke must launch, write a role-local artifact, record `ProviderModelNotFoundError=false`, and avoid silent fallback.
- An explicit conflicting provider/model override is a hard FAIL unless the user explicitly approved it and the override was independently smoke-tested.
- `inherited_parent_model` may be established in two ways:
- `PROVEN_BY_RUNTIME` when the runtime exposes that fact directly.
- `PASS_BY_CONTRACT` when the parent active runtime model is known, the child has no explicit override, delegated launch smoke passed, and `ProviderModelNotFoundError=false`.
- Child `ACTIVE_RUNTIME_MODEL=UNKNOWN_NOT_INTROSPECTABLE` does not fail by itself when inheritance passes by contract.
- Missing role-local artifact is a hard FAIL.

### DIRECT_ROLE_SMOKE

- Applies to manual `@agent` smoke runs.
- Valid only for launch, artifact, and tool-permission checks.
- Direct role smoke cannot by itself prove inheritance from the parent model.
- Direct role smoke must not be used as the sole proof for `inherited_parent_model`.

## PASS Rules

- E may PASS with `inherited_parent_model=PASS_BY_CONTRACT`.
- `ProviderModelNotFoundError=true` always FAILS.
- Silent fallback always FAILS.
- Explicit conflicting override always FAILS unless user-approved and separately smoke-tested.
- Unknown child runtime model only FAILS when it is combined with missing delegated-proof conditions.

## Required Record Fields

- `agent_name`
- `smoke_type`
- `launched`
- `artifact_written`
- `artifact_path`
- `provider_model_not_found_error`
- `explicit_model_override_detected`
- `active_parent_runtime_model`
- `child_runtime_model`
- `inheritance_proof_mode`
- `verdict`
- `blocker`

## Invalid Smoke Patterns

- Launching `bet-orchestrator` through the subagent interface.
- Requiring every child to self-report inheritance when the runtime does not expose it.
- Failing solely because a delegated child reports `UNKNOWN_NOT_INTROSPECTABLE` while the parent runtime is known and no override exists.
- Accepting missing role-local smoke artifacts.
