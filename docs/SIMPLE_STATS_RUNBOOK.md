# Runbook: simple_stats pipeline (DISCOVER → ENRICH → ANALYZE)

Implements `docs/PIPELINE_SIMPLIFICATION_PLAN.md`. Read section 13 of that
document for what was verified live and which of its earlier assumptions no
longer hold.

## Morning procedure

**[docs/MORNING.md](MORNING.md)** is the operator's four-step checklist. Start
there. This document is the reference behind it.

```bash
python3 scripts/simple/run_pipeline.py --preflight
```

Checks quota and credentials for every provider and stops. Zero calls, ~2 s. The
last line is a go/no-go, and `recommended_max_events` is the cap worth passing to
the real run.

## Full run for a date

```bash
python3 scripts/simple/run_pipeline.py -v                    # today, UTC
python3 scripts/simple/run_pipeline.py --date 2026-08-25 -v  # a named day
```

That is the whole run. It mints one `run_id`, threads each step's artifact into
the next, writes everything to `runs/<date>/` and emits exactly one
`AGENT_SUMMARY:` line. Under Kilo the same thing is `/run-day`, which selects the
`bet-simple` primary.

Each step's artifact path is read from that step's own
`AGENT_SUMMARY.metrics.output_path`, not reconstructed from a filename
convention — one convention in two places drifts silently.

### Resuming, and running one step

```bash
python3 scripts/simple/run_pipeline.py --date 2026-08-25 --start-at enrich
python3 scripts/simple/run_pipeline.py --date 2026-08-25 --stop-after discover
```

On resume the wrapper adopts the `run_id` stamped in the artifact it reads rather
than minting a new one, so a restarted run keeps its identity in the DB. If the
artifact a resumed step needs is missing, the run stops at
`PRECONDITION_FAILED` instead of half-producing.

The three steps also stay independently runnable, which is what you want while
diagnosing a bad day:

```bash
DATE=2026-08-25; OUT=runs/$DATE
python3 scripts/simple/run_discover.py --date "$DATE" --output-dir "$OUT"
python3 scripts/simple/run_enrich.py   --event-list "$OUT/${DATE}_event_list.json" --output-dir "$OUT" --max-events 40
python3 scripts/simple/run_analyze.py  --dossier    "$OUT/${DATE}_event_dossiers.json" --output-dir "$OUT"
```

DISCOVER mints a `run_id`; ENRICH and ANALYZE inherit it from the artifact they
read, so all three steps are one traceable run either way.

### The run receipt

`runs/<date>/<date>_run_summary.json` records the run's verdict, each step's
verdict, exit code, artifact path and persistence flag. It sits next to the
artifacts it describes, so a later session reconstructs what happened without
scrollback.

## Agent contract

Every step speaks the repo's standard contract from
[agent_output.py](scripts/agent_output.py) — the same one `AgentOutput.validate_summary()`
checks:

```json
AGENT_SUMMARY:{"step":"simple_stats:ENRICH","verdict":"OK|PARTIAL|FAILED|PRECONDITION_FAILED",
               "metrics":{...},"issues":[...],"counts":{"errors":N,"warnings":N},"ts":"..."}
```

Exit codes: `0` = OK, `1` = PARTIAL (artifact produced, with `data_gaps`),
`2` = FAILED or PRECONDITION_FAILED (no usable artifact). `persisted` /
`persist_error` in `metrics` tell you whether the DB write succeeded — do not
rely on stderr for this.

With `-v` each step also streams one JSON object per line while it runs
(`run_start`, `provider_quota`, `progress`, `warning`, `artifact_written`,
`db_persisted`), so a monitoring agent sees the run unfold rather than only its
final verdict. Every line is parseable JSON; the trailing `AGENT_SUMMARY:` line
is the final result.

```bash
python3 scripts/simple/run_enrich.py --event-list ... --output-dir ... -v \
  | grep -v '^AGENT_SUMMARY' | jq -c 'select(.event=="progress")'
```

