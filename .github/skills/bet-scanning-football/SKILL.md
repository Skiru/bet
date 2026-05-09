---
name: bet-scanning-football
description: "Football-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules. 90+ URLs, 5 dedicated adapters."
user-invokable: false
---

# Scanning Football

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/football/poland/ | flashscore.com | Fixtures | Poland + deep-link to all divisions |
| https://www.flashscore.com/football/poland/ekstraklasa/ | flashscore.com | Fixtures | Polish top flight |
| https://www.flashscore.com/football/poland/division-1/ | flashscore.com | Fixtures | Polish 1st division |
| https://www.flashscore.com/football/poland/division-2/ | flashscore.com | Fixtures | Polish 2nd division |
| https://www.flashscore.com/football/england/premier-league/ | flashscore.com | Fixtures | EPL |
| https://www.flashscore.com/football/spain/laliga/ | flashscore.com | Fixtures | La Liga |
| https://www.flashscore.com/football/germany/bundesliga/ | flashscore.com | Fixtures | Bundesliga |
| https://www.flashscore.com/football/italy/serie-a/ | flashscore.com | Fixtures | Serie A |
| https://www.flashscore.com/football/france/ligue-1/ | flashscore.com | Fixtures | Ligue 1 |
| https://www.flashscore.com/football/england/championship/ | flashscore.com | Fixtures | Championship |
| https://www.flashscore.com/football/germany/2-bundesliga/ | flashscore.com | Fixtures | 2. Bundesliga |
| https://www.flashscore.com/football/brazil/serie-a/ | flashscore.com | Fixtures | Brazil Serie A |
| https://www.flashscore.com/football/usa/mls/ | flashscore.com | Fixtures | MLS |
| https://www.soccerway.com/ | soccerway.com | Fixtures | Dedicated football fixture listing |
| https://www.soccerstats.com/ | soccerstats.com | Stats | Corner/card/foul league averages |
| https://totalcorner.com/ | totalcorner.com | Stats | Corner stats + betting lines |
| https://totalcorner.com/match/today | totalcorner.com | Stats | Today's corner data |
| https://www.whoscored.com/Previews | whoscored.com | Stats | Possession/shots/corners (JS SPA) |
| https://www.forebet.com/en/football-tips-and-predictions-for-today | forebet.com | Predictions | Probabilities (no odds) |
| https://www.betexplorer.com/soccer/ | betexplorer.com | Odds | 1X2 multi-league odds |
| https://www.oddsportal.com/football/ | oddsportal.com | Odds | Named H2H odds |
| https://www.betclic.pl/pilka-nozna-s1 | betclic.pl | Execution | ⚠ Always 403 — conditional only |
| https://scores24.live/en/soccer | scores24.live | Deep | H2H + form + trends |
| https://www.sofascore.com/ | sofascore.com | Fixtures | REST API, 14 sports |
| https://www.covers.com/ | covers.com | Odds | Partial coverage |

**Total URLs**: 90+ (with deep-link expansion to 800+ pages across 70+ countries)

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | home, away, time, league (shallow — JS fallback) |
| soccerstats.com | `soccerstats_adapter` | per-team league averages: corners, cards, fouls |
| totalcorner.com | `totalcorner_adapter` | corner_count, corner_handicap, total_goals_line |
| soccerway.com | `soccerway_adapter` | home, away, time, league (shallow listing) |
| whoscored.com | `whoscored_adapter` | possession, shots, corners (JS SPA regex) |
| betexplorer.com | `betexplorer_adapter` | home, away, time, odds[] |
| oddsportal.com | `oddsportal_adapter` | home, away, odds_structured{home_win, draw, away_win} |
| scores24.com | `scores24_adapter` | match_info, odds, h2h[], form[], trends[] |
| forebet.com | `forebet_adapter` | forebet_probs{home/draw/away %}, forebet_prediction |
| sofascore.com | `sofascore_adapter` | sofascore_id, fixtures via REST |
| betclic.pl | `betclic_adapter` | decimal odds from btn_label elements |
| covers.com | `covers_adapter` | spread/total/ML, consensus %s |

