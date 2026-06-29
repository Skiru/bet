# Unpriced Bet Builder Candidate Contract

This contract defines the structure and mandatory fields for candidates generated without initial provider pricing, enabling them to be processed as first-class analytical suggestions.

## Contract Schema

* **candidate_id** (string): Unique identifier for the candidate.
* **event_id** (string): Unique identifier for the fixture event.
* **sport** (string): Canonical sport name (e.g. `football`).
* **competition** (string): League or competition name.
* **participants** (list of strings): List of participating teams or players.
* **market_family** (string): Market category (e.g. `bet_builder`).
* **bet_builder_legs** (list of dicts): Individual leg definitions, each containing market, pick, and details.
* **preferred_lines** (list of floats): Preferred line settings for relevant legs.
* **alternative_lines** (list of lists/floats): Optional alternative lines for safety review.
* **model_probability** (float): Calculated model probability (0.0 to 1.0).
* **fair_odds** (float): `1 / model_probability`.
* **min_acceptable_operator_odds** (float): `fair_odds * safety_margin_multiplier`.
* **confidence_label** (string): `HIGH` | `MEDIUM` | `LOW`.
* **evidence_pack** (list of dicts): Supporting statistical points and form trends.
* **counter_evidence** (list of dicts): Adversarial counter-arguments and risks.
* **source_gaps** (list of dicts): Discovered dataset or source coverage gaps.
* **correlation_risk** (string): `LOW` | `MEDIUM` | `HIGH` | `UNKNOWN`.
* **scenario_summary** (string): Brief logical flow of the combined Bet Builder scenario.
* **operator_market_required** (boolean): Must be `true`.
* **operator_quote_required** (boolean): Must be `true`.
* **operator_line_required** (boolean): Must be `true`.
* **operator_timestamp_required** (boolean): Must be `true`.
* **status** (string): Must be set to `PRICE_PENDING_OPERATOR_CHECK`.
