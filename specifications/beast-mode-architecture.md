# Beast Mode — Architecture & Impact Analysis

> **Status:** Default pipeline since 2026-05-12. Replaces all legacy HTML-scraping approaches.

## What Is Beast Mode?

Beast Mode is the **Sofascore REST API-first scanning pipeline** that replaced the old multi-source HTML-scraping approach. Instead of maintaining dozens of scraping adapters for different websites, Beast Mode uses a single structured API to discover and enrich ALL events across all 5 core sports.

## Legacy vs Beast Mode

| Aspect | Legacy Pipeline | Beast Mode |
|--------|----------------|------------|
| **Data Source** | Multiple websites (BetExplorer, Flashscore, Forebet, etc.) | Sofascore REST API |
| **Discovery** | Pre-configured URLs in `scan_urls.json` | API endpoint per sport — discovers ALL events |
| **Parsing** | HTML scraping with sport-specific adapters | Structured JSON responses |
| **Enrichment** | `html_deep_parser.py` per-page deep parsing | Per-event API calls: form, H2H, odds, stats |
| **Output Format** | `scan_summary.json` (dict keyed by URL) | `global_events_api.json` (flat list) |
| **Reliability** | Fragile — breaks when sites change HTML | Stable — structured API responses |
| **Coverage** | Limited to configured URLs | ALL events from Sofascore for all 5 sports |
| **Speed** | Depends on page load times | Concurrent API calls with rate limiting |

## How It Works

### Phase 1: Event Discovery
```
scan_events.py --date YYYY-MM-DD --verbose
```
- Calls `api.sofascore.com/api/v1/sport/{sport}/scheduled-events/{date}` for each of 5 sports
- Concurrent discovery (5 workers — one per sport)
- Returns normalized event list with: id, sport, tournament, country, teams, start_time
- Typical yield: **1500-2000 events per day**

### Phase 2: Deep Enrichment
For each discovered event, fetches 4 additional API endpoints:

| Endpoint | Data | Impact |
|----------|------|--------|
| `/event/{id}/pregame-form` | W/L/D sequences, league position, points | Form analysis for safety scoring |
| `/event/{id}/h2h` | Head-to-head record (wins, draws) | H2H market validation |
| `/event/{id}/odds/1/all` | ALL betting markets from multiple bookmakers | Direct odds for EV calculation |
| `/event/{id}/expected` | Pre-match statistical projections | Expected corners, shots, etc. |

**Priority enrichment** (v2): Events sorted by priority score before enrichment:
- Tournament matches (R7): +100 (Champions League, Grand Slams, NHL Playoffs, etc.)
- Protected leagues (R13): +80 (Premier League, MLS, Bundesliga, etc.)
- Sport weighting: Football +30, Basketball +25, Hockey +20, Volleyball +15, Tennis +10

### Phase 3: Ingest to Stats Cache
```
ingest_scan_stats.py --date YYYY-MM-DD --verbose
```
Transforms Beast Mode JSON into the standardized `stats_cache/` format + DB `team_form` table.

**Market extraction** (v2) — captures ALL Sofascore market types:
- **1X2 / Match Winner** (Full time)
- **BTTS** (Both Teams to Score — Yes/No)
- **Totals** (Over/Under goals, games, points)
- **Corners** (Corners 2-Way) — **R5 priority statistical market**
- **Cards** (Cards in match) — **R5 priority statistical market**
- **Double Chance** (1X, 12, X2)
- **Draw No Bet**
- **Asian Handicap**
- **Half-time** (1st and 2nd half)
- **Set Winner** (Tennis)
- **Period Markets** (Basketball quarters, Hockey periods)

### Phase 4: Build Shortlist
```
build_shortlist.py --date YYYY-MM-DD --stats-first --verbose
```

## Data Quality Profile (2026-05-12 Baseline)

| Sport | Events | Form | H2H | Odds | Notes |
|-------|--------|------|-----|------|-------|
| Football | 160 | 87% | 97% | 90% | Best coverage — all markets available |
| Basketball | 190 | 27% | 93% | 52% | Strong H2H, moderate form/odds |
| Tennis | 1316 | 0% | 11% | 14% | Weakest — form/H2H sparse |
| Hockey | 15 | 0% | 100% | 33% | Small sample, good H2H |
| Volleyball | 8 | 12% | 75% | 0% | Too few events for stats |

