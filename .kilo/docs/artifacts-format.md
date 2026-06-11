# Betting Artifacts Format — Compact Reference

## General Rules
- Timezone: Europe/Warsaw. Dot decimals. YYYY-MM-DD dates. `|` separator in CSV multi-value cells.
- Reruns: preserve old versions, add new (v5→v6). Mark old pending as `superseded`.
- DB-first: SQLite primary. JSON/MD dual-write for human readability.

## Paths
- Report: `betting/reports/YYYY-MM-DD.md`
- Coupon: `betting/coupons/YYYY-MM-DD.md`
- Picks ledger: `betting/journal/picks-ledger.csv`
- Coupons ledger: `betting/journal/coupons-ledger.csv`
- Source log: `betting/journal/source-log.csv`

## Coupon File Structure
1. Header (date, bankroll, budget)
2. PEŁNA MATRYCA RYNKÓW — top 30-50 by safety (multiple rows per event)
3. Per-type coupon tables (LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT)
4. COMBINATION MENU — 4-8 COMBO- prefixed coupons
5. ROZSZERZONY WYBÓR (Extended Pool) — EV>0 picks that failed some gate checks
6. Per-coupon reasoning + P(coupon) + risk + tipster insight
7. PODSUMOWANIE table
8. KOLEJNOŚĆ STAWIANIA — placement priority
9. LISTA OBSERWACYJNA — backup picks with promotion criteria
10. ODRZUCONE — near-misses grouped by rejection category

## ID Conventions
- Pick: PK-YYYYMMDD-## (unique per version)
- Coupon: CP-YYYYMMDD-{LR|HR|MS|N}{#}v{version}
- Statuses: pending, placed, win, loss, push, void, half_win, half_loss, superseded

## Polish Market Translations
- Over X.5 corners → Powyżej X.5 rzutów rożnych
- Over X.5 goals → Powyżej X.5 bramek
- Over X.5 cards → Powyżej X.5 kartek
- BTTS Yes → Obie drużyny strzelą - Tak
- Team wins → Zwycięstwo [Team]
- Over X.5 total games → Powyżej X.5 gemów łącznie

## Full Names (MANDATORY)
Always use FULL official names + competition: "RB Leipzig (Bundesliga)", "Jiri Lehecka vs Alejandro Tabilo (ATP Madrid R1)".
