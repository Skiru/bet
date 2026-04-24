---
applyTo: "betting/**/*"
---

# Betting Analysis — Output Formats & Validation Rules

This file defines the EXACT output formats, file schemas, and validation checks for betting artifacts. For the full daily analysis workflow (STEPS 0-10), see [analysis-methodology.instructions.md](analysis-methodology.instructions.md). This file complements it — methodology = HOW to analyze, this file = HOW to write outputs.

## 1. WORKFLOW ORDER (see methodology for detailed STEPS 0-10)

Follow the 11-step workflow in analysis-methodology.instructions.md:
0. Run orchestrator
1. STEP 0: Settle + CLV + bankroll update
2. STEP 1: Scan ALL events across ALL sports
3. STEP 2: Filter to shortlist
4. STEP 3: Deep stats per candidate
5. STEP 4: Tipster deep-dive
6. STEP 5: Odds + EV + Kelly
7. STEP 6: Context verification
8. STEP 7: Bear case for each pick
9. STEP 8: Portfolio construction
10. STEP 9: Validate V1-V10 (V8=source completeness, V9=coupon optimization, V10=final sign-off)
11. STEP 10: Write artifacts (formats below)

## 2. HARD RULES (violating any = automatic reject)

- **No singles.** Every pick goes into a coupon. Minimum 2 legs per coupon.
- **Minimum 5 coupons per day.** Produce at least 5 diverse coupons. Search wider before accepting fewer.
- **No maximum legs per coupon.** A coupon can have 2, 3, 4, 5, or more legs.
- **MANDATORY 12-sport scan.** Every analysis MUST scan ALL 12 configured sports: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma. Never skip a sport. Record "NO EVENTS TODAY" if a sport has no fixtures.
- **MANDATORY Deep Scan Protocol (§1.2).** Do NOT just look at a sport's landing page. Click into EVERY active tournament/league to see the FULL fixture list. Count matches per tournament. Cross-validate event counts between BetExplorer and Flashscore — discrepancy >20% means events were missed.
- **MANDATORY tournament full-slate analysis (§1.3a).** When a MAJOR TOURNAMENT is active (ATP/WTA Masters 1000, Grand Slam, World Championship, Champions League matchday, NBA/NHL Playoffs), analyze ALL matches in the daily slate — not just 1-2. Screen every match for value. Cherry-picking 1 from 32 is a PROTOCOL VIOLATION.
- **MANDATORY non-major tournament depth (§1.3b).** ANY tournament with ≥4 matches today must have ALL matches screened for value — not just major tournaments. ATP 250s, mid-tier leagues, Challengers, tier-2 esports.
- **MANDATORY Scan Completeness Metrics (§1.5).** Before proceeding to analysis, compile per-sport event count table from ≥2 sources. Total unique events must be ≥50. Scan completeness score ≥80%. If not met, go back and scan deeper.
- **Minimum 5-sport diversity in picks.** The final pick roster must include picks from at least 5 different sports. If fewer than 5 sports have picks, search deeper before declaring no value.
- **Multi-sport coupons mandatory.** At least 3 coupons must be multi-sport (2+ sports). At least 1 coupon must include a niche sport (not football/tennis).
- Max coupon stake: 3.00 PLN for low-risk, 2.00 PLN for higher-risk
- Daily exposure cap: per config/betting_config.json `suggested_daily_allocation_range_pln` (currently 5.00–7.50 PLN, but suggest stakes for ALL coupons even if total exceeds cap — user decides which to place)
- Each event may appear in multiple coupons (pewniaki system generates combinations). But never duplicate the same coupon composition.
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

### Raw 1X2/moneyline
- Only when odds are 1.30–3.50 AND statistical edge is clear

## 4. COUPON RULES

| Coupon type | Min legs | Max legs | Max same-sport legs | Min sports | Max stake PLN |
|-------------|----------|----------|---------------------|------------|---------------|
| low-risk | 2 | no limit | 2 | 1 | 3.00 |
| higher-risk | 2 | no limit | 2 | 2 | 2.00 |

