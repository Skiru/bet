---
name: bet-scanning-hockey
description: "Hockey-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Hockey

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/hockey/ | flashscore.com | Fixtures | All hockey leagues |
| https://www.flashscore.com/hockey/usa/nhl/ | flashscore.com | Fixtures | NHL |
| https://www.flashscore.com/hockey/sweden/shl/ | flashscore.com | Fixtures | Swedish SHL |
| https://www.flashscore.com/hockey/finland/liiga/ | flashscore.com | Fixtures | Finnish Liiga |
| https://www.flashscore.com/hockey/czech-republic/extraliga/ | flashscore.com | Fixtures | Czech Extraliga |
| https://www.hockey-reference.com/ | hockey-reference.com | Stats | NHL schedule/stats |
| https://www.betclic.pl/hokej-na-lodzie-s13 | betclic.pl | Execution | ⚠ Always 403 |
| https://www.oddsportal.com/hockey/ | oddsportal.com | Odds | Hockey odds |
| https://www.forebet.com/en/hockey/predictions-today | forebet.com | Predictions | Probabilities |
| https://scores24.live/en/ice-hockey | scores24.live | Deep | H2H + form |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | home, away, time, league |
| hockey-reference.com | `hockey_reference_adapter` | NHL schedule listing (shallow) |
| betexplorer.com | `betexplorer_adapter` | odds[] |
| oddsportal.com | `oddsportal_adapter` | odds_structured |
| scores24.live | `scores24_adapter` | H2H, form, trends |
| forebet.com | `forebet_adapter` | prediction probabilities |

## Data Quality Standards

- **Minimum events per day:** 10
- **Required stat keys:** shots, hits, blocks, pim, powerplay_goals, faceoff_pct
- **Should-have keys:** saves, save_pct, time_on_ice, giveaways, takeaways
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only
- **Stats cache target:** ≥16 team files with ≥8 keys each

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| hockey-reference.com | 20s | 2s | 1 |
| oddsportal.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |
| forebet.com | 20s | 1s | 2 |

**Total scanner timeout:** 3 minutes

## Fallback Chains

**Market odds:**
1. SBR → 2. ESPN Odds → 3. ScoresAndOdds

**Statistical data:**
1. NaturalStatTrick → 2. Hockey-Reference/MoneyPuck → 3. DailyFaceoff (goalies)

**Tipsters:**
1. PicksWise → 2. Sportsgambler → 3. OLBG

## Seasonal Considerations

- **NHL:** Oct-Jun (regular season Oct-Apr, playoffs Apr-Jun)
- **SHL/Liiga/Extraliga:** Sep-Apr
- **Off-season:** Jun-Sep (no major leagues active)
- **World Championship:** May (affects NHL players)
- **Olympics:** Feb (every 4 years, affects NHL schedule)

## Known Issues

- **Hockey-Reference:** Shallow adapter — schedule listing only.
- **NaturalStatTrick:** Advanced analytics (Corsi, Fenwick, xG) but no dedicated adapter.
- **MoneyPuck:** Similar to NaturalStatTrick, no adapter.
- **DailyFaceoff:** Goalie confirmations (critical for hockey betting). Manual check.
- **Covers:** NHL pages sometimes empty.
- **EU leagues:** Less data coverage than NHL. BetExplorer standings as fallback.

## API Enrichment

| Client | Free? | Keys Returned | Notes |
|--------|-------|---------------|-------|
| ESPN | ✅ FREE | 15+ per game | NHL primary |
| API-Hockey | ❌ 100/day shared | goals, shots, hits, blocks, pim | Shared quota |
