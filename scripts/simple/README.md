# scripts/simple — the live pipeline

Everything a betting day needs. The rest of `scripts/` is older tooling for the
quarantined S0–S10 stack (see `legacy/README.md`).

```bash
python3 scripts/simple/run_pipeline.py --preflight   # is today worth running? 0 calls
python3 scripts/simple/run_pipeline.py -v            # run it
```

| Script | Role |
|---|---|
| `run_pipeline.py` | **Start here.** DISCOVER → ENRICH → TIPSTERS → ANALYZE under one `run_id`. Also `--preflight`. |
| `run_discover.py` | Step 1 alone — event universe for a date |
| `run_enrich.py` | Step 2 alone — provider observations per event |
| `run_tipsters.py` | Optional step — public tipster picks per event (`--skip-tipsters` to omit) |
| `run_analyze.py` | Step 3 alone — hit rates and the stats sheet |
| `reset_provider_quota.py` | Clear a local usage counter after rotating a key |

The step scripts stay runnable on their own because re-running one against a
saved artifact is how you debug a bad day. For a normal run, use
`run_pipeline.py` — it threads the artifacts and returns one verdict.

`TIPSTERS` is the only optional step. It fetches public tipster pages, so it can
fail for reasons that have nothing to do with the betting day; it therefore
reports `PARTIAL` rather than `FAILED` and is excluded from the run verdict. What
it produces fills one column of the stats sheet (`row.tipster`) and never touches
a probability — see `src/bet/simple_stats/tipster_signal.py` for why that
separation is structural rather than a convention. Nothing is fetched without an
operator attestation in `docs/pipeline/tipster_terms_review.local.json`.

Operator procedure: [docs/MORNING.md](../../docs/MORNING.md).
Reference: [docs/SIMPLE_STATS_RUNBOOK.md](../../docs/SIMPLE_STATS_RUNBOOK.md).
Library code: `src/bet/simple_stats/`. Tests: `tests/simple_stats/`.
