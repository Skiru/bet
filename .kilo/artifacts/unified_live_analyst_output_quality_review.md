# Targeted Code Review — Unified Live Analyst Output Quality

This review assesses the quality and wiring of the default live/manual session analyst package in the current codebase.

## Answers to Review Questions

1. **Why did the run produce 115 recommendations and 1133 watchlist ideas?**
   - Every discovered event without a specific market is assigned 1 or 2 default market check ideas (e.g. `CORNERS`, `TOTAL_GAMES`).
   - If there is any basic hint in flat text (hint score >= 2), the idea bypasses the watchlist classification and becomes a main recommendation (`BET_BUILDER_LEG`).
   - With 179 total selected matches, this generated 115 recommendations and 1133 watchlist ideas, with no limits or cap applied to the output.

2. **Are recommendations ranked by usefulness, data quality, confidence and market actionability?**
   - No, currently they are not ranked or sorted in the builder or runner. They appear in the order of candidate loading.

3. **Are watchlist-only ideas separated from the main package?**
   - In JSON, they are in `watchlist_only`. However, in the Markdown render, they are printed in full, which creates a huge, noisy document containing 1133 items.

4. **Can runner accidentally use a stale run directory?**
   - Yes, if no `--input` or `--from-run-id` is specified, the runner automatically scans `reports/pipeline_runs` and picks the lexicographically latest directory, which might be stale or unrelated.

5. **Is any old hardcoded run id still used as fallback?**
   - Yes, in `scripts/pipeline_steps/s8_build_coupons.py`, `TODAY_LIVE_BET_BUILDER_FINAL_MANUAL_COUPON_A_20260630_115254` is hardcoded as a fallback run ID if no run ID is provided.

6. **Does S8 fail if unified runner subprocess fails?**
   - No, `s8_build_coupons.py` launches `run_unified_live_analyst_session.py` as a subprocess but does not check its `returncode` or handle failures, which could allow a failed run to proceed silently.

7. **Are default reference lines clearly marked as operator-check-only?**
   - They use `DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK`, but the Markdown report fails to explicitly tell the operator that these are check-only fallback values.

8. **Can a low-evidence idea become a recommendation instead of watchlist?**
   - Yes, if there is a minor keyword match (`hint_score` >= 2), a candidate with zero actual evidence items is promoted to a main recommendation instead of remaining on the watchlist.

9. **Are tennis/Wimbledon and football/World Cup represented without overwhelming output?**
   - No, because of the lack of ranking and output caps, the entire list of 179 matches is dumped, creating overwhelming noise.

10. **Are final coupon and quote safety still intact?**
    - Yes, the validation code correctly blocks final coupon generation or automated placement unless a human-entered Superbet quote is provided.

## Classifications

| File / Component | Issue Classification | Description / Impact |
| --- | --- | --- |
| `scripts/pipeline_steps/s8_build_coupons.py` | `P0_RUNTIME_WIRING_BUG` | Silently ignores subprocess failures from the live analyst runner, and uses hardcoded old fallback run ID. |
| `scripts/run_unified_live_analyst_session.py` | `P0_STALE_RUN_SELECTION_BUG` | Silently falls back to sorting run dirs lexicographically and picking the last one, risking stale selection. |
| `src/bet/pipeline/unified_live_analyst_session.py` | `P1_OUTPUT_TOO_BROAD` | Promotes way too many low-evidence ideas to main recommendations without ranking or capping. |
| `src/bet/pipeline/unified_live_analyst_session.py` | `P1_WATCHLIST_NOISE` | Watchlist printed in full in Markdown instead of being capped to a concise appendix. |
| `src/bet/pipeline/unified_live_analyst_session.py` | `P1_REFERENCE_LINE_LABELING_GAP` | Default reference lines are not clearly marked as manual-check operator-check-only in Markdown. |
| `scripts/pipeline_steps/s8_build_coupons.py` | `P1_SUBPROCESS_RETURN_CODE_GAP` | Subprocess return code is ignored. |
| `src/bet/pipeline/unified_live_analyst_session.py` | `P2_MARKDOWN_USABILITY` | Markdown package does not follow executive summary layout with top recommendations and clean categories. |
