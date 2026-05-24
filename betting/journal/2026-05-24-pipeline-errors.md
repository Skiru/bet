# Pipeline Errors — 2026-05-24

## ⛔ CRITICAL: S3 Deep Stats Fed Wrong Shortlist (3 vs 552 candidates)

### What happened
- `deep_stats_report.py` was called with `--shortlist betting/data/2026-05-24_esports_shortlist.json`
- This file had only 3 esports candidates
- The REAL shortlist `betting/data/2026-05-24_s2_shortlist.json` had 552 candidates
- Result: 549 events NEVER got deep statistical analysis
- Gate (S7) processed only 3 events → approved=0, extended=3, rejected=0
- The v4/v5 coupons had to be built manually from tipster+DB data, bypassing the broken pipeline

### Root cause
- Orchestrator passed wrong `--shortlist` argument (esports file instead of main shortlist)
- No validation existed to catch this catastrophic mismatch

### Impact
- Only 14 events reached the final coupon (should be 25-40+)
- Statistical edge for 549 events was never computed
- All pipeline steps S4-S7 operated on garbage input (3 events)

### Fix applied (3 defense layers)
1. **`deep_stats_report.py`**: Added MIN_CANDIDATES_SHORTLIST=10 check. If shortlist has <10 candidates, it looks for the real `{date}_s2_shortlist.json` and auto-corrects.
2. **`gate_checker.py`**: Added sanity warning when <10 candidates loaded. Prints alert with source info.
3. **`validate_phase.py`**: Added S3→S2 coverage check. If S3 analyzed <20% of shortlist, flags as CRITICAL with recovery command.

### Rule for future sessions
- ALWAYS check candidate count after deep_stats runs
- Expected: deep_stats should process ≥50% of shortlist (after dedup)
- If it processes <20%, something is catastrophically wrong → STOP and investigate
- The orchestrator MUST pass `--shortlist betting/data/{date}_s2_shortlist.json` (the MAIN shortlist)
