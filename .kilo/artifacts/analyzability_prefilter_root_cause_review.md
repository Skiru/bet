# Analyzability Prefilter Root-Cause Review

- source task: `ANALYZABILITY_PREFILTER_AND_DATA_READY_SHORTLIST_A`
- sandbox: `/private/tmp/premerge_probability_release_smoke_a`
- scope: `29` shortlist/S4 candidates analyzed from the last replay artifacts

## Summary of Blockers

- `UNSUPPORTED_SPORT`: `18` (tennis: 8, basketball: 8, cs2: 1, volleyball: 1)
- `STATS_SEED_MISSING`: `11` (all football candidates had no stats seed loaded because team stats were missing from DB and cache)

---

## Candidate Analysis

### tennis|Jesper De Jong|Rinky Hijikata|2026-06-29
* **candidate_id**: `tennis|Jesper De Jong|Rinky Hijikata|2026-06-29`
* **event_id / fixture_id**: `1`
* **sport**: `tennis`
* **competition**: `ATP Wimbledon`
* **participants**: `Jesper De Jong, Rinky Hijikata`
* **market_family**: `UNSUPPORTED_PROP_MATCH`
* **market_type**: `Player B Games O/U`
* **market_label**: `Player B Games O/U`
* **selection**: `UNDER`
* **direction**: `UNDER`
* **line**: `15.0`
* **odds_decimal**: `None`
* **stats_seed_available**: `true`
* **l10_series_available**: `true`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[0]`

### football|Germany|Paraguay|2026-06-29
* **candidate_id**: `football|Germany|Paraguay|2026-06-29`
* **event_id / fixture_id**: `2`
* **sport**: `football`
* **competition**: `International - FIFA World Cup`
* **participants**: `Germany, Paraguay`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `8.75`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[1]`

### tennis|Brandon Nakashima|Jack Pinnington Jones|2026-06-29
* **candidate_id**: `tennis|Brandon Nakashima|Jack Pinnington Jones|2026-06-29`
* **event_id / fixture_id**: `3`
* **sport**: `tennis`
* **competition**: `ATP Wimbledon`
* **participants**: `Brandon Nakashima, Jack Pinnington Jones`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[2]`

### tennis|Wu Yibing|Novak Djokovic|2026-06-29
* **candidate_id**: `tennis|Wu Yibing|Novak Djokovic|2026-06-29`
* **event_id / fixture_id**: `4`
* **sport**: `tennis`
* **competition**: `ATP Wimbledon`
* **participants**: `Wu Yibing, Novak Djokovic`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[3]`

### football|Democrata|Ivinhema|2026-06-29
* **candidate_id**: `football|Democrata|Ivinhema|2026-06-29`
* **event_id / fixture_id**: `5`
* **sport**: `football`
* **competition**: `Brazil - Brasileiro Serie D, Knockout Stage`
* **participants**: `Democrata, Ivinhema`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `6.25`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[4]`

### tennis|Broady, Liam|Matsuoka, Hayato|2026-06-29
* **candidate_id**: `tennis|Broady, Liam|Matsuoka, Hayato|2026-06-29`
* **event_id / fixture_id**: `6`
* **sport**: `tennis`
* **competition**: `Challenger - Cary, USA`
* **participants**: `Broady, Liam, Matsuoka, Hayato`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `3.5`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[5]`

### tennis|Glinka, Daniil|Mayo, Aidan|2026-06-29
* **candidate_id**: `tennis|Glinka, Daniil|Mayo, Aidan|2026-06-29`
* **event_id / fixture_id**: `7`
* **sport**: `tennis`
* **competition**: `Challenger - Cary, USA`
* **participants**: `Glinka, Daniil, Mayo, Aidan`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `2.25`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[6]`

### tennis|Hussey, Giles|Manning, William|2026-06-29
* **candidate_id**: `tennis|Hussey, Giles|Manning, William|2026-06-29`
* **event_id / fixture_id**: `8`
* **sport**: `tennis`
* **competition**: `Challenger - Cary, USA`
* **participants**: `Hussey, Giles, Manning, William`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `3.75`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[7]`

