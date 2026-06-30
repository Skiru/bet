# Deep Discovery Audit Report — TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A
Date: 2026-06-28

## 1. Exact Orchestration Command
The failed session was executed with the following orchestrator command:
```fish
env BET_PIPELINE_RUNTIME_MODE=LIVE_SHADOW \
  python3 scripts/pipeline_steps/run_daily_pipeline.py \
  --date 2026-06-28 \
  --run-id TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A \
  --runtime-mode LIVE_SHADOW \
  --allow-live-network \
  --allow-write
```

## 2. Step-by-Step Candidate Drop-Off and Diagnostics

| Step ID | Phase Name | Output Artifact Name | Candidate/Fixture Count | Key Observations & Diagnostics |
|---------|------------|----------------------|-------------------------|--------------------------------|
| **S1**  | Discover | `S1.json` (market matrix) | 2 fixtures | **CRITICAL FAILURE:** `discover_events.py` crashed during DB migration (`OperationalError: no such column: logical_identity`). The system silently degraded to database fallback and loaded only 2 static database fixtures. |
| **S1e** | Events | `discovered_events` | 2 candidates | Silent propagation of the 2 fallback database fixtures without checking for discovery breadth. |
| **S2**  | Tipsters | `2026-06-28_s2_shortlist.json` | 2 candidates | Both fallback candidates were included because of the "NO AUTO-REJECTION: ALL events are scored and included" policy. Tipster consensus returned 0 active tipster matches. |
| **S3**  | Stats | `2026-06-28_s3_deep_stats.json` | 2 candidates | Stats cache lookup was minimal/blind. H2H meetings = 0 (BLIND), data quality score = 0 (MINIMAL) for Algeria/Austria; Jordan/Argentina had no stats. |
| **S4**  | Valuator | `2026-06-28_s4_valuation_candidates.json`| 2 candidates | Valuation candidates generated without actual live odds (contains_odds = false, 1 estimated EV entry). |
| **S6**  | Repeats | `repeat_loss_handoff_2026-06-28.json` | 2 candidates | Handed off to S7. |
| **S7**  | Gate | `2026-06-28_s7_gate_results.json` | 2 inputs, 0 approved | **BLOCKED:** Both candidates were rejected at the Hard Approval Gate due to numerous failing programmatic checks (e.g. no H2H meetings, no injury data, no tipsters, and estimated odds/stats-first mode). |

## 3. Specific Quality & Completeness Violations

- **Stale Kickoff Events:** Yes, both events had a kickoff time of `02:00:00Z`, but the run started at `12:44:48Z` (approximately 10 hours and 44 minutes after kickoff). This stale kickoff data was silently propagated to S7.
- **Empty Sport/Competition:** Yes, the competition name was an empty string `""` for both events. Empty sport/competition name checks did not filter these out.
- **Missing H2H/Injury/Tipster Data:** Both events lacked active tipster arguments, H2H historical matches (BLIND), and injury/suspension details. This did not trigger any retry or block in S1-S6 and was silently passed to S7.
- **Provider Universe Exhaustion:** Not exhausted. The upstream scraper/discovery step simply crashed and fell back to static DB entries.

## 4. Root Cause Summary
The session ended in `NO_BET` because of an upstream failure chain rather than S7 thresholds being too high. A database migration error caused the raw discovery script `discover_events.py` to fail, which led to a silent fallback to two completed, competition-less database fixtures. The lack of a freshness filter, empty competition gate, source-gap retry, or candidate sufficiency check allowed these stale, empty candidates to reach S7, resulting in a false "NO_BET_SESSION_VALID" instead of an explicit "BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE" blocker.
