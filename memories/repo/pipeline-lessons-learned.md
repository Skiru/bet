# Pipeline Lessons Learned

## 2026-05-11: Four Critical Bugs Found

### Bug Chain: Fixture Kickoff → S3 DB Write → League Profiles
- **Root cause**: `discover_fixtures.py` wrote `kickoff=event_time` (just `"20:00"`) instead of `"{date}T{event_time}"` when `event_date` was empty
- **Impact**: `_resolve_fixture_id()` extracted `"20:00"` as date → no match → `save_analysis_results_to_db()` silently skipped 181/200 records → only 19 saved
- **League profiles**: Query joins `fixtures → match_stats` — broken fixtures broke the join → 0 profiles built
- **Fix**: `discover_fixtures.py` line 140: `kickoff=event_date or (f"{date}T{event_time}" if event_time else "")`
- **Fix**: `db_data_loader.py`: Added `_create_minimal_fixture()` fallback + warning logs instead of silent `continue`

### Dead API Sources
- `balldontlie` (100% fail), `api-tennis` (100% fail), `thesportsdb` (97.8% fail) wasted time in fallback chains
- Disabled in `fetch_api_stats.py` FALLBACK_CHAINS
- **Lesson**: Need automated source health monitoring that disables sources above a failure threshold

### Silent Data Loss Pattern
- `save_analysis_results_to_db()` and `save_gate_results_to_db()` had `if not fixture_id: continue` — no log, no counter
- 181 records silently dropped per run
- **Lesson**: NEVER use bare `continue` in data persistence loops. Always log + count skips.

## Methodology Gaps Identified (2026-05-11)
1. No fixture kickoff format validation after ingestion
2. No source health auto-disable mechanism
3. No DB write count verification (input vs saved)
4. Missing `pipeline-lessons-learned.md` (this file!) was referenced in STEP 0 but didn't exist
