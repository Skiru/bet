# S3 Market-Specific Probability Gap Review

## 1. Candidate Gap Traces

### Candidate 1: Brazil vs Japan
* **candidate_id**: `football|Brazil|Japan|2026-06-29`
* **sport**: `football`
* **competition**: `International - FIFA World Cup`
* **participants**: `["Brazil", "Japan"]`
* **market_family**: `SHOTS`
* **market_type**: `Japan Shots O/U`
* **selection**: `UNDER` (Japan Shots UNDER 24.0)
* **line**: `24.0`
* **stats_seed_fields_present**: `l10_avg` (shots, corners, fouls, goals, yellow_cards, etc. for both sides in DB)
* **stats_seed_fields_missing**: None
* **whether `team_a_l10` can be derived**: `yes`
* **whether `team_b_l10` can be derived**: `yes` (Japan is Team B)
* **whether market direction exists**: `yes` (UNDER)
* **whether probability_engine receives an input market**: `yes`
* **exact reason model_probability is still null**: `PROBABILITY_ENGINE_OUTPUT_NOT_PROPAGATED` / `ValueError` in `float(hit_rate)` parser when trying to convert `'5/10'` string, silently caught and ignored.
* **classification**: `PROBABILITY_ENGINE_OUTPUT_NOT_PROPAGATED`

### Candidate 2: Germany vs Paraguay
* **candidate_id**: `football|Germany|Paraguay|2026-06-29`
* **sport**: `football`
* **competition**: `International - FIFA World Cup`
* **participants**: `["Germany", "Paraguay"]`
* **market_family**: `UNSUPPORTED_PROP_MATCH`
* **market_type**: `player_tackles`
* **selection**: `over`
* **line**: `null`
* **stats_seed_fields_present**: None (player props not in normal team stats DB)
* **stats_seed_fields_missing**: `goals`, `corners`, `yellow_cards`
* **whether `team_a_l10` can be derived**: `no`
* **whether `team_b_l10` can be derived**: `no`
* **whether market direction exists**: `yes` (over)
* **whether probability_engine receives an input market**: `no`
* **exact reason model_probability is still null**: `MARKET_FAMILY_NOT_SUPPORTED_BY_ENGINE` (player tackles and other player props remain blocked).
* **classification**: `MARKET_FAMILY_NOT_SUPPORTED_BY_ENGINE`

### Candidate 3: Deportivo Garcilaso vs Deportivo Binacional
* **candidate_id**: `football|Deportivo Garcilaso|Deportivo Binacional|2026-06-29`
* **sport**: `football`
* **competition**: `Peru - Copa de la Liga, Group F`
* **participants**: `["Deportivo Garcilaso", "Deportivo Binacional"]`
* **market_family**: `GOALS_TOTALS`
* **market_type**: `Goals Total O/U`
* **selection**: `UNDER`
* **line**: `3.0`
* **stats_seed_fields_present**: `l10_avg` for Garcilaso, `l10_matches` for both.
* **stats_seed_fields_missing**: `l10_avg` keys for Binacional (due to DB split-key format discrepancy `goals_home`/`goals_away`).
* **whether `team_a_l10` can be derived**: `yes`
* **whether `team_b_l10` can be derived**: `no` (missing due to DB split keys)
* **whether market direction exists**: `yes` (UNDER)
* **whether probability_engine receives an input market**: `yes`
* **exact reason model_probability is still null**: `L10_SERIES_MISSING` / `MARKET_SPECIFIC_INPUT_NOT_BUILT` (stats_b has_data was evaluated as false because DB goals average split keys were not merged in deep stats report loading).
* **classification**: `MARKET_SPECIFIC_INPUT_NOT_BUILT`

### Candidate 4: Melgar vs CD Moquegua
* **candidate_id**: `football|Melgar|CD Moquegua|2026-06-29`
* **sport**: `football`
* **competition**: `Peru - Copa de la Liga, Group H`
* **participants**: `["Melgar", "CD Moquegua"]`
* **market_family**: `GOALS_TOTALS`
* **market_type**: `Goals Total O/U`
* **selection**: `UNDER`
* **line**: `2.5`
* **stats_seed_fields_present**: `l10_avg` for Moquegua, `l10_matches` for both.
* **stats_seed_fields_missing**: `l10_avg` keys for Melgar (due to DB split-key format discrepancy `goals_home`/`goals_away`).
* **whether `team_a_l10` can be derived**: `no` (missing due to DB split keys)
* **whether `team_b_l10` can be derived**: `yes`
* **whether market direction exists**: `yes` (UNDER)
* **whether probability_engine receives an input market**: `yes`
* **exact reason model_probability is still null**: `L10_SERIES_MISSING` / `MARKET_SPECIFIC_INPUT_NOT_BUILT` (stats_a has_data was evaluated as false because DB goals average split keys were not merged).
* **classification**: `MARKET_SPECIFIC_INPUT_NOT_BUILT`

