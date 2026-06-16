# M0A_TRADITIONAL_SPORTS_PROVIDER_REALITY_MAP

## Phase A: Existing Repository Inventory
- **ESPN**: Fully integrated in `src/bet/api_clients/espn_client.py`, `espn_odds.py`, `espn_stats.py`. Scrapers registered for football, basketball, hockey, tennis, volleyball. No environment variables required. Free, heavily used by S1, S3.
- **API-Sports**: Football, Basketball, Hockey, Volleyball registered. Uses `API_SPORTS_KEY`. Tennis is missing/unreachable at v1.tennis.api-sports.io. Used as fallback in enrichment.
- **TheSportsDB**: Exists (`src/bet/api_clients/thesportsdb.py`), but deprecated/disabled (97.8% fail rate noted). Free tier key is `3`. Used for ID resolution.
- **SportDB.dev**: Mentioned in `football_routing.yaml` and final reports. Marked as BLOCKED (no API key). No active Python client implementation found.

## Phase B: Provider Contract Inspection
- **ESPN**: Free, undocumented REST. No rate limits observed. Deep stats, gamelogs, standings. No native updated_at.
- **API-Sports**: Strict rate limits (100/day per sport on free plan). Requires `API_SPORTS_KEY`. Paginated, comprehensive historical data. Has `update` timestamps on some endpoints.
- **TheSportsDB**: Basic data. Free tier is rate limited. No live stats. Good for cross-referencing.
- **SportDB.dev**: Explored endpoints returned 404. No documentation for MCP.

## Phase C: Bounded Live Reconnaissance
Max Budget: 50. Actual Used: 21.
- **ESPN**: SUCCESS (5/5 sports). High reliability.
- **API-Sports**: SUCCESS (4/5 sports). Tennis failed DNS resolution.
- **TheSportsDB**: SUCCESS (5/5 sports).
- **SportDB.dev**: HTTP 404 (5/5 sports). MCP Unavailable.

## Phase D: Incremental-Sync Assessment
- **Identity**: ESPN has stable IDs (`espn-football`, `espn-basketball`, etc.).
- **Watermarks**: ESPN lacks watermarks; must use date-based polling (e.g., last 3 days). API-Sports provides update timestamps.
- **Refresh Cadence**: Daily for scheduled events. Post-match for completed events (with 24h correction recheck).
- **Derived Stats**: L5/H2H should be calculated locally from immutable match facts.

## Phase E: Provider Decisions
- **football**: PRIMARY: `espn`, FALLBACK: `api-sports`, IDENTITY_ONLY: `thesportsdb`, REJECT: `sportdb.dev`
- **basketball**: PRIMARY: `espn`, FALLBACK: `api-sports`, IDENTITY_ONLY: `thesportsdb`, REJECT: `sportdb.dev`
- **hockey**: PRIMARY: `espn`, FALLBACK: `api-sports`, IDENTITY_ONLY: `thesportsdb`, REJECT: `sportdb.dev`
- **tennis**: PRIMARY: `espn`, FALLBACK: `none` (api-sports DNS failed), IDENTITY_ONLY: `thesportsdb`, REJECT: `sportdb.dev`
- **volleyball**: PRIMARY: `espn`, FALLBACK: `api-sports`, IDENTITY_ONLY: `thesportsdb`, REJECT: `sportdb.dev`

## Phase F: Minimal Temporal Spine Proposal
We propose common minimal temporal concepts based on all five sports:
1. `provider_entities`: stable mapping from canonical ID to provider ID (espn-123). Identity: canonical_id + provider + sport.
2. `source_artifacts`: raw JSON responses. Reused existing `source_artifacts`.
3. `sync_cursors`: temporal cursors for date-based polling (provider, sport, last_sync_date).
4. `entity_memberships`: (valid_from, valid_to) for roster/transfer tracking. Reuses/enhances team rosters.

## Phase G: Next Implementation Slice
**Recommended Next Slice**: Implement exactly one football completed event using the ESPN provider. Fetch raw scoreboard evidence, resolve canonical identity, and store typed team-match facts with replay and idempotent rerun capabilities.
