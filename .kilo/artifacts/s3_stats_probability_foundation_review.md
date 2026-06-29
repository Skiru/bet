# S3 Stats & Probability Foundation Review

## 1. Overview
In the `ANALYTICAL_CANDIDATE_GENERATION_BRIDGE_A` replay, S3 returned `candidates_with_data: 0` out of 8 shortlisted football candidates. This is a trace and root-cause analysis of why each candidate failed to obtain supporting statistics.

---

## 2. Per-Candidate Analysis

### Candidate 1: Brazil vs Japan
* **Candidate ID:** `football|Brazil|Japan|2026-06-29`
* **Sport:** football
* **Competition:** International - FIFA World Cup
* **Participants:** `["Brazil", "Japan"]`
* **Provider Fixture ID:** 1
* **Canonical Names:** Home: Brazil, Away: Japan
* **S3 Lookup Keys Attempted:** `brazil`, `japan` (exact matches and `TeamRepo.resolve` calls)
* **DB/Cache Files Attempted:** `stats_cache/football/brazil.json`, `stats_cache/football/japan.json`, SQLite queries to the `teams` table for sport ID of football.
* **Provider Team ID if Found:** None
* **Provider Team ID if Missing:** Both `Brazil` and `Japan` are missing from DB.
* **Exact Reason for No Stats:** Neither team exists in the database `teams` table, and there are no files `stats_cache/football/brazil.json` or `stats_cache/football/japan.json` in the replay directory or repo-local directory.
* **Classification:** `TEAM_IDENTITY_RESOLUTION_GAP`, `STATS_CACHE_MISSING`, `API_FOOTBALL_TEAM_LOOKUP_MISSING`, `API_FOOTBALL_STATS_NOT_CALLED`

### Candidate 2: Germany vs Paraguay
* **Candidate ID:** `football|Germany|Paraguay|2026-06-29`
* **Sport:** football
* **Competition:** International - FIFA World Cup
* **Participants:** `["Germany", "Paraguay"]`
* **Provider Fixture ID:** 2
* **Canonical Names:** Home: Germany, Away: Paraguay
* **S3 Lookup Keys Attempted:** `germany`, `paraguay`
* **DB/Cache Files Attempted:** `stats_cache/football/germany.json`, `stats_cache/football/paraguay.json`, DB team resolve.
* **Provider Team ID if Found:** None
* **Provider Team ID if Missing:** Both missing from DB.
* **Exact Reason for No Stats:** Both teams are missing from DB and cache files are missing. Also blocked on unsupported market family `player_tackles`.
* **Classification:** `TEAM_IDENTITY_RESOLUTION_GAP`, `STATS_CACHE_MISSING`, `API_FOOTBALL_TEAM_LOOKUP_MISSING`, `MARKET_FAMILY_UNSUPPORTED`

### Candidate 3: Deportivo Garcilaso vs Deportivo Binacional
* **Candidate ID:** `football|Deportivo Garcilaso|Deportivo Binacional|2026-06-29`
* **Sport:** football
* **Competition:** Peru - Copa de la Liga, Group F
* **Participants:** `["Deportivo Garcilaso", "Deportivo Binacional"]`
* **Provider Fixture ID:** 3
* **S3 Lookup Keys Attempted:** `deportivo-garcilaso`, `deportivo-binacional`
* **DB/Cache Files Attempted:** `stats_cache/football/deportivo-garcilaso.json`, `stats_cache/football/deportivo-binacional.json`
* **Provider Team ID if Found/Missing:** Both missing from DB and cache.
* **Exact Reason for No Stats:** Teams not resolved, cache missing, Peru Cup competition profile has mapping gap.
* **Classification:** `TEAM_IDENTITY_RESOLUTION_GAP`, `STATS_CACHE_MISSING`, `COMPETITION_MAPPING_GAP`

