# Betting Source Registry

Purpose: use sources by role, not by raw count. The internet is rich with statistics, analysis, and prediction sites for every sport. Never reject a sport for "lack of sources" — search for specialized sources instead.

## Source Philosophy

Every sport has dedicated communities, statistical databases, and prediction sites. The workflow must:
1. Use Tier A statistical and market sources as the analytical backbone.
2. Use Tier B tipster/community sites to validate direction, discover angles, and check consensus.
3. Use Tier C niche/specialist sites for sport-specific deep dives.
4. Never reject a sport solely because the orchestrator didn't find data — manually search specialist sources.

## Tier A Core Market and Price Sources

- Betclic
  Role: execution price and available markets.
  Use for: the exact bookmaker odds and stake plan.
  Never use for: main analytical justification.
  Access: 403 blocks automated access. All picks CONDITIONAL — user verifies on app.

- OddsPortal
  Role: market-best price, line shopping, dropping odds, value bets, archived results, standings.
  Use for: best-market comparison, price_gap_pct, movement context, and result backchecks.
  Access: OK.

- BetExplorer
  Role: odds comparison, results, streaks, popular bets, and odds movements.
  Use for: bookmaker comparison, results history, and market heat checks.
  Access: OK.

- SportsbookReview (SBR)
  Role: US-sport odds comparison — NHL, NBA, MLB, NFL. Moneyline, spread, AND totals tabs with lines from 6+ books.
  URL: sportsbookreview.com/betting-odds/{sport}/
  Sport slugs: nhl-hockey, nba-basketball, mlb-baseball, nfl-football, college-football, college-basketball.
  Use for: totals lines + prices for US sports (the "Totals" tab shows O/U line + American odds per book).
  Access: OK (no GDPR wall, renders in Playwright). Click "Totals" tab for O/U.
  Coverage: NHL, NBA, MLB, NFL, college sports only.
  American-to-decimal conversion: positive +X → 1 + X/100; negative -X → 1 + 100/X.
  Added: 2026-04-23.

- ESPN Odds
  Role: US-sport odds — NHL, NBA, MLB. Shows moneyline, spread, totals with lines and American odds.
  URL: espn.com/{sport}/odds (sport = nhl, nba, mlb)
  Use for: cross-validation of US sport totals and moneylines. Shows team records inline.
  Access: OK from EU/PL IP. No soccer or tennis odds available.
  Coverage: NHL, NBA, MLB, NFL only.
  Added: 2026-04-23.

- ScoresAndOdds
  Role: US-sport odds comparison with line movements — NHL, NBA, MLB, NFL.
  URL: scoresandodds.com/{sport} (sport = nhl, nba, mlb, nfl)
  Use for: totals lines, moneyline, puck/run/point line, line movement tracking. Shows opening vs current odds.
  Access: OK from EU/PL IP. Renders in Playwright. Has "LINE MOVEMENTS" column.
  Coverage: NHL, NBA, MLB, NFL only.
  Added: 2026-04-23.

- The-Odds-API
  Role: universal odds API — ALL sports globally. Returns JSON with odds from multiple bookmakers.
  URL: api.the-odds-api.com/v4/sports/{sport}/odds?regions={region}&markets={markets}&apiKey={key}
  Use for: programmatic odds retrieval for ANY sport when manual scraping fails. Supports h2h, spreads, totals.
  Access: free tier (500 credits/month). API key in config/odds_api_key.txt or ODDS_API_KEY env var.
  Coverage: MLB, NBA, NHL, NFL, EPL, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Ekstraklasa, MLS, tennis Grand Slams, MMA, and 70+ more.
  NOT covered: volleyball, esports, snooker, darts, table tennis, handball, padel, speedway (fallback sources — OddsPortal, BetExplorer, Betclic — now handle these via the multi-source system).
  Script: `python3 scripts/fetch_odds_api.py` — fetches all sports, saves to betting/data/odds_api_snapshot.json + odds_api_summary.csv.
  Commands: `--list-sports` (free, 0 credits), `--sports baseball,hockey` (filter), `--scores baseball` (settlement).
  Quota: 1 credit per sport×market×region. Full scan (14 sport groups × h2h+totals × eu) ≈ 30 credits. ~16 full scans/month on free tier.
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

## Tier A Core Stats, Fixture, and Verification Sources

