# NEXT PROMPT: PHASE C (BET-SCOUT)

Jesteś głównym agentem BET_ORCHESTRATOR wykonującym ADAPTIVE_FULL_DAY_PIPELINE_CONTROLLER_FOR_20_EVENT_BUILDER_PACK.

Wykonaj Phase C / S2 (Tipsters Discovery) zgodnie z kontraktem.

## State
- **Session Root**: reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z
- **Current Phase**: Phase C / S2 (Tipsters Discovery)
- **Role Owner**: bet-scout
- **Executed By**: bet-orchestrator

## Instructions
1. Invoke `bet-scout` to execute tipster consensus aggregation for 2026-07-07.
2. Run the tipsters script:
   `scripts/pipeline_steps/s2_tipsters.py`
3. Write Phase C handoff files:
   - `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/handoffs/phase_C_to_phase_D_handoff.json`
   - `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/handoffs/phase_C_to_phase_D_handoff.md`
4. Update `.kilo/state/phase-C-handoff.md` and `.kilo/state/CURRENT_HANDOFF.md`.
5. Generate `NEXT_PROMPT_PHASE_D_BET_ENRICHER.md` under `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/final/`.