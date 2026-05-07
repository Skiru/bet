---
name: bet-scanning-basketball
description: "Basketball-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Basketball

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/basketball/ | flashscore.com | Fixtures | All leagues |
| https://www.flashscore.com/basketball/usa/nba/ | flashscore.com | Fixtures | NBA |
| https://www.flashscore.com/basketball/europe/euroleague/ | flashscore.com | Fixtures | Euroleague |
| https://www.flashscore.com/basketball/europe/eurocup/ | flashscore.com | Fixtures | EuroCup |
| https://www.flashscore.com/basketball/europe/champions-league/ | flashscore.com | Fixtures | Basketball CL |
| https://www.flashscore.com/basketball/spain/acb/ | flashscore.com | Fixtures | Spanish ACB |
| https://www.flashscore.com/basketball/germany/bundesliga/ | flashscore.com | Fixtures | German BBL |
| https://www.flashscore.com/basketball/france/lnb/ | flashscore.com | Fixtures | French LNB |
| https://www.flashscore.com/basketball/italy/lega-a/ | flashscore.com | Fixtures | Italian Lega A |
| https://www.flashscore.com/basketball/greece/basket-league/ | flashscore.com | Fixtures | Greek League |
| https://www.flashscore.com/basketball/poland/basket-liga/ | flashscore.com | Fixtures | Polish Basket Liga |
| https://www.flashscore.com/basketball/turkey/bsl/ | flashscore.com | Fixtures | Turkish BSL |
| https://www.basketball-reference.com/ | basketball-reference.com | Stats | NBA schedule (shallow) |
| https://www.teamrankings.com/ | teamrankings.com | Stats | Rankings/stats (intermittent) |
| https://www.betexplorer.com/basketball/ | betexplorer.com | Odds | EU basketball odds |
| https://www.oddsportal.com/basketball/ | oddsportal.com | Odds | Multi-market odds |
| https://www.betclic.pl/koszykowka-s4 | betclic.pl | Execution | ⚠ Always 403 |
| https://www.forebet.com/en/basketball/predictions-today | forebet.com | Predictions | Probabilities |
| https://scores24.live/en/basketball | scores24.live | Deep | H2H + form |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | home, away, time, league |
| basketball-reference.com | `basketball_reference_adapter` | NBA/WNBA schedule listing |
| betexplorer.com | `betexplorer_adapter` | odds[] (1X2, totals, handicap) |
| oddsportal.com | `oddsportal_adapter` | odds_structured |
| scores24.live | `scores24_adapter` | H2H, form, trends |
| forebet.com | `forebet_adapter` | prediction probabilities |

## Data Quality Standards

- **Minimum events per day:** 20
- **Required stat keys:** rebounds, assists, steals, blocks, turnovers, fg_pct, three_pct, ft_pct
- **Should-have keys:** offensive_rebounds, defensive_rebounds, fast_break_points, points_in_paint
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only
- **Stats cache target:** ≥25 team files (NBA-focused), ≥8 keys each

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| basketball-reference.com | 20s | 2s | 1 |
| teamrankings.com | 20s | 2s | 1 |
| betexplorer.com | 20s | 1s | 2 |
| oddsportal.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |

**Total scanner timeout:** 5 minutes

## Fallback Chains

**Market odds (US/NBA):**
1. SBR → 2. ESPN Odds → 3. ScoresAndOdds

**Market odds (EU):**
1. BetExplorer → 2. OddsPortal → 3. The-Odds-API

**Statistical data:**
1. Basketball-Reference → 2. NBA.com/DunksAndThrees → 3. ESPN

**Tipsters:**
1. PicksWise (US) / Sportsgambler (EU) → 2. ZawodTyper → 3. OLBG

## Seasonal Considerations

- **NBA:** Oct-Jun (regular season Oct-Apr, playoffs Apr-Jun)
- **Euroleague/EuroCup:** Oct-May
- **National EU leagues:** Sep-Jun
- **Off-season:** Jul-Sep (Summer League, FIBA tournaments)
- **All-Star break:** Feb (one week, reduced schedule)

## Known Issues

- **Basketball-Reference:** Shallow adapter — schedule listing only, no deep stats.
- **TeamRankings:** Intermittent blocking. Do not rely as sole source.
- **NBA.com:** JS-heavy, may need Playwright for rendering.
- **Covers NBA pages:** Often empty. Use other sources.
- **EU vs US source split:** Different odds chains apply. NBA uses SBR/ESPN, EU uses BetExplorer/OddsPortal.

## API Enrichment

| Client | Free? | Keys Returned | Notes |
|--------|-------|---------------|-------|
| ESPN | ✅ FREE | 17+ per game | NBA primary |
| BallDontLie | ✅ FREE | Player box scores → team aggregation | H2H fallback |
| NBA API | ✅ FREE (1 req/sec) | PTS, REB, AST, STL, BLK, TOV | Rate-limited |
| API-Basketball | ❌ 100/day shared | points, rebounds, assists, blocks, fg_pct | Shared quota |
