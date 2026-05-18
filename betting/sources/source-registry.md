# Betting Source Registry

Purpose: document all data sources used by the 5-sport pipeline (football, volleyball, basketball, tennis, hockey). Sources organized by role — stats, odds, fixtures, tipsters — with depth across every league.

## Source Philosophy

The pipeline uses **API-first discovery architecture**: SofaScore + Odds API + API-Football as the 3 primary discovery sources for event identification (~30s), with enrichment sources filling in deep data (form, H2H, injuries). The workflow must:
1. Use the discovery module (`discover_events.py`) for fixture identification from 3 API sources.
2. Use Tier A market sources for odds comparison and line shopping.
3. Use enrichment sources (ESPN API, Flashscore scrapers, scores24) to fill statistical gaps after discovery.
4. Use Tier B tipster/community sites to validate direction, discover angles, and check consensus.
5. Prioritize lower-division and minor-league coverage — market inefficiency is highest where bookmaker lines are weakest.

## Source Classification Quick Reference

| Category | Sources | Access Method |
|----------|---------|---------------|
| **Automated — Discovery** | SofaScore API, The-Odds-API, API-Football | `src/bet/discovery/` module via `discover_events.py` |
| **Automated — Scrapers** | 19 scrapers: FBref, NBA API, NHL API, Basketball-Reference, Sackmann, ESPN (5 sports), Flashscore (5 sports), Hockey-Reference, Volleybox | `src/bet/scrapers/` module via `run_scrapers.py` |
| **Automated — Odds** | the-odds-api, odds-api.io, api-football-odds | `fetch_odds_api.py`, `fetch_odds_api_io.py`, `fetch_odds_multi.py` |
| **Automated — Enrichment** | ESPN API, Flashscore HTTP | `data_enrichment_agent.py` |
| **Manual/Browser** | OddsPortal, BetExplorer, SBR, ESPN Odds, ScoresAndOdds, Flashscore (results) | Playwright/browser via agents |
| **Tipster/Community** | ZawodTyper, Typersi, OLBG, PicksWise, WinDrawWin, FootballPredictions | `tipster_aggregator.py` (Playwright DOM scraping → DB `tipster_picks` + `tipster_consensus`) |
| **Archived/Blocked** | Forebet, FootySupertips, Volleybox (403) | Not available |

## Tier A Core Market and Price Sources

- Betclic
  Role: execution price and available markets.
  Use for: the exact bookmaker odds and stake plan.
  Never use for: main analytical justification.
  Access: 403 blocks automated access. All picks CONDITIONAL — user verifies on app.

- OddsPortal
  Role: fixture discovery, archived results, standings, dropping odds monitoring (manual).
  Use for: fixture discovery via UnifiedAPIClient, result backchecks, and movement context.
  Access: OK (Playwright required).
  NOTE: Removed from automated odds pipeline (H2H listing odds only, no line data). Use for manual investigation only.

- BetExplorer
  Role: fixture discovery, results, streaks, popular bets.
  Use for: fixture discovery via UnifiedAPIClient, results history, and market heat checks.
  Access: OK.
  NOTE: Removed from automated odds pipeline (odds stub returns empty bookmakers). Use for fixture discovery only.

- SportsbookReview (SBR)
  Role: US-sport odds comparison — NHL, NBA. Moneyline, spread, AND totals tabs with lines from 6+ books.
  URL: sportsbookreview.com/betting-odds/{sport}/
  Sport slugs: nhl-hockey, nba-basketball.
  Use for: totals lines + prices for US sports (the "Totals" tab shows O/U line + American odds per book).
  Access: OK (no GDPR wall, renders in Playwright). Click "Totals" tab for O/U.
  Coverage: NHL, NBA.
  American-to-decimal conversion: positive +X → 1 + X/100; negative -X → 1 + 100/X.
  Added: 2026-04-23.

- ESPN Odds
  Role: US-sport odds — NHL, NBA. Shows moneyline, spread, totals with lines and American odds.
  URL: espn.com/{sport}/odds (sport = nhl, nba)
  Use for: cross-validation of US sport totals and moneylines. Shows team records inline.
  Access: OK from EU/PL IP. No soccer or tennis odds available.
  Coverage: NHL, NBA.
  NOTE: ESPN API no longer returns odds data programmatically. Use for manual cross-validation only — not as a pipeline odds source.
  Added: 2026-04-23.

- ScoresAndOdds
  Role: US-sport odds comparison with line movements — NHL, NBA.
  URL: scoresandodds.com/{sport} (sport = nhl, nba)
  Use for: totals lines, moneyline, puck/point line, line movement tracking. Shows opening vs current odds.
  Access: OK from EU/PL IP. Renders in Playwright. Has "LINE MOVEMENTS" column.
  Coverage: NHL, NBA.
  Added: 2026-04-23.

- The-Odds-API
  Role: universal odds API — ALL sports globally. Returns JSON with odds from multiple bookmakers.
  URL: api.the-odds-api.com/v4/sports/{sport}/odds?regions={region}&markets={markets}&apiKey={key}
  Use for: programmatic odds retrieval for ANY sport when manual scraping fails. Supports h2h, spreads, totals.
  Access: free tier (500 credits/month). API key in config/odds_api_key.txt or ODDS_API_KEY env var.
  Coverage: NBA, NHL, EPL, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Ekstraklasa, MLS, tennis Grand Slams, and 70+ more.
  NOT covered: volleyball (fallback sources — odds-api.io handles this as primary volleyball odds source).
  Script: `python3 scripts/fetch_odds_api.py` — fetches all sports, saves to betting/data/odds_api_snapshot.json + odds_api_summary.csv.
  Commands: `--list-sports` (free, 0 credits), `--sports hockey,basketball` (filter), `--scores hockey` (settlement).
  Quota: 1 credit per sport×market×region. Full scan (5 sport groups × h2h+totals × eu) ≈ 12 credits. ~40 full scans/month on free tier.
  Integration: Run in STEP 1 (event scan) as cross-validation source. Run in STEP 5 (odds check) for market-best prices. Run with --scores for STEP 0 (settlement).
  Added: 2026-04-23. Activated: 2026-04-24.

- API-Football /odds
  Role: deep football odds — 20+ bookmakers, 60+ bet types including corners O/U, cards O/U, BTTS.
  URL: v3.football.api-sports.io/odds
  Use for: football odds cross-validation with far richer market depth than The Odds API.
  Access: free tier (100 req/day shared with stats). Same API key as API-Football.
  Coverage: 1000+ football leagues globally. Odds may lag 15-30 min behind live prices.
  Script: Integrated into `python3 scripts/fetch_odds_multi.py`.
  Added: 2026-04-29.

- odds-api.io
  Role: universal odds API — 265 bookmakers, 34 sports, value bets with pre-calculated EV.
  URL: api.odds-api.io
  Use for: programmatic odds retrieval for ALL 5 sports including volleyball (which The-Odds-API does not cover). Includes Betclic PL and Bet365 among 265 bookmakers. Value bets endpoint provides pre-calculated EV.
  Access: free tier (5,000 requests/hour — very generous). API key in config/api_keys.json.
  Coverage: Football, tennis, basketball, hockey, volleyball — PRIMARY volleyball odds source.
  Script: `python3 scripts/fetch_odds_api_io.py --date YYYY-MM-DD --verbose` — fetches all sports, saves to betting/data/odds_api_io_snapshot.json + persists to DB odds_history table (dual-write).
  Also: `--value-bets` (value bets only), `--list-sports` (list available sports).
  Integration: Run in STEP S1b (odds fetch) alongside fetch_odds_api.py. Also integrated into fetch_odds_multi.py as second source.
  Added: 2026-05-14. Activated: 2026-05-14.

## Tier A Core Stats, Fixture, and Verification Sources

- Flashscore
  Role: Deep enrichment source — H2H, live stats, xG and match statistics, form, and results.
  Use for: deep enrichment (S2), pre-match context, and settlement verification. No longer used for event discovery (replaced by discovery module).
  Access: HTTP + Playwright stealth fallback. Rate limit: 2s between requests.
  Script: `scripts/run_scrapers.py --source flashscore` (FlashscoreClient)

- Covers
  Role: expert-written previews for US sports and big markets.
  Use for: NHL, NBA support and narrative checks.
  Access: PARTIAL — NBA pages return empty; other sections intermittent. Do not rely as sole source.

- TeamRankings
  Role: algorithmic picks, rankings, trends, injuries, matchup pages, and efficiency stats.
  Use for: NBA and college sports, especially totals and spread context.
  Access: INTERMITTENT — sometimes blocked. Do not rely as sole source. When available, useful for totals context.

- TennisAbstract
  Role: tennis Elo, matchup data, serve-return profiles, forecasts, and surface context.
  Use for: tennis moneyline, set handicap, game or set totals, and form quality.

- Sportsgambler
  Role: multi-sport written previews with lineups, injuries, and advanced metrics.
  Use for: football plus North American sports when a fresh preview is needed.

