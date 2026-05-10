---
name: bet-scanning-esports
description: "Esports-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, HLTV rate limits, and validation rules."
user-invokable: false
---

# Scanning Esports

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/esports/ | flashscore.com | Fixtures | CS2, LoL, Dota2 |
| https://www.flashscore.com/esports/counter-strike/ | flashscore.com | Fixtures | CS2 specific |
| https://www.hltv.org/matches | hltv.org | Stats | CS2 matches + team stats |
| https://www.gosugamers.net/ | gosugamers.net | Multi-game | Match listings |
| https://www.betexplorer.com/esports/ | betexplorer.com | Odds | Esports markets |
| https://scores24.live/en/csgo | scores24.live | Data | CS2 section |
| https://www.betclic.pl/esport-s46 | betclic.pl | Execution | ⚠ Always 403 |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | team1, team2, time, game title |
| hltv.org | `hltv_adapter` | match format (BO1/BO3/BO5), map names |
| betexplorer.com | `betexplorer_adapter` | odds[] |
| scores24.live | `scores24_adapter` | H2H, form |

## Data Quality Standards

- **Minimum events per day:** 5
- **Required stat keys:** maps, rounds, format (BO1/BO3/BO5)
- **Optional keys:** kills, deaths, ADR, rating (from HLTV stats pages)
- **Multi-source threshold:** ≥2 sources per event
- **Data freshness:** Same-day data only

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| hltv.org | 30s | 3s (rate-limited) | 1 |
| gosugamers.net | 20s | 2s | 1 |
| betexplorer.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |

**Total scanner timeout:** 5 minutes

## Fallback Chains

**Market odds:**
1. BetExplorer → 2. GosuGamers → (no tertiary)

**Statistical data:**
1. HLTV (stats pages only) → 2. Liquipedia → 3. VLR.gg/BO3.gg

**Tipsters:**
1. GosuGamers → 2. Tipstrr → 3. BO3.gg

## Seasonal Considerations

- **CS2 Majors:** Two per year (typically Mar and Oct/Nov)
- **Pro League/ESL events:** Year-round, tournament-clustered
- **Player breaks:** Jan and Jul (brief, some events continue)
- **Roster changes:** Between Majors — affects team data relevance
- **LoL Worlds:** Oct-Nov. MSI: May.
- **Dota2 TI:** Aug-Oct.

## Known Issues

- **HLTV rate limiting:** Aggressive anti-bot. Max 1 request per 3 seconds. IP ban after rapid requests. Stats pages OK, tips/predictions pages → 403.
- **No detailed API on free tier:** No free esports stats API exists.
- **CS2 map pool changes:** Maps rotate, historical data on removed maps irrelevant.
- **Game-specific stat models:** CS2 (rounds, maps), LoL (dragons, barons, towers), Dota2 (heroes, towers). Different analysis per game.
- **Team roster instability:** Esports teams change players frequently. Historical data may not reflect current roster.
- **The-Odds-API:** Does NOT cover esports.
- **GosuGamers:** Coverage varies, sometimes slow to update.
