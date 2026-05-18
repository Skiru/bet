# Pipeline Data Flow Audit

Date: 2026-05-18
Scope: DB-first betting pipeline flow for S1, S2, S2.5, S3, S7, and S8, plus cross-cutting agent analysis surfaces and side-channel dependencies.

## Najwazniejsze wnioski

1. The pipeline is DB-first in its durable contracts, but one critical handoff remains file-based: `build_shortlist.py` writes `betting/data/{date}_s2_shortlist.json`, and `deep_stats_report.py` consumes that JSON.
2. The highest-severity data quality problem is confirmed corruption inside `team_form`: at least 282 football stat rows contain impossible per-match values, with the contamination entering through non-Flashscore enrichment paths that bypass validation.
3. Two important producer chains are outside the numbered S1-S8 flow slice documented here but are still hard dependencies for downstream quality: `odds_history` and `tipster_consensus`.
4. Agent analysis capability is strong because agents can read the same DB artifacts that scripts produce, but their verdict quality is only as good as the underlying data contracts and validation discipline.
5. There is a contract ambiguity between S7 and S8: the gathered context says S8 reads `APPROVED` gate rows only, yet also produces an extended pool. That is not self-consistent unless extended-pool inputs are sourced from additional statuses or another artifact.

## 1. Complete Pipeline Flow Diagram

```text
External event sources
  SofaScoreAdapter | OddsAPIAdapter | APIFootballAdapter
        |
        v
S1 discover_events.py
  - concurrent source collection
  - deduplication via DeduplicationEngine
  - identity resolution / lookup upserts
        |
        +--> DB: sports, competitions, teams
        +--> DB: fixtures, fixture_sources, scan_results
        +--> JSON: betting/data/{date}_s1_events.json
        |
        +--> Agent overlay: bet-scanner
              validates scan completeness, source health, coverage, duplicates

S2 data_enrichment_agent.py
  - reads discovered fixtures / teams needing enrichment
  - fallback chain: UnifiedAPIClient -> Flashscore -> ESPN -> Scores24
  - rate limit + circuit breaker + known-missing cache
        |
        +--> DB: team_form, injuries
        +--> JSON: betting/data/stats_cache/{sport}/{slug}.json
        +--> JSON: betting/data/stats_cache/{sport}/deep/{slug}.json
        |
        +--> Agent overlay: bet-enricher
              validates yield, stat ranges, stale gaps, fallback behavior

Side channel A (upstream but not expanded in this audit's numbered step list)
  -> DB: odds_history

S2.5 build_shortlist.py
  - reads fixtures + odds
  - applies data quality / competition / odds / verification scoring
        |
        +--> JSON: betting/data/{date}_s2_shortlist.json

Side channel B (upstream but not expanded in this audit's numbered step list)
  -> DB: tipster_picks, tipster_consensus

S3 deep_stats_report.py
  - reads shortlist JSON
  - reads DB-first stats: team_form, h2h_stats, injuries, standings, odds/tipster signals
  - cache fallback + inline enrichment when missing
  - computes data_quality_score and market safety rankings
        |
        +--> DB: analysis_results, analysis_raw_data
        +--> JSON: betting/data/{date}_s3_deep_stats.json
        |
        +--> Agent overlay: bet-statistician
              validates per-candidate data depth, market ranking, 3-way alignment

Logical analysis layers between S3 and S7
  - EV / drift / context / upset / red-flag reasoning
  - persisted mainly through S3 outputs and S7 decisions in this audit slice

S7 gate_checker.py
  - reads analysis outputs and supporting signals
  - runs 18-point gate + ghost fixture protection
        |
        +--> DB: gate_results
        +--> JSON: betting/data/{date}_s7_gate_results.json
        |
        +--> Agent overlay: bet-gatekeeper
              audits false rejections, phantom fixtures, gate consistency

S8 coupon_builder.py
  - reads gate outcomes
  - builds core portfolio, combo menu, and coupon artifacts
        |
        +--> DB: coupons, bets
        +--> MD: betting/coupons/{date}_vN_coupon.md
        |
        +--> Agent overlay: bet-portfolio
              validates correlation, stress, portfolio shape, staking logic

Post-pipeline learning loop
  - coupons / bets / outcomes feed settlement and future advisory learning
```

