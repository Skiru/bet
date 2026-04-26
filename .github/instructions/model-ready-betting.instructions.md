---
applyTo: "betting/**/*"
---

# Betting Analysis — Output Formats & Validation Rules

This file defines the EXACT output formats, file schemas, and validation checks for betting artifacts. For the full daily analysis workflow (STEPS 0-10), see [analysis-methodology.instructions.md](analysis-methodology.instructions.md). This file complements it — methodology = HOW to analyze, this file = HOW to write outputs.

## 1. WORKFLOW ORDER (see methodology for detailed STEPS 0-10)

Follow the workflow in analysis-methodology.instructions.md (STEPS 0-10 plus STEP 3B):
0. Run orchestrator
1. STEP 0: Settle + CLV + bankroll update
2. STEP 1: Scan ALL events across ALL sports
3. STEP 2: Filter to shortlist
4. STEP 3: Deep stats per candidate (sport-specific protocols including padel FIP rankings, speedway rider averages)
5. STEP 3B: Time-sensitive data collection — lineups, late injuries, weather, odds movement (run within 2-3h of earliest event)
6. STEP 4: Tipster deep-dive
7. STEP 5: Odds + EV + Kelly
8. STEP 6: Context verification
9. STEP 7: Bear case for each pick
10. STEP 8: Portfolio construction
11. STEP 9: Validate V1-V10 (V7b date verification, V7c cross-coupon integrity, V8 source completeness, V9 coupon optimization, V10 final sign-off)
12. STEP 10: Write artifacts (formats below)

## 2. HARD RULES (violating any = automatic reject)

- **No singles.** Every pick goes into a coupon. Minimum 2 legs per coupon.
- **Coupon count = f(quality events, deep statistics), NOT f(bankroll).** If 20 excellent picks survive analysis → make 10 coupons. If only 6 → make 3. NEVER reduce coupon count because of money constraints. Target minimum 5 if enough quality picks exist, but produce MORE if quality justifies it. Stakes are ADVISORY — user decides which to place.
- **No maximum legs per coupon.** A coupon can have 2, 3, 4, 5, or more legs.
- **MANDATORY 14-sport scan.** Every analysis MUST scan ALL 14 configured sports: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma, padel, speedway. Never skip a sport. Record "NO EVENTS TODAY" if a sport has no fixtures.
- **MANDATORY Deep Scan Protocol (§1.2).** Do NOT just look at a sport's landing page. Click into EVERY active tournament/league to see the FULL fixture list. Count matches per tournament. Cross-validate event counts between BetExplorer and Flashscore — discrepancy >20% means events were missed.
- **MANDATORY tournament full-slate analysis (§1.3a).** When a MAJOR TOURNAMENT is active (ATP/WTA Masters 1000, Grand Slam, World Championship, Champions League matchday, NBA/NHL Playoffs), analyze ALL matches in the daily slate — not just 1-2. Screen every match for value. Cherry-picking 1 from 32 is a PROTOCOL VIOLATION.
- **MANDATORY non-major tournament depth (§1.3b).** ANY tournament with ≥4 matches today must have ALL matches screened for value — not just major tournaments. ATP 250s, mid-tier leagues, Challengers, tier-2 esports.
- **MANDATORY Scan Completeness Metrics (§1.5).** Before proceeding to analysis, compile per-sport event count table from ≥2 sources. Total unique events must be ≥50. Scan completeness score ≥80%. If not met, go back and scan deeper.
- **Minimum 5-sport diversity in picks.** The final pick roster must include picks from at least 5 different sports. If fewer than 5 sports have picks, search deeper before declaring no value.
- **Multi-sport coupons mandatory.** At least 3 coupons must be multi-sport (2+ sports). At least 1 coupon must include a niche sport (not football/tennis).
- Max coupon stake: 3.00 PLN for low-risk, 2.00 PLN for higher-risk
- Daily exposure cap: per config/betting_config.json `suggested_daily_allocation_range_pln` (currently 5.00–7.50 PLN, but suggest stakes for ALL coupons even if total exceeds cap — user decides which to place)
- Each event may appear in ONLY ONE coupon. **UNIQUE EVENT PER COUPON (ABSOLUTE RULE — NEVER VIOLATE).** Never share events between coupons. Each coupon is 100% independent.
- Every pick needs: 1 Tier A stats source (Flashscore, Sofascore) + 1 Tier A market source (BetExplorer, OddsPortal)
- If sources conflict on a pick, skip it
- price_gap_pct formula: 100 * ((bookmaker_odds / market_best_odds) - 1)
- Low-risk: reject if price_gap_pct < -3%
- Higher-risk: reject if price_gap_pct < -5%
- No "medium" risk tier in coupons-ledger.csv. Only use: low-risk or higher-risk
- If Betclic odds are not live-verified, mark pick as CONDITIONAL with acceptance threshold

