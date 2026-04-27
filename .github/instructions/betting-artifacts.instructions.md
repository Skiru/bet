---
applyTo: "betting/**/*"
---

Write betting artifacts in a strict, reusable format.

General rules:
- Use the Europe/Warsaw betting-day convention defined in the repo instructions.
- Use dot decimals for odds and PLN amounts.
- Use YYYY-MM-DD for dates and YYYY-MM-DD HH:MM for local timestamps.
- Use | as the separator inside CSV cells that contain multiple source names.
- On reruns for the same betting day, PRESERVE old versions and ADD new ones. Increment the version suffix (v5 → v6). Mark old pending picks/coupons as `superseded`. Add new picks and coupons with the new version. Create a new versioned coupon file. The previous version files are kept for history. The user compares all versions to decide which to place.

Daily report path:
- betting/reports/YYYY-MM-DD.md

Daily report required sections and order:
1. # Betting Day YYYY-MM-DD
2. ## Run Metadata
3. ## Previous Day Settlement
4. ## Learning Update
5. ## Source Availability
6. ## Candidate Board
7. ## Final Coupons
8. ## Rejected Picks
9. ## Exposure Summary

Daily report required content:
- Run Metadata must include betting_day, run_timestamp_local, bookmaker, sports_focus, and bankroll_cap_pln.
- Previous Day Settlement must include settled picks summary, settled coupons summary, previous day pnl, and rolling 7-day pnl when available.
- Learning Update must contain at most 3 process-level changes.
- Source Availability must log each important source with role, availability, and a short note.
- Candidate Board must show the shortlist with verdict values approved, rejected, or watch.
- Final Coupons has TWO parts:
  1. **Core Portfolio:** Coupons where each event appears in exactly ONE coupon. Subsections by risk tier: Low-Risk, Multi-Sport, Higher-Risk, and/or Night. Target: ≥2 LR, ≥1 MS, ≥1 HR (scale up with picks). Each coupon must include coupon_id, leg list (minimum 2 legs), combined_odds, stake_pln, correlation check, and main logic. **UNIQUE EVENT PER COUPON.** No singles allowed.
  2. **Combination Menu (COMBO):** Additional coupons that remix approved picks into new groupings. 4-8 extra combos. Picks MAY be reused from core. Each combo prefixed "COMBO-" and has a distinct thesis. This gives the user more choice on top of the core list.
- Rejected Picks must state the event or market, the rejection reason, and which gate/check failed. Show at least 10 near-misses. Group by rejection category: EV≤0, source gap, bear>bull, market unavailable, stale odds.
- Exposure Summary must include total_core_exposure_pln (core portfolio sum), total_menu_exposure_pln (core + combos sum), suggested_budget_pln (daily cap), and a note: "Core portfolio = primary bets. Combo menu = extra options. Pick your favorites from both."
- If no bet is made, still write every section and state NO BET TODAY where appropriate.

Chat + file output format (PRIMARY deliverable):
The main deliverable is a compact Markdown summary. It MUST be:
1. Shown directly in chat, AND
2. Saved to betting/coupons/YYYY-MM-DD.md with IDENTICAL formatting.
Required sections:
1. Per-coupon table with columns: #, Coupon ID, What to bet (Polish, specific market description), Combined odds, Stake, Potential return.
   - Group by type: LOW-RISK, MULTI-SPORT, HIGHER RISK, NIGHT.
   - Market descriptions must be in plain Polish (e.g. "poniżej 2.5 bramek", "powyżej 22.5 gemów").
   - Include opponent/event name so user can find it in Betclic.
2. **PER-COUPON REASONING (mandatory under each coupon table):**
   - 1-2 sentences explaining WHY these specific legs were combined.
   - State P(coupon) estimate: "Szacowane prawdopodobieństwo: ~XX%".
   - State the biggest risk: "Największe ryzyko: [specific scenario]".
3. PODSUMOWANIE table:
   - Wydatek (total spend)
   - Bankroll po (bankroll after placing)
   - Łączny pot. zwrot (total potential return)
   - Stan konta po zwrocie (bankroll after + total potential return)
   - Najlepszy scenariusz (all win)
   - Realistyczny (expected hit rate)
