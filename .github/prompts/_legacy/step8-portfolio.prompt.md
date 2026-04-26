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
2. **UNIQUE EVENT PER COUPON (ABSOLUTE — NEVER VIOLATE):** Each pick appears in ONLY ONE coupon. Zero sharing.
   - 10 picks → 5 × 2-leg coupons
   - 12 picks → 4 × 3-leg coupons, or mix of 2-leg and 3-leg
   - If not enough picks for 5 coupons → reduce to 3-4 coupons. If <4 picks → NO BET.
3. **Build diverse coupons** from approved picks:
   - Low-risk (2-3 legs, best EV picks)
   - Multi-sport (≥2 sports per coupon)
   - Higher risk (3-5 legs, combined odds 8-20)
   - Night (events ≥22:00 CEST only)
4. **Correlation check** every leg pair in every coupon:
   - Same match → inherently impossible (unique event rule)
   - Same league → FLAG (max 2 per coupon)
   - Same narrative → REMOVE weaker
5. **Stake assignment**:
   - Low risk (2-leg): max 3.00 PLN
   - Medium risk (3-4 legs): 1.50-2.00 PLN
   - High risk (5+ legs): 1.00-1.50 PLN
6. No singles. No maximum legs.
7. **Watchlist**: picks that didn't pass approval gate but are close. Include promotion criteria.

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
| V6 | Portfolio risk | Exposure <25% bankroll, diversification, unique-event verified |
| V7 | Weaknesses | Borderline picks flagged, CONDITIONAL noted, weakest leg per coupon named |
| V7b | Date verification | Every event confirmed on correct date with correct teams |
| V7c | Cross-coupon | UNIQUE EVENT PER COUPON verified, no correlated narratives |
| V8 | Source audit | Tier A per pick, ≥2 independent sources, tipster checked |
| V9 | Composition | EV ranking applied, sport diversity, combined odds ranges (2-leg 2-4, 3-leg 4-10, 4-leg 8-20) |
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

### LOW-RISK
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
