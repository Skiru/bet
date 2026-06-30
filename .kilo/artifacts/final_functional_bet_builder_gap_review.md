# Final Functional Bet Builder Gap Review

TASK_ID=ARTIFACT_HYGIENE_AND_FINAL_FUNCTIONAL_GATE_RETRY_A

## Retry Result

- handoff artifact: `reports/pipeline_runs/2026-06-30/ARTIFACT_HYGIENE_AND_FINAL_FUNCTIONAL_GATE_RETRY_A/data/2026-06-29_s4_valuation_candidates_analytical_candidate_handoff_smoke_replay.json`
- runtime prefilter report: `reports/pipeline_runs/2026-06-30/ARTIFACT_HYGIENE_AND_FINAL_FUNCTIONAL_GATE_RETRY_A/artifacts/analyzability_prefilter_report.json`
- package type: `RESEARCH_GAP_PACKAGE`
- analytical suggestions: `0`
- hydrated candidates: `0`
- partial hydration candidates: `0`
- minimal hydration candidates: `29`
- analyzable candidates: `0`

## Evidence

- source valuation slate size: `29`
- source valuation sports mix: `football=10`, `basketball=9`, `tennis=8`, `volleyball=1`, `cs2=1`
- source valuation candidates missing `model_probability`: `28/29`
- source valuation probability methods: `NONE=28`, `S3_PROBABILITY_ENGINE=1`
- football analyzability statuses: `UNSUPPORTED_MARKET_FAMILY=8`, `RESEARCH_GAP_L10_MISSING=2`
- football blocker reasons: `MARKET_SPECIFIC_INPUT_NOT_BUILT=8`, `L10_SERIES_MISSING=2`

## Why This Is Data Coverage, Not Code

- The retry completed and emitted both the analytical handoff artifact and the runtime analyzability report at isolated run-scoped paths.
- Required regression passed: `230 passed` across the requested targeted suite.
- Full repository regression passed: `2269 passed, 97 skipped`.
- The football subset failed because no candidate reached `HYDRATED`, and no candidate carried contract-compliant market-specific inputs plus model probability.
- Two football candidates reached result-market semantics but still failed with `NO_STATS_DATA_FOR_MODEL_PROBABILITY` and `L10_SERIES_MISSING`.
- Eight football candidates failed earlier with `MARKET_SPECIFIC_INPUT_NOT_BUILT`, meaning the source slate still lacks analyzable market-shape data for those fixtures.

## Final Gap Verdict

The artifact hygiene blocker is fixed. The remaining blocker is live data coverage for football analytical candidate hydration and model-probability support, not a runtime overwrite bug.
