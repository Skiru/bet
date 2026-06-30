# Manual Superbet Operator Quote Contract

This contract defines the structure and fields required for entering a manual quote from the Superbet operator screen.

## Contract Schema

* **candidate_id** (string): Unique identifier matching the unpriced candidate.
* **operator** (string): Must be `Superbet`.
* **market_label** (string): Label of the market on the operator screen.
* **line** (string): Line value on the operator screen (e.g. `2.5`, `4.5`).
* **odds_decimal** (float): Checked decimal odds for the individual leg or single outcome.
* **combined_odds_decimal** (float): Combined decimal odds for the entire multi-leg Bet Builder, as shown on the operator screen.
* **as_of_utc** (string): ISO-8601 UTC timestamp of the quote entry.
* **entered_by_human** (boolean): Must be `true`.
* **computed_by_pipeline** (boolean): Must be `false`.
* **screenshot_reference_optional** (string): Optional path/URL to screenshot evidence of the operator quote.
* **quote_status** (string): `QUOTE_ENTERED` | `QUOTE_MISSING` | `LINE_MISMATCH` | `MARKET_NOT_FOUND`.
