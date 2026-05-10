---
agent: "bet-settler"
description: "S0: Settle previous day's picks/coupons, PnL, CLV, bankroll update, learning review"
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R2 DB-FIRST: Read/write via `get_db()`. R6 BETCLIC ADVISORY: Settlement analysis is INFORMATIONAL — show hit rates, NEVER auto-reject markets/sports.

# S0 — SETTLE PREVIOUS DAY

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` for every complex settlement (multi-leg coupons, partial wins, voids)
2. Read `/memories/repo/pipeline-lessons-learned.md` before starting — check for known settlement errors
3. Use `todo` to track each pending pick/coupon through resolution
4. Use `askQuestions` when results are ambiguous (abandoned matches, extra time)
5. Write new patterns to `/memories/session/` after settlement
6. Self-validate ALL arithmetic before returning

## Required Skills

Load these skills before starting:
- `bet-settling-results` — settlement execution, PnL rules, CLV tracking, bankroll management, learning query
- `bet-formatting-artifacts` — ledger CSV formats, pick/coupon ID conventions

## Context (provided by orchestrator)

- **run_date**: The current betting day
- **Previous betting day**: run_date - 1 day
- **Settlement window**: 06:00 yesterday → 05:59 today CEST
- **Settlement script**: `python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD`
- **Betclic history**: `betting/data/betclic_bets_history.json` (MANDATORY read)

## Workflow

### 1. Settlement Execution (§0.1)

1. Run `python3 scripts/settle_on_finish.py --betting-day {yesterday}`
2. For each pending pick: find result (Flashscore → verify Sofascore), resolve market (auto: 1X2/totals/BTTS/DC; manual: corners/cards/HC/MyCombi), update `picks-ledger.csv`
3. For each pending coupon: all legs win = coupon win; void leg = recalculate odds; update `coupons-ledger.csv`
4. US sports: `python3 scripts/fetch_odds_api.py --scores hockey`

### 2. Historical Learning Query (§0.2 — MANDATORY)

Before STEP 1 of the next day, extract actionable patterns:
1. Per-market hit rate (group by `market` column, flag <40% on 10+ picks, ⚠️ <30%)
2. Per-sport hit rate (flag <30% on 5+ picks — ADVISORY, never auto-downgrade)
3. Coupon failure analysis (identify coupon killers — ADVISORY)
4. Streak check (same team/player 3+ times recently)
5. Write 3-line summary
6. Previous-day PnL, rolling 7-day PnL, per-league ROI
7. Post-mortem EACH LOSS (bad thesis vs variance)

**Run**: `python3 scripts/analyze_betclic_learning.py` (reads `betclic_bets_history.json`)

### 3. CLV Tracking (§0.3)

For each settled pick: closing odds → `CLV = (closing_implied_prob / placement_implied_prob) - 1`

### 4. Bankroll Update (§0.4)

Update `working_bankroll_pln` in config. >20% drawdown → reduce exposure 25%. >30% growth → consider +10-15%.

### 5. Learning Review (§0.5)

Read last 3 learning-log entries. Check Zero Tolerance Shield. Apply rule changes.

## Output

Save to: `betting/data/{date}_s0_settlement.md`

Sections: Settled Picks table, Settled Coupons table, Performance summary, Per-Market Hit Rates, Per-Sport ROI, CLV Summary, Post-Mortem, Learning Review.

## Self-Verification (V-S0-01 to V-S0-10)

All 10 checks from §0 must pass. See `bet-settling-results` skill for full checklist.

## Pass/Fail Gate

ALL checks pass → "S0 PASSED" → orchestrator proceeds to S1.

<!-- BET:internal-prompt:bet-settle:v1 -->
