---
applyTo: "betting/**/*"
---

# Betting Artifacts Format

## General Rules

- Timezone: Europe/Warsaw. Dot decimals. YYYY-MM-DD dates. `|` in CSV multi-value cells.
- Reruns: preserve old versions, add new (v5→v6). Mark old pending as `superseded`.
- DB-first: SQLite primary. JSON/MD dual-write for readability.
- Full Polish descriptions mandatory for every coupon leg (matches Betclic UI).
- Full team/player names with competition in parentheses.

## Coupon File (`betting/coupons/YYYY-MM-DD.md`)

**Sections in order:**
1. Header (date, bankroll, budget) + conditional notice
2. **PEŁNA MATRYCA RYNKÓW** — top 30-50 by safety. Columns: `# | Sport | Event | Market | Odds | Safety | Hit% | Direction | Uwagi`
3. Per-type coupons: LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT. Columns: `# | Coupon ID | Co obstawić | Kurs | Stawka | Zwrot`. UNIQUE EVENT PER COUPON.
4. **COMBINATION MENU** — 4-8 COMBO- coupons remixing picks. Reuse allowed.
5. **ROZSZERZONY WYBÓR** — EV>0 picks that failed some gate checks. Bull/bear case per pick.
6. Per-coupon reasoning: logic + P(coupon) + risk + tipster insight.
7. PODSUMOWANIE table + per-pick exposure.
8. KOLEJNOŚĆ STAWIANIA — placement priority.
9. LISTA OBSERWACYJNA — 2-3 backups with promotion criteria.
10. ODRZUCONE — top 10 near-misses by rejection category.

## Extended Pool Rules

Includes ALL picks with EV > 0 not in core/combo. Never exclude by sport/market hit rate.
Each pick shows: event, market, odds, EV, gate score, bull case, bear case, missing data, when to bet, suggested combos.

## STATS-FIRST Picks (`PORTFOLIO PRAWDOPODOBIEŃSTW` section)

For events without API odds. Shows: hit rate, safety, direction+margin, min odds for EV>0, suggested lines.
User checks Betclic → if `hit_rate × odds > 1.0` → positive EV → bet.

## Polish Translations (standard)

| English | Polish (Betclic) |
|---------|-----------------|
| Over X.5 corners | Powyżej X.5 rzutów rożnych |
| Under X.5 corners | Poniżej X.5 rzutów rożnych |
| Over X.5 cards | Powyżej X.5 kartek |
| Over X.5 goals | Powyżej X.5 bramek |
| BTTS Yes | Obie drużyny strzelą - Tak |
| Team ML | Zwycięstwo [Team] |
| Double chance 1X | Podwójna szansa 1X |
| Over X.5 total games | Powyżej X.5 gemów łącznie |
| Set handicap -1.5 | Handicap setowy -1.5 |
| Total sets Over 3.5 | Łączna liczba setów powyżej 3.5 |

## Ledger Files

**picks-ledger.csv** (`betting/journal/`):
`betting_day,version,pick_id,event,sport,competition,market,selection,bookmaker,bookmaker_odds,market_best_odds,price_gap_pct,odds_checked_at_local,stake_pln,risk_tier,confidence_1_5,status,pnl_pln,stat_sources,market_sources,verification_sources,main_reason,main_risk,notes`

**coupons-ledger.csv** (`betting/journal/`):
`betting_day,version,coupon_id,variant,selections_count,pick_ids,combined_odds,stake_pln,risk_level,status,pnl_pln,odds_checked_at_local,correlation_check,main_logic,notes`

## ID Rules

- Pick: `PK-YYYYMMDD-##` (unique per version, never reused)
- Coupon: `CP-YYYYMMDD-LR1v#`, `CP-YYYYMMDD-HR1v#`, `CP-YYYYMMDD-MS1v#`, `CP-YYYYMMDD-N1v#`
- Extended: `CP-YYYYMMDD-EXT-##`

## Statuses & PnL

| Status | PnL |
|--------|-----|
| win | stake × (odds − 1) |
| loss | −stake |
| push/void | 0 |
| half_win | stake × (odds − 1) / 2 |
| half_loss | −stake / 2 |
| pending | (empty) |
| superseded | (preserved, not settled) |

## Field Values

- `version`: v1, v2, v3...
- `risk_tier`: low, medium, high
- `confidence_1_5`: 1-5 integer
- `risk_level`: low-risk, higher-risk
- `correlation_check`: pass, flagged
- `availability`: available, partial, unavailable