## 3. MARKET SELECTION RULES

### Football statistical markets (PRIMARY — use BEFORE goals markets)
- **Corners**: Three-source stack required: TotalCorner match total + SoccerStats league ranking + Betclic Statystyki verified odds
- **Cards**: SoccerStats card data + Betclic Statystyki when available
- **Fouls/Shots**: Betclic Statystyki tab (top leagues only: EPL, LaLiga, Bundesliga)
- Betclic Statystyki tab unavailable for Championship, Austrian BL, lower leagues → fall back to BTTS/U2.5/DC

### Football totals/BTTS/DC (SECONDARY — when statistical markets unavailable)
- BTTS: SoccerStats league BTTS% must be > 55%; both teams must score AND concede regularly
- Under 2.5: SoccerStats defensive profile (team GF+GA < 2.0/match), league O2.5% < 50%
- Over 2.5: LAST RESORT. Require strong form, H2H backing, and SoccerStats league goals avg > 2.8 if available
- DC/DNB: only when standings gap is clear and odds 1.10-1.40

### UNIVERSAL RULE — ALL SPORTS: ML/1X2/match winner is LAST RESORT

**NEVER default to ML/1X2/match winner in ANY sport.** Statistical markets (totals, handicaps, cards, corners, fouls, frames, legs, maps, sets, games, method of victory) are ALWAYS preferred across EVERY discipline. They have higher hit rates (~60-65%) and are less efficiently priced by bookmakers.

ML/winner picks are the ABSOLUTE LAST RESORT — only when:
1. No statistical market is available on Betclic for the event, AND
2. The statistical edge is overwhelming (EV > 5%), AND
3. The price is acceptable (within price gap threshold).

This applies equally to: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, handball, table tennis, MMA, padel, and speedway.

### Tennis market selection (STATISTICAL FIRST — ML is LAST RESORT)
**ABSOLUTE RULE: NEVER default to ML in tennis.** Tennis ML is the most volatile market — even 1.50 favorites lose 35-40% of matches. Statistical markets (game totals, set totals) have dramatically higher hit rates.

**Tennis market hierarchy** (use in this order, ML only as last resort):
1. **Game totals O/U** (e.g., O21.5, O22.5) — PRIMARY. Highest hit rate (~65% for STRONG ratio matches).
2. **Set totals O/U** (e.g., O2 sets) — good for competitive matches.
3. **Game handicap** — when one player is clearly better but not dominant.
4. **Set handicap** — for bigger mismatches.
5. **ML** — LAST RESORT ONLY. Requires ALL of: STRONG odds ratio (≤1.15) + surface dominance + H2H dominance. If any is missing → use games/sets instead.

**Proven by loss:** Shelton ML v6 coupon — match went 3 sets, ML lost, O21.5 games would have won easily. This is the typical failure mode.

### Tennis over-games (Over 20.5)
- Both match odds must be 1.50–2.50
- Calculate odds_gap_ratio = max(odds_A, odds_B) / min(odds_A, odds_B)
- Ratio grades (USE THESE EXACT BOUNDARIES — do NOT invent grades like "ACCEPTABLE" or "COMPETITIVE"):
  - ≤1.15 → STRONG (confidence 4–5, high-confidence coupon legs). Examples: 1.02, 1.08, 1.12, 1.15 are ALL STRONG.
  - 1.16–1.30 → GOOD (confidence 3–4, coupon legs). The boundary starts at 1.16, NOT 1.15.
  - 1.31–1.50 → BORDERLINE (confidence 3, coupon legs ONLY, never singles)
  - > 1.50 → REJECT
- ONLY these four grade words exist: STRONG, GOOD, BORDERLINE, REJECT. Never use other words.
- Note surface (clay = more breaks = supports over)
- Check Flashscore for cancellations

### Raw 1X2/moneyline — LAST RESORT IN ALL SPORTS
- ONLY when no statistical market available AND odds 1.30–3.50 AND statistical edge is overwhelming
- For tennis: ML is LAST RESORT (see tennis hierarchy above)
- For ALL other sports: check sport-specific hierarchy first. If totals, handicaps, props exist → use those instead
- Every ML pick must justify WHY no statistical market was used

### UPSET RISK ASSESSMENT — MANDATORY for every candidate

**Run the sport-specific Upset Risk Checklist (§6.5 in analysis-methodology.instructions.md) for EVERY candidate pick BEFORE approving it.**

