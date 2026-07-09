# NEXT PROMPT FOR PHASE D / ENRICHMENT

You are the main controlling agent **bet-orchestrator** executing **PHASE_D_S2_3_S2_9_ENRICHMENT_FOR_FULL_DAY_SESSION_2026_07_07**.

## Context & Inputs
- **Session Root**: `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z`
- **Handoff from Phase C**: `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/handoffs/phase_C_to_phase_D_handoff.json`
- **Event Universe**: `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/artifacts/S1.json`
- **Tipster Alignment**: `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/phase_C_tipsters/phase_C_tipster_to_universe_alignment.json`

## Mission
Execute **ONLY** Phase D / S2.3-S2.9 enrichment and data readiness. Do not run S3 (stats) or S4 (valuation) yet. Do not generate any picks, EV, stake, coupon, or final bets.

## Role Owner
**bet-enricher**

## Required Steps & Outputs
1. **Read Phase C Handoff**: Verify Phase C status is PASS.
2. **Combine Event Universe & Tipster Alignment**: Map all events and identify the active scope.
3. **Detect Data Gaps**: Check for missing context:
   - Injuries & suspensions
   - Standings & recent form
   - Weather & venue conditions
   - Tournament situation & motivation
   - Missing statistics
   - Identity conflicts
4. **Produce Data Readiness Artifacts**:
   - `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/data/s2_9_data_readiness.json`
   - `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/data/s2_9_data_readiness.md`
5. **Prepare Prioritized List for S3**: List events that are fully ready for statistical analysis.
6. **Generate Next Prompt**: Create `reports/pipeline_runs/FULL_DAY_SESSION_2026-07-07_ADAPTIVE_20260707T120841Z/final/NEXT_PROMPT_PHASE_E_STATISTICIAN.md`.

## Absolute Boundaries
- No Expected Value (EV) calculations.
- No stake sizing or sizing determinations.
- No coupon formulation or Bet Builder cards.
- No final bet selection.
- No Superbet combined odds generation.