- Flashscore
  Role: schedules, lineups, H2H, live stats, xG and match statistics where available, and results.
  Use for: fixture confirmation, pre-match context, and settlement verification.

- Sofascore
  Role: schedules, team form, player ratings, lineups, H2H, dropping or rising odds, and cross-sport stats.
  Use for: pre-match context, verification, extra stats, and line movement cross-check.

- Covers
  Role: expert-written previews for US sports and big markets.
  Use for: NHL, MLB, NFL, and UFC support and narrative checks.
  Access: PARTIAL — NBA pages return empty; other sections intermittent. Do not rely as sole source.

- TeamRankings
  Role: algorithmic picks, rankings, trends, injuries, matchup pages, and efficiency stats.
  Use for: NBA, MLB, NFL, and college sports, especially totals and spread context.
  Access: INTERMITTENT — sometimes blocked. Do not rely as sole source. When available, useful for totals context.

- TennisAbstract
  Role: tennis Elo, matchup data, serve-return profiles, forecasts, and surface context.
  Use for: tennis moneyline, set handicap, game or set totals, and form quality.

- Sportsgambler
  Role: multi-sport written previews with lineups, injuries, and advanced metrics.
  Use for: football plus North American sports when a fresh preview is needed.

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
  Fallback: BallDontLie → nba_api (NBA only).
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
  Use for: NBA statistical analysis as fallback when API-Basketball quota exhausted.
  Access: free tier (requires key). API key in config/api_keys.json or BALLDONTLIE_KEY env var.
  Coverage: NBA only.
  Added: 2026-04-28.

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

- API-Tennis (custom client)
  Role: tennis statistics API client — player rankings, match results, H2H, surface-specific form.
  Use for: L10/L5/H2H statistical data for tennis game totals, set totals, and serve/return markets.
  Script: `python3 scripts/fetch_api_stats.py --sports tennis` (uses `api_clients/api_tennis.py`)
  Fallback: TheSportsDB → Playwright (TennisExplorer, TennisAbstract).
  Added: 2026-04-30.

- API-Volleyball (custom client)
  Role: volleyball statistics API client — team stats, match results, set scores, point totals.
  Use for: L10/L5/H2H statistical data for volleyball set totals, point totals, and set handicap markets.
  Script: `python3 scripts/fetch_api_stats.py --sports volleyball` (uses `api_clients/api_volleyball.py`)
  Fallback: TheSportsDB → Playwright (Flashscore, Sofascore).
  Added: 2026-04-30.

- API-Handball (custom client)
  Role: handball statistics API client — team stats, match results, half-time scores, goal totals.
  Use for: L10/L5/H2H statistical data for handball half totals, game totals, and team total markets.
  Script: `python3 scripts/fetch_api_stats.py --sports handball` (uses `api_clients/api_handball.py`)
  Fallback: TheSportsDB → Playwright (EHF, Handball-World).
  Added: 2026-04-30.

- API-Baseball (custom client)
  Role: baseball statistics API client — team stats, pitcher data, game results, run totals.
  Use for: L10/L5/H2H statistical data for baseball F5 totals, team totals, and run line markets.
  Script: `python3 scripts/fetch_api_stats.py --sports baseball` (uses `api_clients/api_baseball.py`)
  Fallback: TheSportsDB → Playwright (BaseballSavant, ESPN).
  Added: 2026-04-30.

- TheSportsDB
  Role: universal sports fixture database — covers ALL sports with basic fixture/result data.
  Use for: fixture discovery for sports without API-Sports.io coverage (volleyball, tennis, handball, etc.). No per-match stats.
  Access: free tier (~100 req/day). Key "3" for free tier.
  Coverage: All sports globally — but basic data only (fixtures, results, team info).
  Added: 2026-04-28.

### API Fallback Chains

```
Football:   API-Football → Football-Data.org → Understat (xG only) → Playwright
Basketball: API-Basketball → BallDontLie → nba_api (NBA only) → Playwright
Hockey:     API-Hockey → Playwright
Tennis:     API-Tennis (api_clients/api_tennis.py) → TheSportsDB → Playwright
Volleyball: API-Volleyball (api_clients/api_volleyball.py) → TheSportsDB → Playwright
Handball:   API-Handball (api_clients/api_handball.py) → TheSportsDB → Playwright
Baseball:   API-Baseball (api_clients/api_baseball.py) → TheSportsDB → Playwright
Other:      TheSportsDB (fixtures only) → Playwright
```