## 2. Per-Step Data Contracts

Legend:

| Label | Meaning |
|------|---------|
| Schema-confirmed | Table and columns were confirmed from the repository schema during this audit. |
| Context-confirmed | The step behavior was provided directly in the audit input. |
| Dependency gap | The artifact is a real dependency, but its producer step is outside the numbered slice documented here. |

### S1 - Event Discovery (`scripts/discover_events.py`)

#### Reads

| Contract type | Source | Exact table / payload contract | Purpose |
|---------------|--------|--------------------------------|---------|
| Context-confirmed | External adapters | SofaScoreAdapter, OddsAPIAdapter, APIFootballAdapter payloads | Raw event discovery inputs. |
| Schema-confirmed | `sports` | `id`, `name`, `tier`, `stat_keys` | Resolve or create sport identity. |
| Schema-confirmed | `competitions` | `id`, `sport_id`, `name`, `country`, `importance`, `season` | Resolve or create competition identity. |
| Schema-confirmed | `teams` | `id`, `sport_id`, `name`, `aliases`, `country`, `venue`, `style_tags` | Resolve or create team identity before fixture insert. |
| Schema-confirmed | `fixtures` | `id`, `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status`, `score_home`, `score_away`, `source`, `fetched_at` | Deduplication against already-known fixtures. |

#### Writes

| Contract type | Sink | Exact table / artifact contract | Notes |
|---------------|------|---------------------------------|-------|
| Schema-confirmed | `sports` | `name`, `tier`, `stat_keys` | Auto-created if a new sport identity appears. |
| Schema-confirmed | `competitions` | `sport_id`, `name`, `country`, `importance`, `season` | Auto-created if a new competition appears. |
| Schema-confirmed | `teams` | `sport_id`, `name`, `aliases`, `country`, `venue`, `style_tags` | Auto-created if a new team appears. |
| Schema-confirmed | `fixtures` | `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status`, `score_home`, `score_away`, `source`, `fetched_at` | Canonical discovered fixture row. |
| Schema-confirmed | `fixture_sources` | `fixture_id`, `source`, `external_id`, `confidence`, `raw_data`, `fetched_at` | Multi-source identity cross-reference. |
| Schema-confirmed | `scan_results` | `betting_date`, `sport`, `source_domain`, `event_key`, `home_team`, `away_team`, `competition`, `kickoff`, `raw_data`, `scan_timestamp` | Per-event scan metadata and raw evidence. |
| Context-confirmed | JSON | `betting/data/{date}_s1_events.json` | Backward-compatible event dump. |

### S2 - Enrichment (`scripts/data_enrichment_agent.py`)

#### Reads

| Contract type | Source | Exact table / artifact contract | Purpose |
|---------------|--------|--------------------------------|---------|
| Schema-confirmed | `fixtures` | `id`, `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status`, `score_home`, `score_away`, `source`, `fetched_at` | Identify fixtures and teams that still need enrichment. |
| Schema-confirmed | `teams` | `id`, `sport_id`, `name`, `aliases`, `country`, `venue`, `style_tags` | Team identity and slug mapping. |
| Schema-confirmed | `sports` | `id`, `name`, `tier`, `stat_keys` | Sport-specific stat-key handling. |
| Schema-confirmed | `team_form` | `id`, `team_id`, `sport_id`, `stat_key`, `l10_values`, `l5_values`, `l10_avg`, `l5_avg`, `h2h_values`, `h2h_opponent_id`, `trend`, `updated_at`, `source` | Upsert baseline and freshness check for already-known team stats. |
| Schema-confirmed | `source_health` | `id`, `source_name`, `last_success`, `last_failure`, `consecutive_failures`, `total_requests`, `total_failures`, `avg_response_ms` | Circuit-breaker and source reliability tracking. |
| Context-confirmed | External chain | UnifiedAPIClient -> Flashscore -> ESPN -> Scores24 | Ordered fallback enrichment chain. |

#### Writes

