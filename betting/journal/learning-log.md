# Learning Log

Rules:
- Append only.
- Record process changes, not emotions.
- Tie every rule change to settled results, source reliability, or repeated pricing issues.
- Keep entries short.

Template:

## YYYY-MM-DD
- Settlement summary:
- What worked:
- What failed:
- Rule changes for future runs:
- Source notes:

No entries yet.
## 2026-04-21
- Settlement summary: none — no picks settled from previous day.
- What worked: source stack availability check completed; Tier A sources accessible except execution bookmaker.
- What failed: Betclic execution price retrieval failed due to dynamic content or geo-blocking; recommend manual odds recheck when composing final picks.
- Rule changes for future runs: add explicit fallback step to recheck bookmaker odds via mobile or alternative access method before finalising picks.
- Source notes: mark Betclic as partial until execution-price endpoint accessible from run environment.
 - Deviation note: live AKO placed today with 2.00 PLN stake (outside default planned split). This was a deliberate one-off decision; resume normal workflow tomorrow.
 - Pre-system bets recorded: added several pre-system coupons from user screenshots into ledgers and report. These were reconciled into `picks-ledger.csv` and `coupons-ledger.csv` and marked `placed` where screenshot showed stake. Continue to require screenshot or bookmaker confirmation for any manual-entry bets.
 - Automated market scan note: attempted automated scan of OddsPortal, BetExplorer, Oddspedia, Flashscore and Sofascore for tonight's candidate lines. Scan was partially blocked by privacy/consent overlays and some endpoints returned errors; plan to use manual recheck for finalisation and add a fallback interactive-check step to the workflow.
- Settlement summary (update 2026-04-21 16:50): Settled 3 failed coupons recorded from user screenshots (tennis AKO + two pre-system AKOs). Total realised PnL: -7.00 PLN. Continue manual verification for coupon-level settlements when screenshot evidence is provided.
- What worked: quick reconciliation from user screenshots; monitor script ready for automated checks where accessible.
- What failed: some aggregator endpoints blocked; cannot rely solely on automated scanning for every bookmaker.
- Rule changes for future runs: accept screenshot-confirmed pre-system bets into ledgers as `placed` and settle only when a confirmed final-status screenshot or two Tier A settlement sources (Flashscore + Sofascore) confirm result.
- Source notes: User screenshots are an acceptable verification source when bookmaker confirmation is not accessible; record ref id and timestamp.
 - Bankroll update: user provided current balance 43.26 PLN. Workflow change: use available balance or configured bankroll as the working bankroll for the next runs (see config/betting_config.json).
 - Operational rule: place bets only that are recorded in the ledger; accept screenshot/bookmaker confirmation for manual entries and settle when two Tier A sources or bookmaker confirmation exist.

## 2026-04-22 (codebase audit)
- Settlement summary: no new settlements — codebase audit day.
- What worked: identified and fixed critical bugs across all scripts.
- What failed (fixed):
  - adapters/__init__.py: broken __import__() calls crashed the adapter system — replaced with proper Python imports.
  - site_selectors.json: invalid JSON (two concatenated objects) — merged into one valid JSON.
  - settle_on_finish.py: hardcoded to one match, operator precedence bug in match winner logic, hardcoded totals threshold at 3.5 — rewritten as generic settlement with dynamic line parsing, BTTS/DC support, CLI args, and coupon settlement.
  - aggregate_and_select.py: `or True` in market filter included all sources as market sources (bypassing Tier-A requirement); import inside loop; no config loading; no risk-tier differentiation — rewritten with proper Tier-A filtering, fuzzy match dedup, config-driven allocation, and risk tiers.
  - scan_events.py: no rate limiting between fetches, deprecated datetime.utcnow() — added 3s delay, error log output, progress counter.
  - fetch_with_playwright.py: deprecated datetime.utcnow(), no user-agent rotation — fixed timezone, added UA rotation and viewport/locale.
  - quick_betclic_extract.py: picked lowest-odds favorites instead of value — rewritten to prefer 1.30-3.50 range with source-count weighting.
  - requirements.txt: pinned playwright breaking upgrades — changed to >=1.45.0.
  - run_full_scan_and_prepare.sh: no error handling, no timing info — added pipeline steps, timing, error summary, graceful failure handling.
- Rule changes for future runs:
  - Use `settle_on_finish.py --betting-day YYYY-MM-DD` for targeted settlement instead of editing the script per match.
  - Check `betting/data/scan_errors.json` after every orchestrator run for source availability issues.
  - Config thresholds (price gap, max legs, odds range) are now in config/betting_config.json — change config not code.
- Source notes: all adapter domains now mapped in adapters/__init__.py (predictz, bettingexpert, zawodtyper, oddspedia, betexplorer added).