# Betclic Market Scraper — Implementation Notes (completed 2026-05-18)

## Architecture
- Module: `src/bet/scrapers/betclic.py` (~600 lines)
- Validation script: `scripts/validate_betclic_markets.py`
- DB tables: `betclic_markets` (per-event observations), `betclic_competition_profiles` (aggregated)
- Schema: migration `010_betclic_markets.sql` (DB version 10)
- Uses curl_cffi with `impersonate='chrome110'` (same pattern as flashscore.py)
- Extracts from SSR-rendered Angular script tags (NO JS execution needed)

## Key Classes
- **`BetclicSession`** — HTTP layer with retries, rate limiting (1s/req), session cookies
- **`BetclicMarketChecker`** — High-level API: discovers events per sport/competition, checks market availability, persists to DB, validates coupon picks
- **`BetclicMarketInfo`** — Data class per event: tabs, market names, match metadata, `is_market_available(type)` → (bool|None, explanation)

## Key Discovery: Statystyki Tab = TIME-DEPENDENT
- **≤48h before kickoff**: Full markets (300-600 total), Statystyki tab present → corners/cards/shots/fouls available
- **>48h before kickoff**: Basic markets only (140-150 total), no Statystyki tab
- **Implication**: Validation MUST run on betting day, not earlier
- **Threshold**: openMarketCount ≥ 200 → statistical markets likely available

## Page Structure
- Match pages: `https://www.betclic.pl/{sport-slug}/{comp-slug}-c{id}/{teams}-m{event_id}`
- Market data in `<script>` tag #6 (~500K chars, Angular serialized state)
- Regex extraction: `"marketId":"(\d+)","marketName":"([^"]+)"`
- Tabs extracted from HTML: `class="tab_label"[^>]*>([^<]+)`

## Market Availability Rules
| Competition | Statystyki Tab | Corners | Cards | Shots | Fouls |
|---|---|---|---|---|---|
| PL/EL/CL (≤48h) | ✅ | ✅ | ✅ | ✅ | ✅ |
| DFB Pokal | ❌ (even match day) | ❌ | ❌ | ❌ | ❌ |
| Hockey (ALL) | ❌ NEVER | ❌ | ❌ | ❌ | ❌ |
| Minor leagues | ❌ | ❌ | ❌ | ❌ | ❌ |
| Basketball | Different page structure (no market script) | ? | ? | ? | ? |

## URL Patterns (Sport Slugs)
- football: `pilka-nozna-sfootball`
- tennis: `tenis-stennis`
- basketball: `koszykowka-sbasketball`
- volleyball: `siatkowka-svolleyball`
- hockey: `hokej-sice_hockey`

## Competition Registry (38 competitions)
Stored in `COMPETITION_REGISTRY` dict in betclic.py. Key IDs:
- Premier League: c3, La Liga: c4, Bundesliga: c5, Serie A: c6, Ligue 1: c7
- Champions League: c1, Europa League: c3453, Conference League: c18942
- Ekstraklasa: c221, Eredivisie: c11, Liga Portugal: c12
- NBA: c3, NHL: c3, ATP: c1, WTA: c4
- Hockey WC: c108, Allsvenskan: c13, Romania Liga 1: c16

## Pipeline Integration
1. **Pre-coupon validation**: `validate_betclic_markets.py --date X --validate-coupon coupon.md`
2. **Output**: `betting/data/betclic_market_validation_{date}.json`
3. **Coupon builder reads**: `coupon_builder.py` loads validation JSON → sets `coupons_data["betclic_market_validation"]`
4. **Markdown output**: "⚠️ WALIDACJA RYNKÓW BETCLIC" section with unavailable/unknown/available tables

## DB Persistence
- `betclic_markets`: 19 columns (sport, competition, event, tabs, market count, has_statistics_tab, detected markets JSON, checked_at)
- `betclic_competition_profiles`: 15 columns (sport, competition, typically_has_statistics, avg_open_markets, observations_count)
- Connection: Direct `sqlite3.connect()` + `_configure_connection()` (NOT get_db() context manager — long-lived)
- Profiles auto-aggregated on each save (running averages)

## Rate Limiting
- 1 second between requests (BetclicSession enforced)
- ~20-30 events shown per sport/competition listing page
- Full scan of 5 sports (12 events each) = ~54 seconds
- Competition-specific pages supplement sport listings for major leagues

## CLI Usage
```bash
# Full scan + coupon validation
PYTHONPATH=src .venv/bin/python3 scripts/validate_betclic_markets.py --date 2026-05-18 --validate-coupon betting/coupons/2026-05-18.md --verbose

# Single event check
PYTHONPATH=src .venv/bin/python3 -m bet.scrapers.betclic --event-url "https://www.betclic.pl/..." --verbose

# Competition scan
PYTHONPATH=src .venv/bin/python3 -m bet.scrapers.betclic --competition football/premier-league --verbose
```

## E2E Test Results (2026-05-18)
- 43 events scanned, 9 stored to DB, 3 competition profiles updated
- 385 coupon picks validated: 4 available, 17 unavailable, 364 unknown
- Premier League profile: `typically_has_statistics=1`, `avg_open_markets=254` (8 observations)
- Hockey/basketball/minor leagues: correctly profiled as `typically_has_statistics=0`
