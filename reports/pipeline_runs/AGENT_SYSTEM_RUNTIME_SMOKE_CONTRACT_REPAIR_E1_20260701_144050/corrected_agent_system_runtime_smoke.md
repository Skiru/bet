# Corrected Agent System Runtime Smoke Report

Run ID: `AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050`

## Scope

- Mode: launch-only
- Sports analysis: disabled
- Browser automation: disabled
- Operator APIs: disabled
- Active parent runtime model: `google-vertex/gemini-3.5-flash`

## Results

1. `bet-orchestrator`
- Smoke Type: `PRIMARY_AGENT_CONFIG_SMOKE`
- Launched: `false`
- Artifact Written: `true` (docs/pipeline/Betting Agent Runtime Smoke Contract.md)
- Verdict: `PASS`

2. `bet-enricher`
- Smoke Type: `DELEGATED_SUBAGENT_LAUNCH_SMOKE`
- Launched: `true`
- Artifact Written: `true`
- Artifact Path: `reports/pipeline_runs/AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050/bet-enricher_runtime_smoke.md`
- Active Runtime Model: `google-vertex/gemini-3.5-flash`
- Inheritance Proof Mode: `PASS_BY_CONTRACT`
- Verdict: `PASS`

3. `bet-statistician`
- Smoke Type: `DELEGATED_SUBAGENT_LAUNCH_SMOKE`
- Launched: `true`
- Artifact Written: `true`
- Artifact Path: `reports/pipeline_runs/AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050/bet-statistician_runtime_smoke.md`
- Active Runtime Model: `google-vertex/gemini-3.5-flash`
- Inheritance Proof Mode: `PASS_BY_CONTRACT`
- Verdict: `PASS`

4. `bet-valuator`
- Smoke Type: `DELEGATED_SUBAGENT_LAUNCH_SMOKE`
- Launched: `true`
- Artifact Written: `true`
- Artifact Path: `reports/pipeline_runs/AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050/bet-valuator_runtime_smoke.md`
- Active Runtime Model: `google-vertex/gemini-3.5-flash`
- Inheritance Proof Mode: `PASS_BY_CONTRACT`
- Verdict: `PASS`

5. `bet-challenger`
- Smoke Type: `DELEGATED_SUBAGENT_LAUNCH_SMOKE`
- Launched: `true`
- Artifact Written: `true`
- Artifact Path: `reports/pipeline_runs/AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050/bet-challenger_runtime_smoke.md`
- Active Runtime Model: `google-vertex/gemini-3.5-flash`
- Inheritance Proof Mode: `PASS_BY_CONTRACT`
- Verdict: `PASS`

6. `bet-builder`
- Smoke Type: `DELEGATED_SUBAGENT_LAUNCH_SMOKE`
- Launched: `true`
- Artifact Written: `true`
- Artifact Path: `reports/pipeline_runs/AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050/bet-builder_runtime_smoke.md`
- Active Runtime Model: `google-vertex/gemini-3.5-flash`
- Inheritance Proof Mode: `PASS_BY_CONTRACT`
- Verdict: `PASS`

7. `bet-test-engineer`
- Smoke Type: `DELEGATED_SUBAGENT_LAUNCH_SMOKE`
- Launched: `true`
- Artifact Written: `true`
- Artifact Path: `reports/pipeline_runs/AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050/bet-test-engineer_runtime_smoke.md`
- Active Runtime Model: `google-vertex/gemini-3.5-flash`
- Inheritance Proof Mode: `PASS_BY_CONTRACT`
- Verdict: `PASS`

## Verdict

- Overall Runtime Smoke Verdict: `PASS`
- All subagents launched successfully under delegation.
- All subagents wrote their role-local launch artifacts to the designated run directory.
- No ProviderModelNotFoundError detected.
- No explicit model overrides or conflicting overrides detected.
- Active parent-child model inheritance successfully proven via `PASS_BY_CONTRACT`.
