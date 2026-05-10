---
name: bet-scanning-niche
description: "Niche sports (snooker, darts, speedway) scanning — source URLs, adapter mappings, data quality requirements, timeouts, specialist sources, and validation rules."
user-invokable: false
---

# Scanning Niche Sports (Snooker + Darts + Speedway)

## Source URLs

### Snooker
| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/snooker/ | flashscore.com | Fixtures | Snooker events |
| https://cuetracker.net/ | cuetracker.net | Stats | Player records, H2H |
| https://www.betexplorer.com/snooker/ | betexplorer.com | Odds | Snooker markets |
| https://www.betclic.pl/snooker-s19 | betclic.pl | Execution | ⚠ Always 403 |
| https://scores24.live/en/snooker | scores24.live | Data | Snooker section |

### Darts
| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/darts/ | flashscore.com | Fixtures | PDC + WDF events |
| https://www.flashscore.com/darts/pdc/ | flashscore.com | Fixtures | PDC specific |
| https://dartsorakel.com/ | dartsorakel.com | Stats | Predictions + detailed stats |
| https://www.betexplorer.com/darts/ | betexplorer.com | Odds | Darts markets |
| https://www.betclic.pl/rzutki-s11 | betclic.pl | Execution | ⚠ Always 403 |
| https://scores24.live/en/darts | scores24.live | Data | Darts section |

### Speedway
| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://speedwayekstraliga.pl/ | speedwayekstraliga.pl | Official | Polish Ekstraliga |
| https://www.betexplorer.com/speedway/ | betexplorer.com | Odds | Speedway markets |
| https://www.betclic.pl/zuzel-s36 | betclic.pl | Execution | ⚠ Always 403 |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | player1/team1, player2/team2, time, event |
| cuetracker.net | N/A (needs adapter) | Player records, centuries, H2H |
| dartsorakel.com | N/A (needs adapter) | Predictions, averages, checkout % |
| speedwayekstraliga.pl | N/A (needs adapter) | Fixtures, team lineups |
| betexplorer.com | `betexplorer_adapter` | odds[] |
| scores24.live | `scores24_adapter` | H2H, form |

## Data Quality Standards

- **Minimum events per day:** 1 (combined — highly seasonal and tournament-driven)
- **Snooker stat keys:** frames, centuries, highest_break (specialist sources)
- **Darts stat keys:** legs, sets, 180s, checkout_pct, average (DartsOrakel)
- **Speedway stat keys:** heats, points (limited)
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day events only

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| cuetracker.net | 20s | 2s | 1 |
| dartsorakel.com | 20s | 2s | 1 |
| speedwayekstraliga.pl | 20s | 2s | 1 |
| betexplorer.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |

**Total scanner timeout:** 5 minutes

## Fallback Chains

**Snooker market odds:**
1. BetExplorer → 2. OddsPortal → (no tertiary)

**Snooker stats:**
1. CueTracker → 2. SnookerOrg → 3. WorldSnooker

**Darts market odds:**
1. BetExplorer → 2. OddsPortal → (no tertiary)

**Darts stats:**
1. DartsOrakel → 2. DartConnect → 3. PDC.tv

**Speedway market odds:**
1. BetExplorer → (no fallback)

**Speedway stats:**
1. SpeedwayEkstraliga → 2. SportoweFakty → (no tertiary)

**Tipsters:**
1. Sportsgambler/OLBG → 2. Tipstrr → 3. ZawodTyper (speedway)

## Seasonal Considerations

### Snooker
- **Year-round** but tournament-clustered
- **World Championship:** Apr-May (biggest event)
- **UK Championship:** Nov-Dec
- **Masters:** Jan
- **Tour events:** Throughout year with gaps between ranking events

### Darts
- **PDC Premier League:** Jan-May (weekly)
- **World Championship:** Dec-Jan (biggest event)
- **Players Championship:** Weekly/fortnightly
- **World Matchplay:** Jul
- **Summer:** Reduced schedule (Jun-Jul)
- **European Tour:** Throughout year

### Speedway
- **Polish Ekstraliga:** Apr-Oct ONLY
- **Speedway Grand Prix:** Apr-Oct (8-10 rounds)
- **Off-season:** Nov-Mar (ZERO events)
- **Weather dependent:** Rain cancellations common

## Known Issues

- **CueTracker:** No dedicated adapter. Web scraping needed for player stats and H2H.
- **DartsOrakel:** No dedicated adapter. Specialist darts analysis site with predictions.
- **SpeedwayEkstraliga:** No dedicated adapter. Polish-language site.
- **No free stats API** for any of these three sports.
- **The-Odds-API:** Does NOT cover snooker, darts, or speedway.
- **Low daily volume:** Many days have zero events across all three sports. This is normal.
- **Tournament clustering:** Events come in bursts during major tournaments, then nothing.
- **Speedway weather:** Outdoor sport, rain delays/cancellations affect scheduling.
