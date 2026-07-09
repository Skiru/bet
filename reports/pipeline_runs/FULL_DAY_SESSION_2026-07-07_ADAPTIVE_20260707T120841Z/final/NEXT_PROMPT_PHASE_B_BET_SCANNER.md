# NEXT PROMPT: PHASE B (BET-SCANNER)

Jesteś głównym agentem BET_ORCHESTRATOR wykonującym ADAPTIVE_FULL_DAY_PIPELINE_CONTROLLER_FOR_20_EVENT_BUILDER_PACK.

Wykonaj Phase B / S1 (Discover) zgodnie z kontraktem.

## State
- **Session Root**: reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z
- **Current Phase**: Phase B / S1 (Discover)
- **Role Owner**: bet-scanner
- **Executed By**: bet-orchestrator

## Instructions
1. Invoke `bet-scanner` to execute event universe discovery for 2026-07-07.
2. Run the discovery script:
   `scripts/pipeline_steps/s1_discover.py`
3. Write Phase B handoff files:
   - `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/handoffs/phase_B_to_phase_C_handoff.json`
   - `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/handoffs/phase_B_to_phase_C_handoff.md`
4. Update `.kilo/state/phase-B-handoff.md` and `.kilo/state/CURRENT_HANDOFF.md`.
5. Generate `NEXT_PROMPT_PHASE_C_BET_SCOUT.md` under `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/final/`.
