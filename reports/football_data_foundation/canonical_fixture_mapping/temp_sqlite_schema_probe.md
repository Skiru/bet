# Temp SQLite Schema Probe Report

**Phase:** Football Data Foundation - A5 Canonical Fixture Resolution and Temp SQLite DB Mapping Proof  

## Verification of Temporary Database Environment

We successfully initialized a temporary, in-memory SQLite store using the repository schema `src/bet/db/schema.sql` via `src/bet/db/schema.py:init_db`. 

### Probe Key Metrics

- **Schema Version Observed:** `20`
- **Foreign Keys Enabled:** `ON` (Verified via `PRAGMA foreign_keys = 1`)
- **Isolation Level:** Complete in-memory isolation (`:memory:` connection)
- **Zero Production Mutations:** Confirmed. `betting/data/betting.db` is completely untouched.

### Observed Table Counts (Pre-population)

All relevant tables exist and contain exactly `0` records:

| Table Name | Initial Record Count | Existence Verified |
|---|---|---|
| `sports` | `0` | Yes |
| `competitions` | `0` | Yes |
| `teams` | `0` | Yes |
| `fixtures` | `0` | Yes |
| `fixture_sources` | `0` | Yes |
| `scan_results` | `0` | Yes |
| `sports_entity` | `0` | Yes |
| `source_entity_reference` | `0` | Yes |
| `evidence_package_revision` | `0` | Yes |
| `sports_enrichment_run` | `0` | Yes |
| `source_operation_attempt` | `0` | Yes |
| `fixture_capability_observation` | `0` | Yes |
| `fixture_capability_projection` | `0` | Yes |