- Score every candidate on the 8-14 factor checklist for their sport.
- Record in report: `UPSET: [score]/[max] — [top 3 factors]`.
- If score ≥ sport threshold → **ML is BANNED**. Only statistical markets allowed.
- **The Paradox Rule:** High upset risk = competitive match = MORE total play (games, frames, sets, corners). Prefer OVER totals when upset score is high. Low upset risk = blowout risk = OVERS fail. Prefer UNDER or handicaps when upset score is low.
- **Proven by loss:** Shelton-Prizmic scored 8.5/10 — 36 games played, O22.5 wins by +13.5 margin, ML lost. Struff-Michelsen: low upset risk, blowout (15 games), O22.5 misses by -7.5.
- Thresholds by sport: tennis ≥4, football ≥4, basketball ≥3, hockey ≥3, baseball ≥3, volleyball ≥3, esports ≥2, snooker ≥2, darts ≥2, MMA ≥3, handball ≥3, table tennis ≥2, padel ≥3, speedway ≥3.
- **V4k validation check** verifies upset scores are calculated and ML bans enforced.

## 4. COUPON RULES

| Coupon type | Min legs | Max legs | Max same-sport legs | Min sports | Max stake PLN |
|-------------|----------|----------|---------------------|------------|---------------|
| low-risk | 2 | no limit | 2 | 1 | 3.00 |
| higher-risk | 2 | no limit | 2 | 2 | 2.00 |

- Coupon count = f(quality events, deep statistics), NOT f(bankroll). Target minimum 5 if quality justifies. Produce MORE if 10+ unique picks exist. NEVER reduce coupon count because of money. If <4 picks → NO BET.
- No singles allowed. Every pick goes into exactly one coupon.
- **UNIQUE EVENT PER COUPON (ABSOLUTE — NEVER VIOLATE).** Each pick appears in ONLY ONE coupon. Zero sharing between coupons. Each coupon is 100% independent.
- Combined odds = multiply each leg's odds. Must match stated combined_odds ±10%.
- No two legs from same match.
- If >4 picks from one tournament, flag weather/schedule correlation risk.
- Suggest stakes for ALL coupons. Total suggested stakes may exceed daily budget — user decides which to place.

## 5. OUTPUT FILES — EXACT FORMATS

### 5a. Coupon file: betting/coupons/YYYY-MM-DD.md

The coupon .md file is a visual Markdown document — identical to what the user sees in chat.
See betting-artifacts.instructions.md for the full structure spec.

Key rules:
- Visual Markdown tables grouped by type: LOW-RISK, MULTI-SPORT, HIGHER RISK, NIGHT.
- Each table has columns: #, Coupon ID, Co obstawić (Polish market description + event), Kurs, Stawka, Zwrot.
- PODSUMOWANIE table at the end: Wydatek, Bankroll po, Łączny pot. zwrot, Stan konta po zwrocie, scenarios.
- KOLEJNOŚĆ STAWIANIA — placement priority list.
- NO old-style plain-text metadata (BETTING DAY:, RUN TIME LOCAL:, etc.). Metadata lives in ledger CSVs.
- Coupon IDs use these prefixes: LR (low-risk), MS (multi-sport), HR (higher-risk), N (night) + version suffix.
- FORBIDDEN labels: "MEDIUM", "ATP CLAY", "WTA", "KUPON", "SINGLES", "PEWNIAKI", or any sport/tournament name as coupon type.
- Tennis-only coupons MUST be low-risk.
- Every market description must be in plain Polish matching Betclic's interface.

### 5b. picks-ledger.csv

Headers (exact, one line):
```
betting_day,version,pick_id,event,sport,competition,market,selection,bookmaker,bookmaker_odds,market_best_odds,price_gap_pct,odds_checked_at_local,stake_pln,risk_tier,confidence_1_5,status,pnl_pln,stat_sources,market_sources,verification_sources,main_reason,main_risk,notes
```

Rules:
- **version**: the analysis version for this betting day (e.g., v1, v2, v5, v6). On first run = v1. On rerun, increment from the highest existing version for that day. ALL picks from ALL versions are kept — the user compares versions to decide which to place.
- pick_id format: PK-YYYYMMDD-## (e.g., PK-20260422-01). Pick IDs are UNIQUE PER VERSION — a rerun creates new pick IDs (next available ##) rather than reusing old ones.
- risk_tier allowed values: low, medium, high
- risk_tier assignment logic (do NOT set all picks to "low"):
  - low: STRONG tennis ratio (≤1.15), football with SoccerStats goals avg >3.0, confidence 4–5
  - medium: GOOD tennis ratio (1.16–1.30), football with avg_goals 2.8–3.0, confidence 3–4
  - high: BORDERLINE tennis ratio (1.31–1.50), cup matches, confidence 3
- confidence_1_5: integer 1–5
- CROSS-FILE CONSISTENCY: the confidence score for a pick MUST be identical in picks-ledger.csv, the report, and the analysis file. If you change it in one place, change it everywhere.
- status allowed values: pending, win, loss, void, placed, superseded
- Multiple sources separated by | (e.g., Flashscore|SoccerStats)
- Coupon legs get stake_pln = 0.00 (stake is on the coupon, not the leg)
- Since there are no singles, all picks will have stake_pln = 0.00 in picks-ledger.csv