| Contract type | Sink | Exact table / artifact contract | Notes |
|---------------|------|---------------------------------|-------|
| Schema-confirmed | `team_form` | `team_id`, `sport_id`, `stat_key`, `l10_values`, `l5_values`, `l10_avg`, `l5_avg`, `h2h_values`, `h2h_opponent_id`, `trend`, `updated_at`, `source` | Core per-team aggregate stat store; this is the table currently contaminated by garbage values. |
| Schema-confirmed | `injuries` | `team_id`, `athlete_name`, `sport`, `status`, `injury_type`, `expected_return`, `source`, `fetched_at` | ESPN-derived injury facts. |
| Context-confirmed | JSON | `betting/data/stats_cache/{sport}/{slug}.json` | Backward-compatible stats cache. |
| Context-confirmed | JSON | `betting/data/stats_cache/{sport}/deep/{slug}.json` | Deep extraction payload cache. |

### S2.5 - Build Shortlist (`scripts/build_shortlist.py`)

#### Reads

| Contract type | Source | Exact table / artifact contract | Purpose |
|---------------|--------|--------------------------------|---------|
| Schema-confirmed | `fixtures` | `id`, `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status`, `score_home`, `score_away`, `source`, `fetched_at` | Candidate fixture universe loaded via `load_fixtures_from_db()`. |
| Schema-confirmed | `sports` | `id`, `name`, `tier`, `stat_keys` | Sport metadata for ranking and display. |
| Schema-confirmed | `competitions` | `id`, `sport_id`, `name`, `country`, `importance`, `season` | Competition importance and protected-league logic. |
| Schema-confirmed | `teams` | `id`, `sport_id`, `name`, `aliases`, `country`, `venue`, `style_tags` | Team names and identity joins. |
| Schema-confirmed | `odds_history` | `id`, `fixture_id`, `bookmaker`, `market`, `selection`, `odds`, `line`, `fetched_at`, `is_closing` | Odds attractiveness scoring via `load_odds_from_db()`. |
| Schema-confirmed | `fixture_sources` | `fixture_id`, `source`, `external_id`, `confidence`, `raw_data`, `fetched_at` | Secondary verification evidence for fixture identity. |
| Schema-confirmed | `scan_results` | `betting_date`, `sport`, `source_domain`, `event_key`, `home_team`, `away_team`, `competition`, `kickoff`, `raw_data`, `scan_timestamp` | Secondary verification evidence for scan completeness and fixture confidence. |

#### Writes

| Contract type | Sink | Exact table / artifact contract | Notes |
|---------------|------|---------------------------------|-------|
| Context-confirmed | JSON | `betting/data/{date}_s2_shortlist.json` | Ranked shortlist handoff to S3. No DB write was confirmed for the shortlist itself. |

### S3 - Deep Stats Report (`scripts/deep_stats_report.py`)

#### Reads

