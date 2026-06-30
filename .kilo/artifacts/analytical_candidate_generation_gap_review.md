# Analytical Candidate Generation Gap Review

- task: `ANALYTICAL_CANDIDATE_GENERATION_BRIDGE_A`
- failed smoke artifact set: `/private/tmp/full_analytical_session_smoke_a`
- replay artifact set used to validate the bridge: `/private/tmp/analytical_candidate_bridge_replay_b`

## Summary

- Original smoke root cause 1: `S3` produced `candidates_with_data=0/8`, so no ranked market or model probability existed for any selected football fixture.
- Original smoke root cause 2: `S4` stripped `sport` and market identity from valuation rows even though `S3` still carried `sport=football`, so `S5` rejected all `8/8` rows as `REJECTED_MISSING_SPORT` instead of reporting an upstream propagation fault with field paths.
- Post-fix replay: `S4` now preserves event identity; `S5` reads `S4` instead of accidentally falling back to `S3`; `analytical_candidate_handoff.json` is emitted with `blocked_probability_missing=7`, `blocked_identity_missing=1`; `S8` emits a `RESEARCH_GAP_PACKAGE` instead of `BLOCKED_COUPON_INPUT_MISSING`.

## Candidate Trace

### 1. Brazil vs Japan

- candidate_id: `football|Brazil|Japan|2026-06-29`
- event_id / fixture_id: `1`
- sport before S4: `football`
- sport after S4 in failed smoke: `null`
- sport after S4 in replay: `football`
- competition before S4: `International - FIFA World Cup`
- competition after S4: `International - FIFA World Cup`
- participants before S4: `Brazil`, `Japan`
- participants after S4 in replay: `Brazil`, `Japan`
- market_family: `RESULT`
- market_type: `ml`
- pick / selection: `Japan`
- line: `null`
- odds_decimal: `5.0`
- odds_source / as_of: `betclic`, `UNAVAILABLE`
- model_probability: `null`
- ev_missing_reason: `MISSING_PROBABILITY`
- supporting_stats_count: `0`
- candidates_with_data flag: `false`
- why S3 had no data: shortlist row had `n_safety_markets=0`; no cache/DB team-form payload was available; `S3` emitted `NO_STATS_DATA: Could not build safety input from cache`
- why S4 had `MISSING_PROBABILITY`: `S3` produced no ranked market; replay now records `probability_missing_reason=NO_RANKED_MARKET`
- why S5 saw `REJECTED_MISSING_SPORT`: failed-smoke `S4` row dropped `sport`; current fix preserves it and attaches field-path diagnostics on rejection
- could become analytical if identity/probability/evidence existed: `yes`
- classifications: `IDENTITY_PROPAGATION_BUG`, `SPORT_MISSING_BUG`, `S3_STATS_JOIN_BUG`, `S4_PROBABILITY_MISSING`, `ANALYTICAL_ELIGIBLE_AFTER_FIX`

### 2. Germany vs Paraguay

- candidate_id: `football|Germany|Paraguay|2026-06-29`
- event_id / fixture_id: `2`
- sport before S4: `football`
- sport after S4 in failed smoke: `null`
- sport after S4 in replay: `football`
- competition before S4: `International - FIFA World Cup`
- competition after S4: `International - FIFA World Cup`
- participants before S4: `Germany`, `Paraguay`
- participants after S4 in replay: `Germany`, `Paraguay`
- market_family: `UNSUPPORTED_PROP_MATCH`
- market_type: `player_tackles`
- pick / selection: `over`
- line: `null`
- odds_decimal: `8.5`
- odds_source / as_of: `betclic`, `UNAVAILABLE`
- model_probability: `null`
- ev_missing_reason: `MISSING_PROBABILITY`
- supporting_stats_count: `0`
- candidates_with_data flag: `false`
- why S3 had no data: same pattern as above; `S3` emitted `NO_STATS_DATA...` and replay logs show `Team not found: Germany` and `Team not found: Paraguay`
- why S4 had `MISSING_PROBABILITY`: no ranked market and no model probability existed upstream
- why S5 saw `REJECTED_MISSING_SPORT`: failed-smoke `S4` row lost `sport`; replay keeps `sport` and the bridge now classifies this row as a market-family identity gap instead of a hidden sport loss
- could become analytical if identity/probability/evidence existed: `not with the exact matched prop market; only after a supported football family is identified`
- classifications: `IDENTITY_PROPAGATION_BUG`, `SPORT_MISSING_BUG`, `S3_STATS_JOIN_BUG`, `S4_PROBABILITY_MISSING`, `MARKET_FAMILY_MAPPING_MISSING`, `NOT_ANALYTICAL_ELIGIBLE`

### 3. Deportivo Garcilaso vs Deportivo Binacional

