# Market Semantics Handoff Contract

## Contract

`MarketSemantics` must be available on every supported market row carried from market matrix to shortlist, S4 valuation, market probability input, analytical bridge, and pre-S7 validation.

Required fields:

- `market_family`
- `market_type`
- `market_label`
- `outcome_name`
- `selection`
- `direction`
- `line`
- `point`
- `provider_market_key`
- `bookmaker`
- `source_artifact_path`
- `confidence`
- `mapping_source`
- `mapping_status`

## Supported Mapping Rules

- `h2h`, `match winner`, `moneyline`, `ml` -> `RESULT`
- `totals`, `over_under`, `total goals`, `goals total` -> `GOALS_TOTALS`
- `corners`, `total corners` -> `CORNERS`
- `cards`, `bookings`, `yellow cards` -> `CARDS`
- `shots`, `total shots` -> `SHOTS`
- `shots on target`, `sot` -> `SHOTS_ON_TARGET`

## Unsupported Or Blocked Mapping Rules

- player props, including `player_tackles`, `player_passes`, and unstable player-specific lines -> `UNSUPPORTED_PROP_MATCH`
- ambiguous labels with no safe family inference -> `AMBIGUOUS_MARKET_LABEL`
- O/U-style families without a numeric line -> `LINE_MISSING`
- O/U-style families without explicit direction -> `DIRECTION_MISSING`

## Runtime Rules

- Market matrix must emit market semantics whenever they are explicitly derivable from provider market key, label, outcome, direction, and point/line.
- Shortlist must preserve emitted market semantics without dropping fields.
- S4 valuation must preserve explicit semantics and may backfill from shortlist only when the shortlist match is exact and contract-safe.
- Analytical bridge must read S4 semantics first and use upstream artifacts only as fallback.
- When semantics are missing or blocked, the emitted error must include both `source_artifact_path` and the exact field path.
- Raw or low-confidence reference probabilities must not count as `MODEL_PROBABILITY_READY`.
- `MODEL_PROBABILITY_READY_COUNT` must not exceed `MARKET_PROBABILITY_INPUT_READY_COUNT` unless separately reported as non-promotion-safe reference-only probability.

## Safe Backfill Order

1. S4 top-level market semantics
2. S4 `best_market`
3. S3 `best_market`
4. shortlist `odds_markets[]` exact odds match only

## Fail-Closed Expectations

- No fake market family
- No fake line
- No fake direction
- No bookmaker implied probability promoted as model probability
- No unsupported player props promoted into analytical-ready candidates