| Contract type | Source | Exact table / artifact contract | Purpose |
|---------------|--------|--------------------------------|---------|
| Context-confirmed | JSON | `betting/data/{date}_s2_shortlist.json` | Candidate list to analyze. |
| Schema-confirmed | `team_form` | `id`, `team_id`, `sport_id`, `stat_key`, `l10_values`, `l5_values`, `l10_avg`, `l5_avg`, `h2h_values`, `h2h_opponent_id`, `trend`, `updated_at`, `source` | L10, L5, trend, and stored H2H-side values. |
| Schema-confirmed | `h2h_stats` | `id`, `team1_id`, `team2_id`, `sport`, `stat_key`, `values_json`, `avg_value`, `match_count`, `source`, `updated_at` | Matchup-specific historical stat context. |
| Schema-confirmed | `injuries` | `id`, `team_id`, `athlete_name`, `sport`, `status`, `injury_type`, `expected_return`, `source`, `fetched_at` | Injury component of `data_quality_score`. |
| Schema-confirmed | `standings` | `id`, `competition_id`, `team_id`, `season`, `rank`, `wins`, `draws`, `losses`, `goals_for`, `goals_against`, `goal_diff`, `points`, `form`, `home_wins`, `home_draws`, `home_losses`, `away_wins`, `away_draws`, `away_losses`, `streak`, `source`, `updated_at` | Standings component of `data_quality_score`. |
| Schema-confirmed | `odds_history` | `id`, `fixture_id`, `bookmaker`, `market`, `selection`, `odds`, `line`, `fetched_at`, `is_closing` | Odds-source depth and price context. |
| Schema-confirmed | `tipster_consensus` | `id`, `betting_date`, `event`, `sport`, `competition`, `home_team`, `away_team`, `total_tipsters`, `consensus_market`, `consensus_direction`, `agreement_pct`, `statistical_picks`, `outcome_picks`, `has_reasoning`, `tipster_sources`, `confidence_adj`, `created_at` | Tipster and reasoning component of `data_quality_score` and 3-way checks. |
| Schema-confirmed | `fixtures` | `id`, `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status`, `score_home`, `score_away`, `source`, `fetched_at` | Fixture identity and event metadata. |
| Schema-confirmed | `competitions` | `id`, `sport_id`, `name`, `country`, `importance`, `season` | Competition context for ranking and reporting. |
| Context-confirmed | JSON fallback | `betting/data/stats_cache/{sport}/{slug}.json` and `betting/data/stats_cache/{sport}/deep/{slug}.json` | Cache fallback when DB data is absent. |
| Context-confirmed | Inline recovery | `data_enrichment_agent.enrich_team()` | Last-resort enrichment when no cache exists. |

#### Writes

| Contract type | Sink | Exact table / artifact contract | Notes |
|---------------|------|---------------------------------|-------|
| Schema-confirmed | `analysis_results` | `fixture_id`, `betting_date`, `has_data`, `best_market_name`, `best_market_line`, `best_market_direction`, `best_safety_score`, `markets_evaluated`, `ranking_json`, `three_way_check_json`, `warnings_json`, `stats_summary_json`, `source`, `created_at` | Primary S3 summary row per fixture/day. |
| Schema-confirmed | `analysis_raw_data` | `fixture_id`, `betting_date`, `team_a_l10_json`, `team_b_l10_json`, `h2h_meetings_json`, `per_market_details_json`, `safety_input_json`, `created_at` | Detailed audit trail for per-team and per-market inputs. |
| Context-confirmed | JSON | `betting/data/{date}_s3_deep_stats.json` | Human-readable / backward-compatible S3 output. |

### S7 - Gate Checker (`scripts/gate_checker.py`)

#### Reads

| Contract type | Source | Exact table / artifact contract | Purpose |
|---------------|--------|--------------------------------|---------|
| Schema-confirmed | `analysis_results` | `id`, `fixture_id`, `betting_date`, `has_data`, `best_market_name`, `best_market_line`, `best_market_direction`, `best_safety_score`, `markets_evaluated`, `ranking_json`, `three_way_check_json`, `warnings_json`, `stats_summary_json`, `source`, `created_at` | Primary S3 decision input. |
| Schema-confirmed | `analysis_raw_data` | `id`, `fixture_id`, `betting_date`, `team_a_l10_json`, `team_b_l10_json`, `h2h_meetings_json`, `per_market_details_json`, `safety_input_json`, `created_at` | Supporting evidence for gate decisions and diagnostics. |
| Schema-confirmed | `fixtures` | `id`, `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status`, `score_home`, `score_away`, `source`, `fetched_at` | Ghost-fixture filter and event identity checks. |
| Schema-confirmed | `fixture_sources` | `fixture_id`, `source`, `external_id`, `confidence`, `raw_data`, `fetched_at` | Multi-source fixture confirmation for ghost filtering. |
| Schema-confirmed | `odds_history` | `id`, `fixture_id`, `bookmaker`, `market`, `selection`, `odds`, `line`, `fetched_at`, `is_closing` | EV and drift checks. |
| Schema-confirmed | `tipster_consensus` | `id`, `betting_date`, `event`, `sport`, `competition`, `home_team`, `away_team`, `total_tipsters`, `consensus_market`, `consensus_direction`, `agreement_pct`, `statistical_picks`, `outcome_picks`, `has_reasoning`, `tipster_sources`, `confidence_adj`, `created_at` | Tipster and reasoning gate components. |

