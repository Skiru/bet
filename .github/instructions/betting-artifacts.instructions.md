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
4. **LISTA OBSERWACYJNA (WATCHLIST) — 2-5 backup picks:**
   - For each: event, market, odds, and promotion criteria ("Wstaw jeśli Betclic ≥ X.XX").
   - Why it didn't make final: "Odrzucone bo: [reason]".
   - **TIPSTER-SOURCED PICKS (§4.3):** If a tipster with >55% accuracy argues for a statistical market (corners, cards, games, frames) with specific data backing, it MUST appear here with:
     - Tipster name and accuracy % from site
     - Full tipster argument (translated to Polish if from Polish site)
     - The specific stats cited (e.g., "Liège: śr. 6.2 rzutów rożnych/mecz w domu, 6/10 meczów >4.5 CK")
     - Promotion criteria: "Wstaw jeśli: kurs Betclic ≥X.XX + potwierdzone przez ≥1 źródło statystyczne"
   - **NOTE:** With the Extended Pool section now capturing EV>0 watchlist picks directly, LISTA OBSERWACYJNA is reserved for picks WITHOUT calculated EV or awaiting a specific trigger (e.g., lineup confirmation). EV>0 picks move to Extended Pool.
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
2b. **PEŁNA MATRYCA RYNKÓW (FULL MARKET MATRIX)** — Placed BEFORE coupons for quick scanning. Reference link to `betting/data/market_matrix_{date}.md` and `decision_matrix_{date}.md` (see §1.9 in analysis-methodology). Inline in the coupon file, include a COMPACT matrix of the top 30-50 bettable opportunities:
   - Table: | # | Sport | Event | Market | Odds | Safety | Hit% | Direction | Uwagi | — sorted by safety score desc, then by sport.
   - **Multiple rows per event**: When an event has multiple statistical markets analyzed (e.g., corners, cards, fouls, totals), show ALL markets as separate rows. This lets the user compare markets and pick the strongest one per event. Group by event visually (indent or blank row between events).
   - **Safety**: safety score from §3.0 ranking (0.00-1.00). Shows how statistically reliable the market is.
   - **Hit%**: Combined L10 + H2H hit rate (e.g., "8/10 L10, 4/5 H2H = 80%"). Shows probability of the pick landing.
   - **Direction**: OVER/UNDER + margin (e.g., "OVER +17.9%") — how far the average is from the line.
   - **WHY this is shown**: The matrix is a decision tool. Probability data lets the user do quick mental EV: `hit% × odds > 1.0 → bet`. Without it, the user must open market_matrix.md separately.
   - This is the PRIMARY decision tool for the user.
   - NO events are filtered out based on EV — show everything with available data.
   - For events with API odds: show odds + safety + hit%. For STATS-FIRST events (no API odds): show "SPRAWDŹ" + safety + hit% + min odds for EV>0.
3. Per-type coupon tables (LOW-RISK, MULTI-SPORT, HIGHER RISK, NIGHT) — each with columns: #, Coupon ID, Co obstawić, Kurs, Stawka, Zwrot. UNIQUE EVENT PER COUPON.
3b. **COMBINATION MENU** — additional combos (COMBO-LR1, COMBO-MS1, etc.) that remix approved picks. Same table format. Prefixed "COMBO-" for clarity.
3c. **ROZSZERZONY WYBÓR (EXTENDED POOL)** — EV > 0 picks that did NOT fully pass the 17-point gate but have positive expected value. These are optional higher-risk plays the user may choose to add. See §EXTENDED-POOL below for structure.
4. **Per-coupon reasoning block** (under each table): logic, P(coupon), biggest risk.
5. PODSUMOWANIE table (Wydatek, Bankroll po, Łączny pot. zwrot, Stan konta po zwrocie, Najlepszy scenariusz, Realistyczny).
6. KOLEJNOŚĆ STAWIANIA — placement priority list.
7. **LISTA OBSERWACYJNA** — 2-3 backup picks with promotion criteria.
8. **ODRZUCONE** — Top 10 near-misses with specific rejection reasons, grouped by rejection category.
9. Pominięte coupons note (which coupons were skipped and why, one line).
10. Time-sensitive warnings if any matches may have already started.

No old-style plain-text metadata blocks (BETTING DAY:, RUN TIME LOCAL:, etc.) — that data lives in the ledger CSVs.
Coupon count = f(quality events, deep statistics), NOT f(bankroll). No singles. No maximum legs per coupon.
Core portfolio: unique event per coupon. Combo menu: reuse allowed. Extended pool: optional extras. Together they give the user maximum choice.
Total suggested stakes (core + combos + extended) WILL exceed daily budget — user picks favorites. NEVER reduce coupon count because of money constraints.

### §EXTENDED-POOL — Extended Pool (ROZSZERZONY WYBÓR)

