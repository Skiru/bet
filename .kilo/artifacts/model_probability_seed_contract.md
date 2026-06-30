# Model Probability Seed Contract

## Required Probability Fields

`S3` must seed, and `S4` must preserve:

- `model_probability`
- `probability_method`
- `probability_sources`
- `probability_as_of`
- `probability_confidence`
- `probability_missing_reason`

## Allowed Behavior

- If a real model probability exists, keep it as `model_probability`.
- If no model probability can be produced, emit an exact `probability_missing_reason`.
- If a probability comes from `hit_rate_l10`, label it explicitly as `S3_HIT_RATE_PROXY`.
- If a probability source is bookmaker implied only, label it `BOOKMAKER_IMPLIED_REFERENCE_ONLY` and do not promote it to `model_probability`.

## Forbidden Behavior

- No fake model probability from odds alone.
- No fake fair odds or minimum acceptable odds when `model_probability` is missing.
- No use of `BOOKMAKER_IMPLIED_REFERENCE_ONLY` as a substitute model.

## Repair Implemented

- `scripts/deep_stats_report.py` now writes explicit `probability_*` fields into the canonical `S3` JSON.
- `scripts/odds_evaluator.py` now preserves `probability_*` into `S4` valuation rows and sets `probability_missing_reason` when `ev_missing_reason=MISSING_PROBABILITY` comes from absent upstream model data.
- `src/bet/pipeline/analytical_candidate_bridge.py` blocks analytical promotion whenever `model_probability` is absent.

## Replay Evidence

- Replay `S3`: `probability_missing_reason=NO_RANKED_MARKET` for all `8/8` candidates.
- Replay `S4`: `ev_missing_reason=MISSING_PROBABILITY` for all `8/8`; no fake EV or fair-odds path was created.
- Replay analytical handoff: `blocked_probability_missing=7`; the remaining `1` row is blocked on market-family identity, not fabricated probability.
