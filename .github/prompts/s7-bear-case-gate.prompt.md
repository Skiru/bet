---
name: s7-bear-case-gate
description: "STEP 7: Bear case + Red Flags + Contrarian + 13-point Pick Approval Gate"
agent: bet-analyst
---

# STEP 7 — BEAR CASE + RED FLAGS + PICK GATE

## INPUTS
- `betting/data/{date}_s6_context.md` — context + upset risk
- All prior S3-S6 data per candidate

## TASK
For EACH surviving candidate: build bear case, check red flags, think contrarian, run 13-point gate. This is the KILL STEP — weak picks die here.

### PER-CANDIDATE PROTOCOL:

#### 7A — BEAR CASE
- **Bull case** (2-3 sentences): why this bet wins
- **Bear case** (2-3 sentences): why this bet LOSES — must be SPECIFIC, not vague
- **If any tipster argued against your pick with facts** → bear case MUST respond to their argument
- **Key failure scenario**: what happens + estimated probability
- **20%-lower-odds test**: if Betclic odds were 20% lower, would you still take it? If NO → coupon-only (not highest confidence)

#### 7B — INSTANT RED FLAGS (§7.3)
Run the 30-second sport-specific checklist:

**Tennis**: WC/Q/LL? Fatigue (3h+ prev round)? First match on surface? Defending champion R1/R2? Identity slash? Odds drift >8%?
**Football**: Dead rubber? Cup rotation (CL/EL <5 days)? Derby? International break return? Synthetic pitch?
**Basketball**: B2B? Load management? Tank mode? Elimination game?
**Hockey**: Backup goalie? B2B? Down 0-3 in series? Goalie unconfirmed?
**Baseball**: Bullpen game? MLB debut pitcher? Wind blowing out? Day-after-night?
**Volleyball**: Playoff clinched? 5th set to 15? Home crowd >70%?
**Esports**: Stand-in? New patch <2 weeks? Online vs LAN? BO1?
**Snooker**: Long-format fatigue? Morning session? Century frequency mismatch?
**Darts**: Sets vs legs format? Premier League vs ranking? 180s power matchup?
**Handball**: European week rotation? 7m specialist absent?
**Table Tennis**: Division gap in cup? BO5 vs BO7? Withdrawal history?
**MMA**: Late opponent change? Failed weight cut? Layoff >1 year? Reach advantage?
**Padel**: New pair <3 events? Indoor vs outdoor? FIP gap <500?
**Speedway**: Rain/wet? Rider track record? Junior rider rule?

**ANY red flag fired → REJECT, DOWNGRADE, or explicitly JUSTIFY with data.**

#### 7C — CONTRARIAN THINKING (§7.4)
Four mandatory questions:
1. Am I applying the right MODEL to this SPECIFIC case?
2. What's the #1 way this bet type LOSES?
3. Would I take it FRESH at CURRENT odds (defeat anchoring)?
4. What would a SHARP DISAGREE-ER say?

If you can't refute #4 with data → pick is WEAK.

#### 7D — PICK APPROVAL GATE (§7.5) — 13 POINTS
Every pick MUST pass ALL 13:

| # | Check | Pass? |
|---|-------|-------|
| 1 | Player/team IDENTITY verified (full name, ranking, country) | |
| 2 | WC/Q/LL status checked (tennis: hard reject O22.5+ for WC) | |
| 3 | H2H fetched (≥5 meetings or "no H2H" noted) | |
| 4 | Injuries/suspensions checked (source named) | |
| 5 | ≥2 independent sources confirm thesis | |
| 6 | ≥1 argument-based tipster checked | |
| 7 | Upset risk scored (and ML ban enforced if applicable) | |
| 8 | EV > 0 calculated | |
| 9 | Odds drift < 8% (or re-evaluation done) | |
| 10 | Red flags cleared (or explicitly justified) | |
| 11 | Contrarian questions answered | |
| 12 | Bear case < Bull case (bear doesn't overwhelm) | |
| 13 | Not anchored to stale analysis (data is from TODAY) | |

**ANY check FAIL → pick is REJECTED or DOWNGRADED to watchlist.**

### ZERO TOLERANCE SHIELD — PROVEN FAILURES (scan EVERY candidate against this)

| # | What happened | Root cause | Check that prevents it |
|---|--------------|------------|------------------------|
| 1 | Shelton ML lost (3 sets, 36 games) | ML on tennis instead of game totals | NEVER default to ML. O22.5 would have won by +13.5. |
| 2 | Struff O22.5 lost (15 games) | Low upset risk = blowout, not close match | Paradox Rule: LOW upset risk → UNDER bias. |
| 3 | Jodar O22.5 lost (16 games) | Wildcard match → binary outcome | WC/Q/LL → O22.5+ HARD REJECT. |
| 4 | Jodar identity confusion | "Pedro Martinez / Jodar" slash | Full name + ranking + country. No slashes EVER. |
| 5 | Jodar odds drift ignored | 1.65→1.82 (+10.3%) not caught | >8% drift = MANDATORY re-eval. |
| 6 | Palmeiras date wrong | Match was May 14, not April 24 | V7b: verify EVERY event date on BetExplorer. |
| 7 | N11-01 in 5/7 coupons (71%) | No resilience coupon | >60% concentration → add coupon WITHOUT that pick. |
| 8 | ITF tennis all lost | Low-level tennis is unreliable | Skip ITF. Only ATP/WTA or strong Challengers. |
| 9 | HR1v5 combined odds wrong | No arithmetic shown | ALWAYS multiply legs explicitly. Show the math. |
| 10 | Liverpool O1.5 TG vs Palace | H2H not checked — Palace dominated | ALWAYS check H2H. Crystal Palace won ALL 3 recent. |
| 11 | PHI @ ATL direction wrong | "@" = Away @ Home confused | Verify home/away for EVERY event. |

**IF ANY PATTERN MATCHES → STOP. FIX. THEN CONTINUE.**

Additional fast checks:
- Tennis ML as default? → REJECT, switch to game totals
- Same pick in >60% coupons? → note for S8
- ITF tennis? → SKIP
- Night session treated as "compact"? → FULL PROCESS REQUIRED

### OUTPUT FORMAT
Save to: `betting/data/{date}_s7_gate.md`

```
## [Pick ID] — [Event] — [Market]

### Bull vs Bear
- **BULL**: [2-3 sentences]
- **BEAR**: [2-3 sentences]
- **Key failure scenario**: [what + probability]
- **20% lower test**: [YES still bet / NO coupon-only]

### Red Flags
| Flag | Fired? | Resolution |
|------|--------|------------|
| [sport-specific] | Y/N | [justify if Y] |

### Contrarian Answers
1. Right model? [answer]
2. #1 loss scenario? [answer]
3. Fresh at current odds? [answer]
4. Sharp counter? [answer + refutation]

### 13-Point Gate
| # | Check | PASS/FAIL |
|---|-------|-----------|
| 1-13 | ... | ... |

**FINAL VERDICT**: ✅ APPROVED (confidence X/5) / ❌ REJECTED (reason) / ⚠️ WATCHLIST (promote if...)
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S7-01**: Every candidate has bull AND bear case written
- [ ] **V-S7-02**: Bear case references specific data (not vague "could lose")
- [ ] **V-S7-03**: If tipster argued against → bear case responds to their argument
- [ ] **V-S7-04**: Red flag table completed for every candidate (sport-specific)
- [ ] **V-S7-05**: Every fired red flag has resolution (reject/downgrade/justify)
- [ ] **V-S7-06**: All 4 contrarian questions answered per candidate
- [ ] **V-S7-07**: 13-point gate completed (all 13 rows, not abbreviated)
- [ ] **V-S7-08**: No APPROVED pick has any FAIL in 13-point gate
- [ ] **V-S7-09**: Zero Tolerance patterns checked (ML default, WC, drift, date)
- [ ] **V-S7-10**: Rejected picks have clear reason documented

### PASS/FAIL GATE
- ALL checks pass → "S7 PASSED" → proceed to S8