### Candidate 5: B68 Toftir vs Argir
* **candidate_id**: `football|B68 Toftir|Argir|2026-06-29`
* **sport**: `football`
* **competition**: `Faroe Islands - Premier League`
* **participants**: `["B68 Toftir", "Argir"]`
* **market_family**: `RESULT`
* **market_type**: `ml`
* **selection**: `Argir`
* **line**: `null`
* **stats_seed_fields_present**: None (teams missing stats entirely)
* **stats_seed_fields_missing**: All stats
* **whether `team_a_l10` can be derived**: `no`
* **whether `team_b_l10` can be derived**: `no`
* **whether market direction exists**: `yes` (winner / ml)
* **whether probability_engine receives an input market**: `no`
* **exact reason model_probability is still null**: `L10_SERIES_MISSING` / `INSUFFICIENT_SAMPLE_SIZE` (no stats exist in DB or cache).
* **classification**: `L10_SERIES_MISSING`

### Candidate 6: HB Torshavn vs Skala
* **candidate_id**: `football|HB Torshavn|Skala|2026-06-29`
* **sport**: `football`
* **competition**: `Faroe Islands - Premier League`
* **participants**: `["HB Torshavn", "Skala"]`
* **market_family**: `RESULT`
* **market_type**: `ml`
* **selection**: `Skala`
* **line**: `null`
* **stats_seed_fields_present**: `l10_avg` for HB Torshavn
* **stats_seed_fields_missing**: `l10_avg` for Skala
* **whether `team_a_l10` can be derived**: `yes`
* **whether `team_b_l10` can be derived**: `no`
* **whether market direction exists**: `yes`
* **whether probability_engine receives an input market**: `no`
* **exact reason model_probability is still null**: `L10_SERIES_MISSING` (Skala stats are missing).
* **classification**: `L10_SERIES_MISSING`

### Candidate 7: Vikingur vs Runavik
* **candidate_id**: `football|Vikingur|Runavik|2026-06-29`
* **sport**: `football`
* **competition**: `Faroe Islands - Premier League`
* **participants**: `["Vikingur", "Runavik"]`
* **market_family**: `GOALS_TOTALS`
* **market_type**: `Goals Total O/U`
* **selection**: `UNDER`
* **line**: `2.0`
* **stats_seed_fields_present**: None (no averages loaded because of DB split keys discrepancy)
* **stats_seed_fields_missing**: Both team averages
* **whether `team_a_l10` can be derived**: `no`
* **whether `team_b_l10` can be derived**: `no`
* **whether market direction exists**: `yes` (UNDER)
* **whether probability_engine receives an input market**: `yes`
* **exact reason model_probability is still null**: `L10_SERIES_MISSING` / `MARKET_SPECIFIC_INPUT_NOT_BUILT` (both teams have has_data evaluated as false due to split-key format discrepancy).
* **classification**: `MARKET_SPECIFIC_INPUT_NOT_BUILT`

### Candidate 8: Kazma vs Al-Salmiya
* **candidate_id**: `football|Kazma|Al-Salmiya|2026-06-29`
* **sport**: `football`
* **competition**: `Kuwait - Premier League, Championship Group`
* **participants**: `["Kazma", "Al-Salmiya"]`
* **market_family**: `RESULT`
* **market_type**: `ml`
* **selection**: `Al-Salmiya`
* **line**: `null`
* **stats_seed_fields_present**: `l10_avg` for Al-Salmiya
* **stats_seed_fields_missing**: `l10_avg` for Kazma
* **whether `team_a_l10` can be derived**: `no`
* **whether `team_b_l10` can be derived**: `yes`
* **whether market direction exists**: `yes`
* **whether probability_engine receives an input market**: `no`
* **exact reason model_probability is still null**: `L10_SERIES_MISSING` (Kazma stats are missing).
* **classification**: `L10_SERIES_MISSING`
