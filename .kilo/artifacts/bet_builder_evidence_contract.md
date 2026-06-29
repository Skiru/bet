# Sport-Specific Bet Builder Evidence Contract

## 1. Overview
Production-grade sports betting analytics requires that all combined markets in a Bet Builder be supported by structured, verifiable point-in-time evidence. The pipeline prevents placing bets or claiming model edge unless the data contract requirements are fully satisfied.

---

## 2. Market Families & Evidence Requirements

### 2.1 Goals / Totals
* **Required Evidence Fields**: 
  - `team_goals_scored_avg_l10` (Decimal)
  - `team_goals_conceded_avg_l10` (Decimal)
  - `opponent_goals_scored_avg_l10` (Decimal)
  - `opponent_goals_conceded_avg_l10` (Decimal)
* **Counter-Evidence Fields**: `low_tempo_risk` (Boolean), `early_lead_risk` (Boolean), `rotation_risk` (Boolean).
* **Source count**: Minimum 2 sources.
* **Gaps**: Missing L10 averages is fatal.

### 2.2 Corners
* **Required Evidence Fields**: 
  - `team_corners_for_avg_l10` (Decimal)
  - `team_corners_against_avg_l10` (Decimal)
  - `opponent_corners_for_avg_l10` (Decimal)
  - `opponent_corners_against_avg_l10` (Decimal)
  - `tactical_pressure_proxy` (String)
  - `match_script_assumption` (String)
  - `line_under_review` (Decimal)
* **Counter-Evidence Fields**: `low_tempo` (Boolean), `early_lead_risk` (Boolean), `rotation` (Boolean), `weather` (String), `referee` (String).
* **Source count**: Minimum 2 sources or explicit gap documented.
* **Gaps**: Missing L10 corners, tactical pressure proxy, or match script assumption is fatal.

### 2.3 Cards
* **Required Evidence Fields**: 
  - `team_cards_avg_l10` (Decimal)
  - `opponent_cards_avg_l10` (Decimal)
  - `referee_cards_avg_season` (Decimal)
* **Counter-Evidence**: Lenient referee assignment or friendly match context.
* **Gaps**: Missing referee stats is fatal.

### 2.4 Shots / Shots on Target
* **Required Evidence Fields**: 
  - `team_shots_on_target_avg_l10` (Decimal)
  - `opponent_shots_on_target_avg_l10` (Decimal)
* **Counter-Evidence**: Heavy defensive low-block setup.
* **Gaps**: Missing shots-on-target averages is fatal.

### 2.5 Player Props
* **Required Evidence Fields**: 
  - `player_prop_avg_l10` (Decimal)
  - `player_minutes_avg_l5` (Decimal)
* **Counter-Evidence**: Rotation threat, returning from long injury limit.
* **Gaps**: Player not in predicted starting lineup is fatal.

### 2.6 Team Result / Double Chance
* **Required Evidence Fields**: `team_win_rate_l10` (Decimal), `opponent_loss_rate_l10` (Decimal).
* **Gaps**: H2H depth sparse/blind is fatal.

### 2.7 Same-Team Pressure Scenario
* **Required Evidence Fields**: `must_win_motivation` (Boolean), `attack_tilt_expected` (Boolean).
* **Gaps**: Standings position context missing is fatal.

### 2.8 Underdog Pressure Scenario
* **Required Evidence Fields**: `low_block_defense_stats` (String), `tactical_foul_rate_l10` (Decimal).
* **Gaps**: Defensive averages missing is fatal.

### 2.9 Referee / Cards Scenario
* **Required Evidence Fields**: `referee_yellow_cards_avg` (Decimal), `referee_red_cards_count` (Integer).
* **Gaps**: Unknown/missing referee assignment is fatal.

### 2.10 Game-State Scenario
* **Required Evidence Fields**: `lead_preservation_pattern` (String), `draw_propensity` (Decimal).
* **Gaps**: Historical game-state average missing is fatal.

---

## 3. Approved Sources
All stats must be cross-verified across at least 2 independent allowed source types:
- `api-football`
- `whoscored`
- `fbref`
- `understat`
- `sofascore`
- `betclic`
- `superbet`
- `consensus_model`

---

## 4. Freshness & `as_of` Rules
Every evidence field must be timestamped with an `as_of` ISO 8601 string. The maximum age of stats is 24 hours relative to kickoff. Gaps must be explicitly flagged rather than hidden.