#### Writes

| Contract type | Sink | Exact table / artifact contract | Notes |
|---------------|------|---------------------------------|-------|
| Schema-confirmed | `gate_results` | `fixture_id`, `betting_date`, `status`, `gate_score`, `gate_details_json`, `best_market_name`, `best_market_line`, `best_market_direction`, `best_safety_score`, `ev`, `risk_tier`, `rejection_reasons_json`, `source`, `created_at` | Final gate output per fixture/day. |
| Context-confirmed | JSON | `betting/data/{date}_s7_gate_results.json` | Human-readable / backward-compatible S7 output. |

### S8 - Coupon Builder (`scripts/coupon_builder.py`)

#### Reads

| Contract type | Source | Exact table / artifact contract | Purpose |
|---------------|--------|--------------------------------|---------|
| Schema-confirmed | `gate_results` | `id`, `fixture_id`, `betting_date`, `status`, `gate_score`, `gate_details_json`, `best_market_name`, `best_market_line`, `best_market_direction`, `best_safety_score`, `ev`, `risk_tier`, `rejection_reasons_json`, `source`, `created_at` | Coupon selection base. Gathered context says this is limited to `APPROVED` rows. |
| Schema-confirmed | `fixtures` | `id`, `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status`, `score_home`, `score_away`, `source`, `fetched_at` | Event naming and kickoff ordering. |
| Schema-confirmed | `teams` | `id`, `sport_id`, `name`, `aliases`, `country`, `venue`, `style_tags` | Human-readable coupon leg formatting. |
| Schema-confirmed | `competitions` | `id`, `sport_id`, `name`, `country`, `importance`, `season` | Competition naming in coupon output. |
| Schema-confirmed | `coupons` | `id`, `coupon_id`, `coupon_type`, `total_odds`, `stake_pln`, `status`, `pnl_pln`, `placed_at`, `settled_at`, `betclic_ref`, `version`, `created_at` | Versioning and supersession awareness. |

#### Writes

| Contract type | Sink | Exact table / artifact contract | Notes |
|---------------|------|---------------------------------|-------|
| Schema-confirmed | `coupons` | `coupon_id`, `coupon_type`, `total_odds`, `stake_pln`, `status`, `pnl_pln`, `placed_at`, `settled_at`, `betclic_ref`, `version`, `created_at` | One coupon row per generated coupon artifact. |
| Schema-confirmed | `bets` | `coupon_id`, `fixture_id`, `sport`, `event_name`, `market`, `selection`, `odds`, `min_odds`, `safety_score`, `hit_rate`, `status`, `pnl_pln`, `settled_at`, `market_pl`, `navigation_hint`, `stats_detail` | One row per coupon leg / pick. |
| Context-confirmed | Markdown | `betting/coupons/{date}_vN_coupon.md` | Versioned user-facing coupon output. |

## 3. Data Quality Audit Results

### 3.1 Current volume snapshot

| Artifact | Current volume | Notes |
|----------|----------------|-------|
| `scan_results` | football=1786, basketball=518, tennis=389, volleyball=50, hockey=34 | Today only. |
| `team_form` | 207876 total rows, 434 updated today | Largest core stats table in this slice. |
| `h2h_stats` | 47234 total rows, 11 updated today | Sparse daily updates relative to total history. |
| `analysis_results` | 360 today | S3 output count. |
| `gate_results` | 197 APPROVED, 3 REJECTED today | 200 gated rows total today. |
| `tipster_consensus` | football=583, basketball=99, hockey=94, tennis=88 | Cross-cutting reasoning input. |

### 3.2 Confirmed out-of-range `team_form` contamination

| Sport | `stat_key` | Expected per-match range | Observed max | Garbage rows | Severity |
|-------|------------|--------------------------|--------------|--------------|----------|
| football | `corners` | 0-20 | 989 | 38 | Critical |
| football | `fouls` | 0-40 | 989 | 38 | Critical |
| football | `goals` | 0-8 | 211 | 146 | Critical |
| football | `possession` | 0-100 | 989 | 10 | Critical |
| football | `red_cards` | 0-5 | 989 | 50 | Critical |

