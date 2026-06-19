# Football Data Foundation - Code/Schema/Consumer/Persistence Recon

## 1. Modules Loading `provider_capability_matrix.json`
- `src/bet/enrichment/football_service.py`: Loads and parses the capability matrix inside `load_provider_capability_matrix()` and resolves routing qualifications in `_resolve_route_qualification()`.
- Various test suites and migration scripts validate the JSON structure against active shadow/selectable statuses.

## 2. Modules Loading `football_routing.yaml`
- `src/bet/enrichment/football_service.py`: Uses the YAML file to resolve configured production, shadow, and candidate routes.

## 3. Modules Consuming `SourceOperationResult`
- `src/bet/enrichment/football_service.py`
- `src/bet/enrichment/football_data_foundation/calibration.py`
- `src/bet/enrichment/football_data_foundation/connector_kernel/__init__.py`

## 4. Active Enrichment Schema & Routing Representation
- The schema of `provider_capability_matrix.json` can express active enrichment by keeping a valid status (e.g. `CERTIFIED_SELECTABLE` or `CERTIFIED_SHADOW`) and adding extra fields:
  - `active_enrichment: true`
  - `selectable_as_projection: true`
  - `production_betting_decision: false`
- This ensures full compatibility with the existing parser in `football_service.py` while preventing active enrichment from being misused for autonomous production betting decisions.

## 5. Persistence Store & Migration Conventions
- While the repository has a persistent SQLite DB (`betting.db`) with tables like `fixture_capability_observation` and `source_operation_attempt`, implementing a generic active enrichment state store inside the DB would require schema migrations.
- To maintain perfect safety and isolation, we implement a file-backed `EnrichmentStateStore` adapter under `reports/football_data_foundation/active_enrichment_profiles/world-cup-2026/state_store`. Production DB integration is explicitly marked as deferred.

## 6. Profile-Driven Portability
- To move away from the league/season parameters in calibration, we implement generic `CompetitionProfile` and `CanonicalCompetitionScope` contracts.
- This framework can represent future football leagues, tennis tournaments, esports matches, or other sports/competitions through clean, declarative provider scope hints and completeness policies.
- Scanner-to-enrichment pipelines can be simulated by consuming a `ScannerEventCandidate` contract rather than triggering real-time scanners during acceptance runs.
