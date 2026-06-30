# Football Stat Semantics Mapping

This document specifies the exact mapping, split policy, aggregation, and series derivation logic for all supported football market families.

---

## 1. Market Family Semantic Mapping Matrix

### 1.1 RESULT
* **Accepted Raw Stat Keys:** `goals`
* **Aggregation Policy:** Sum / Average comparison of home vs away team's goals.
* **`_home/_away` Split:** Yes (uses `goals_home` and `goals_away`).
* **Stat Type:** Count (when looking at a single match) or Average (across a series).
* **How L10 Series is Derived:** Synthesized from `l10_avg` of goals or derived from `l10_matches` if available.
* **Fatal Unknown Cases:** Missing opponent details or unresolvable team names.

### 1.2 GOALS_TOTALS
* **Accepted Raw Stat Keys:** `goals`
* **Aggregation Policy:** Sum of average goals scored and conceded by both sides.
* **`_home/_away` Split:** Yes (uses `goals_home` and `goals_away`).
* **Stat Type:** Average.
* **How L10 Series is Derived:** Synthesized from `l10_avg` of goals or from `l10_matches`.
* **Fatal Unknown Cases:** Unknown/unmappable goals keys.

### 1.3 CORNERS
* **Accepted Raw Stat Keys:** `corners`
* **Aggregation Policy:** Sum of averages or home/away split key averages.
* **`_home/_away` Split:** Yes (uses `corners_home` and `corners_away`).
* **Stat Type:** Count / Average.
* **How L10 Series is Derived:** Synthesized from `l10_avg` of corners or from `l10_matches`.
* **Fatal Unknown Cases:** Split stats with unknown split keys.

### 1.4 CARDS
* **Accepted Raw Stat Keys:** `yellow_cards`, `red_cards` (Note: red cards are never aggregated directly with yellow cards unless explicitly defined).
* **Aggregation Policy:** Direct mapping of raw card averages. Percentage values must never be summed.
* **`_home/_away` Split:** Yes (uses `yellow_cards_home`, `yellow_cards_away`).
* **Stat Type:** Count / Average.
* **How L10 Series is Derived:** Synthesized from `l10_avg` of yellow cards or from `l10_matches`.
* **Fatal Unknown Cases:** Mixed card metrics with raw percentages.

### 1.5 SHOTS
* **Accepted Raw Stat Keys:** `shots`
* **Aggregation Policy:** Direct mapping of raw shot count averages.
* **`_home/_away` Split:** Yes (uses `shots_home`, `shots_away`).
* **Stat Type:** Count / Average.
* **How L10 Series is Derived:** Synthesized from `l10_avg` of shots or from `l10_matches`.
* **Fatal Unknown Cases:** Ambiguous shot types or player props (player props are strictly blocked).

### 1.6 SHOTS_ON_TARGET
* **Accepted Raw Stat Keys:** `shots_on_target`
* **Aggregation Policy:** Direct mapping of raw shots on target averages.
* **`_home/_away` Split:** Yes (uses `shots_on_target_home`, `shots_on_target_away`).
* **Stat Type:** Count / Average.
* **How L10 Series is Derived:** Synthesized from `l10_avg` of shots on target or from `l10_matches`.
* **Fatal Unknown Cases:** Unknown split stat keys or player props.

---

## 2. Aggregation & Anti-Hallucination Constraints

1. **Percentage Stats Rule**: Any percentage stat (such as `possession_pct`) **must never be summed**. It must be combined using a mean aggregation policy (`MEAN_OF_HOME_AWAY_PERCENTAGES`).
2. **Split Stat Safety**: If split statistics are present (e.g. `corners_home` and `corners_away`), they must be resolved strictly using the pre-approved `aggregate_split_stat_value` protocol. If the policy is unknown, the candidate **must remain blocked** with `UNKNOWN_SPLIT_STAT_SEMANTICS`.
3. **No Player Props**: Player-specific prop markets (e.g. "player shots", "player tackles") remain strictly unsupported and must always stay blocked under `UNSUPPORTED_MARKET_FAMILY`.
