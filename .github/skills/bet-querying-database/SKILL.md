# Querying the Betting Database

## Overview
The betting pipeline uses SQLite at `betting/data/betting.db` with 28 tables across 6 domains. All access MUST use `from bet.db.connection import get_db` — NEVER raw `sqlite3.connect()`.

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

## Anti-Patterns
- ❌ NEVER use `sqlite3.connect()` directly
- ❌ NEVER use string formatting for SQL values (`f"WHERE name = '{name}'"`)
- ❌ NEVER assume tables exist — use `CREATE TABLE IF NOT EXISTS` or check first
- ❌ NEVER ignore `conn.commit()` — `get_db()` context manager handles this
- ✅ ALWAYS use parameterized queries with `?` placeholders
- ✅ ALWAYS use repository classes when available
- ✅ ALWAYS report specific row counts and metrics