- candidate_id: `football|Deportivo Garcilaso|Deportivo Binacional|2026-06-29`
- event_id / fixture_id: `3`
- sport before S4: `football`
- sport after S4 in failed smoke: `null`
- sport after S4 in replay: `football`
- competition before S4: `Peru - Copa de la Liga, Group F`
- competition after S4: `Peru - Copa de la Liga, Group F`
- participants before S4: `Deportivo Garcilaso`, `Deportivo Binacional`
- participants after S4 in replay: `Deportivo Garcilaso`, `Deportivo Binacional`
- market_family: `RESULT`
- market_type: `ml`
- pick / selection: `Deportivo Binacional`
- line: `null`
- odds_decimal: `6.0`
- odds_source / as_of: `api`, `UNAVAILABLE`
- model_probability: `null`
- ev_missing_reason: `MISSING_PROBABILITY`
- supporting_stats_count: `0`
- candidates_with_data flag: `false`
- why S3 had no data: `n_safety_markets=0`, no cache/DB match, `NO_STATS_DATA...`
- why S4 had `MISSING_PROBABILITY`: no ranked market / no model probability from `S3`
- why S5 saw `REJECTED_MISSING_SPORT`: anonymous `S4` row in failed smoke
- could become analytical if identity/probability/evidence existed: `yes`
- classifications: `IDENTITY_PROPAGATION_BUG`, `SPORT_MISSING_BUG`, `S3_STATS_JOIN_BUG`, `S4_PROBABILITY_MISSING`, `ANALYTICAL_ELIGIBLE_AFTER_FIX`

### 4. Melgar vs CD Moquegua

- candidate_id: `football|Melgar|CD Moquegua|2026-06-29`
- event_id / fixture_id: `4`
- sport before S4: `football`
- sport after S4 in failed smoke: `null`
- sport after S4 in replay: `football`
- competition before S4: `Peru - Copa de la Liga, Group H`
- competition after S4: `Peru - Copa de la Liga, Group H`
- participants before S4: `Melgar`, `CD Moquegua`
- participants after S4 in replay: `Melgar`, `CD Moquegua`
- market_family: `RESULT`
- market_type: `ml`
- pick / selection: `CD Moquegua`
- line: `null`
- odds_decimal: `3.4`
- odds_source / as_of: `api`, `UNAVAILABLE`
- model_probability: `null`
- ev_missing_reason: `MISSING_PROBABILITY`
- supporting_stats_count: `0`
- candidates_with_data flag: `false`
- why S3 had no data: `n_safety_markets=0`, no cache/DB match, `NO_STATS_DATA...`
- why S4 had `MISSING_PROBABILITY`: no ranked market / no model probability from `S3`
- why S5 saw `REJECTED_MISSING_SPORT`: anonymous `S4` row in failed smoke
- could become analytical if identity/probability/evidence existed: `yes`
- classifications: `IDENTITY_PROPAGATION_BUG`, `SPORT_MISSING_BUG`, `S3_STATS_JOIN_BUG`, `S4_PROBABILITY_MISSING`, `ANALYTICAL_ELIGIBLE_AFTER_FIX`

### 5. B68 Toftir vs Argir

- candidate_id: `football|B68 Toftir|Argir|2026-06-29`
- event_id / fixture_id: `5`
- sport before S4: `football`
- sport after S4 in failed smoke: `null`
- sport after S4 in replay: `football`
- competition before S4: `Faroe Islands - Premier League`
- competition after S4: `Faroe Islands - Premier League`
- participants before S4: `B68 Toftir`, `Argir`
- participants after S4 in replay: `B68 Toftir`, `Argir`
- market_family: `RESULT`
- market_type: `ml`
- pick / selection: `Argir`
- line: `null`
- odds_decimal: `2.45`
- odds_source / as_of: `api`, `UNAVAILABLE`
- model_probability: `null`
- ev_missing_reason: `MISSING_PROBABILITY`
- supporting_stats_count: `0`
- candidates_with_data flag: `false`
- why S3 had no data: `n_safety_markets=0`, no cache/DB match, `NO_STATS_DATA...`
- why S4 had `MISSING_PROBABILITY`: no ranked market / no model probability from `S3`
- why S5 saw `REJECTED_MISSING_SPORT`: anonymous `S4` row in failed smoke
- could become analytical if identity/probability/evidence existed: `yes`
- classifications: `IDENTITY_PROPAGATION_BUG`, `SPORT_MISSING_BUG`, `S3_STATS_JOIN_BUG`, `S4_PROBABILITY_MISSING`, `ANALYTICAL_ELIGIBLE_AFTER_FIX`

### 6. HB Torshavn vs Skala