### 5c. coupons-ledger.csv

Headers (exact, one line):
```
betting_day,version,coupon_id,variant,selections_count,pick_ids,combined_odds,stake_pln,risk_level,status,pnl_pln,odds_checked_at_local,correlation_check,main_logic,notes
```

Rules:
- **version**: matches the picks-ledger version for the same run (e.g., v6). All coupon versions are kept.
- coupon_id format: CP-YYYYMMDD-PD1v6, CP-YYYYMMDD-PD2v6 etc. The version suffix is part of the coupon_id to prevent collisions across versions.
- coupon_id prefixes: LR = low-risk; HR = higher-risk; MS = multi-sport; N = night. Legacy PD/PT/PQ/CP-YYYYMMDD also valid for pre-versioning data.
- variant allowed values: low-risk, higher-risk (NEVER use "medium", "pre-system", "single", "tennis-ako")
- risk_level allowed values: low-risk, higher-risk (NEVER use "medium", "high")
- pick_ids separated by | (e.g., PK-20260422-02|PK-20260422-06)
- correlation_check: pass or flagged
- Extra coupons beyond LR and HR use variant=higher-risk if they have mixed confidence

### 5d. source-log.csv

Headers:
```
betting_day,source_name,role,sport_scope,availability,used_in_analysis,used_in_final_picks,notes
```

- availability: available, partial, unavailable, not_applicable
- used_in_analysis / used_in_final_picks: yes or no

### 5e. Daily report: betting/reports/YYYY-MM-DD.md

Required sections IN THIS ORDER:
1. `# Betting Day YYYY-MM-DD`
2. `## Run Metadata`
3. `## Previous Day Settlement`
4. `## Learning Update` (max 3 points)
5. `## Source Availability`
6. `## Candidate Board`
7. `## Final Picks` (all picks — no singles exist, every pick is a coupon leg)
8. `## Final Coupons`
9. `## Rejected Picks`
10. `## Exposure Summary`

### 5f. learning-log.md

Append a section for each run:
```
## YYYY-MM-DD
- Settlement summary: (one sentence)
- What worked: (one sentence)
- What failed: (one sentence)
- Rule changes: (bullet list, STRICTLY max 3 — if you have more, keep only the 3 most important)
- Source notes: (one sentence)
```

## 6. VALIDATION CHECKLIST (run AFTER writing all files)

Go through every check. Write YES or NO for each. If any is NO, fix it before presenting.

### V1: File Consistency
- [ ] Every pick_id in coupon file exists in picks-ledger.csv
- [ ] Every coupon_id in coupon file exists in coupons-ledger.csv
- [ ] Sum of all stakes = TOTAL PLANNED EXPOSURE PLN
- [ ] UNUSED BANKROLL PLN = BANKROLL CAP PLN - TOTAL PLANNED EXPOSURE PLN
- [ ] No pick_id appears twice in picks-ledger
- [ ] No event appears in 2+ tickets (build event→ticket table to verify)
- [ ] Report Exposure Summary numbers match coupon file numbers

### V2: Source Check (for EACH pick)
- [ ] Has Tier A stats source with specific data point named
- [ ] Has Tier A market source with specific odds named
- [ ] Bookmaker odds stated or marked CONDITIONAL
- [ ] price_gap_pct within threshold for risk tier

### V3: Tennis Check (for EACH tennis pick)
- [ ] **Market hierarchy respected**: game totals > set totals > game HC > set HC > ML. If pick is ML, verify ALL of: STRONG ratio (≤1.15) + surface dominance + H2H dominance. Otherwise → REJECT ML, use statistical market instead.
- [ ] Both match odds between 1.50 and 2.50
- [ ] odds_gap_ratio calculated and ≤ 1.50
- [ ] Ratio grade matches these EXACT ranges (no other grade names allowed):
  - ≤1.15 → STRONG (e.g., 1.02, 1.08, 1.12, 1.15 are ALL STRONG)
  - 1.16–1.30 → GOOD (starts at 1.16, NOT 1.15)
  - 1.31–1.50 → BORDERLINE
  - >1.50 → REJECT
- [ ] Surface noted
- [ ] Match not cancelled on Flashscore
- [ ] BORDERLINE picks are in coupons only (never singles)
- [ ] COUNT the STRONG/GOOD/BORDERLINE picks — verify the total matches the number listed
- [ ] **Player identity verified**: Full name (first + last), country, ranking confirmed. No slashes or ambiguous identifiers.
- [ ] **WC/Q/LL check**: If either player is wildcard/qualifier/lucky loser → O22.5+ is HARD REJECT, O21.5 requires both within 20 ranking spots, O20.5 max with STRONG ratio only.
- [ ] **Odds movement gate**: Placement odds within 8% of analysis odds? If drift >8% → re-evaluated and justified in notes?

