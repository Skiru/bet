# Plan: close the loop — persist real outcomes back into the DB

Status: **draft, not implemented**. Written 2026-09-07 after confirming current
state: DISCOVER/ENRICH/ANALYZE already persist predictions to
`betting/data/betting.db` (`fixtures`, `fixture_sources`, `analysis_raw_data`,
`analysis_results` via [persistence.py](../src/bet/simple_stats/persistence.py)),
and `scripts/simple/backtest_slate.py` already knows how to fetch real
outcomes and settle rows against them — but only when run by hand, and its
output never goes back into the DB. This plan wires those two together.

## What exists today (verified, not assumed)

- `runs/{date}/{date}_event_list.json` / `_event_dossiers.json` / etc. — frozen
  per-day snapshots. Re-running a date with `--start-at` reads these instead
  of re-calling bzzoiro.
- `betting/data/betting.db` — SQLite. `run_discover.py`, `run_enrich.py`,
  `run_analyze.py` each call `persist_pipeline_run` / `persist_stats_sheet`
  unconditionally (not behind a flag). `fixtures.score_home` /
  `fixtures.score_away` columns exist in
  [models.py:72-73](../src/bet/db/models.py) but nothing ever writes them.
- `scripts/simple/backtest_slate.py` — fetches real outcomes from bzzoiro
  (`/events/{id}/stats/`, `/events/{id}/`) and ESPN (tennis), caches them in
  `runs/_backtest_actuals.json` (pure JSON, no DB), and settles each coupon
  row via `bet.simple_stats.settle.settle_row` into an in-memory report
  written to `--output` if given. Nothing reads `--output` back into
  `betting.db`. Nothing calls this script automatically.
- `analysis_results.ranking_json` (one row per fixture, list of market/line/
  direction dicts) has no settlement columns — no `outcome`, no `actual_value`,
  no `hit`.

## Gap

1. No automatic trigger: a day's outcomes are only ever settled if someone
   runs `backtest_slate.py --date X --recorded` by hand.
2. Settlement output is JSON-only. It never rejoins `betting.db`, so there is
   no SQL query of the form "which of yesterday's `analysis_results` rows
   actually won" — you have to open the backtest report file and cross-
   reference by hand.
3. `fixtures.score_home/away` sit unused, so even the final score isn't on the
   fixture row itself.

## Proposed changes

### 1. Schema: one new table, no changes to existing ones

```sql
CREATE TABLE row_settlements (
    id INTEGER PRIMARY KEY,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    market TEXT NOT NULL,
    line REAL,
    direction TEXT NOT NULL,
    team_name TEXT,           -- NULL for match-total rows
    player_id TEXT,           -- NULL for non-prop rows
    outcome TEXT NOT NULL,    -- WON | LOST | PUSH | NO_DATA
    actual_value REAL,        -- what the metric actually was, NULL for NO_DATA
    p_low REAL,               -- the row's claimed lower bound, carried for calibration queries
    settlement_source TEXT NOT NULL,  -- 'recorded' | 'rebuilt'
    backtest_run_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date, market, line, direction, team_name, player_id, settlement_source)
);
```

The natural key mirrors the row identity `backtest_slate.py` already uses
internally to match a coupon row to a dossier — no new identity scheme to
invent, just persist the one that exists. `settlement_source` is kept because
RECORDED and REBUILT answer different questions (was the shipped sheet right,
vs. is today's code right) and must never be averaged together.

Also: start writing `fixtures.score_home` / `score_away` / `status='finished'`
when `backtest_slate.py` fetches a final score, since the columns already
exist and cost nothing to populate.

### 2. `persistence.py`: one new function

`persist_row_settlements(settlements: list[RowSettlement], conn) -> None` —
same upsert-on-conflict pattern as `_persist_fixture_sources`. Takes the
already-computed settlement rows (whatever `backtest_slate.py` builds today
for its JSON report) and writes them via the natural key above, so a re-run
after a code change updates rows in place instead of duplicating them.

### 3. `backtest_slate.py`: add `--persist-db` (or make it the default alongside `--output`)

After the existing settle loop produces its report, call
`persist_row_settlements` inside the same `get_db(...)` connection pattern the
other `run_*.py` scripts already use. No change to the settle logic itself
(`settle.py` stays pure — no network, no DB, unchanged per its own docstring).
Reuses `runs/_backtest_actuals.json` exactly as today, so this costs zero
additional bzzoiro requests.

### 4. Automatic trigger: settle yesterday before running today

Add a step to `scripts/simple/run_pipeline.py` (or a thin wrapper script
`settle_previous_day.py`) that runs before DISCOVER: given today's date,
compute `yesterday = date - 1`, check whether `runs/{yesterday}/` exists and
has no corresponding `row_settlements` rows yet, and if so shell out to
`backtest_slate.py --date {yesterday} --recorded --persist-db`. Failure is
logged and non-fatal (today's run must not block on yesterday's settlement).

For truly unattended operation (the user asked about "next day" specifically),
wire this as a scheduled step rather than folding it into `run_pipeline.py`'s
critical path — e.g. a cron entry (see `schedule` skill / `CronCreate`) that
fires once daily, independent of when `run-day` happens to be invoked, so a
skipped day still gets settled later.

### 5. Read path for analysts / future queries

No agent changes required for this plan. Once `row_settlements` exists, a
follow-up (out of scope here) could have `bet-analyst-football` /
`bet-analyst-tennis` query it directly ("has this market/line ever hit for
this team before?") instead of relying on the JSON backtest reports referenced
in memory (`settled-record-by-market-family.md`, etc.). Not doing this now —
first land the write path and confirm it's correct on a few real days.

## Sequencing / rollout

1. Add the table (migration in `bet.db` — check how existing tables are
   migrated before inventing a new mechanism).
2. Add `persist_row_settlements` + tests (mirror the existing
   `persistence.py` test coverage).
3. Wire `--persist-db` into `backtest_slate.py`, run it by hand against 2-3
   already-played days, spot-check `row_settlements` against the JSON report
   it replaces.
4. Only then add the automatic yesterday-trigger (step 4) — do not automate
   before the write path has been eyeballed against real data, since a bug
   here would silently poison every future calibration query.

## Explicitly out of scope for this plan

- Changing `settle.py`'s settlement logic itself.
- Any change to how `p_low`/bar-basis is computed.
- Backfilling `row_settlements` for all historical `runs/` days — that's a
  one-time batch job to run *after* step 3 confirms the schema is right, not
  part of landing the feature.