### Daily API Budget (~776 requests)

| API | Daily Limit | Typical Use | Reserve |
|-----|-------------|-------------|---------|
| API-Football | 100 | 70 | 30 |
| API-Basketball | 100 | 60 | 40 |
| API-Hockey | 100 | 50 | 50 |
| Football-Data.org | ~1000 | 200 | 800 |
| BallDontLie | ~1000 | 100 | 900 |
| nba_api | ~1800/hr | 200 | 1600 |
| TheSportsDB | ~100 | 30 | 70 |
| Understat | unlimited | 50 | — |
| The Odds API | ~16/day | 16 | 0 |

## Weather Data Source

- Open-Meteo
  Role: free weather API — temperature, precipitation, wind speed, weather conditions by geographic coordinates.
  URL: api.open-meteo.com/v1/forecast
  Use for: STEP 3B weather impact assessment for outdoor sports (football, tennis, baseball, speedway). No API key required.
  Script: `python3 scripts/fetch_weather.py --date YYYY-MM-DD` — fetches weather data for all outdoor event venues.
  Access: free (no key, no registration). Rate limit ~10,000 req/day.
  Coverage: Global. Hourly forecast data for any latitude/longitude.
  Integration: Run as part of STEP 3B (time-sensitive data). Output used to assess wind/rain impact on statistical markets (e.g., rain → fewer corners, wind → fewer goals in football).
  Added: 2026-04-30.

## Scan Adapters (Structured Parsing)

These adapters provide structured data extraction from web sources, normalizing raw HTML into fixture/stats JSON format used by the pipeline. They are invoked by `run_full_scan_and_prepare.sh` and `deep_link_discovery.py`.

- soccerway_adapter.py (`scripts/adapters/soccerway_adapter.py`)
  Role: structured parser for Soccerway pages — extracts fixtures, results, standings, H2H, and squad data.
  Use for: exotic league fixture discovery and H2H extraction. Covers 200+ countries and 1000+ leagues.
  Input: Soccerway URLs (e.g., `/football/[country]/[league]/`)
  Output: normalized fixture/stats JSON for the analysis pool.
  Added: 2026-04-30.

- tennisexplorer_adapter.py (`scripts/adapters/tennisexplorer_adapter.py`)
  Role: structured parser for TennisExplorer pages — extracts player H2H, surface form, rankings, and match schedules.
  Use for: tennis H2H extraction with surface filtering, player ranking verification.
  Input: TennisExplorer URLs (player pages, H2H pages, tournament draws)
  Output: normalized player stats and H2H data for tennis analysis.
  Added: 2026-04-30.

- soccerstats_adapter.py (`scripts/adapters/soccerstats_adapter.py`)
  Role: structured parser for SoccerStats pages — extracts league-level corner, card, foul, and BTTS statistics.
  Use for: league-level statistical context for football corner/card/foul markets.
  Input: SoccerStats league URLs (e.g., `/latest.asp?league={league}`)
  Output: normalized league statistics (team averages for corners, cards, fouls, goals).
  Added: 2026-04-30.

### Odds Cross-Validation Sources (Multi-Source System)

The multi-source odds aggregator (`fetch_odds_multi.py`) tries sources in priority order per sport, merging events and deduplicating bookmakers:

| Sport | Source 1 | Source 2 | Source 3 | Source 4 | Source 5 |
|-------|----------|----------|----------|----------|----------|
| football | The Odds API | API-Football /odds | OddsPortal | BetExplorer | Betclic |
| tennis | The Odds API | OddsPortal | BetExplorer | Betclic | — |
| basketball | The Odds API | OddsPortal | BetExplorer | Betclic | — |
| hockey | The Odds API | OddsPortal | BetExplorer | Betclic | — |
| baseball | The Odds API | OddsPortal | BetExplorer | Betclic | — |
| mma | The Odds API | OddsPortal | BetExplorer | Betclic | — |
| volleyball | OddsPortal | BetExplorer | Betclic | — | — |
| handball | OddsPortal | BetExplorer | Betclic | — | — |
| esports | OddsPortal | BetExplorer | Betclic | — | — |
| snooker | OddsPortal | BetExplorer | Betclic | — | — |
| darts | OddsPortal | BetExplorer | Betclic | — | — |
| table_tennis | OddsPortal | BetExplorer | Betclic | — | — |
| padel | BetExplorer | Betclic | — | — | — |
| speedway | BetExplorer | Betclic | — | — | — |

