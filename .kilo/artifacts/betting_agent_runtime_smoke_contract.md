# Betting Agent Runtime Smoke Contract Artifact

- `PRIMARY_AGENT_CONFIG_SMOKE`: primary agents such as `bet-orchestrator` are audited by config and prompt contract, not by subagent launch.
- `DELEGATED_SUBAGENT_LAUNCH_SMOKE`: required specialist subagents must launch via parent delegation, write a role-local artifact, and pass inheritance by runtime proof or `PASS_BY_CONTRACT`.
- `DIRECT_ROLE_SMOKE`: useful for launch and artifact checks only; it cannot prove inheritance alone.
- `ProviderModelNotFoundError=true`, silent fallback, explicit conflicting override, or missing delegated artifact remain hard failures.
- Child runtime `UNKNOWN_NOT_INTROSPECTABLE` is acceptable only when the parent runtime is known and inheritance passes by contract.
