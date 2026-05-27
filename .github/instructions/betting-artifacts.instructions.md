---
applyTo: "betting/**/*"
---

# Betting Artifacts Format (Canonical)

Companion skill [bet-formatting-artifacts](../skills/bet-formatting-artifacts/SKILL.md) provides activation guidance only.

## General Rules

- Timezone: Europe/Warsaw. Dot decimals for odds/PLN. YYYY-MM-DD dates. `|` separator in CSV multi-value cells.
- Reruns: PRESERVE old versions, ADD new (v5 → v6). Mark old pending as `superseded`.
- DB-first: SQLite primary, JSON/MD dual-write for human readability.
- Key DB tables: `analysis_results` (S3), `gate_results` (S7), `coupons` + `bets`, `fixtures`, `odds_history`, `team_form`.

## Daily Report

**Path:** `betting/reports/YYYY-MM-DD.md`

**Sections (in order):** Run Metadata → Previous Day Settlement → Learning Update (max 3 changes) → Source Availability → Candidate Board → Final Coupons → Rejected Picks → Exposure Summary

## Coupon File (PRIMARY DELIVERABLE)

**Path:** `betting/coupons/YYYY-MM-DD.md` — identical to chat output.

**Structure:**
1. H1 header (date, bankroll, budget) + conditional notice
2. **PEŁNA MATRYCA RYNKÓW** — top 30-50 opportunities sorted by safety desc. Columns: `# | Sport | Event | Market | Odds | Safety | Hit% | Direction | Uwagi`. Multiple rows per event (all analyzed markets). NO filtering by EV.
3. Per-type coupon tables (LOW-RISK, MULTI-SPORT, HIGHER RISK, NIGHT). Columns: `# | Coupon ID | Co obstawić | Kurs | Stawka | Zwrot`. UNIQUE EVENT PER COUPON.
4. **COMBINATION MENU** — 4-8 COMBO- prefixed coupons remixing approved picks.
5. **ROZSZERZONY WYBÓR (Extended Pool)** — EV>0 picks that failed some gate checks.
6. Per-coupon reasoning: logic + P(coupon) + biggest risk + tipster insight.
7. PODSUMOWANIE table (Wydatek, Bankroll po, Łączny pot. zwrot, Stan konta po zwrocie, Najlepszy/Realistyczny scenariusz).
8. KOLEJNOŚĆ STAWIANIA — placement priority.
9. LISTA OBSERWACYJNA — 2-3 backup picks with promotion criteria.
10. ODRZUCONE — Top 10 near-misses grouped by rejection category.

Total suggested stakes WILL exceed budget — user picks favorites.

### §EXTENDED-POOL — Extended Pool (ROZSZERZONY WYBÓR)

The extended pool captures ALL picks with **EV > 0** that were NOT included in core/combo coupons. These are picks that failed some 18-point gate checks, had bear≥bull concerns, or lacked data — but still have positive expected value. The user sees them with full context and decides whether to risk them.

**Inclusion threshold:** EV > 0 (calculated in S4). Exclude only: phantom fixtures (ZT#6), wrong dates, or negative EV. **NEVER exclude based on sport/market historical hit rates** — Betclic learning data is advisory for the user only.

**COMPLETENESS RULE (§3.0f enforcement):** Per §3.0f in analysis-methodology, ALL shortlisted candidates that are not PHANTOM/VOID receive full §3.0 analysis. After analysis, every candidate lands in exactly one of three buckets:
1. **Core portfolio** — passed 18-point gate fully
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

DB artifact storage:
- Picks are stored in DB `bets` table (via `CouponRepo`) in addition to `picks-ledger.csv`.
- Coupons are stored in DB `coupons` table (via `CouponRepo`) in addition to `coupons-ledger.csv`.
- S3 deep stats output is stored in DB `analysis_results` table alongside `{date}_s3_deep_stats.json/.md`.
- S7 gate results are stored in DB `gate_results` table alongside `{date}_s7_gate_results.json/.md`.
- The DB is the queryable primary store; CSV/JSON/MD files remain for human readability.

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
- Total sets Over 3.5 → Łączna liczba setów powyżej 3.5
- Team +X.5 pts set 1 → [Team] +X.5 pkt w 1. secie
- Total goals Under X → Łączna liczba goli poniżej X
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