## Data Quality Standards

- **Minimum events per day:** 200
- **Required stat keys:** corners, fouls, yellow_cards, shots, shots_on_target, possession
- **Should-have keys:** accurate_passes, crosses, long_balls, tackles, interceptions, clearances, blocked_shots
- **Bonus keys:** xG (Understat, 6 EU leagues: EPL, LaLiga, Bundesliga, Serie A, Ligue 1, RFPL)
- **Multi-source threshold:** ≥2 sources confirming each event
- **Data freshness:** Same-day data only (reject stale content)
- **Stats cache target:** ≥100 team files with ≥10 stat keys each (ESPN provides 28+)

## Deep-Link Discovery

Football has the most aggressive deep-link expansion:
- **Max deep links:** 50 per seed URL
- **Discovery domains:** flashscore.com, sofascore.com, soccerway.com, soccerstats.com, betexplorer.com, oddsportal.com, whoscored.com
- **Pattern:** Country pages → league pages → match detail pages
- **Expected expansion:** 90 seed URLs → 800+ actual pages fetched

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 45s | 1s | 3 |
| soccerstats.com | 45s | 2s | 2 |
| totalcorner.com | 45s | 1s | 2 |
| whoscored.com | 45s (JS heavy) | 3s | 1 |
| soccerway.com | 45s | 1s | 2 |
| betexplorer.com | 45s | 1s | 2 |
| oddsportal.com | 45s | 1s | 2 |
| scores24.live | 45s | 1s | 2 |
| forebet.com | 45s | 1s | 2 |
| sofascore.com | 45s | 1s | 2 |
| betclic.pl | 45s | 2s | 1 |

**Total scanner timeout:** 15 minutes (per-sport; enforced by orchestrator at 15 min first attempt, 20 min retry)

## Fallback Chains

**Market odds:**
1. BetExplorer → 2. OddsPortal → 3. The-Odds-API

**Statistical data:**
1. SoccerStats/Sofascore → 2. Flashscore/Betaminic → 3. TotalCorner (corners specialist)

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
- THINK IN THE MIDDLE: use sequentialthinking to evaluate scan quality

**xG data:**
1. Understat (6 EU leagues only) → no fallback for non-covered leagues

**Tipsters:**
1. ZawodTyper → 2. Typersi/Meczyki → 3. PicksWise/BetIdeas → 4. OLBG/Sportsgambler

## Seasonal Considerations

- **European leagues:** Aug-May (main season), Jun-Jul off-season but Copa America/AFCON/friendlies
- **South American leagues:** Year-round (Brazil Serie A Feb-Dec, Argentina year-round)
- **MLS:** Mar-Oct (playoff Nov)
- **Asian leagues:** Various (J-League Feb-Dec, K-League Feb-Nov)
- **African leagues:** Various schedules
- **Summer:** Fewer European games but South America + Asia + Africa active
- **International breaks:** ~6 per year, club football pauses 1-2 weeks

## Known Issues

- **SoccerStats intermittent:** HTTP 500 errors common. Fallback: Betaminic team pages.
- **WhoScored JS-heavy:** Requires full Playwright rendering. Regex extraction brittle.
- **FootyStats 403:** Individual team pages sometimes work but main pages blocked.
- **Deep-link explosion:** 50 deep links × 90 URLs can produce 4000+ pages. Rate limiting critical.
- **Forebet/TotalCorner/Scores24 data lost downstream:** Extracted by adapters but NOT fed into safety score pipeline. Data exists in scan_summary.json but lost during aggregation.
- **Betclic always 403:** Never scrape — execution odds checked manually by user on app.

## API Enrichment

| Client | Free? | Keys Returned | Notes |
|--------|-------|---------------|-------|
| ESPN | ✅ FREE | 28+ per game (36 football leagues) | Unlimited, PRIMARY source |
| API-Football | ❌ 100/day shared | corners, fouls, cards, shots, possession | Shared quota with 6 other sports |
| Understat | ✅ FREE | xG, xGA | 6 EU leagues only |
| football-data.org | ✅ FREE (10 req/min) | Fixtures + standings | Only standings source |
