---
name: bet-scanning-baseball
description: "Baseball-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Baseball

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/baseball/ | flashscore.com | Fixtures | MLB games |
| https://www.oddsportal.com/baseball/ | oddsportal.com | Odds | MLB odds |
| https://www.betclic.pl/baseball-s14 | betclic.pl | Execution | ⚠ Always 403 |
| https://scores24.live/en/baseball | scores24.live | Data | Baseball section |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | home, away, time, league |
| oddsportal.com | `oddsportal_adapter` | odds_structured |
| scores24.live | `scores24_adapter` | H2H, form |

## Data Quality Standards

- **Minimum events per day:** 5 (in-season, ~15 MLB games daily)
- **Required stat keys:** runs, hits, home_runs, strikeouts, walks, stolen_bases
- **Should-have keys:** era, whip, batting_avg, on_base_pct, slugging_pct
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only
- **Stats cache target:** ≥28 team files (30 MLB teams)

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| oddsportal.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |

**Total scanner timeout:** 3 minutes

## Fallback Chains

**Market odds:**
1. SBR → 2. ESPN Odds → 3. ScoresAndOdds

**Statistical data:**
1. BaseballSavant → 2. ESPN → (no tertiary)

**Tipsters:**
1. PicksWise → 2. Sportsgambler → 3. OLBG

## Seasonal Considerations

- **MLB Regular Season:** Apr-Oct (162 games per team, ~15 games daily)
- **Spring Training:** Feb-Mar (exhibition, limited betting value)
- **Postseason:** Oct (Wild Card → Division Series → Championship Series → World Series)
- **All-Star Break:** Jul (one week, no games)
- **Off-season:** Nov-Mar (ZERO MLB games)
- **Weather:** Outdoor stadiums affected by rain/cold, PPD (postponements) common early season
- **KBO/NPB:** Korean and Japanese baseball available year-round for additional coverage

## Known Issues

- **Seasonal sport:** Nov-Mar produces zero MLB events. This is expected.
- **BaseballSavant:** Advanced stats (Statcast) but no dedicated adapter.
- **Starting pitchers:** Critical for baseball betting. Must verify SP confirmed day-of.
- **Weather postponements:** Common in Apr/Sep. Check weather before betting.
- **The-Odds-API:** Covers baseball (MLB). Use `--scores baseball` for settlement.
- **Runs totals market:** Key baseball bet (8.5/9.5 line typical). Weather + pitching matchup driven.
- **US odds format:** SBR/ESPN use American odds. Convert: +X → 1+X/100, −X → 1+100/X.

## API Enrichment

| Client | Free? | Keys Returned | Notes |
|--------|-------|---------------|-------|
| ESPN | ✅ FREE | 12+ per game | MLB primary |
| API-Baseball | ❌ 100/day shared | runs, hits, home_runs, strikeouts | Shared quota |
