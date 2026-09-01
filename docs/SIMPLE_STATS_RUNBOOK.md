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
  - `upstream_unavailable` — will not clear on its own (understat; and
    `sackmann`, which is no longer asserted for tennis at all — see below).
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

ANALYZE also writes `${DATE}_event_dossiers_stats_sheet_top.json` — the same
rows filtered to `p_low >= 0.50`, the coupon's own floor. It exists because
Faza 2 roughly doubled the line grid: the full sheet stays on disk for audit,
but the analyst reads the top file so its context window is not spent on rows
no coupon could ever use. `run_analyze.py --max-rows-per-event N` additionally
caps how many rows (strongest `p_low` first) one event contributes to *both*
files; the default is unlimited.

It holds three families of row, told apart by the row's own fields rather than by
a type tag:

| Family | `team_name` | `player_id` | Markets |
|---|---|---|---|
| match total | null | null | `corners_total`, `cards_total`, `fouls_total`, `shots_on_target_total`, `shots_total`, `goals_total`, `goals_1h_total`, `goals_2h_total`, `offsides_total`, `red_cards_total`, … |
| per team | set | null | `corners_for`, `cards_for`, `fouls_for`, `shots_on_target_for`, `shots_for`, `goals_for`, `offsides_for` |
| player prop | set (his side) | set | `player_total_shots`, `player_shots_on_target`, `player_fouls`, `player_was_fouled`, `player_cards` |

`goals_1h_total`/`goals_2h_total` (Faza 3) are read off the fixture's own
half-time score the same way `goals_total` reads the final score, so they need
no `/stats/` payload either. `corners_1h_total`, `cards_2h_for` and the rest of
the half-split family exist in the dossier's `metrics` as soon as the raw
`/stats/` payload carries `first_half`/`second_half` blocks, but have no
`STANDARD_MARKET_LINES` entry and so never reach the stats sheet — there is no
operator-screen evidence yet for what line to price them at. Player props
(Faza 4) only populate `dossier.player_metrics` when the run passed
`--player-props`; a player on either squad's `unavailable` list never reaches
a row even then (`analyze.py:_unavailable_player_ids` filters it before the
stats sheet is built).

`goals_total`/`goals_for`/`goals_against` are read straight off each historical
fixture's final score, not off `/stats/`, so their `n` on a given event is
usually larger than every other market's and does not depend on whether that
match published a box score at all (docs/PLAN_BOGATE_STATYSTYKI.md Faza 1).
`goals_for` is also the one per-team market not exclusive to bzzoiro:
`espn-football` and `highlightly` can both tell which side of a historical
match scored, so it can be `AGREE`-corroborated like a match total, unlike the
rest of the per-team row.

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

### The three optional columns

Every field above is computed with no knowledge that either of these exists, and
neither can reach `p_low`, `hit_rate`, `mean`, `median` or `confidence`.

`row.tipster` — public-tipster agreement, from TIPSTERS.

`row.market_signal` — a bookmaker price and an independent model probability,
from MARKET_CONTEXT (`<date>_market_context.json`). It carries
`model_probability`, `market_implied_probability` (de-vigged: **one
bookmaker's own** paired over/under legs, pinnacle preferred, never the best
over from one book against the best under from another — mixing books lets
whichever one prices a side more aggressively pull the number toward it),
`market_price`, `market_bookmaker` and a `verdict` of `CONFIRMS` / `CONTRADICTS`
/ `SPLIT` / `NO_MARKET_DATA`. `market_price`/`market_bookmaker` are still the
best price across every bookmaker tracked, so the two numbers on one row can
legitimately name different books.

Four things about it that read as bugs and are not:

- **It exists only on `corners_total` and `goals_total` rows.** bzzoiro's odds
  feed publishes fourteen markets and none of them is cards, fouls or shots on
  target; the model covers none of them either. `null` on those rows is the
  provider's coverage, not a gap.
