# J2A2 Tennis Chunk 1 Enrichment Prompt

## Execution Parameters
- **Role:** `bet-enricher`
- **Session ID:** `TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101`
- **Subagent Mode:** DELEGATED
- **Active Model:** Inherited from Parent (Active UI Runtime model)

## Input Scope
- **Chunk File:** `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/j2_chunk_tennis_1.json`
- **Upstream Source Artifact:** `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/scanner_event_universe.json`

## Target Outputs
- **Chunk Output:** `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/enricher_context_layer_tennis_1.json` (and `.md`)

## Hard Rules
- **No Final File Reading:** Never read `enricher_context_layer.json` as input.
- **Maximum 20 Events:** Process exactly the events listed in tennis chunk 1.
- **Strict Isolation:** Write only the dedicated chunk output, do not merge or finalize state yet.
