---
name: bet-scanning-combat
description: "Combat/MMA-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Combat/MMA

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/mma/ | flashscore.com | Fixtures | UFC, ONE, PFL |
| https://www.flashscore.com/mma/ufc/ | flashscore.com | Fixtures | UFC specific |
| https://www.betclic.pl/mma-s38 | betclic.pl | Execution | ⚠ Always 403 |
| https://scores24.live/en/mma | scores24.live | Data | MMA section |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | fighter1, fighter2, time, event_name |
| scores24.live | `scores24_adapter` | H2H, form |

## Data Quality Standards

- **Minimum events per day:** 1 (sporadic event schedule)
- **Required stat keys:** takedowns, strikes, submissions (when available)
- **Optional keys:** knockdowns, control_time, significant_strikes, takedown_accuracy
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day or upcoming card

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| scores24.live | 20s | 1s | 2 |

**Total scanner timeout:** 2 minutes

## Fallback Chains

**Market odds:**
1. BetExplorer → 2. Tapology → (no tertiary)

**Statistical data:**
1. UFCstats → 2. Tapology → 3. Sherdog

**Tipsters:**
1. Sportsgambler → 2. PicksWise → 3. Tipstrr

## Seasonal Considerations

- **UFC:** Year-round, typically Saturday events (numbered UFC + Fight Night cards)
- **ONE Championship:** Year-round, Asia-focused (Friday/Saturday)
- **PFL:** Seasonal format (Apr-Nov)
- **Bellator:** Discontinued — merged into PFL
- **Most weeks:** 1 UFC event (8-14 fights per card)
- **International Fight Week:** July (multiple events)

## Known Issues

- **Sporadic schedule:** Many days have zero MMA events. This is normal.
- **No free MMA stats API.** Fighter data requires per-fighter page scraping.
- **UFCstats.com:** Best free source but no dedicated adapter. Manual scraping needed.
- **Tapology:** Fighter records, fight history. No adapter but scrapeable.
- **Sherdog:** Similar to Tapology but ad-heavy. No adapter.
- **ESPN MMA:** Limited to UFC, mostly behind ESPN+ paywall.
- **Weight class matters:** Fighter stats only meaningful within same weight class.
- **Short-notice replacements:** Fighters pull out frequently, replacements change odds dramatically.
