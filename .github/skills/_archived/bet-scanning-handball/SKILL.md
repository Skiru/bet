---
name: bet-scanning-handball
description: "Handball-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Handball

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/handball/ | flashscore.com | Fixtures | All handball leagues |
| https://www.flashscore.com/handball/poland/superliga/ | flashscore.com | Fixtures | Polish Superliga |
| https://www.flashscore.com/handball/poland/superliga-women/ | flashscore.com | Fixtures | Polish women |
| https://www.flashscore.com/handball/europe/champions-league/ | flashscore.com | Fixtures | EHF Champions League |
| https://www.flashscore.com/handball/germany/bundesliga/ | flashscore.com | Fixtures | German Bundesliga |
| https://www.flashscore.com/handball/france/starligue/ | flashscore.com | Fixtures | French Starligue |
| https://www.flashscore.com/handball/spain/liga-asobal/ | flashscore.com | Fixtures | Spanish Liga Asobal |
| https://www.flashscore.com/handball/denmark/handboldligaen/ | flashscore.com | Fixtures | Danish league |
| https://www.betexplorer.com/handball/ | betexplorer.com | Odds | Handball markets |
| https://www.oddsportal.com/handball/ | oddsportal.com | Odds | Handball odds |
| https://www.betclic.pl/pilka-reczna-s3 | betclic.pl | Execution | ⚠ Always 403 |
| https://www.forebet.com/en/handball/predictions-today | forebet.com | Predictions | Probabilities |
| https://scores24.live/en/handball | scores24.live | Deep | H2H + form |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | home, away, time, league |
| betexplorer.com | `betexplorer_adapter` | odds[] |
| oddsportal.com | `oddsportal_adapter` | odds_structured |
| scores24.live | `scores24_adapter` | H2H, form, trends |
| forebet.com | `forebet_adapter` | prediction probabilities |

## Data Quality Standards

- **Minimum events per day:** 10
- **Required stat keys:** goals, saves, turnovers, penalties, total_goals
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only
- **⚠ KNOWN GAP:** Stats cache currently EMPTY

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| betexplorer.com | 20s | 1s | 2 |
| oddsportal.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |
| forebet.com | 20s | 1s | 2 |

**Total scanner timeout:** 3 minutes

## Fallback Chains

**Market odds:**
1. BetExplorer → 2. OddsPortal → (no tertiary)

**Statistical data:**
1. Flashscore → 2. EHF website → 3. Handball-World

**Tipsters:**
1. Sportsgambler → 2. ZawodTyper → 3. OLBG

## Seasonal Considerations

- **European club season:** Sep-Jun (Bundesliga, Starligue, Liga Asobal, Polish Superliga)
- **Champions League:** Sep-Jun (group stage → Final Four)
- **Off-season:** Jul-Aug
- **World Championship:** Jan (odd years). European Championship: Jan (even years).
- **Olympics:** Jul-Aug (every 4 years)

## Known Issues

- **Stats cache EMPTY:** Same root cause as volleyball — shared API-Sports quota exhausted before handball.
- **api_handball.py exists** but rarely gets budget (100/day shared across 7 sports).
- **EHF website:** Has detailed match stats but no scraping adapter built.
- **National federation sites:** Have data but no adapters (Handball-Bundesliga.de, LNH.fr).
- **The-Odds-API:** Does NOT cover handball.
- **Total goals market:** Key handball bet (high-scoring sport, 50-65 total goals per match).
