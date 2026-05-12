# Adapter Enrichment & Source Registry Overhaul — 2026-05-12

## What Changed

### Broken API Clients Disabled (3)
- **TheSportsDB**: `_HOST_BROKEN = True`, free tier key "3" has 97.8% fail rate. Removed from fallback chains.
- **BallDontLie**: `_HOST_BROKEN = True`, v1 API deprecated/paywalled, 100% fail rate. Removed from fallback chains.
- **API-Tennis**: `_HOST_BROKEN = True`, v1.tennis.api-sports.io NXDOMAIN (host gone). Removed from fallback chains.

### Adapter Standard Schema Enrichment (6 adapters updated)
All adapters now emit standard field names (`home`, `away`, `time`, `league`, `source_type`, `source_url`, `raw`):
- `covers_adapter.py` — added American→decimal odds conversion, standard fields
- `basketball_reference_adapter.py` — standard fields, sport="basketball", league="NBA"
- `hockey_reference_adapter.py` — standard fields, sport="hockey", league="NHL"
- `soccerway_adapter.py` — fixed score-in-odds bug (now separate `score` field, `odds=None`), added `match_url` extraction
- `whoscored_adapter.py` — restructured raw `stats` dict into `corners`/`shots` sub-dicts
- `oddsportal_adapter.py` — odds dict now uses `w1/x/w2` keys (was `home_win/draw/away_win`), added `_detect_sport()`, merged `odds_structured` into `odds`

### Ingest Pipeline Updated
- `ingest_scan_stats.py` — now extracts enriched fields (corners, cards, fouls, shots, standings, predictions, dangerous_attacks) from events, passes as `enriched` dict to `_ingest_team_side()`, maps home/away data to scan_stats keys (corners_per_game, yellow_cards_per_game, etc.)

### ESPN Fix
- `src/bet/api_clients/espn.py` — fixed `competition_name` extraction crash when `season.type` is not a dict

### Source Registry Updated
- `betting/sources/source-registry.md` — 3 broken sources documented, fallback chains corrected, daily budget table updated

### Fallback Chains (current)
```
Football:     ESPN → API-Football → Football-Data.org → Understat → SerpAPI
Basketball:   ESPN → API-Basketball → SerpAPI
Hockey:       ESPN → API-Hockey → SerpAPI
Tennis:       ESPN → SerpAPI
Volleyball:   ESPN-Volleyball → API-Volleyball → SerpAPI
```

### New Test Scripts
- `scripts/_live_test_adapters.py` — tests all adapters + API clients against real URLs
- `scripts/_live_test_ingest_pipeline.py` — end-to-end: adapter → normalizer → ingest → cache
- `scripts/_test_sources.py` — HTTP reachability test for all known source URLs

### Research
- `specifications/playwright-scraping-research/` — comprehensive research on new deep-data sources per sport, Playwright library comparison, gap analysis

## Live Test Results (2026-05-12)

### API Clients: 17 tested
- 9 AVAILABLE (api-football, api-basketball, api-hockey, api-volleyball, football-data-org, nba-api, odds-api-io, serpapi, understat)
- 3 CORRECTLY_BROKEN (thesportsdb, balldontlie, api-tennis)
- 5 ESPN clients working (football=23, basketball=4, hockey=2, tennis=594 events)

### Scan Adapters: 12 tested
- 9 working: sofascore(80), betexplorer(235), flashscore(146), totalcorner(158), soccerway(263), covers(86), soccerstats(71), basketball-reference(2), hockey-reference(2)
- 3 blocked by anti-bot: forebet, oddsportal, whoscored

### Full Pipeline Integration: PASS
- totalcorner → normalizer → ingest → cache: `corners_per_game` written successfully

## Test Suite
- 487 passed, 1 pre-existing failure (test_extract_team_stats_with_cache assertion mismatch, unrelated to our changes)

## Lessons Learned
- Normalizer in `adapters/__init__.py` is the single point of schema enforcement — all adapters flow through it
- `update_cache()` in `build_stats_cache.py` has its own CACHE_DIR — can't redirect via `ingest_scan_stats.CACHE_DIR`
- ESPN returns HTTP 400 for leagues without games on a given date — noisy but not broken
- Anti-bot sites (forebet, oddsportal, whoscored) need stealth Playwright config; basic headless doesn't work
