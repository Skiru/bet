# Betting Workflow

You are maintaining a disciplined small-bankroll betting workflow, not writing casual tipster content.

Operating rules:
- Daily bankroll cap is configurable via config/betting_config.json (default: use smart allocation). It is acceptable and preferred to leave part of the bankroll unused.
- Default execution bookmaker is Betclic. Use Betclic as the place where the bet would be placed, not as the main analytical source.
- Default local timezone is Europe/Warsaw.
- Define a betting day as 06:00 on run_date through 05:59 on the next local day. Use this window consistently for reports, ledgers, and settlement.
- Always settle the previous betting day before generating new picks for the current one.
- Never invent exact odds, lineups, injuries, suspensions, results, or source conclusions. If data is missing or conflicting, say so and downgrade or skip the selection.
- Follow the artifact schema in [betting-artifacts.instructions.md](instructions/betting-artifacts.instructions.md).
- Follow the source hierarchy in [source-registry.md](../betting/sources/source-registry.md).

Scripted workflow:
- Always run the repository scanner and aggregator before composing final coupons. Use the orchestrator script `bash scripts/run_full_scan_and_prepare.sh` (or follow the manual commands below) to install dependencies, run a Playwright smoke test, fetch pages, and produce `betting/data/scan_summary.json` and `betting/data/picks_suggested.json`.
- The orchestrator uses Playwright (headless Chromium) for JS-heavy pages. This is the primary fetching method — use it for all source data, not manual fetch_webpage calls.
- The orchestrator scans all configured sports (football, tennis, basketball, hockey, baseball) across all Tier A and Tier B sources with sport-specific subpages.
- The agent and prompts assume these structured outputs are present and up-to-date; if they are missing or stale, re-run the orchestrator and retry the run.
- After the orchestrator finishes, check `betting/data/scan_errors.json` for source failures. Record any failed sources in the daily source log.
- Use `python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD` to settle pending picks for a specific day. The script supports `--match "Team vs Team"` for targeted settlement and `--no-poll` for single-attempt mode.
- The settlement script auto-resolves: match winner/1X2, totals (any line), BTTS, and double chance. Markets like corners, cards, handicaps, and MyCombi require manual settlement.
- Never auto-push settled results to git. Verify first, then commit manually.

Selection rules:
- Analyze all sports configured in config/betting_config.json (football, tennis, basketball, hockey, baseball). Diversify across sports when the board supports it.
- Prefer statistical markets over raw winners: totals, team totals, both teams to score, double chance, draw no bet, spreads, handicaps, tennis set or game lines, basketball and baseball totals, corners, cards, fouls, and similar markets with clearer quantitative support.
- Use 1X2 or moneyline only when the edge is strong and the price is still acceptable.
- A final pick requires at least one Tier A stats or fixture source and one Tier A market or price source. Tier B opinion or consensus sources may support a pick but cannot be the main reason for it.
- If primary sources disagree materially or are unavailable, skip the pick.
- Prefer 0 to 3 singles over forcing accumulators.
- Never force both coupon variants. If the board is weak, produce a one-coupon day or a full no-bet day.
- Reject correlated legs in the same coupon, especially same-game and strongly linked narrative outcomes.
- Prefer multi-sport coupons over same-sport coupons when possible. Limit same-sport legs to 2 per coupon.

Price and risk rules:
- Compare Betclic odds against market-best odds from a comparison source.
- Calculate price_gap_pct as 100 * ((bookmaker_odds / market_best_odds) - 1).
- For low-risk selections, reject prices worse than -3%.
- For higher-risk selections, reject prices worse than -5% unless the report explicitly states why the price is still playable and stake is reduced.
- Recheck odds immediately before writing the final artifacts.
- Never stake more than 2.00 PLN on a single pick.
- Suggested daily allocation is 4 to 7 PLN across singles, up to 2 PLN on the low-risk coupon, up to 1 PLN on the higher-risk coupon, and the rest left unused if the board is weak.

Learning rules:
- Update the daily report, coupon file, picks ledger, coupons ledger, source log, and learning log on every run.
- On reruns for the same betting day, update existing records instead of duplicating them.
- Learning means process adjustments backed by settled results. Do not add emotional commentary and do not claim model retraining.