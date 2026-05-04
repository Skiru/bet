---
name: s7-bear-case-gate
description: "STEP 7: Bear case + Red Flags + Contrarian + 17-point Pick Approval Gate"
agent: bet-challenger
---

# STEP 7 — BEAR CASE + RED FLAGS + PICK GATE

## AUTOMATED FIRST

The pipeline runs `gate_checker.py` automatically:
- All 17 gate points evaluated programmatically
- Stats-first EV fix: candidates without odds pass gate #8 with advisory "user verifies manually"
- Gate #9 (drift) also passes with advisory when no odds available
- Red flags checked per sport-specific checklists
- Risk tier (LR/MS/HR/N) and confidence scoring
- 48h repeat check via picks-ledger
- Sport diversity check (§7.6)
- Produces `{date}_s7_gate_results.json` and `{date}_s7_gate_results.md`

**Agent role:** Build qualitative bear cases for borderline picks, construct adversarial arguments, verify Zero Tolerance Shield manually, check context that scripts can't access (injuries, weather, lineup changes).

## INPUTS
- `betting/data/{date}_s6_context.md` — context + upset risk
- All prior S3-S6 data per candidate

## TASK
For EACH surviving candidate: build bear case, check red flags, think contrarian, run 17-point gate. This is the KILL STEP — weak picks die here.

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

#### 7D — PICK APPROVAL GATE (§7.5) — 17 POINTS
Every pick MUST pass ALL 17:

| # | Check | Pass? |
|---|-------|-------|
| 1 | Player/team IDENTITY verified (full name, ranking, country) | |
| 2 | WC/Q/LL status checked (tennis: hard reject O22.5+ for WC) | |
| 3 | H2H fetched (≥5 meetings or "no H2H" noted) | |
| 4 | Injuries/suspensions checked (source named) | |
| 5 | ≥2 independent sources confirm thesis | |
| 6 | ≥1 argument-based tipster checked. If 0 after fallback chain → TIPSTER-BLIND: −0.5 confidence, NO LR coupon | |
| 7 | Upset risk scored (and ML ban enforced if applicable) | |
| 8 | EV > 0 calculated | |
| 9 | Odds drift < 8% (or re-evaluation done) | |
| 10 | Red flags cleared (or explicitly justified) | |
| 11 | Contrarian questions answered | |
| 12 | Bear case < Bull case (bear doesn't overwhelm) | |
| 13 | Not anchored to stale analysis (data is from TODAY) | |
| 14 | 48h repeat check: same team+market lost in last 48h → HARD REJECT (unless materially different) | |
| 15 | MULTI-MARKET COMPARISON: ≥3 stat markets calculated (§3.0). Best safety score selected. | |
| 16 | H2H STAT-SPECIFIC: H2H for EXACT stat exists (§3.0c). If missing → H2H-STAT-BLIND, −0.5 conf, no LR. | |
| 17 | THREE-WAY ALIGNMENT: L10 + H2H + L5 all support direction. 2/3 conflict → DOWNGRADE. | |

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
| 12 | Basketball blanket-rejected on 0/2 | Small sample panic | NEVER blanket-reject sport on <5 picks. FLAG ≠ BAN. |
| 13 | Football defaulted to corners (fouls/cards/shots not checked) | Tunnel vision on one stat | ALWAYS run §3.0 RANKING for ALL available stats. |
| 14 | Corner pick missing H2H corner data | H2H was match-level only | ALWAYS get H2H for the EXACT stat being bet (§3.0c). |
| 15 | Betclic history skipped → repeated failures | §0.2a not executed | ALWAYS read `betclic_bets_history.json` + run `analyze_betclic_learning.py`. |
| 16 | S3 output approved without §3.0 ranking table | Narrative instead of structured table | §3.0e template MANDATORY. §S3.3 must have ≥3 rows with real numbers. |
| 17 | Narrative analysis substituted for structured template | Paragraphs instead of §S3.1-§S3.10 sections | Every candidate MUST have all 10 sections. Missing markers = auto-reject. |
| 18 | Exotic league without Betclic market check | Full S3-S7 on no-market league | §1.7a: Check Betclic market existence BEFORE deep analysis. |
| 19 | 16/33 candidates skipped S3 entirely | S3 only for "top" candidates | 100% of non-PHANTOM candidates MUST receive full §3.0 analysis. |
| 20 | 58% shortlist was phantom fixtures (19/33) | Tipster-only events not cross-verified | §1.8: Verify every candidate against ≥2 non-tipster sources. |

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

### 17-Point Gate
| # | Check | PASS/FAIL |
|---|-------|-----------|
| 1-14 | ... | ... |

**FINAL VERDICT**: ✅ APPROVED (confidence X/5) / ❌ REJECTED (reason) / ⚠️ WATCHLIST (promote if...)

### DEEP ADVERSARIAL REASONING (MANDATORY — the thinking that makes picks battle-tested)
- **Scenario model**: BULL {P}% / BASE {P}% / BEAR {P}% — pick survives in [scenarios] — probabilities must sum to 100%
- **Assumptions challenged**: List top 5 assumptions in the thesis, challenge each with data. {N}/5 survived — weakest: [{assumption}]
- **Historical analogy**: [NONE / {similar past situation} → {outcome} → {relevance to this pick}]
- **Second-order effects**: [beyond obvious — e.g., "rain → fewer corners" is first-order; "rain → fewer goals → closer game → MORE corners from desperation" is second-order]
- **Bayesian update**: Prior P(hit)={X}% → Adjusted P(hit)={Y}% after context/tipster/analogy evidence
- **Adversarial verdict**: [ROBUST / FRAGILE / REJECT] — {1-sentence justification}
```

## DEEP ADVERSARIAL THINKING LAYER (MANDATORY — after gate, before submission)

The 17-point gate is mechanical. `gate_checker.py` handles that. YOUR unique value is ADVERSARIAL THINKING that scripts can't do:

### For EVERY candidate, think deeply:
1. **Model THREE scenarios** (Bull/Base/Bear) with explicit probabilities summing to 100%. The pick wins fully in BULL, partially in BASE, loses in BEAR. If BEAR > 30% → pick should be HR, not LR.
2. **Audit TOP 5 assumptions** in the thesis. Challenge each with contrary evidence. If ANY assumption fails → confidence drops.
3. **Search for historical analogies** — have you seen this exact situation before? Check Betclic history and picks-ledger for this team/player.
4. **Think second-order** — the obvious conclusion is already priced in. What happens NEXT? (e.g., key player injury → fewer set pieces is obvious → but also changes formation → might create MORE open play corners)
5. **Bayesian update**: Start with Poisson P(hit), then adjust for every piece of context evidence. State final adjusted probability explicitly. If >10% divergence from model, explain why.

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S7-01**: Every candidate has bull AND bear case written
- [ ] **V-S7-02**: Bear case references specific data (not vague "could lose")
- [ ] **V-S7-03**: If tipster argued against → bear case responds to their argument
- [ ] **V-S7-04**: Red flag table completed for every candidate (sport-specific)
- [ ] **V-S7-05**: Every fired red flag has resolution (reject/downgrade/justify)
- [ ] **V-S7-06**: All 4 contrarian questions answered per candidate
- [ ] **V-S7-07**: 17-point gate completed (all 17 rows, not abbreviated)
- [ ] **V-S7-08**: No APPROVED pick has any FAIL in 17-point gate
- [ ] **V-S7-09**: Zero Tolerance patterns checked (ML default, WC, drift, date)
- [ ] **V-S7-10**: Rejected picks have clear reason documented
- [ ] **V-S7-11**: Every APPROVED candidate has DEEP ADVERSARIAL REASONING section with all 6 fields (scenario model, assumptions challenged, historical analogy, second-order effects, Bayesian update, adversarial verdict)

### PASS/FAIL GATE
- ALL checks pass → "S7 PASSED" → proceed to S8
