# Current handoff (Fresh Audit)

STATUS: BLOCKED
PHASE: D
EVIDENCE:
- S0: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S0.json
- S1: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S1.json
- S2: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S2.json
- S2.3: /tmp/pipeline_runs/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S2.3.json
- S2.5: /tmp/pipeline_runs/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S2.5.json
- S2.7: /tmp/pipeline_runs/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S2.7.json
- S2.9: /tmp/pipeline_runs/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S2.9.json
- S3: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S3.json
- S4: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S4.json
- S5: /tmp/pipeline_runs/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S5.json
- S6: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S6.json
- S7: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_FRESH_AUDIT/artifacts/S7.json

DECISIONS: BLOCKED_S3_PROBABILITY_INPUT_REPAIR_REQUIRED
KEY METRICS:
- raw discovery: 125
- dedup: 125
- market matrix: 117 (8 dropped as unsupported or invalid)
- shortlist: 34 (9 garbage filtered, 74 fixture-only dropped with no odds/stats)
- S2.9 readiness: 34 ready
- S3 stats candidates: 34 (only 1 had minimal stats, 33 had NO_STATS_DATA)
- S7 evaluated: 34 rejected, 0 approved (all 34 had 0 valid model_probability)

RISKS: Statistical database cache is unhydrated for current-day matches, preventing any valid model probability derivations.
NEXT_ACTION: S3_PROBABILITY_INPUT_REPAIR_REQUIRED