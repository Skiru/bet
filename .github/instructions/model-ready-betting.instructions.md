---
applyTo: "betting/**/*"
---

# Betting Analysis — Complete Model Instructions

This is the ONLY file you need. Follow it top to bottom. Do not skip sections.

## 1. WORKFLOW ORDER (do steps 1–7 in this exact order)

1. Settle previous betting day (check results, update ledgers)
2. Update learning-log.md (max 3 bullet points)
3. Update source-log.csv (one row per source used today)
4. List events in betting-day window (06:00 today → 05:59 tomorrow, Europe/Warsaw)
5. Evaluate each candidate, reject or approve
6. Build portfolio (singles first, then coupons)
7. Write all output files, then run validation checklist

## 2. HARD RULES (violating any = automatic reject)

- Max single stake: 2.00 PLN
- Daily exposure cap: 4.00–8.00 PLN (leave unused if board is weak)
- Each event appears in EXACTLY ONE ticket (single or coupon leg). Never reuse an event.
- Every pick needs: 1 Tier A stats source (Flashscore, Sofascore) + 1 Tier A market source (BetExplorer, OddsPortal)
- If sources conflict on a pick, skip it
- price_gap_pct formula: 100 * ((bookmaker_odds / market_best_odds) - 1)
- Low-risk: reject if price_gap_pct < -3%
- Higher-risk: reject if price_gap_pct < -5%
- No "medium" risk tier in coupons-ledger.csv. Only use: low-risk or higher-risk
- If Betclic odds are not live-verified, mark pick as CONDITIONAL with acceptance threshold

## 3. MARKET SELECTION RULES

### Football totals (Over 2.5)
- Forebet avg_goals must be > 2.8
- H2H last 3–5 meetings must support Over
- Both teams must be in scoring form

### Tennis over-games (Over 20.5)
- Both match odds must be 1.50–2.50
- Calculate odds_gap_ratio = max(odds_A, odds_B) / min(odds_A, odds_B)
- Ratio grades (USE THESE EXACT BOUNDARIES — do NOT invent grades like "ACCEPTABLE" or "COMPETITIVE"):
  - ≤ 1.15 → STRONG (confidence 4–5, singles OK). Examples: 1.02, 1.08, 1.12, 1.15 are ALL STRONG.
  - 1.16–1.30 → GOOD (confidence 3–4, singles or coupon). The boundary starts at 1.16, NOT 1.15.
  - 1.31–1.50 → BORDERLINE (confidence 3, coupon legs ONLY, never singles)
  - > 1.50 → REJECT
- ONLY these four grade words exist: STRONG, GOOD, BORDERLINE, REJECT. Never use other words.
- Note surface (clay = more breaks = supports over)
- Check Flashscore for cancellations

### Raw 1X2/moneyline
- Only when odds are 1.30–3.50 AND statistical edge is clear

## 4. COUPON RULES

| Coupon type | Max legs | Max same-sport legs | Min sports | Max stake PLN |
|-------------|----------|---------------------|------------|---------------|
| low-risk | 3 | 2 | 1 | 2.00 |
| higher-risk | 4 | 2 | 2 | 1.00 |

- Combined odds = multiply each leg's odds. Must match stated combined_odds ±10%.
- No two legs from same match.
- If >4 picks from one tournament, flag weather/schedule correlation risk.

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

Singles format:
```
SINGLES:
- [PK-20260422-01] Event Name | market | Selection | odds | stake PLN | accept if >= threshold
```

Coupon format — use EXACTLY these label patterns:
```
LOW-RISK COUPON (CP-20260422-LR):
- coupon_id: CP-20260422-LR
- legs:
  1. [PK-20260422-02] Event | market | Selection | odds | accept if >= threshold
  2. [PK-20260422-06] Event | market | Selection | odds | accept if >= threshold
- combined_odds: ~2.18
- stake_pln: 1.00
- rationale: one sentence

HIGHER-RISK COUPON 2 (CP-20260422-HR):
...same format...

HIGHER-RISK COUPON 3 (CP-20260422-C3):
...same format...
```

