# Enrichment Completeness Decisions Report - FIFA World Cup 2026

This report documents the behavioral proof for the state-store completeness checks and fetch decisions.

## Scenarios Proven

### 1. Empty State Store Run
- **Condition**: First dry-run where no completeness record exists.
- **Results**:
  - `current_discovery` capability => `FETCH_REQUIRED` (No completeness record exists for capability current_discovery)
  - `detailed_metrics` capability => `FETCH_REQUIRED` (No completeness record exists for capability detailed_metrics)

### 2. Reuse State Store Run
- **Condition**: Second dry-run after writing fresh completeness and evidence records.
- **Results**:
  - `current_discovery` capability => `REUSE_CACHED` (Completeness record is fresh and clean)
  - `detailed_metrics` capability => `REUSE_CACHED` (Completeness record is fresh and clean)

### 3. Force-Refresh Run
- **Condition**: Dry-run with explicit `--force-refresh` requested.
- **Results**:
  - `current_discovery` capability => `FETCH_FORCED` (Explicit force_refresh flag requested)

### 4. Unsupported Capability/Provider
- **Condition**: Missing/unsupported provider support (e.g. Understat World Cup advanced_xg xG data).
- **Results**:
  - `advanced_xg` capability => `SKIP_UNSUPPORTED` (Capability or provider marked as unsupported for this profile)

## Persistence Strategy
To maintain the highest repository safety and prevent accidental DB modifications, we utilize a file-backed `EnrichmentStateStore` adapter under `reports/football_data_foundation/active_enrichment_profiles/world-cup-2026/state_store`. Production SQL DB migration remains deferred.
