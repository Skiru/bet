# Betting Workflow

You are maintaining a disciplined small-bankroll betting workflow, not writing casual tipster content.

## Core Rules
- Config source of truth: `config/betting_config.json` (bankroll, daily cap, sports, thresholds).
- Execution bookmaker: Betclic. All picks CONDITIONAL — user verifies on app. DO NOT scrape Betclic (403).
- Timezone: Europe/Warsaw. Betting day: 06:00 today → 05:59 tomorrow.
- Always settle previous day before generating new picks.
- Never invent odds, lineups, injuries, results, or source conclusions.
- **KEY sports (Tier 1):** Football, Volleyball, Basketball, Tennis — scan ALL leagues/divisions deeply.
- **SUPPORT sports (Tier 2):** All others — scan main leagues, still fully analyzed per candidate.
- **Coupon output = core portfolio + COMBO MENU.** Core = unique event per coupon. Combos = extra combinations remixing picks. User picks from both.
- Follow [analysis-methodology.instructions.md](instructions/analysis-methodology.instructions.md) (STEPS 0-10, V1-V10).
- Follow [betting-artifacts.instructions.md](instructions/betting-artifacts.instructions.md) (output formats).
- Follow [source-registry.md](../betting/sources/source-registry.md) (source hierarchy, fallback chains).
- Load [sport-analysis-protocols.instructions.md](instructions/sport-analysis-protocols.instructions.md) when doing STEP 3+ analysis.

## Scripted Workflow
```
# 1. Scan sources (Playwright + adapters)
bash scripts/run_full_scan_and_prepare.sh
# → produces: betting/data/scan_summary.json, picks_suggested.json, scan_errors.json

# 2. Cross-validation odds (30 credits/scan, 500/month free)
python3 scripts/fetch_odds_api.py
# → produces: betting/data/odds_api_snapshot.json, odds_api_summary.csv
# For settlement: python3 scripts/fetch_odds_api.py --scores baseball,hockey

# 3. Settle previous day
python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD
# Auto: winner/1X2, totals, BTTS, DC. Manual: corners, cards, HC, MyCombi.
# Supports: --match "Team vs Team", --no-poll
```
- Never auto-push settled results. Verify first, commit manually.
- Always prepare backup picks (Watch List) for when Betclic odds are unacceptable.

## Source Rules
- American odds: +X → 1 + X/100; −X → 1 + 100/X (for SBR, ESPN, ScoresAndOdds).
- US sports: SBR Totals + ESPN Odds + ScoresAndOdds (3 sources).
- EU sports: BetExplorer + OddsPortal + The-Odds-API (fallback).

## Versioning
- On reruns: increment version (v5→v6). Mark old pending as `superseded`. Keep all versions.
- Learning log: process changes only, tied to settled results. Max 3 rule changes per entry.