### V4: Football Check (for EACH football pick)
- [ ] For corner picks: TotalCorner match total confirms direction
- [ ] For corner picks: SoccerStats league corner data supports
- [ ] For corner picks: Betclic Statystyki verified odds (or marked CONDITIONAL if non-top-league)
- [ ] For BTTS: SoccerStats BTTS% > 55% for the league
- [ ] For U2.5: SoccerStats league O2.5% < 55% AND team defensive profile confirms
- [ ] For O2.5 (fallback): SoccerStats goals avg > 2.7 OR Betaminic team goals data supports
- [ ] H2H supports direction
- [ ] Team form supports direction

### V4b: Volleyball Check (for EACH volleyball pick)
- [ ] Set totals: favorite ML between 1.30-2.00 (competitive match)
- [ ] Point totals: O3.5 sets likely first (competitive odds)
- [ ] Competition context: semifinal/final = competitive
- [ ] BetExplorer odds comparison verified

### V5: Coupon Check (for EACH coupon)
- [ ] Leg count ≥ 2 (minimum 2 legs per coupon)
- [ ] Same-sport legs ≤ 2
- [ ] Higher-risk coupon has ≥ 2 sports
- [ ] No two legs from same match
- [ ] **Combined odds ARITHMETIC (MANDATORY):** Multiply each leg's odds explicitly (e.g., 1.50 × 1.65 = 2.475). Write the calculation. Compare to stated combined odds. Tolerance ±2%. NEVER skip this step or claim "verified" without showing the math.
- [ ] **Home/away direction verified** for every event ("@" = Away @ Home). Cross-check with ESPN/BetExplorer.
- [ ] Stake ≤ max for coupon type (3.00 LR, 2.00 HR)
- [ ] Coupon label is "LOW-RISK", "MULTI-SPORT", "HIGHER-RISK", or "NIGHT" (never "MEDIUM", "ATP CLAY", "SINGLES", "PEWNIAKI", etc.)
- [ ] **UNIQUE EVENT PER COUPON verified:** no event/pick appears in more than 1 coupon
- [ ] At least 5 total coupons produced (if 10+ picks exist)

### V6: Portfolio Check
- [ ] No coupon stake > 3.00 PLN (LR) or 2.00 PLN (HR)
- [ ] Total exposure < 25% of bankroll
- [ ] At least 2 sports represented
- [ ] At least 5 coupons produced
- [ ] If >4 picks from one tournament: flag it in V7
- [ ] **Unique-event verification:** No event appears in >1 coupon. Each coupon 100% independent.
- [ ] Note: total suggested exposure may exceed daily budget — this is OK

### V7: Weakness List
- [ ] List all BORDERLINE tennis picks (ratio 1.31–1.50) with coupon and stake
- [ ] List all CONDITIONAL picks with acceptance threshold (non-top-league corners, unverified odds)
- [ ] List all picks where Betclic Statystyki was unavailable (non-top-league football)
- [ ] For EACH coupon: name the weakest leg and write ONE sentence describing how it fails
- [ ] If >4 picks from one tournament: state shared risks (weather, schedule)
- [ ] Every weakness marked ACCEPTED (with reason) or FIXED

### V8: Source Completeness Audit
- [ ] Every pick has ≥2 independent sources (1 Tier A stats + 1 Tier A market minimum)
- [ ] Every pick had ≥1 argument-based tipster site checked (ZawodTyper/Typersi/Meczyki/OLBG/PicksWise/BetIdeas/GosuGamers)
- [ ] Football corners: TotalCorner + SoccerStats + Betclic Statystyki checked. Missing any → flag pick.
- [ ] Tennis: TennisAbstract checked. Missing → flag.
- [ ] MLB: BaseballSavant or pitcher stats checked. Missing → flag.
- [ ] Esports: Liquipedia or GosuGamers checked. Missing → flag.
- [ ] Snooker: CueTracker checked. Missing → flag.
- [ ] Every sport with picks had ≥2 tipster sites checked
- [ ] ALL tipster conflicts recorded and addressed in bear case
- [ ] If tipster consensus <50% → pick justified or removed
- [ ] H2H records checked for every pick (last 5-10 meetings, home/away splits)
- [ ] Injuries/suspensions verified for every team/player in picks (ESPN, Flashscore, team news)
- [ ] **Upset Risk Assessment (§6.5) completed for EVERY candidate** — score recorded, ML ban enforced, Paradox Rule applied, confidence adjusted