Script: `python3 scripts/fetch_odds_multi.py`
Commands: `--sports volleyball` (filter sport), `--sources the-odds-api,oddsportal` (filter sources), `--dry-run` (show plan only), `--no-window` (all events).
Outputs: `betting/data/odds_api_snapshot.json` (backward compatible), `betting/data/odds_api_summary.csv`, `betting/data/odds_multi_sources.json` (provenance log).
Added: 2026-04-29.

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
  Role: ARGUMENT-BASED expert analysis — detailed game previews with reasoning for NBA, NHL, MLB, NFL, tennis, soccer.
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
  Role: algorithmic football predictions — mathematical model covering 500+ leagues with probability, predicted score, odds value.
  URL: forebet.com
  Use for: model-based predictions for exotic leagues. Shows predicted score, probability %, and whether odds represent value.
  Access: OK (previously blocked but now accessible via direct league pages).
  Coverage: 500+ leagues globally including most exotic leagues.
  **Deep-dive required**: NO — model output, not human analysis. Use for direction confirmation.
  Note: If main page is blocked, try direct league pages: forebet.com/en/football-predictions/predictions-[country]/

- WhoScored Predictions
  Role: data-driven match previews and predictions with statistical context.
  URL: whoscored.com/Previews
  Use for: match previews for larger exotic leagues (Egyptian Premier, Saudi Pro, Indian ISL).
  Access: PARTIAL — may be blocked on some pages. Try direct match URLs.
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
  Use for: corner handicap and total lines for today's matches, pre-match corner average context.
  Access: OK (no Cloudflare).

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
  Use for: programmatic fixture discovery for exotic leagues. Useful when Flashscore/Sofascore don't list a specific league's fixtures.
  Access: Free tier available. API-based (JSON).
  Coverage: 100+ leagues including many exotic ones. Good for verifying fixture existence.

### Tennis

- TennisExplorer
  Role: player rankings, H2H records, match schedules, results, surface form, and tournament draws.
  URL: tennisexplorer.com
  Use for: H2H matchup data, surface-specific records, recent form sequences.
  Access: OK.

- TennisAbstract
  Role: Elo ratings, serve-return profiles, surface performance, forecasts, and matchup data.
  URL: tennisabstract.com
  Use for: Elo-based forecasts, serve/return quality, break rate analysis.
  Access: OK.

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
  Access: OK.

- NHL.com
  Role: official NHL stats — team/player stats, standings, game previews, power play/penalty kill data.
  URL: nhl.com/stats
  Use for: official team stats, PP%/PK%, referenced in hockey protocol.
  Access: OK.

- MoneyPuck
  Role: NHL expected goals models, win probability, game predictions, player cards.
  URL: moneypuck.com
  Use for: model-based NHL game predictions and xG totals context.
  Access: OK.

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

### Baseball

- BaseballSavant (Statcast)
  Role: MLB Statcast data — exit velocity, launch angle, pitch movement, sprint speed, expected stats.
  URL: baseballsavant.mlb.com
  Use for: pitcher quality (xERA, xFIP), hitter quality (xwOBA, barrel%), and totals context.
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
  Role: volleyball team form, player stats, match stats.
  URL: sofascore.com/volleyball
  Use for: form context and match analysis.
  Access: OK.

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

### Esports

- HLTV
  Role: CS2 statistics, team rankings, match history, player stats, map veto patterns, event schedules.
  URL: hltv.org
  Use for: CS2 moneyline, map handicap, map totals. Team rankings, recent form, map pool analysis.
  Access: PARTIAL — statistics pages work, but tips/predictions pages return 403. Use for STATS ONLY, not tips.
  Note: HLTV tips are BLOCKED (listed in copilot-instructions blocked tipster list). Use stats pages only (rankings, match history, player data). For esports tips/predictions, use GosuGamers instead.

- Liquipedia
  Role: comprehensive esports wiki — CS2, Dota 2, League of Legends, Valorant, StarCraft, Rocket League. Tournament brackets, team rosters, match history.
  URL: liquipedia.net
  Use for: tournament context, roster changes, bracket paths, format context.
  Access: OK.

