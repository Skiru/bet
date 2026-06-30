# Superbet Bet Builder Odds Architecture Guard Contract

This guard defines the architectural limits, data dependencies, and mandatory validations for Bet Builder integrations, specifically focusing on Superbet.

---

## 1. Core Architectural Mandates

### A. Provider Odds are Reference Input Only
- Odds sourced from standard REST API providers (such as OddsAPI.io or The Odds API) represent **priced single-market inputs** only. They serve as valuable sanity checks and reference values.
- Sourced provider odds are utilized to compute fair values, identify arbitrage/EV drift, and establish minimum acceptable odds.

### B. Lack of Provider Odds is Non-Blocking
- Sourcing single-market odds from standard providers is optional for candidate generation.
- **A lack of standard provider odds must never block deep analysis or prevent an analytical candidate from being processed** by the pipeline.

### C. Manual Operator Quote Required for BETTABLE Status
- To achieve a finalized **`BETTABLE`** status, a candidate **must have a manual operator quote** verified inside Superbet.
- Sponsoring/placing a bet without verifying actual operator-provided Bet Builder lines and prices is strictly prohibited.
- **A lack of a manual Superbet operator quote blocks `BETTABLE` status.**

---

## 2. Combined Odds Computation Rules

### A. Combined Odds are Manual/Operator-Screen-Only
- Combined odds for multi-outcome Bet Builders (e.g. Home Win + Under 2.5 goals + Home Over 4.5 corners) are computed exclusively by the bookmaker's proprietary risk models.
- These combined odds must be read manually off of the official Superbet operator screens/web app.

### B. Fair Odds and Min Acceptable Odds May be Computed
- The pipeline is fully authorized to compute its own **Fair Odds** (statistical fair probability) and **Minimum Acceptable Odds** (the price threshold below which a bet is no longer profitable).

### C. Never Fabricate Bookmaker Combined Odds
- **The pipeline must never calculate, combine, or fabricate bookmaker combined Bet Builder odds.**
- Standard compounding formulas (like simple multiplication of single odds, e.g., $1.8 \times 2.0 = 3.6$) are mathematically invalid for Bet Builders due to high multi-market correlation (e.g. team wins are correlated with team goals and corner counts).
- Any attempt to mathematically synthesize or estimate bookmaker Bet Builder prices is classified as a critical system hazard and must fail verification.
