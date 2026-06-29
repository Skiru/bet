# Manual Quote Decision Contract

This contract defines the logic and output format of the final safety decision evaluating an entered manual operator quote against an unpriced candidate's bounds.

## Contract Schema

* **candidate_id** (string): Unique identifier matching the unpriced candidate.
* **min_acceptable_operator_odds** (float): Minimum acceptable decimal odds required.
* **actual_operator_odds** (float): Combined odds entered from the bookmaker operator screen.
* **actual_operator_line** (string): Verified operator line setting.
* **decision** (string): `BETTABLE_MANUAL_ONLY` | `REJECTED_BY_PRICE` | `LINE_MISMATCH_REQUIRES_REMODEL` | `NO_OPERATOR_MARKET_FOUND`.
* **reason** (string): Human-readable explanation of the final decision and threshold comparison.