- VLR.gg
  Role: Valorant statistics — team stats, player stats, match history, event coverage.
  URL: vlr.gg
  Use for: Valorant map stats, team form, head-to-head.
  Access: OK.

- GosuGamers
  Role: esports match schedule, odds comparison, community predictions, and results across CS2, Dota 2, LoL, Valorant.
  URL: gosugamers.net
  Use for: esports consensus, odds comparison, and match scheduling.
  Access: OK.

- Esports Charts
  Role: esports viewership and popularity data — useful for identifying high-stakes matches.
  URL: escharts.com
  Use for: identifying Tier 1 vs Tier 2 events (higher tier = more reliable data).
  Access: OK.

- BO3.gg
  Role: CS2 match predictions with model confidence, map stats, head-to-head.
  URL: bo3.gg
  Use for: CS2 map predictions, win probabilities, match analysis.
  Access: OK.

### Snooker

- CueTracker
  Role: snooker statistics — player rankings, tournament history, head-to-head records, frame averages, century breaks.
  URL: cuetracker.net
  Use for: H2H analysis, frame averages, scoring patterns, tournament form.
  Access: OK.

- SnookerOrg
  Role: live scores, rankings, draw brackets, season statistics.
  URL: snooker.org
  Use for: live fixtures, draw context, ranking points context.
  Access: OK.

- WorldSnooker (WST)
  Role: official World Snooker Tour — tournament schedules, results, player profiles.
  URL: wst.tv
  Use for: official schedule, tournament format (best-of-X frames), and player news.
  Access: OK.

### Table Tennis

- ITTF (International Table Tennis Federation)
  Role: official rankings, tournament schedules, player profiles.
  URL: ittf.com
  Use for: official rankings, tournament tier context.
  Access: OK.

- tt-series.com
  Role: table tennis statistics and predictions — player form, head-to-head, recent results.
  URL: tt-series.com
  Use for: predictions and form analysis for Russian/Ukrainian/Polish table tennis leagues (popular for live betting).
  Access: OK.

- TableTennisDaily
  Role: table tennis news, analysis, and community discussion.
  URL: tabletennisdaily.com
  Use for: player form context, equipment changes, injury news.
  Access: OK.

### Darts

- DartConnect
  Role: darts statistics — player averages, checkout percentages, leg/set data.
  URL: dartconnect.com
  Use for: player averages, form trends, tournament-level performance.
  Access: OK.

- DartsOrakel
  Role: darts predictions and statistics — modeled probabilities, head-to-head analysis.
  URL: dartsorakel.com
  Use for: match predictions, leg/set totals analysis.
  Access: OK.

- PDC.tv
  Role: official PDC — tournament schedules, results, player profiles, averages, order of merit.
  URL: pdc.tv
  Use for: official schedule, format (best-of-X legs/sets), player form. Referenced in darts protocol.
  Access: OK.

### Handball

- Handball-World
  Role: handball news, statistics, and analysis across European leagues.
  URL: handball-world.com
  Use for: team form, league standings, injury context.
  Access: OK.

- EHF (European Handball Federation)
  Role: official European handball — Champions League, EHF League results and stats.
  URL: eurohandball.com
  Use for: fixture confirmation, team stats, competition context.
  Access: OK.

### MMA / UFC

- UFCstats
  Role: official UFC statistics — strikes, takedowns, submission attempts, fight history.
  URL: ufcstats.com
  Use for: fighter comparison, statistical matchup analysis, finish rate.
  Access: OK.

- Tapology
  Role: MMA rankings, fight cards, fighter records, community predictions.
  URL: tapology.com
  Use for: community consensus, fighter records, weight class context.
  Access: OK.

- Sherdog
  Role: MMA fighter records, fight history, news, rankings across all promotions (UFC, Bellator, ONE, PFL).
  URL: sherdog.com
  Use for: fighter records, fight history, win/loss streaks. Referenced in MMA protocol.
  Access: OK.

### Padel

- Premier Padel (Official)
  Role: official Premier Padel Tour — live scores, results, draws, match stats, highlights.
  URL: premierpadel.com
  Use for: fixture confirmation, draw context, match stats per event, tournament format.
  Access: OK.

- Sofascore Padel
  Role: padel livescores, H2H, form, and basic match stats across Premier Padel + FIP Tours.
  URL: sofascore.com/padel
  Use for: fixture discovery, H2H records, form context, live scores and settlement.
  Access: OK.

