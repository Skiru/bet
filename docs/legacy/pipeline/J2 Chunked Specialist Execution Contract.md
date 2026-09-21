# J2 Chunked Specialist Execution Contract

This contract defines the execution strategy, file isolation, and quarantine procedures for Phase J2 (Enrichment & Statistical Evidence) of the sports betting pipeline.

## Core Rules

1. **Monolithic Run Prohibited:** Under no circumstances may Phase J2 be executed as a single, full 60-event monolithic specialist run.
2. **Mandatory Chunking:**
   - **J2A Enrichment Chunking:**
     - `J2A1` (Football): Max 20 events.
     - `J2A2` (Tennis Chunk 1): Max 20 events.
     - `J2A3` (Tennis Chunk 2): Max 20 events.
     - `J2A4` (Merge Enrichment): Consolidates J2A1, J2A2, J2A3.
   - **J2B Statistician Chunking:**
     - `J2B1` (Football): Max 20 events.
     - `J2B2` (Tennis Chunk 1): Max 20 events.
     - `J2B3` (Tennis Chunk 2): Max 20 events.
     - `J2B4` (Merge Statistics): Consolidates J2B1, J2B2, J2B3.
3. **State and Continuation (J2C):**
   - J2C is the final orchestration step that updates session state, omission ledger, manifest, and writes the J3 resume prompts. No specialist chunk execution is performed here.

## File Isolation and Naming

Chunk agents must never read stale final output files as input. Chunk outputs must use separate file names.

### Isolated Chunk Output Artifacts
- **Enrichment Chunks:**
  - `enricher_context_layer_football.json`/`.md`
  - `enricher_context_layer_tennis_1.json`/`.md`
  - `enricher_context_layer_tennis_2.json`/`.md`
- **Statistician Chunks:**
  - `statistician_market_analysis_football.json`/`.md`
  - `statistician_market_analysis_tennis_1.json`/`.md`
  - `statistician_market_analysis_tennis_2.json`/`.md`

### Consolidations (Merge Tasks)
The merge tasks `J2A4` and `J2B4` create the final consolidated files:
- `enricher_context_layer.json`/`.md`
- `statistician_market_analysis.json`/`.md`
- `deep_event_dossiers.json`/`.md`

## Stale Output Quarantine Protocol

Any existing blocked final output (e.g. from prior failed runs or errors) must be copied/quarantined to:
`reports/pipeline_runs/<SESSION_RUN_ID>/stale_blocked_outputs/`
before any new final outputs are written. Chunk and merge agents must explicitly ignore existing blocked files in their source paths and use only the newly generated chunks or the quarantined paths for debugging.