**Football market coverage** (the pipeline's core strength):
```
BTTS, Corners, Cards, Double Chance, Draw No Bet,
Half-time, Handicap, Totals — ALL extracted from a single API call
```

## Impact on Pipeline Quality

### Before Beast Mode (Legacy)
- 5-15 sources to maintain, each with custom adapters
- HTML structure changes broke scanning regularly
- Limited to pre-configured leagues/URLs
- No standardized odds extraction across sources
- Deep parsing took 30-60 minutes per source

### After Beast Mode
- **Single source** — one API, one adapter, one format
- **Universal coverage** — every event Sofascore tracks, all 5 sports
- **Deep enrichment** — form, H2H, odds, stats per event
- **13+ market types** extracted automatically (R5 compliance)
- **Priority-based enrichment** — tournaments and protected leagues first
- **Concurrent processing** — configurable workers for deep enrichment

## v2 Improvements (2026-05-12)

### scan_events.py
1. **Concurrent deep enrichment** — ThreadPoolExecutor with configurable workers (`--deep-workers N`)
2. **Thread-safe rate limiting** — Reserves time slots inside lock, sleeps outside (no deadlock)
3. **Per-thread sessions** — Each worker gets its own `requests.Session` (thread-safe)
4. **Priority-based enrichment** — Tournament/protected league events enriched first
5. **Statistics endpoint** — Fetches `/event/{id}/expected` for pre-match projections
6. **403 handling** — Non-retryable (immediate return, no wasted backoff)
7. **Zero-event protection** — Won't overwrite existing data on scan failure
8. **Correct timezone** — Uses `zoneinfo.ZoneInfo("Europe/Warsaw")` instead of hardcoded UTC+2
9. **Richer AGENT_SUMMARY** — Per-sport enrichment depth, form/H2H/odds/stats breakdown

### ingest_scan_stats.py
1. **Full market extraction** — 13+ market types from Sofascore odds (BTTS, corners, cards, DC, DNB, HC, HT, 2ndHT, sets, periods)
2. **Fractional odds parsing** — Converts "5/4" → 2.25 decimal, validates ≥ 1.0
3. **Form data preservation** — Extracts league position, points, label from pregame-form
4. **Expected stats passthrough** — Sofascore pre-match projections flow to stats_cache
5. **2nd half markets** — No longer silently dropped (BUG 10 fix)
6. **Market type tracking** — Summary shows which market categories were extracted per sport

## CLI Reference

```bash
# Full scan with deep enrichment (default: 3 workers)
.venv/bin/python scripts/scan_events.py --date 2026-05-12 --verbose

# Custom worker count
.venv/bin/python scripts/scan_events.py --date 2026-05-12 --deep-workers 5 --verbose

# Limit deep enrichment to top N priority events
.venv/bin/python scripts/scan_events.py --date 2026-05-12 --deep-limit 500 --verbose

# Skip deep enrichment (fast scan, discovery only)
.venv/bin/python scripts/scan_events.py --date 2026-05-12 --skip-deep --verbose

# Single sport scan
.venv/bin/python scripts/scan_events.py --date 2026-05-12 --sport football --verbose

# Ingest with market extraction
.venv/bin/python scripts/ingest_scan_stats.py --date 2026-05-12 --verbose

# Dry-run ingest
.venv/bin/python scripts/ingest_scan_stats.py --date 2026-05-12 --dry-run --verbose
```

## Known Limitations

1. **Tennis form data** — Sofascore's pregame-form endpoint returns sparse data for tennis (0% coverage). Tennis enrichment relies on H2H and odds only.
2. **Rate limiting** — Sofascore may 403-block IPs during heavy scanning. The pipeline handles this gracefully but enrichment depth is reduced.
3. **No lineup data** — Sofascore has a lineups endpoint but it's not yet integrated.
4. **No rankings data** — Tennis/basketball rankings available via API but not fetched.

## Files

| File | Role |
|------|------|
| `scripts/scan_events.py` | Beast Mode scan engine — discovery + deep enrichment |
| `scripts/ingest_scan_stats.py` | Transform Beast Mode JSON → stats_cache + DB |
| `scripts/beast_mode_pipeline.py` | **DEPRECATED** — V1 football-only prototype |
| `betting/data/global_events_api.json` | Beast Mode output — flat list of all events |
| `tests/test_beast_mode_improvements.py` | 28 unit tests for v2 improvements |