- **A corners-total row off the 6.5/7.5/11.5/12.5 lines always reads
  `NO_MARKET_DATA`.** The model serves 8.5, 9.5 and 10.5 only (Faza 2 widened
  the priced line grid without widening what the model itself covers). Nothing
  is interpolated — over 10.5 is evidence about a different bet than over
  11.5, not weak evidence about it.
- **`goals_total` is one feed code *per line***, not one code for the whole
  market the way corners is: `over_under_05/15/25/35`. 0.5 gets a price with no
  model read; 4.5 has no feed code at all and gets neither. Both always read
  `NO_MARKET_DATA` for that reason, not for lack of data on the day.
- **A verdict needs both numbers.** One agreeing figure is not triangulation, and
  a line quoted on one side only yields a price but no probability, because there
  is no second leg to remove the overround against.

The prices come from ~88 bookmakers and **none of them is Superbet** (checked
live 2026-08-28). Treat `market_price` as a market reference point.

`row.superbet` — the price on the operator's own book, from SUPERBET
(`<date>_superbet_offer.json`). Added 2026-08-31 for exactly the reason the
paragraph above states: everything else here is a reference to a bookmaker the
operator does not use.

It carries `availability`, `price`, `status`, `source_market_name` (Superbet's
own Polish market name, kept verbatim so a mapping can be audited),
`nearest_offered_line`/`nearest_offered_price` and `superbet_event_id`.

**`availability` matters more than `price`**, and the reason is the finding this
column was built on. On the 2026-08-31 night slate, eight of fifteen singles were
on lines Superbet does not list:

| Our line | Superbet's ladder |
|---|---|
| `shots_on_target_total` 4.5 | starts at 7.5 |
| `shots_total` 19.5 | starts at 24.5 |
| `offsides_total` 1.5 | starts at 2.5 |
| tennis `total_sets` 2.5, `total_games` 19.5-23.5 | 3.5/4.5 and 24.5-46.5 on every ATP slam tie — best-of-five |

The seven values, and what each one is about:

| Value | Whose problem |
|---|---|
| `OFFERED` | takeable; compare `price` to `min_acceptable_odds` |
| `LINE_NOT_OFFERED` | **ours** — our line generator, not the book |
| `MARKET_NOT_OFFERED` | the book's coverage |
| `OFFER_EMPTY` | the clock: the fixture kicked off and the book pulled the offer |
| `SCOPE_NOT_SUPPORTED` | **ours** — player props, which we choose not to read |
| `EVENT_NOT_MATCHED` | our matcher, or the fixture is already live |
| `SUSPENDED` | the book blocked the outcome |

Two of the seven are our own limitations and must never be reported as the book
lacking something. `SCOPE_NOT_SUPPORTED` is the larger of the two by volume:
Superbet prices player props heavily, under free-text names carrying the player
inside the market string ("Carrillo, Guido powyżej 0.5 celnych strzałów"), and
matching "Surname, Forename" onto our player ids would be a guess rather than a
lookup. On the first live run those were 7,891 of 12,193 supposedly-missing
markets.

Nothing here reaches `p_low`, `fair_odds` or `min_acceptable_odds`. A price only
changes the *order* of the coupon and the labels on it.

### `row.context_flags` (Faza 5b)

A third column with the same structural boundary: computed with no knowledge
of `p_low`/`hit_rate`/`confidence`, and read by `tier_for_row` only, never by
the statistics themselves. Each entry is
`{source, direction: SUPPORTS|ARGUES_AGAINST, magnitude, note}`, produced by
`src/bet/simple_stats/context_flags.py` from fields already on the dossier —
no new provider call. Five rules today: a referee's own season average sitting
on the other side of a `cards_total`/`fouls_total` line (`matches >= 8`), four
or more unavailable players against that side's own `shots_for`/
`shots_on_target_for`/`goals_for` OVER, a local derby supporting OVER on
`cards_*`/`fouls_*`, wind above 25 arguing against OVER on `corners_*`/
`shots_*`, and a team scoring well above its own season xG (`xg_games >= 5`)
arguing against its `goals_for` OVER continuing at that rate.