Confirmed anomaly count in the current audit slice: at least 282 corrupted `team_form` rows.

### 3.3 Concrete examples

| Team example | `stat_key` | Stored value pattern | Why it is invalid |
|--------------|------------|----------------------|-------------------|
| Toronto II | `corners` | `[59.0]` | Impossible as an L10 per-match corners series; looks like a season aggregate. |
| NY RB II | `corners` | `[59.0]` | Same impossible singleton value as another unrelated team, which strongly suggests source-level aggregate leakage. |
| Inter Miami II | `corners` | `[59.0]` | Same repeated bad payload pattern, inconsistent with real match-by-match variation. |

### 3.4 Downstream impact

| Downstream step | Impact of bad `team_form` rows | Risk |
|-----------------|-------------------------------|------|
| S3 `deep_stats_report.py` | Corrupt `l10_values`, `l5_values`, `l10_avg`, and `l5_avg` distort `build_safety_input()` and `rank_markets()` outputs. | False confidence, wrong market ranking, bad 3-way alignment. |
| S7 `gate_checker.py` | Gate decisions inherit contaminated `best_safety_score`, `stats_summary_json`, and possibly EV inputs. | False approvals and false rejections. |
| S8 `coupon_builder.py` | Coupon construction operates on already-approved rows shaped by polluted analytics. | Portfolio quality degradation and hidden exposure to bad picks. |

### 3.5 Additional reconciliation observations

| Observation | Why it matters |
|-------------|----------------|
| `analysis_results` today = 360, while `gate_results` today = 200 | Either the S3->S7 chain was partial, multiple runs are coexisting, or not all analyzed fixtures were gated. This should be reconciled by run/date/version when auditing completeness. |
| `team_form` daily updates = 434, but `h2h_stats` daily updates = 11 | The matchup layer is much thinner than the team-form layer, so H2H-driven safety components may often be weak or stale relative to L10/L5 inputs. |
| `build_shortlist.py` depends on `odds_history`, but no odds-producing step appears in the numbered flow slice | This is a real data dependency even though it is outside the mapped S1-S8 core list. |

## 4. Root Cause Analysis of Garbage Data

The corruption pattern is consistent with a validation asymmetry inside enrichment.

| Root cause element | Evidence | Consequence |
|--------------------|----------|-------------|
| Validation exists only on one enrichment path | `flashscore_enricher.py` applies `_validate_stat_values()`, but non-Flashscore paths do not enforce the same range guard. | Invalid stats can bypass validation and still reach `team_form`. |
| Non-Flashscore paths can persist season totals as per-match values | Example singleton arrays like `[59.0]` for corners and maxima such as 989 or 211 are far above realistic per-match bounds. | The table stores aggregates in a structure meant for L10/L5 per-match series. |
| `_save_to_db()` lacks a final write-time guard | The user-provided audit already identified that non-Flashscore paths bypass validation before DB writes. | Any malformed or semantically wrong payload can become durable DB state. |
| `team_form` stores JSON text without DB-level stat-range constraints | `l10_values`, `l5_values`, and `h2h_values` are free-form JSON text columns. | SQLite cannot stop impossible stat arrays; application validation is the only effective control. |
| Repeated identical garbage across unrelated teams | Toronto II, NY RB II, and Inter Miami II all show the same invalid `[59.0]` corners payload. | This points to source-to-model mapping leakage, not isolated bad team data. |

Root-cause summary: the enrichment system mixes validated and non-validated source paths, and the final DB write layer does not enforce sport/stat sanity bounds. Once aggregate or season-level numbers are misinterpreted as per-match series, they propagate into S3 rankings and every downstream decision layer.

## 5. Recommended Fixes (Prioritized)