### Candidate 4: Melgar vs CD Moquegua
* **Candidate ID:** `football|Melgar|CD Moquegua|2026-06-29`
* **Sport:** football
* **Competition:** Peru - Copa de la Liga, Group H
* **Participants:** `["Melgar", "CD Moquegua"]`
* **Provider Fixture ID:** 4
* **S3 Lookup Keys Attempted:** `melgar`, `cd-moquegua`
* **DB/Cache Files Attempted:** `stats_cache/football/melgar.json`, `stats_cache/football/cd-moquegua.json`
* **Exact Reason for No Stats:** DB resolve fails, cache missing, competition mapping gap.
* **Classification:** `TEAM_IDENTITY_RESOLUTION_GAP`, `STATS_CACHE_MISSING`, `COMPETITION_MAPPING_GAP`

### Candidate 5: B68 Toftir vs Argir
* **Candidate ID:** `football|B68 Toftir|Argir|2026-06-29`
* **Sport:** football
* **Competition:** Faroe Islands - Premier League
* **Participants:** `["B68 Toftir", "Argir"]`
* **Provider Fixture ID:** 5
* **S3 Lookup Keys Attempted:** `b68-toftir`, `argir`
* **DB/Cache Files Attempted:** `stats_cache/football/b68-toftir.json`, `stats_cache/football/argir.json`
* **Exact Reason for No Stats:** Teams not resolved in DB, cache files missing.
* **Classification:** `TEAM_IDENTITY_RESOLUTION_GAP`, `STATS_CACHE_MISSING`

### Candidate 6: HB Torshavn vs Skala
* **Candidate ID:** `football|HB Torshavn|Skala|2026-06-29`
* **Sport:** football
* **Competition:** Faroe Islands - Premier League
* **Participants:** `["HB Torshavn", "Skala"]`
* **Provider Fixture ID:** 6
* **S3 Lookup Keys Attempted:** `hb-torshavn`, `skala`
* **DB/Cache Files Attempted:** `stats_cache/football/hb-torshavn.json`, `stats_cache/football/skala.json`
* **Exact Reason for No Stats:** Teams not resolved in DB, cache files missing.
* **Classification:** `TEAM_IDENTITY_RESOLUTION_GAP`, `STATS_CACHE_MISSING`

### Candidate 7: Vikingur vs Runavik
* **Candidate ID:** `football|Vikingur|Runavik|2026-06-29`
* **Sport:** football
* **Competition:** Faroe Islands - Premier League
* **Participants:** `["Vikingur", "Runavik"]`
* **Provider Fixture ID:** 7
* **S3 Lookup Keys Attempted:** `vikingur`, `runavik`
* **DB/Cache Files Attempted:** `stats_cache/football/vikingur.json`, `stats_cache/football/runavik.json`
* **Exact Reason for No Stats:** Teams not resolved in DB, cache files missing.
* **Classification:** `TEAM_IDENTITY_RESOLUTION_GAP`, `STATS_CACHE_MISSING`

### Candidate 8: Kazma vs Al-Salmiya
* **Candidate ID:** `football|Kazma|Al-Salmiya|2026-06-29`
* **Sport:** football
* **Competition:** Kuwait - Premier League, Championship Group
* **Participants:** `["Kazma", "Al-Salmiya"]`
* **Provider Fixture ID:** 8
* **S3 Lookup Keys Attempted:** `kazma`, `al-salmiya`
* **DB/Cache Files Attempted:** `stats_cache/football/kazma.json`, `stats_cache/football/al-salmiya.json`
* **Exact Reason for No Stats:** Teams not resolved in DB, cache files missing.
* **Classification:** `TEAM_IDENTITY_RESOLUTION_GAP`, `STATS_CACHE_MISSING`

---

## 3. General Gap Summary Table

| Gap Category | Count | Primary Remedy |
|---|---|---|
| **TEAM_IDENTITY_RESOLUTION_GAP** | 8 | Build minimal football team identity resolver supporting aliases/normalization |
| **STATS_CACHE_MISSING** | 8 | Seed stats json cache for target smoke cases when cache missing |
| **COMPETITION_MAPPING_GAP** | 2 | Improve competition mapping profiles to support Peru Copa |
| **MARKET_FAMILY_UNSUPPORTED** | 1 | Block player_tackles from promotion, mapping correctly to UNSUPPORTED_PROP_MATCH |
