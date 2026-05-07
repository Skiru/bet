---
name: bet-scanning-volleyball
description: "Volleyball-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Volleyball

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/volleyball/ | flashscore.com | Fixtures | All volleyball leagues |
| https://www.flashscore.com/volleyball/poland/plusliga/ | flashscore.com | Fixtures | PlusLiga (Polish top) |
| https://www.flashscore.com/volleyball/poland/i-liga/ | flashscore.com | Fixtures | Polish 1st division |
| https://www.flashscore.com/volleyball/poland/tauron-liga-women/ | flashscore.com | Fixtures | Polish women |
| https://www.flashscore.com/volleyball/italy/superlega/ | flashscore.com | Fixtures | Italian SuperLega |
| https://www.flashscore.com/volleyball/france/ligue-a/ | flashscore.com | Fixtures | French Ligue A |
| https://www.flashscore.com/volleyball/turkey/efeler-ligi/ | flashscore.com | Fixtures | Turkish league |
| https://www.flashscore.com/volleyball/germany/bundesliga/ | flashscore.com | Fixtures | German Bundesliga |
| https://www.flashscore.com/volleyball/europe/champions-league/ | flashscore.com | Fixtures | CEV Champions League |
| https://www.flashscore.com/volleyball/brazil/superliga/ | flashscore.com | Fixtures | Brazil Superliga |
| https://www.betexplorer.com/volleyball/ | betexplorer.com | Odds | Volleyball markets |
| https://www.oddsportal.com/volleyball/ | oddsportal.com | Odds | Limited coverage |
| https://www.betclic.pl/siatkowka-s18 | betclic.pl | Execution | ⚠ Always 403 |
| https://www.forebet.com/en/volleyball/predictions-today | forebet.com | Predictions | Probabilities |
| https://scores24.live/en/volleyball | scores24.live | Deep | H2H + form |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | home, away, time, league |
| betexplorer.com | `betexplorer_adapter` | odds[] |
| oddsportal.com | `oddsportal_adapter` | odds_structured |
| scores24.live | `scores24_adapter` | H2H, form, trends |
| forebet.com | `forebet_adapter` | prediction probabilities |
| sofascore.com | `sofascore_adapter` | REST API fixtures |

## Data Quality Standards

- **Minimum events per day:** 15
- **Required stat keys:** points, aces, blocks, attack_pct, sets_won, total_points, errors
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only
- **⚠ CRITICAL GAP:** Stats cache is currently EMPTY — zero team files

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
1. Flashscore → 2. Sofascore → 3. CEV/PlusLiga websites (no adapter)

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

- **CRITICAL: Stats cache empty.** API-Sports quota (100/day shared across 7 sports) consumed by football/basketball before volleyball gets allocated.
- **Root cause:** `api_volleyball.py` exists and works but never gets budget.
- **Workaround:** Run `fetch_api_stats.py --sports volleyball` FIRST before other sports, or use Sofascore API (free).
- **No dedicated volleyball adapter.** Only generic adapters (flashscore, betexplorer) cover volleyball.
- **CEV website:** Has detailed match stats but no scraping adapter built.
- **PlusLiga website:** Polish league stats available but no adapter.
- **The-Odds-API:** Does NOT cover volleyball.