The extended pool captures ALL picks with **EV > 0** that were NOT included in core/combo coupons. These are picks that failed some 17-point gate checks, had bear≥bull concerns, or lacked data — but still have positive expected value. The user sees them with full context and decides whether to risk them.

**Inclusion threshold:** EV > 0 (calculated in S5). Exclude only: phantom fixtures (ZT#6), wrong dates, or negative EV. **NEVER exclude based on sport/market historical hit rates** — Betclic learning data is advisory for the user only.

**COMPLETENESS RULE (§3.0f enforcement):** Per §3.0f in analysis-methodology, ALL shortlisted candidates that are not PHANTOM/VOID receive full §3.0 analysis. After analysis, every candidate lands in exactly one of three buckets:
1. **Core portfolio** — passed 17-point gate fully
2. **Extended pool** — EV > 0 but failed some gate checks
3. **Rejected list (ODRZUCONE)** — EV ≤ 0 or critical red flag

No candidate with completed §3.0 analysis and EV > 0 may be silently omitted. The user must see all three groups to make informed decisions.

**Required format per extended pick:**

| Field | Content |
|-------|---------|
| Event | Full names, competition, time |
| Market | Polish description (same as coupon legs) |
| Odds | Estimated Betclic odds |
| EV | Calculated EV % |
| Gate score | X/17 passed (e.g., "11/17") |
| ✅ Co przemawia ZA (Bull case) | 2-3 bullet points with specific data |
| ❌ Co przemawia PRZECIW (Bear case) | 2-3 bullet points with specific failure scenarios |
| ⚠️ Brakujące dane (Missing data) | Which gate checks failed and why |
| 🎯 Kiedy wstawiać (When to bet) | Specific conditions: "Wstaw jeśli kurs ≥X.XX + [condition]" |
| 🏷️ Sugerowane combo | Which approved picks it pairs well with, with combined odds |

**Extended pool picks also get COMBO suggestions** — pairings with approved picks, prefixed "EXT-" (e.g., EXT-HR1). These combos have their own table with the same columns as regular combos. Extended combos use `risk_level=higher-risk` always.

**Ledger handling:** Extended picks are added to picks-ledger.csv with `risk_tier=high` and `notes` starting with "EXTENDED POOL:". Extended combos are added to coupons-ledger.csv with coupon_id prefix "CP-YYYYMMDD-EXT".

**Extended pool picks are NEVER in core or combo coupons** — they live in their own section. This preserves the quality separation: Core = fully vetted, Combo = remixed vetted picks, Extended = EV>0 but user's choice.

### §STATS-FIRST — Probability Portfolio Output (when odds unavailable)

When using STATS-FIRST mode (§5.ALT in analysis-methodology), events without API odds get a **probability portfolio** format instead of standard coupon entries.

**Required format per STATS-FIRST pick:**

| Field | Content |
|-------|---------|
| Event | Full names, competition, time |
| Market | Polish description (e.g., "powyżej 9.5 rzutów rożnych") |
| Odds | `SPRAWDŹ NA BETCLIC` |
| Hit Rate | e.g., "8/10 L10, 4/5 H2H = 80%" |
| Safety Score | e.g., "0.80" |
| Direction | OVER / UNDER + margin (e.g., "OVER +17.9%") |
| Min Odds | Minimum Betclic odds for EV>0: `1/hit_rate` (e.g., "≥1.25") |
| L10 Avg | Average from last 10 matches (e.g., "11.2") |
| H2H Avg | Average from H2H meetings (e.g., "10.8") |
| Suggested Lines | Lines to check on Betclic (e.g., "O9.5 / O10.5 / O11.5") |
| ✅ Argument | 2-3 bullets with specific data why this market is strong |
| ⚠️ Red Flags | Any concerns (H2H blind, small sample, trend divergence) |
| 🏷️ Sugerowane combo | Which other picks it pairs well with |

**User workflow after receiving probability portfolio:**
1. Open Betclic app → search for the event
2. Navigate to the specific market (e.g., "Rzuty rożne" → "Powyżej 9.5")
3. Note the Betclic odds
4. Quick mental check: `hit_rate × odds > 1.0?` → YES = positive EV → BET
5. If multiple lines available, pick the one where `hit_rate × odds` is highest

**Coupon file format:** STATS-FIRST picks appear in a separate section **"PORTFOLIO PRAWDOPODOBIEŃSTW"** AFTER the core/combo/extended sections. They are NOT included in coupon arithmetic (no combined odds) until the user confirms Betclic odds.

**Ledger handling:** STATS-FIRST picks are added to picks-ledger.csv with:
- `odds` = blank (filled by user after Betclic check)
- `ev` = blank (filled by user after Betclic check)
- `notes` starting with "STATS-FIRST: min odds X.XX for EV>0, safety=X.XX"
- `status` = "conditional"

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