**Any `ARGUES_AGAINST` flag steps the row's tier down exactly one level**
(`CALL`->`LEAN`->`WEAK`, never further, never touching `p_low`) — this is now
enforced in `bet_builder_draft.tier_for_row`, the same ceiling that already
caps a single-source row at `LEAN`. `SUPPORTS` is reported but changes nothing:
context may argue a real read down, never up.

## Coupons — the operator's deliverable

```bash
python3 scripts/simple/build_coupons.py --date $DATE \
  --vetoes runs/$DATE/${DATE}_analyst_vetoes.json \
  --market-context runs/$DATE/${DATE}_market_context.json
```

Writes `runs/$DATE/${DATE}_kupony.md` (the file you open) and
`${DATE}_coupons.json`. No network, no DB, no quota — re-run it as often as you
like. `/run-day` calls it automatically; this is the manual form.

**The header warns if "Football Unlimited" was ever anything but entitled
during the run** (3bis.6): `--market-context` is read for exactly one thing —
whether any event's `comparison_entitlement` came back other than
`ENTITLED`/`NOT_ATTEMPTED`. If so, the coupon file's very first line says so,
because a lapsed entitlement removes both the market price *and* the model
probability for goals and corners at once, and with them the edge ranking
above. A missing `--market-context` file is silent, same as a missing
`--vetoes` file — the default healthy (unknown) state, not an error.

**`BET_MARKETS_PROFILE=legacy` is the rollback switch for the whole market/line
grid** (3bis.1), read fresh by `bet.stats.market_ranking.standard_market_lines()`/
`player_prop_lines()` on every call — set it before running ANALYZE
(`run_analyze.py`, or the `analyze` step inside `run_pipeline.py`) to reproduce
exactly the pre-Faza-1 football market set (10 markets, the narrower line
grids) without a git revert. Unset or any value other than exactly `"legacy"`
stays on `v2`, the current grid. `scripts/simple/diff_stats_sheet.py --profile
legacy` replays the frozen Faza 0 fixture under that profile and diffs against
`tests/fixtures/simple_stats/stats_sheet_baseline_legacy_2026-08-31.json`.

**Singles** are split into two sections that are never merged into one sorted
list (Faza 5c). Rows with a resolved market reference (today: `corners_total`
and `goals_total` — see `row.market_signal.market_implied_probability` above)
are ranked by **edge** (`p_low - market_implied_probability`) descending, then
by `p_low`; every other row is ranked by `p_low` alone, exactly as before. A
row this sheet can price against the market outranks one it cannot, however
high the second row's own `p_low` climbs — `p_low` on its own has no opinion on
whether a price already agrees with it. Both sections share one `max_singles`
budget, spent by the priced section first. Within each section: one per
market-per-fixture (four lines of one market are one read, not four bets),
filtered to `CALL`/`LEAN` rows at `p_low >= 0.50`. Below that threshold the
fair odds pass 2.00 and the required price exceeds what these markets
realistically pay, so the row is unplaceable rather than merely weak.
**Bet Builder** slips are the per-match drafts, 2–4 legs, ranked by their
**weakest** leg — a slip settles on every leg, so averaging would let three
strong legs carry a fourth nobody should be betting.

Low-line UNDERs (`<= 1.5`) are pushed to the bottom of the no-market-reference
section rather than dropped: a `player_cards UNDER 0.5` at 10/10 lands near
`p_low` 0.72, above almost every corners row, because most players are not
carded in most matches — which is also exactly why that side is priced near
1.05 and is not a bet.

**Youth and friendly competitions never reach the coupon** (Faza 5d):
`config/competition_tier_map.json` pins a small, hand-authored, exact-name-only
map from `EventRecord.competition` to `TIER_1`/`TIER_2`/`TIER_3`/`YOUTH`/
`FRIENDLY`. A `YOUTH`/`FRIENDLY` row is excluded from both singles and slips
(`excluded.competition_youth_or_friendly`) but stays on the full stats sheet.
An unmapped competition is left alone — never guessed at from a name pattern —
the same discipline `config/espn_competition_map_verification.json` already
follows for provider resolution.

