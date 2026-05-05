---
description: "Ask any betting question — routes to the right specialist agent via the orchestrator. Use for questions, actions, and status checks."
agent: bet-orchestrator
argument-hint: "Ask any betting question, e.g. 'what is the current bankroll?'"
---

# ASK BETTING

Route this user message to the appropriate specialist agent.

## USER MESSAGE

{{input}}

## INSTRUCTIONS

1. Classify the intent of the user message (QUESTION / ACTION / STATUS).
   - This is NOT a pipeline invocation — do NOT enter S0→S8 mode.
2. Discover current session state (date, version, pipeline progress, last settlement).
3. Match the message against the knowledge domain map and delegate to the appropriate specialist agent:
   - **Settlement/PnL/bankroll** → bet-settler (use `.github/internal-prompts/bet-settle.prompt.md`)
   - **Scanning/fixtures/events** → bet-scanner (use `.github/internal-prompts/bet-scan.prompt.md`)
   - **Statistics/safety scores/H2H** → bet-statistician (use `.github/internal-prompts/bet-deep-stats.prompt.md`)
   - **Tipsters/consensus** → bet-scout (use `.github/internal-prompts/bet-tipsters.prompt.md`)
   - **Odds/EV/pricing** → bet-valuator (use `.github/internal-prompts/bet-odds-ev.prompt.md`)
   - **Context/upset risk/gate** → bet-challenger (use `.github/internal-prompts/bet-gate.prompt.md`)
   - **Coupons/portfolio/validation** → bet-builder (use `.github/internal-prompts/bet-portfolio.prompt.md`)
4. For STATUS: answer directly from artifacts.
5. For QUESTION/ACTION: delegate to the matched specialist agent with context files and session state.
6. For multi-domain messages: follow the multi-domain triage protocol (max 2 agent calls).
7. Return the specialist's answer to the user.

## DATA SOURCES AVAILABLE

When answering questions, check these sources in order of freshness:
- **SQLite DB**: `betting/data/betting.db` — 14-table schema (events, picks, coupons, odds_snapshots, gate_results, etc.). Query for structured data.
- **Flat files**: `betting/data/` — scan summaries, market matrices, deep stats, analysis pools, weather data
- **Ledgers**: `betting/journal/picks-ledger.csv`, `coupons-ledger.csv`, `source-log.csv`, `learning-log.csv`
- **Config**: `config/betting_config.json` — bankroll, daily cap, sports, thresholds, db_path
- **Betclic history**: `betting/data/betclic_bets_history.json` — real placed bets (run `python3 scripts/analyze_betclic_learning.py` for analysis)
- **Coupons**: `betting/coupons/` — versioned coupon files per day
- **Reports**: `betting/reports/` — daily reports
- **Pipeline state**: `betting/data/pipeline_state_{date}.json` — step-by-step progress with timestamps
- **Probability engine**: `scripts/probability_engine.py` — Poisson/NegBin with bootstrap CI, multi-line optimization, Bayesian league priors, weather modifiers, tennis Elo
