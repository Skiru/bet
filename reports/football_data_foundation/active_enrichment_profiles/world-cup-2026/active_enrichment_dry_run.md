# Active Enrichment Dry-Run Reports - Profile: world-cup-2026

- Generated at UTC: `2026-06-19T20:35:25.079525+00:00`
- No secrets, cookies, proxy settings, Tor, or browser profiles were used.
- Unit tests remain offline and do not perform network calls.
- Betting decision logic and production route selection are unchanged.

## Run 1: Empty Store (Completeness check MISSING)
- **Status**: `ENRICH_FAILED_CLOSED`
### Decisions:
  - Capability `current_discovery` => `FETCH_REQUIRED` (Reason: No completeness record exists for capability current_discovery.)
  - Capability `detailed_metrics` => `FETCH_REQUIRED` (Reason: No completeness record exists for capability detailed_metrics.)
  - Capability `current_form` => `FETCH_REQUIRED` (Reason: No completeness record exists for capability current_form.)
### Generated Facts:

## Run 2: Reuse Store (Completeness check COMPLETE_FRESH)
- **Status**: `ENRICHED_COMPLETE`
### Decisions:
  - Capability `current_discovery` => `REUSE_CACHED` (Reason: Completeness record is fresh and clean.)
  - Capability `detailed_metrics` => `REUSE_CACHED` (Reason: Completeness record is fresh and clean.)
  - Capability `current_form` => `REUSE_CACHED` (Reason: Completeness record is fresh and clean.)
### Generated Facts:
  - `current_discovery` / `event_status_state` => text `in` num `None`
  - `current_discovery` / `event_status_name` => text `STATUS_SECOND_HALF` num `None`
  - `current_discovery` / `kickoff_utc` => text `2026-06-19T19:00Z` num `None`
  - `current_discovery` / `kickoff_local` => text `2026-06-19T21:00:00+02:00` num `None`
  - `current_discovery` / `venue_name` => text `Lumen Field` num `None`
  - `current_discovery` / `venue_city` => text `Seattle, Washington` num `None`
  - `current_discovery` / `broadcast_name_1` => text `FOX` num `None`
  - `current_discovery` / `broadcast_name_2` => text `Tele` num `None`
  - `current_discovery` / `broadcast_name_3` => text `FOX One` num `None`
  - `current_discovery` / `score_home` => text `None` num `2.0`
  - `current_discovery` / `score_away` => text `None` num `0.0`
  - `detailed_metrics` / `home_possessionPct` => text `None` num `71.5`
  - `detailed_metrics` / `home_shotsOnTarget` => text `None` num `2.0`
  - `detailed_metrics` / `home_totalShots` => text `None` num `11.0`
  - `detailed_metrics` / `away_possessionPct` => text `None` num `28.5`
  - `detailed_metrics` / `away_shotsOnTarget` => text `None` num `1.0`
  - `detailed_metrics` / `away_totalShots` => text `None` num `2.0`
  - `current_form` / `home_team_record_summary` => text `1-0-0` num `None`
  - `current_form` / `away_team_record_summary` => text `1-0-0` num `None`

## Run 3: Force-Refresh (Completeness bypassed)
- **Status**: `ENRICHED_COMPLETE`
### Decisions:
  - Capability `current_discovery` => `FETCH_FORCED` (Reason: Explicit force_refresh flag requested.)
  - Capability `detailed_metrics` => `FETCH_FORCED` (Reason: Explicit force_refresh flag requested.)
  - Capability `current_form` => `FETCH_FORCED` (Reason: Explicit force_refresh flag requested.)
### Generated Facts:
  - `current_discovery` / `event_status_state` => text `in` num `None`
  - `current_discovery` / `event_status_name` => text `STATUS_SECOND_HALF` num `None`
  - `current_discovery` / `kickoff_utc` => text `2026-06-19T19:00Z` num `None`
  - `current_discovery` / `kickoff_local` => text `2026-06-19T21:00:00+02:00` num `None`
  - `current_discovery` / `venue_name` => text `Lumen Field` num `None`
  - `current_discovery` / `venue_city` => text `Seattle, Washington` num `None`
  - `current_discovery` / `broadcast_name_1` => text `FOX` num `None`
  - `current_discovery` / `broadcast_name_2` => text `Tele` num `None`
  - `current_discovery` / `broadcast_name_3` => text `FOX One` num `None`
  - `current_discovery` / `score_home` => text `None` num `2.0`
  - `current_discovery` / `score_away` => text `None` num `0.0`
  - `detailed_metrics` / `home_possessionPct` => text `None` num `71.5`
  - `detailed_metrics` / `home_shotsOnTarget` => text `None` num `2.0`
  - `detailed_metrics` / `home_totalShots` => text `None` num `11.0`
  - `detailed_metrics` / `away_possessionPct` => text `None` num `28.5`
  - `detailed_metrics` / `away_shotsOnTarget` => text `None` num `1.0`
  - `detailed_metrics` / `away_totalShots` => text `None` num `2.0`
  - `current_form` / `home_team_record_summary` => text `1-0-0` num `None`
  - `current_form` / `away_team_record_summary` => text `1-0-0` num `None`