### V9: Coupon Composition Optimization
- [ ] Picks re-ranked by EV × confidence — best picks in coupons first
- [ ] No coupon has ≥3 legs of same market type
- [ ] Every active pick in exactly 1 coupon (no orphans, no sharing)
- [ ] Night coupons contain only events within the night time window (≥22:00 CEST)
- [ ] **Session parity rule: night/morning sessions follow the EXACT SAME coupon-building process as full sessions (full V1-V10). Only the event time window differs.**
- [ ] Weakest-leg swap test done per coupon
- [ ] Combined odds in sweet spots (2-leg 2-4, 3-leg 4-10, 4-leg 8-20)

### V10: Final Sign-Off
- [ ] All V1–V9 checks pass
- [ ] **V10a: Forced Sport Enumeration** — all 14 sports listed with events/sources/candidates/picks. Any sport with 0 events and <3 sources → go back.
- [ ] **V10b: Pick Approval Gates** — every pick passed 13-point gate (§7.5 methodology).
- [ ] **V10c: Red Flags cleared** — every pick had sport-specific red flags (§7.3) checked and addressed.
- [ ] **V10d: Portfolio damage** — if most-concentrated pick loses, ≥3 coupons survive.
- [ ] **V10e: Per-Pick Completeness Matrix** — print matrix for EVERY pick: Tipster≥1 | H2H≥5 | Injuries | Sources≥2 | Red Flags | EV>0 | Gate14. ANY ❌ on ANY pick → STOP, fix, re-check. ALL picks must be ✅ on ALL 7 columns. A coupon file without this matrix is a PROTOCOL VIOLATION.
- [ ] All pass → write "PORTFOLIO APPROVED"
- [ ] If any check fails → fix it, re-check, do not present until all pass

## 7. COMMON MISTAKES (read before writing — CHECK EVERY ONE)

