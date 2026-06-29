# S1 Discovery Root Cause Reproduction and Classification

## 1. Context of Reproduction
- **Betting Day:** 2026-06-28
- **Run ID:** `TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A`
- **Mode:** `LIVE_SHADOW`
- **Execution Command:**
  ```fish
  env BET_PIPELINE_LIVE_ACK="I_UNDERSTAND_LIVE_PROVIDER_CALLS" \
    .venv/bin/python3 scripts/pipeline_steps/run_daily_pipeline.py \
    --date 2026-06-28 \
    --run-id TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A \
    --runtime-mode LIVE_SHADOW \
    --allow-live-network \
    --allow-write \
    --verbose
  ```

## 2. Diagnostics and Traceback
The original execution of S1 crashed inside `discover_events.py` during database schema migration:

```python
Traceback (most recent call last):
  File "/Users/mkoziol/projects/bet/scripts/discover_events.py", line 101, in <module>
    main()
  File "/Users/mkoziol/projects/bet/scripts/discover_events.py", line 44, in main
    result = discover_events(
             ^^^^^^^^^^^^^^^^
  File "/Users/mkoziol/projects/bet/src/bet/discovery/__init__.py", line 46, in discover_events
    init_db(conn)
  File "/Users/mkoziol/projects/bet/src/bet/db/schema.py", line 31, in init_db
    migrate(conn, current_version, SCHEMA_VERSION)
  File "/Users/mkoziol/projects/bet/src/bet/db/schema.py", line 240, in migrate
    _migrate_v20_football_history_engine(conn)
  ...
sqlite3.OperationalError: no such column: logical_identity
```

### Key Elements of the Failure:
- **DB Path Used:** `betting/data/betting.db` (canonical path)
- **Table Affected:** `fixture_capability_observation`
- **Column Missing:** `logical_identity`
- **Migration Code where crash occurred:** Executing `019_football_history_engine.sql` in `_migrate_v20_football_history_engine`. The SQL script tries to create unique and query indexes on `logical_identity` column, but that column does not exist on `fixture_capability_observation` because the table was originally created in `_migrate_v16_fixture_scoped_observations` WITHOUT this column, and subsequent migrations (v17-v19) skipped adding it for already-existing databases.
- **Silent Fallback Triggered:** Yes. Python exits with code `1` on uncaught exceptions. Since the wrapper script `s1_discover.py` treated exit code `1` (which is typically reserved for `PARTIAL` success) as a valid success code, it continued to execute `generate_market_matrix.py`. Because discovery didn't run, no fresh fixtures were loaded into the database, and `generate_market_matrix.py` silently loaded two stale, completed, competition-less database fixtures. This stale universe propagated all the way to S7, producing an incorrect `NO_BET_SESSION_VALID` verdict instead of an explicit block.

## 3. Classification
- **Primary Classification:** `DISCOVERY_MIGRATION_ORDER_BUG`
- **Secondary Classification:** `SILENT_FALLBACK_BUG` and `DISCOVERY_DB_SCHEMA_MISMATCH`
