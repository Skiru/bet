# J2 Chunked Specialist Execution Contract

This is the system-wide artifact certifying the J2 Chunked Specialist Execution Contract.

## Target Structure
- **J2A Enrichment Chunks (Max 20 events each):**
  - J2A1: Football chunk
  - J2A2: Tennis chunk 1
  - J2A3: Tennis chunk 2
  - J2A4: Consolidation & Merge
- **J2B Statistician Chunks (Max 20 events each):**
  - J2B1: Football chunk
  - J2B2: Tennis chunk 1
  - J2B3: Tennis chunk 2
  - J2B4: Consolidation & Merge
- **Orchestration (J2C):** Updates state, ledger, manifest and creates J3 resume prompts.

## Quarantine Policy
Before writing final consolidated output files, any stale blocked outputs in the run directory must be archived under `stale_blocked_outputs/` to avoid polluting the state context.
