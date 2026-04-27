---
name: s3b-time-sensitive
description: "STEP 3B: Lineup, weather, late injuries, odds movement — run 2-3h before earliest event"
agent: bet-statistician
---

# STEP 3B — TIME-SENSITIVE DATA COLLECTION

## TIMING
**MUST run within 2-3 hours of the earliest event kickoff.** Data from this step overrides earlier analysis. If findings contradict pick thesis → re-evaluate, downgrade, or void.

## INPUTS
- `betting/data/{date}_s7_gate.md` — APPROVED picks (✅ only) from the 17-point gate
- `betting/data/{date}_s5_odds_ev.md` — odds at analysis time (needed for drift calculation)
- All prior S3-S6 data as needed

## TASK
For EVERY approved candidate: verify lineups, check late injuries, check weather, check odds movement.

---

### 3B.1 — LINEUP & INJURY VERIFICATION

| Sport | What to check | Source | Timing |
|-------|--------------|--------|--------|
| **Football** | Confirmed lineup (XI + subs) | Flashscore lineups tab | ~1h before kickoff |
| **Tennis** | Not withdrawn? On order of play? | ATP/WTA official Order of Play | ~2h before |
| **Hockey** | Starting goalie CONFIRMED | DailyFaceoff.com / team Twitter | ~10am game day |
| **Basketball** | Injury report update (GTD/OUT) | ESPN NBA injury report | ~5h before |
| **Baseball** | Starting pitcher confirmed | ESPN MLB / BaseballSavant | ~2-3h before |
| **Speedway** | Full lineup (7 riders) confirmed | SportoweFakty / SpeedwayEkstraliga.pl | ~2-3h before |
| **Padel** | Pair not withdrawn? | PremierPadel.com draw | day of |
| **MMA** | No late opponent change? Weight made? | UFC.com / Tapology | weigh-in day |
| **Volleyball** | No roster surprise | Flashscore / team social | ~1h before |
| **Snooker** | Player not withdrawn | WorldSnooker / Flashscore | day of |
| **All sports** | Not postponed/cancelled/venue changed? | Flashscore / Sofascore | continuous |

**KEY ACTIONS:**
- Surprise benching of star player (football) → recalculate. If thesis depends on that player → VOID.
- Goalie change (hockey) → thesis for totals pick likely invalidated → VOID or recalculate.
- Pitcher change (baseball) → VOID the pick immediately.
- Rider substitution (speedway) → recalculate team total from new lineup.

### 3B.2 — WEATHER CHECK (outdoor sports)

| Sport | Weather impact | What to look for |
|-------|--------------|------------------|
| **Football** | Rain → fewer corners, slippery = fewer cards. Wind → more long balls, more corners | weather.com for match city |
| **Tennis** | Extreme heat → fatigue favors fitter player. Wind → serve quality drops, more breaks | event city forecast |
| **Speedway** | Rain → wet track → more falls, unpredictable | event city + speedway forums |
| **Padel** | Wind disrupts lobs (key padel shot) | outdoor venue weather |
| **Baseball** | Wind blowing out = +1.5 runs avg. Rain delay risk | ballpark weather |

**KEY ACTIONS:**
- If weather materially changes expected scoring → adjust pick line or confidence.
- Rain in speedway → reduce confidence by -1, or void if heavy.
- Wind blowing out at baseball → adjust totals up.

### 3B.3 — LATE NEWS SCAN

Check these sources for EVERY approved pick:
1. Flashscore match detail → "info" or "lineups" tabs
2. Team official social media (Twitter/X)
3. SportoweFakty for żużel lineups
4. ESPN injury report (US sports)
5. ATP/WTA withdrawal list (tennis)

**If any finding contradicts pick thesis** → recalculate EV. If EV now ≤ 0 → VOID.

### 3B.4 — ODDS MOVEMENT CHECK

For EVERY approved pick:
1. Compare CURRENT odds to odds at S5 analysis time
2. Calculate drift with EXPLICIT FORMULA (show the math, not just the result):
   ```
   drift_pct = 100 × ((current_odds / analysis_odds) - 1)
   Example: analysis 1.65, current 1.80 → 100 × (1.80/1.65 - 1) = +9.1%
   ```