- Scores24.live
  Role: universal multi-sport deep data source — match detail pages with H2H, recent form (last 5-10 matches with scores), live odds (W1/X/W2, handicaps, totals), and structured betting trends with statistical hit rates.
  URL: scores24.live/en/{sport} (sport = soccer, tennis, basketball, ice-hockey, volleyball)
  Detail URL: scores24.live/en/{sport}/m-{DD-MM-YYYY}-{slug}
  Trends URL: scores24.live/en/{sport}/m-{DD-MM-YYYY}-{slug}#trends
  Use for:
    - Fixture discovery across ALL sports (listing pages provide match links with dates).
    - Deep pre-match context: H2H records with actual match scores, last 5+ form for both sides.
    - Odds cross-validation: W1/X/W2 + handicap lines + totals from multiple bookmakers.
    - Trend-based analysis: structured betting tips with "X of last Y" hit rates (e.g., "Team has won in 6 of last 7 matches" → 86%).
    - Surface, venue, tournament, and round info for tennis and other sports.
  Data depth per match:
    - match_info: home, away, tournament, venue, surface, round, date, time
    - odds: W1/X/W2, handicap lines (e.g., +1.5, -3), total lines (O/U with lines)
    - h2h: win count per side + last N H2H matches with full scores
    - form_home / form_away: last 5-10 matches with opponent, result (W/L), scores
    - trends: categorized tips (Match Result, Double Chance, Over/Under, Handicap, BTTS) with hit_count/sample_size/hit_rate and associated odds
  Access: OK. Renders via Playwright (JS-heavy SPA). No GDPR wall. Cookie selectors configured.
  Coverage: 20+ sports globally. Best coverage for football, tennis, basketball, ice hockey, volleyball.
  Adapter: `scripts/adapters/scores24_adapter.py` — handles both listing pages and detail pages.
  Added: 2026-04-30.

## Tier A Core Stats — API Sources (Programmatic)

These API sources provide structured statistical data via REST APIs. They are the primary data pipeline for the deep analysis pool engine. All use free tiers with daily rate limits.

- API-Football v3 (api-sports.io)
  Role: comprehensive football statistics API — per-match corners, fouls, cards, shots, possession across 1000+ leagues globally.
  Use for: L10/L5/H2H statistical data for ALL football markets. Primary source for safety score computation.
  Access: free tier (100 req/day). API key in config/api_keys.json or API_FOOTBALL_KEY env var.
  Coverage: 1000+ leagues, 120+ countries. All exotic leagues (E1-E3) covered.
  Stats per match: corners, shots, SOT, fouls, cards, possession, passes, saves, offsides.
  Script: `python3 scripts/fetch_api_stats.py --sports football`
  Fallback: Football-Data.org → Understat → Playwright scraping.
  Added: 2026-04-28.

- API-Basketball v1 (api-sports.io)
  Role: basketball statistics API — per-game points, rebounds, assists, steals, blocks across NBA, Euroleague, and 50+ leagues.
  Use for: L10/L5/H2H statistical data for basketball totals, spreads, and team prop markets.
  Access: free tier (100 req/day). API key in config/api_keys.json or API_BASKETBALL_KEY env var.
  Coverage: NBA, Euroleague, ACB, NBL, BSL, LNB, and all major+minor leagues.
  Script: `python3 scripts/fetch_api_stats.py --sports basketball`
  Fallback: nba_api (NBA only).
  Added: 2026-04-28.

- API-Hockey v1 (api-sports.io)
  Role: hockey statistics API — per-game goals, shots, PP, PIM, hits, blocks, faceoffs across NHL, KHL, and European leagues.
  Use for: L10/L5/H2H statistical data for hockey totals and period markets.
  Access: free tier (100 req/day). API key in config/api_keys.json or API_HOCKEY_KEY env var.
  Coverage: NHL, KHL, SHL, DEL, Liiga, Czech Extraliga, Swiss NL.
  Script: `python3 scripts/fetch_api_stats.py --sports hockey`
  Added: 2026-04-28.

- Football-Data.org
  Role: EU football fixtures, results, standings — fallback when API-Football quota exhausted.
  Use for: fixture discovery and form validation for 12 major EU leagues. Does NOT provide per-match corner/foul stats.
  Access: free tier (10 req/min). API key in config/api_keys.json or FOOTBALL_DATA_ORG_KEY env var.
  Coverage: EPL, Bundesliga, Serie A, La Liga, Ligue 1, Eredivisie, Primeira, Championship, Brasileirão.
  Added: 2026-04-28.

- BallDontLie API
  Role: free NBA stats API — game results, player box scores, season averages.
  Use for: DEPRECATED — see "Deprecated / Broken Sources" section below.
  Status: DEPRECATED 2026-05-13. Moved to deprecated section.

- nba_api (Python package)
  Role: unofficial NBA stats from stats.nba.com — most detailed free NBA data source.
  Use for: advanced NBA stats (pace, ORtg, DRtg), team game logs, detailed box scores.
  Access: free (no key, rate ~30 req/min). Rate-sensitive — add delays between calls.
  Coverage: NBA only (current + historical seasons).
  Added: 2026-04-28.

- Understat (Python package)
  Role: expected goals (xG) data for top 6 European football leagues.
  Use for: xG, xGA, npxG, PPDA per match — enriches football analysis depth.
  Access: free Python package (scrapes understat.com). No API key needed.
  Coverage: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL.
  Added: 2026-04-28.

- NaturalStatTrick
  Role: advanced NHL statistics (Corsi, Fenwick, expected goals, high danger chances).
  URL: naturalstattrick.com
  Use for: NHL team possession metrics and game flow data.
  Access: **BLOCKED** — Cloudflare "Under Attack" mode returns 403 on ALL methods (requests, cloudscraper, Playwright headless/non-headless). NOT fixable without proxy/residential IP.
  Coverage: NHL.
  Adapter: `scripts/adapters/naturalstattrick_adapter.py` (code works but source unreachable).
  Status: L2 fallback only — replaced by MoneyPuck as primary xG/Corsi/Fenwick source.
  Added: 2026-05-12.

- MoneyPuck
  Role: advanced NHL team statistics (xG%, Corsi%, Fenwick%, high-danger chances, PDO, shooting%, save%).
  URL: moneypuck.com/moneypuck/playerData/seasonSummary/{season}/{type}/teams.csv
  Use for: **PRIMARY** NHL advanced stats — 37 normalized stat keys per team, 5 situations (all/5on5/4on5/5on4/other).
  Access: FREE, no API key, no Cloudflare. CSV endpoint via requests (Playwright triggers download error).
  Coverage: NHL (32 teams, 102 raw columns).
  Client: `scripts/api_clients/moneypuck_client.py` (fetches CSV, 12h cache).
  Adapter: `scripts/adapters/moneypuck_adapter.py`
  Enrichment: integrated in `deep_stats_report.py` for hockey candidates.
  Added: 2026-05-12.

- Google Sports (SerpAPI)
  Role: H2H enrichment via Google Knowledge Graph sports panels — returns structured head-to-head match data, scores, venues, tournaments, red cards, goal scorers, and Knowledge Graph IDs (kgmids).
  URL: serpapi.com (proxied Google search — "Team A vs Team B" query)
  Use for: H2H enrichment for ALL 5 sports. Returns 2-10 recent head-to-head matches with full scores, tournament names, venues, red cards (football/hockey), set scores (tennis), and player rankings.
  Data depth per query:
    - Football/Hockey/Basketball: H2H matches with home/away scores, tournament, venue, red cards, date, kgmids
    - Tennis: set scores per set, rankings, tournament stage, winner
    - Live/Today matches: league, status, stadium, goal scorers (player name, jersey number, minute + stoppage time)
  Access: SerpAPI free tier (250 searches/month). API key in config/api_keys.json ("serpapi" key). Budget: max 15 queries per pipeline run.
  Coverage: ALL sports globally — any match Google has a Knowledge Panel for.
  Client: `scripts/api_clients/google_sports_client.py` (GoogleSportsClient)
  Cache: 48h file-based cache in betting/data/stats_cache/google-sports/
  DB integration: Saves fixtures, H2H team_form, team entities with kgmids.
  Fallback chain position: After sport-specific APIs, before generic SerpAPI. E.g., football: `["espn-football", "api-football", "football-data-org", "understat", "google-sports", "serpapi"]`
  Added: 2026-05-17.

- DailyFaceoff
  Role: starting NHL goalie confirmations and line combos.
  URL: dailyfaceoff.com
  Use for: confirming starting goalies for NHL matches (critical for betting). status: confirmed/expected/unconfirmed.
  Access: OK (Playwright).
  Coverage: NHL.
  Adapter: `scripts/adapters/dailyfaceoff_adapter.py`
  Added: 2026-05-12.

- API-Tennis (custom client)
  Role: tennis statistics API client.
  Use for: DEPRECATED — see "Deprecated / Broken Sources" section below.
  Status: DEPRECATED 2026-05-13. Moved to deprecated section.

- API-Volleyball (custom client)
  Role: volleyball statistics API client — team stats, match results, set scores, point totals.
  Use for: L10/L5/H2H statistical data for volleyball set totals, point totals, and set handicap markets.
  Script: `python3 scripts/fetch_api_stats.py --sports volleyball` (uses `api_clients/api_volleyball.py`)
  Fallback: Playwright (Flashscore).
  Added: 2026-04-30.

- TheSportsDB
  Role: universal sports fixture database.
  Use for: DEPRECATED — see "Deprecated / Broken Sources" section below.
  Status: DEPRECATED 2026-05-13. Moved to deprecated section.

