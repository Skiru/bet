# Unified Live Analyst Event Context & Evidence Extraction Review

## Phase 1 — Answers to Core Questions

### 1. Why are event labels numeric/generic instead of actual match labels?
In previous runs, the unified analyst session script parsed candidates solely from intermediate final package files (which already had identity and evidence fields stripped/downgraded) because the rich raw day-run artifacts containing team and player names were never matched or merged.

### 2. Which artifact fields contain real team/player names?
In the S3 deep stats (`2026-06-30_s3_deep_stats.json`), the fields `home_team`, `away_team`, and the `participants` array contain complete participant names. In S4 valuation candidates and S2 shortlist files, the same fields contain them.

### 3. Which artifact fields contain competition/tournament/kickoff?
In S3 deep stats and S4 valuation files, the field `competition` holds the competition or tournament name (e.g. `ATP - Wimbledon, London, Great Britain` or `International - FIFA World Cup`), and `kickoff` or `scheduled_time` contains the ISO kickoff timestamp.

### 4. Which artifact fields contain market family, line, direction?
In S4 valuation candidates and S2 shortlist candidates, `market_family` contains the normalized family name, `line` or `point` contains the line, and `direction` or `recommendation_direction` contains the OVER/UNDER direction.

### 5. Which artifact fields contain usable quantitative/contextual evidence?
In S3 deep stats `analyses` list:
- `stats_a_summary` and `stats_b_summary` contain player/team specific performance series;
- `h2h_summary` contains head-to-head match stats;
- `ranking` contains team or player ranking profiles;
- `best_market` has `hit_rate_l10` for specific market families.

### 6. Why does evidence_summary fall back to generic text?
Because the `_evidence_items` function searched for keys like `supporting_evidence` directly on the parsed candidates. Since those keys were absent in raw events, and S3 stats summaries were never loaded, it defaulted to the fallback string.

### 7. Why is counter-evidence missing?
Because the candidates lacked any `counter_evidence` key, and since counter-evidence was never generated from the candidate's actual data gaps (like missing L10, surface data, lineup), it fell back to the generic UNKNOWN message.

### 8. Which sports currently have enough context for Top Recommendations?
Football (e.g. FIFA World Cup) and Tennis (e.g. Wimbledon ATP/WTA) have extremely rich deep stats, form summaries, and matchup histories inside the pipeline runs.

### 9. Why are Wimbledon and World Cup events not producing named recommendations?
Because player/team names were nested inside raw S3/S4 JSON files and were never extracted or mapped to the candidate event labels. This caused candidates to fail the Quality Gate C identity checks and get downgraded to watchlist-only.

### 10. What extraction changes will produce genuine Match Context + evidence?
Automatically loading raw run files (S2/S3/S4/matrix) from disk when running the session script, matching candidates to these files by ID or participants, and dynamically extracting names, competition, kickoff, stats, and gaps.

---

## Blocker Classification & Status

- **EVENT_IDENTITY_FIELD_MAPPING_MISSING**: **PASS** (Resolved by parsing `home_team`, `away_team`, `player_one`, `player_two` using aliases)
- **PARTICIPANTS_FIELD_MAPPING_MISSING**: **PASS** (Resolved by parsing `participants` / `competitors` arrays)
- **COMPETITION_FIELD_MAPPING_MISSING**: **PASS** (Resolved by parsing `competition` / `league` / `tournament` aliases)
- **KICKOFF_FIELD_MAPPING_MISSING**: **PASS** (Resolved by parsing `kickoff` / `start_time` / `scheduled_time` / `commence_time`)
- **MARKET_FIELD_MAPPING_MISSING**: **PASS** (Resolved by checking `market_family` / `market_type` aliases)
- **EVIDENCE_FIELD_MAPPING_MISSING**: **PASS** (Resolved by extracting S3 `stats_a_summary`, `stats_b_summary`, `h2h_summary`, and `hit_rate_l10`)
- **COUNTER_EVIDENCE_GENERATION_MISSING**: **PASS** (Resolved by generating risks dynamically from L10/H2H/lineup data gaps)
- **SPORT_SPECIFIC_CONTEXT_EXTRACTION_MISSING**: **PASS** (Resolved by adding custom football and tennis-specific contextual reasons)
- **SOURCE_ARTIFACT_MISSING**: **PASS** (Resolved by recursively loading all JSON files under `reports/pipeline_runs/`)
- **TRUE_INSUFFICIENT_DATA**: **PASS** (Empty/placeholder candidates are correctly kept in watchlist only)