## Preflight

ENRICH checks provider quotas **before** the first network call:

- **All providers exhausted, unconfigured or dead** → `PRECONDITION_FAILED`,
  exit 2, nothing spent. Override with `--skip-preflight` for the all-gaps artifact.
- **Some unavailable** → run proceeds; each one is a `warning` in `issues`,
  tagged by kind so you know whether waiting helps:
  - `missing_credentials` — names the `.env` variable to set;
  - `quota_exhausted` — clears daily; the message names both
    `BET_LIMIT_<PROVIDER>` and the `reset_provider_quota.py` command;
  - `upstream_unavailable` — will not clear on its own (sackmann, understat).
- **Quota too thin for the planned event count** → warning naming the provider,
  plus `recommended_max_events` in `metrics`.

`recommended_max_events` is the number of events that can still be seen by
**two** providers — the threshold `readiness=READY` and
`cross_provider_agreement` both need. It deliberately does not report the most
generous provider's reach, which would promise 400 events off an unlimited ESPN
quota while the only provider that could corroborate it runs dry after 7.

## Run lineage

```bash
python3 -c "
import sys; sys.path.insert(0,'src')
from bet.simple_stats.run_context import load_run
import json; print(json.dumps(load_run('$DATE'), indent=2))
"
```

Each step upserts a `pipeline_runs` row keyed `(date, 'simple_stats:<STEP>')`
holding its status, timings, `run_id`, artifact path and SHA256. The `run_id`
is also stamped into `analysis_raw_data.safety_input_json` and
`analysis_results.stats_summary_json`.

The output artifact is the readable deliverable:
`${DATE}_event_dossiers_stats_sheet.json`, sorted `confidence` desc then
`hit_rate` desc. Rows carry `hits/sample_size`, `mean`, `median`, `sources`,
`cross_provider_agreement`, `confidence` and `data_quality`. There is no price,
no EV and no `bettable` field — by design (plan §1). Pick a line by hand in
Superbet Bet Builder.

## Flags that matter

| Flag | Default | Why you would change it |
|---|---|---|
| `--preflight` (pipeline) | off | Check providers and stop. Zero calls. Run it first, every morning. |
| `--max-events` (enrich) | 40 | A day is 150+ fixtures at several dozen provider calls each; no quota survives an uncapped run. Events beyond the cap appear in the artifact as `BLOCKED` with reason `not enriched: run capped at N events`. |
| `--provider-call-budget` (enrich) | 100 | Per-provider ceiling **inside one run**, on top of the durable daily `RateLimiter`. |
| `--db-path` (all) | `betting/data/betting.db` | `bet.db.connection` refuses to guess an operational DB. Override, or set `BET_DB_PATH`. |
| `--sports` (discover) | `football,tennis` | |
| `--skip-preflight` (enrich) | off | Run even with every provider exhausted. Produces an all-gaps artifact — only useful for testing the downstream steps. |
| `--run-id` (discover) | minted | Reuse an existing run id, e.g. when re-running DISCOVER inside an already-identified run. |
| `-v` / `--verbose` (all) | off | Stream JSON-line events for a monitoring agent. |
| `--stop-on-error` (all) | off | Exit on the first non-recoverable error instead of log-and-continue. |

Events are enriched best-corroborated-first (identity `CONFIRMED` and native
provider ids present), so a capped run spends its budget where READY is
reachable.

## Configuration — `.env` only

Credentials and quotas are read from the process environment first, then the
project `.env`. There is no third source: the former silent fallbacks to
`config/api_keys.json` and `config/odds_api_key.txt` were removed, because one
secret in several files drifts and a quiet fallback turns that drift into odd
provider behaviour instead of a config error. Parsing is `python-dotenv`, so
quoting and `export` behave normally. See [.env.example](.env.example).

