---
name: s8-portfolio-coupons
description: "STEP 8: Portfolio construction, coupon building, V1-V10, artifact generation"
agent: bet-builder
---

# STEP 8 — PORTFOLIO + COUPONS + VALIDATION + ARTIFACTS

## INPUTS
- `betting/data/{date}_s7_gate.md` — approved picks with confidence scores
- All prior S1-S7 data
- `config/betting_config.json` — bankroll, limits, sport list

## TASK
Build coupons, validate V1-V10, write all artifacts.

---

## 8A — RANK APPROVED PICKS
1. List ALL approved picks from S7 (✅ only, not ❌ or ⚠️)
2. Rank by: EV (highest first) → confidence → price_gap favorability
3. Minimum requirement: ≥4 approved picks from ≥4 sports for betting. ≥5 picks from ≥5 sports = ideal. If <4 approved → declare NO BET day.
4. Need 10+ unique picks for 5 coupons × 2 legs. If not enough → 3-4 coupons OK.

## 8B — UNIQUE EVENT PER COUPON (ABSOLUTE — NEVER VIOLATE)
**Each pick appears in ONLY ONE coupon. Zero sharing. Each coupon is 100% independent.**

Assign picks to coupons by EV × confidence ranking (best picks get assigned first):
- 10 picks → 5 × 2-leg coupons
- 12 picks → 4 × 3-leg coupons, or mix of 2-leg and 3-leg
- 15 picks → 5 × 3-leg coupons, or 3 × 3-leg + 3 × 2-leg
- If <8 picks → 3-4 coupons. If <4 picks → NO BET.

Label: CP-{date}-LR01, LR02, ... (low-risk), MS01, ... (multi-sport), HR01, ... (higher-risk), N01, ... (night)

## 8C — DIVERSE COUPON TYPES
Build varied coupons from approved picks (each pick used ONCE):
- **Low-risk (LR)**: 2-3 legs, all confidence ≥4, combined odds 2.0-5.0
- **Multi-sport (MS)**: ≥2 sports, 2-4 legs, combined odds 3.0-10.0
- **Higher-risk (HR)**: 3-5 legs, combined odds 8.0-20.0, reduced stake
- **Night (N)**: only events after 22:00 CEST (if applicable)

## 8D — CORRELATION CHECK
For every coupon:
- [ ] No two legs from same match (inherent from unique-event rule)
- [ ] Max 2 legs from same sport per coupon
- [ ] No correlated narratives (e.g., Team A ML + Team A O2.5 in DIFFERENT coupons)
- [ ] **UNIQUE EVENT PER COUPON verified**: each pick in exactly 1 coupon
- [ ] Combined odds arithmetic: **MULTIPLY EACH LEG EXPLICITLY, SHOW THE MATH**
- [ ] **Home/away direction verified for EVERY event**: "@" = Away @ Home. BetExplorer = "Home vs Away". ALWAYS cross-check.

## 8E — STAKING
- Low-risk coupons: max 3.00 PLN
- Higher-risk coupons: max 2.00 PLN
- Total suggested exposure may exceed daily budget — user decides which to place
- Apply 1/4 Kelly guidance from S5 where available

## 8F — WATCHLIST
Picks not in any coupon but close to approval:
```
| Pick | Market | Promote if... |
|------|--------|---------------|
| [event] | [market] | Betclic odds ≥ X.XX |
```

## §8.2 — COUPON STRESS TEST (MANDATORY per coupon)
For EACH coupon, before finalizing:
1. **Probability estimate:** Multiply estimated true probabilities of all legs. P(coupon) = P(leg1) × P(leg2) × ... If P(coupon) < 10% → HR only. If < 5% → consider dropping a leg or splitting.
2. **Weakest-leg identification:** Which leg has the lowest P(win)? Can it be swapped for a better pick from the approved pool WITHOUT creating correlation? If yes → SWAP.
3. **Catastrophe scenario:** Write ONE sentence: "This coupon fails if [specific scenario]."
4. **Betclic market existence check:** Verify the market EXISTS on Betclic. If not (e.g., O20.5 games not offered, only O17.5) → drop or adjust line.

---

## V1-V10 VALIDATION (MANDATORY — EVERY CHECK)

