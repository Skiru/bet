# M0A_TRADITIONAL_SPORTS_PROVIDER_REALITY_MAP

## 1. Repository Inventory
- **ESPN**: Fully integrated in `src/bet/api_clients/espn_client.py` and adapter scripts. Scrapers are registered for football, basketball, hockey, tennis, and volleyball. Free, no authentication required.
- **API-Sports**: Football, Basketball, Hockey, and Volleyball are registered. Tennis is missing/unreachable. Uses `API_SPORTS_KEY`.
- **TheSportsDB**: Exists (`src/bet/api_clients/thesportsdb.py`). Uses the public free tier key `123`.
- **SportDB.dev**: Mentions in configuration, but lacks an active Python client. The S0 specification demands its probing for football capabilities.

## 2. Documentation-Derived Facts
- **ESPN**: Free, undocumented REST API. Used by native clients across multiple sports for scoreboard and statistics.
- **API-Sports**: Strict rate limits. Paginated historical data with `update` watermarks. No tennis offering in the current product suite.
- **TheSportsDB**: Public free tier truncates responses heavily. Documented to use `123` for free discovery.
- **SportDB.dev**: REST paths must be under `/api/...` authenticated via `X-API-Key`. Provides MCP functionality at `https://api.sportdb.dev/mcp/`. Does not offer basketball, hockey, tennis, or volleyball.

## 3. Live Verified Evidence
*Based on 20 executed physical live attempts with strict budget enforcement (Max: 40).*

- **ESPN**: `SUCCESS`. The free API reliably returns scoreboard discovery (`events.id`, `events.status.type.state`), completed event context (`boxscore`), and standings across all 5 sports.
- **API-Sports**: `BLOCKED_BY_CONFIGURATION`. The probe correctly observed the absence of `API_SPORTS_KEY` and prevented physical data execution.
- **TheSportsDB**: `SUCCESS`. The public `123` key resolved entities like `Arsenal` in football and `Roger Federer` in tennis, albeit with free tier truncation restrictions.
- **SportDB.dev (REST)**: `BLOCKED_BY_CONFIGURATION`. `SPORTDB_API_KEY` was absent. Non-football sports were properly rejected as `NOT_SUPPORTED`.
- **SportDB.dev (MCP)**: `NOT_CONFIGURED`. No active MCP server configuration was found in the local `kilo.json`. This did not consume a physical request.

## 4. Blocked or Unproven Capabilities
- **API-Sports Data Capabilities**: Unproven due to missing credentials.
- **API-Sports Tennis**: `NOT_OFFERED` based on documented product portfolio.
- **SportDB.dev Data Capabilities**: Unproven due to missing credentials and MCP configuration.

## 5. Provider Decisions per Capability

### Football
- **Discovery**: PRIMARY: `espn`, SHADOW: `api-sports`, REJECT: `thesportsdb`
- **Completed Event**: PRIMARY: `espn`, FALLBACK: `api-sports`, REJECT: `sportdb`
- **Event Stats**: PRIMARY: `espn`, UNPROVEN: `api-sports`, REJECT: `sportdb`
- **Crosswalk/Identity**: PRIMARY: `thesportsdb`, FALLBACK: `espn`
- **Standings**: PRIMARY: `espn`

### Basketball
- **Discovery**: PRIMARY: `espn`, FALLBACK: `api-sports`
- **Completed Event**: PRIMARY: `espn`, UNPROVEN: `api-sports`
- **Event/Player Stats**: PRIMARY: `espn`, UNPROVEN: `api-sports`
- **Standings**: PRIMARY: `espn`

### Hockey
- **Discovery**: PRIMARY: `espn`, FALLBACK: `api-sports`
- **Completed Event**: PRIMARY: `espn`, UNPROVEN: `api-sports`
- **Standings**: PRIMARY: `espn`

### Tennis
- **Discovery**: PRIMARY: `espn`
- **Completed Event**: PRIMARY: `espn`
- **Event/Player Stats**: PRIMARY: `espn`
- **Crosswalk/Identity**: PRIMARY: `thesportsdb`
- **Standings/Ranking**: PRIMARY: `espn`

### Volleyball
- **Discovery**: PRIMARY: `espn`, FALLBACK: `api-sports`
- **Completed Event**: PRIMARY: `espn`, UNPROVEN: `api-sports`
- **Standings**: PRIMARY: `espn`

## 6. Incremental-Sync Economics
- **Identity**: ESPN provides stable IDs for all 5 sports. TheSportsDB provides crosswalk IDs.
- **Watermarks**: API-Sports provides robust `update` watermarks. ESPN lacks watermarks and requires date-bound polling (e.g., last 3 days).
- **Refresh Cadence**: Daily for scheduled fixtures; immediate post-match with a 24-hour correction-recheck window for completed events.
- **L5/L10/H2H Stats**: Do not rely on provider native endpoints for dynamic stats. These should be calculated locally from a unified fact database of completed matches to ensure idempotency and replayability.

## 7. Crosswalk Findings
- TheSportsDB correctly acts as a universal Rosetta Stone for standardizing names and returning external IDs (e.g., matching "Arsenal" or "Roger Federer" across sports). Minimal truncation limits historical scraping but satisfies identity resolution.

## 8. Minimal Temporal Spine Implications
The temporal spine remains fully achievable with the proven data:
1. `provider_entities`: stable mapping from canonical ID to provider ID (espn-123). Identity: canonical_id + provider + sport.
2. `source_artifacts`: raw JSON responses containing complete boxscores and identities.
3. `sync_cursors`: temporal cursors for date-based polling (provider, sport, last_sync_date).

## 9. Recommended Next Slice
Implement exactly **one football completed event flow using ESPN**.
Fetch raw scoreboard evidence, resolve canonical identity via TheSportsDB, and store typed team-match facts with replay and idempotent rerun capabilities to prove the ingestion layer. Do not start S1S until this is validated.

## 10. Unresolved Blockers
- **Missing Credentials**: `SPORTDB_API_KEY` and `API_SPORTS_KEY` are not configured in the active environment.
- **MCP Configuration**: The `sportdb.dev` MCP server is not registered in `kilo.json`.
