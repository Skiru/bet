# J2A1 Football Enrichment Prompt

## Execution Parameters
- **Role:** `bet-enricher`
- **Session ID:** `TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101`
- **Subagent Mode:** DELEGATED
- **Active Model:** Inherited from Parent (Active UI Runtime model)

## Input Scope
- **Chunk File:** `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/j2_chunk_football.json`
- **Upstream Source Artifact:** `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/scanner_event_universe.json`

## Target Outputs
- **Chunk Output:** `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/enricher_context_layer_football.json` (and `.md`)

## Hard Rules
- **No Final File Reading:** Never read `enricher_context_layer.json` as input.
- **Maximum 20 Events:** Process exactly the events listed in the football chunk.
- **Strict Isolation:** Write only the dedicated chunk output, do not merge or finalize state yet.
