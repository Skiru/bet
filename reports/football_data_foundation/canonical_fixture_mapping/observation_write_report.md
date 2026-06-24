# Observation Write Report

**Phase:** Football Data Foundation - A5 Canonical Fixture Resolution and Temp SQLite DB Mapping Proof  

## Observation Mapping & Population Proof

We successfully proved that the enrichment state/facts can be fully mapped to the repository's existing schema columns and structures using temporary SQLite.

### General Design & Deterministic Mapping Policy

The repository's `fixture_capability_observation` table imposes a `NOT NULL REFERENCES teams(id)` foreign key constraint on the `team_id` column. Because some enrichment facts are fixture-level (such as venue, kickoff, event status, and broadcast info) rather than team-specific, we designed and implemented a **Deterministic Team Handling Policy**:

1. **Team-Specific Facts:**
   - Facts starting or containing `home_` or ending with `_home` (e.g. `home_possessionPct`, `home_totalShots`, `home_team_record_summary`, `score_home`) are mapped directly to `home_team_id`.
   - Facts starting or containing `away_` or ending with `_away` (e.g. `away_possessionPct`, `away_totalShots`, `away_team_record_summary`, `score_away`) are mapped directly to `away_team_id`.

2. **Fixture-Level Facts:**
   - General facts (e.g. `event_status_state`, `venue_name`, `kickoff_utc`) are stored in separate observations for both the `home_team_id` and `away_team_id` to ensure complete coverage while satisfying the `NOT NULL` constraint.

### Populate Results Table

The following database counts were observed during the proof execution of the target profile `world-cup-2026`:

| Table Name | Inserted Rows | ID & Mapping Role |
|---|---|---|
| `evidence_package_revision` | `3` | Tracks completeness and member counts for each payload. |
| `sports_enrichment_run` | `1` | Records execution details, start/complete times, and metadata. |
| `source_operation_attempt` | `3` | Represents each provider fetch decision mapped to the run. |
| `fixture_capability_observation` | `6` | Stores the actual JSON-serialized payloads with a valid team_id. |
| `fixture_capability_projection` | `6` | Pins selected observations to the current active run. |

### Idempotency and Deduplication Verification

- **ID Re-Resolution Check:** Running the resolver a second time with the same input yielded the exact same canonical `fixture_id` (`1`), returning the status `MATCHED_EXISTING_FIXTURE` instead of creating another row.
- **Payload Hash Checks:** Payload SHA-256 values are verified to ensure that identical fact sets result in identical observation logical identities, preventing row proliferation.
