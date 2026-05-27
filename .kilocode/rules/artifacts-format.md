# Betting Artifacts Format

## General Rules

- Timezone: Europe/Warsaw. Dot decimals for odds/PLN. YYYY-MM-DD dates.
- Reruns: PRESERVE old versions, ADD new (v5 → v6). Mark old pending as `superseded`.
- DB-first: SQLite primary, JSON/MD dual-write for human readability.
- Polish market descriptions mandatory. Full team/player names mandatory.

---

## Coupon File Structure

**Path:** `betting/coupons/YYYY-MM-DD.md`

1. **H1 header** — date, bankroll, budget + conditional notice
2. **PEŁNA MATRYCA RYNKÓW** — top 30-50 by safety DESC. Columns: `# | Sport | Event | Market | Odds | Safety | Hit% | Direction | Uwagi`. Multiple rows per event. NO filtering by EV.
3. **Core coupon tables** — LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT. Columns: `# | Coupon ID | Co obstawić | Kurs | Stawka | Zwrot`. UNIQUE EVENT PER COUPON.
4. **COMBINATION MENU** — 4-8 COMBO- prefixed coupons remixing approved picks.
5. **ROZSZERZONY WYBÓR (Extended Pool)** — EV>0 picks that failed some gate checks.
6. **Per-coupon reasoning** — logic + P(coupon) + biggest risk + tipster insight.
7. **PODSUMOWANIE** — Wydatek, Bankroll po, Łączny pot. zwrot, Stan konta po zwrocie, Najlepszy/Realistyczny scenariusz.
8. **KOLEJNOŚĆ STAWIANIA** — placement priority.
9. **LISTA OBSERWACYJNA** — 2-3 backup picks with promotion criteria.
10. **ODRZUCONE** — Top 10 near-misses grouped by rejection category.

---

## Extended Pool Format (§EXTENDED-POOL)

**Inclusion:** EV > 0. Exclude only phantom fixtures, wrong dates, negative EV.

Per extended pick:
| Field | Content |
|-------|---------|
| Event | Full names, competition, time |
| Market | Polish description |
| Odds | Estimated Betclic odds |
| EV | Calculated EV % |
| Gate score | X/18 passed |
| ✅ Co przemawia ZA | 2-3 bullets with specific data |
| ❌ Co przemawia PRZECIW | 2-3 bullets with failure scenarios |
| ⚠️ Brakujące dane | Which gate checks failed |
| 🎯 Kiedy wstawiać | Conditions: "Wstaw jeśli kurs ≥X.XX + [condition]" |
| 🏷️ Sugerowane combo | Pairing suggestions |

---

## STATS-FIRST Format (§STATS-FIRST)

For picks without verified Betclic odds — probability portfolio:

| Field | Content |
|-------|---------|
| Event | Full names, competition, time |
| Market | Polish description |
| Odds | `SPRAWDŹ NA BETCLIC` |
| Hit Rate | e.g., "8/10 L10, 4/5 H2H = 80%" |
| Safety Score | e.g., "0.80" |
| Min Odds | Minimum for EV>0: `1/hit_rate` |
| L10 Avg | Average from last 10 |
| Suggested Lines | Lines to check on Betclic |

---

## Polish Market Translations

| English | Polish (Betclic) |
|---------|-----------------|
| Over X.5 goals | Powyżej X.5 bramek |
| Under X.5 goals | Poniżej X.5 bramek |
| Over X.5 corners | Powyżej X.5 rzutów rożnych |
| Over X.5 cards | Powyżej X.5 kartek |
| BTTS Yes | Obie drużyny strzelą - Tak |
| BTTS No | Obie drużyny strzelą - Nie |
| Team ML | Zwycięstwo [Team] |
| Double chance 1X | Podwójna szansa 1X |
| Over X.5 total games | Powyżej X.5 gemów łącznie |
| Set handicap -1.5 | Handicap setowy -1.5 |
| Total sets Over 3.5 | Łączna liczba setów powyżej 3.5 |

---

## Full Names (MANDATORY)

- Always use FULL official names: "RB Leipzig" not "Leipzig", "Montreal Canadiens" not "Montreal"
- Include competition: "(Bundesliga)", "(ATP Madrid R1)", "(NHL Playoffs)"
- Tennis: both players + tournament + round: "Jiri Lehecka vs Alejandro Tabilo (ATP Madrid R1)"

---

## DB Artifact Storage

| Artifact | DB Table | Secondary |
|----------|----------|-----------|
| S3 stats | `analysis_results` | `{date}_s3_deep_stats.json/.md` |
| S7 gate | `gate_results` | `{date}_s7_gate_results.json/.md` |
| Picks | `bets` (CouponRepo) | `picks-ledger.csv` |
| Coupons | `coupons` (CouponRepo) | `coupons-ledger.csv` |

---

## Per-Pick Concentration Limit

When user selects coupons: no single pick may account for >50% of total selected budget.
Include per-pick exposure table in PODSUMOWANIE.

## Daily Report

**Path:** `betting/reports/YYYY-MM-DD.md`
Sections: Run Metadata → Previous Day Settlement → Learning Update → Source Availability → Candidate Board → Final Coupons → Rejected Picks → Exposure Summary
