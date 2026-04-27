---
name: s0-settlement
description: "STEP 0: Settle previous day, PnL, CLV, bankroll update, learning review"
agent: bet-analyst
---

# STEP 0 — SETTLE PREVIOUS DAY

## CONFIG
- **Today**: {{run_date}}
- **Previous betting day**: {{run_date}} - 1 day
- **Settlement window**: 06:00 yesterday → 05:59 today CEST
- **Settlement script**: `python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD`

## TASK
Settle ALL pending picks/coupons from the previous betting day. Update PnL, CLV, bankroll. Post-mortem losses.

### 0.1 — SETTLEMENT EXECUTION

1. **Run settlement script**: `python3 scripts/settle_on_finish.py --betting-day {yesterday}`
2. **For each pending pick**:
   - Find result on Flashscore → verify on Sofascore
   - Resolve market:
     - **Auto-resolve**: match winner (1X2), totals (any line), BTTS, double chance
     - **Manual resolve**: corners, cards, handicaps, MyCombi
   - Update `picks-ledger.csv` → status (won/lost/void/push), result, pnl_pln
3. **For each pending coupon**:
   - Coupon WINS only if ALL legs win
   - Any leg void → recalculate combined odds without that leg
   - Update `coupons-ledger.csv` → status, pnl_pln
4. **For US sports settlement**: use `python3 scripts/fetch_odds_api.py --scores baseball,hockey`

### §0.2 — HISTORICAL LEARNING QUERY (MANDATORY before scanning)

Before STEP 1, query the picks-ledger to extract actionable patterns. This takes 2 minutes and prevents repeating proven failures.

1. **Per-market hit rate:** Group settled picks by `market` column. Calculate win% per market type (e.g., corners: 75%, ML: 40%, BTTS: 55%). Any market <40% on 10+ picks → AUTO-DOWNGRADE (STEP 5 rule). Any market <30% → WATCHLIST ONLY.
2. **Per-sport hit rate:** Group by `sport`. Any sport with <30% hit rate on 5+ picks → FLAG. Scan that sport but apply −1 confidence to all picks from it.
3. **Coupon failure analysis:** For each LOST coupon, identify the leg that failed. Track which pick types are the "coupon killers." If a specific market/sport kills coupons >50% of the time → exclude from LR coupons.
4. **Streak check:** Any team/player appearing 3+ times in recent picks? Check if the thesis is stale or if the edge has been priced in.
5. **Write a 3-line summary** of what the data says today. Example: "Corners 6/8 (75%). Tennis ML 1/5 (20%) — avoid. Hockey totals killing coupons — HR only."
6. **Previous-day PnL**: sum(returns) - sum(stakes)
7. **Rolling 7-day PnL**: sum of last 7 days
8. **Per-league ROI**: which leagues/sports produced profit vs loss
5. **Post-mortem EACH LOSS**:
   - Was the thesis WRONG (bad analysis) or did VARIANCE hit (correct thesis, unlucky)?
   - What would you change in hindsight?
   - Record in learning log

### 0.3 — CLV TRACKING (Closing Line Value)

For each settled pick:
1. Record closing odds (odds just before kickoff) from OddsPortal/BetExplorer
2. Calculate CLV: `(closing_implied_prob / placement_implied_prob) - 1`
   - Positive CLV = you got better odds than closing = sharp behavior
   - Negative CLV = market moved against you = concerning
3. Track rolling average CLV
4. If CLV consistently negative → fundamental approach revision needed

### 0.4 — BANKROLL UPDATE

1. Update `working_bankroll_pln` in `config/betting_config.json`
2. If bankroll dropped >20% from peak → reduce daily exposure by 25%
3. If bankroll grew >30% from start → consider increasing daily range by 10-15%

### 0.5 — LEARNING REVIEW

1. Read `betting/journal/learning-log.csv` last 3 entries
2. Read Zero Tolerance Shield in agent config — any new patterns?
3. Check previous day's error patterns — are we repeating mistakes?
4. Apply any rule changes from settled results to today's analysis

### OUTPUT FORMAT
Save to: `betting/data/{date}_s0_settlement.md`

```
# Settlement — {yesterday}

## Settled Picks
| Pick ID | Event | Market | Status | Score | PnL |
|---------|-------|--------|--------|-------|-----|
...

## Settled Coupons
| Coupon ID | Legs | Status | PnL |
|-----------|------|--------|-----|
...

## Performance
- Previous day PnL: X.XX PLN
- Rolling 7-day PnL: X.XX PLN
- Bankroll before: X.XX PLN → Bankroll after: X.XX PLN

## Per-Market Hit Rates (updated)
| Market Type | Hits | Misses | Rate |
|------------|------|--------|------|
...

## Per-Sport ROI (last 7 days)
| Sport | Picks | Won | Lost | ROI% |
|-------|-------|-----|------|------|
...

## CLV Summary
| Pick | Analysis Odds | Closing Odds | CLV |
|------|--------------|-------------|-----|
...
- Average CLV: X.X%

## Post-Mortem (losses only)
| Pick | What Happened | Bad Thesis or Variance? | Lesson |
|------|--------------|------------------------|--------|
...

## Learning Review
- Lessons from last 3 days: [bullets]
- Zero Tolerance patterns matched: [none / list]
- Rule changes for today: [bullets]
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S0-01**: Every pending pick from previous day resolved (won/lost/void/push)
- [ ] **V-S0-02**: Every pending coupon resolved
- [ ] **V-S0-03**: picks-ledger.csv updated with results and pnl
- [ ] **V-S0-04**: coupons-ledger.csv updated with results and pnl
- [ ] **V-S0-05**: PnL calculated (not estimated — actual math)
- [ ] **V-S0-06**: Bankroll updated in config/betting_config.json
- [ ] **V-S0-07**: Post-mortem written for each loss (bad thesis vs variance)
- [ ] **V-S0-08**: CLV calculated for picks where closing odds available
- [ ] **V-S0-09**: Learning log reviewed — no repeating mistakes
- [ ] **V-S0-10**: Rolling 7-day PnL calculated

### PASS/FAIL GATE
- ALL checks pass → "S0 PASSED" → proceed to S1
- If no picks to settle (first run or NO BET day) → note "NO SETTLEMENT NEEDED" → proceed