- Minimum 5 coupons per day. No maximum coupon count.
- No singles allowed. Every pick goes into at least one coupon.
- Picks CAN appear in multiple coupons (e.g., pewniaki combinations). But no two coupons should have identical composition.
- Combined odds = multiply each leg's odds. Must match stated combined_odds ±10%.
- No two legs from same match.
- If >4 picks from one tournament, flag weather/schedule correlation risk.
- Suggest stakes for ALL coupons. Total suggested stakes may exceed daily budget — user decides which to place.

## 5. OUTPUT FILES — EXACT FORMATS

### 5a. Coupon file: betting/coupons/YYYY-MM-DD.txt

Use these EXACT header field names:
```
BETTING DAY: 2026-04-22
RUN TIME LOCAL: 2026-04-22 16:30
BOOKMAKER: Betclic
BANKROLL CAP PLN: 8.00
TOTAL PLANNED EXPOSURE PLN: 7.00
UNUSED BANKROLL PLN: 1.00
```

Coupon format — use EXACTLY these label patterns:
```
PEWNIAKI DOUBLE 1 (CP-20260422-PD1):
- coupon_id: CP-20260422-PD1
- legs:
  1. [PK-20260422-01] Event | market | Selection | odds | accept if >= threshold
  2. [PK-20260422-02] Event | market | Selection | odds | accept if >= threshold
- combined_odds: ~2.18
- stake_pln: 1.00
- rationale: one sentence

PEWNIAKI TRIPLE 1 (CP-20260422-PT1):
...same format...

HIGHER-RISK COUPON 1 (CP-20260422-HR1):
...same format...
```

Coupon label rules:
- Use "PEWNIAKI DOUBLE/TRIPLE/QUAD" for pewniaki combinatorial coupons
- Use "LOW-RISK COUPON" when: all legs confidence 4+, or meets low-risk criteria
- Use "HIGHER-RISK COUPON" when: multi-sport (≥2), mixed confidence, or higher volatility
- Append a number for additional coupons: "LOW-RISK COUPON 2", "HIGHER-RISK COUPON 3"
- Tennis-only coupons MUST be low-risk (they cannot meet higher-risk min 2 sports requirement)
- FORBIDDEN labels: "MEDIUM", "ATP CLAY", "WTA", "KUPON", "SINGLES", or any sport/tournament name as coupon type
- The word before "COUPON" must be either LOW-RISK or HIGHER-RISK — no exceptions (except PEWNIAKI prefix)

End with:
```
SKIPPED OR OMITTED:
- reason for each skipped event or coupon variant
```

The coupon file ends after SKIPPED OR OMITTED. Do NOT add any additional sections like "USER ACTION REQUIRED", "ALTERNATIVE PICKS", or "CONDITIONAL NOTE" after it.

### 5b. picks-ledger.csv

Headers (exact, one line):
```
betting_day,pick_id,event,sport,competition,market,selection,bookmaker,bookmaker_odds,market_best_odds,price_gap_pct,odds_checked_at_local,stake_pln,risk_tier,confidence_1_5,status,pnl_pln,stat_sources,market_sources,verification_sources,main_reason,main_risk,notes
```

Rules:
- pick_id format: PK-YYYYMMDD-## (e.g., PK-20260422-01)
- risk_tier allowed values: low, medium, high
- risk_tier assignment logic (do NOT set all picks to "low"):
  - low: STRONG tennis ratio (≤1.15), football with SoccerStats goals avg >3.0, confidence 4–5
  - medium: GOOD tennis ratio (1.16–1.30), football with avg_goals 2.8–3.0, confidence 3–4
  - high: BORDERLINE tennis ratio (1.31–1.50), cup matches, confidence 3
- confidence_1_5: integer 1–5
- CROSS-FILE CONSISTENCY: the confidence score for a pick MUST be identical in picks-ledger.csv, the report, and the analysis file. If you change it in one place, change it everywhere.
- status allowed values: pending, win, loss, void, placed
- Multiple sources separated by | (e.g., Flashscore|SoccerStats)
- Coupon legs get stake_pln = 0.00 (stake is on the coupon, not the leg)
- Since there are no singles, all picks will have stake_pln = 0.00 in picks-ledger.csv

