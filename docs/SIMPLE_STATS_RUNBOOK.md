# Runbook: simple_stats pipeline (DISCOVER → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE)

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
`${DATE}_event_dossiers_stats_sheet.json`, sorted by `p_low` desc. Rows carry
`hits/sample_size`, `mean`, `median`, `sources`, `cross_provider_agreement`,
`confidence` and `data_quality`. There is no price, no EV and no `bettable`
field — by design (plan §1). Pick a line by hand in Superbet Bet Builder.

It holds three families of row, told apart by the row's own fields rather than by
a type tag:

| Family | `team_name` | `player_id` | Markets |
|---|---|---|---|
| match total | null | null | `corners_total`, `cards_total`, `fouls_total`, `shots_on_target_total`, … |
| per team | set | null | `corners_for`, `cards_for`, `fouls_for`, `shots_on_target_for`, `shots_for` |
| player prop | set (his side) | set | `player_total_shots`, `player_shots_on_target`, `player_fouls`, `player_was_fouled`, `player_cards` |

A per-team row is **one** team's own contribution, and the two sides of a fixture
produce two rows of the same market and line that differ only in `team_name` and
in their numbers. Their samples are never pooled: pooling would build one
twenty-match sample out of two different teams. Neither family reads the H2H
bucket, because an H2H observation carries no marker for which side it belongs
to.

Because the sort is by `p_low` across all three families, the low-line props
(`player_cards` UNDER 0.5 and friends) land at the top: most players are not
carded in most matches, which is also why that side is priced at 1.05 and is not
a bet. Group by family before reading.

### The two optional columns

Every field above is computed with no knowledge that either of these exists, and
neither can reach `p_low`, `hit_rate`, `mean`, `median` or `confidence`.

`row.tipster` — public-tipster agreement, from TIPSTERS.

`row.market_signal` — a bookmaker price and an independent model probability,
from MARKET_CONTEXT (`<date>_market_context.json`). It carries
`model_probability`, `market_implied_probability` (de-vigged: the two legs of the
line normalised against each other), `market_price`, `market_bookmaker` and a
`verdict` of `CONFIRMS` / `CONTRADICTS` / `SPLIT` / `NO_MARKET_DATA`.

Three things about it that read as bugs and are not:

- **It exists only on `corners_total` rows.** bzzoiro's odds feed publishes
  fourteen markets and none of them is cards, fouls or shots on target; the model
  covers none of them either. `null` on those rows is the provider's coverage,
  not a gap.
- **An 11.5-corner row always reads `NO_MARKET_DATA`.** The model serves 8.5,
  9.5 and 10.5 only. Nothing is interpolated — over 10.5 is evidence about a
  different bet than over 11.5, not weak evidence about it.
- **A verdict needs both numbers.** One agreeing figure is not triangulation, and
  a line quoted on one side only yields a price but no probability, because there
  is no second leg to remove the overround against.

The prices come from ~88 bookmakers and **none of them is Superbet** (checked
live 2026-08-28). Treat `market_price` as a market reference point; the operator
still reads their own screen.

## Bet Builder draft

```bash
python3 scripts/simple/bet_builder_draft.py \
  --stats-sheet runs/$DATE/${DATE}_event_dossiers_stats_sheet.json \
  --event-id <event_id> [--max-legs 4]
```

Stateless — reads one artifact, prints JSON, writes nothing, calls nothing. It
selects `CALL`/`LEAN` rows only (never `WEAK`), one per market, ranked by
`p_low`, and gives each leg `fair_odds = 1/p_low` and a `min_acceptable_odds`
carrying the tier's margin.

**It prints no combined price and its contract types that field `None` so it
cannot hold one.** There is no bet-builder endpoint in any provider here, and the
product of the legs would be wrong: corners, cards, fouls and shots in one match
are strongly positively correlated, so they land together far more often than
independence implies. `correlation_risk: HIGH` says so explicitly whenever two or
more legs come from that family — which is almost any same-match multi.

## Flags that matter