- PadelFIP (Official Rankings)
  Role: official FIP world rankings for men and women, tournament calendar.
  URL: padelfip.com
  Use for: ranking context, tournament tier (Major/P1/P2/Bronze), seeding verification.
  Access: OK.

- BetExplorer Padel
  Role: padel odds comparison — moneyline, set totals.
  URL: betexplorer.com/padel/
  Use for: price comparison across bookmakers, market depth check.
  Access: OK (JS-rendered, may need Playwright).

- OddsPortal Padel
  Role: padel odds comparison and historical odds data.
  URL: oddsportal.com/padel/
  Use for: secondary odds comparison, odds movement tracking.
  Access: OK (JS-rendered, may need Playwright).

### Speedway / Żużel

- Ekstraliga App / SpeedwayEkstraliga (Official)
  Role: official PGE Ekstraliga — results, standings, rider stats, heat-by-heat scores.
  URL: speedwayekstraliga.pl
  Use for: team lineups, rider averages, home/away stats, heat results, league standings.
  Access: OK.

- SportoweFakty Żużel
  Role: comprehensive Polish speedway coverage — news, analysis, expert predictions, lineup announcements, track conditions.
  URL: sportowefakty.wp.pl/zuzel
  Use for: pre-match analysis, lineup changes, rider form, expert opinions, track/weather context. CRITICAL for Polish speedway insight.
  Access: OK (GDPR wall — accept cookies to access content).
  **Deep-dive required**: YES — expert opinions and match previews contain valuable angles.

- Flashscore Speedway
  Role: speedway live scores and results.
  URL: flashscore.com/speedway/ (or within motorsport section)
  Use for: fixture discovery, results, settlement.
  Access: OK (may be under motorsport category).

- BetExplorer Speedway
  Role: speedway odds comparison — match winner, handicap, total points.
  URL: betexplorer.com/speedway/
  Use for: price comparison across bookmakers for PGE Ekstraliga and international events.
  Access: OK (JS-rendered).

### Multi-Sport Odds and Analytics

- Covers
  Role: expert previews, odds, and picks for NBA, NHL, MLB, NFL, and more.
  URL: covers.com
  Use for: narrative and preview context for US sports.
  Access: OK.

- StatMuse
  Role: natural language sports queries — NBA, NHL, MLB, NFL stats on demand.
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
  Role: universal fixture aggregator — ALL sports in one place with form, H2H, stats.
  URL: sofascore.com
  Use for: cross-validating event counts from BetExplorer/Flashscore. Covers ALL 14 sports. Good for niche sports missing on BetExplorer (padel, speedway).
  Access: OK.

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
- Forebet (forebet.com) — Cloudflare 403. Was football model support.
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
- WhoScored (whoscored.com) — 403
- KenPom (kenpom.com) — blocked
- FanGraphs (fangraphs.com) — blocked. Use BaseballSavant (Statcast) as replacement for pitcher/hitter stats.
- ActionNetwork (actionnetwork.com) — blocked
- VolleyBox (volleybox.net) — blocked
- HLTV (hltv.org) — tips/predictions 403. Stats pages (rankings, match history, player data) partially accessible. Use GosuGamers for esports tips.

**Partial (availability noted in main entries above):**
- Covers (covers.com) — NBA pages return empty; other sections partial. See Tier A entry.
- TeamRankings (teamrankings.com) — inconsistently blocked. See Tier A entry.

## Sport Playbooks

### Odds Source Map by Sport (verified 2026-04-23)

Use this table to know WHERE to get odds for each sport. Never give up after one source.

