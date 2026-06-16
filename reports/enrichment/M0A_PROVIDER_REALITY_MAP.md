# M0A_TRADITIONAL_SPORTS_PROVIDER_REALITY_MAP

## 1. Documentation-Derived Support
- **ESPN**: Free, undocumented REST API. Known to support football, basketball, hockey, tennis, and volleyball scoreboards and summaries.
- **API-Sports**: Strict rate limits. Paginated historical data with `update` watermarks. Verified capability for football, basketball, hockey, and volleyball. Tennis is `NOT_OFFERED` in the current product suite. Some historic plan restrictions exist (e.g., standings require higher tiers).
- **TheSportsDB**: Public free tier truncates responses heavily. Documented to use `123` for free discovery.
- **SportDB.dev**: REST paths under `/api/flashscore/...` authenticated via `X-API-Key`. Provides MCP functionality (unconfigured locally). Live discovery, match details, and match stats proven for football. Discovery proven for basketball, hockey, tennis, and volleyball.

## 2. Live-Proven Capability
*Capabilities explicitly proven by a physical HTTP response containing all mandatory fields.*

- **ESPN**:
  - Scoreboard/Discovery (Football, Basketball, Hockey, Tennis, Volleyball)
  - Completed Event Summary (Football, Basketball, Hockey, Tennis, Volleyball)
  - Standings (Football, Basketball, Hockey, Tennis, Volleyball)
- **TheSportsDB**:
  - Entity Lookup (Football, Basketball, Hockey, Tennis, Volleyball)
  - External-ID Crosswalk (Football ONLY - `idESPN` and `idAPIfootball` observed)
- **API-Sports**:
  - Discovery (Football, Basketball, Hockey, Volleyball)
  - Completed Event (Football, Basketball, Hockey, Volleyball)
  - Event Stats (Football)
- **SportDB.dev**:
  - Discovery (Football, Basketball, Hockey, Tennis, Volleyball)
  - Completed Event (Football)
  - Event Stats (Football)

## 3. Blocked Capability
*Capabilities where access was physically prevented due to missing credentials, yielding no network attempt.*

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
- **Discovery**: PRIMARY: `api-sports`, SHADOW: `espn`, FALLBACK: `sportdb`
- **Completed Event**: PRIMARY: `api-sports`, SHADOW: `espn`, FALLBACK: `sportdb`
- **Event Stats**: PRIMARY: `api-sports`, SHADOW: `espn`, FALLBACK: `sportdb`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: PRIMARY: `thesportsdb`
- **Standings**: PRIMARY: `espn`, PLAN_RESTRICTED: `api-sports`

### Basketball
- **Discovery**: PRIMARY: `api-sports`, SHADOW: `espn`, FALLBACK: `sportdb`
- **Completed Event**: PRIMARY: `api-sports`, SHADOW: `espn`
- **Event/Player Stats**: PRIMARY: `espn`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: UNPROVEN: `thesportsdb`
- **Standings**: PRIMARY: `espn`

### Hockey
- **Discovery**: PRIMARY: `api-sports`, SHADOW: `espn`, FALLBACK: `sportdb`
- **Completed Event**: PRIMARY: `api-sports`, SHADOW: `espn`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: UNPROVEN: `thesportsdb`
- **Standings**: PRIMARY: `espn`

### Tennis
- **Discovery**: PRIMARY: `espn`, FALLBACK: `sportdb`, NOT_OFFERED: `api-sports`
- **Completed Event**: PRIMARY: `espn`, NOT_OFFERED: `api-sports`
- **Event/Player Stats**: PRIMARY: `espn`, NOT_OFFERED: `api-sports`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: UNPROVEN: `thesportsdb`
- **Standings/Ranking**: PRIMARY: `espn`

### Volleyball
- **Discovery**: PRIMARY: `api-sports`, SHADOW: `espn`, FALLBACK: `sportdb`
- **Completed Event**: PRIMARY: `api-sports`, SHADOW: `espn`
- **Entity Lookup**: PRIMARY: `thesportsdb`
- **External-ID Crosswalk**: UNPROVEN: `thesportsdb`
- **Standings**: PRIMARY: `espn`

## 7. Report Counts
- Previous declared physical attempts: 63
- Supplement physical attempts (API-Sports + SportDB): 16
- Final closure physical attempts: 79

## 8. Provider Decision (Football First Slice)
**Option B: API-Sports primary, ESPN shadow.**
- API-Sports provides robust, heavily structured, and predictable JSON with canonical IDs and pagination. It successfully proved capabilities for discovery, matches, and stats. Standings face a plan limitation but can rely on ESPN if needed.
- SportDB provides good real-time coverage via the Flashscore bridge, making it a reliable fallback.
- **SportDB.dev Roles**: SportDB.dev will be deferred for the first slice. It lacks structured historic standings in the immediate `/live` + details paths without deep navigation and has `EMPTY_RESULT` quirks on matches lacking events.
