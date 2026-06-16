# M0A_TRADITIONAL_SPORTS_PROVIDER_REALITY_MAP

## 1. Documentation-Derived Support
- **ESPN**: Free, undocumented REST API. Known to support football, basketball, hockey, tennis, and volleyball scoreboards and summaries.
- **API-Sports**: Strict rate limits. Paginated historical data with `update` watermarks. Official documentation confirms support for football, basketball, hockey, and volleyball. Tennis is not offered in the current product suite.
- **TheSportsDB**: Public free tier truncates responses heavily. Documented to use `123` for free discovery.
- **SportDB.dev**: REST paths under `/api/...` authenticated via `X-API-Key`. Provides MCP functionality. Official documentation declares multisport support including football, basketball, tennis, and hockey.

## 2. Live-Proven Capability
*Capabilities explicitly proven by a physical HTTP response containing all mandatory fields.*

- **ESPN**:
  - Scoreboard/Discovery (Football, Basketball, Hockey, Tennis, Volleyball)
  - Completed Event Summary (Football, Basketball, Hockey, Tennis, Volleyball)
  - Standings (Football, Basketball, Hockey, Tennis, Volleyball)
- **TheSportsDB**:
  - Entity Lookup (Football, Basketball, Hockey, Tennis, Volleyball)
  - External-ID Crosswalk (Football ONLY - `idAPIfootball` and `idESPN` observed)

## 3. Blocked Capability
*Capabilities where access was physically prevented due to missing credentials, yielding no network attempt.*

- **API-Sports**: Data endpoints for Football, Basketball, Hockey, and Volleyball (`BLOCKED_BY_CONFIGURATION`)
- **SportDB.dev**: REST endpoints for Football, Basketball, Hockey, Tennis, and Volleyball (`BLOCKED_BY_CONFIGURATION`)
- **SportDB.dev**: MCP endpoints (`BLOCKED_BY_CONFIGURATION`)

## 4. Unproven Capability
*Capabilities we theoretically support but lack evidence for due to blocks or missing evidence.*

- **TheSportsDB**: External-ID Crosswalk for Basketball, Hockey, Tennis, and Volleyball (no external IDs observed in responses yet)
- **ESPN**: Reliable update watermarks (absent in payload)

## 5. Rejected Capability
*Capabilities that were proven unsuitable or are definitively not offered.*

- **API-Sports**: Tennis data (`NOT_OFFERED` per documentation)

## 6. Provider Decisions per Capability

### Football
- **Discovery**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Completed Event**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Event Stats**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: PRIMARY: `thesportsdb`
- **Standings**: PRIMARY: `espn`

### Basketball
- **Discovery**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Completed Event**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Event/Player Stats**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: UNPROVEN: `thesportsdb`
- **Standings**: PRIMARY: `espn`

### Hockey
- **Discovery**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Completed Event**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: UNPROVEN: `thesportsdb`
- **Standings**: PRIMARY: `espn`

### Tennis
- **Discovery**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `sportdb`, NOT_OFFERED: `api-sports`
- **Completed Event**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `sportdb`, NOT_OFFERED: `api-sports`
- **Event/Player Stats**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `sportdb`, NOT_OFFERED: `api-sports`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: UNPROVEN: `thesportsdb`
- **Standings/Ranking**: PRIMARY: `espn`

### Volleyball
- **Discovery**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Completed Event**: PRIMARY: `espn`, BLOCKED_BY_CONFIGURATION: `api-sports`, BLOCKED_BY_CONFIGURATION: `sportdb`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: UNPROVEN: `thesportsdb`
- **Standings**: PRIMARY: `espn`

## 7. Report Counts
- Previous declared physical attempts: 41
- Previous newly discovered uncounted attempts: 2
- Final closure physical attempts: 20
- Corrected cumulative physical attempts: 63