Execute the full V1-V10 validation suite as defined in the `bet-building-coupons` skill. Key checks:
- **V1**: Artifact consistency — pick/coupon IDs match across files, unique event per coupon, stakes correct
- **V2**: Per-pick sources — Tier A stats + market source, EV > 0, confidence 1-5
- **V3**: Tennis — odds ratio graded, surface form, WC/Q/LL → O22.5+ rejected, drift <8%
- **V4**: Football — market hierarchy respected, corner 3-source stack, BTTS%, xG regression
- **V4b-V4k**: Other sports — per-sport validations (volleyball, esports, snooker, darts, handball, table tennis, MMA, padel, speedway) + upset risk for favorites ≤1.50
- **V5**: Coupon structure — min 2 legs, same-sport ≤2, combined odds arithmetic shown, home/away verified
- **V6**: Portfolio risk — exposure <25% bankroll, sport diversification ≥5
- **V7**: Weakness flagging — borderline/conditional picks, date verification (V7b), cross-coupon integrity (V7c)
- **V8**: Source completeness — ≥2 sources + tipster per pick, failed sources in source-log
- **V9**: Coupon optimization — ranked by EV×confidence, no orphans, weakest-leg swap test
- **V10**: Final sign-off — 14-sport enumeration (V10a), gate verification (V10b), red flags (V10c), portfolio damage (V10d), PER-PICK COMPLETENESS MATRIX 10-column (V10e)

Run ALL 10 checks. Report pass/fail per check with specific failing items. ANY ❌ → fix → re-verify.

---

## ARTIFACT GENERATION

### Coupon File: `betting/coupons/{date}-v{version}.md`

**MANDATORY SECTIONS (in this order):**

1. **Header**: date, bankroll, budget, version, odds_checked_at
2. **Conditional notice**: all picks CONDITIONAL — verify on Betclic
3. **AKTYWNE TYPKI (Active Picks) table**: all picks with ID, event, market, odds, conf, sport, kickoff
4. **KUPONY (Coupons)**: grouped by type (LOW-RISK, MULTI-SPORT, HIGHER RISK, NIGHT)
   - Per coupon: legs table, combined odds arithmetic shown, stake, return, weakest leg, sports list
5. **ARYTMETYKA KUPONÓW**: explicit multiplication for every coupon
6. **PODSUMOWANIE**: financial summary table + coupon table + budget variants (A/B/C)
7. **Per-pick ekspozycja**: which coupon each pick is in, stake
8. **UNIQUE-EVENT VERIFICATION**: confirm each pick in exactly 1 coupon
9. **KOLEJNOŚĆ STAWIANIA (Placement Order)**: when to place each coupon, time-sensitive first
10. **POMINIĘTE / USUNIĘTE (Removed Picks)**: every rejected pick with reason
11. **WATCHLIST**: picks not approved but close, with promotion criteria
12. **PORTFOLIO DAMAGE ASSESSMENT**: if top 2 picks fail → what coupons survive?
13. **CONDITIONAL NOTES**: time-sensitive checks user must do before placing
14. **V10e PER-PICK COMPLETENESS MATRIX**:
    ```
    | Pick ID | Tipster≥1 | H2H≥5 | H2H-Stat | StatRank | 3WayChk | Injuries | Sources≥2 | RedFlags | EV>0 | Gate17 | PASS |
    |---------|-----------|--------|----------|----------|---------|----------|-----------|----------|------|--------|------|
    ```
    ALL 10 columns ✅ for EVERY pick. ANY ❌ → STOP, fix, re-check.
15. **V1-V10 STATUS**: full validation status table
16. **USUNIĘTE WERSJE**: which old versions this supersedes

**Polish descriptions (MANDATORY on every leg):**
- Over = Powyżej, Under = Poniżej, Goals = bramek, Corners = rzutów rożnych
- Cards = kartek, Shots = strzałów, Games = gemów, Frames = frejmów
- Points = punktów, Rounds = rund, Sets = setów, Maps = map
- BTTS = Obie drużyny strzelą, ML = Zwycięstwo, HC = Handicap

Format per coupon:
```markdown
#### LR01 — Low-Risk #1 | CP-{date}-LR1

| # | Wydarzenie | Co obstawić | Kurs |
|---|-----------|------------|------|
| 1 | [Full event name] (Competition) | [Polish market description] | X.XX |
| 2 | [Full event name] (Competition) | [Polish market description] | X.XX |

**Kurs łączony:** X.XX × X.XX = **X.XX** | **Stawka: X.XX PLN** | Zwrot: X.XX PLN
**Najsłabsze ogniwo:** [pick_id] — [why it fails]
**Sporty:** Sport1 × N + Sport2 × M ✅
```