### 5c. coupons-ledger.csv

Headers (exact, one line):
```
betting_day,coupon_id,variant,selections_count,pick_ids,combined_odds,stake_pln,risk_level,status,pnl_pln,odds_checked_at_local,correlation_check,main_logic,notes
```

Rules:
- coupon_id format: CP-YYYYMMDD-PD1, CP-YYYYMMDD-PD2 etc. for pewniaki doubles; CP-YYYYMMDD-PT1 for pewniaki triples; CP-YYYYMMDD-PQ1 for pewniaki quads; CP-YYYYMMDD-LR1 for low-risk; CP-YYYYMMDD-HR1 for higher-risk. Legacy CP-YYYYMMDD-LR and CP-YYYYMMDD-HR also valid.
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
- [ ] Stake ≤ max for coupon type (3.00 LR, 2.00 HR)
- [ ] Coupon label is "PEWNIAKI", "LOW-RISK COUPON", or "HIGHER-RISK COUPON" (never "MEDIUM", "ATP CLAY", "SINGLES", etc.)
- [ ] At least 5 total coupons produced

### V6: Portfolio Check
- [ ] No coupon stake > 3.00 PLN (LR) or 2.00 PLN (HR)
- [ ] Total exposure < 25% of bankroll
- [ ] At least 2 sports represented
- [ ] At least 5 coupons produced
- [ ] If >4 picks from one tournament: flag it in V7
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

### V9: Coupon Composition Optimization
- [ ] Picks re-ranked by EV × confidence — highest in most coupons
- [ ] No coupon has ≥3 legs of same market type
- [ ] Every active pick in ≥1 coupon (no orphans)
- [ ] Night coupons = only night games
- [ ] Weakest-leg swap test done per coupon
- [ ] Combined odds in sweet spots (pewniaki 2-8, MS 3-10, HR 8-20)

### V10: Final Sign-Off
- [ ] All V1–V9 checks pass → write "PORTFOLIO APPROVED"
- [ ] If any check fails → fix it, re-check, do not present until all pass

## 7. COMMON MISTAKES (read before writing — CHECK EVERY ONE)

1. Using "medium" as variant or risk_level in coupons-ledger. ONLY use low-risk or higher-risk.
2. Using "BANKROLL:" instead of "BANKROLL CAP PLN:" in coupon file header.
3. Using "UNUSED FROM CAP PLN:" instead of "UNUSED BANKROLL PLN:" in coupon file header.
4. Classifying odds_gap_ratio 1.12 as "GOOD" — it is ≤1.15, so it is "STRONG". Same for 1.02, 1.08, 1.10, 1.14.
5. Putting alternative or contradictory pick suggestions at the bottom of the coupon file.
6. Setting different confidence scores for the same pick in different files. Pick ONE score and use it EVERYWHERE.
7. Forgetting to write the weakest-leg failure scenario for each coupon in V7.
8. Not flagging tournament concentration when >4 picks share one tournament.
9. Using risk_tier "low" for all picks — assign based on actual market volatility (see picks-ledger rules above for logic).
10. Leaving stale content from previous iterations in output files.
11. Labeling coupons as "MEDIUM COUPON" or "ATP CLAY COUPON" in coupon file — only PEWNIAKI, LOW-RISK COUPON and HIGHER-RISK COUPON exist.
12. Inventing ratio grade names like "ACCEPTABLE" or "COMPETITIVE" — only STRONG, GOOD, BORDERLINE, REJECT exist.
13. Adding extra sections ("USER ACTION REQUIRED", "CONDITIONAL NOTE") after SKIPPED OR OMITTED in coupon file.
14. Writing "5 picks at 4/5" when the list actually contains 6 — COUNT the list, do not guess.
15. Using "Med" or "Medium" as tier label in V5 validation table — use "Low" or "Higher" only.
16. Producing singles instead of coupons — NO SINGLES allowed. Minimum 2 legs per coupon.
17. Producing fewer than 5 coupons without exhausting all sport/market opportunities first.
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
