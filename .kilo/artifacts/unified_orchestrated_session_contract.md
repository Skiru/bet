# Unified Orchestrated Session Contract - Production Schema

This document mirrors and defines the production schema and quality gate definitions for the live analyst session contract.

## Required Subagents and Order
1. `bet-scanner` (S1e Event Universe)
2. `bet-scout` (S2 Tipster/Opinion Layer)
3. `bet-enricher` (S2.3-S2.6 Enrichment Layer)
4. `bet-statistician` (S3-S5 Market-Stat Layer)
5. `bet-valuator` (S3-S5 Valuation-Reference Layer)
6. `bet-challenger` (S7 Challenger Layer)
7. `bet-builder` (S8-S10 Builder Package)
8. `bet-test-engineer` (Final Verification)

## Required Artifacts
The following artifacts must be successfully written to disk:
- `orchestrator_session_plan.md`
- `orchestrator_subagent_manifest.json`
- `model_routing_matrix.json`
- `active_model_runtime_proof.md`
- `scanner_event_universe.md` / `scanner_event_universe.json`
- `scout_tipster_opinion_layer.md` / `scout_tipster_opinion_layer.json`
- `enricher_context_layer.md` / `enricher_context_layer.json`
- `statistician_market_analysis.md` / `statistician_market_analysis.json`
- `valuator_reference_odds_layer.md` / `valuator_reference_odds_layer.json`
- `challenger_adversarial_review.md` / `challenger_adversarial_review.json`
- `builder_package.md` / `builder_package.json`
- `omission_ledger.md` / `omission_ledger.json`
- `package_quality_review.md`
- `status_safety_review.md`

## Quality Gates
- **Zero Valid Tips:** Blocks Phase C if tip count == 0.
- **No-Silent-Omission:** Every discovered event or sport must be OMITTED (with reason), WATCHLIST, or REJECTED if not recommended.
- **Human Quote Safety:** Coupon combined odds cannot be auto-generated; they require a human-entered Superbet operator quote.
- **Model Routing Gate:** All agents must run on Gemini 3.5 Flash Flex (`google-vertex/gemini-3.5-flash-flex-high`).
