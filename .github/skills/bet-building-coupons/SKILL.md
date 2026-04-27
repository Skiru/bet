---
name: bet-building-coupons
description: "Coupon construction and validation — portfolio building rules (unique event per coupon), combo menu creation, correlation checks, coupon stress test (§8.2), risk tier labels (LR/MS/HR/N), V1-V10 validation suite, §S8.FINAL mechanical verification (arithmetic, placement order, cross-checks), and per-pick concentration limits. Use when building coupons from approved picks, validating coupon integrity, or generating final betting artifacts."
user-invokable: false
---

# Building Betting Coupons

Rules for constructing coupon portfolios and validating them. This skill covers the entire S8 process: ranking, building, stress-testing, validating (V1-V10), and mechanical verification (§S8.FINAL).

## Core Rules

1. **NO SINGLES.** Every pick in a coupon. Min 2 legs per coupon.
2. **UNIQUE EVENT PER COUPON (ABSOLUTE)** in core portfolio. Zero sharing.
3. **Coupon count = f(quality, NOT money).** Scale: 4-5 picks → 2 core, 6-7 → 3, 8-9 → 4, 10+ → 5+.
4. **<4 approved picks → NO BET.** Don't produce shallow coupons as compromise.
5. **Max same-sport legs per coupon: 2.**

## Pick Ranking

Rank approved picks by: EV (highest) → confidence → price_gap favorability.

## Core Portfolio

Assign picks to coupons by ranking (best first):
- **Low-risk (LR)**: 2-3 legs, all confidence ≥4, combined odds 2.0-5.0
- **Multi-sport (MS)**: ≥2 sports, 2-4 legs, combined odds 3.0-10.0
- **Higher-risk (HR)**: 3-5 legs, combined odds 8.0-20.0, reduced stake
- **Night (N)**: only events after 22:00 CEST

Target: ≥2 LR, ≥1 MS, ≥1 HR. Scale up with approved picks.

## Combination Menu (COMBO)

After core portfolio, generate 4-8 extra combos remixing approved picks:
- Reuse from core portfolio IS allowed
- Each combo needs a distinct thesis (not reshuffled legs)
- Example theses: "all-corners combo", "safe-totals combo", "high-EV longshot", "3-sport diversifier"
- Label: COMBO-LR1, COMBO-MS1, COMBO-HR1, etc.
- Same rules: min 2 legs, max 2 same-sport, correlation check

## Correlation Check (per coupon)

- [ ] No two legs from same match
- [ ] Max 2 legs from same sport
- [ ] No correlated narratives (e.g., Team A ML + Team A O2.5 in different coupons)
- [ ] Home/away direction verified for EVERY event
- [ ] Combined odds: **MULTIPLY EACH LEG EXPLICITLY, SHOW THE MATH**

## §8.2 Coupon Stress Test (MANDATORY per coupon)

1. **Probability**: P(coupon) = P(leg1) × P(leg2) × ... If <10% → HR only. If <5% → drop a leg.
2. **Weakest-leg**: Which leg has lowest P(win)? Swap for better pick if possible without correlation.
3. **Catastrophe scenario**: "This coupon fails if [specific scenario]."
4. **Betclic market existence**: Verify market EXISTS. If not → drop or adjust line.

## Per-Coupon Reasoning (MANDATORY)

Under each coupon table:
- 1-2 sentences: WHY these legs combined
- P(coupon) estimate: "Szacowane prawdopodobieństwo: ~XX%"
- Biggest risk: "Największe ryzyko: [specific scenario]"

## Per-Pick Concentration Limit

When user selects coupons (core + combos), compute per-pick exposure:
- Sum stakes of ALL SELECTED coupons containing that pick
- No single pick may account for >50% of total selected budget
- If exceeded → suggest swapping one coupon

## V1-V10 Validation Suite

### V1 — Artifact Consistency
pick_ids match across files, coupon_ids match, no duplicate IDs, unique event per coupon in core, stake sums correct.

### V2 — Per-Pick Sources
Tier A stats source, Tier A market source, EV > 0, confidence 1-5 justified.

### V3 — Tennis
Odds ratio graded, surface form checked, WC/Q/LL → O22.5+ HARD REJECTED, identity verified, drift <8%.

### V4 — Football
Market hierarchy respected, corner 3-source stack, BTTS league %, xG regression check.

### V4b-V4k — Other Sports
Each sport's specific validation (see sport-analysis-protocols).

### V5 — Coupon Structure
Min 2 legs, same-sport ≤2, no same-match, combined odds arithmetic shown, unique event per coupon.

### V6 — Portfolio Completeness
All approved picks assigned (no orphans), ≥4 combo coupons, multi-sport diversification, total stakes exceed daily cap.

### V7 — Weaknesses
Borderline/conditional picks listed, dates verified for EVERY event, cross-coupon integrity.

### V8 — Source Completeness
≥2 independent sources + ≥1 tipster per pick, sport-specific sources checked, H2H stat-specific (V8b), statistical market ranking audit (V8c).

### V9 — Coupon Optimization
Ranked by EV×confidence, no orphan picks, no ≥3 same-market-type, night coupons = night games only, weakest-leg swap test.

### V10 — Final Sign-Off
V10a: Forced 14-sport enumeration. V10b: 17-point gate per pick. V10c: Red flags addressed. V10d: Portfolio damage test. V10e: PER-PICK COMPLETENESS MATRIX (10 columns, all ✅).

### V10e Matrix Template
```
| Pick ID | Tipster≥1 | H2H≥5 | H2H-Stat | StatRank | 3WayChk | Injuries | Sources≥2 | RedFlags | EV>0 | Gate17 | PASS |
|---------|-----------|--------|----------|----------|---------|----------|-----------|----------|------|--------|------|
```
ALL 10 columns ✅ for EVERY pick. ANY ❌ → STOP, fix, re-check. No coupon file without this matrix.

## §S8.FINAL Mechanical Verification

### A. Coupon Arithmetic
Multiply each leg step by step. Compare to listed combined odds. Tolerance ±0.02.
```
Example: 1.50 × 1.55 = 2.325; 2.325 × 1.60 = 3.720
```
Also: Return = Combined odds × Stake.

### B. Placement Order
Trace pick IDs in each coupon → find earliest kickoff → deadline = earliest minus 30-60 min.

### C. Pick-Coupon Cross-Check
Every pick in ≥1 coupon. No pick in >60% of coupons. Max 2 same-sport per coupon.

### D. Home/Away Direction
US sports: "@" = Away @ Home. BetExplorer: "Home vs Away". Cross-check.

### E. EV Consistency
Verify stated EV matches formula: `EV = (true_prob × odds) - 1`.

### F. Price Gap Flagging
Picks outside threshold (−3% LR, −5% HR) → FLAG.

### G. Total Exposure
Sum all stakes. Compare to listed total. Verify against 25% bankroll limit.

## Watchlist

2-5 backup picks not in any coupon:
```
| Pick | Market | Promote if... |
|------|--------|---------------|
| [event] | [market] | Betclic odds ≥ X.XX |
```

Include §4.3 tipster-sourced picks with full argument, accuracy %, and promotion criteria.

## Connected Skills

- `bet-formatting-artifacts` — output format standards for coupon files, Polish descriptions, ledger CSVs
- `bet-analyzing-statistics` — market hierarchy and statistical ranking that informs pick selection
- `bet-applying-sport-protocols` — sport-specific validations (V3, V4, V4b-V4k)
- `bet-evaluating-odds` — EV calculations and staking rules used in coupon construction