- ESPN API (espn_adapter.py)
  Role: FREE, UNLIMITED, NO API KEY — multi-sport statistics via ESPN's public endpoints. Per-match stats: corners, fouls, cards, shots, shots on target, possession, saves, offsides, passes, tackles, interceptions, clearances. 36+ football leagues, NBA, NHL, ATP/WTA.
  Use for: PRIMARY L10/L5/H2H stats source (first in every applicable fallback chain). Produces ~64KB slug-based cache per team. Feeds safety score computation and market ranking.
  Access: free (no API key, no rate limit). Endpoint: site.api.espn.com/apis/site/v2/sports/{sport}/{league}/.
  Coverage: Football (36 leagues: eng.1-4, ger.1, esp.1, ita.1, fra.1, ned.1, por.1, usa.1, mex.1, bra.1, arg.1, tur.1, gre.1, rus.1, bel.1, sco.1, chn.1, jpn.1, kor.1, aus.1 + 16 more). Basketball (NBA). Hockey (NHL). Tennis (ATP, WTA).
  Stats per match (football): fouls, yellow_cards, red_cards, offsides, corners, saves, possession, shots, shots_on_target, shot_accuracy, penalty_goals, accurate_passes, total_passes, pass_accuracy, accurate_crosses, long_balls, blocked_shots, tackles_won, interceptions, clearances, goals.
  Client registry: `espn-football`, `espn-basketball`, `espn-hockey`, `espn-tennis` (4 registered factories).
  Script: Integrated into `python3 scripts/fetch_api_stats.py` via fallback chains.
  Added: 2026-04-30. Promoted to first in chains: 2026-05-04.

- SerpAPI
  Role: Google search API with structured sports data — fixtures, results, standings, odds snippets from Google Knowledge Graph.
  Use for: last-resort supplementary data when all sport-specific APIs fail. Returns structured Google search results including live scores, standings snippets, and injury news.
  Access: free tier (100 searches/month). API key in config/api_keys.json or SERPAPI_KEY env var.
  Coverage: ALL sports (Google indexes everything). Quality depends on Google's knowledge graph coverage for the specific event.
  Client registry: `serpapi` — last in every fallback chain.
  Script: Integrated into `python3 scripts/fetch_api_stats.py` as final fallback.
  Added: 2026-05-04.

- Odds-API.io
  Role: real-time odds comparison from 265 bookmakers across 34 sports — value bets, pre-calculated EV opportunities, participant search.
  URL: api.odds-api.io/v3
  Use for: odds cross-validation with Betclic PL and Bet365 focus. Value bet detection (/value-bets endpoint). Fixture discovery. 34 sports including volleyball and more.
  Access: free tier (5,000 req/hour). API key in config/api_keys.json or ODDS_API_IO_KEY env var.
  Coverage: 34 sports (football, basketball, tennis, hockey, volleyball + more). 265 bookmakers.
  Key endpoints: /events (fixtures by sport), /odds (bookmaker odds per event), /odds/multi (batch), /value-bets (pre-calculated EV), /participants (team/player search).
  Client registry: `odds-api-io` — used separately by `fetch_odds_multi.py`, NOT in stats fallback chains.
  Script: `python3 scripts/fetch_odds_multi.py` (integrated as odds source), also callable via `api_clients/odds_api_io.py` directly.
  Added: 2026-05-04.

### API Fallback Chains

ESPN is first for all sports it covers (FREE, unlimited). SerpAPI is last resort for all sports.

**Stats API chains:**
```
Football:     ESPN → API-Football → Football-Data.org → Understat (xG only) → SerpAPI
Basketball:   ESPN → API-Basketball → SerpAPI
Hockey:       ESPN → API-Hockey → SerpAPI
Tennis:       ESPN → SerpAPI
Volleyball:   ESPN-Volleyball → API-Volleyball → SerpAPI
```

**Fixture discovery chains (UnifiedAPIClient SOURCE_PRIORITY):**
```
Football:     Flashscore → BetExplorer → Soccerway → ESPN
Tennis:       Flashscore → Scores24 → ESPN
Basketball:   Flashscore → BetExplorer → Scores24 → ESPN
Hockey:       Flashscore → BetExplorer → Scores24 → ESPN
Volleyball:   Flashscore → BetExplorer → Scores24 → ESPN
```

**Odds comparison chains (pipeline — via `fetch_odds_multi.py`):**
```
Football:     the-odds-api → odds-api.io → api-football-odds
Tennis:       the-odds-api → odds-api.io
Basketball:   the-odds-api → odds-api.io
Hockey:       the-odds-api → odds-api.io
Volleyball:   odds-api.io
```

**Stats-specific chains (STATS_PRIORITY):**
```
Football corners: TotalCorner → Flashscore
```

**Trends/hit rates:** Scores24 (all sports)

Disabled sources (2026-05-11): TheSportsDB (97.8% fail), BallDontLie (100% fail), API-Tennis (NXDOMAIN).

### Daily API Budget (~560 requests)

| API | Daily Limit | Typical Use | Reserve |
|-----|-------------|-------------|---------|
| ESPN (all sports) | unlimited | 500+ | — |
| API-Football | 100 | 70 | 30 |
| API-Basketball | 100 | 60 | 40 |
| API-Hockey | 100 | 50 | 50 |
| Football-Data.org | ~1000 | 200 | 800 |
| nba_api | ~1800/hr | 200 | 1600 |
| Understat | unlimited | 50 | — |
| The Odds API | ~40/day | 40 | 0 |
| Odds-API.io | 5000/hr | 200 | 4800 |
| SerpAPI | 100/mo | 20 | 80 |

## Weather Data Source

- Open-Meteo
  Role: free weather API — temperature, precipitation, wind speed, weather conditions by geographic coordinates.
  URL: api.open-meteo.com/v1/forecast
  Use for: STEP 3B weather impact assessment for outdoor sports (football, tennis). No API key required.
  Script: `python3 scripts/fetch_weather.py --date YYYY-MM-DD` — fetches weather data for all outdoor event venues.
  Access: free (no key, no registration). Rate limit ~10,000 req/day.
  Coverage: Global. Hourly forecast data for any latitude/longitude.
  Integration: Run as part of STEP 3B (time-sensitive data). Output used to assess wind/rain impact on statistical markets (e.g., rain → fewer corners, wind → fewer goals in football).
  Added: 2026-04-30.

## Scan Adapters (Structured Parsing — Legacy)

These adapters provide structured data extraction from web sources, normalizing raw HTML into fixture/stats JSON format. They were used by the legacy `scan_events.py` and `deep_link_discovery.py`. The primary scan path now uses the discovery module (`src/bet/discovery/`). Adapters remain available for enrichment and fallback scenarios.

- soccerway_adapter.py (`scripts/adapters/soccerway_adapter.py`)
  Role: structured parser for Soccerway pages — Soccerway-specific selectors (team-a/team-b/score-time), group-head league detection, and raw fallback with sport/source_type enrichment.
  Use for: exotic league fixture discovery. Covers 200+ countries and 1000+ leagues. 38+ matches via HTTP (raw fallback), more with Playwright.
  Input: Soccerway URLs (e.g., `/matches/YYYY/MM/DD/`)
  Output: normalized fixtures with home/away, league, match_url (absolute), sport, source_type. `get_deep_links()` for /matches/ sub-pages.
  Features: verbose logging, dedup, absolute match_url (not relative), raw fallback enriches sport/source_type.
  Updated: 2026-05-12.

- tennisexplorer_adapter.py (`scripts/adapters/tennisexplorer_adapter.py`)
  Role: structured parser for TennisExplorer pages — uses paired-row parsing (two rows per match) to extract player names, match URLs, scores, and tournament context.
  Use for: primary tennis fixture discovery. 302+ matches per page with 94% match_url coverage.
  Input: TennisExplorer URLs (/matches/, main page, tournament pages)
  Output: normalized match data with home/away, match_url, period_scores, surface, country.
  Features: bookmaker link filtering (bet365/1xBet/Unibet/bwin), seed number stripping, deep link patterns for /match-detail/ and /head-to-head/.
  Updated: 2026-05-12.

- soccerstats_adapter.py (`scripts/adapters/soccerstats_adapter.py`)
  Role: structured parser for SoccerStats pages — extracts league-level corner, card, foul, and BTTS statistics with safe float parsing.
  Use for: league-level statistical context for football corner/card/foul markets.
  Input: SoccerStats league URLs (e.g., `/latest.asp?league={league}`)
  Output: normalized league statistics (team averages for corners, cards, fouls, goals). `get_deep_links()` for results/teams/homeaway.asp sub-pages.
  Features: verbose logging, dedup, try/except float parsing, removed duplicate source/url fields.
  Updated: 2026-05-12.

- scores24_adapter.py (`scripts/adapters/scores24_adapter.py`)
  Role: structured deep parser for scores24.live — listing pages (fixture discovery) and detail pages (H2H, form, odds, trends).
  Use for: multi-sport fixture discovery + deep pre-match data. Provides structured betting trends with hit rates, H2H with match scores, form per team, and multi-market odds.
  Input: scores24.live listing URLs (`/en/{sport}`) or detail URLs (`/en/{sport}/m-{date}-{slug}`).
  Output: listing → match links with dates and detail URLs; detail → full match data dict with match_info, odds, h2h, form_home, form_away, and trends.
  Sports covered: soccer, tennis, basketball, ice-hockey, volleyball.
  Added: 2026-04-30.

- flashscore_adapter.py (`scripts/adapters/flashscore_adapter.py`)
  Role: structured parser for Flashscore pages — extracts fixtures, live scores, results across ALL 14 sports using 3 heuristic methods (table rows, event blocks, regex patterns).
  Use for: primary fixture discovery. Handles football, tennis, basketball, hockey, volleyball.
  Input: Flashscore URLs (e.g., `/football/`, `/tennis/`, `/volleyball/`)
  Output: normalized fixture list with home/away teams, competition, sport, kickoff time.
  Includes: garbage entry filtering, team name cleanup, deep-link discovery support.
  Added: 2026-04-30.

