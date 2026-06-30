# Bet Builder Correlation Model Contract

## 1. Overview
Bet Builders combine multiple events from the same match. This contract defines how the correlation of these selections must be programmatically evaluated, preventing simple leg-odds multiplication, logical contradictions, or un-modeled high-risk combinations.

---

## 2. Evaluation Fields

* `scenario_family`: (String) e.g., Same-Team Domination, Referee Cards, Co-dependent Player Props.
* `leg_count`: (Integer) Number of legs combined.
* `same_match`: (Boolean) Must be true for same-match Bet Builder.
* `same_team_dependency`: (String) Rationale of how same-team legs relate.
* `opposing_team_dependency`: (String) Rationale of co-dependence between teams.
* `game_state_dependency`: (String) How game state (e.g. early lead, tight draw) affects legs.
* `player_dependency`: (String) How player actions co-depend on overall match script.
* `market_family_overlap`: (Boolean) True if combining overlapping/related market types (e.g. Corners + Shots).
* `positive_correlation_reasons`: (List of String) Reasons why legs are positively correlated.
* `negative_correlation_reasons`: (List of String) Reasons why legs are negatively correlated.
* `conflicting_legs`: (List of String) Conflicting selections (e.g. Under 1.5 goals + Over 3.5 corners from dominant same team).
* `scenario_coherence_score`: (Decimal, range [0.0, 1.0]) Quantified coherence of the script.
* `correlation_risk`: `LOW` | `MEDIUM` | `HIGH` | `BLOCKED`.
* `correlation_verdict`: `PASS` | `REVIEW` | `FAIL`.

---

## 3. Strict Rules

### 3.1 Logical Contradictions
Any direct logical contradictions (e.g., Over on a market and Under on the same/overlapping market for the same team) must immediately result in `correlation_verdict = FAIL`.

### 3.2 High Correlation & Scenario Coherence
Combining player-specific props with team totals (e.g. Player A shots + match goals Over) represents `HIGH` correlation risk. These require a scenario coherence score of $\ge 0.80$ explaining their co-dependence to receive a `PASS`/`REVIEW` verdict; otherwise, they must `FAIL`.

### 3.3 No Odds Multiplication
No Bet Builder combined odds can be computed by multiplying individual leg odds together. Multiplication ignores co-dependence and is mathematically fraudulent for same-match events.

### 3.4 No Fabricated Bookmaker Odds
Do not invent or synthesize Bet Builder combined odds. Combined odds must be retrieved directly from the operator (Superbet) interface and timestamped.
