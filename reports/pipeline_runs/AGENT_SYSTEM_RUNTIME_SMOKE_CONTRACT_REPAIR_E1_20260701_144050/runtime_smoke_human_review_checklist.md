# Runtime Smoke Human Review Checklist

Run ID: `AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050`

## Questions & Answers

### 1. Why was E blocked?
E was blocked because of a mismatch between the runtime smoke test protocol and actual agent constraints. Specifically:
- It attempted to smoke-launch `bet-orchestrator` as a delegated subagent via the `task` interface, which is disallowed for primary agents.
- It demanded children self-report their active runtime model to prove inheritance, failing the run if the child returned `UNKNOWN` (due to local introspection limits) even if parent-model inheritance was active.
- Prompts for `bet-builder` and `bet-test-engineer` lacked an explicit requirement/rule to write a tiny role-local artifact when in `RUNTIME_SMOKE` mode, resulting in missing artifacts.
- An explicit model override was falsely reported as a conflict on `bet-challenger`.

### 2. Which blockers were invalid smoke assumptions?
- **Invalid Blockers / Assumptions:**
  - Launching `bet-orchestrator` via `task` delegation is an invalid subagent smoke assumption. Orchestrator is a primary agent (`mode: primary`).
  - Mandatory child model introspection as the sole inheritance proof is an invalid assumption. Child agents running locally often cannot introspect their hosting model reliably; inheritance is better proven via `PASS_BY_CONTRACT` (if the parent model is known, the child has no overrides, and the launch completes successfully).
  - The `bet-challenger` conflicting override was unsupported by any configuration/frontmatter model pins and was an artifact of prior testing assumptions.

### 3. Which blockers were real prompt/tool bugs?
- **Real Prompt / Tool Bugs:**
  - Missing "RUNTIME SMOKE MODE" section in prompts for `bet-valuator`, `bet-challenger`, `bet-builder`, and `bet-test-engineer`.
  - Lack of explicit instructions for `bet-builder` and `bet-test-engineer` to write exactly one tiny role-local artifact when task_id contains `RUNTIME_SMOKE`, causing the missing artifact failures.

### 4. Is `bet-orchestrator` correctly treated as primary?
Yes. It is classified under `PRIMARY_AGENT_CONFIG_SMOKE`. The audit script no longer requires it to launch through the subagent `task` interface, and validates its configuration, permissions, prompts, and schema statically instead.

### 5. Is inheritance proven by runtime or by contract?
Inheritance is proven **by contract** (`PASS_BY_CONTRACT`). This allows the smoke to pass successfully if the parent runtime model is known, the subagents have no explicit model overrides in their config/frontmatter, and the subagents launch and write their local artifacts successfully.

### 6. Did every subagent write a role-local artifact?
Yes. Every one of the 6 required subagents successfully wrote its launch-smoke artifact under `reports/pipeline_runs/AGENT_SYSTEM_RUNTIME_SMOKE_CONTRACT_REPAIR_E1_20260701_144050/`.

### 7. Did any subagent have explicit model override?
No. All required subagents have `explicit_model_override_detected: false`.

### 8. Is ProviderModelNotFoundError absent?
Yes. `ProviderModelNotFoundError=false` for all agents, meaning there were no model provider configuration errors or missing model IDs.

### 9. Is J2 safe after merge?
Yes. All 2356 tests passed, all audit scripts passed, and the corrected runtime smoke contract maintains strict safety checks (preventing silent fallbacks, unapproved overrides, and silent omission) while allowing legitimate deployment patterns to succeed.