### tennis|Kennedy, Jack|Uchida, Kaichi|2026-06-29
* **candidate_id**: `tennis|Kennedy, Jack|Uchida, Kaichi|2026-06-29`
* **event_id / fixture_id**: `9`
* **sport**: `tennis`
* **competition**: `Challenger - Cary, USA`
* **participants**: `Kennedy, Jack, Uchida, Kaichi`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `2.37`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[8]`

### tennis|Watanuki, Yosuke|Ilagan, Andre|2026-06-29
* **candidate_id**: `tennis|Watanuki, Yosuke|Ilagan, Andre|2026-06-29`
* **event_id / fixture_id**: `10`
* **sport**: `tennis`
* **competition**: `Challenger - Cary, USA`
* **participants**: `Watanuki, Yosuke, Ilagan, Andre`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `1.9`
* **stats_seed_available**: `true`
* **l10_series_available**: `true`
* **split_stat_semantics_known**: `true`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[9]`

### football|Brazil|Japan|2026-06-29
* **candidate_id**: `football|Brazil|Japan|2026-06-29`
* **event_id / fixture_id**: `11`
* **sport**: `football`
* **competition**: `World Cup`
* **participants**: `Brazil, Japan`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[10]`

### football|Deportivo Garcilaso|Deportivo Binacional|2026-06-29
* **candidate_id**: `football|Deportivo Garcilaso|Deportivo Binacional|2026-06-29`
* **event_id / fixture_id**: `12`
* **sport**: `football`
* **competition**: `Copa De La Liga`
* **participants**: `Deportivo Garcilaso, Deportivo Binacional`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[11]`

### football|FBC Melgar|UCV Moquegua|2026-06-29
* **candidate_id**: `football|FBC Melgar|UCV Moquegua|2026-06-29`
* **event_id / fixture_id**: `13`
* **sport**: `football`
* **competition**: `Copa De La Liga`
* **participants**: `FBC Melgar, UCV Moquegua`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[12]`

### basketball|Aleman|CD Huachipato|2026-06-29
* **candidate_id**: `basketball|Aleman|CD Huachipato|2026-06-29`
* **event_id / fixture_id**: `14`
* **sport**: `basketball`
* **competition**: `LNB 2`
* **participants**: `Aleman, CD Huachipato`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[13]`

### basketball|The Sharks|Arturo Prat San Felipe|2026-06-29
* **candidate_id**: `basketball|The Sharks|Arturo Prat San Felipe|2026-06-29`
* **event_id / fixture_id**: `15`
* **sport**: `basketball`
* **competition**: `LNB 2`
* **participants**: `The Sharks, Arturo Prat San Felipe`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[14]`

### cs2|MIBR Academy|Procyon Gaming|2026-06-29
* **candidate_id**: `cs2|MIBR Academy|Procyon Gaming|2026-06-29`
* **event_id / fixture_id**: `16`
* **sport**: `cs2`
* **competition**: `Series 3`
* **participants**: `MIBR Academy, Procyon Gaming`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `2.0`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[15]`

### football|Union Espanola|Colo-Colo|2026-06-29
* **candidate_id**: `football|Union Espanola|Colo-Colo|2026-06-29`
* **event_id / fixture_id**: `16`
* **sport**: `football`
* **competition**: `Chile - Copa Chile, Group E`
* **participants**: `Union Espanola, Colo-Colo`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `5.75`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[16]`

### basketball|Iran|Syria|2026-06-29
* **candidate_id**: `basketball|Iran|Syria|2026-06-29`
* **event_id / fixture_id**: `17`
* **sport**: `basketball`
* **competition**: `World Cup`
* **participants**: `Iran, Syria`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[17]`

### basketball|Iraq|Jordan|2026-06-29
* **candidate_id**: `basketball|Iraq|Jordan|2026-06-29`
* **event_id / fixture_id**: `18`
* **sport**: `basketball`
* **competition**: `World Cup`
* **participants**: `Iraq, Jordan`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[18]`

### basketball|Lebanon|India|2026-06-29
* **candidate_id**: `basketball|Lebanon|India|2026-06-29`
* **event_id / fixture_id**: `19`
* **sport**: `basketball`
* **competition**: `World Cup`
* **participants**: `Lebanon, India`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[19]`