| Sport | Primary Odds | Secondary Odds | Tertiary Odds | Fallback |
|-------|-------------|----------------|---------------|----------|
| **Football** (EU) | BetExplorer (1X2/O-U/BTTS/corners) | OddsPortal | — | The-Odds-API |
| **Football** (Exotic) | BetExplorer | OddsPortal | Soccerway | The-Odds-API |
| **NHL** | SBR (Totals tab) | ESPN Odds | ScoresAndOdds | The-Odds-API |
| **NBA** | SBR (Totals tab) | ESPN Odds | ScoresAndOdds | The-Odds-API |
| **MLB** | SBR (Totals tab) | ESPN Odds | ScoresAndOdds | The-Odds-API |
| **NFL** | SBR (Totals tab) | ESPN Odds | ScoresAndOdds | The-Odds-API |
| **Tennis** | BetExplorer (ML) | OddsPortal | — | The-Odds-API |
| **Volleyball** | BetExplorer (set/point totals) | OddsPortal | — | The-Odds-API |
| **Esports** | BetExplorer | OddsPortal | GosuGamers | The-Odds-API |
| **Snooker** | OddsPortal | BetExplorer | — | The-Odds-API |
| **Darts** | BetExplorer | OddsPortal | — | The-Odds-API |
| **Table Tennis** | BetExplorer | OddsPortal | — | The-Odds-API |
| **Handball** | BetExplorer | OddsPortal | — | The-Odds-API |
| **MMA/UFC** | OddsPortal | BetExplorer | — | The-Odds-API |
| **Padel** | BetExplorer | OddsPortal | — | The-Odds-API |
| **Speedway** | BetExplorer | OddsPortal | — | The-Odds-API |

**Rule:** If all sources in the row fail for a pick → do NOT skip. Try The-Odds-API or search for a new source. The internet always has odds data somewhere.

### Sport-Specific Playbooks

- Football
  Minimum stack: Flashscore or Sofascore + BetExplorer or OddsPortal + SoccerStats (league context) + TotalCorner (match corners).
  Tipster cross-check: Zawod Typer, Typersi, BetIdeas, PicksWise, Tipstrr.
  Specialist sources: Betaminic (corners/cards tables), Betclic Statystyki (top leagues only), TransferMarkt (coaching changes, transfers).
  Preferred markets: fouls > cards > corners > shots > team totals > BTTS > U2.5 > O2.5 > DC/DNB > 1X2 (LAST RESORT).
  Exotic fallback: Soccerway (H2H, standings) + AiScore/Xscores (Asian/African stats) + Goaloo/NowGoal (Asian coverage). Use when SoccerStats/TotalCorner have no data for the league.

- Basketball
  Minimum stack: Basketball-Reference + **SBR or ESPN or ScoresAndOdds** (totals/spreads) + BetExplorer.
  Tipster cross-check: PicksWise, Tipstrr.
  Preferred markets: team totals > quarter totals > game totals > spreads > moneyline (LAST RESORT).

- Baseball
  Minimum stack: BaseballSavant (Statcast) + **SBR or ESPN** (totals/run line) + BetExplorer.
  Note: FanGraphs is BLOCKED — use BaseballSavant (xERA, xFIP, barrel%) as the primary pitcher/hitter stats source.
  Tipster cross-check: PicksWise.
  Preferred markets: F5 totals > team totals > game totals > run line > moneyline (LAST RESORT).

- Hockey
  Minimum stack: Hockey-Reference + **SBR or ESPN or ScoresAndOdds** (totals/puck line) + NaturalStatTrick for xG.
  Tipster cross-check: PicksWise.
  Preferred markets: period totals > game totals > puck line > moneyline (LAST RESORT).

- Tennis
  Minimum stack: TennisAbstract (Elo) + TennisExplorer (H2H) + BetExplorer or OddsPortal.
  Tipster cross-check: Zawod Typer, Tipstrr.
  Preferred markets: game totals O/U (PRIMARY) > set totals O/U > game handicap > set handicap > moneyline (LAST RESORT — only 1.50-2.50 range + STRONG odds ratio + surface + H2H dominance).
  **ABSOLUTE RULE**: NEVER default to ML in tennis. Statistical markets have ~65% hit rate vs ML ~58%. Always prefer games/sets.

- Volleyball
  Minimum stack: BetExplorer volleyball section + Flashscore or Sofascore.
  Tipster cross-check: Tipstrr.
  Preferred markets: set totals > point totals > set handicap > moneyline (LAST RESORT).

- Esports (CS2, Dota 2, LoL, Valorant)
  Minimum stack: GosuGamers + Liquipedia + BetExplorer or OddsPortal.
  Tipster cross-check: GosuGamers community, Tipstrr.
  Note: HLTV blocked — use GosuGamers and Liquipedia as primary CS2 sources.
  Preferred markets: map totals > round totals > map handicap > kill totals > moneyline (LAST RESORT).