Coupon label rules:
- Use "LOW-RISK COUPON" when: single sport, all legs confidence 4+, or meets low-risk criteria
- Use "HIGHER-RISK COUPON" when: multi-sport (≥2), mixed confidence, or higher volatility
- Append a number for additional coupons: "LOW-RISK COUPON 3", "HIGHER-RISK COUPON 2"
- Tennis-only coupons MUST be low-risk (they cannot meet higher-risk min 2 sports requirement)
- FORBIDDEN labels: "MEDIUM", "ATP CLAY", "WTA", "KUPON", or any sport/tournament name as coupon type
- The word before "COUPON" must be either LOW-RISK or HIGHER-RISK — no exceptions

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
  - low: STRONG tennis ratio (≤1.15), football with Forebet avg_goals >3.0, confidence 4–5
  - medium: GOOD tennis ratio (1.16–1.30), football with avg_goals 2.8–3.0, confidence 3–4
  - high: BORDERLINE tennis ratio (1.31–1.50), cup matches, confidence 3
- confidence_1_5: integer 1–5
- CROSS-FILE CONSISTENCY: the confidence score for a pick MUST be identical in picks-ledger.csv, the report, and the analysis file. If you change it in one place, change it everywhere.
- status allowed values: pending, win, loss, void, placed
- Multiple sources separated by | (e.g., Flashscore|Forebet)
- Coupon legs get stake_pln = 0.00 (stake is on the coupon, not the leg)
- Singles get their actual stake in stake_pln

### 5c. coupons-ledger.csv

Headers (exact, one line):
```
betting_day,coupon_id,variant,selections_count,pick_ids,combined_odds,stake_pln,risk_level,status,pnl_pln,odds_checked_at_local,correlation_check,main_logic,notes
```

Rules:
- coupon_id format: CP-YYYYMMDD-LR or CP-YYYYMMDD-HR or CP-YYYYMMDD-C3 etc.
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
7. `## Final Singles`
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

### V4: Football Check (for EACH football totals pick)
- [ ] Forebet avg_goals > 2.8 (for Over 2.5)
- [ ] H2H supports direction
- [ ] Team form supports direction

### V5: Coupon Check (for EACH coupon)
- [ ] Leg count ≤ limit (see table in section 4)
- [ ] Same-sport legs ≤ 2
- [ ] Higher-risk coupon has ≥ 2 sports
- [ ] No two legs from same match
- [ ] Combined odds = product of leg odds ±10%
- [ ] Stake ≤ max for coupon type
- [ ] Coupon label in file is either "LOW-RISK COUPON" or "HIGHER-RISK COUPON" (never "MEDIUM", "ATP CLAY", etc.)

### V6: Portfolio Check
- [ ] Total exposure ≤ 8.00 PLN (or config cap)
- [ ] No single stake > 2.00 PLN
- [ ] Total exposure < 25% of bankroll
- [ ] At least 2 sports represented
- [ ] If >4 picks from one tournament: flag it in V7

### V7: Weakness List
- [ ] List all BORDERLINE tennis picks (ratio 1.31–1.50) with coupon and stake
- [ ] List all CONDITIONAL picks with acceptance threshold
- [ ] For EACH coupon: name the weakest leg and write ONE sentence describing how it fails (e.g., "Kasatkina wins 6-2 6-3 = 17 games, under 20.5")
- [ ] If >4 picks from one tournament: state shared risks (weather, schedule)
- [ ] Every weakness marked ACCEPTED (with reason) or FIXED

### V8: Final Answer
- [ ] All V1–V7 checks pass → write "PORTFOLIO APPROVED"
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
11. Labeling coupons as "MEDIUM COUPON" or "ATP CLAY COUPON" in coupon file — only LOW-RISK COUPON and HIGHER-RISK COUPON exist.
12. Inventing ratio grade names like "ACCEPTABLE" or "COMPETITIVE" — only STRONG, GOOD, BORDERLINE, REJECT exist.
13. Adding extra sections ("USER ACTION REQUIRED", "CONDITIONAL NOTE") after SKIPPED OR OMITTED in coupon file.
14. Writing "5 picks at 4/5" when the list actually contains 6 — COUNT the list, do not guess.
15. Using "Med" or "Medium" as tier label in V5 validation table — use "Low" or "Higher" only.
