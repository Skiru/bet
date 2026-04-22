# Bet Project — Key Facts

## Architecture
- Orchestrator: `scripts/run_full_scan_and_prepare.sh` → smoke_playwright → scan_events → aggregate_and_select
- Config: `config/betting_config.json` — all thresholds and limits
- Adapters: `scripts/adapters/` — domain-specific HTML parsers, fallback to raw_adapter
- Settlement: `scripts/settle_on_finish.py --betting-day YYYY-MM-DD [--match "..."] [--no-poll]`
- Quick picks: `scripts/quick_betclic_extract.py` — standalone Betclic + Flashscore/Sofascore check

## Outputs
- `betting/data/scan_summary.json` — all extracted matches per source URL
- `betting/data/picks_suggested.json` — aggregated candidates + auto-selected picks
- `betting/data/scan_errors.json` — source failures (check after every run)
- `betting/data/<domain>/structured_latest.json` — per-source latest extraction

## Known Limitations
- Adapters are HTML-heuristic based; JS-heavy sites (Flashscore, Sofascore, Betclic) may return minimal data without Playwright
- Privacy/consent overlays block some sources (OddsPortal, BetExplorer) even with cookie selectors
- Settlement search via HTML scraping is fragile; prefer manual verification for non-trivial markets
- Fuzzy matching in aggregator uses SequenceMatcher at 0.75 threshold — may merge distinct teams with similar names

## Conventions
- Timezone: Europe/Warsaw, betting day 06:00–05:59
- IDs: PK-YYYYMMDD-##, CP-YYYYMMDD-LR/HR
- CSV pipe-separated multi-values
- All amounts in PLN with dot decimals
