# Controller Mode Detection

- **Timestamp (UTC)**: 20260707T120841Z
- **Session Root**: reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z
- **Controller Mode**: PHASE_BOUNDED_ONE_PHASE_ONLY
- **Current Required Phase**: Phase A / S0 (Settler)
- **Required Next Agent**: bet-settler
- **Full Flow in One Session Allowed**: NO

## Rationale
The pipeline contract and runtime rules explicitly state that the controller is phase-bounded and must run exactly one phase per session. Context must not be carried across phases, and a fresh session must be started after each phase completion.
Therefore, the controller mode is determined to be `PHASE_BOUNDED_ONE_PHASE_ONLY`.
The current required phase is Phase A / S0 because the previous session closed with Phase A blocked/incomplete, and a fresh settlement baseline is required.
