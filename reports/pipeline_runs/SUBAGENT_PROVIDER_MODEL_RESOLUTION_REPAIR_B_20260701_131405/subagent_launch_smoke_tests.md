# Subagent Launch Smoke Tests

## Required Smokes

- `bet-enricher`: `FAIL` (`ProviderModelNotFoundError`)
- `bet-statistician`: `FAIL` (`ProviderModelNotFoundError`)

## Additional Smoke

- `bet-valuator`: `FAIL` (`ProviderModelNotFoundError`)

## Deferred After Shared Failure

- `bet-challenger`: `SKIPPED`
- `bet-builder`: `SKIPPED`
- `bet-test-engineer`: `SKIPPED`

## Verdict

- `STATUS=BLOCKED_PROVIDER_MODEL_RESOLUTION_NOT_FIXED`
- No smoke artifact could be written by the failing subagents because launch never completed.
