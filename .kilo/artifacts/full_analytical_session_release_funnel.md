# Full Analytical Session Release Funnel

## Funnel Counts

- `S1 raw discovery`: `89`
- `S1 market matrix`: `80`
- `S1 shortlist`: `29`
- `S3 stats ready`: `2`
- `S4 valuation candidates`: `29`
- `market probability input ready`: `0`
- `model probability ready`: `1`
- `S7 approved priced`: `0`
- `S7 analytical ready`: `0`
- `S8 analytical suggestions`: `0`

## Stage-by-Stage Trace

- Discovery -> matrix: `89 -> 80`
  - net reduction came from dedup + matrix validation, not from protected-path or provider blocks.
- Matrix -> shortlist: `80 -> 29`
  - shortlist kept the highest-ranked all-sport candidate universe for the day.
- Shortlist -> stats ready: `29 -> 2`
  - `27` candidates remained without contract-compliant stats evidence.
- Stats ready -> market probability input ready: `2 -> 0`
  - `29/29` candidates failed `MarketProbabilityInput` validation with `MARKET_SPECIFIC_INPUT_NOT_BUILT` because the valuation payload lacked a contract-safe market family/market line handoff.
- Valuation -> model probability ready: `29 -> 1`
  - only one candidate carried a raw model probability into `S4`, and it was not promotion-safe.
- Handoff -> analytical ready: `29 -> 0`
  - `11` blocked for `NO_STATS_DATA_FOR_MODEL_PROBABILITY`
  - `18` blocked for `MISSING_MARKET_FAMILY`
- Pre-S7 universe -> valid priced/analytical candidates: `29 -> 0`
  - `28` rejected as `REJECTED_MISSING_MARKET`
  - `1` rejected as `REJECTED_MISSING_TIMESTAMP`

## Readiness Flags

- `ready_for_manual_operator_quote_review`: `false`
- `ready_for_manual_placement`: `false`
- `ready_for_production_execution`: `false`
- `ready_for_automated_bet_placement`: `false`

## Release Interpretation

- The repaired probability path now fails closed instead of manufacturing an analytical-ready suggestion from incomplete market semantics or missing stats.
- The release blocker is current live input completeness, not a verified code-level probability bug.