4. **LISTA OBSERWACYJNA (WATCHLIST) — 2-3 backup picks:**
   - For each: event, market, odds, and promotion criteria ("Wstaw jeśli Betclic ≥ X.XX").
   - Why it didn't make final: "Odrzucone bo: [reason]".
5. **ODRZUCONE (DECLINED) — Top 10 near-misses:**
   - For each: event, market considered, and specific rejection reason (1 sentence).
   - Grouped: "Brak wartości" (EV≤0), "Słabe źródła" (source gap), "Zbyt ryzykowne" (bear>bull), "Rynek niedostępny" (no Betclic market).
6. Placement order recommendation.
Keep coupon tables SHORT for fast clicking. Reasoning and watchlist/declined sections follow AFTER all coupon tables.

Daily coupon file path:
- betting/coupons/YYYY-MM-DD.md

The .md file MUST be identical to what is shown in chat — visual Markdown tables with Polish descriptions.
Structure of the .md file:
1. H1 header with date, bankroll, budget.
2. Conditional notice (all picks are CONDITIONAL — verify on Betclic).
3. Per-type coupon tables (LOW-RISK, MULTI-SPORT, HIGHER RISK, NIGHT) — each with columns: #, Coupon ID, Co obstawić, Kurs, Stawka, Zwrot. UNIQUE EVENT PER COUPON.
3b. **COMBINATION MENU** — additional combos (COMBO-LR1, COMBO-MS1, etc.) that remix approved picks. Same table format. Prefixed "COMBO-" for clarity.
4. **Per-coupon reasoning block** (under each table): logic, P(coupon), biggest risk.
5. PODSUMOWANIE table (Wydatek, Bankroll po, Łączny pot. zwrot, Stan konta po zwrocie, Najlepszy scenariusz, Realistyczny).
6. KOLEJNOŚĆ STAWIANIA — placement priority list.
7. **LISTA OBSERWACYJNA** — 2-3 backup picks with promotion criteria.
8. **ODRZUCONE** — Top 10 near-misses with specific rejection reasons, grouped by rejection category.
9. Pominięte coupons note (which coupons were skipped and why, one line).
10. Time-sensitive warnings if any matches may have already started.

No old-style plain-text metadata blocks (BETTING DAY:, RUN TIME LOCAL:, etc.) — that data lives in the ledger CSVs.
Coupon count = f(quality events, deep statistics), NOT f(bankroll). No singles. No maximum legs per coupon.
Core portfolio: unique event per coupon. Combo menu: reuse allowed. Together they give the user real choice.
Total suggested stakes (core + combos) WILL exceed daily budget — user picks favorites. NEVER reduce coupon count because of money constraints.

Per-pick concentration limit (MANDATORY when user selects coupons):
When the user selects a subset of coupons (core + combos), compute per-pick exposure:
- For each unique pick, sum the stakes of all SELECTED coupons containing that pick.
- No single pick may account for more than 50% of the total selected budget.
- If exceeded, suggest swapping one coupon for a different one.
- Include a per-pick exposure table in the PODSUMOWANIE section.

Human-readable Polish descriptions (mandatory for every coupon leg):
Every selection in the coupon table MUST use a Polish-language market description so the user can match it to Betclic's Polish interface without error.

Full team/player names (MANDATORY):
- Always use FULL official names: "RB Leipzig" not "Leipzig", "Istanbul Basaksehir" not "Basaksehir", "Montreal Canadiens" not "Montreal".
- Include competition name in parentheses: "(Bundesliga)", "(ATP Madrid R1)", "(NHL Playoffs)".
- For tennis: include both player names + tournament + round: "Jiri Lehecka vs Alejandro Tabilo (ATP Madrid R1)".
- Reason: Betclic often lists multiple teams with similar names (e.g. RB Leipzig, Lokomotive Leipzig, Chemie Leipzig). User must find the EXACT event.

