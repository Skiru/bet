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
| `purge_unproven_cache.py` | Delete cached provider data written before the checks that would have caught it. Dry run by default. |

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

## Keeping the provider claims honest

Three of the pipeline's tables are claims about providers we do not control, so
each one ships with a script that re-derives its evidence and fails loudly when
the evidence stops agreeing. None runs as part of a betting day; all are cheap
and should be re-run whenever something resolves to nothing it should resolve
to, and on a routine every month or so.

| Script | Proves |
|---|---|
| `build_sportdb_competition_map.py` | Every seeded competition in `config/sportdb_competition_map.json` still exists on Flashscore under the asserted name, with the asserted clubs in its real season results. |
| `verify_espn_competition_map.py` | Every ESPN league code the competition table pins still answers `/teams` with a non-empty directory, and ESPN's own name for it contradicts none of the names pinned to it. Writes `config/espn_competition_map_verification.json`, which the test suite treats as an allowlist. |
| `verify_tennis_providers.py` | Every provider in `PROVIDERS_BY_SPORT["tennis"]` resolves a rostered player, returns his matches, and names him as the player in every row it returns — judged against the provider's *own* name field. Writes `config/tennis_provider_verification.json`, also an allowlist. |

The tennis script exists because of a failure the other two cannot have:
tennisabstract answers **200 with somebody else's page** when it has no player
on the route asked. `player-classic.cgi` returns Benoit Paire's table, byte for
byte, for every WTA player. Nothing about that response is an error — the
status is fine, the table is real, and the numbers are somebody's — so the only
thing that catches it is comparing the page's own `var fullname` against the
player we asked for. Run it per tour, per player, or against tonight's actual
slate:

```bash
.venv/bin/python scripts/simple/verify_tennis_providers.py
.venv/bin/python scripts/simple/verify_tennis_providers.py --tour wta
.venv/bin/python scripts/simple/verify_tennis_providers.py --from-events runs/<date>/<date>_event_list.json
```

```bash
.venv/bin/python scripts/simple/verify_espn_competition_map.py            # probe what is new
.venv/bin/python scripts/simple/verify_espn_competition_map.py --refresh  # re-prove everything
```

Exit 1 means drift: a code died, or a name and a code disagree about which
league they mean. The fix belongs in the table, not in the script — a looser
comparison here is how a map starts guessing. Adding a code to
`api_clients/espn.py` without re-running the script fails
`tests/simple_stats/test_espn_competition_map.py`, which is the point: the 18
dead codes the table used to carry were committable precisely because nothing
made the claim checkable.

Per-run drift is reported without any probing at all: ENRICH's `AGENT_SUMMARY`
carries `espn_competition_coverage`, which names every competition on the day's
slate that the table could not resolve, weighted by fixtures as well as by name.
