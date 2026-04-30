---
name: s5-odds-ev
description: "STEP 5: Multi-source odds comparison, EV calculation, Kelly staking"
agent: bet-valuator
---

# STEP 5 — ODDS + EV ANALYSIS

## INPUTS
- `betting/data/{date}_s3_deep_stats.md` — stats + recommended markets
- `betting/data/{date}_s4_tipsters.md` — tipster consensus
- Multi-source odds (choose best available):
  - **Preferred**: `betting/data/odds_multi_sources.json` (from `fetch_odds_multi.py` — aggregates 5 sources: The-Odds-API + API-Football + OddsPortal + BetExplorer + Betclic per SPORT_SOURCE_PRIORITY)
  - **Fallback**: `betting/data/odds_api_snapshot.json` (from `fetch_odds_api.py` — The-Odds-API only)
  - Both produce backward-compatible `odds_api_snapshot.json` + `odds_api_summary.csv`
- **Analysis pool**: `betting/data/analysis_pool_{date}.json` — may contain pre-computed EV for candidates with API odds data (`ev` field, calculated as `safety_score × market_best_odds − 1`). Use as starting point but always verify with fresh Betclic odds.
- **Market matrix** (if available): `betting/data/market_matrix_{date}.json` — contains consolidated odds from all sources per event/market, sorted by safety score

## TASK
For EACH candidate: get multi-source odds, estimate true probability, calculate EV. Reject if EV ≤ 0.

### PRE-CHECK: ANALYSIS POOL EV
Before web-fetching odds for each candidate:
1. Check `betting/data/analysis_pool_{date}.json` for pre-computed `ev` and `odds.market_best`
2. If present: use as cross-validation baseline. Still get fresh Betclic odds (user verifies on app).
3. The pool EV uses `safety_score` as probability proxy — refine with sharp bookmaker implied probabilities in the full EV calculation below.

### PER-CANDIDATE PROTOCOL:

1. **Get market-best odds** from ≥2 sources:
   - BetExplorer (primary)
   - OddsPortal (secondary)
   - The-Odds-API (cross-validation)
   - Sport-specific: SBR for US sports, SoccerStats for football

2. **Estimate true probability**:
   - Pinnacle implied probability (if available) — most sharp
   - Average of sharp bookmakers (Pinnacle, Betfair, bet365)
   - Statistical model estimate from S3 data
   - Tipster consensus from S4

3. **Calculate EV**:
   ```
   EV = (true_probability × betclic_odds) - 1
   ```
   Must be > 0. If ≤ 0 → REJECT.

4. **Calculate price_gap_pct**:
   ```
   price_gap_pct = 100 × ((betclic_odds / market_best_odds) - 1)
   ```
   - Low-risk: reject if < -3%
   - Higher-risk: reject if < -5%

5. **Check line movement**:
   - Opening odds vs current: steam move? RLM (reverse line movement)?
   - **Drift formula**: `drift_pct = 100 × ((current_odds / analysis_odds) - 1)`
   - For OVER markets: drift > +8% = market thinks LESS likely → investigate
   - For UNDER/ML: drift > +8% = market respects opponent more → investigate
   - Drift > 8% → MANDATORY re-evaluation — check injuries, lineups, sharp money. No explanation → SKIP.

6. **American odds conversion** (for SBR, ESPN, ScoresAndOdds):
   - Positive +X → decimal = 1 + X/100 (e.g., +150 = 2.50)
   - Negative -X → decimal = 1 + 100/X (e.g., -150 = 1.667)

7. **Apply 1/4 Kelly**:
   ```
   kelly_fraction = (true_prob × odds - 1) / (odds - 1)
   suggested_stake = bankroll × kelly_fraction / 4
   ```
   If Kelly ≤ 0 → SKIP (no edge).

### OUTPUT FORMAT
Save to: `betting/data/{date}_s5_odds_ev.md`

For each candidate:
```
## [Event] — [Recommended Market]

| Source | Odds | Line |
|--------|------|------|
| BetExplorer best | X.XX | [market] |
| OddsPortal best | X.XX | [market] |
| Betclic (est.) | X.XX | CONDITIONAL |
| Pinnacle | X.XX | [market] |

- **True probability estimate**: XX% (method: [Pinnacle implied / model / consensus])
- **Betclic odds (est.)**: X.XX (CONDITIONAL — verify on app)
- **EV**: +X.X% ✅ or -X.X% ❌
- **price_gap_pct**: X.X%
- **Line movement**: [stable / steaming / drifting] [direction]
- **Drift check**: analysis odds X.XX → current X.XX = X.X% change [OK/RE-EVAL]
- **1/4 Kelly**: X.XX PLN
- **VERDICT**: APPROVED / REJECTED (reason)
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S5-01**: Every candidate has odds from ≥2 sources
- [ ] **V-S5-02**: EV calculated for every candidate (formula shown)
- [ ] **V-S5-03**: ALL rejected candidates have EV ≤ 0 or price_gap outside threshold
- [ ] **V-S5-04**: ALL approved candidates have EV > 0
- [ ] **V-S5-05**: price_gap_pct calculated and within threshold for risk tier
- [ ] **V-S5-06**: Betclic odds marked CONDITIONAL (since we can't scrape Betclic)
- [ ] **V-S5-07**: Line movement checked (opening vs current)
- [ ] **V-S5-08**: Drift > 8% flagged for re-evaluation
- [ ] **V-S5-09**: Kelly fraction calculated (positive for all approved picks)
- [ ] **V-S5-10**: No approved pick has only 1 odds source

### ERROR LOG
```
| Check | Status | Error | Fix |
|-------|--------|-------|-----|
```

### PASS/FAIL GATE
- ALL checks pass → "S5 PASSED" → proceed to S6/S7