- Snooker
  Minimum stack: CueTracker (H2H, frame stats) + BetExplorer or OddsPortal. SnookerOrg/WST for schedule.
  Tipster cross-check: Tipstrr.
  Preferred markets: frame totals > frame handicap > century/50+ break props > moneyline (LAST RESORT).

- Table Tennis
  Minimum stack: ITTF rankings + Flashscore or Sofascore. tt-series.com for league-level analysis.
  Tipster cross-check: Tipstrr.
  Preferred markets: total points > set totals > set handicap > moneyline (LAST RESORT).

- Darts
  Minimum stack: DartsOrakel + BetExplorer or OddsPortal.
  Tipster cross-check: Tipstrr.
  Preferred markets: 180s O/U > leg/set totals > checkout props > moneyline (LAST RESORT).

- Handball
  Minimum stack: EHF or Handball-World + BetExplorer or OddsPortal. Flashscore for results.
  Tipster cross-check: Tipstrr.
  Preferred markets: half totals > game totals > handicap > moneyline (LAST RESORT).

- MMA / UFC
  Minimum stack: UFCstats + OddsPortal or BetExplorer. Tapology for records.
  Tipster cross-check: PicksWise, Tipstrr.
  Preferred markets: method of victory > O/U rounds > ITD > round betting > moneyline (LAST RESORT).

- Padel
  Minimum stack: Sofascore Padel (H2H, form) + BetExplorer or OddsPortal. PremierPadel.com for draws/stats.
  Tipster cross-check: Limited — no major tipster sites cover padel yet. Use ranking context + H2H as primary edge.
  Statistical edge: Rankings highly predictive at top level (top-8 pairs dominate). H2H and surface (indoor/outdoor) matter.
  Market note: ML market similar to tennis — ranking gaps create predictable outcomes. Set totals viable for close matchups.
  Preferred markets: game totals > set totals O/U 2.5 > set handicap > moneyline (LAST RESORT, 1.40-2.20 range, only when ranking gap >3000).
  Seasonal note: Premier Padel tour runs Feb-Dec with P1/P2 events most weeks. FIP Bronze events daily but low data quality.

- Speedway / Żużel
  Minimum stack: SpeedwayEkstraliga.pl (rider stats, home/away averages) + SportoweFakty.wp.pl/zuzel (expert analysis, lineups) + BetExplorer or OddsPortal.
  Tipster cross-check: SportoweFakty experts, Polish betting forums. Deep-dive SportoweFakty match previews.
  Statistical edge: HOME ADVANTAGE is extreme in speedway (70-75% home win rate). Rider track-specific averages, lineup changes, track conditions (weather), and gate positions are statistically significant. Reserve rider usage patterns matter.
  Market note: Match winner (handicap) and total points are the main markets. Home dominance is well-known but still often mispriced in handicap lines.
  Preferred markets: handicap > total_points > match_winner (LAST RESORT).
  Seasonal note: PGE Ekstraliga runs Apr-Sep, 1-2 matches per round (4 teams play per matchday). 2. Ekstraliga and KLŻ also covered. SGP events occasionally.

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

## Settlement Sources

- Primary settlement sources: Flashscore and Sofascore.
- Secondary settlement sources: bookmaker settled market plus OddsPortal or BetExplorer archived results.
- Use two sources whenever possible.
- If only one reliable source is available, note it explicitly in the daily report and ledger notes.

## Hard Source Rules

- A final pick must have at least one Tier A stats or fixture source and one Tier A market or price source.
- Tier B sources can strengthen or weaken confidence by at most one level, but they cannot create a bet on their own.
- Community sources (Zawod Typer, Typersi, Meczyki, OLBG, PicksWise, BetIdeas, Sportsgambler, Tipstrr, GosuGamers) can adjust confidence by ±1 level based on consensus alignment/divergence, but cannot be the primary reason for a pick.
- However, strong consensus from multiple tipster sites IS a valid supporting signal — it provides angles and perspectives that statistics alone may miss.
- If Tier A sources materially disagree on the core read, skip the bet unless the disagreement is clearly explained and the stake is reduced.
- If the only support comes from a single consensus or tipster page with no statistical backing, skip the bet.
- If community consensus strongly diverges from Tier A direction (≥60% opposite), note the divergence in the report and investigate before proceeding.
- Never reject a sport for "lack of sources" — search specialist sites (see Sport Playbooks above).
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