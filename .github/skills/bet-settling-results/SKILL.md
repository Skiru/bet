---
name: bet-settling-results
description: "Settlement procedures for betting results — PnL calculation rules (win/loss/push/void/half), CLV tracking, bankroll management (20% drawdown protection), historical learning query (per-market hit rates, coupon killer analysis, sport trends), and post-mortem protocols. Use when settling previous day's picks, updating bankroll, or analyzing historical betting performance."
user-invokable: false
---

# Settling Betting Results

Procedures for settling picks and coupons, tracking performance, and maintaining bankroll discipline.

## Settlement Execution

### Auto-Resolve Markets
Winner/1X2, totals (any line), BTTS, double chance — resolve from Flashscore + verify on ESPN.

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
- Historical observation (ADVISORY): Match winner has been the #1 coupon killer historically. Flag ML picks prominently for user.
- AKO(5+) near-zero win rate → MAX 4 legs. Sweet spot: AKO(2-3).
- Historical observation (ADVISORY): UNDER direction has historically outperformed OVER. Show this trend to user.
- Historical observation (ADVISORY): High stakes (5+ PLN) have historically had poor win rate. Show this trend to user.

**GATE: If `betclic_bets_history.json` is not read, §0.2 is INCOMPLETE. Do NOT proceed to STEP 1.**

1. **Per-market hit rate:** Group settled picks by `market`. Win% per market type. Show all rates in report. **ADVISORY ONLY** — NEVER auto-reject, auto-downgrade, or auto-exclude any market. Cross-reference with Betclic history market rates for user awareness.
2. **Per-sport hit rate:** Group by `sport`. Show all rates in report. **ADVISORY ONLY** — NEVER blanket-reject or apply automatic confidence penalties. Cross-reference with Betclic history sport rates for user awareness.
3. **Coupon failure analysis:** Each LOST coupon → identify the failed leg. Track "coupon killers." Cross-reference with Betclic §7 coupon killer analysis. Show coupon killer data in report — do NOT auto-exclude from any coupon tier.
4. **Streak check:** Team/player appearing 3+ times → check if thesis is stale or edge priced in.
5. **Betclic cross-check (ADVISORY):** Show all market/sport hit rates from Betclic history in the report. **NEVER auto-reject any market/sport combination.** Full analysis is mandatory for every candidate.
6. **Write 3-line summary** of advisory findings for user decision-making.

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

- `bet-formatting-artifacts` — Ledger CSV formats and pick/coupon ID conventions used during settlement
- `bet-analyzing-statistics` — Historical hit rates from settlement feed back into §3.0 market ranking confidence
- `bet-navigating-sources` — Result verification sources (Flashscore, ESPN scores)
