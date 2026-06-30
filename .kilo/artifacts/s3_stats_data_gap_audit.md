# S3 Stats Data Gap Audit

## Verified Findings

- Input shortlist used by the smoke: `/private/tmp/analytical_candidate_bridge_replay_b/data/2026-06-29_s2_shortlist.json`
- All selected football rows had live odds but `n_safety_markets=0`.
- No `stats_cache/football/*.json` files were present in the replay sandbox or repo-local runtime path.
- Replay `S3` log showed repeated DB misses such as:
  - `Team not found: Brazil`
  - `Team not found: Germany`
  - `Team not found: Melgar`
  - `Team not found: Kazma`
- Replay `S3` result: `total_candidates=8`, `candidates_with_data=0`, `fixture_ids_injected=8`.

## Root Cause Assessment

- Verified real data gap: the selected same-day football fixtures lacked DB-resolved team-form rows and lacked shortlist safety-market fallback.
- Not a fake block and not an odds-discovery issue.
- Small verified bug repaired separately: `S5` input resolution previously matched `candidate` in the run-root directory name and could fall back to `S3` instead of the real `S4` valuation artifact.

## Repairs Applied

- `S3` now emits `stats_gap_reason=NO_STATS_DATA_FROM_CACHE_OR_DB_AND_NO_SHORTLIST_SAFETY_MARKETS` when that exact condition occurs.
- `S3` also preserves `candidate_id`, `participants`, and `probability_*` fields so downstream steps can distinguish data absence from propagation failure.
- No fake stats were inserted.

## Verdict

- `S3_STATS_GAP_VERDICT=EXPLICITLY_BLOCKED`
- The bridge repair is production-safe because it converts the real `0/8` stats outcome into a traceable research gap rather than fabricating evidence.
