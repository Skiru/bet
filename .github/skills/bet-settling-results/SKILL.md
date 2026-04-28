---
name: bet-settling-results
description: "Settlement procedures for betting results — PnL calculation rules (win/loss/push/void/half), CLV tracking, bankroll management (20% drawdown protection), historical learning query (per-market hit rates, coupon killer analysis, sport trends), and post-mortem protocols. Use when settling previous day's picks, updating bankroll, or analyzing historical betting performance."
user-invokable: false
---

# Settling Betting Results

Procedures for settling picks and coupons, tracking performance, and maintaining bankroll discipline.

## Settlement Execution

### Auto-Resolve Markets
Winner/1X2, totals (any line), BTTS, double chance — resolve from Flashscore + verify on Sofascore.

### Manual-Resolve Markets
Corners, cards, handicaps, MyCombi — require manual result lookup.

### US Sports Settlement
```bash
python3 scripts/fetch_odds_api.py --scores baseball,hockey
```

### Settlement Script
```bash
python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD
```
Supports: `--match "Team vs Team"`, `--no-poll`

## PnL Rules

| Status | PnL Formula |
|--------|-------------|
| win | `stake_pln × (odds - 1)` |
| loss | `-stake_pln` |
| push | `0` |
| void | `0` |
| half_win | `stake_pln × (odds - 1) / 2` |
| half_loss | `-stake_pln / 2` |
| pending | empty pnl_pln cell |

### Coupon Settlement
- Coupon WINS only if ALL legs win
- Any leg void/push → recalculate effective combined odds from remaining active legs, settle from adjusted price
- One leg loss → entire coupon is LOSS

## Allowed Statuses

**Picks:** pending, placed, win, loss, push, void, half_win, half_loss, superseded

**Coupons:** pending, win, loss, void, superseded

## CLV Tracking (Closing Line Value)

For each settled pick:
1. Record closing odds (just before kickoff) from OddsPortal/BetExplorer
2. Calculate: `CLV = (closing_implied_prob / placement_implied_prob) - 1`
   - Positive CLV = got better odds than closing = sharp behavior
   - Negative CLV = market moved against you = concerning
3. Track rolling average CLV
4. Consistently negative CLV → fundamental approach revision needed

## Bankroll Management

1. Update `working_bankroll_pln` in `config/betting_config.json`
2. Dropped >20% from peak → reduce daily exposure by 25%
3. Grew >30% from start → consider increasing daily range by 10-15%

## §0.2 Historical Learning Query (MANDATORY before scanning)

Query `picks-ledger.csv` AND `betting/data/betclic_bets_history.json` to extract actionable patterns. Takes 2 minutes, prevents repeating proven failures.

**§0.2a BETCLIC HISTORY (MANDATORY — NEVER SKIP)**
```
read_file: betting/data/betclic_bets_history.json
run: python3 scripts/analyze_betclic_learning.py
```
This file contains ALL actually placed bets from the Betclic account. It is the GROUND TRUTH. Always use the analyzer's live output for current stats — never rely on memorized numbers. Core patterns:
- Statistical markets consistently outperform outcome markets. Corners = top market.
- Match winner is the #1 coupon killer. DEMOTE ML.
- AKO(5+) near-zero win rate → MAX 4 legs. Sweet spot: AKO(2-3).
- UNDER direction outperforms OVER. Actively seek UNDER plays.
- High stakes (5+ PLN) have poor win rate. Keep stakes small.

**GATE: If `betclic_bets_history.json` is not read, §0.2 is INCOMPLETE. Do NOT proceed to STEP 1.**

1. **Per-market hit rate:** Group settled picks by `market`. Win% per market type. <40% on 10+ picks → AUTO-DOWNGRADE. <30% → WATCHLIST ONLY. Cross-reference with Betclic history market rates.
2. **Per-sport hit rate:** Group by `sport`. <30% on 5+ picks → FLAG (−1 confidence to all picks from that sport). NEVER blanket-reject on <5 picks. Cross-reference with Betclic history sport rates.
3. **Coupon failure analysis:** Each LOST coupon → identify the failed leg. Track "coupon killers." Cross-reference with Betclic §7 coupon killer analysis. If market/sport kills coupons >50% → exclude from LR coupons.
4. **Streak check:** Team/player appearing 3+ times → check if thesis is stale or edge priced in.
5. **Betclic cross-check:** Verify NO pick uses a market/sport combo with <30% hit rate in Betclic history (§8 cross-analysis).
6. **Write 3-line summary** of actionable findings.

## Post-Mortem Protocol

For EACH LOSS:
- **Bad thesis** (wrong analysis) vs **Variance** (correct thesis, unlucky)?
- What would you change in hindsight?
- Record in `betting/journal/learning-log.csv`

## Performance Metrics to Calculate

- Day PnL: sum(returns) − sum(stakes)
- Rolling 7-day PnL
- Per-league ROI: which leagues/sports produced profit vs loss
- Per-market win rate trends

## Connected Skills

- `bet-formatting-artifacts` — ledger CSV formats and field conventions for recording settlement data
- `bet-navigating-sources` — sources for verifying results (Flashscore, Sofascore, The-Odds-API --scores)