**`--vetoes <path>` applies bet-analyst's read** (Faza 5e): a JSON array of
`{event_id, market, line, direction, action: VETO|DOWNGRADE, reason}`, matched
by exact `(event_id, market, line, direction)`. `VETO` excludes the row
(`excluded.analyst_veto`); `DOWNGRADE` steps its tier down one level, using the
same ceiling `context_flags` uses. Neither ever touches `p_low`. Every applied
veto/downgrade is echoed into `CouponSet.notes` with the analyst's own reason,
so the file's header shows exactly what was struck and why — a missing or
empty vetoes file is the default healthy state, not an error.

**No combined price, no EV, no stake.** `CouponSet.combined_price` is typed
`None`, so it cannot hold a value; the correlated-legs argument below is why.

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
| `--player-props` (enrich, and forwarded by `run_pipeline.py`) | off | Collect per-player prop history: one call per outfield starter, ~20 extra per event. Needs a lineup, so it is only worth passing within a few hours of kickoff. Every prop row records whether the XI was `confirmed` or `predicted`. |
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
# ESPN and tennis-abstract need no credential.

BET_LIMIT_HIGHLIGHTLY=100   # override the default compiled into rate_limiter.py
BET_LIMIT_BZZOIRO=-1        # football: uncapped on PRO — see below
BET_LIMIT_BZZOIRO_TENNIS=95 # tennis: same account, still 100/day
BET_LIMIT_SPORTDB=300       #   -1 = no local cap,  0 = disable the provider
```

The limits in `src/bet/api_clients/rate_limiter.py` are conservative guesses,
not measurements — the real number is in the provider's dashboard. Set
`BET_LIMIT_<PROVIDER>` once you know it rather than editing code.

### `BZZORIO_KEY` and the MCP servers

`.mcp.json` registers two bzzoiro MCP servers for the analyst agent and reads the
credential as `${BZZORIO_KEY}`. Claude Code resolves that from the process
environment and from a project-root `.env`, so the existing entry should be
enough — the key is never written into `.mcp.json` itself, which is committed.

If MCP tools answer `-32001 Authentication required` while `run_pipeline.py`
works fine, the variable did not resolve: Claude Code leaves an unresolved
`${VAR}` as the literal string rather than erroring, so the header is sent as
`Token ${BZZORIO_KEY}`. Export it explicitly and restart the session:

```bash
export BZZORIO_KEY=...      # same value as the .env entry
```

The auth shape itself is verified: `Authorization: Token <key>`, and tool calls
return `-32001` without it (probed live 2026-08-28).

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
bzzoiro-tennis             42     100     58  BET_LIMIT_BZZOIRO_TENNIS
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
- `sample_size` counts matches, not observations. Both sides' last-10 and the
  H2H bucket overlap, and two providers usually report the same match, so the
  raw observation list double-counts. Until 2026-08-28 the hit rate and Wilson
  bound read that raw list, which inflated `p_low` by up to 19pp on
  well-corroborated rows.
- **The collapse keys on (bucket, calendar day), not on names.** A team plays at
  most one match per day, so two observations in the same bucket stamped the
  same day are the same match — whatever each provider called the opponent, and
  whatever native `match_id` it stamped. `_one_per_day` does this per bucket;
  `_independent_match_sample` then folds the head-to-head day, the one match
  that legitimately sits in all three buckets.
- An earlier attempt keyed the collapse on (day + fuzzy opponent name). **Do not
  reintroduce that.** Measured over the 2026-08-25 and 2026-08-28 runs, 72
  same-bucket same-day pairs failed to cluster because two providers spelled one
  club differently (`mk dons` / `milton keynes dons`, `atletico junior` /
  `junior barranquilla`, `shenzhen peng city` / `shenzhen xinpengcheng`), so one
  match counted as two trials and *inflated* `p_low`. Loosening `_team_matches`
  is not the fix: `real madrid` and `real sociedad` share a substantive token
  too, and that same predicate is what team-identity resolution depends on,
  where a false positive files another team's data.
- Residual, and narrow: an observation with **no parseable date** cannot be
  placed, so it is kept whole and could still overstate a sample. Zero such
  observations in either measured run. Misreading the head-to-head day can err
  either way. `sample_size` is a floor on evidence, not a guarantee.
- `mean`/`median` are reported alongside, never instead of, the hit rate.

## Known limitations (2026-08-25, tennis section revised 2026-08-28)

- **Tennis tops out at `PARTIAL`.** `READY` needs 2+ providers on 3 priority
  metrics; only `tennis-abstract` supplies all three (`espn-tennis` covers only
  `total_games`/`total_sets`). This is a data limit, not a code one.
- **`understat` always produces a `data_gap`** — unbuildable dependency.
  Expected, not a failure.
- **`sackmann` is gone and is no longer asserted.** Removed from
  `PROVIDERS_BY_SPORT["tennis"]` on 2026-08-28: `JeffSackmann/tennis_atp` and
  `tennis_wta` both return 404 from the GitHub API — the *repositories*, not
  merely the CSVs, while the account is alive and still publishes
  `tennis_MatchChartingProject`. It stays in `KNOWN_DEAD_PROVIDERS` so preflight
  keeps naming it rather than letting it vanish from the record.
- **`sportdb` is out of the active football roster as of 2026-08-31.** Removed
  from `NATIVE_ID_PROVIDERS_BY_SPORT["football"]`: it answered HTTP 402 on
  159/159 requests that day, producing ~340 false `data_gap` entries per run
  for zero data. Its client and fetch functions are kept, unused — restoring it
  is a one-line change to that tuple once the entitlement is resolved — but a
  fresh run should never show a `sportdb`-sourced gap or observation.

### Tennis identity: what to expect in the log

`tennis-abstract` serves ATP and WTA from **different routes**, and the ATP
route answers 200 for a WTA player with somebody else's page. Two lines in a
tennis run are therefore normal and mean the guard is working:

```
[tennis-abstract] player-classic served 'Benoit Paire' for 'Iga Swiatek' --
    refusing the page rather than filing another player's matches under his name
