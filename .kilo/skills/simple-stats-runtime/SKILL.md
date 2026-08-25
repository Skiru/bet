---
name: simple-stats-runtime
description: Runtime contract for the default betting day - one run_id, one entrypoint, preflight before spend, and what each verdict obliges you to do.
---

# simple_stats Runtime

The default betting day. Three steps, one command, one `run_id`.

## Ownership

| Step | Script | Produces |
|---|---|---|
| DISCOVER | `scripts/simple/run_discover.py` | `EVENT_LIST_V1` |
| ENRICH | `scripts/simple/run_enrich.py` | `EVENT_DOSSIER_V1[]` |
| ANALYZE | `scripts/simple/run_analyze.py` | `STATS_SHEET_V1` |
| **whole day** | **`scripts/simple/run_pipeline.py`** | all three + `<date>_run_summary.json` |

`bet-simple` is the default primary. Run `scripts/simple/run_pipeline.py`; reach for the
individual scripts only to re-run one step against a saved artifact while
diagnosing. Business specialists do not run shell.

## One run_id

DISCOVER mints it; ENRICH and ANALYZE read it from the artifact they consume, so
all three steps and every DB row share one id. On a resumed run
(`--start-at enrich|analyze`) the wrapper adopts the id stamped in the artifact
rather than minting a new one — a run's identity comes from its data, not from
the process that happened to restart it.

Lineage lives in `pipeline_runs` keyed `(date, 'simple_stats:<STEP>')`, and the
id is stamped into `analysis_raw_data.safety_input_json` and
`analysis_results.stats_summary_json`.

## Spend nothing before checking

`scripts/simple/run_pipeline.py --preflight` checks the provider roster -- quota and
credentials -- and stops. Zero calls. Run it before the day's run; its advice
line is the go/no-go, and `recommended_max_events` is the cap to pass on.

ENRICH then runs the same check again before its first network call, so a stale
morning answer cannot let a run start on an exhausted roster. No usable provider
means `PRECONDITION_FAILED` and exit 2 with nothing spent.

`--skip-preflight` produces an all-gaps artifact that looks like a result. It is
for testing downstream steps, never for a real run.

`recommended_max_events` is the count reachable by **two** providers — the bar
`READY` and `cross_provider_agreement` both need. It is deliberately not the most
generous provider's reach.

## Per-verdict obligation

- `OK` — report the stats sheet path.
- `PARTIAL` — report, and name the unavailable providers and single-source rows.
  Partial evidence is never PASS-without-qualification.
- `PRECONDITION_FAILED` — report each blocked provider's `kind`. Do not retry:
  `missing_credentials` needs a human to edit `.env`, `quota_exhausted` clears
  daily (or needs `reset_provider_quota.py` after a key rotation),
  `upstream_unavailable` will not clear at all.
- `FAILED` — report the failing step and its issues. Do not retry blindly.

Check `metrics.<step>_metrics.persisted` for the DB write. Never infer it from
stderr.

## Failure handling

Retry the same operation at most twice, then change strategy. A quota error is
not a retry candidate — retrying spends what is left. If code repair is needed,
checkpoint and use Code/General in a fresh worktree; the betting executor never
repairs code.

## Boundaries

The deliverable is a stats sheet: hit rates, sample sizes, provider agreement.
No price, no EV, no stake, no `bettable` — by design. The operator picks lines by
hand in Superbet, and every pick stays conditional on a human-entered quote.

Never echo `.env` values. Report the *name* of a missing variable, never a value.
