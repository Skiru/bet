---
name: bet-querying-database
description: "Database access patterns for the betting pipeline — connection via get_db(), repository classes, key queries for all pipeline steps (scan, enrichment, analysis, gate, settlement), table schemas across 6 domains, and data quality scoring. Use when querying betting.db for pipeline data, gap analysis, or performance tracking."
user-invokable: false
---

# Querying the Betting Database

SQLite at `betting/data/betting.db` — 28 tables, 6 domains. Access: `from bet.db.connection import get_db` — NEVER raw `sqlite3.connect()`.

## Connection Pattern
```python
from bet.db.connection import get_db
with get_db() as conn:
    rows = conn.execute("SELECT * FROM teams WHERE sport_id = ?", (sport_id,)).fetchall()
    # conn auto-commits on clean exit, rolls back on exception
```

## Repository Classes (preferred over raw SQL)
All in `bet.db.repositories`:
- `SportRepo` — `get_by_name(name)`, `get_all()`, `seed_defaults()`
- `TeamRepo` — `find_or_create(name, sport_id)`, `resolve(name, sport_id)`, `update_aliases(team_id, aliases)`
- `CompetitionRepo` — `find_or_create(name, sport_id)`, `get_by_name(name, sport_id)`
- `FixtureRepo` — `find_or_create(home_id, away_id, kickoff, sport_id)`, `get_by_date(date)`
- `StatsRepo` — `save_team_form(team_form)`, `get_team_form(team_id, stat_key)`, `get_team_forms(team_id)`
- `MatchStatsRepo` — `save(fixture_id, team_id, stat_key, value, source)`
- `OddsRepo` — `save(fixture_id, bookmaker, market, selection, odds)`, `get_latest(fixture_id, market)`
- `PipelineRepo` — `start_step(date, step)`, `complete_step(date, step, stats)`, `get_step_status(date, step)`
- `ScanResultRepo` — `save(scan_result)`, `get_by_date(date)`
- `SourceHealthRepo` — `record_success(source, ms)`, `record_failure(source, reason)`, `get_all()`
- `GateResultRepo` — `save(gate_result)`, `get_by_date(date)`
- `AnalysisResultRepo` — `save(result)`, `get_by_date(date)`, `get_by_fixture(fixture_id)`

## Key Queries for Pipeline Agents

### Data freshness check
```sql
SELECT MAX(updated_at) as latest FROM team_form;
SELECT MAX(fetched_at) as latest FROM scan_results WHERE betting_date = ?;
```

### Candidates missing data (gap analysis)
```sql
-- Fixtures without team_form for home team
SELECT f.id, t.name, s.name as sport
FROM fixtures f
JOIN teams t ON f.home_team_id = t.id
JOIN sports s ON f.sport_id = s.id
LEFT JOIN team_form tf ON tf.team_id = t.id
WHERE date(f.kickoff) = ? AND tf.id IS NULL;
```

### Sport distribution
```sql
SELECT s.name, COUNT(f.id) 
FROM fixtures f JOIN sports s ON f.sport_id = s.id 
WHERE date(f.kickoff) = ? 
GROUP BY s.name ORDER BY COUNT(f.id) DESC;
```

### Pipeline progress
```sql
SELECT step_name, status, started_at, completed_at, metrics_json
FROM pipeline_runs WHERE betting_date = ? ORDER BY started_at;
```

### Source reliability
```sql
SELECT source_name, total_requests, total_failures, 
       ROUND(total_failures*100.0/MAX(total_requests,1),1) as fail_pct
FROM source_health ORDER BY total_requests DESC;
```

## Data Quality Scoring
Each candidate should have a `data_quality_score` (0-10):
- **FULL (≥7)**: team_form L10+L5+H2H, league_profiles, odds, match_stats
- **PARTIAL (4-6)**: team_form L10 only, OR missing H2H, OR no odds
- **MINIMAL (<4)**: fixture only, no team_form, no stats

## Agent-Specific Queries

### For bet-statistician (S3 deep stats)
```sql
-- Load safety scores for a fixture
SELECT best_market_name, best_safety_score, ranking_json, three_way_check_json
FROM analysis_results WHERE fixture_id = ? AND betting_date = ?;

-- Load team form for safety calculation
SELECT stat_key, l10_values, l5_values, l10_avg, l5_avg, h2h_values, trend
FROM team_form WHERE team_id = ? AND sport_id = ?;

-- League baseline for deviation analysis
SELECT stat_key, avg_value, median_value, std_dev, sample_size
FROM league_profiles WHERE competition_id = ? AND season = ?;
```

### For bet-builder (S8 coupon construction)
```sql
-- Load gate-approved candidates
SELECT gr.*, f.home_team_id, f.away_team_id, f.kickoff,
       t1.name as home, t2.name as away, s.name as sport
FROM gate_results gr
JOIN fixtures f ON gr.fixture_id = f.id
JOIN teams t1 ON f.home_team_id = t1.id
JOIN teams t2 ON f.away_team_id = t2.id
JOIN sports s ON f.sport_id = s.id
WHERE gr.betting_date = ? AND gr.status IN ('STRONG','MODERATE')
ORDER BY gr.gate_score DESC;
```

### For bet-settler (settlement)
```sql
-- Pending bets to settle
SELECT b.*, c.coupon_id, c.stake_pln, f.score_home, f.score_away
FROM bets b
JOIN coupons c ON b.coupon_id = c.id
JOIN fixtures f ON b.fixture_id = f.id
WHERE c.status = 'pending' AND date(f.kickoff) = ?;

-- CLV calculation data
SELECT oh.odds as closing_odds, b.odds as placement_odds
FROM odds_history oh
JOIN bets b ON oh.fixture_id = b.fixture_id AND oh.market = b.market
WHERE oh.is_closing = 1 AND b.id = ?;
```

### For bet-enricher (data gap analysis)
```sql
-- Teams missing form data for today's fixtures
SELECT DISTINCT t.id, t.name, s.name as sport,
  (SELECT COUNT(*) FROM team_form tf WHERE tf.team_id = t.id) as form_count
FROM fixtures f
JOIN teams t ON t.id IN (f.home_team_id, f.away_team_id)
JOIN sports s ON f.sport_id = s.id
WHERE date(f.kickoff) = ?
AND NOT EXISTS (SELECT 1 FROM team_form tf WHERE tf.team_id = t.id)
ORDER BY s.name, t.name;
```

## Table Schema Reference (6 domains)

| Domain | Tables |
|--------|--------|
| **Core** | `sports`, `teams`, `competitions`, `fixtures`, `athletes` |
| **Stats** | `team_form`, `match_stats`, `league_profiles`, `standings`, `power_index` |
| **Analysis** | `analysis_results`, `analysis_raw_data`, `gate_results`, `decision_snapshots`, `decision_outcomes` |
| **Betting** | `coupons`, `bets`, `odds_history` |
| **Pipeline** | `pipeline_runs`, `scan_results`, `scan_run_stats`, `source_health` |
| **ESPN** | `espn_predictions`, `player_gamelogs`, `player_splits`, `team_ats_records`, `team_ou_records`, `team_rosters` |

## Anti-Patterns
- ❌ `sqlite3.connect()` directly — use `get_db()` context manager
- ❌ String formatting for SQL values — use `?` placeholders
- ❌ Assuming tables exist — check first
- ✅ Repository classes when available, raw SQL for complex joins
- ✅ Report specific row counts and metrics