Standard translations:
- Over X.5 goals → Powyżej X.5 bramek
- Under X.5 goals → Poniżej X.5 bramek
- Over X.5 corners → Powyżej X.5 rzutów rożnych
- Under X.5 corners → Poniżej X.5 rzutów rożnych
- Over X.5 cards → Powyżej X.5 kartek
- BTTS Yes → Obie drużyny strzelą - Tak
- BTTS No → Obie drużyny strzelą - Nie
- Team ML / Team wins → Zwycięstwo [Team]
- Double chance 1X → Podwójna szansa 1X (gospodarze lub remis)
- Double chance X2 → Podwójna szansa X2 (goście lub remis)
- Draw No Bet → Remis - Loss refund
- Over X.5 shots → Powyżej X.5 strzałów
- Over X.5 total games (tennis) → Powyżej X.5 gemów łącznie
- Set handicap -1.5 → Handicap setowy -1.5
- Map handicap -1.5 → Handicap mapowy -1.5
- Total sets Over 3.5 → Łączna liczba setów powyżej 3.5
- Team +X.5 pts set 1 → [Team] +X.5 pkt w 1. secie
- Total frames Over X.5 → Łączna liczba framów powyżej X.5
- Total goals Under X → Łączna liczba goli poniżej X
- Run line -1.5 → Handicap -1.5 (runs)
For any market not listed: provide a clear Polish description that matches Betclic's terminology.

Use these exact CSV headers.

betting/journal/picks-ledger.csv
betting_day,version,pick_id,event,sport,competition,market,selection,bookmaker,bookmaker_odds,market_best_odds,price_gap_pct,odds_checked_at_local,stake_pln,risk_tier,confidence_1_5,status,pnl_pln,stat_sources,market_sources,verification_sources,main_reason,main_risk,notes

betting/journal/coupons-ledger.csv
betting_day,version,coupon_id,variant,selections_count,pick_ids,combined_odds,stake_pln,risk_level,status,pnl_pln,odds_checked_at_local,correlation_check,main_logic,notes

betting/journal/source-log.csv
betting_day,source_name,role,sport_scope,availability,used_in_analysis,used_in_final_picks,notes

Field conventions:
- version values are v1, v2, v3, etc. On first run = v1. On rerun, increment from the highest existing version for that day.
- risk_tier values are low, medium, high.
- confidence_1_5 uses integers from 1 to 5.
- variant is a short coupon label/name (e.g., "LR01 Pewniaki v23", "MS01 Multi-Sport v23", "HR01 Ryzykanci v23", "N01 Night v23"). Use descriptive names.
- risk_level values are low-risk or higher-risk.
- correlation_check values are pass or flagged.
- availability values are available, partial, or unavailable.
- used_in_analysis and used_in_final_picks values are yes or no.

ID and update rules:
- Pick IDs use PK-YYYYMMDD-## (e.g., PK-20260422-01).
- Pick IDs are UNIQUE PER VERSION — a rerun creates new pick IDs (next available ##) rather than reusing old ones. All picks from all versions are kept.
- Coupon IDs: CP-YYYYMMDD-LR1v#, CP-YYYYMMDD-LR2v#, CP-YYYYMMDD-HR1v#, CP-YYYYMMDD-MS1v# for each type. Prefixes: LR = low-risk, HR = higher-risk, MS = multi-sport, N = night. The version suffix (e.g., v6) prevents collisions across versions.
- Legacy single-coupon IDs CP-YYYYMMDD-LR and CP-YYYYMMDD-HR are also valid.
- Overwrite same-day report and coupon files on rerun.
- Update ledger rows in place where IDs already exist. Do not append duplicate rows for the same ID.

Allowed pick statuses:
- pending
- placed
- win
- loss
- push
- void
- half_win
- half_loss
- superseded

Allowed coupon statuses:
- pending
- win
- loss
- void
- superseded

PnL rules:
- win = stake_pln * (odds - 1)
- loss = -stake_pln
- push = 0
- void = 0
- half_win = stake_pln * (odds - 1) / 2
- half_loss = -stake_pln / 2
- pending uses an empty pnl_pln cell
- if a coupon leg is void or push, recalculate effective combined odds from the remaining active legs and settle the coupon from the adjusted price