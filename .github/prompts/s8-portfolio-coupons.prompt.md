---
name: s8-portfolio-coupons
description: "STEP 8: Portfolio construction, coupon building, V1-V10, artifact generation"
agent: bet-analyst
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
3. Identify TOP 3-5 as "pewniaki" (highest confidence + EV)
4. Minimum requirement: ≥5 approved picks from ≥5 sports. If not → try promoting watchlist picks or declare NO BET day.

## 8B — PEWNIAKI COUPON SYSTEM
From top 3-5 picks, build ALL non-repeating combinations:
- All doubles (C(n,2))
- All triples (C(n,3))
- All quads (C(n,4)) if ≥4 pewniaki
- One "full pewniaki" with all top picks

Label: CP-{date}-PD01, PD02, ... (doubles), PT01, ... (triples), PQ01, ... (quads)

## 8C — THEMED COUPONS
From remaining approved picks + pewniaki:
- **Multi-sport (MS)**: ≥3 sports, 3-5 legs, moderate risk
- **Low-risk (LR)**: 2-3 legs, all confidence ≥4, combined odds 2.0-4.0
- **Higher-risk (HR)**: 3-5 legs, combined odds 8.0-20.0, reduced stake
- **Night (N)**: only events after 20:00 local (if applicable)

## 8D — CORRELATION + CONCENTRATION CHECK
For every coupon:
- [ ] No two legs from same match (FORBIDDEN)
- [ ] Max 2 legs from same sport per coupon
- [ ] No correlated narratives (e.g., Team A ML + Team A O2.5 in DIFFERENT coupons)
- [ ] No pick in >60% of coupons (concentration) — if violated, add resilience coupon WITHOUT it
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

---

## V1-V10 VALIDATION (MANDATORY — EVERY CHECK)

### V1 — Artifact Consistency
- [ ] All pick_ids match across coupon file, picks-ledger, report
- [ ] All coupon_ids match across coupon file, coupons-ledger
- [ ] Stake sums ≤ daily budget per coupon tier
- [ ] Exposure total calculated

### V2 — Per-Pick Source Validation
- [ ] Every pick has Tier A stats source named
- [ ] Every pick has Tier A market/price source
- [ ] Every pick has EV > 0
- [ ] Every pick has confidence score 1-5

### V3 — Tennis Checks
- [ ] Odds ratio graded (STRONG/GOOD/BORDERLINE/REJECT)
- [ ] Surface form checked
- [ ] WC/Q/LL → O22.5+ HARD REJECTED
- [ ] Player identity verified (full name, ranking, no slashes)
- [ ] Odds drift < 8%

### V4 — Football Checks
- [ ] Market hierarchy respected (corners > cards > fouls > team totals > BTTS > DC > ML)
- [ ] Corner picks have 3-source stack (or gap documented)
- [ ] BTTS picks have league BTTS% from SoccerStats
- [ ] xG regression check for goals markets

### V4b-V4k — Other Sports (per methodology)
- [ ] V4b Volleyball: set totals checked, ML range 1.30-2.00
- [ ] V4c Esports: map pool checked, BO format noted, roster confirmed
- [ ] V4d Snooker: frame stats from CueTracker, format (BO) noted
- [ ] V4e Darts: 3-dart avg, format (sets vs legs) noted
- [ ] V4f Handball: home advantage factored (60-65%), half totals checked
- [ ] V4g Table Tennis: ranking gap assessed, high variance noted
- [ ] V4h MMA: finish rates checked, method of victory considered
- [ ] V4i Padel: FIP ranking gap checked, partnership duration noted, indoor/outdoor surface
- [ ] V4j Speedway: rider TRACK-SPECIFIC averages used (not season avg), lineup confirmed
- [ ] V4k: **Upset risk scored for EVERY favorite ≤1.50** — ML banned if score ≥ threshold

### V5 — Coupon Structure
- [ ] Min 2 legs per coupon
- [ ] Same-sport ≤ 2 per coupon
- [ ] No same-match legs
- [ ] **Combined odds ARITHMETIC shown for EVERY coupon**:
  ```
  CP-XX: leg1 × leg2 × leg3 = X.XX × X.XX × X.XX = X.XX
  ```
- [ ] **Home/away direction verified** for every event ("@" = Away @ Home, BetExplorer = Home vs Away)
- [ ] Stake within limits (3.00 LR, 2.00 HR)
- [ ] Min 5 coupons total
- [ ] Coupon-level sport listed per leg

