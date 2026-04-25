---
name: step8-portfolio
description: "STEP 8-10: Portfolio construction, V1-V10 validation, artifact generation. Builds final coupons."
agent: bet-analyst
argument-hint: "run_date=2026-04-25"
tools:
  - search
  - editFiles
  - runCommands
  - memory/*
  - sequentialthinking/*
---

## Inputs
- **run_date** = ${input:run_date:today}
- **bear_case** = `betting/data/{run_date}_bear_case.md` (approved picks from step7)
- **odds_ev** = `betting/data/{run_date}_odds_ev.md`
- **config** = `config/betting_config.json`

## Task

Build the final coupon portfolio from approved picks. Validate with V1-V10 protocol. Generate all artifacts.

### STEP 8: Portfolio Construction

1. **Rank approved picks** by: EV (highest first) → confidence → price_gap
2. **Identify Pewniaki** (top 3-5 by EV×confidence) — build ALL non-repeating combinations:
   - 3 pewniaki → 3 doubles + 1 triple = 4 coupons
   - 4 pewniaki → 6 doubles + 4 triples + 1 quad = 11 coupons
   - 5 pewniaki → 10 doubles + 10 triples + 5 quads + 1 quint = 26 coupons (pick best 4-6)
3. **Build themed coupons** from remaining picks:
   - Multi-sport (≥3 sports per coupon)
   - Evening/night (events after 20:00)
   - US sports (NHL/NBA/MLB)
   - Higher risk (5+ legs, higher combined odds)
4. **Correlation check** every leg pair in every coupon:
   - Same match → FORBIDDEN
   - Same league → FLAG (max 2 per coupon)
   - Same narrative → REMOVE weaker
5. **Concentration check**: If any pick in >60% of coupons → add resilience coupon WITHOUT it
6. **Stake assignment**:
   - Low risk (2-leg pewniaki): max 3.00 PLN
   - Medium risk (3-4 legs): 1.50-2.00 PLN
   - High risk (5+ legs): 1.00-1.50 PLN
7. **Minimum 5 coupons total**. No singles. No maximum legs.
8. **Watchlist**: picks that didn't pass approval gate but are close. Include promotion criteria.

### STEP 9: V1-V10 Validation

Run EVERY check. Fail = fix and re-check.

| V | Check | What to verify |
|---|-------|----------------|
| V1 | Artifact consistency | pick_ids unique, coupon_ids unique, stake sums match |
| V2 | Per-pick sources | ≥1 Tier A stats + ≥1 Tier A market + EV>0 + confidence score |
| V3 | Tennis checks | Ratio graded, surface verified, WC/LL checked, identity confirmed, drift <8% |
| V4 | Football checks | Market hierarchy followed, corner stack, BTTS league %, defensive profile |
| V4b-j | Sport-specific | Volleyball ML range, padel FIP, speedway lineup, etc. |
| V4k | Upset risk | Every fav ≤1.50 has upset score. If ≥threshold and ML → MUST justify |
| V5 | Coupon structure | Min 2 legs, same-sport ≤2, **ARITHMETIC: multiply legs explicitly**, stake limits, min 5 coupons |
| V6 | Portfolio risk | Exposure <25% bankroll, diversification, no >60% concentration |
| V7 | Weaknesses | Borderline picks flagged, CONDITIONAL noted, weakest leg per coupon named |
| V7b | Date verification | Every event confirmed on correct date with correct teams |
| V7c | Cross-coupon | No duplicate legs outside pewniaki, no identical coupons |
| V8 | Source audit | Tier A per pick, ≥2 independent sources, tipster checked |
| V9 | Composition | EV ranking applied, sport diversity, combined odds ranges (pewniaki 2-8, MS 3-10, HR 8-20) |
| V10 | Sign-off | All V1-V9 pass → APPROVED |

### STEP 10: Artifact Generation

Write/update ALL of these files:

1. **Coupon file**: `betting/coupons/{run_date}-v{N}.md` — Polish descriptions, tables, PODSUMOWANIE
2. **Picks ledger**: `betting/journal/picks-ledger.csv` — add new picks, supersede old version
3. **Coupons ledger**: `betting/journal/coupons-ledger.csv` — add new coupons, supersede old version
4. **Source log**: `betting/journal/source-log.csv` — record all sources used and failures
5. **Report**: `betting/reports/{run_date}-v{N}.md` — full daily report per artifact spec

### Coupon File Format (Polish)

```markdown
# Kupony {date} — v{N}
## Bankroll: X PLN | Budżet: X-X PLN
## Wszystkie typy WARUNKOWE — zweryfikuj kursy w aplikacji Betclic

### PEWNIAKI
| # | Kupon | Co obstawić | Kurs | Stawka | Zwrot |
|---|-------|-------------|------|--------|-------|

### MULTI-SPORT
| # | Kupon | Co obstawić | Kurs | Stawka | Zwrot |
...

### HIGHER RISK
...

### PODSUMOWANIE
| Metryka | Wartość |
|---------|--------|
| Wydatek | X PLN |
| Bankroll po | X PLN |
| Łączny pot. zwrot | X PLN |
| Najlepszy scenariusz | X PLN |

### KOLEJNOŚĆ STAWIANIA
1. [coupon] — [reason]
...
```

### Quality Gates
- [ ] ≥5 coupons
- [ ] ≥5 sports in picks
- [ ] All arithmetic shown (multiply each coupon's legs explicitly)
- [ ] No pick in >60% coupons (or resilience coupon added)
- [ ] Every pick has Polish description
- [ ] PODSUMOWANIE complete
- [ ] All ledgers updated
- [ ] odds_checked_at timestamp per pick
