---
name: bet-formatting-artifacts
description: "Output formatting standards for betting artifacts — Polish-language market descriptions, coupon table structure, ledger CSV headers and field conventions, pick/coupon ID generation rules, versioning protocol, full team name requirements, and standard translations. Use when writing coupon files, updating ledgers, generating reports, or formatting any betting output."
user-invokable: false
---

# Formatting Betting Artifacts

Standards for all betting output files — coupons, reports, ledgers, and source logs. Ensures consistent formatting, correct Polish descriptions, and proper ID management.

## File Paths

| Artifact | Path |
|----------|------|
| Daily report | `betting/reports/YYYY-MM-DD.md` (rerun: `-vN.md`) |
| Coupon file | `betting/coupons/YYYY-MM-DD.md` (session: `-night.md`, `-morning.md`, `-day.md`; rerun: `-vN.md`) |
| Picks ledger | `betting/journal/picks-ledger.csv` |
| Coupons ledger | `betting/journal/coupons-ledger.csv` |
| Source log | `betting/journal/source-log.csv` |
| Learning log | `betting/journal/learning-log.csv` |

## Polish Market Descriptions (MANDATORY for every coupon leg)

| English | Polish |
|---------|--------|
| Over X.5 goals | Powyżej X.5 bramek |
| Under X.5 goals | Poniżej X.5 bramek |
| Over X.5 corners | Powyżej X.5 rzutów rożnych |
| Under X.5 corners | Poniżej X.5 rzutów rożnych |
| Over X.5 cards | Powyżej X.5 kartek |
| BTTS Yes | Obie drużyny strzelą - Tak |
| BTTS No | Obie drużyny strzelą - Nie |
| Team ML / wins | Zwycięstwo [Team] |
| Double chance 1X | Podwójna szansa 1X (gospodarze lub remis) |
| Double chance X2 | Podwójna szansa X2 (goście lub remis) |
| Draw No Bet | Remis - Loss refund |
| Over X.5 shots | Powyżej X.5 strzałów |
| Over X.5 total games (tennis) | Powyżej X.5 gemów łącznie |
| Set handicap -1.5 | Handicap setowy -1.5 |
| Map handicap -1.5 | Handicap mapowy -1.5 |
| Total sets Over 3.5 | Łączna liczba setów powyżej 3.5 |
| Total frames Over X.5 | Łączna liczba framów powyżej X.5 |
| Run line -1.5 | Handicap -1.5 (runs) |
| Over X.5 fouls | Powyżej X.5 fauli |

For unlisted markets: provide clear Polish that matches Betclic's terminology.

## Full Team/Player Names (MANDATORY)

- Always use FULL official names: "RB Leipzig" not "Leipzig", "Istanbul Basaksehir" not "Basaksehir"
- Include competition: "(Bundesliga)", "(ATP Madrid R1)", "(NHL Playoffs)"
- Tennis: both names + tournament + round: "Jiri Lehecka vs Alejandro Tabilo (ATP Madrid R1)"
- Reason: Betclic lists multiple teams with similar names.

## ID Rules

### Pick IDs
Format: `PK-YYYYMMDD-##` (e.g., PK-20260422-01)
- UNIQUE PER VERSION — reruns create new IDs (next available ##)
- All picks from all versions are kept

### Coupon IDs
Format: `CP-YYYYMMDD-{TYPE}{N}v{VERSION}`
- Prefixes: LR = low-risk, HR = higher-risk, MS = multi-sport, N = night
- Combo prefix: COMBO-LR1, COMBO-MS1, etc.
- Example: CP-20260427-LR1v6, CP-20260427-COMBO-HR1v6

## Versioning Protocol (Reruns)

1. Scan existing `betting/coupons/YYYY-MM-DD*.md` for highest version
2. Increment: v5 → v6
3. New IDs with new version suffix
4. Old `pending` picks/coupons → `superseded`
5. Create new versioned files. Keep all previous versions.

## Coupon File Structure

```markdown
# 🎯 Kupony na [date] | Bankroll: X.XX PLN | Budżet: X.XX PLN

> ⚠️ Wszystkie typy są WARUNKOWE — zweryfikuj kursy w aplikacji Betclic

## LOW-RISK
| # | Kupon | Co obstawić | Kurs | Stawka | Zwrot |
|---|-------|-------------|------|--------|-------|

[Per-coupon reasoning: logic, P(coupon), biggest risk]

## MULTI-SPORT
[same table format]

## HIGHER RISK
[same table format]

## COMBINATION MENU
[COMBO-prefixed coupons, same table format]

## PODSUMOWANIE
| Metryka | Wartość |
|---------|--------|
| Wydatek | X.XX PLN |
| Bankroll po | X.XX PLN |
| Łączny pot. zwrot | X.XX PLN |
| Najlepszy scenariusz | X.XX PLN |
| Realistyczny | X.XX PLN |

## KOLEJNOŚĆ STAWIANIA
[placement priority list]

## LISTA OBSERWACYJNA
[2-5 backup picks with promotion criteria]

## ODRZUCONE
[Top 10 near-misses grouped by rejection category]
```

## Ledger CSV Headers

### picks-ledger.csv
```
betting_day,version,pick_id,event,sport,competition,market,selection,bookmaker,bookmaker_odds,market_best_odds,price_gap_pct,odds_checked_at_local,stake_pln,risk_tier,confidence_1_5,status,pnl_pln,stat_sources,market_sources,verification_sources,main_reason,main_risk,notes
```

### coupons-ledger.csv
```
betting_day,version,coupon_id,variant,selections_count,pick_ids,combined_odds,stake_pln,risk_level,status,pnl_pln,odds_checked_at_local,correlation_check,main_logic,notes
```

### source-log.csv
```
betting_day,source_name,role,sport_scope,availability,used_in_analysis,used_in_final_picks,notes
```

## Field Conventions

| Field | Valid Values |
|-------|-------------|
| version | v1, v2, v3, ... |
| risk_tier | low, medium, high |
| confidence_1_5 | integers 1-5 |
| variant | descriptive label: "LR01 Pewniaki v23", "MS01 Multi-Sport v23" |
| risk_level | low-risk, higher-risk |
| correlation_check | pass, flagged |
| availability | available, partial, unavailable |
| used_in_analysis / used_in_final_picks | yes, no |

## General Formatting Rules

- Dot decimals for odds and PLN amounts
- YYYY-MM-DD for dates, YYYY-MM-DD HH:MM for local timestamps
- `|` separator inside CSV cells with multiple source names
- Timezone: Europe/Warsaw
- Betting day: 06:00 today → 05:59 tomorrow
- No old-style plain-text metadata blocks — metadata in ledger CSVs only

## Connected Skills

| Skill | Load for |
|-------|----------|
| `bet-building-coupons` | Coupon construction rules — what goes INTO the artifacts formatted here |
| `bet-settling-results` | Settlement PnL entries, ledger status transitions |
