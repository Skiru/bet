---
name: step7-bear-case
description: "STEP 7: Bear case + instant red flags + contrarian thinking + pick approval gate for each candidate. Final go/no-go."
agent: bet-analyst
argument-hint: "run_date=2026-04-25"
tools:
  - search
  - editFiles
  - memory/*
  - sequentialthinking/*
---

## Inputs
- **run_date** = ${input:run_date:today}
- **deep_stats** = `betting/data/{run_date}_deep_stats.md`
- **tipster_dive** = `betting/data/{run_date}_tipster_dive.md`
- **odds_ev** = `betting/data/{run_date}_odds_ev.md`

## Task

For EACH candidate that passed EV analysis, run the full devil's advocate protocol. Use sequentialthinking — one call per candidate.

### Per-Candidate Protocol (4 phases)

#### PHASE 1: Bull vs Bear Case
- **Bull case** (1-2 sentences): Why this bet wins. Best statistical argument.
- **Bear case** (1-2 sentences): Why this bet loses. Strongest counter-argument.
- **Tipster conflict response**: If ANY tipster argued against this pick with specific facts (from Step 4), the bear case MUST address their argument directly.
- **Streak dependency**: If thesis relies on streak >5 games → reduce confidence -1.
- **Regression risk**: xG mismatch? Overperformance? Unsustainable run?
- **Key failure scenario**: What's the single most likely way this bet loses? Estimated probability.
- **20% lower odds test**: Would you still bet at 20% lower odds? If NO → coupon leg only.

#### PHASE 2: Instant Red Flags (§7.3) — 30-second binary checks
Run the sport-specific table. ANY flag fired → address (reject/downgrade/justify with data):

| Sport | Red Flags |
|-------|-----------|
| Football | Dead rubber? Cup rotation (CL/EL ≤5 days)? Derby? International break return? Synthetic pitch? |
| Tennis | WC/Q/LL? Fatigue (3h+ prev round)? First match on surface? Defending R1/R2? Identity slash? Drift >8%? |
| Basketball | B2B? Load management? Tank mode? Elimination game? |
| Hockey | Backup goalie? B2B? Down 0-3? Goalie unconfirmed? |
| Baseball | Bullpen game? MLB debut? Wind blowing out? Day-after-night? |
| Volleyball | Playoff clinched? 5th set to 15? Home crowd >70%? |
| Esports | Stand-in? New patch <2 weeks? Online vs LAN? BO1? |
| Snooker | Long-format fatigue? Morning session? Century mismatch? |
| Darts | Sets vs legs? Premier League vs ranking? 180s power mismatch? |
| Handball | European week rotation? 7m specialist absent? |
| Table Tennis | Division gap in cup? BO5 vs BO7? Withdrawal history? |
| MMA | Late opponent change? Failed weight cut? Layoff >1 year? Reach advantage? |
| Padel | New pair <3 events? Indoor vs outdoor? FIP gap <500? |
| Speedway | Rain/wet? Rider track record? Junior rider rule? |

#### PHASE 3: Contrarian Thinking (§7.4) — 4 questions
1. Am I applying the right MODEL to this SPECIFIC case? (e.g., are league averages applicable to THIS match?)
2. What's the #1 way this bet type LOSES?
3. Would I take it FRESH at CURRENT odds? (defeat anchoring)
4. What would a SHARP DISAGREE-ER say?

#### PHASE 4: Pick Approval Gate (§7.5) — 13-point checklist
Every pick must pass ALL 13:
- [ ] 1. Identity verified (full name, correct opponent, correct date)
- [ ] 2. WC/Q/LL status checked (tennis)
- [ ] 3. H2H checked (last 5-10 meetings)
- [ ] 4. Injuries/suspensions checked
- [ ] 5. ≥2 independent sources used
- [ ] 6. ≥1 tipster argument checked (reasoning read)
- [ ] 7. Upset risk scored (if favorite ≤1.50)
- [ ] 8. EV > 0 calculated
- [ ] 9. Odds drift < 8%
- [ ] 10. No instant red flags (or flags justified)
- [ ] 11. Contrarian 4Q answered
- [ ] 12. Bear case weaker than bull case
- [ ] 13. Not anchored to previous version's pick

### Zero Tolerance Shield — Check BEFORE approving
Does this pick match any proven failure pattern?

| # | Pattern | Check |
|---|---------|-------|
| 1 | Tennis ML instead of game totals | Is this an ML pick? |
| 2 | Low upset risk = blowout not close match | Paradox Rule applied? |
| 3 | WC/Q/LL O22.5 | Hard reject? |
| 4 | Identity confusion (slash names) | Full name verified? |
| 5 | Odds drift >8% ignored | Drift checked? |
| 6 | Wrong date for match | Date verified on BetExplorer? |
| 7 | One pick in >60% of coupons | Will check in Step 8 |
| 8 | ITF tennis | Excluded? |
| 9 | Combined odds not verified | Will check in Step 8 |

### Output Format

Save to `betting/data/{run_date}_bear_case.md`:

```markdown
# Bear Case & Approval — {run_date}

## CANDIDATE: Arsenal vs Newcastle — Corners O9.5

### Bull Case
Arsenal's pressing generates corners. Newcastle counter-attacks create end-to-end play.

### Bear Case  
Newcastle may sit deep vs Arsenal at home, reducing corner opportunities. No corner-specific stats available.

### Red Flags
- [X] Dead rubber? NO — Arsenal title race
- [X] Rotation? POSSIBLE — CL semi next week → CHECK

### Contrarian 4Q
1. Model: League avg corners applied to THIS match — but Arsenal at home generate more than avg
2. #1 loss: Newcastle park bus, <5 corners first half, Arsenal cross instead of corner
3. Fresh: At 1.70 → yes, still take it
4. Sharp would say: No TotalCorner/SoccerStats backing = flying blind on corners

### Approval Gate: 11/13 PASS (missing: tipster argument, corner 3-source stack)
### VERDICT: APPROVED with flags / BORDERLINE / REJECTED
```