[tennis-abstract] 125 matches for 'Iga Swiatek' via jsmatches (page names 'Iga Swiatek')
```

The first is the ATP route being rejected; the second is the WTA route
answering. A refusal with **no** following success means the site has no page it
can prove is that player's, and the player is reported unresolved — which is
the correct outcome, not a regression.

Re-prove the whole tennis roster whenever it looks wrong, and on a routine:

```bash
.venv/bin/python scripts/simple/verify_tennis_providers.py
.venv/bin/python scripts/simple/verify_tennis_providers.py --from-events runs/<date>/<date>_event_list.json
```
- **ESPN only resolves teams in leagues** that `COMPETITION_TO_ESPN_LEAGUE`
  maps. Unmapped competitions produce `could not resolve team identity`. Some
  names stay unmapped **by design**: ESPN's own `/teams` directory answers 200
  with zero teams for several real leagues (Finland's Veikkausliiga, Sweden's
  Superettan, Argentina's Primera C, Israel's Liga Leumit, Azerbaijan's
  Premier League, among others re-probed live 2026-08-31 — see the comment
  block above `_ESPN_FOOTBALL_COMPETITIONS` in `src/bet/api_clients/espn.py`).
  Adding a table entry for one of these would not fix anything; the code
  simply does not exist on ESPN's side.
- **`config/competition_name_canonical_map.json` (Faza 6, DISCOVER stage)**
  rewrites a handful of known duplicate spellings — `"EPL"` →
  `"Premier League"`, `"Veikkausliiga - Finland"` → `"Veikkausliiga"`,
  `"Danish Superliga"` → `"Denmark Superliga"`, `"Allsvenskan - Sweden"` →
  `"Allsvenskan"` — to one canonical string before dedup and ESPN resolution
  ever see them, so the same real league does not need two entries in every
  competition-keyed map and the same real fixture from two providers does not
  hash into two different `event_id`s. Exact-name pin only, same discipline as
  the ESPN and SportDB maps: bare `"Superliga"` is deliberately **not** in
  this map (Denmark and Romania both use the name) and must stay unresolved
  rather than be guessed.
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
