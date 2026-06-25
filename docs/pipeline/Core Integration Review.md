# Core Integration Review

- Scope: non-enrichment pipeline from S1 discovery through S8 coupon construction.
- Inventory source of truth: `src/bet/pipeline/core_integration_inventory.py`.
- Contract source of truth: `src/bet/pipeline/core_integration_contracts.py` plus `src/bet/pipeline/tipster_sources.py`.
- Runtime safety: live integrations are allowed only in runtime-managed `LIVE_SHADOW` or `PRODUCTION` executions with `BET_PIPELINE_LIVE_ACK` present.
- S7b output is a market-availability artifact, not a coupon artifact.
- S8 requires PASS script evidence for `S7` and `S7b` before writing coupon artifacts when runtime-managed paths are active.