- candidate_id: `football|HB Torshavn|Skala|2026-06-29`
- event_id / fixture_id: `6`
- sport before S4: `football`
- sport after S4 in failed smoke: `null`
- sport after S4 in replay: `football`
- competition before S4: `Faroe Islands - Premier League`
- competition after S4: `Faroe Islands - Premier League`
- participants before S4: `HB Torshavn`, `Skala`
- participants after S4 in replay: `HB Torshavn`, `Skala`
- market_family: `RESULT`
- market_type: `ml`
- pick / selection: `Skala`
- line: `null`
- odds_decimal: `4.5`
- odds_source / as_of: `api`, `UNAVAILABLE`
- model_probability: `null`
- ev_missing_reason: `MISSING_PROBABILITY`
- supporting_stats_count: `0`
- candidates_with_data flag: `false`
- why S3 had no data: `n_safety_markets=0`, no cache/DB match, `NO_STATS_DATA...`
- why S4 had `MISSING_PROBABILITY`: no ranked market / no model probability from `S3`
- why S5 saw `REJECTED_MISSING_SPORT`: anonymous `S4` row in failed smoke
- could become analytical if identity/probability/evidence existed: `yes`
- classifications: `IDENTITY_PROPAGATION_BUG`, `SPORT_MISSING_BUG`, `S3_STATS_JOIN_BUG`, `S4_PROBABILITY_MISSING`, `ANALYTICAL_ELIGIBLE_AFTER_FIX`

### 7. Vikingur vs Runavik

- candidate_id: `football|Vikingur|Runavik|2026-06-29`
- event_id / fixture_id: `7`
- sport before S4: `football`
- sport after S4 in failed smoke: `null`
- sport after S4 in replay: `football`
- competition before S4: `Faroe Islands - Premier League`
- competition after S4: `Faroe Islands - Premier League`
- participants before S4: `Vikingur`, `Runavik`
- participants after S4 in replay: `Vikingur`, `Runavik`
- market_family: `RESULT`
- market_type: `ml`
- pick / selection: `Vikingur`
- line: `null`
- odds_decimal: `2.7`
- odds_source / as_of: `api`, `UNAVAILABLE`
- model_probability: `null`
- ev_missing_reason: `MISSING_PROBABILITY`
- supporting_stats_count: `0`
- candidates_with_data flag: `false`
- why S3 had no data: `n_safety_markets=0`, no cache/DB match, `NO_STATS_DATA...`
- why S4 had `MISSING_PROBABILITY`: no ranked market / no model probability from `S3`
- why S5 saw `REJECTED_MISSING_SPORT`: anonymous `S4` row in failed smoke
- could become analytical if identity/probability/evidence existed: `yes`
- classifications: `IDENTITY_PROPAGATION_BUG`, `SPORT_MISSING_BUG`, `S3_STATS_JOIN_BUG`, `S4_PROBABILITY_MISSING`, `ANALYTICAL_ELIGIBLE_AFTER_FIX`

### 8. Kazma vs Al-Salmiya

- candidate_id: `football|Kazma|Al-Salmiya|2026-06-29`
- event_id / fixture_id: `8`
- sport before S4: `football`
- sport after S4 in failed smoke: `null`
- sport after S4 in replay: `football`
- competition before S4: `Kuwait - Premier League, Championship Group`
- competition after S4: `Kuwait - Premier League, Championship Group`
- participants before S4: `Kazma`, `Al-Salmiya`
- participants after S4 in replay: `Kazma`, `Al-Salmiya`
- market_family: `RESULT`
- market_type: `ml`
- pick / selection: `Al-Salmiya`
- line: `null`
- odds_decimal: `3.1`
- odds_source / as_of: `api`, `UNAVAILABLE`
- model_probability: `null`
- ev_missing_reason: `MISSING_PROBABILITY`
- supporting_stats_count: `0`
- candidates_with_data flag: `false`
- why S3 had no data: `n_safety_markets=0`, no cache/DB match, `NO_STATS_DATA...`
- why S4 had `MISSING_PROBABILITY`: no ranked market / no model probability from `S3`
- why S5 saw `REJECTED_MISSING_SPORT`: anonymous `S4` row in failed smoke
- could become analytical if identity/probability/evidence existed: `yes`
- classifications: `IDENTITY_PROPAGATION_BUG`, `SPORT_MISSING_BUG`, `S3_STATS_JOIN_BUG`, `S4_PROBABILITY_MISSING`, `ANALYTICAL_ELIGIBLE_AFTER_FIX`

## Verdict

- The failed smoke was blocked for the correct safety reason, but it exposed a real handoff gap: real shortlisted valuation candidates could not enter the analytical lane unless `S7` already had approved picks.
- The repair now preserves S3/S4 identity, records explicit probability/data gaps, writes `analytical_candidate_handoff.json`, and allows `S8` to emit a research-gap package without faking probability, stats, or operator quotes.