| Priority | Recommendation | Why now | Expected outcome |
|----------|----------------|---------|------------------|
| P0 | Add sport/stat range validation inside `data_enrichment_agent._save_to_db()` as a mandatory last-resort guard for every source path. | This closes the exact hole that allowed bad non-Flashscore payloads through. | No impossible values are persisted regardless of upstream source behavior. |
| P0 | Quarantine or delete already-corrupted `team_form` rows and re-enrich affected teams before the next serious S3/S7 run. | Current DB state is already polluted; new validation alone does not repair downstream analytics. | S3 and S7 stop inheriting known-bad L10/L5 inputs. |
| P1 | Normalize source semantics before persistence: if a source provides season totals, do not map them into `l10_values` or `l5_values` without an explicit per-match transformation rule. | The core issue is not only range but also semantic mismatch. | `team_form` remains a true per-match aggregate store instead of a generic bucket for any number. |
| P1 | Add enrichment audit counters to agent summaries and/or DB logging: rejected rows by `sport`, `stat_key`, and `source`; fallback-source usage; known-missing hits. | The pipeline currently surfaces outcomes more strongly than data hygiene. | Agents can detect contamination immediately instead of after it has spread. |
| P1 | Add a pre-S3 blocking data-quality audit over `team_form` for impossible ranges. | S3 is the first heavy consumer of corrupted stats. | The pipeline fails fast before contaminated safety scores are written. |
| P2 | Reconcile the S7->S8 contract for extended-pool generation. If S8 truly reads only `APPROVED` rows, extended-pool logic needs another source or another status set. | The present contract description is internally inconsistent. | Coupon generation rules become auditable and easier to reason about. |
| P2 | Document the upstream producers for `odds_history` and `tipster_consensus` beside the core numbered stages. | These are hard dependencies but appear as hidden side channels in the current flow. | The audit surface becomes complete for operators and future debugging. |

## 6. Agent Analysis Capabilities Matrix

All specialist agents are DB-capable. Their common access pattern is `from bet.db.connection import get_db` plus repository classes such as `SportRepo`, `TeamRepo`, `StatsRepo`, `FixtureRepo`, `OddsRepo`, `PipelineRepo`, `AnalysisResultRepo`, `GateResultRepo`, and `CouponRepo`.

| Agent | Stage | Primary tables / artifacts it can access | How it uses the data | Typical analytical verdicts |
|------|-------|-------------------------------------------|----------------------|-----------------------------|
| `bet-scanner` | S1 | `sports`, `competitions`, `teams`, `fixtures`, `fixture_sources`, `scan_results`, `source_health` | Checks scan completeness, protected league coverage, duplicate fixture identity, and source reliability. | Scan complete / partial / failed; missing tournaments; suspect duplicates; source outage notes. |
| `bet-enricher` | S2 | `fixtures`, `teams`, `team_form`, `injuries`, JSON stats caches, `source_health` | Measures enrichment yield, stale-team coverage, fallback-source usage, impossible ranges, and missing-data hotspots. | Enrichment healthy / degraded; stat-range anomalies; source-chain bottlenecks; re-enrichment targets. |
| `bet-statistician` | S3 | `team_form`, `h2h_stats`, `injuries`, `standings`, `odds_history`, `tipster_consensus`, `analysis_results`, `analysis_raw_data` | Performs per-candidate market ranking, L10/L5/H2H validation, 3-way alignment, and data-depth classification. | Best market, safety confidence, data-quality score, warnings, bear cases, alternate markets. |
| `bet-gatekeeper` | S7 | `analysis_results`, `analysis_raw_data`, `fixtures`, `fixture_sources`, `odds_history`, `tipster_consensus`, `gate_results` | Audits the 18-point gate, ghost-fixture filtering, EV/drift validity, and false-rejection risk. | Approve / reject rationale, gate score confidence, phantom-fixture alerts, borderline picks for review. |
| `bet-portfolio` | S8 | `gate_results`, `fixtures`, `teams`, `competitions`, `coupons`, `bets` | Builds unique-event coupons, checks correlation and stress, validates coupon shape, and applies Kelly 1/4 staking logic. | Core portfolio, combo menu, concentration warnings, versioned coupon set, high-risk extras. |

### Agent-specific strengths by data type

