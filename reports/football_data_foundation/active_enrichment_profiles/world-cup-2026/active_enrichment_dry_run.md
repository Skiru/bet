# Active Enrichment Dry-Run Reports - Profile: world-cup-2026

- Generated at UTC: `2026-06-19T19:53:16.460346+00:00`
- No secrets, cookies, proxy settings, Tor, or browser profiles were used.
- Unit tests remain offline and do not perform network calls.
- Betting decision logic and production route selection are unchanged.

## Run 1: Empty Store (Completeness check MISSING)
- **Status**: `ENRICHED_COMPLETE`
### Decisions:
  - Capability `current_discovery` => `FETCH_REQUIRED` (Reason: No completeness record exists for capability current_discovery.)
  - Capability `detailed_metrics` => `FETCH_REQUIRED` (Reason: No completeness record exists for capability detailed_metrics.)
  - Capability `current_form` => `FETCH_REQUIRED` (Reason: No completeness record exists for capability current_form.)
### Generated Facts:
  - `current_discovery` / `current_discovery_status` => value `VERIFIED_SCHEDULED` (Retrieved from: espn-fifa-worldcup, Consensus: single_source_verified)
  - `detailed_metrics` / `detailed_metrics_status` => value `VERIFIED_SCHEDULED` (Retrieved from: espn-fifa-worldcup, Consensus: single_source_verified)
  - `current_form` / `current_form_status` => value `VERIFIED_SCHEDULED` (Retrieved from: espn-fifa-worldcup, Consensus: single_source_verified)

## Run 2: Reuse Store (Completeness check COMPLETE_FRESH)
- **Status**: `ENRICHED_COMPLETE`
### Decisions:
  - Capability `current_discovery` => `REUSE_CACHED` (Reason: Completeness record is fresh and clean.)
  - Capability `detailed_metrics` => `REUSE_CACHED` (Reason: Completeness record is fresh and clean.)
  - Capability `current_form` => `REUSE_CACHED` (Reason: Completeness record is fresh and clean.)

## Run 3: Force-Refresh (Completeness bypassed)
- **Status**: `ENRICHED_COMPLETE`
### Decisions:
  - Capability `current_discovery` => `FETCH_FORCED` (Reason: Explicit force_refresh flag requested.)
  - Capability `detailed_metrics` => `FETCH_FORCED` (Reason: Explicit force_refresh flag requested.)
  - Capability `current_form` => `FETCH_FORCED` (Reason: Explicit force_refresh flag requested.)