### V6 — Portfolio Risk
- [ ] Total exposure < 25% of bankroll
- [ ] Sport diversification (≥5 sports in all coupons combined)
- [ ] No tournament over-concentration

### V7 — Weakness Flagging
- [ ] Borderline picks flagged
- [ ] CONDITIONAL picks noted (all Betclic picks)
- [ ] Weakest leg per coupon identified
- [ ] Same-tournament risks flagged

### V7b — Date & Fixture Verification
- [ ] EVERY event exists on correct date (verify on BetExplorer)
- [ ] Correct teams/players (no identity confusion)
- [ ] Correct competition name

### V7c — Cross-Coupon Integrity
- [ ] No accidental duplicate legs (outside pewniaki system)
- [ ] No identical coupons
- [ ] No correlated narratives across coupons

### V8 — Source Completeness
- [ ] Tier A stats + market per pick (both present)
- [ ] ≥2 independent sources per pick
- [ ] Argument-based tipster checked per pick
- [ ] Failed sources documented in source-log

### V9 — Coupon Composition Optimization
- [ ] Picks ranked by EV × confidence — highest in most coupons
- [ ] No coupon has ≥3 same-market-type legs
- [ ] Every active pick in ≥1 coupon (no orphans)
- [ ] Weakest-leg swap test: could any leg improve?
- [ ] Combined odds in sweet spots: pewniaki 2-8, MS 3-10, HR 8-20

### V10 — Final Sign-Off
- [ ] V10a: ALL 14 sports enumerated with scan evidence
- [ ] V10b: All pick approval gates verified
- [ ] V10c: All red flags cleared
- [ ] V10d: Portfolio damage assessment (if top pick loses, what survives?)
- [ ] ALL V1-V9 pass → **APPROVED**

---

## ARTIFACT GENERATION

### Coupon File: `betting/coupons/{date}-v{version}.md`

**MANDATORY SECTIONS (in this order):**

1. **Header**: date, bankroll, budget, version, odds_checked_at
2. **Conditional notice**: all picks CONDITIONAL — verify on Betclic
3. **AKTYWNE TYPKI (Active Picks) table**: all picks with ID, event, market, odds, conf, sport, kickoff
4. **KUPONY (Coupons)**: grouped by type (PEWNIAKI 2-ki, 3-ki, MULTI-SPORT, HIGHER RISK, NIGHT)
   - Per coupon: legs table, combined odds arithmetic shown, stake, return, weakest leg, sports list
5. **ARYTMETYKA KUPONÓW**: explicit multiplication for every coupon
6. **PODSUMOWANIE**: financial summary table + coupon table + budget variants (A/B/C)
7. **Per-pick ekspozycja**: which coupons each pick appears in, total stake, % of exposure
8. **Koncentracja per kupon**: max 60% check table
9. **KOLEJNOŚĆ STAWIANIA (Placement Order)**: when to place each coupon, time-sensitive first
10. **POMINIĘTE / USUNIĘTE (Removed Picks)**: every rejected pick with reason
11. **WATCHLIST**: picks not approved but close, with promotion criteria
12. **PORTFOLIO DAMAGE ASSESSMENT**: if top 2 picks fail → what coupons survive?
13. **CONDITIONAL NOTES**: time-sensitive checks user must do before placing
14. **V1-V10 STATUS**: full validation status table
15. **USUNIĘTE WERSJE**: which old versions this supersedes

**Polish descriptions (MANDATORY on every leg):**
- Over = Powyżej, Under = Poniżej, Goals = bramek, Corners = rzutów rożnych
- Cards = kartek, Shots = strzałów, Games = gemów, Frames = frejmów
- Points = punktów, Rounds = rund, Sets = setów, Maps = map
- BTTS = Obie drużyny strzelą, ML = Zwycięstwo, HC = Handicap

Format per coupon:
```markdown
#### PD01 — Pewniaki 2-ka #1 | CP-{date}-LR1

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
- [ ] **V-S8-07**: V1-V10 ALL passed (if any fail, loop back and fix)
- [ ] **V-S8-08**: All pick IDs consistent across coupon file + ledgers
- [ ] **V-S8-09**: Weakest leg identified per coupon
- [ ] **V-S8-10**: Watchlist present with promotion criteria
- [ ] **V-S8-11**: odds_checked_at timestamp on every pick
- [ ] **V-S8-12**: Superseded old version picks/coupons in ledgers

### PASS/FAIL GATE
- ALL V-S8 checks pass AND V1-V10 pass → "S8 PASSED — COUPONS READY"
- Any V1-V10 fail → fix and re-run validation