1. Using "medium" as variant or risk_level in coupons-ledger. ONLY use low-risk or higher-risk.
2. Adding old-style plain-text metadata (BETTING DAY:, BANKROLL CAP PLN:) to the .md coupon file. Metadata lives in ledger CSVs only.
3. Writing coupon .md content that differs from what was shown in chat. They MUST be identical.
4. Classifying odds_gap_ratio 1.12 as "GOOD" — it is ≤1.15, so it is "STRONG". Same for 1.02, 1.08, 1.10, 1.14.
5. Putting alternative or contradictory pick suggestions at the bottom of the coupon file.
6. Setting different confidence scores for the same pick in different files. Pick ONE score and use it EVERYWHERE.
7. Forgetting to write the weakest-leg failure scenario for each coupon in V7.
8. Not flagging tournament concentration when >4 picks share one tournament.
9. Using risk_tier "low" for all picks — assign based on actual market volatility (see picks-ledger rules above for logic).
10. Leaving stale content from previous iterations in output files.
11. Labeling coupons as "MEDIUM COUPON" or "ATP CLAY COUPON" in coupon file — only LOW-RISK, MULTI-SPORT, HIGHER-RISK, and NIGHT exist. PEWNIAKI label is RETIRED.
12. Inventing ratio grade names like "ACCEPTABLE" or "COMPETITIVE" — only STRONG, GOOD, BORDERLINE, REJECT exist.
13. Adding extra sections ("USER ACTION REQUIRED", "CONDITIONAL NOTE") after SKIPPED OR OMITTED in coupon file.
14. Writing "5 picks at 4/5" when the list actually contains 6 — COUNT the list, do not guess.
15. Using "Med" or "Medium" as tier label in V5 validation table — use "Low" or "Higher" only.
16. Producing singles instead of coupons — NO SINGLES allowed. Minimum 2 legs per coupon.
17. Reducing coupon count because total suggested exposure exceeds daily budget — coupon count = f(quality), money is a SUGGESTION. Produce ALL quality-justified coupons.
18. Self-censoring coupon count because total exposure exceeds daily budget — suggest ALL coupons, user decides.
19. Giving up on a source after first 403/block instead of trying next source in the Odds Source Map.
20. Skipping the V8 source completeness audit — EVERY pick needs ≥2 sources verified, ≥1 tipster site checked, sport-specific sources confirmed.
21. Skipping V9 coupon optimization — EVERY coupon must be verified for pick ranking, orphan picks, market concentration, weakest-leg swap, timing coherence.
22. Missing Polish descriptions on coupon legs — EVERY selection MUST have a Polish parenthetical (e.g., "Powyżej 10.5 rzutów rożnych").
23. Having an active pick not in ANY coupon — under NO SINGLES rule, every pick must be in ≥1 coupon or moved to watchlist.
24. Accepting a tipster conflict without addressing it in the bear case — if Meczyki/Typersi/OLBG argue against your pick, the bear case MUST respond.
25. **Shallow sport scanning** — glancing at a sport's landing page and seeing 3 events when clicking into tournaments reveals 40+. ALWAYS enter every active tournament/league to see full fixture list.
26. **Missing tournament depth** — picking 1 match from a 16-match tournament slate (e.g., only Shelton from 16 ATP Madrid R1 matches). Screen ALL matches, shortlist best 3-8.
27. **No cross-source event validation** — checking only BetExplorer for tennis and seeing 5 matches, when Flashscore shows 28. Always compare event counts from ≥2 sources per sport.
28. **Skipping Scan Completeness Metrics (§1.5)** — proceeding to analysis without recording per-sport event counts, total unique events, or scan completeness score. This GATE prevents shallow scanning.
29. **Claiming combined odds are verified without arithmetic** — writing "Combined odds verified: products match within ±2%" in V5 validation without actually multiplying each coupon's leg odds. This led to HR1v5 being listed at 13.27 instead of 13.69, and HR2v5 at 10.01 instead of 11.22. ALWAYS show the explicit multiplication for EVERY coupon. Also check same-sport leg count per coupon by listing each pick's sport.
30. **Skipping sports during scan** — claiming "no events found" for volleyball/padel/speedway/esports/etc. without checking ≥3 sources. Landing pages are deceptive — volleyball landing page shows 3 events but clicking into 15 national leagues reveals 60+ matches. ALWAYS click into sub-tournaments. If BetExplorer shows nothing, check Flashscore. If both show nothing, check Sofascore. If all three show nothing, Google "[sport] matches today".
31. **Shallow tipster checks** — glancing at ZawodTyper headlines without reading the argument. The VALUE is in the tipster's REASONING ("Villarreal avg 6.2 corners away because of defensive setup"), not the bare pick ("Over 9.5 corners"). Navigate to match pages, read each tipster's full argument, extract stats and tactical reasoning. A tip without extracted reasoning is INCOMPLETE.
32. **Giving up after first source block** — TotalCorner has cookie wall? Skip corners entirely. BetExplorer esports page empty? Skip esports. This is FORBIDDEN. Source-registry.md has fallback chains for every sport. If primary fails, try secondary, tertiary, then Google search. The internet ALWAYS has data. Never give up.
33. **Football-only or football+tennis-only portfolio** — producing final picks from only 2-3 sports when 14 are available. Minimum 5 different sports in final picks. If you have <5 sports, go back and scan the missing ones deeper before declaring no value.
34. **Skipping H2H check** — finalizing a pick without checking head-to-head records. H2H can reveal that an underdog dominates at this venue (e.g., Union Berlin at Leipzig). Always check last 5-10 meetings with home/away context.
35. **Skipping injury/suspension check** — finalizing picks without verifying key absences. A single missing star player can invalidate an entire thesis. Check ESPN, Flashscore lineups, team social media for EVERY pick.
36. **Defaulting to tennis ML instead of statistical markets** — picking Machac ML 1.73 instead of O21.5 games 1.50 because it "looks like value." Tennis ML is the MOST VOLATILE market. Shelton v6 proved this: match went 3 sets, ML lost, O21.5 games wins easily. ALWAYS use game totals > set totals > handicaps > ML. ML is LAST RESORT requiring STRONG ratio + surface + H2H all aligned. Lower odds on games/sets are compensated by dramatically higher hit rates (~65% vs ~58%).
37. **Using ML for padel without ranking gap analysis** — padel ML only viable when FIP ranking gap >3000. For gaps <3000, use game totals or set totals. New partnerships add extra volatility — ML even riskier.
38. **Defaulting to ML/1X2 in ANY sport** — applies universally, not just tennis. For basketball: use totals/spreads before ML. Hockey: period totals/game totals/puck line before ML. Baseball: F5 totals/team totals before ML. Snooker: frame totals/HC before ML. Every sport has statistical markets that hit more often than raw winner picks. ML is ALWAYS the LAST RESORT across ALL 14 sports. If a pick is ML, the analysis MUST explicitly justify why no statistical market was viable.
39. **Skipping Upset Risk Assessment (§6.5)** — approving a pick without scoring it on the sport-specific upset checklist. The Shelton-Prizmic loss (8.5/10 on checklist, killing 2 coupons) proved this is PREVENTABLE. Every candidate must be scored. Score ≥ threshold = ML BANNED. Score recorded in report. V4k validates this. NEVER skip — this is a HARD REQUIREMENT, not a nice-to-have.
40. **Ignoring the Paradox Rule** — using OVER totals when upset risk is LOW (blowout territory) or avoiding OVER totals when upset risk is HIGH (competitive territory). High upset risk = more total play = overs WIN. Low upset risk = one-sided match = overs FAIL. Struff-Michelsen (15 games, miss by -7.5) vs Shelton-Prizmic (36 games, win by +13.5) proves this conclusively.
41. **Not recording upset score in bear case** — STEP 7 bear case template now REQUIRES the upset score and top 3 risk factors. A bear case without upset context is incomplete. If the upset score flags risk and you still proceed, you must explain why in the bear case.
42. **Treating night/morning sessions as reduced-scope** — producing only 1-2 "compact" coupons for night sessions, skipping deep analysis, scanning only 3 sports instead of all 14. Night/morning sessions are IDENTICAL to full sessions in EVERY aspect except the event time window. Same 14-sport scan, same STEPS 0-10, same V1-V10 validation. "Fewer events in window" ≠ "fewer analysis depth." This was the v10 night error — agent produced 2 shallow coupons with zero tipster checks, zero H2H, zero injury verification.
43. **Home/away direction reversed in US sports** — listing "ATL @ PHI" when game is at Atlanta (Truist Park), so correct is "PHI @ ATL". The "@" symbol means "visiting at": Away @ Home. BetExplorer uses "Home vs Away" — OPPOSITE convention. ALWAYS verify which team is home. Wrong direction = user may bet on wrong game in Betclic app.
44. **Concentration risk without resilience coupon** — N11-01 appeared in 5/7 coupons (71%). If that one pick lost, only 2/7 survived. RULE: If ANY pick appears in >60% of coupons, ADD a resilience coupon that EXCLUDES that pick. After adding, verify ≥3 coupons survive if the most-used pick fails. This is a V6 (Portfolio Risk) check.
45. **Skipping post-construction audit** — presenting coupons without final cross-check of: (1) home/away direction, (2) pick concentration across coupons, (3) payout arithmetic (odds × stake), (4) name consistency between coupon file + picks-ledger + coupons-ledger, (5) financial summary matches actual coupon count and total spend. Three bugs in v11 were only caught by this audit.
46. **Using O22.5+ game total for wildcard/qualifier matches** — WC/Q/LL matches produce BINARY results (blowout OR competitive), not normal distributions. P(≤16 games) is 40-50% for WC matches. O22.5 is HARD REJECT for any WC/Q/LL match. Maximum line: O20.5 with STRONG ratio. Jodar vs De Minaur (v6): WC match, O22.5 @ 1.82, result 6-3 6-1 = 16 games. Lost by 7. See §3.2G in methodology.
47. **Ignoring odds movement >8% between analysis and placement** — Jodar O22.5 estimated @ 1.65, Betclic actual 1.82 = +10.3% drift. This massive move signals the market shifting AWAY from Over. Any drift >8% requires MANDATORY re-evaluation: check injuries, lineup changes, sharp money. If no explanation found → SKIP. See §5.5a in methodology.
48. **Ambiguous player identity in tennis picks** — using slashes ("Pedro Martinez Portero / Jodar") or abbreviations when two different players could match. This led to wrong player data, wrong odds ratio (1.01 instead of actual), wrong probability estimate (76% instead of ~35-45%), and a catastrophic 16-game blowout loss. ALWAYS use full first + last name, country, and ATP/WTA ranking. See §3.2F.
49. **Equal Odds Blowout Fallacy** — assuming ratio ≤1.10 = close match. Even odds mean UNCERTAINTY about the winner, not guaranteed competitiveness. A coin-flip match can produce 6-3 6-1 just as easily as 7-6 6-7 7-5. Especially dangerous for: WC/Q/LL matches, first H2H meetings, surface mismatches. Do NOT inflate P(O22.5) based solely on ratio closeness. Jodar-De Minaur ratio 1.01 → "coin flip" → 6-3 6-1 = 16 games.
50. **Skipping sport-specific Instant Red Flags (§7.3)** — not checking backup goalie status before an NHL totals pick, not checking B2B in NBA, not checking bullpen game in MLB, not checking dead rubber in football. These are 30-second checks that prevent the most common, most OBVIOUS failures. Every sport has 3-6 fast binary checks. Run them ALL for EVERY pick. See §7.3 in methodology.
51. **Skipping Contrarian Thinking (§7.4)** — not questioning whether the model applies to this specific case. The Jodar loss: standard P(3 sets) model applied to a WC match where binary outcomes dominate. ALWAYS ask: "Am I applying the right model?" and "What's the #1 way this specific bet type loses?" before approving.
52. **Not running the Pick Approval Gate (§7.5)** — presenting picks that haven't passed the unified 13-point pre-flight checklist. This single checklist catches ALL past mistakes in one pass: identity, WC status, H2H, injuries, sources, tipsters, EV, drift, red flags, contrarian, bear case, anchoring. Skip it = repeat past failures.
53. **Presenting coupons without Per-Pick Completeness Matrix (V10e)** — v19-night had 10 picks but only 2/10 had tipster arguments, 1/10 had H2H, 2/10 had injury checks. The agent claimed analysis was "deep" but the matrix would have instantly revealed 8/10 picks were INCOMPLETE. RULE: Before presenting ANY coupon, print the V10e matrix (Tipster/H2H/Injuries/Sources/RedFlags/EV/Gate14) for EVERY pick. ANY ❌ = STOP and fix. This is the FINAL safety net — never skip it.
