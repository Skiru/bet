# Betclic HTML Parser — Implementation Notes

## Created: 2026-05-13

### File
`scripts/parse_betclic_html.py` — S0.2 step in pipeline (runs after S0.1 warmup)

### What it does
Parses cached Betclic HTML pages (from `daily_odds_warmup.py`) into structured events + odds.
- **Listing pages** (`{date}_betclic_{sport}.html`): 20 events per page with teams, league, kickoff, 1X2/ML odds
- **Match detail pages** (`{date}_betclic_match_{sport}.html`): full market data with all selections and odds

### Key DOM selectors (verified against real HTML)
- Event card: `sports-events-event-card` (NOT `sports-events-skeleton` — skeleton = pre-render failure)
- Team names: `[data-qa="contestant-1-label"]` / `[data-qa="contestant-2-label"]`
- Odds buttons: `button[betbuttontype="odd"]` → `bcdk-bet-button-label.btn_label.is-top` (name) + `.btn_label` (odds)
- Team name split: `span.ellipsis` + `span.clip` — use `get_text(separator=" ")` to avoid "ManawatuJets"
- Kickoff: `.scoreboard_hour` (non-live) — NOT `.event_infoTime` (not found in actual HTML)
- Market count: `.event_betsNum` text like "+24"
- Match detail markets: `sports-markets-single-market` → `.marketBox_headTitle` + `.marketBox_lineSelection`

### Polish locale
- Comma decimals: `"8,25"` → `8.25` via `polish_decimal()`
- Full market name map: ~70 entries across 5 sports (Polish → English)
- Dynamic team-prefixed markets: `"{Team} Gole Powyżej/Poniżej"` → strip team, match base pattern
- O/U labels: `"Powyżej 2,5"` → `("Over", 2.5)`

### DB integration
- Uses existing repos: `FixtureRepo.upsert()`, `OddsRepo.save()`
- Bookmaker: `"betclic"`, source: `"betclic"`
- Re-run safe: `ON CONFLICT DO UPDATE` for fixtures, `INSERT OR IGNORE` for odds
- Per-event try/except so one bad record doesn't kill the batch

### Known limitations
- **Volleyball HTML often loads as skeleton** (Angular SPA pre-render) — 0 events, not a parser bug
- **Hockey has no cached listing page** — warmup target exists but no hockey events some days
- **Only 1 match detail page per sport** — warmup currently caches only 1 match detail per sport
- **Tennis listing may show all-live events** with minimal/no listing odds (Betclic suppresses odds on live listings)
- **Match detail cross-sport mismatch**: `_betclic_match_tennis.html` might contain a football match if warmup navigated wrongly

### Output
- JSON: `betting/data/betclic_parsed_{date}.json` — per-sport events + markets + totals
- DB: fixtures + odds_history tables
- AGENT_SUMMARY with verdict OK/PARTIAL/FAILED

### Pipeline position
```
daily_odds_warmup.py (S0.1) → HTML cache
parse_betclic_html.py (S0.2) → fixtures + odds in DB + JSON
build_shortlist.py (S1) + generate_market_matrix.py ← consume from DB
```
