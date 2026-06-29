# Football Stats Seed Contract

## 1. Objective
Define the minimal statistical data schema (the stats seed) required for each supported market family in football to enable analytical modeling and probability evaluation.

---

## 2. Minimal Stats Seeds by Market Family

### RESULT
* **Description:** Match winner, Double Chance, Draw No Bet (3-way or 2-way outcomes).
* **Required Fields:**
  * `l10_matches` list with at least 5 games including:
    * `opponent_name`
    * `full_time_score_home`
    * `full_time_score_away`
    * `is_home` (whether team was playing at home)
* **Optional Fields:** `half_time_score_home`, `half_time_score_away`
* **Minimum Sample Size:** 5 matches (L10 preferably, minimum 5)
* **Source Freshness:** `< 48 hours`
* **Fatal Gaps:** No matches or scores in the last 10 games.
* **Non-fatal Gaps:** Missing halftime scores.

### GOALS_TOTALS
* **Description:** Over/Under Total Goals, Team Total Goals.
* **Required Fields:**
  * `l10_matches` with fulltime scores (home and away goals scored and conceded).
  * `l10_avg["goals"]` (average team goals scored per match in last 10).
  * `l10_avg["goals_conceded"]` (average team goals conceded per match in last 10).
* **Optional Fields:** `l5_avg["goals"]`, `l5_avg["goals_conceded"]`
* **Minimum Sample Size:** 5 matches
* **Source Freshness:** `< 48 hours`
* **Fatal Gaps:** Missing match score data entirely.
* **Non-fatal Gaps:** Missing L5 average (computable on fly if raw matches exist).

### CORNERS
* **Description:** Match Corners Over/Under, Team Corners Over/Under.
* **Required Fields:**
  * `l10_avg["corners"]` (average team corners in last 10).
  * `l10_avg["corners_conceded"]` (average opponent corners in last 10).
* **Optional Fields:** `l5_avg["corners"]`, `l10_values["corners"]`
* **Minimum Sample Size:** 5 matches
* **Source Freshness:** `< 48 hours`
* **Fatal Gaps:** Missing corners average for both teams.
* **Non-fatal Gaps:** Missing match-by-match raw values if averages are present.

### CARDS
* **Description:** Booking Points, Yellow Cards Over/Under, Red Cards.
* **Required Fields:**
  * `l10_avg["yellow_cards"]` (average team yellow cards).
  * `l10_avg["red_cards"]` (average team red cards).
* **Optional Fields:** `l10_avg["yellow_cards_conceded"]`, `l10_avg["red_cards_conceded"]`
* **Minimum Sample Size:** 5 matches
* **Source Freshness:** `< 48 hours`
* **Fatal Gaps:** Missing cards data entirely.
* **Non-fatal Gaps:** Missing card details for individual games.

### SHOTS
* **Description:** Shots Over/Under.
* **Required Fields:**
  * `l10_avg["shots"]` (average team shots).
  * `l10_avg["shots_conceded"]` (average opponent shots).
* **Minimum Sample Size:** 5 matches
* **Fatal Gaps:** Missing shots averages entirely.
* **Non-fatal Gaps:** Missing raw values.

### SHOTS_ON_TARGET
* **Description:** Shots on Target Over/Under.
* **Required Fields:**
  * `l10_avg["shots_on_target"]` (average team shots on target).
  * `l10_avg["shots_on_target_conceded"]` (average opponent shots on target).
* **Minimum Sample Size:** 5 matches
* **Fatal Gaps:** Missing shots on target averages entirely.
* **Non-fatal Gaps:** Missing raw values.

---

## 3. Provider Priority

To ensure data integrity, stats are looked up in the following strict order:
1. **Existing DB/Cache (Highest Priority):** Checks `team_form` table in SQLite first, followed by JSON files in `stats_cache/football/`.
2. **API-Football / API-Sports (Second Priority):** Enriches from `api-football` endpoints if keys and environment are configured.
3. **Football-Data.org (Third Priority):** Pulls from `football-data.org` ONLY for league standings, upcoming fixtures, and context.
4. **Explicit Gap (Hard Stop):** If no source has data, S3 must report an explicit `stats_gap_reason` (e.g., `NO_STATS_DATA_FROM_CACHE_OR_DB`). No fake/dummy stats are permitted.