- betexplorer_adapter.py (`scripts/adapters/betexplorer_adapter.py`)
  Role: structured parser for BetExplorer pages — extracts fixtures with odds, results, and competition context across all sports. Auto-detects sport from URL.
  Use for: fixture discovery with embedded odds data. Covers football, tennis, basketball, hockey, volleyball. 235+ matches via HTTP.
  Input: BetExplorer sport URLs (e.g., `/football/`, `/volleyball/`)
  Output: normalized fixture list with odds context (1X2 or ML prices), sport, source_type. `get_deep_links()` for /match/ detail pages.
  Features: verbose logging, dedup, sport auto-detection from URL.
  Updated: 2026-05-12.

- forebet_adapter.py (`scripts/adapters/forebet_adapter.py`)
  Role: structured parser for Forebet prediction pages — extracts model predictions, probabilities, and predicted scores. 44+ football matches via HTTP (server-rendered).
  Use for: model-backed direction confirmation for football and tennis. Parses 60+ tennis matches and 40+ football matches per page with 2-way/3-way probabilities.
  Input: Forebet tip pages (e.g., `/football-tips-and-predictions-for-today`, `/tennis/predictions-today`)
  Output: normalized predictions with probability %, predicted score, match_url, and value indicators. `get_deep_links()` extracts tnmscn detail links.
  Features: verbose logging, dedup.
  Updated: 2026-05-12.

- oddsportal_adapter.py (`scripts/adapters/oddsportal_adapter.py`)
  Role: structured parser for OddsPortal pages — SPA requiring Playwright. 3 parsing strategies: structured divs, table rows, link-based.
  Use for: odds cross-validation, price gap detection, and line movement tracking. Needs Playwright (0 matches via HTTP).
  Input: OddsPortal sport/league URLs
  Output: normalized odds data with match_url, sport, source_type. `get_deep_links()` extracts match detail URLs.
  Features: verbose logging, dedup, sport auto-detection, fixed deep link pattern (actual match URLs, not /h2h/).
  Updated: 2026-05-12.

- sofascore_adapter.py (`scripts/adapters/sofascore_adapter.py`)
  Role: ARCHIVED — Sofascore API blocked by Cloudflare WAF (403). Kept as insurance.
  Status: DISABLED. All scan/enrichment routes through Flashscore + ESPN.
  Updated: 2026-05-13.

- totalcorner_adapter.py (`scripts/adapters/totalcorner_adapter.py`)
  Role: structured parser for TotalCorner pages — extracts corner counts, dangerous attacks, goal handicaps, cards, standings. Needs Playwright for JS-rendered content.
  Use for: football corner market analysis. Extracts pre-match corner predictions, averages, and handicap lines.
  Input: TotalCorner match list (e.g., `/match/today`)
  Output: normalized corner prediction data per match (corner avg, corner handicap, dangerous attacks, match_url). `get_deep_links()` for /match/ /corner/ sub-pages.
  Features: verbose logging, dedup, match_url extraction.
  Updated: 2026-05-12.

