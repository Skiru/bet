# Data Sources & Architecture — Current State

## Primary Scan Source: Flashscore
- `UnifiedAPIClient` → `FlashscoreClient` → ESPN fallback
- HTTP + Playwright stealth fallback, 2s rate limit
- Covers: football (~225/day), tennis (~568), basketball (~75), hockey (~15), volleyball (~7)

## New Scrapers Module (`src/bet/scrapers/`) — 19 scrapers
ESPN is now a FIRST-CLASS scraper in the new module (not just old fallback):
```
Football:     FBref (players+xG) → ESPN (29 team stats: corners,fouls,cards,shots,possession) → Flashscore
Basketball:   NBA API → Basketball-Reference → ESPN (boxscores+rosters) → Flashscore
Hockey:       NHL API → Hockey-Reference → ESPN (boxscores+rosters) → Flashscore
Tennis:       Sackmann (player stats) → ESPN (scoreboard: sets,games,rankings) → SofaScore → Flashscore
Volleyball:   Volleybox → ESPN (kills,aces,blocks) → SofaScore → Flashscore
```

## Legacy Enrichment Fallback Chains (old system — `data_enrichment_agent.py`)
```
Football:     ESPN → scores24 (HTTP) → TotalCorner (corners) → TransferMarkt (roster)
Basketball:   ESPN → Basketball-Reference → nba-api (NBA only)
Hockey:       MoneyPuck (PRIMARY NHL advanced) → ESPN → Hockey-Reference → DailyFaceoff (goalies)
Tennis:       ESPN → TennisAbstract → TennisExplorer
Volleyball:   ESPN → Flashscore scan data → CEV/PlusLiga
```

## API Client Status
| Client | Status | Notes |
|--------|--------|-------|
| ESPN | WORKING, free, no key | Football, basketball, hockey, tennis, volleyball |
| Flashscore | WORKING (stealth Playwright) | Primary scan source, DOM scraping |
| MoneyPuck | WORKING, free CSV API | 32 NHL teams, 40 stat keys, no auth/Cloudflare |
| The-Odds-API | WORKING, 500/month free | Odds only, 30 credits/scan |
| API-Football | WORKING | api-sports.io, key required |
| API-Basketball | WORKING | api-sports.io, dynamic season |
| API-Hockey | WORKING | api-sports.io |
| API-Volleyball | WORKING | api-sports.io |
| nba-api | WORKING, free | NBA stats, 1 req/sec |
| Sofascore | DEAD (403) | Client code preserved but not imported |
| TheSportsDB | DEAD | `_HOST_BROKEN=True` |
| BallDontLie | DEAD | `_HOST_BROKEN=True` |
| API-Tennis | DEAD | `_HOST_BROKEN=True`, NXDOMAIN |

## Anti-Bot Blocked Sources
| Source | Status | Workaround |
|--------|--------|------------|
| Forebet | 403 Cloudflare | None — use BetExplorer/Flashscore |
| WhoScored | 403 | None |
| NaturalStatTrick | 403 "Under Attack" | MoneyPuck replaces for NHL |
| ATP Tour | Cloudflare challenge | TennisAbstract/TennisExplorer |
| Sofascore | Server-side bot detection | Removed from pipeline |

## Multi-Sport Adapter Summary
- **Football**: BetExplorer (235), Flashscore (45 raw), Forebet (44+deep links), Soccerway (38 raw)
- **Basketball**: Basketball-Reference (box scores, season avgs), nba-api (NBA stats)
- **Hockey**: MoneyPuck (37 raw + 3 derived stats), Hockey-Reference (box scores), DailyFaceoff (goalie confirmations)
- **Tennis**: TennisExplorer (H2H, surface), TennisAbstract (Elo ratings)
- **Volleyball**: Flashscore (scan data), Scores24 (aces, blocks, kills)

## Gemini Integration (feature-flagged, additive)
| Module | Purpose | Flag |
|--------|---------|------|
| `gemini_tipster_reader.py` | Read tipster sites via URL reading | `--use-gemini` |
| `gemini_web_research.py` | L7a Search Grounding (replaces SerpAPI) | `use_gemini=True` (default) |
| `gemini_news_enrichment.py` | Injuries/coaching/morale → `team_news` DB | `--news` |
| `gemini_deep_analyst.py` | Per-candidate "second opinion" | `--gemini` |

## Key Data Flow
Adapters → `normalize_adapter_output()` → scan_results JSON → `fetch_api_stats.py` (fallback chains) → `build_stats_cache` → `stats_cache/{sport}/{team}.json` + DB → `deep_stats_report.py` / `compute_safety_scores.py`

## API Clients Overhaul (planned)
Plan at `betting/plans/api-clients-overhaul.plan.md`. Key: extract shared Playwright boilerplate into `PlaywrightBaseClient`, create 5 new clients (BetExplorer, Soccerway, OddsPortal, TotalCorner, Scores24), clean up 3 dead legacy clients.