### volleyball|Blat|Anwar|2026-06-29
* **candidate_id**: `volleyball|Blat|Anwar|2026-06-29`
* **event_id / fixture_id**: `20`
* **sport**: `volleyball`
* **competition**: `1st Division`
* **participants**: `Blat, Anwar`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[20]`

### basketball|Qatar|Saudi Arabia|2026-06-29
* **candidate_id**: `basketball|Qatar|Saudi Arabia|2026-06-29`
* **event_id / fixture_id**: `21`
* **sport**: `basketball`
* **competition**: `World Cup`
* **participants**: `Qatar, Saudi Arabia`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[21]`

### football|Gol Gohar|Chadormalu SC|2026-06-29
* **candidate_id**: `football|Gol Gohar|Chadormalu SC|2026-06-29`
* **event_id / fixture_id**: `22`
* **sport**: `football`
* **competition**: `Persian Gulf Pro League`
* **participants**: `Gol Gohar, Chadormalu SC`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[22]`

### football|Asheville City SC|Charlotte Independence 2|2026-06-29
* **candidate_id**: `football|Asheville City SC|Charlotte Independence 2|2026-06-29`
* **event_id / fixture_id**: `23`
* **sport**: `football`
* **competition**: `USA - USL, League Two`
* **participants**: `Asheville City SC, Charlotte Independence 2`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[23]`

### football|Academica|Marin|2026-06-29
* **candidate_id**: `football|Academica|Marin|2026-06-29`
* **event_id / fixture_id**: `24`
* **sport**: `football`
* **competition**: `USL League Two`
* **participants**: `Academica, Marin`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[24]`

### football|Miami AC|Brevard|2026-06-29
* **candidate_id**: `football|Miami AC|Brevard|2026-06-29`
* **event_id / fixture_id**: `25`
* **sport**: `football`
* **competition**: `USL League Two`
* **participants**: `Miami AC, Brevard`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `None`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_STATS_MISSING`
* **exact blocker reason**: `STATS_SEED_MISSING`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[25]`

### basketball|Club Atletico Olimpia|CD Albatros|2026-06-29
* **candidate_id**: `basketball|Club Atletico Olimpia|CD Albatros|2026-06-29`
* **event_id / fixture_id**: `26`
* **sport**: `basketball`
* **competition**: `Uruguay - Liga de Ascenso`
* **participants**: `Club Atletico Olimpia, CD Albatros`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `3.75`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[26]`

### basketball|Tabare|Colon|2026-06-29
* **candidate_id**: `basketball|Tabare|Colon|2026-06-29`
* **event_id / fixture_id**: `27`
* **sport**: `basketball`
* **competition**: `Uruguay - Liga de Ascenso`
* **participants**: `Tabare, Colon`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `8.25`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[27]`

### basketball|Trouville|Lagomar|2026-06-29
* **candidate_id**: `basketball|Trouville|Lagomar|2026-06-29`
* **event_id / fixture_id**: `28`
* **sport**: `basketball`
* **competition**: `Uruguay - Liga de Ascenso`
* **participants**: `Trouville, Lagomar`
* **market_family**: `None`
* **market_type**: `None`
* **market_label**: `None`
* **selection**: `None`
* **direction**: `None`
* **line**: `None`
* **odds_decimal**: `2.85`
* **stats_seed_available**: `false`
* **l10_series_available**: `false`
* **split_stat_semantics_known**: `false`
* **market_probability_input_buildable**: `false`
* **model_probability_buildable**: `false`
* **analyzability_status**: `RESEARCH_GAP_SPORT_UNSUPPORTED`
* **exact blocker reason**: `UNSUPPORTED_SPORT`
* **source_artifact_path**: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s4_valuation_candidates.json`
* **field_path**: `candidates[28]`
