# Unified Live Analyst Flow Code Review

This document reviews the current default live/manual session flow and analyzes how we can implement one unified, odds-optional, hydration-optional statistical analyst recommendation flow.

## 1. Analysis of Current Failure Points

In the existing pipeline, live manual sessions frequently end with `DATA_COVERAGE_BLOCKED` or `NO_BET_PACKAGE` when minor data gaps exist. Active, high-profile events (e.g., Wimbledon, World Cup) are completely discarded from output summaries because the coupon-gate validation flow requires perfect data before generating any recommendations.

### 1.1 Classifications of System Components & Issues

#### Component: `src/bet/pipeline/analyzability_prefilter.py`
- **UNSUPPORTED_SPORT constraint**: Blocks any sport other than `football` from being `ANALYZABLE`. This is a severe limitation for multi-sport coverage like Wimbledon tennis.
  - *Classification*: **REMOVE_AS_DEFAULT_BLOCKER** / **LIVE_ANALYST_FLOW_BUG**
- **STATS_SEED_MISSING / L10_SERIES_MISSING**: Hard-blocks candidates if historical team form or sample sizes are not fully hydrated.
  - *Classification*: **HYDRATION_OPTIONAL_BUT_BLOCKING** / **DATA_GAP_SHOULD_LOWER_CONFIDENCE**
- **LINE_MISSING / DIRECTION_MISSING**: Hard-blocks candidate promotion if reference point or direction is absent.
  - *Classification*: **ODDS_OPTIONAL_BUT_BLOCKING** / **DATA_GAP_SHOULD_LOWER_CONFIDENCE**

#### Component: `src/bet/pipeline/market_probability_inputs.py`
- **Validation Contract (validate_market_probability_input)**: Enforces strict data completeness rules (needs fully `HYDRATED` status with L10 $\ge$ 5 matches, traceable metadata, valid `probability_confidence` & `probability_method`).
  - *Classification*: **FINAL_COUPON_SAFETY_KEEP** (Essential for EV/fair odds and actual bet placing, but must not prevent qualitative analyst suggestions).
  - *Classification*: **HYDRATION_OPTIONAL_BUT_BLOCKING** / **MODEL_PROBABILITY_OPTIONAL_BUT_BLOCKING**

#### Component: `src/bet/pipeline/analytical_candidate_bridge.py`
- **Bridge Lane Routing**: Sorts drafts into `analytical_ready` vs several `blocked_*` arrays. If a candidate has any hydration or model-probability gap, it gets moved to a blocked category, meaning it is never passed to downstream steps as an active suggestion.
  - *Classification*: **REMOVE_AS_DEFAULT_BLOCKER** / **ODDS_OPTIONAL_BUT_BLOCKING**

#### Component: `src/bet/pipeline/daily_manual_session.py`
- **Candidate Filtration Gate (`_quote_review_ready`)**: Strictly checks if candidates are `HYDRATED`, `ANALYZABLE`, and have a valid model probability. If not, they are ignored during manual session reviews, resulting in a blank or blocked ledger.
  - *Classification*: **HYDRATION_OPTIONAL_BUT_BLOCKING** / **MODEL_PROBABILITY_OPTIONAL_BUT_BLOCKING**

#### Component: `src/bet/pipeline/rich_coupon_package.py`
- **No-Bet Fallback**: If no perfect candidates are resolved, it defaults to a `NO_BET_PACKAGE` with empty suggestions.
  - *Classification*: **REMOVE_AS_DEFAULT_BLOCKER**

### 1.2 Unified Live/Manual Flow Solution Strategy

The new unified flow implements **one single path** that integrates both statistical analysis and manual coupon safety:
1. **Odds/Hydration/Model-Probability Optionality**: These fields are reference-only. If they are absent, we still generate an analyst recommendation or a watchlist-only idea, but lower the confidence and skip EV/fair-odds calculations.
2. **Confidence-Graded Ideas**:
   - High-quality, hydrated sources with balance of evidence $\rightarrow$ Recommendations (`BET_BUILDER_LEG` suggestions).
   - Weak or incomplete evidence $\rightarrow$ Watchlist-only ideas (`WATCHLIST_ONLY`).
3. **No Fake Data**: All predictions use authentic, verified context/evidence. No simulated odds or fake probabilities.
4. **Final Coupon Safe Gate**: Actual coupon placement or production-readiness *requires* human-entered Superbet quote validation. Without a verified quote, `ready_for_manual_placement` remains false.

## 2. Component Review Matrix

| Component File | Issue / Current Behavior | Target Behavior | Classification |
|---|---|---|---|
| `analyzability_prefilter.py` | Restricts sport to football, blocks on missing line/stats. | Retain as final-coupon safety, but do not block high-level analyst recommendations. | **FINAL_COUPON_SAFETY_KEEP** |
| `market_probability_inputs.py` | Requires full hydration (L10 $\ge$ 5). | Retain for model/EV math, but allow analyst recommendations to bypass for simple checklist views. | **FINAL_COUPON_SAFETY_KEEP** |
| `analytical_candidate_bridge.py` | Segregates drafts into blocked lists. | Allow candidates to bridge over as raw drafts for analyst evaluation. | **REMOVE_AS_DEFAULT_BLOCKER** |
| `rich_coupon_package.py` | Only processes perfect `BETTABLE_MANUAL_ONLY` or empty `NO_BET_PACKAGE`. | Use the new `UnifiedLiveAnalystPackage` as the default live output. | **REMOVE_AS_DEFAULT_BLOCKER** |
| `daily_manual_session.py` | Filters candidates strictly on `_quote_review_ready`. | Support the unified live analyst flow with confidence grading. | **REMOVE_AS_DEFAULT_BLOCKER** |
| `bet_builder_analytical.py` | Strict contracts for unpriced candidates. | Retain for quote-carrying final coupons, bypass for loose recommendations. | **FINAL_COUPON_SAFETY_KEEP** |
| `run_no_placement_smoke.py` | Uses old unpriced flow. | Uses new unified runner. | **LIVE_ANALYST_FLOW_BUG** |
| `pipeline_steps/s8_build_coupons.py` | Returns `BLOCK` when no fully hydrated candidates exist. | Emit loose analyst/watchlist coupons to allow manual reviews. | **REMOVE_AS_DEFAULT_BLOCKER** |
