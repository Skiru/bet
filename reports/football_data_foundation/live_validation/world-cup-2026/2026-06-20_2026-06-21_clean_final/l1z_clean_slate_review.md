# Clean-Slate Review and Rejection of Old Live Validation Loop

- **Phase ID:** `FOOTBALL_DATA_FOUNDATION_L1Z_FINAL_CLEAN_LIVE_VALIDATION_AND_LIVE_FRESHNESS_HARDENING`
- **Accepted Foundation Baseline SHA:** `79d378fa8dc932ffed6c27c1050c662e0dc7d848`

## Rejection Verdict

The old live-validation repair loop is rejected as unreliable and must not be
used as acceptance evidence. This rejection extends to the following items:

1. **Rejected Commits:**
   - `3a22dc7` (run live scanner window enrichment validation)
   - `7061f91` (correct live validation wrapper and artifacts)
   - `4960d2a` (fix live validation raw integrity and verdict logic)
   - `fd6c900` (repair live validation raw proof and verdict gates)
   - `841926e` (adjudicate live validation public raw source of truth)
   - `a4cc8e2` (update raw audit reports with post-push end_sha metrics)

2. **Rejected Evidence Directories:**
   - `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21`
   - `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21_clean`

## Clean Acceptance Proof

The new clean evidence directory:
`reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21_clean_final`
is the only source of acceptance evidence for this run.
Final acceptance requires pushed `END_SHA` public raw proof only.
