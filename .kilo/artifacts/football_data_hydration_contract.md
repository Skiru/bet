# Football Data Hydration Contract

This contract defines the strict schema and behavioral specifications for hydrating football-related stats and historical series in the `S3` and `S4` stages of the sports betting pipeline.

---

## 1. Schema Specifications: `FootballDataHydrationReport`

Every hydrated candidate must produce or reference a structured entry matching the JSON Schema in `football_data_hydration_contract.json` with the following fields:

* **`candidate_id`** (string): Unique identifier for the candidate match.
* **`home_team`** (string): Canonical home team name.
* **`away_team`** (string): Canonical away team name.
* **`home_provider_team_id`** (string | null): Provider-specific ID for the home team (e.g., API-Football ID).
* **`away_provider_team_id`** (string | null): Provider-specific ID for the away team.
* **`competition`** (string): Name of the league/competition.
* **`market_family`** (string | null): Canonical market family (e.g. `SHOTS`, `GOALS_TOTALS`, `CORNERS`, `CARDS`).
* **`required_stats`** (array of strings): Metrics needed for the specific market family.
* **`hydrated_stats`** (array of strings): Actually found and hydrated metrics.
* **`l10_series_home`** (array of numbers): Last 10 matches stat values for home team.
* **`l10_series_away`** (array of numbers): Last 10 matches stat values for away team.
* **`stat_semantics`** (object): Mapping of key properties (e.g. split policies, stat type).
* **`source_provider`** (string): E.g. `api-football`, `local_db_cache`.
* **`source_artifact_path`** (string): File path of the originating artifact.
* **`as_of_utc`** (string): UTC timestamp when data was fetched or loaded.
* **`hydration_status`** (string): Status of the hydration process.
* **`gap_reasons`** (array of strings): List of specific failure reasons if not fully hydrated.

---

## 2. Hydration Statuses

* **`HYDRATED`**: Both teams have complete L10 statistics, and line/direction inputs are fully buildable.
* **`PARTIAL_HYDRATION`**: Some stats are present but sample size < 5 or one team lacks data.
* **`L10_SERIES_MISSING`**: No recent match series could be retrieved for either team.
* **`TEAM_IDENTITY_MISSING`**: One or both teams could not be mapped to provider-specific team IDs.
* **`PROVIDER_DATA_UNAVAILABLE`**: API or Cache returned empty responses or errors.
* **`STAT_SEMANTICS_UNKNOWN`**: Split averages or stats are present but aggregation policy is unsupported or ambiguous.
* **`MARKET_INPUT_NOT_BUILDABLE`**: Found stats but cannot map line or direction to a buildable market probability input.

---

## 3. Core Contract Rules

1. **Analytical Eligibility**: Only `HYDRATED` candidates may feed downstream analyzability as stats-ready. 
2. **Research Package Restriction**: `PARTIAL_HYDRATION` or other blocked statuses may appear in the research package only, never as `ANALYZABLE`.
3. **No Fake Rows**: Under no circumstances can placeholder, default, or random stats be injected to satisfy the length >= 5 constraint. If data is missing, the candidate must remain blocked with an honest data gap status.
4. **No Implied Probabilities as Stats**: Bookmaker implied probabilities cannot be substituted for actual statistical averages or model probability inputs.
5. **Traceability**: Every stat must have a declared `source_provider` and `as_of_utc` timestamp.
