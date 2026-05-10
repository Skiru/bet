---
name: bet-scanning-racket
description: "Racket sports (table tennis + padel) scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Racket Sports (Table Tennis + Padel)

## Source URLs

### Table Tennis
| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/table-tennis/ | flashscore.com | Fixtures | Daily TT matches |
| https://www.betexplorer.com/table-tennis/ | betexplorer.com | Odds | TT markets |
| https://www.betclic.pl/tenis-stolowy-s10 | betclic.pl | Execution | ⚠ Always 403 |
| https://scores24.live/en/table-tennis | scores24.live | Data | TT section |

### Padel
| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.sofascore.com/padel | sofascore.com | Fixtures | Padel coverage |
| https://www.betclic.pl/padel-s48 | betclic.pl | Execution | ⚠ Always 403 |
| https://www.betexplorer.com/padel/ | betexplorer.com | Odds | Padel markets |
| https://www.premierpadel.com/ | premierpadel.com | Official | Tournament schedules |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | player1, player2, time, tournament |
| betexplorer.com | `betexplorer_adapter` | odds[] |
| sofascore.com | `sofascore_adapter` | REST API fixtures |
| scores24.live | `scores24_adapter` | H2H, form |

## Data Quality Standards

- **Minimum events per day:** 5 (combined TT + padel)
- **Table tennis stat keys:** sets, games (limited data available)
- **Padel stat keys:** sets, games (limited data available)
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| betexplorer.com | 20s | 1s | 2 |
| sofascore.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |
| premierpadel.com | 30s | 2s | 1 |

**Total scanner timeout:** 3 minutes

## Fallback Chains

**Market odds (Table Tennis):**
1. BetExplorer → (no fallback — limited coverage)

**Market odds (Padel):**
1. BetExplorer → 2. Sofascore → (no tertiary)

**Statistical data (Table Tennis):**
1. ITTF → 2. Flashscore → 3. tt-series.com

**Statistical data (Padel):**
1. Sofascore → 2. PremierPadel → 3. PadelFIP

**Tipsters:**
1. Sportsgambler → 2. OLBG → 3. Tipstrr

## Seasonal Considerations

### Table Tennis
- **Year-round:** Professional table tennis has daily events (WTT, national leagues)
- **WTT events:** World Table Tennis tour events throughout year
- **Olympics:** Jul-Aug (every 4 years)
- **High volume:** 50+ matches daily across various levels

### Padel
- **Premier Padel season:** Feb-Dec
- **Growing calendar:** More events added each year as sport expands
- **Off-season:** Jan (brief)
- **Geographic focus:** Spain, Argentina, France, Italy primarily

## Known Issues

- **Table tennis high volume, low data:** Many daily matches but very shallow per-match data.
- **No TT stats API:** ITTF website has rankings but no match-level stats API.
- **Padel is a growing sport:** Source coverage still developing, limited historical data.
- **Premier Padel JS rendering:** May require Playwright for dynamic content.
- **The-Odds-API:** Does NOT cover table tennis or padel.
- **BetExplorer TT:** Only source with reliable table tennis odds.
- **Player identification:** Table tennis has many players with similar names (especially Asian players).
