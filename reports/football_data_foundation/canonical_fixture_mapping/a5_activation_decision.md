# A5 Activation Decision Report

**Phase:** Football Data Foundation - A5 Canonical Fixture Resolution and Temp SQLite DB Mapping Proof  

## Activation Decision Summary

The proof of concept for canonical fixture resolution and DB table mapping has been completely and successfully executed. We have shown that the existing repository schema can safely represent scanner events and enrichment facts using a temporary, isolated SQLite connection.

### Status Highlights

1. **Canonical Fixture Mapping Status**
   - **Status:** `DB_CANONICAL_MAPPING_PROVEN_IN_TEMP_SQLITE`
   - **Details:** The resolver correctly maps separate scanner and provider IDs, creates the necessary core tables, and maintains complete idempotency.

2. **Production DB Adapter Status**
   - **Status:** `PRODUCTION_DB_ADAPTER_DEFERRED`
   - **Details:** We defer connecting to the production database `betting/data/betting.db` to prevent premature mutations or risks to ongoing production processes.

3. **Matrix Activation Status**
   - **Status:** `MATRIX_ACTIVATION_DEFERRED`
   - **Details:** Provider capability matrix activation is deferred to maintain a safe, clean separation of concern.

4. **Routing Activation Status**
   - **Status:** `ROUTING_ACTIVATION_DEFERRED`
   - **Details:** Football routing activation is deferred to prevent downstream components (e.g. predictions, coupons, staking) from reading incomplete mapping states.

### Sufficiency of Temporary SQLite Proof

The temporary SQLite proof is **fully sufficient** for moving into the next migration and adapter phase. It demonstrates that the current schema version `20` handles:
- Core relationships (sports -> competitions -> teams -> fixtures).
- Multi-source references (`fixture_sources`).
- Generic sports enrichment concepts (`sports_entity`, `source_entity_reference`).
- Temporal observation captures (`fixture_capability_observation`, `fixture_capability_projection`).

### Next Required Conditions

- **For Real DB Adapter Activation:** User review and approval of the mapping schemas demonstrated in A5, followed by establishing a safe production bridge connection.
- **For Routing Activation:** Creation of a secure, isolated enrichment route configuration in `football_routing.yaml` that directs only enrichment-scoped traffic without bleeding into decision engines.