```bash
HIGHLIGHTLY_API_KEY=...     # also accepts RAPIDAPI_KEY
SPORTDB_API_KEY=...         # also accepts SPORTDB_KEY
API_FOOTBALL_KEY=...
SERPAPI_KEY=...
ODDS_API_KEY=...
# ESPN, tennis-abstract and sackmann need no credential.

BET_LIMIT_HIGHLIGHTLY=100   # override the default compiled into rate_limiter.py
BET_LIMIT_SPORTDB=300       #   -1 = no local cap,  0 = disable the provider
```

The limits in `src/bet/api_clients/rate_limiter.py` are conservative guesses,
not measurements — the real number is in the provider's dashboard. Set
`BET_LIMIT_<PROVIDER>` once you know it rather than editing code.

## Provider quotas — check and reset

```bash
python3 scripts/simple/reset_provider_quota.py --status
```

```
provider                 used   limit   left  override w .env
api-football              101     100      0  BET_LIMIT_API_FOOTBALL
highlightly               130     100      0  BET_LIMIT_HIGHLIGHTLY
sportdb                    42     300    258  BET_LIMIT_SPORTDB
```

**After rotating a key**, the counter in `betting/data/.api_usage/` is stale: it
recorded what the *old* key spent, so preflight keeps reporting the provider as
exhausted while the new key is untouched. Clear it:

```bash
python3 scripts/simple/reset_provider_quota.py --provider highlightly
python3 scripts/simple/reset_provider_quota.py --all --yes
```

This only forgets our own count — it changes nothing at the provider. To raise
the ceiling instead, set `BET_LIMIT_<PROVIDER>` in `.env`.

`highlightly` is the binding constraint (one `/statistics` call per historical
match) and its counter rolls over daily. At `remaining=0` the provider answers
`HTTP 429` and every Highlightly observation becomes a `data_gap` — the run
still completes, with fewer providers corroborating each metric. ENRICH's
preflight reports the same numbers as `provider_quota` events before it starts.

## Reading the result

- `cross_provider_agreement=AGREE` — 2+ providers reported the same historical
  match within tolerance (±1 for counts, ±5pp for percentages). This is the
  signal to trust.
- `DISAGREE` — providers conflict. Both values stay in the dossier and are
  never averaged; `confidence` drops to `LOW`. Look at the dossier before using
  the row.
- `SINGLE_SOURCE` — only one provider covered those matches. Common and not an
  error, but nothing corroborates it.
- `sample_size` counts every observation pooled into the hit rate across both
  sides and all providers, so it is not a count of independent matches.
- `mean`/`median` are reported alongside, never instead of, the hit rate.

## Known limitations (2026-08-25)

- **Tennis tops out at `PARTIAL`.** `READY` needs 2+ providers on 3 priority
  metrics; only `tennis-abstract` supplies them (`sackmann`'s GitHub repo is
  404, `espn-tennis` covers only `total_games`/`total_sets`).
- **`sackmann` and `understat` always produce a `data_gap`** — dead upstream
  and unbuildable dependency respectively. Expected, not a failure.
- **ESPN only resolves teams in leagues** that `COMPETITION_TO_ESPN_LEAGUE`
  maps. Unmapped competitions produce `could not resolve team identity`.
- **SportDB rejects a competition it cannot confidently match.** That yields
  `no season results for '<league>'` — deliberate: data from the wrong league
  would be worse than no data.
- **The Odds API monthly quota is spent**, so discovery uses its free
  `/events` endpoint. No action needed; odds are out of scope anyway.

## Tests

```bash
python3 -m pytest tests/simple_stats -q
```

The rest of `tests/` has ~172 pre-existing failures and 25 collection errors.
They come from unresolved merge-conflict markers (`<<<<<<< HEAD`) committed into
the S0-S10 stack, which now lives under `legacy/` — see `legacy/README.md`.
`simple_stats` imports zero `bet.pipeline` modules, verified by import trace, so
none of that can affect a run.
