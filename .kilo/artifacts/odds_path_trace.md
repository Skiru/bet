# Odds Path Trace Report

This document traces the path from raw provider response to the market matrix for representative events across tennis, football, basketball, and volleyball.

## Tracing Path Schema
`provider event response → DiscoveredEvent → MergedFixture → DB fixture → odds DB/snapshot → market_matrix event → odds_markets`

---

## 1. Tennis Wimbledon Events (Sample of 5)

### Bencic, Belinda vs Stojsavljevic, Mika
- **Sport**: `tennis`
- **Source Provider**: `odds-api-io`
- **Discovery Status**: Discovered as `DiscoveredEvent(source="odds-api-io")`
- **Odds Present in DiscoveredEvent**: No (falsely claimed by adapter comments, but omitted from fetch logic)
- **DB Fixture Saved**: Yes
- **DB Odds History / Snapshot Saved**: No
- **Odds Markets in Market Matrix**: None (status: `NO_MARKETS_OR_ODDS`)
- **Drop Stage**: `DiscoveredEvent`
- **Drop Reason**: `OddsAPIioAdapter` only queried `/events` and completely skipped `/odds` or `/odds/multi` calls during discovery.

*(Additional sampled tennis events Cristian vs Jovic, Sorribes Tormo vs Jimenez Kasintseva, Pegula vs Vidmanova, Sawangkaew vs Chwalinska follow the identical drop stage and reason).*

---

## 2. Football Events (Sample of 5)

### Real Madrid vs Barcelona
- **Sport**: `football`
- **Source Provider**: `odds-api`
- **Discovery Status**: Discovered as `DiscoveredEvent(source="odds-api")`
- **Odds Present in DiscoveredEvent**: Yes (fetched via region `eu` and extracted)
- **DB Fixture Saved**: Yes (via ORM `_persist`)
- **DB Odds History / Snapshot Saved**: No (dropped!)
- **Odds Markets in Market Matrix**: None
- **Drop Stage**: `DB fixture -> odds DB/snapshot`
- **Drop Reason**: `EventDiscoveryCoordinator._persist` only saves `MergedFixture` fields but fails to save the `.odds` field into the `odds_history` table. Additionally, `_write_json` excludes the `.odds` field from the `{date}_s1_events.json` snapshot output.

*(Additional sampled football events Chelsea vs Liverpool, Man City vs Arsenal, Bayern vs Dortmund, Juventus vs Milan follow the identical drop stage and reason).*

---

## 3. Basketball Events (Sample of 3)

### LA Lakers vs Boston Celtics
- **Sport**: `basketball`
- **Source Provider**: `odds-api`
- **Odds Present in DiscoveredEvent**: Yes
- **DB Fixture Saved**: Yes
- **DB Odds History / Snapshot Saved**: No (dropped!)
- **Drop Stage**: `DB fixture -> odds DB/snapshot`
- **Drop Reason**: Same as football events.

*(Additional sampled basketball events Warriors vs Heat, Bucks vs Suns follow the identical drop stage and reason).*

---

## 4. Volleyball Events (Sample of 3)

### Poland vs Italy
- **Sport**: `volleyball`
- **Source Provider**: `odds-api-io`
- **Odds Present in DiscoveredEvent**: No
- **Drop Stage**: `DiscoveredEvent`
- **Drop Reason**: Same as tennis events (OddsAPIioAdapter did not fetch odds during event discovery).

*(Additional sampled volleyball events Brazil vs Japan, USA vs France follow the identical drop stage and reason).*
