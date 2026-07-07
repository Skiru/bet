# Review Loop 6 — ProTipster

## Key Audit Points
- **Public Tip Cards Only:** BS4 parser extracts darmowe typy (event, league, time, sport, pick, odds) statically from public-only pages.
- **Affiliate and AKO Combo Rejection:** Checked and verified. All accumulators, coupons, and bookmaker bonus/clickout offers are successfully rejected (0 leaks).
- **PT Score Mapping:** Proprietary PT Score mapped solely to `source_quality` under `valuable_signals`.
- **Top Matches Integration:** Matches without explicit picks are successfully packaged as `ContextSignals` and excluded from `TipsterPicks`.
- **Outcome:** PASS.
