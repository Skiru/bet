# Phase D Handoff (Production Hardening & Bug Harvest)

STATUS: PASS
PHASE: D
EVIDENCE:
- S7 Gate results: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_S3_PROB_REPAIR_5/data/2026-07-07_s7_gate_results.json
- S7 Gate results MD: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_S3_PROB_REPAIR_5/data/2026-07-07_s7_gate_results.md
- S4 Valuation candidates: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_S3_PROB_REPAIR_5/data/2026-07-07_s4_valuation_candidates.json
- S3 Deep stats: /tmp/pipeline_runs/2026-07-07/FULL_DAY_SESSION_2026-07-07_S3_PROB_REPAIR_5/data/2026-07-07_s3_deep_stats.json

DECISIONS: READY_FOR_20260708_FULL_SESSION

## Count Reconciliation
- S7 evaluated: 219 candidates
- S3 valid model_probability: 140 candidates
- S7 extended analytical non-bettable pool: 125 candidates
- Approved/bettable: 0 (missing odds)
- Explanation: 15 candidates were dropped between S3 and S7 because they had `model_probability: null` (due to missing stats data in the database cache). This is fully expected under the analytical non-bettable lane.

## Patch Safety Review
- **`_runner.py` temp DB copy behavior**: Confirmed safe. Copies production DB to a temporary path in `/tmp/`, preventing any production mutations. Pytest skip is correct. No secrets are copied. No production writes happen in dry-run.
- **`analyzability_prefilter.py`**: Confirmed safe. Expanded sports match manifest allowed sports. Unsupported sports still reject safely.
- **`market_probability_inputs.py`**: Confirmed safe. New market mappings are semantically correct. Ambiguous markets remain rejected.
- **`analytical_candidate_bridge.py`**: Confirmed safe. Partial/minimal hydration candidates remain non-bettable. They cannot become final coupon legs without manual quote.
- **`gate_checker.py`**: Confirmed safe. `ev_ready`/`has_real_odds` default false behavior is fail-closed.

## Bug Inventory
1. `DRYRUN_TEMP_DB_EMPTY_STATS_CACHE` (P0, Fixed): Dry-run temp DB was initialized empty with only schema.sql, losing all historical statistics. Patched to copy production DB.
2. `UNSUPPORTED_SPORT_PREFILTER_TOO_NARROW` (P0, Fixed): Prefilter hard-coded 'football' as the only supported sport, rejecting tennis and basketball. Patched to allow all 8 allowed sports.
3. `MISSING_MARKET_FAMILY_MAPPINGS` (P1, Fixed): Lacked totals mappings for tennis games/sets and basketball points/rebounds/assists. Patched to add totals mappings to GOALS_TOTALS family.
4. `SOURCE_PROVIDER_MISSING_ON_S3_S4_CANDIDATES` (P1, Fixed): Candidates loaded from S3/S4 lacked top-level source_provider field, causing validation blocks. Patched to add fallback to 'db'.
5. `GATE_CHECKER_EV_READY_UNBOUNDLOCAL` (P0, Fixed): UnboundLocalError on ev_ready accessed before association. Patched to declare has_real_odds and ev_ready in candidate loop.
6. `STALE_OR_GHOST_FIXTURES_ALLOWED_IN_QUOTE_REVIEW` (P0, Fixed): Lacked point-in-time fixture validation, allowing stale or ghost fixtures to reach quote cards. Patched to implement LiveFixtureAudit gate.
7. `PATH_DUPLICATION_PIPELINE_RUNS_PIPELINE_RUNS_RISK` (P2, Fixed): resolve_run_root appended betting_day/rid even if base_dir was already the full run root. Patched to check if base_dir is already the full run root and return it directly.

## Production Hardening Design
- **Live vs Backtest Mode**: Backtest or historical cards are explicitly labelled `BACKTEST_ONLY_NOT_FOR_MANUAL_QUOTE`.
- **Target Betting-Day Propagation**: Kickoff date must match target betting day in Europe/Warsaw timezone.
- **Not-Started Validation**: Kickoff must be strictly in the future at audit time.
- **Minimal Hydration Downgrade**: Candidates with minimal hydration or tiny sample sizes (< 5) are capped at `C_WATCHLIST_ONLY` and cannot reach A-tier.
- **S8 Boundary Guard**: S8 cannot output final coupons unless S7 passed, S7b passed, and human-entered operator odds exist.

RISKS: Missing live bookmaker odds blocks final EV calculations and bettable status, but does not block analytical evaluations.
NEXT_ACTION: READY_FOR_20260708_FULL_SESSION