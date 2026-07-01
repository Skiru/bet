# J2A4 Consolidation and Merge Enrichment Prompt

## Execution Parameters
- **Role:** `bet-orchestrator`
- **Session ID:** `TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101`
- **Subagent Mode:** DELEGATED (Merge Execution)

## Input Scope
- **Upstream Chunks:**
  - `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/enricher_context_layer_football.json`
  - `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/enricher_context_layer_tennis_1.json`
  - `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/enricher_context_layer_tennis_2.json`
- **Quarantined Stale Data:** `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/stale_blocked_outputs/` (Only for debugging or comparison, never read as active state input)

## Target Outputs
- **Final Merged Artifacts:**
  - `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/enricher_context_layer.json`
  - `reports/pipeline_runs/TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101/enricher_context_layer.md`

## Hard Rules
- **Fresh Overwrite:** Overwrite any remaining files or ensure they are moved/archived to the stale outputs quarantine folder first.
- **Strict Merging:** Produce a fully complete and unified analytical context layer.
