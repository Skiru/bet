# Repo Workflow Notes

## Orchestrator is mandatory
- Always run `bash scripts/run_full_scan_and_prepare.sh` BEFORE analysis.
- It uses Playwright (headless Chromium) to fetch JS-heavy pages (OddsPortal, Betclic match pages, etc.)
- Do NOT use manual `fetch_webpage` as a substitute — Playwright handles cookies, consent popups, and JS rendering.

## Multi-sport scanning
- The orchestrator fetches sport-specific subpages for Flashscore, Betclic, OddsPortal (football, tennis, basketball, hockey, baseball).
- Config `sports` array in `config/betting_config.json` controls which sports are analyzed.
- Sport is detected from URL patterns and tagged on each extracted item.

## Tier A stats sources by sport
- Football: Flashscore, Sofascore
- Tennis: Flashscore, Sofascore, TennisAbstract
- Basketball/Baseball/Hockey: Flashscore, Sofascore, Covers, TeamRankings

## Market diversity
- Don't limit analysis to goals/1X2. Check: corners, cards, fouls, game totals (tennis), quarter totals (basketball), period totals (hockey), run lines (baseball).
- `config/betting_config.json` has a `market_types` dict per sport.

## Betclic sport URLs
- Football: betclic.pl/pilka-nozna-s1
- Tennis: betclic.pl/tenis-s2
- Basketball: betclic.pl/koszykowka-s4
- Hockey: betclic.pl/hokej-na-lodzie-s13
- Baseball: betclic.pl/baseball-s14