- tennisabstract_adapter.py (`scripts/adapters/tennisabstract_adapter.py`)
  Role: structured parser for TennisAbstract Elo table — uses header-based column mapping to extract player Elo ratings (overall + surface-specific: hElo, cElo, gElo) for 518 ATP + 542 WTA players.
  Use for: Elo-based tennis analysis via `fetch_tennis_elo.py`. Records are marked `_elo_only=True` and filtered by `normalize_adapter_output()` to prevent entering event pipeline.
  Input: TennisAbstract ranking pages (table#reportable)
  Output: player Elo ratings (overall, hard, clay, grass, peak) cached at `betting/data/stats_cache/tennis_elo/`.
  Integration: `compute_safety_scores.py` `lookup_tennis_elo()` reads cache, `has_elo` adds +1 to data quality score.
  Updated: 2026-05-12.

- atptour_adapter.py (`scripts/adapters/atptour_adapter.py`)
  Role: structured parser for atptour.com — extracts scores, rankings, and draw brackets from ATP Tour pages.
  Use for: ATP-level match data. Requires Playwright for JS-rendered content (403 with requests).
  Input: atptour.com pages (scores, rankings, draws)
  Output: normalized match/ranking data with source_type="atptour".
  Added: 2026-05-12.

- fetch_tennis_elo.py (`scripts/fetch_tennis_elo.py`)
  Role: standalone script to fetch and cache TennisAbstract Elo ratings.
  Use for: run BEFORE pipeline to populate Elo cache. Outputs ATP + WTA combined summaries.
  Output: `betting/data/stats_cache/tennis_elo/{tour}_elo.json` with player_count, players array.
  Integration: `compute_safety_scores.py` `lookup_tennis_elo()` reads these files.
  Added: 2026-05-12.

- betclic_adapter.py (`scripts/adapters/betclic_adapter.py`)
  Role: structured parser for Betclic pages — extracts available markets and odds from the execution bookmaker.
  Use for: Betclic market verification. Note: Betclic blocks automated access (403), so this adapter has limited utility. All picks CONDITIONAL — user verifies on app.
  Input: Betclic sport/match URLs
  Output: normalized market/odds data (when accessible).
  Added: 2026-04-30.

- raw_adapter.py (`scripts/adapters/raw_adapter.py`)
  Role: fallback parser for any unrecognized domain — uses regex heuristics to extract "Team A vs Team B" patterns from raw HTML. Now auto-detects sport from URL and source_type from domain.
  Use for: catch-all adapter when no domain-specific adapter exists. Applies garbage entry filtering. Enriches results with sport/source_type for pipeline traceability.
  Input: any HTML page
  Output: normalized fixture list with sport and source_type (lower confidence than domain-specific adapters).
  Updated: 2026-05-12.

### Odds Cross-Validation Sources (Multi-Source System)

The multi-source odds aggregator (`fetch_odds_multi.py`) tries sources in priority order per sport, merging events and deduplicating bookmakers:

| Sport | Source 1 | Source 2 | Source 3 |
|-------|----------|----------|----------|
| football | The Odds API | odds-api.io | API-Football /odds |
| tennis | The Odds API | odds-api.io | — |
| basketball | The Odds API | odds-api.io | — |
| hockey | The Odds API | odds-api.io | — |
| volleyball | odds-api.io | — | — |

Script: `python3 scripts/fetch_odds_multi.py`
Commands: `--sports volleyball` (filter sport), `--sources the-odds-api,odds-api-io` (filter sources), `--dry-run` (show plan only), `--no-window` (all events).
Outputs: `betting/data/odds_api_snapshot.json` (backward compatible), `betting/data/odds_api_summary.csv`, `betting/data/odds_multi_sources.json` (provenance log).
Added: 2026-04-29. Updated: 2026-05-14 (removed broken BetExplorer/OddsPortal, activated odds-api.io).

## Tier B Support and Consensus Sources

- Zawod Typer
  Role: ARGUMENT-BASED tipster community — individual tipsters post detailed written reasoning for each pick.
  URL: zawodtyper.pl
  Navigation: Daily page `/typy-dnia-[DD]-[month]-[weekday]/`. Scroll deeply (lazy-loaded). Search: `/szukaj?q=[team]`.
  Use for: consensus alignment check, divergence warning, local knowledge (injuries, lineup rumors, motivation context), and DEEP ARGUMENT EXTRACTION.
  Priority: highest among community sources for Polish league, La Liga, and tennis events.
  **Deep-dive required**: YES — read each tipster's full argument, not just the pick.

- Tipstrr
  Role: verified tipster platform with tracked ROI, profit/loss history per tipster.
  URL: tipstrr.com
  Use for: finding high-ROI tipsters for specific sports/leagues, consensus direction, and pick validation.
  Access: OK.

- Typersi
  Role: ARGUMENT-BASED Polish betting tips and predictions community — tipsters write reasoning for picks.
  URL: typersi.pl
  Navigation: Daily tips page. Click into individual match pages for tipster arguments.
  Use for: Polish-language consensus on football, tennis, and other sports. Good for LaLiga, Bundesliga, and Ekstraklasa.
  Access: OK.
  **Deep-dive required**: YES — read each tipster's full argument.

- OLBG (Online Betting Guide)
  Role: ARGUMENT-BASED UK tipster community — tipsters compete for accuracy and post written reasoning with each tip.
  URL: olbg.com/tips
  Navigation: Sport → today's tips. Each tip has a written reason. Filter by sport/competition.
  Use for: football and racing consensus, verified tipster records, market trends, and DEEP ARGUMENT EXTRACTION.
  Access: OK.
  **Deep-dive required**: YES — read each tipster's reasoning.

- PicksWise
  Role: ARGUMENT-BASED expert analysis — detailed game previews with reasoning for NBA, NHL, tennis, soccer.
  URL: pickswise.com
  Navigation: Sport → game preview pages. Expert analysis with detailed reasoning per game.
  Use for: US sport totals/spreads analysis, parlay ideas, and expert reasoning per game.
  Access: OK.
  **Deep-dive required**: YES — read expert analysis and reasoning per game.

- BetIdeas
  Role: ARGUMENT-BASED data-driven football tips — model-backed predictions with statistical reasoning.
  URL: betideas.com/tips
  Navigation: Tip category pages (corner-betting-tips, btts-tips, over-under-tips). Each tip includes model probability and reasoning.
  Use for: football BTTS/O2.5/corners predictions backed by models.
  Access: OK.
  **Deep-dive required**: YES — read model reasoning and statistical backing.

- Meczyki
  Role: ARGUMENT-BASED Polish match analysis — tipsters write detailed previews with betting arguments.
  URL: meczyki.pl/typy-bukmacherskie
  Navigation: Daily tips page. Click individual match links for tipster arguments. Good for LaLiga, Bundesliga, Serie A.
  Use for: Polish-language match analysis with tactical context, injury info, and betting angles.
  Access: OK.
  **Deep-dive required**: YES — navigate to individual match pages and read arguments.

### Community Source Usage Rules

Community sources CANNOT create a bet on their own. They serve four functions:

1. **Consensus alignment (+confidence):** If ≥70% of community tips agree with the Tier A statistical direction, boost confidence by 0.5 (round to nearest integer). Note this in the report.
2. **Consensus divergence (red flag):** If ≥60% of community tips CONTRADICT the Tier A direction, treat as a warning. Check for information the stats might miss (injuries, lineup changes, motivation). If no explanation is found, reduce confidence by 1 or skip the pick.
3. **Early news detection:** Forum posts may contain injury/suspension/weather info before it appears in Flashscore. If a community source reports a key absence, verify with a second source before acting on it.
4. **Angle discovery:** Argument-based tipster sites (marked with **Deep-dive required: YES** above — Zawod Typer, Typersi, OLBG, PicksWise, BetIdeas, Meczyki, Sportsgambler) reveal angles that pure statistics miss — tactical changes, managerial styles, weather effects, squad rotation patterns, motivation context, model disagreements. Navigate into match pages, read each tipster's argument, and extract their reasoning. Tipsters with arguments > tipsters with bare picks. Strong consensus from multiple argument-based tipster sites IS a valid supporting signal.

Always record in the report which community sources were checked and whether consensus aligned or diverged. Check at least 2-3 tipster sources per candidate event.

### Exotic League Tipster & Prediction Sources

These sources provide tips, predictions, and community analysis for exotic football leagues. They follow the same Community Source Usage Rules above — they CANNOT create a bet alone but serve as consensus/divergence/angle signals.

- Bettingclosed
  Role: free football predictions with statistical backing — covers 100+ leagues including exotic leagues (South American, African, Asian, Middle Eastern).
  URL: bettingclosed.com
  Use for: pre-match predictions with probability estimates for exotic leagues. Covers Peru Liga 1, Egyptian Premier League, Saudi Pro League, Colombian Liga BetPlay, Indian ISL, Uzbekistan Super League, and many more.
  Access: OK. No login required.
  Coverage: 100+ football leagues globally. Strong in South America, Africa, and Middle East.
  **Deep-dive required**: NO — automated model predictions, not written arguments. Use for consensus direction only.

- Forebet
  Role: algorithmic predictions — mathematical model covering 500+ leagues with probability, predicted score, odds value. Covers football, tennis, basketball, hockey, volleyball.
  URL: forebet.com
  Use for: model-based predictions for all sports. Shows predicted score, probability %, average stats (goals, corners, etc.), and whether odds represent value.
  Access: OK via Playwright (custom forebet_adapter.py). Direct pages work: football-tips-and-predictions-for-today, tennis/predictions-today, etc.
  Coverage: 500+ leagues globally including most exotic leagues. Multi-sport.
  **Deep-dive required**: NO — model output, not human analysis. Use for direction confirmation and probability cross-check.
  Note: Parses 60+ tennis matches and 40+ football matches per page. Includes 2-way/3-way probabilities and predicted scores.

- WhoScored Predictions
  Role: data-driven match previews and predictions with statistical context.
  URL: whoscored.com/Previews
  Use for: match previews for larger exotic leagues (Egyptian Premier, Saudi Pro, Indian ISL).
  Access: OK via Playwright (425k chars fetched successfully). Added to scan URLs.
  Coverage: Major exotic leagues (Saudi, Egypt, India, Colombia, Chile). Not available for ultra-thin leagues.
  **Deep-dive required**: YES — previews contain tactical analysis and statistical context.

- BetGenuine
  Role: free football predictions with H2H analysis, form analysis, and statistical breakdowns for global leagues.
  URL: betgenuine.com
  Use for: exotic league predictions backed by recent form, H2H data, and league standing context.
  Access: OK.
  Coverage: Global coverage including South American, African, and Asian leagues.
  **Deep-dive required**: NO — automated analysis. Use for consensus check.

- SoccerVista
  Role: football predictions and tips community — covers a wide range of global leagues with community picks.
  URL: soccervista.com
  Use for: community consensus on exotic league matches. Shows pick distribution and odds.
  Access: OK.
  Coverage: Wide global coverage including exotic leagues.
  **Deep-dive required**: NO — community picks aggregation. Use for consensus alignment.

- Predictz
  Role: free football predictions with probability calculations for global leagues.
  URL: predictz.com
  Use for: probability-based predictions for exotic leagues.
  Access: PARTIAL — may redirect. Try direct league/country pages.
  Coverage: Decent exotic coverage (South America, Africa).
  **Deep-dive required**: NO — automated probabilities.
  Note: Listed as blocked in source-registry but some direct pages may work. Test before relying.

- Feedinco
  Role: football predictions, tips, and statistical analysis covering 700+ leagues globally.
  URL: feedinco.com
  Use for: exotic league predictions with form analysis, H2H, and head-to-head statistics. One of the broadest coverage sites for exotic leagues.
  Access: OK.
  Coverage: 700+ leagues. Excellent for exotic: covers Peru, Egypt, Uzbekistan, Kings League, Saudi Arabia, India, Vietnam, Thailand, Kazakhstan, Georgia, Kosovo, and more.
  **Deep-dive required**: YES — provides written analysis and statistical context per match.

- Tips180
  Role: African football predictions and tips specialist — dedicated coverage of African leagues and cups.
  URL: tips180.com
  Use for: Egyptian Premier League, Algerian Ligue 1, Moroccan Botola, Nigerian NPFL, South African PSL, and other African leagues.
  Access: OK.
  Coverage: Africa-specialist. Best source for African exotic football tips.
  **Deep-dive required**: YES — match previews with local knowledge.

- AsiaBet
  Role: Asian football betting tips and predictions — specializes in Asian leagues.
  URL: asiabet.org
  Use for: J-League, K-League, Thai League, Vietnamese V-League, Indian ISL, Chinese Super League, and other Asian leagues.
  Access: OK.
  Coverage: Asia-specialist. Covers Southeast Asian and East Asian leagues comprehensively.
  **Deep-dive required**: YES — match previews with Asian market context and local knowledge.

- FootyAmigo
  Role: AI-powered football predictions with statistical edge detection — covers global leagues.
  URL: footyamigo.com
  Use for: value bet detection for exotic leagues. Shows probability vs odds comparison (EV indicator).
  Access: OK (free tier available).
  Coverage: Global including exotic leagues.
  **Deep-dive required**: NO — automated model. Use for value direction confirmation.

## Optional or Fragile Sources

- Understat
  Role: football xG and xGA.
  Use when accessible, especially for stronger football shot-quality context.

- WhoScored
  Role: football ratings and match stats.
  Use when accessible, never as the only source.

## Tier A Specialist Statistical Sources (by sport)

### All Sports — Roster, Coaching, Transfers

- TransferMarkt
  Role: player transfers, coaching changes, contract details, squad values, injury histories, and player market values across ALL football leagues + some other sports.
  URL: transfermarkt.com
  Use for: COACH/ROSTER STABILITY CHECK (STEP 3 item 9). Verify coaching changes in last 5 matches, major transfers in last 14 days, loan returns, squad depth. Also useful for injury history and player availability.
  Access: OK (may require cookie consent).
  Note: CRITICAL source for the mandatory Coach/Roster Stability Check. Check before relying on form-based stats that may not reflect current squad.

### Football — Corners, Cards, Fouls

- Betaminic
  Role: corners per team, yellow cards per team, goals per team — tables and charts across ALL leagues.
  URLs: betaminic.com/statistics/corners-team-stats-tables/, yellow-cards-team-stats-tables/
  Use for: identifying high-corner or high-card teams across obscure leagues, backing O/U corner and card markets.
  Access: OK (no Cloudflare).

- TotalCorner
  Role: live corner predictions, corner handicap lines, corner totals, corner averages per match.
  URL: totalcorner.com/match/today
  Use for: corner handicap and total lines for today's matches, pre-match corner average context. Extracts 200+ matches with corner counts, goal handicaps, dangerous attacks.
  Access: OK via Playwright + totalcorner_adapter.py. Previously only 3-4 items with raw adapter, now 200+ with custom parser.

- SoccerStats
  Role: league-level corner stats, card stats, fouls, BTTS rates, O2.5 rates, team-by-team averages.
  URL: soccerstats.com/latest.asp?league={league}
  Leagues available: austria, england, england2, italy, spain, germany, france, netherlands, and 50+ more.
  Use for: league-level corner/card context, identifying leagues with extreme corner or card averages.
  Access: INTERMITTENT — sometimes returns HTTP 500. When down, use FootyStats.org team pages or Betaminic as fallback.
  Note: If SoccerStats is down, do NOT skip league-level context. Use FootyStats team-specific pages (footystats.org/teams/{team}) which sometimes work even when the main site is blocked.

### Exotic League Specialist Sources

- Soccerway
  Role: massive global football coverage — fixtures, results, standings, H2H, squad lists, referee assignments for 200+ countries and 1000+ leagues.
  URL: soccerway.com
  Use for: exotic league fixtures, results, standings, H2H (primary H2H source for exotic leagues where Flashscore H2H is thin). Squad and referee data for context.
  Access: OK (no Cloudflare). Direct page URLs by country: `/football/[country]/[league]/`.
  Coverage: Peru Liga 1, Egyptian Premier League, Uzbekistan Super League, Kings League, Algerian Ligue 1, Moroccan Botola, Saudi Pro League, UAE Pro League, Indian ISL, Vietnamese V-League, Thai League, Colombian Liga BetPlay, Chilean Primera, Paraguayan Primera, Bolivian Primera, Ecuadorian LigaPro, Costa Rican Primera, Iranian Persian Gulf Pro League, Jordanian Pro League, Kazakhstan Premier League, Georgian Erovnuli Liga, Armenian Premier League, Azerbaijani Premier League, Faroe Islands Premier League, Gibraltar National League, Kosovo Superliga, North Macedonian First League, and 150+ more.
  Note: PRIMARY source for exotic league H2H and standings when Flashscore coverage is thin.

- AiScore
  Role: live scores and statistics for obscure leagues — covers Asian, African, and South American football with match stats.
  URL: aiscore.com
  Use for: fixture discovery and basic match stats (possession, shots, corners) for leagues not covered by SoccerStats/TotalCorner. Secondary H2H source.
  Access: OK.
  Coverage: Strong in Southeast Asia (Vietnam, Thailand, Myanmar, Cambodia, Laos), Middle East (Iran, Iraq, Jordan), Central Asia (Uzbekistan, Kazakhstan, Kyrgyzstan), and Africa (Egypt, Algeria, Morocco, Nigeria).

- Xscores
  Role: Asian and African football league coverage — live scores, results, standings, and basic stats.
  URL: xscores.com
  Use for: fixture cross-validation and results for Asian/African exotic leagues. Good for H2H lookups in leagues not on Flashscore.
  Access: OK.
  Coverage: Specializes in Asian and African football. Good for Iran, Iraq, Saudi Arabia, Egypt, Algeria, Morocco, India, Bangladesh, Myanmar.

- Goaloo
  Role: Asian football coverage — live scores, odds, stats, and standings for Asian leagues.
  URL: goaloo.com
  Use for: Asian exotic league fixtures and basic stats. Odds comparison for Asian bookmakers (useful for line cross-validation).
  Access: OK.
  Coverage: J-League, K-League, Chinese Super League, Thai League, Vietnamese V-League, Indian ISL, A-League, and other Asian leagues.

- NowGoal
  Role: Asian market focused football data — live scores, odds, stats, Asian handicap lines.
  URL: nowgoal.com
  Use for: Asian exotic league coverage with Asian handicap lines. Good for Southeast Asian and East Asian football.
  Access: OK.
  Coverage: J-League, K-League, Thai League, Vietnamese V-League, Indonesian Liga 1, Malaysian Super League, Singapore Premier League, and other SEA/East Asian leagues.

- BetsAPI
  Role: API for live and upcoming events across 100+ football leagues globally — covers fixtures, results, and basic odds.
  URL: betsapi.com
  Use for: programmatic fixture discovery for exotic leagues. Useful when Flashscore doesn't list a specific league's fixtures.
  Access: Free tier available. API-based (JSON).
  Coverage: 100+ leagues including many exotic ones. Good for verifying fixture existence.

### Tennis

- TennisExplorer
  Role: player rankings, H2H records, match schedules, results, surface form, and tournament draws. Covers ATP, WTA, Challenger, and ITF Futures circuits.
  URL: tennisexplorer.com
  Use for: H2H matchup data, surface-specific records, recent form sequences. Includes Challenger and ITF draws for lower-tier coverage.
  Access: OK.

- TennisAbstract
  Role: Elo ratings, serve-return profiles, surface performance, forecasts, and matchup data.
  URL: tennisabstract.com
  Use for: Elo-based forecasts, serve/return quality, break rate analysis. Provides overall Elo + surface-specific Elo (hard=hElo, clay=cElo, grass=gElo) for 518 ATP + 519 WTA players.
  Access: OK via Playwright + tennisabstract_adapter.py. Elo table format parsed. Returns player ratings (not match fixtures).
  Note: Custom adapter needed because raw adapter cannot parse Elo table format. Output is player-level data with `source_type: tennisabstract_elo`.

- UltimateTennisStatistics
  Role: deep historical stats — Elo, serve %, return %, break rate, surface filters, H2H explorer.
  URL: ultimatetennisstatistics.com
  Use for: detailed service game and return game analysis per surface, historical Elo trends.
  Access: OK.

- TennisPrediction
  Role: model-based predictions, H2H, and match odds.
  URL: tennisprediction.com
  Use for: secondary model confirmation, H2H context.
  Access: OK.

### Basketball

- Basketball-Reference
  Role: comprehensive NBA and international stats — team/player stats, advanced metrics, pace, ratings.
  URL: basketball-reference.com
  Use for: pace, offensive/defensive ratings, historical totals averages, and matchup context.
  Access: OK.

- DunksAndThrees
  Role: NBA analytics — pace, efficiency, shooting trends, lineup data.
  URL: dunksandthrees.com
  Use for: pace and efficiency context for NBA totals.
  Access: OK.

- NBA.com
  Role: official NBA stats — player/team stats, matchup pages, pace, advanced stats, game logs.
  URL: nba.com/stats
  Use for: official pace data, team stats, player game logs. Referenced in basketball protocol.
  Access: OK (JS-heavy, may need Playwright).

- Eurobasket.com
  Role: European basketball stats — standings, team stats (PF/PA), player stats, schedules across 50+ European leagues (BBL, ACB, BSL, VTB, ABA, LNB, LBA, PLK, etc.).
  URL: eurobasket.com
  Use for: European league standings, team scoring averages, H2H context for non-NBA basketball.
  Access: OK.

- RealGM Basketball
  Role: international basketball stats — rosters, transactions, schedules, standings for NBA + European leagues.
  URL: basketball.realgm.com
  Use for: roster changes, league standings, and scheduling context for European basketball.
  Access: OK.

- Proballers.com
  Role: global basketball player and team database — career stats, team rosters, season-by-season stats across 100+ leagues worldwide.
  URL: proballers.com
  Use for: European and international league player stats, team history, roster depth for non-NBA basketball. Covers BBL, ACB, Euroleague, VTB, ABA, NBL, and many minor leagues.
  Access: OK.

### Hockey

- Hockey-Reference
  Role: NHL and international stats — team/player stats, advanced metrics, goalie save %.
  URL: hockey-reference.com
  Use for: team GF/GA, power play %, penalty kill %, goalie performance, shot quality.
  Access: OK.

- NaturalStatTrick
  Role: NHL advanced stats — xGF, Corsi, Fenwick, shot quality, 5v5 data, goalie performance.
  URL: naturalstattrick.com
  Use for: shot-quality and expected goals context for NHL totals and moneyline.
  Access: **BLOCKED** — Cloudflare "Under Attack" mode, returns 403. Replaced by MoneyPuck CSV.

- NHL.com
  Role: official NHL stats — team/player stats, standings, game previews, power play/penalty kill data.
  URL: nhl.com/stats
  Use for: official team stats, PP%/PK%, referenced in hockey protocol.
  Access: OK.

- MoneyPuck
  Role: **PRIMARY** NHL advanced stats source — xG%, Corsi%, Fenwick%, high-danger chances, PDO, shooting%, save%. Free CSV API, no auth.
  URL: moneypuck.com/moneypuck/playerData/seasonSummary/{season}/{type}/teams.csv
  Use for: all NHL advanced metrics. 37 normalized stat keys per team, 5 situations. 12h cache. Integrated in deep_stats_report.py enrichment.
  Access: FREE CSV, no Cloudflare. Must use requests (not Playwright — triggers download error).
  Client: `scripts/api_clients/moneypuck_client.py`
  Adapter: `scripts/adapters/moneypuck_adapter.py`

- HockeyDB
  Role: historical hockey stats, player careers, team history.
  URL: hockeydb.com
  Use for: roster context and historical team performance.
  Access: OK.

- DailyFaceoff
  Role: NHL starting goalie confirmations, line combinations, depth charts.
  URL: dailyfaceoff.com
  Use for: confirming starting goalies (CRITICAL for totals picks — goalie change invalidates thesis). Also shows line combos and PP units.
  Access: OK.
  Note: Goalie confirmations typically posted 2-4h before puck drop. Check as part of STEP 3B time-sensitive data collection.

- EliteProspects.com
  Role: comprehensive hockey player database — player profiles, career stats, team rosters across NHL, KHL, SHL, DEL, Liiga, Czech Extraliga, Swiss NL, and 50+ leagues worldwide.
  URL: eliteprospects.com
  Use for: player depth, roster changes, prospect tracking, team roster context for European hockey leagues. Covers all levels from junior to professional.
  Access: OK.

- Eurohockey.com
  Role: European hockey league coverage — standings, schedules, results, team stats for SHL, DEL, Liiga, Czech Extraliga, Swiss NL, EIHL, ICE Hockey League, and more.
  URL: eurohockey.com
  Use for: European hockey league standings, scheduling, and results cross-validation. Good for non-NHL hockey context.
  Access: OK.

### Volleyball

- BetExplorer (Volleyball section)
  Role: volleyball odds comparison — moneyline, set totals O/U (3.5, 4.5), point totals O/U (172.5–180.5), Asian handicap.
  URL: betexplorer.com/volleyball/
  Use for: price comparison across bookmakers including Betclic, market depth check.
  Access: OK.

- Flashscore (Volleyball section)
  Role: volleyball schedules, live scores, results, H2H.
  URL: flashscore.com/volleyball/
  Use for: fixture confirmation, results, and settlement.
  Access: OK.

- Sofascore (Volleyball section)
  Role: ARCHIVED — blocked by Cloudflare WAF (403).
  URL: sofascore.com/volleyball
  Status: DISABLED. Use Flashscore volleyball section instead.

- CEV (Confédération Européenne de Volleyball)
  Role: official European volleyball — Champions League, CEV Cup results, team stats, standings.
  URL: cev.eu
  Use for: European club competition context, standings, team stats. Referenced in volleyball protocol.
  Access: OK.

- PlusLiga
  Role: official Polish volleyball league — standings, stats, team rosters, match reports.
  URL: plusliga.pl
  Use for: Polish volleyball context — team form, player stats, standings. Relevant for Betclic PL market.
  Access: OK.

- VolleyballWorld.com
  Role: official FIVB platform — international volleyball competitions, world rankings, team stats, match results, tournament schedules.
  URL: volleyballworld.com
  Use for: international competition context (Nations League, World Championship, Olympic qualifiers), team world rankings, and official match stats.
  Access: OK.

### Multi-Sport Odds and Analytics

- Covers
  Role: expert previews, odds, and picks for NBA, NHL, and more.
  URL: covers.com
  Use for: narrative and preview context for US sports.
  Access: OK.

- StatMuse
  Role: natural language sports queries — NBA, NHL stats on demand.
  URL: statmuse.com
  Use for: quick stat lookups across multiple sports.
  Access: OK.

### Cross-Sport Fixture and Draw Sources (for Deep Scan Protocol §1.2)

These sources help ensure NO tournament or event is missed during the scan phase:

- ATP Tour (Official)
  Role: official tournament draws, order of play, live scores.
  URL: atptour.com/en/scores/current
  Use for: confirming full R1/R2 draw for ATP events — ensures no match is missed. Shows exact schedule.
  Access: OK.

- WTA Tour (Official)
  Role: official tournament draws, order of play, live scores.
  URL: wtatennis.com/scores
  Use for: confirming full WTA tournament draw — same as ATP but for women's tour.
  Access: OK.

- Sofascore (All Sports)
  Role: ARCHIVED — blocked by Cloudflare WAF (403). All API endpoints return HTTP 403.
  URL: sofascore.com
  Status: DISABLED. Use Flashscore + ESPN for cross-validation.
  Blocked: 2026-05-13.

- LiveScore
  Role: multi-sport live scores and fixtures — football, tennis, basketball, hockey, cricket.
  URL: livescore.com
  Use for: secondary fixture cross-check, especially for Asian/South American football.
  Access: OK.

- Oddspedia — BLOCKED (Cloudflare 403). Do not use.

### Blocked Sources (verified 2026-04-23)

Do NOT attempt to fetch these — they waste time and produce no data:

**Tier A (former):**
- Oddspedia (oddspedia.com) — Cloudflare 403. Removed from Tier A markets.

**Geoblocked from EU/PL IP (US-only sportsbooks):**
- OddsChecker (oddschecker.com) — empty response from EU. Works from US IP only.
- DraftKings (sportsbook.draftkings.com) — geoblocked, empty response.
- FanDuel (sportsbook.fanduel.com) — geoblocked, empty response.
- Betfair Exchange (betfair.com) — geoblocked, empty response.
- Pinnacle (pinnacle.com) — timeout/geoblocked.

**Tier B (former):**
- ~~Forebet (forebet.com)~~ — **FIXED**: accessible via Playwright + forebet_adapter.py. Moved to active sources.
- SportyTrader (sportytrader.com) — blocked. Was football previews.
- PredictZ (predictz.com) — redirect/block. Was football scoreline support.
- BettingExpert (bettingexpert.com) — navigation leak/broken. Was tipster sentiment.
- ProTipster (protipster.com) — Cloudflare 403. Was tipster aggregation.
- FootySupertips (footysupertips.com) — DNS dead ERR_NAME_NOT_RESOLVED.
- Windrawwin (windrawwin.com) — 403 Forbidden.
- Trafiamy (trafiamy.pl) — domain dead/not resolving.
- Blogabet (blogabet.com) — requires login; not automatable.

**Stats sources:**
- FootyStats (footystats.org) — 403 on main pages. HOWEVER: individual team/match pages (e.g., footystats.org/teams/{team-slug}) sometimes work via Playwright. Use as SoccerStats fallback for fouls, cards, and team-level stats when SoccerStats is down (HTTP 500). NOT reliable as primary source.
- FBRef (fbref.com) — 403
- FCTables (fctables.com) — 403
- ~~WhoScored (whoscored.com)~~ — **FIXED**: accessible via Playwright (425k chars). Added to scan URLs.
- KenPom (kenpom.com) — blocked
- ActionNetwork (actionnetwork.com) — blocked
- VolleyBox (volleybox.net) — blocked

**Partial (availability noted in main entries above):**
- Covers (covers.com) — NBA pages return empty; other sections partial. See Tier A entry.
- TeamRankings (teamrankings.com) — inconsistently blocked. See Tier A entry.

## Sport Playbooks

### Odds Source Map by Sport (verified 2026-04-23)

Use this table to know WHERE to get odds for each sport. Never give up after one source.

| Sport | Primary Odds | Secondary Odds | Tertiary Odds | Fallback |
|-------|-------------|----------------|---------------|----------|
| **Football** (EU) | The-Odds-API | odds-api.io | API-Football-Odds | SBR (manual) |
| **Football** (Exotic) | The-Odds-API | odds-api.io | API-Football-Odds | — |
| **NHL** | SBR (Totals tab) | ESPN Odds | ScoresAndOdds | The-Odds-API |
| **NBA** | SBR (Totals tab) | ESPN Odds | ScoresAndOdds | The-Odds-API |
| **Tennis** | The-Odds-API | odds-api.io | — | — |
| **Volleyball** | odds-api.io (primary) | — | — | — |

**Rule:** If all sources in the row fail for a pick → do NOT skip. Try The-Odds-API or search for a new source. The internet always has odds data somewhere.

### Sport-Specific Playbooks

- Football
  Minimum stack: Flashscore + BetExplorer or OddsPortal + SoccerStats (league context) + TotalCorner (match corners).
  Tipster cross-check: Zawod Typer, Typersi, BetIdeas, PicksWise, Tipstrr.
  Specialist sources: Betaminic (corners/cards tables), Betclic Statystyki (top leagues only), TransferMarkt (coaching changes, transfers).
  Lower-division coverage: Soccerway (200+ countries, 1000+ leagues) + AiScore/Xscores (Asian/African stats) + Goaloo/NowGoal (Asian coverage). Use when SoccerStats/TotalCorner have no data for the league. BetsAPI for programmatic fixture discovery of ultra-exotic leagues.
  Preferred markets: fouls > cards > corners > shots > team totals > BTTS > U2.5 > O2.5 > DC/DNB > 1X2 (LAST RESORT).

- Basketball
  Minimum stack: Basketball-Reference + **SBR or ESPN or ScoresAndOdds** (totals/spreads) + BetExplorer.
  Tipster cross-check: PicksWise, Tipstrr.
  European coverage: Eurobasket.com (50+ European leagues — BBL, ACB, BSL, VTB, ABA, LNB, LBA, PLK) + RealGM Basketball (rosters, transactions) + Proballers.com (player stats, team history across European leagues).
  Preferred markets: team totals > quarter totals > game totals > spreads > moneyline (LAST RESORT).

- Hockey
  Minimum stack: Hockey-Reference + **SBR or ESPN or ScoresAndOdds** (totals/puck line) + **MoneyPuck** for xG/Corsi/Fenwick (NaturalStatTrick BLOCKED by Cloudflare).
  Tipster cross-check: PicksWise.
  European coverage: EliteProspects.com (player profiles, team rosters for SHL, DEL, Liiga, Czech Extraliga, Swiss NL, KHL) + HockeyDB.com (historical stats, player careers) + Eurohockey.com (European league standings, schedules, results).
  Preferred markets: period totals > game totals > puck line > moneyline (LAST RESORT).

- Tennis
  Minimum stack: TennisAbstract (Elo via `fetch_tennis_elo.py`) + TennisExplorer (fixture discovery, 302+ matches/page) + ESPN (L10 form + H2H via `enrich_tennis_stats.py`) + BetExplorer or OddsPortal.
  New: ATP Tour adapter (`atptour_adapter.py`) for scores/rankings (requires Playwright).
  Tipster cross-check: Zawod Typer, Tipstrr.
  Elo integration: `lookup_tennis_elo()` in `compute_safety_scores.py` reads cached Elo data, adds +1 to data quality score.
  H2H enrichment: `enrich_tennis_stats.py` with `--verbose` fetches ESPN athlete-vs-athlete API data.
  Challenger/ITF coverage: TennisExplorer covers Challenger and ITF Futures draws. UltimateTennisStatistics provides surface-specific Elo for lower-ranked players. Flashscore lists all ITF events.
  Preferred markets: game totals O/U (PRIMARY) > set totals O/U > game handicap > set handicap > moneyline (LAST RESORT — only 1.50-2.50 range + STRONG odds ratio + surface + H2H dominance).
  **ABSOLUTE RULE**: NEVER default to ML in tennis. Statistical markets have ~65% hit rate vs ML ~58%. Always prefer games/sets.

- Volleyball
  Minimum stack: BetExplorer volleyball section + Flashscore.
  Tipster cross-check: Tipstrr.
  Enhanced coverage: VolleyballWorld.com (official FIVB — international competitions, world rankings, team stats) + CEV.eu (European club competitions — Champions League, CEV Cup) + PlusLiga.pl (Polish league).
  Preferred markets: set totals > point totals > set handicap > moneyline (LAST RESORT).

### Exotic League Coverage Map

Use this table to know WHERE to get data for exotic football leagues. "Betclic" column indicates known market availability (✅ = markets exist, ❓ = check manually, ❌ = no markets).

#### South America
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|
| Liga 1 | Peru | ✅ | ✅ | ✅ | ✅ | ❓ |
| Liga BetPlay | Colombia | ✅ | ✅ | ✅ | ✅ | ❓ |
| Primera División | Chile | ✅ | ✅ | ✅ | ✅ | ❓ |
| División Profesional | Paraguay | ✅ | ✅ | ✅ | ✅ | ❓ |
| Primera División | Bolivia | ✅ | ✅ | ❓ | ✅ | ❓ |
| LigaPro | Ecuador | ✅ | ✅ | ✅ | ✅ | ❓ |
| Primera División | Costa Rica | ✅ | ✅ | ❓ | ✅ | ❓ |
| Liga Nacional | Guatemala | ✅ | ❓ | ❓ | ✅ | ❓ |
| Liga Nacional | Honduras | ✅ | ❓ | ❓ | ✅ | ❓ |
| Primera División | El Salvador | ✅ | ❓ | ❓ | ✅ | ❓ |

#### Africa & Middle East
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | AiScore | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|---------|
| Egyptian Premier League | Egypt | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Ligue 1 | Algeria | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Botola Pro | Morocco | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Saudi Pro League | Saudi Arabia | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| UAE Pro League | UAE | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Persian Gulf Pro League | Iran | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Stars League | Iraq | ✅ | ❓ | ❓ | ✅ | ✅ | ❓ |
| Pro League | Jordan | ✅ | ❓ | ❓ | ✅ | ✅ | ❓ |

#### Asia & Oceania
| League | Country | Flashscore | Sofascore | BetExplorer | Goaloo | NowGoal | Betclic |
|--------|---------|------------|-----------|-------------|--------|---------|---------|
| ISL / I-League | India | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| V-League | Vietnam | ✅ | ✅ | ❓ | ✅ | ✅ | ❓ |
| Thai League | Thailand | ✅ | ✅ | ❓ | ✅ | ✅ | ❓ |
| Super League | Uzbekistan | ✅ | ✅ | ❓ | ❓ | ❓ | ❓ |
| Premier League | Kazakhstan | ✅ | ✅ | ✅ | ❓ | ❓ | ❓ |
| Premier League | Bangladesh | ✅ | ❓ | ❓ | ❓ | ❓ | ❓ |
| National League | Myanmar | ✅ | ❓ | ❓ | ❓ | ✅ | ❓ |
| C-League | Cambodia | ❓ | ❓ | ❓ | ❓ | ✅ | ❓ |
| Premier League | Laos | ❓ | ❓ | ❓ | ❓ | ❓ | ❓ |

#### Central Asia & Caucasus
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|
| Premier League | Kazakhstan | ✅ | ✅ | ✅ | ✅ | ❓ |
| Premier League | Kyrgyzstan | ✅ | ❓ | ❓ | ✅ | ❓ |
| Vysshaya Liga | Tajikistan | ✅ | ❓ | ❓ | ✅ | ❓ |
| Ýokary Liga | Turkmenistan | ❓ | ❓ | ❓ | ✅ | ❓ |
| Erovnuli Liga | Georgia | ✅ | ✅ | ✅ | ✅ | ❓ |
| Premier League | Armenia | ✅ | ✅ | ✅ | ✅ | ❓ |
| Premier League | Azerbaijan | ✅ | ✅ | ✅ | ✅ | ❓ |

#### European Micro/Minor Leagues
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|
| Betrideildin | Faroe Islands | ✅ | ✅ | ✅ | ✅ | ❓ |
| National League | Gibraltar | ✅ | ✅ | ❓ | ✅ | ❓ |
| Primera Divisió | Andorra | ✅ | ❓ | ❓ | ✅ | ❓ |
| Campionato | San Marino | ✅ | ❓ | ❓ | ✅ | ❓ |
| Superliga | Kosovo | ✅ | ✅ | ✅ | ✅ | ❓ |
| First League | North Macedonia | ✅ | ✅ | ✅ | ✅ | ❓ |

#### Entertainment Leagues
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|
| Kings League | Spain | ✅ | ✅ | ❓ | ❓ | ❓ |

**Note:** ❓ = verify manually on the source website or Betclic app before analysis. Kings League uses modified rules (shorter halves, special gameplay mechanics) — see §1.7 for protocol.

## Deprecated / Broken Sources

These API clients are formally deprecated and removed from all fallback chains. Files are retained for reference but their `get_fixtures()` methods return `[]` immediately. Do NOT re-enable without verifying the underlying service is restored.

- BallDontLie API
  Role: free NBA stats API — game results, player box scores, season averages.
  Client: `scripts/api_clients/balldontlie.py`
  Status: **DEPRECATED 2026-05-13.** v1 API migrated to paid model. 100% failure rate since 2026-05-11.
  Reason: BallDontLie v1 API is fully deprecated. Free tier no longer available. Requires paid API key.
  Replacement: `nba_api` Python package (registered as `nba-api` in CLIENT_REGISTRY) + ESPN Basketball.
  `_HOST_BROKEN = True`. Removed from CLIENT_REGISTRY. File retained for nba_api fallback methods.

- TheSportsDB
  Role: universal sports fixture database — fixtures, results, team info across all sports.
  Client: `scripts/api_clients/thesportsdb.py`
  Status: **DEPRECATED 2026-05-13.** Free tier (key "3") has 97.8% failure rate since 2026-05-11.
  Reason: Free API appears deprecated or severely rate-limited. Premium keys may work but are untested.
  Replacement: ESPN API (free, unlimited) + Flashscore (Playwright) for fixture discovery.
  `_HOST_BROKEN = True`. Removed from CLIENT_REGISTRY.

- API-Tennis (api-sports.io)
  Role: tennis statistics API — player rankings, match results, H2H, surface-specific form.
  Client: `scripts/api_clients/api_tennis.py`
  Status: **DEPRECATED 2026-05-13.** v1.tennis.api-sports.io returns NXDOMAIN (host does not resolve).
  Reason: DNS resolution failure. API may have been discontinued or moved to a different host.
  Replacement: ESPN Tennis + TennisAbstract Elo + TennisExplorer for fixture/H2H/stats.
  `_HOST_BROKEN = True`. Removed from CLIENT_REGISTRY.

## Settlement Sources

- Primary settlement sources: Flashscore.
- Secondary settlement sources: bookmaker settled market plus OddsPortal or BetExplorer archived results.
- Use two sources whenever possible.
- If only one reliable source is available, note it explicitly in the daily report and ledger notes.

## Hard Source Rules

- A final pick must have at least one Tier A stats or fixture source and one Tier A market or price source.
- Tier B sources can strengthen or weaken confidence by at most one level, but they cannot create a bet on their own.
- Community sources (Zawod Typer, Typersi, Meczyki, OLBG, PicksWise, BetIdeas, Sportsgambler, Tipstrr) can adjust confidence by ±1 level based on consensus alignment/divergence, but cannot be the primary reason for a pick.
- However, strong consensus from multiple tipster sites IS a valid supporting signal — it provides angles and perspectives that statistics alone may miss.
- If Tier A sources materially disagree on the core read, skip the bet unless the disagreement is clearly explained and the stake is reduced.
- If the only support comes from a single consensus or tipster page with no statistical backing, skip the bet.
- If community consensus strongly diverges from Tier A direction (≥60% opposite), note the divergence in the report and investigate before proceeding.
- Never reject a sport for "lack of sources" — search specialist sites (see Sport Playbooks above). Each of the 5 pipeline sports has ≥4 dedicated sources.
- Record source outages and partial availability in the daily source log.

## Internal Data Sources (Historical Learning)

- Betclic Bet History
  File: `betting/data/betclic_bets_history.json`
  Parser: `scripts/parse_betclic_bets.py` (from HTML export of betclic.pl/my-bets)
  Analyzer: `scripts/analyze_betclic_learning.py`
  Role: Ground truth for all actually placed bets. Contains 141 coupons, 469 legs (13.04–27.04.2026).
  Use for: §0.2 Historical Learning Query, market hit rate checks, coupon killer analysis, sport performance validation.
  Key findings: Statistical markets 67% vs outcome markets 46%. Corners 73%. Match winner 37%. AKO(5+) 0% win rate.
  Refresh: Re-export from betclic.pl/my-bets when needed.
- Bookmaker bonuses, promos, and affiliate content are irrelevant to pick quality.