| Flag | Default | Why you would change it |
|---|---|---|
| `--preflight` (pipeline) | off | Check providers and stop. Zero calls. Run it first, every morning. |
| `--max-events` (enrich) | 40 | A day is 150+ fixtures at several dozen provider calls each; no quota survives an uncapped run. Events beyond the cap appear in the artifact as `BLOCKED` with reason `not enriched: run capped at N events`. |
| `--provider-call-budget` (enrich) | 100 | Per-provider ceiling **inside one run**, on top of the durable daily `RateLimiter`. `bzzoiro` is exempted up to 20000 (`RUN_BUDGET_OVERRIDES` in `providers.py`): at 100 it would run dry after three or four events, and since PRO removed its daily ceiling this per-run number is the only bound left — set where it cannot cap a real day, purely to terminate a runaway loop. Passing a larger value raises it further. |
| `--max-events` (market_context) | 40 | Forwarded from the pipeline's own `--max-events`, so ENRICH and this step cap at the same number. Both rank the slate with `_enrichment_priority`, so the two budgets land on the same fixtures. Running them separately with different caps is how you pay for context on events that produce no row: on 2026-08-28 mismatched slices overlapped on 3 of 12 fixtures. ~4 calls per event. |
| `--skip-market-context` (pipeline) | off | Do not fetch bookmaker odds or model predictions. The sheet is produced without `row.market_signal`. |
| `--player-props` (enrich) | off | Collect per-player prop history: one call per outfield starter, ~20 extra per event. Needs a lineup, so it is only worth passing within a few hours of kickoff. Every prop row records whether the XI was `confirmed` or `predicted`. Not forwarded by `run_pipeline.py` — call `run_enrich.py` then `run_analyze.py` directly. |
| `--backfill-from` (enrich) | off | Path to an earlier `EVENT_DOSSIER_V1` for the same date. Re-enriches only its `BLOCKED`/`PARTIAL` events, keeps that run's `run_id`, and merges back into the same file — replacing a dossier only when the retry reaches a better readiness, or the same readiness with more observations. Worth one pass per day now that bzzoiro has budget left for it. |
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
BZZORIO_KEY=...             # sports.bzzoiro.com — note the 'ri', see below
SPORTDB_API_KEY=...         # also accepts SPORTDB_KEY
API_FOOTBALL_KEY=...
SERPAPI_KEY=...
ODDS_API_KEY=...
# ESPN, tennis-abstract and sackmann need no credential.

BET_LIMIT_HIGHLIGHTLY=100   # override the default compiled into rate_limiter.py
BET_LIMIT_BZZOIRO=-1        # football: uncapped on PRO — see below
BET_LIMIT_BZZOIRO_TENNIS=95 # tennis: same account, still 100/day
BET_LIMIT_SPORTDB=300       #   -1 = no local cap,  0 = disable the provider
```

The limits in `src/bet/api_clients/rate_limiter.py` are conservative guesses,
not measurements — the real number is in the provider's dashboard. Set
`BET_LIMIT_<PROVIDER>` once you know it rather than editing code.

### `BZZORIO_KEY` must also be **exported** for the MCP servers

`.mcp.json` registers two bzzoiro MCP servers for the analyst agent and reads
the key as `${BZZORIO_KEY}`. That expansion is done by the agent harness against
the **process environment**, which is not the same thing as this repo's `.env`:
the Python clients parse `.env` with `python-dotenv`, the harness does not. So a
key that only lives in `.env` authenticates every pipeline call and none of the
MCP calls, which surface as `-32001 Authentication required`.

Export it in your shell profile as well:

```bash
export BZZORIO_KEY=...      # same value as the .env entry
```

The key is never written into `.mcp.json` itself — that file is committed.

`bzzoiro` is the exception in the other direction: **it has no compiled default
at all.** On the PRO plan the football product stops sending rate-limit headers
entirely — verified live 2026-08-28 across `/leagues/`, `/events/`,
`/events/{id}/stats/` and `/coverage/`, where the free plan had answered
`ratelimit-policy: "football";q=7500;w=86400`. An absent entry is how this
limiter spells "unlimited" (ESPN is the same), so preflight reports it as
unlimited rather than inventing a ceiling. The only remaining bound is per-run:
`RUN_BUDGET_OVERRIDES["bzzoiro"]` in `simple_stats/providers.py`, set where it
cannot bind a real day (~600 fixtures) and exists purely to terminate a loop.
Set `BET_LIMIT_BZZOIRO` in `.env` to reimpose a daily ceiling.

Its credential is `BZZORIO_KEY` while its quota override is `BET_LIMIT_BZZOIRO` —
the provider spells its key differently from its own domain, and both spellings
are load-bearing.

**`bzzoiro-tennis` is the same account, the same key, and still capped.** The
tennis product answers `ratelimit-policy: "tennis";q=100;w=86400` — checked again
*after* the PRO upgrade, which changed nothing there. Separate bucket
server-side, so a tennis call costs nothing against football and vice versa. At
~16 calls per fixture that is about six enriched tennis matches a day, which is
why the tennis discovery adapter drops UTR and ITF outright rather than letting
them compete for the budget. The two products are separate provider keys
precisely so their counters stay separate: one key would have let football's
uncapped traffic mask the tennis ceiling until a run hit HTTP 429 with the
budget already spent.

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

`bzzoiro` is what removed the old binding constraint. On 2026-08-25, with
highlightly's 100 calls a day, 175 of 181 events came back `BLOCKED`; the
football product is uncapped on PRO, so a full slate is now affordable. It is also the only
provider that serves the per-team and per-player markets at all, because it is
the only one whose client keeps the home/away split (`/events/{id}/stats/`) and
the only one with per-player history (`/players/{id}/stats/`, box scores inline,
one call). Rows from those markets are therefore always `SINGLE_SOURCE`, which is
a property of the roster and not a defect in the day.

`highlightly` is the other daily-capped provider (one `/statistics` call per
historical match) and its counter rolls over daily. At `remaining=0` the provider answers
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
