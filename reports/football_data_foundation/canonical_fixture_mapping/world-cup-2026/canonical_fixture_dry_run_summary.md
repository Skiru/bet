# Canonical Fixture Resolution & DB Mapping Proof

**Profile ID:** `world-cup-2026`
**Scanner Event ID:** `66456944`
**Provider Event ID:** `760442`

## Resolution Metrics

- **Sport ID resolved:** `1`
- **Competition ID resolved:** `1`
- **Home Team ID resolved:** `1`
- **Away Team ID resolved:** `2`
- **Fixture ID resolved:** `1`
- **Sports Entity Event ID resolved:** `1`

## Idempotency Proof

- **First resolution status:** `CREATED_CANONICAL_FIXTURE`
- **Second resolution status:** `MATCHED_EXISTING_FIXTURE` (Expected: `MATCHED_EXISTING_FIXTURE`)
- **First Resolved Fixture ID:** `1`
- **Second Resolved Fixture ID:** `1`
- **Idempotency Validated:** `PASS`

## Database Table Counts Snapshot Before/After

| Table Name | Before | After | Delta |
|---|---|---|---|
| `sports` | `0` | `1` | `1` |
| `competitions` | `0` | `1` | `1` |
| `teams` | `0` | `2` | `2` |
| `fixtures` | `0` | `1` | `1` |
| `fixture_sources` | `0` | `2` | `2` |
| `scan_results` | `0` | `0` | `0` |
| `sports_entity` | `0` | `1` | `1` |
| `source_entity_reference` | `0` | `2` | `2` |
| `evidence_package_revision` | `0` | `3` | `3` |
| `sports_enrichment_run` | `0` | `1` | `1` |
| `source_operation_attempt` | `0` | `3` | `3` |
| `fixture_capability_observation` | `0` | `6` | `6` |
| `fixture_capability_projection` | `0` | `6` | `6` |

## Safety Assertions Verified

- **No real database touched:** `True` (Used `:memory:` temporary SQLite store)
- **Scanner reference separate:** `True` (Scanner event `66456944` and Provider event `760442` stored in distinct mapping records)
- **All observations/projections successfully linked:** `True`