### Updates Required:
- `betting/journal/picks-ledger.csv` — add new picks, supersede old version
- `betting/journal/coupons-ledger.csv` — add new coupons, supersede old version
- `betting/journal/source-log.csv` — add source successes/failures
- `betting/journal/learning-log.csv` — process changes from this run
- `betting/reports/{date}.md` — daily report

### Financial Summary (end of coupon file):
```
| Metric | Value |
|--------|-------|
| Total coupons | X |
| Total suggested exposure | X.XX PLN |
| Bankroll | X.XX PLN |
| Exposure % | X.X% |
| Max single coupon stake | X.XX PLN |
| Picks from N sports | X |
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S8-01**: ≥5 coupons produced
- [ ] **V-S8-02**: Every pick in ≥1 coupon (no orphans)
- [ ] **V-S8-03**: Combined odds arithmetic SHOWN for every coupon
- [ ] **V-S8-04**: No pick in >60% of coupons (or resilience coupon added)
- [ ] **V-S8-05**: Polish descriptions on every leg
- [ ] **V-S8-06**: Financial summary present and accurate

---

## §S8.FINAL — MECHANICAL VERIFICATION (MANDATORY — last step before presenting)

**Run this AFTER all artifacts are written.** Use `sequentialthinking` for exact computation. This catches bugs that V1-V10 misses — proven by v18 where 3 bugs were found post-V10.

### A. COUPON ARITHMETIC RE-CALCULATION
For EVERY coupon, multiply each leg's odds step by step with exact decimal math.
```
CP-XX: leg1 × leg2 × leg3
Step: 1.50 × 1.55 = 2.325; 2.325 × 1.60 = 3.720
Listed: 3.72 → MATCH ✅ | Listed: 3.65 → MISMATCH ❌ → FIX
```
Also verify: Return = Combined odds × Stake. Fix rounding errors >0.02.

### B. PLACEMENT ORDER VERIFICATION
For EVERY coupon: identify picks → find each pick's kickoff → earliest kickoff → deadline = earliest minus ~30-60 min.
```
CP-XX has PK-01 (18:45) + PK-05 (19:00) → earliest 18:45 → deadline 18:00
```
**Common bug**: listing deadline based on a pick NOT in that coupon. ALWAYS trace pick IDs to coupon contents.

### C. PICK-COUPON CROSS-CHECK
1. List every pick + which coupons contain it → verify per-pick exposure table matches.
2. NO orphan picks (every pick in ≥1 coupon).
3. Concentration: no pick in >60% of coupons.
4. Sport count per coupon: max 2 same-sport legs.

### D. HOME/AWAY DIRECTION CHECK
US sports: "@" = Away @ Home. BetExplorer: "Home vs Away". Cross-check team ordering in coupons.

### E. EV CONSISTENCY CHECK
For every pick: stated EV must match `EV = (true_prob × odds) - 1`. If label says "+20%" but math gives +12.5% → fix.

### F. PRICE GAP FLAGGING
Any picks with price_gap_pct beyond threshold (-3% LR, -5% HR)? If marginal and CONDITIONAL → FLAG, don't reject.

### G. TOTAL EXPOSURE VERIFICATION
Sum all coupon stakes → compare to listed total. Verify against 25% bankroll rule. Budget variants: correct stake sums.

### H. FIX PROTOCOL
If ANY check fails:
1. Fix the coupon file IN PLACE
2. Fix corresponding ledger entry if affected
3. Re-run the failed check to confirm fix
4. Log what was wrong + what was fixed
- [ ] **V-S8-07**: V1-V10 ALL passed (if any fail, loop back and fix)
- [ ] **V-S8-08**: All pick IDs consistent across coupon file + ledgers
- [ ] **V-S8-09**: Weakest leg identified per coupon
- [ ] **V-S8-10**: Watchlist present with promotion criteria
- [ ] **V-S8-11**: odds_checked_at timestamp on every pick
- [ ] **V-S8-12**: Superseded old version picks/coupons in ledgers

### PASS/FAIL GATE
- ALL V-S8 checks pass AND V1-V10 pass → "S8 PASSED — COUPONS READY"
- Any V1-V10 fail → fix and re-run validation
