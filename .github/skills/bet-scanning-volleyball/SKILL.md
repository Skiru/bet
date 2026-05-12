---
name: bet-scanning-volleyball
description: "Volleyball-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Volleyball

## Source URLs

Scanner loads URLs from `config/scan_urls.json` → `sports.volleyball.urls` (43 URLs as of 2026-05-12). Falls back to 17 hardcoded URLs if config is missing. Key source categories:

| Category | Examples | Count |
|----------|---------|-------|
| FlashScore league pages | PlusLiga, SuperLega, Bundesliga, Ligue A, Efeler Ligi, CEV Champions League, Nations League, World Championship | ~30 |
| FlashScore women | Tauron Liga, Serie A1 Women, Sultanlar Ligi, CEV CL Women | ~8 |
| FlashScore Asia/South America | J-League, V-League (KOR/JPN), CSL, Superliga Brazil, Liga A1 Argentina | ~6 |
| Odds sources | BetExplorer, OddsPortal, Betclic | 3 |
| Deep data | Scores24, Forebet | 2 |
| API-based | Sofascore REST API | 1 |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields | Volleyball-Specific |
|--------|---------|----------------------|---------------------|
| flashscore.com | `flashscore_adapter` | home, away, time, league, sport, match_id, match_url, period_scores, status | `volleyball.sets_won_home/away`, `volleyball.total_points` from period scores |
| sofascore.com | `sofascore_adapter` | home, away, time, league, sport, match_id, match_url | `match_url` → `api.sofascore.com/api/v1/event/{id}/statistics` |
| betexplorer.com | `betexplorer_adapter` | home, away, time, league, odds | — |
| oddsportal.com | `oddsportal_adapter` | odds (2-way: w1, w2) | — |
| scores24.live | `scores24_adapter` | H2H, form, trends, odds | `volleyball` stats: aces, blocks, kills, digs, assists |
| forebet.com | `forebet_adapter` | predictions (probabilities), match_url | — |
| espn (API) | `espn` client (registered as `espn-volleyball`) | fixtures, stats via FIVB leagues | VOLLEYBALL_STAT_MAP: kills, aces, blocks, digs, assists, errors, hitting_pct, points |

## Normalized Volleyball Schema

The adapter normalizer (`scripts/adapters/__init__.py`) includes volleyball-specific fields:

```python
"volleyball": {
    "sets_won_home": None, "sets_won_away": None,
    "total_points": None, "kills": None, "aces": None,
    "blocks": None, "digs": None, "assists": None,
    "errors": None, "hitting_pct": None, "attack_pct": None,
    "service_errors": None,
}
```

Adapters emit `event["volleyball"] = {...}` → normalizer merges into standard schema.

## Data Quality Standards

- **Minimum events per day:** 15
- **Required stat keys:** points, aces, blocks, attack_pct, sets_won
- **Stat validation:** Scanner warns when 0% of events contain required stat keys (does not fail scan)
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only
- **Max deep links:** 20 (from config)

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| betexplorer.com | 20s | 1s | 2 |
| oddsportal.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |
| forebet.com | 20s | 1s | 2 |

**Total scanner timeout:** 5 minutes

## Fallback Chains

**Market odds:**
1. BetExplorer → 2. OddsPortal → (no tertiary)

**Statistical data:**
1. Flashscore (period scores → sets/points) → 2. Sofascore API (event statistics) → 3. ESPN FIVB (free, no rate limit) → 4. API-Sports volleyball (shared quota)

**Tipsters:**
1. ZawodTyper/Typersi → 2. Sportsgambler → 3. Meczyki

## Seasonal Considerations

- **European club season:** Sep-May (PlusLiga, SuperLega, Bundesliga)
- **Off-season:** Jun-Aug for European clubs
- **Beach volleyball:** May-Sep (different sport, different sources)
- **Women's leagues:** Similar calendar to men's
- **Champions League:** Oct-May (group stage → final four)
- **National teams:** Nations League (sporadic), World Championship (Sep)

## Known Issues

- **API-Sports quota pressure.** 100/day shared across 5 sports. Run `fetch_api_stats.py --sports volleyball` FIRST before other sports to ensure volleyball allocation.
- **ESPN FIVB limited to international events.** Covers FIVB Nations League, World Championship, NCAA volleyball. Does NOT cover domestic European leagues (PlusLiga, SuperLega, etc.). Returns HTTP 400 when no events are scheduled.
- **Scores24 requires Playwright.** Returns 403 for plain HTTP requests. Listed in PLAYWRIGHT_ADAPTERS.
- **CEV website:** Has detailed match stats but no scraping adapter built. Playwright selector profile exists in `site_selectors.json`.
- **PlusLiga website:** Polish league stats available but no adapter. Playwright selector profile exists.
- **The-Odds-API:** Does NOT cover volleyball.
- **OddsPortal:** React SPA — adapter may return 0 events when JS rendering is incomplete.

## Live Test URLs

Test volleyball adapters with: `python3 scripts/_live_test_adapters.py --sport volleyball --verbose`

| Domain | Test URL | Status (2026-05-12) |
|--------|----------|---------------------|
| flashscore.com | /volleyball/ | ✅ 5 events (sport=volleyball, match_id, league) |
| sofascore.com | /api/v1/sport/volleyball/scheduled-events/{today} | ✅ 6 events (match_url with statistics API) |
| betexplorer.com | /volleyball/ | ✅ 3 events (odds, league, time) |
| forebet.com | /en/volleyball/predictions-today | ⚠️ 0 events (seasonal — no predictions today) |
| oddsportal.com | /volleyball/ | ⚠️ 0 events (React SPA rendering issue) |
| scores24.live | /en/volleyball | ⚠️ 0 events (no matches scheduled today) |

## Deep Data Requirements (v4 Pipeline)

For every scanned fixture, the scanner MUST attempt to collect:
1. H2H history (last 5 meetings minimum) with per-stat breakdowns
2. Recent form (last 10 matches) with opponents, results, scores  
3. League standings position and zone status
4. Key injuries/suspensions
5. Per-match statistical data (not just averages)

## Data Quality Validation

After scan completes, validate per fixture:
- Has ≥2 independent source confirmations?
- Has team form data for BOTH teams?
- Has at least 1 statistical data source (API or deep parse)?
- Required stat keys checked at scan validation (WARNING level)
- THINK IN THE MIDDLE: use sequentialthinking to evaluate scan quality