| Data type | Best-positioned agent | Why |
|-----------|-----------------------|-----|
| Scan completeness and source outages | `bet-scanner` | It sees discovery metadata closest to the source adapters and identity joins. |
| Range anomalies and enrichment contamination | `bet-enricher` | It operates nearest to `team_form` writes and source fallback behavior. |
| Market ranking integrity | `bet-statistician` | It consumes raw stat aggregates, H2H, tipster, odds, and safety inputs directly. |
| False approvals / false rejections | `bet-gatekeeper` | It can compare gate decisions against full S3 evidence and fixture identity signals. |
| Portfolio concentration and coupon-level risk | `bet-portfolio` | It is the first layer that sees pick combinations, reused logic, and stake distribution. |

## 7. Inter-Script Data Dependency Map

| Producer | Artifact / contract | Consumer | Dependency type | Failure mode if broken |
|----------|---------------------|----------|-----------------|------------------------|
| S1 `discover_events.py` | `sports`, `competitions`, `teams`, `fixtures`, `fixture_sources`, `scan_results` | S2 `data_enrichment_agent.py` | Hard DB dependency | No canonical fixture/team universe for enrichment; duplicate or phantom identities propagate. |
| S1 `discover_events.py` | `fixtures`, `teams`, `competitions`, `sports` | S2.5 `build_shortlist.py` | Hard DB dependency | Shortlist scoring cannot resolve events or competition context. |
| Upstream odds producer outside this slice | `odds_history` | S2.5 `build_shortlist.py`, S3 `deep_stats_report.py`, S7 `gate_checker.py` | Hard side-channel dependency | Odds-based shortlist ranking, EV, and drift logic degrade or vanish. |
| S2 `data_enrichment_agent.py` | `team_form`, `injuries`, JSON stats cache | S3 `deep_stats_report.py` | Hard DB dependency with JSON fallback | S3 falls back to cache or inline enrichment; if both fail, analysis quality drops sharply. |
| Upstream tipster producer outside this slice | `tipster_picks`, `tipster_consensus` | S3 `deep_stats_report.py`, S7 `gate_checker.py` | Advisory side-channel dependency | Tipster reasoning and the tipster component of `data_quality_score` disappear. |
| S2.5 `build_shortlist.py` | `betting/data/{date}_s2_shortlist.json` | S3 `deep_stats_report.py` | Hard file dependency | S3 has no candidate list even if DB discovery/enrichment succeeded. |
| S3 `deep_stats_report.py` | `analysis_results`, `analysis_raw_data` | S7 `gate_checker.py` | Hard DB dependency | Gate decisions cannot be derived or audited. |
| S7 `gate_checker.py` | `gate_results` | S8 `coupon_builder.py` | Hard DB dependency | Coupon construction cannot separate approved from failed candidates. |
| S8 `coupon_builder.py` | `coupons`, `bets`, coupon markdown | Settlement / learning loop | Downstream history dependency | Advisory learning and bankroll tracking lose ground-truth bet history. |

### Contract gaps worth documenting explicitly

| Gap | Why it matters |
|-----|----------------|
| `build_shortlist.py` writes JSON only | This is the main non-DB handoff in an otherwise DB-first architecture and is a clear single-point file dependency. |
| `odds_history` producer is not shown in the core stage list | Operators can misread odds as ambient state rather than a required upstream feed. |
| `tipster_consensus` producer is not shown in the core stage list | S3 and S7 can appear to have missing tipster data even when the real issue is an omitted producer step. |
| S8 extended-pool contract is ambiguous | If only `APPROVED` rows are read, extended-pool generation from failed-but-positive-EV picks is not explainable from the documented flow. |

## Final audit summary

The pipeline's durable backbone is coherent: discovery populates canonical fixture identity, enrichment fills team-level stat stores, shortlist ranking bridges into deep analysis, gating turns analysis into decisions, and coupon building materializes bet artifacts. The main operational weakness is not the overall architecture but data-contract hygiene at the enrichment write boundary. Once bad values enter `team_form`, they contaminate S3 rankings, S7 gate outcomes, and S8 portfolio construction.

The most important remediation is therefore immediate and narrow: enforce stat-range validation in the final enrichment DB write path, clean the already-corrupted rows, and expose quality counters prominently enough that specialist agents can stop the pipeline before contaminated analytics become betting decisions.