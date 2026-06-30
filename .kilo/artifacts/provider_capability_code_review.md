# Provider Capability Code Review

Performed production-grade code review of scanning/discovery provider capability routing and odds/market persistence.

## Executive Summary Findings

1. **OddsAPIioAdapter Contract and Odds Fetching**:
   - `OddsAPIioAdapter` in `src/bet/discovery/sources/odds_api_io.py` only calls `/events` via `self._client.get_events()`. It **does not** call `/odds` or `/odds/multi` during the standard discovery run. Therefore, it does not attach odds to discovered events, despite claims in header comments.
   
2. **DiscoveredEvent.odds Lifecycle & Drop Stages**:
   - **Deduplication/Merge**: `DiscoveredEvent.odds` survives deduplication and matches. `DeduplicationEngine.merge` assigns `odds=ev.odds` and merges them via `_attach_source` if subsequent sources have odds.
   - **JSON Output**: `EventDiscoveryCoordinator._write_json` **drops** the odds. It formats fixtures to write to `_s1_events.json` but completely omits the `"odds"` key.
   - **DB Persistence**: `EventDiscoveryCoordinator._persist` **drops** the odds. It saves fixtures, fixture sources, and scan results, but never writes any odds records to the `odds_history` table.
   - **Market Matrix**: Because of the above drops, the market matrix receives zero odds/markets from discovery, leading to `NO_MARKETS_OR_ODDS` status for all sports.

3. **The Odds API Flat Odds Schema Mismatch**:
   - `OddsAPIAdapter._extract_odds` flat-maps bookmakers into a flat `{"bookmaker|market|selection": price}` dict.
   - This format completely discards the line `point` (e.g. `Over 2.5` line value `2.5` is not stored as a separate point field or inside the selection name), causing schema and parsing mismatches with `extract_markets_from_odds_api` which expects a structured bookmaker/market/outcome hierarchy.

4. **Guaranteed Upstream Odds Step in Market Matrix**:
   - `generate_market_matrix.py` expects odds snapshot JSON or database entries in the `odds_history` table. There is **no guaranteed upstream odds snapshot or database persistence step** executed by the scan/discovery pipeline, leaving the matrix empty unless `fetch_odds_multi.py` is manually run or discovery is corrected.

5. **Diagnostic Status for Unavailable Providers**:
   - `EventDiscoveryCoordinator` tracks provider errors and unavailability in `SourceRunStats`. However, sport-level routing fails silently or reports generic partial success rather than detailed per-sport provider capability diagnostic failures.

---

## Detailed Provider Analysis

Refer to `.kilo/artifacts/provider_capability_matrix.json` for the structured capability data.
All 8 active adapters are registered and reviewed:
- `odds-api-io` (Primary replacement, multi-sport)
- `odds-api` (Secondary, tennis/football/basketball/hockey odds)
- `api-football` (Events-only)
- `api-basketball` (Events-only)
- `api-volleyball` (Events-only)
- `api-hockey` (Events-only)
- `football-data` (Events-only)
- `espn` (Events-only, no API key needed)
