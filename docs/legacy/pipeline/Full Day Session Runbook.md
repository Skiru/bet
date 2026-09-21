# Full Day Session Runbook

## Tipster Evidence Mandatory Pre-step

Before starting S3 (Statistics Analysis) or S4 (Odds Valuation), you must execute the certified shadow tipster evidence wrapper to gather public predictions. This provides essential market sentiment and community cross-check evidence for the session.

### Execution Commands

Run the following commands in the Fish shell:

```fish
set -gx RUN_DATE (date +%F)
set -gx SESSION_DIR reports/pipeline_runs/FULL_DAY_SESSION_$RUN_DATE
mkdir -p $SESSION_DIR/tipsters

.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_shadow_evidence.py \
  --date $RUN_DATE \
  --runtime-mode LIVE_SHADOW \
  --allow-live-network \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --include-certified-shadow \
  --max-pages-per-source 6 \
  --out $SESSION_DIR/tipsters/certified_shadow.json \
  --handoff-out $SESSION_DIR/tipsters/certified_shadow_handoff.json \
  --sqlite-db /tmp/full_day_session_tipsters.sqlite
```

---

## Instructions for the Daily-Session Agent

As the daily-session orchestrator, you must process the extracted tipster evidence during your execution cycle:

1. **Load Inputs Before S3/S4**:
   - Locate and parse `$SESSION_DIR/tipsters/certified_shadow_handoff.json` and `certified_shadow.json`.
   
2. **Summarize Sentiment**:
   - Summarize the aggregate tipster sentiment and choice distribution grouped by `normalized_event_key`.
   
3. **Audit Tracked Sources**:
   - Explicitly list and mark the source IDs used during the run. The active certified set must contain: `zawodtyper` and `typersi`.
   - **Typersi**: Treat strictly as a static table tip/sentiment source. Do not expect or attempt to find qualitative reasoning.
   - **ZawodTyper**: Treat as a potential qualitative community reasoning source when commentary is present.

4. **Highlight Analytical Conflicts**:
   - Actively seek and highlight contradictions between our internal statistical models and the tipster consensus.
   - Examples of critical conflicts:
     - Tipsters select Over whereas statistical models point to Under.
     - Tipsters select X2 (Draw or Away Win) whereas our models strongly back a Home Win.
     - Bookmaker odds/markets mismatch or duplicate events with conflicting ordering.

5. **Strict Boundary Enforcement (No Auto-Bets)**:
   - **DO NOT** output or propose any final bet, stake, coupon, or sizing purely based on tipster recommendations.
   - **DO NOT** calculate EV (Expected Value) or stake using tipster-indicated odds.
   - **DO NOT** form any final bet based purely on tipster recommendations.
   - **DO NOT** generate or combine odds for bookmaker coupons (e.g. Superbet combined odds) based on tipster data.

6. **Fallback and Resilience Protocols**:
   - If the handoff file is missing, corrupted, or if `fail_closed=true` is triggered:
     - **DO NOT** crash the full daily session.
     - Continue with the session, but explicitly flag the session state with: `TIPSTER_EVIDENCE_UNAVAILABLE`.
   - If `total_picks=0` is recorded:
     - Continue the session with a prominent warning flag. Do not abort the run unless the user has explicitly set a strict dependency on tipster evidence.