**Action triggers:**
| Drift | Action | Required Evidence |
|-------|--------|-------------------|
| ≤3% | Normal — no action | Just note drift % |
| 3-8% | Note direction, check for news | Name 1 source checked for news |
| **>8%** | **MANDATORY RE-EVALUATION** | **Must check ≥3 things: (1) injury update, (2) lineup change, (3) sharp money signal. Write findings. No explanation found → SKIP the pick.** |
| >15% | Likely material news — VOID unless clear explanation found | Same as >8% plus Google search for breaking news |

3. Check for **Reverse Line Movement (RLM)**: line moving against public side = sharp money. Source: OddsPortal line history.
4. Check for **steam moves**: sudden dramatic movement = institutional bet. Source: OddsPortal.

**DRIFT TABLE (mandatory in output):**
```
## Odds Drift Summary
| Pick | Market | S5 Odds | Current Odds | Drift % | Source Checked | Action |
|------|--------|---------|-------------|---------|---------------|--------|
| PK-01 | O10.5 CK | 1.65 | 1.68 | +1.8% | — | ✅ OK |
| PK-02 | O22.5g | 1.55 | 1.72 | +11.0% | ESPN/FS/OP | 🔄 RE-EVAL: [finding] |
...
```
**The orchestrator will verify this table exists and that ALL >8% drifts have investigation notes.**

### 3B.5 — DECISION MATRIX

For each pick after 3B checks:

| Scenario | Action |
|----------|--------|
| All clear — lineup confirmed, weather OK, odds stable | ✅ CONFIRMED |
| Minor concern — backup player rested, slight weather | ⚠️ CONFIRMED with note — reduce confidence -0.5 |
| Material change — star out, goalie changed, pitcher swapped | 🔄 RE-EVALUATE — recalculate EV, may downgrade or void |
| Critical change — event postponed, key player injured, odds drifted >15% | ❌ VOID — remove from all coupons |

---

### OUTPUT FORMAT
Save to: `betting/data/{date}_s3b_time_sensitive.md`

**CRITICAL: The orchestrator will verify that (1) every pick has a status entry, (2) the Drift Summary Table exists, and (3) all >8% drifts have investigation notes.**

```
# Time-Sensitive Update — {date}
**Checked at**: HH:MM CEST (X hours before earliest event)

## Odds Drift Summary (orchestrator verifies this table)
| Pick | Market | S5 Odds | Current Odds | Drift % | Sources Checked | Finding | Action |
|------|--------|---------|-------------|---------|-----------------|---------|--------|
| PK-01 | O10.5 CK | 1.65 | 1.68 | +1.8% | — | — | ✅ OK |
| PK-02 | O22.5g | 1.55 | 1.72 | +11.0% | ESPN, FS, OP | No injury found | 🔄 SKIP (unexplained) |
...

## Pick Status Updates

### [Pick ID] — [Event]
- **Lineup**: [confirmed/pending/surprise — details]
- **Late injuries**: [none / list with source]
- **Weather**: [N/A / conditions + impact]
- **Odds movement**: analysis X.XX → current X.XX = drift X.X% [OK/RE-EVAL/VOID]
- **Status**: ✅ CONFIRMED / ⚠️ CONFIRMED (note) / 🔄 RE-EVALUATE / ❌ VOID
- **Action**: [none / reduce conf / swap coupon / remove]

...(repeat for every pick)...

## VOIDED PICKS
| Pick ID | Reason | Coupons Affected |
|---------|--------|-----------------|
...

## COUPON ADJUSTMENTS
If any pick voided, list which coupons need restructuring:
| Coupon | Voided Leg | Action (remove coupon / swap leg) |
|--------|-----------|----------------------------------|
...
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S3B-01**: Every approved pick has lineup/injury status checked
- [ ] **V-S3B-02**: Weather checked for ALL outdoor sport picks
- [ ] **V-S3B-03**: Odds drift calculated for every pick (formula shown)
- [ ] **V-S3B-04**: Drift >8% flagged with investigation result
- [ ] **V-S3B-05**: Any voided picks listed with affected coupons
- [ ] **V-S3B-06**: Coupon adjustments specified if picks voided
- [ ] **V-S3B-07**: Check performed within 2-3h of earliest kickoff
- [ ] **V-S3B-08**: Hockey: starting goalie confirmed or flagged
- [ ] **V-S3B-09**: Baseball: starting pitcher confirmed
- [ ] **V-S3B-10**: Speedway: full lineup confirmed from SportoweFakty

### PASS/FAIL GATE
- ALL checks pass → "S3B PASSED" → proceed to final coupon adjustments
- Voided picks → adjust coupons in S8, re-run V5 coupon arithmetic
