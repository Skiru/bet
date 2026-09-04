---
description: Run a betting day end to end, unattended, and produce the coupons file (singles + Bet Builder slips) plus the per-match analysis.
argument-hint: dzisiaj | jutro | YYYY-MM-DD
---

Run one betting day from nothing to a finished coupons file. The operator passes
only the day and walks away. **Do not stop to ask permission between steps** —
the whole point of this command is that it completes unattended. Stop only for
the three hard blocks named below.

Deliverables, in this order of importance:

1. `runs/<date>/<date>_kupony.md` — the coupons file. This is what the operator opens.
2. `runs/<date>/<date>_analiza.md` — the per-match reasoning behind it.

## Resolve the day first

`$ARGUMENTS` is one of `dzisiaj`/`today`, `jutro`/`tomorrow`, or `YYYY-MM-DD`.
Empty means today. Resolve in **UTC** — the pipeline's betting day is UTC:

```bash
date -u +%F                        # dzisiaj
date -u -v+1d +%F                  # jutro (macOS)
```

State the resolved date before anything else. If you cannot parse what was
passed, ask — do not guess a day and spend quota on it.

For a tomorrow-run say two things out loud: provider quotas reset at midnight
UTC so it spends **today's** budget, and tomorrow's fixture list is usually
thinner because fewer matches are published.

## Step 1 — Preflight (spends nothing)

```bash
python3 scripts/simple/run_pipeline.py --preflight
```

Quote the advice line, then act on it:

| Advice | Action |
|---|---|
| `GO: quota corroborates all N` | Run with `--max-events 250` |
| `GO with --max-events N` | Run with **exactly** that N |
| `GO, but nothing will be corroborated` | Run, and say up front every row will be `SINGLE_SOURCE` |
| `NO-GO: no usable provider` | **STOP.** Report each blocked provider's `kind`. Write no file |

### The local counter can be wrong — check it before believing a low `--max-events`

Preflight reads a **local** usage counter, not the provider's dashboard, and the
two drift. Measured 2026-08-28: the counter said `highlightly 72/100 used, 28
left` while highlightly's own dashboard showed **30% used**, and it said
`api-football 0 left` when that account was in fact `SUSPENDED` with **0
requests used** — failed calls had been counted as usage.

Historically this mattered most for `highlightly` as the dominant discovery
source; since 2026-09-04 football DISCOVER runs from `bzzoiro` only
(uncapped on PRO) and highlightly is out of the ENRICH roster entirely, so a
stale highlightly counter no longer shrinks the day. A pessimistic counter on
`bzzoiro` or `espn-football` is now the one worth catching.

```bash
python3 scripts/simple/reset_provider_quota.py --status          # spends nothing
python3 scripts/simple/reset_provider_quota.py --provider highlightly --yes
```

Reset only what you can see is wrong, and say in the run report that you did.
Resetting a counter whose provider really *is* part-used risks 429s late in
ENRICH — those land as data gaps, not a crash, but they cost coverage. A
`SUSPENDED` provider is unusable whatever the counter says: report it as
`kind=suspended`, not as quota.

**`entitlement_required` is not `quota_exhausted` and the reset script cannot
touch it.** The provider answered HTTP 402: it wants a plan or an addon bought.
Do not reset its counter, do not raise its `BET_LIMIT_*`, and do not tell the
operator to wait for midnight. Report it once, as a purchase decision, and run
without it. `bzzoiro-tennis` was the live case (a $5/mo Sports Addon) until it
was removed from the pipeline on 2026-09-02 -- and it sent `ratelimit: r=0` on
that 402, so if any provider goes from full to empty without a run that could
have spent it, suspect billing rather than repeating the reset advice.

`understat` is a permanently dead upstream. Never report it as today's problem.
`sackmann` was removed from the tennis roster on 2026-08-28 (both source
repositories 404) and should not appear at all; if it does, that is a repo
regression, not a provider outage.

**Check DISCOVER's own issues for `SPORT_EMPTY` and `SLATE_BELOW_FLOOR`
(added 2026-09-04) before quoting any coverage number.** These are the live
replacements for watching `highlightly`'s quota, which drove discovery breadth
until 2026-09-04 (measured 2026-08-28: 348 events with it available vs 80
without — a 77% smaller day) but no longer runs at DISCOVER at all
(`DISCOVERY_SOURCES_BY_SPORT` is bzzoiro-only for football, odds-api-only for
tennis). `SPORT_EMPTY: <sport>` means that sport discovered zero `ACTIVE`
events outright. `SLATE_BELOW_FLOOR: <sport>: N ACTIVE vs median M over W
prior runs` means today's count collapsed relative to that sport's own recent
history, whatever the cause — read `metrics.events_by_sport` for the numbers.
Either one demotes DISCOVER's verdict from `OK` to `PARTIAL` on its own; say so
before quoting `active_events` as if the day were normal.

### If the slate has tennis on it

Tennis providers are the ones that fail *quietly*, so they get one extra check
before the run — free, no quota, ~30 seconds:

```bash
.venv/bin/python scripts/simple/verify_tennis_providers.py
```

Exit 0 means each asserted provider resolved a real player on both tours and
named him correctly in every row it returned. Exit 1 is drift: a provider
stopped resolving, went stale, or started serving somebody else's matches.
**`MISIDENTIFIED` is the one verdict that must stop a tennis run** — it means
numbers belonging to another player would land on the sheet looking measured.
Report it and run football only.

If a previous run's cache may predate the 2026-08-28 tennis fixes, clear it
once — it is a dry run unless you pass `--apply`:

```bash
.venv/bin/python scripts/simple/purge_unproven_cache.py
```

It now also clears `espn/tennis/*/athlete_search/`, the cached name→id answers.
That matters because those have a seven-day TTL and a fix to a resolver does not
fix what the broken one already wrote: on 2026-08-28, 466 of them had been
produced by a matcher that accepted a shared forename or a surname substring,
including one mapping the literal string `TBD` to athlete id `-4`. They were
purged on 2026-08-28; if the report ever shows them again, purge before running.

**`verify_tennis_providers.py` cannot catch a crossing on today's players.** It
probes a fixed list of canary names, and it exited 0 on the day Qinwen Zheng's
sheet carried Lorenzo Musetti's matches. The real guard is now inside ENRICH:
every tennis payload is checked against the name the provider itself put on the
rows, and a payload naming somebody else is dropped whole with a
`MISIDENTIFIED` data gap. Read those gaps in the run report — one appearing is
the check working, not a new outage.

## Step 2 — Run the pipeline

```bash
python3 scripts/simple/run_pipeline.py --date <resolved> -v --max-events <N> --player-props
```

**`--player-props` costs ~20 extra bzzoiro calls per event** (one per outfield
starter) to fill player prop rows (shots, shots on target, fouls, cards). It
roughly doubles ENRICH's call volume, which is why it stays an explicit flag
rather than the default — but bzzoiro football is uncapped on PRO, so the cost
is time, not quota. **Timing:** a confirmed XI is usually available only
~1 hour before kickoff. For a morning run, most props will come off a
*predicted* XI (`lineup_status: predicted`), which caps every one of those rows
at tier `LEAN` (`bet_builder_draft.tier_for_row`) — do not expect `CALL` props
on a morning slate and do not wait for one that will not arrive. Every prop row
records which kind of XI it was built on.

Player props on a player either squad's `squad_availability` marks
`unavailable` are dropped before ANALYZE ever sees them
(`analyze.py:_unavailable_player_ids`) — a prop on an injured player is void,
not losing, and that filter is enforced in code now, not left to manual review.

**`--max-events 40` is too small and was the single biggest cost of the
2026-08-28 run.** 277 of 387 discovered fixtures came back BLOCKED reading "run
capped at 40 events", which looks like a quota problem and is not one: football
is uncapped on the PRO plan, and ESPN is free. 250 is the number to use unless
preflight says otherwise. Measured on that slate, going from 40 to 250 took the
sheet from 37 to 92 events and 2954 to 5218 rows.

The cap is now **split between sports** before ranking inside each one. It used
to be one global sort whose tie-break rewards corroboration -- and corroboration
is a property of the sport, not of the fixture. With 39 of 40 tennis fixtures
single-source, every tennis event ranked below every football event, the one
corroborated tennis match landed at position 41 under `--max-events 40`, and the
whole sport vanished while its own tennis quota sat unspent. Under
apportionment a cap of 40 gives tennis 4 slots and football 36; a sport that
cannot fill its share hands the slots back.

`--provider-call-budget` is **not** what throttled football, despite reading that
way. Only the native-id providers are metered by it. At the time this was
measured that was `bzzoiro` (overridden to 20000 in `RUN_BUDGET_OVERRIDES`) and
`highlightly` (a real daily ceiling of exactly 100); highlightly left football's
native-id roster on 2026-09-04 (`NATIVE_ID_PROVIDERS_BY_SPORT`), so the flag now
binds nothing at all for either sport -- bzzoiro has no ceiling to hit and no
other provider is metered by it. Leave it alone.

DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE, one `run_id`.

**SUPERBET runs second, and that is what makes the slate honest.** It moved
ahead of ENRICH on 2026-09-02 because ENRICH is the step that spends the
provider budget and it had no way to know which fixtures were on the board.
Measured on that day's run: of 325 dossiers, **113 were already past kickoff**
when ENRICH ran and **155 had no Superbet offer** -- about 82% of the slate was
enriched at full cost and could never reach a coupon.

ENRICH now reads the offer as a *slate gate* (`enrich.SlateGate`) and refuses
three kinds of fixture, each for a stated reason that lands in the dossier's
`data_gaps` as `not enriched: ...`:

1. **bzzoiro never discovered it.** The primary provider is addressed by native
   id, so a fixture it did not find has 6 metrics available instead of 55.
2. **Kickoff has passed.** Not backable pre-match. Not enforced when the run's
   date is in the past, so a backfill still works.
3. **Superbet prices the competition but not this fixture.** Only when it priced
   *other* fixtures of the same competition that day -- when it matched none of
   them, the silence is more likely our name join than the book, and the fixture
   is kept.

Expect a much smaller slate and a much higher READY share. On 2026-09-02 the
gate takes football from 287 fixtures to 25, and none of the survivors is
BLOCKED. `--no-slate-gate` on `run_enrich.py` turns it off for a backfill.

**Re-running a day: resume at `superbet`, not at `enrich`.** The offer is a
snapshot, and it is now an ENRICH input -- resuming at ENRICH re-gates the run
against prices from the first pass. `--start-at superbet` refreshes the board
and then re-enriches against it. It still requires an explicit `--max-events`.

**SUPERBET (added 2026-08-31) is the step that decides whether any of this is
bettable.** One public HTTP request for the day plus one per matched fixture,
no credential and no quota, against superbet.pl's own prematch offer. It exists
because bzzoiro's grid of ~88 bookmakers **does not contain Superbet**, so every
price this pipeline had before it was a reference to a book the operator does
not use.

What it buys, in one number: on the 2026-08-31 night slate, **eight of fifteen
singles were on lines Superbet does not list at all**. Not priced too short --
absent. The sheet prices `shots_on_target_total` at 4.5 and Superbet's ladder
begins at 7.5; `shots_total` 19.5 against a ladder from 24.5; `offsides_total`
1.5 against 2.5. Every ATP US Open tie was quoted best-of-five (sets 3.5/4.5,
games 24.5-46.5) against a sheet that only emits best-of-three lines, so not one
ATP row was placeable. None of that was visible from a reference price.

Read three fields off its `AGENT_SUMMARY` and lead with the first:

* `markets_with_no_line_overlap` -- market families Superbet lists but never at
  a line we generate. Non-empty means a **line-generator defect**, not a thin
  day; say so in the analysis under *Czego zabrakło*, with the market named.
  **It is absent from this step's summary, always, and absent does not mean
  empty.** It is computed only from the *comparison* artifact, and SUPERBET
  runs before ANALYZE, so no sheet exists yet at this point. Read it from the
  pipeline's own `AGENT_SUMMARY` instead — `run_pipeline.py` runs a free
  comparison-only pass after ANALYZE and hoists `markets_with_no_line_overlap`,
  `verdict_counts` and `value_rows` to the top level of its summary. Reading
  this step's silence as "no defect" is how the 2026-08-31 line-generator hole
  would ship unnoticed.
* `our_events_kicked_off` -- check it before reading `our_events_without_offer`
  as a matching failure. `offerState=prematch` drops a fixture the moment it
  goes live, so a run started after the first kickoff always finds some of its
  own fixtures missing from the book.
* `unmapped_market_names` -- a market Superbet added that we do not read.
  Report it; do not act on it.

`--skip-superbet` exists and should not be used casually. Skipping it does not
lose a column so much as return every `min_acceptable_odds` in the coupon to
being a target nobody checked.

**Never** pass `--skip-preflight`. Do not pass `--skip-market-context` or
`--skip-tipsters` unless the operator asked — both are optional columns and both
are excluded from the run verdict, so `market_context: FAILED` or
`tipsters: PARTIAL` in `step_verdicts` is **not** a reason to stop. Note it and
carry on.

Stop only on `FAILED` or `PRECONDITION_FAILED` from a non-optional step. Report
what a human must change and write no files — a coupons file with no coupons in
it is worse than its absence.

## Step 3 — Backfill once, then re-analyse

Read `enrich_metrics.by_readiness` **together with `slate_gate_drops`**. Since
2026-09-02 a large `BLOCKED` count is the normal, healthy shape of a gated run:
every fixture the slate gate refused is carried through as a BLOCKED dossier
with its reason. Subtract them before deciding anything —

```
BLOCKED worth backfilling = by_readiness.BLOCKED - sum(slate_gate_drops)
```

— and `slate_gate_drops.capped` is the only one of those four that a backfill
can help with. The backfill itself already knows this: it skips gate refusals
and reports `gate_refused_not_retried`, so running it when there is nothing to
retry costs a process start and no provider calls.

Also read the `bettable fixture dropped for want of a bzzoiro id` warnings.
Those are fixtures Superbet prices, in a competition bzzoiro covers, that
bzzoiro's `/events/` did not return — real bets the run chose not to make,
typically 0–4 a day. They are not fixable from here; report them.

If anything is left `BLOCKED` or `PARTIAL` after that subtraction, run
**exactly one** backfill pass:

```bash
python3 scripts/simple/run_enrich.py \
  --event-list runs/<date>/<date>_event_list.json \
  --output-dir runs/<date> \
  --backfill-from runs/<date>/<date>_event_dossiers.json \
  --max-events <BLOCKED+PARTIAL count> --player-props -v
```

Pass `--player-props` here too if Step 2 did — a backfill pass that drops it
would silently overwrite props ENRICH already collected for the merged events.

Report `backfill_improved_dossiers`. **Once only** — a third pass spends quota
to re-learn that the provider has nothing for those fixtures. A backfill is not
a retry of a failed run: if the first verdict was `FAILED`, stop instead.

**`<date>_run_summary.json` is not rewritten by these follow-up steps.** After a
backfill it still describes the first pass — its `by_readiness`, `total_rows`
and `steps_run` are stale, and it is the one artifact on disk not to quote from.
Take those numbers from each step's own `AGENT_SUMMARY` instead, and say in the
report that the summary lags.

Then re-run ANALYZE so the sheet reflects the merge. **Pass every optional
artifact that exists and none that does not** — ANALYZE rebuilds the sheet from
scratch, so an omitted flag silently drops that column and the backfill looks
like it *lost* data it never touched:

**`--event-list` is not one of the optional columns — pass it always.** It is read
for exactly one thing: each fixture's **competition name**, which the dossier does
not carry and which is the only input deciding whether a tennis tie is
best-of-five. Omit it and `tennis_match_format(None)` returns `None`, so the
best-of-five gate in `analyze.py:suppressed_markets_for` suppresses nothing and
`total_sets` / `total_games` / `aces_total` / `double_faults_total` rows for men's
Grand Slam ties come back onto the sheet. There is no error and no warning — the
sheet just gets bigger, and those rows sort to the **top** (`p_low` 0.78–0.84),
because "under 3.5 sets" is a tautology in best-of-three. Measured 2026-09-01:
dropping the flag put 19 ATP US Open events and 137 rows back, disguised as the
day's best bets, and the analyst spent its pass writing 113 vetoes by hand for
rows the code already knew how to suppress.

The tell is `events_covered` (93 without the flag vs 74 with it). Checking
`rows_by_market` is **not** enough: WTA alone produces the same
`total_games 228 / total_sets 38` counts, so the numbers look unchanged. Verify
instead that `ATP US Open` events have zero rows on the sheet.

```bash
ls runs/<date>/<date>_event_list.json runs/<date>/<date>_market_context.json \
   runs/<date>/<date>_tipster_signal.json runs/<date>/<date>_superbet_offer.json

python3 scripts/simple/run_analyze.py \
  --dossier runs/<date>/<date>_event_dossiers.json \
  --output-dir runs/<date> \
  --event-list runs/<date>/<date>_event_list.json \
  --market-context runs/<date>/<date>_market_context.json \
  --tipster-signal runs/<date>/<date>_tipster_signal.json \
  --superbet-offer runs/<date>/<date>_superbet_offer.json -v
```

**Re-run SUPERBET before ANALYZE, and compare after it.** Two passes, and they
are not the same pass.

*Before* — refresh the prices. They are a snapshot and by the time a backfill
has finished they are an hour old. One cheap public request per fixture, so
re-taking them costs nothing but time. **Do not pass `--stats-sheet` here.**

```bash
python3 scripts/simple/run_superbet.py \
  --event-list runs/<date>/<date>_event_list.json \
  --output-dir runs/<date> -v
```

*After* ANALYZE — compare, against the sheet that actually shipped:

```bash
python3 scripts/simple/run_superbet.py \
  --event-list runs/<date>/<date>_event_list.json \
  --offer runs/<date>/<date>_superbet_offer.json \
  --stats-sheet runs/<date>/<date>_event_dossiers_stats_sheet.json \
  --output-dir runs/<date> -v
```

`--offer` reads the offer already on disk: **no HTTP, no OddsPapi probe, and
the offer artifact is not rewritten.** It is free, and it is the only ordering
that gives an honest answer.

**Why the order matters, and it is not a nicety.** This used to be one pass
handed the sheet ANALYZE was about to replace, and the comparison could
therefore never describe the sheet that shipped. Measured 2026-09-02: the
comparison covered 8,958 rows over 56 events; the final sheet had 12,300 over
78. Twenty-two whole fixtures missing — Grasshopper–St Gallen (285 rows),
FC Thun (294), Falkirk–Rangers (289), Widzew (247), Harris–Tsitsipas (13). The
artifact said `verdict_counts.VALUE = 52`; the real answer was **82** (77 LEAN
+ 5 CALL), and 52 was reported to the operator as the day's yield.

`run_pipeline.py` now does this second pass by itself after ANALYZE and hoists
the three fields onto its own `AGENT_SUMMARY`, so on a full pipeline run you do
not have to. Run it by hand only when you re-ran ANALYZE by hand, as above.

Then read off that summary, and quote the first two in the run report:

* `markets_with_no_line_overlap` — `[]` is the healthy answer and now means it,
  because the field was actually computed. Non-empty means our generated lines
  and Superbet's ladder **do not intersect at all** for that market; it is an
  intersection test, not "nothing matched today", so an unmatched fixture no
  longer triggers it.
* `verdict_counts` / `value_rows` — how many rows are `VALUE` versus
  `PRICED_BELOW_THRESHOLD`. This is the day's real yield and the honest headline:
  measured 2026-09-01, 10,917 rows considered → 508 compared → **14 `VALUE`**
  against 494 priced below their own threshold.

**Do not recount VALUE by hand off the sheet with a flat 1.10 margin** — that
undercounts `CALL` rows, which use 1.05. See the `min_acceptable_odds` note in
Step 5.

This writes two sheets: `<date>_event_dossiers_stats_sheet.json` (every row)
and `<date>_event_dossiers_stats_sheet_top.json` (the same rows filtered to
`p_low >= 0.50`, the coupon's own floor). Hand the analyst the **top** file —
the full one is for audit and for chasing a row that never reached the floor.

## Step 4 — Analysis — two agents, one per sport

Two analysts, run **in parallel**, each on its own half of the slate:

| Agent | Covers | Source of record | Skills preloaded |
|---|---|---|---|
| `bet-analyst-football` | every `sport == "football"` event | bzzoiro MCP, by `source_ids.bzzoiro` | `bet-analysis-core`, `football-analysis` |
| `bet-analyst-tennis` | every `sport == "tennis"` event | none (`bzzoiro-tennis` is `402 addon_required`); WebFetch, two domains | `bet-analysis-core`, `tennis-analysis` |

Skip an agent whose sport has no event on the day's `event_list` and say so.
The split exists because the two sports share nothing but the row schema: the
football analyst reasons about a referee, a second leg and a derby the code's
flags missed; the tennis analyst reasons about surface, best-of-five, the
opposition class of a ten-match sample and a previous match's length. One
agent carrying both methods carried neither (the 2026-09-03 tennis section was
right about one estimand and silent about opponent quality until the operator
asked).

**Runs before the coupon exists** (docs/PLAN_BOGATE_STATYSTYKI.md Faza 5e,
Wariant A), against the stats-sheet **top** file from Step 3; its output feeds
the coupon build in Step 6.

### What to put in each prompt

Hand each agent the resolved date and one paragraph of run facts: verdict,
whether a backfill ran, `--player-props` on/off, providers that failed
(`highlightly quota_exhausted`, …), whether `verify_tennis_providers.py`
passed, the offer's `generated_at`, and `verdict_counts`/`value_rows` from the
pipeline's `AGENT_SUMMARY`. Then ask for **the per-match read of its sport and
the veto block**. Say explicitly:

* *football:* bzzoiro MCP is the source of record; every fixture on the sheet
  must be checked through `get_match_detail` by id (football is uncapped);
  read `round_name` and `previous_leg_event_id` there because the dossiers
  carry them as null; WebFetch is for what bzzoiro does not carry.
* *tennis:* there is no MCP; verify time and round against the tournament's
  order of play plus one independent domain; confirm the best-of-five gate
  ran (men's slam events must show no `total_sets 2.5` rows).
* *both:* the method document is `docs/SUPERBET_BET_BUILDER_METHOD_v3.md` and
  the agent must open the sections it cites. `bet_builder_draft.py`
  **implements** §44's builder score; what remains manual is §40 as a
  *scenario* test (a concrete scoreline satisfying every leg), the tail-risk
  penalty and the source-conflict penalty. Do not tell the analyst §44 is
  unimplemented — it will either duplicate the code's number or present a
  hand figure the artifact disagrees with.

Both agents already know the standing obligations from their skills: the
a/b/h2h split per row, DB depth probed not assumed, distribution over mean,
`FACT → CALCULATION → IMPLICATION → RISK`, buy case / kill case, price last,
`KEEP / WATCH / NO BET`.

### What comes back

From each agent: a Polish markdown body for its sport, then a fenced JSON
array of vetoes — `[{event_id, market, line, direction, action, reason_class,
reason}]`, contract in `.claude/skills/bet-analysis-core/references/
veto-contract.md`. `[]` is the common case. A `VETO` removes the row from the
coupon; a `DOWNGRADE` steps its tier down once, except that `reason_class`
`SAMPLE_NOT_REPRESENTATIVE` / `ESTIMAND_WRONG` zero the sample's weight and
`MISSING_REFEREE` doubles `k` (`coupons.py`). Nothing touches `p_low`.

Two things learned the hard way about the MCP tools, still true:

* **A refreshed token does not reach a running session.** If the football
  analyst reports `requires re-authorization (token expired)`, that is a new
  fault for the run report, not a judgement it made; restart the session.
* **Never verify a fixture by team name.** `search_matches`' `team` filter is
  ignored server-side; `get_match_detail` by `source_ids.bzzoiro` is exact.

## Step 5 — Write `runs/<date>/<date>_analiza.md` and `<date>_analyst_vetoes.json`

**You write these files, not the analysts.** Neither agent has a Write tool by
construction — an agent that can rewrite the artifacts it is judging can quietly
launder a bad day into a good one. Each returns a markdown body and a vetoes
JSON as text; you merge and save.

**Merging.** `<date>_analiza.md` = one day header (run, verdict, coverage for
both sports, providers, offer time, `verdict_counts`, the applied vetoes count)
followed by the football body under `## Piłka nożna` and the tennis body under
`## Tenis`, each verbatim. `<date>_analyst_vetoes.json` = the two arrays
concatenated into one bare array. Before saving it:

```bash
python3 - <<'PY2'
import json, pathlib, sys
sys.path.insert(0, "src")
from bet.simple_stats.bet_builder_draft import AnalystVeto
raw = json.loads(pathlib.Path("/tmp/vetoes_merged.json").read_text())   # your merge
ok = [AnalystVeto.model_validate(v).model_dump() for v in raw]           # extra keys fail here, on purpose
pathlib.Path("runs/<date>/<date>_analyst_vetoes.json").write_text(json.dumps(ok, ensure_ascii=False, indent=2))
print(len(ok), "vetoes")
PY2
```

An entry that fails validation (a `player_name` key, a bad `reason_class`) is
dropped and reported in the analysis as an unapplied WATCH — never repaired by
stripping keys, because a prop veto widened to `(event, market, line,
direction)` hits every player on the fixture (memory:
`analyst-veto-cannot-name-a-player`). Write `[]` if both agents returned
nothing, not a missing file, so the next step can tell "checked, nothing to
veto" apart from "the file never got written".

Polish, because the operator reads it. Overwrite if it exists; the artifacts it
describes were overwritten too.

**Confidence % is `p_low` × 100**, never the raw `hit_rate`. It is the sort key
for the whole file, descending.

**Do not reconcile it by hand against a Wilson calculator — it is not Wilson
alone, and has not been since `d1ef288f`.** `p_low` is the *lower* of two
bounds:

```
p_low = min( wilson_lower_bound(hits, sample_size),
             count_model_bound(values, line, direction, shrunk_mean) )
```

Wilson prices how few trials there were; the count model prices how far the
line sits from what those trials actually measured. Wilson alone cannot tell
4.5 from 7.5 on a clean sweep — that is the saturation defect that lost
2026-09-01, where one number rode the whole ladder and the coupon picked
whichever rung paid best.

The tell that both are live: **the same `hits`/`sample_size` gives different
`p_low` at different lines.** Measured on the 2026-09-02 sheet, `n=24 h=24`
reads 0.8436 at line 4.5 and 0.8620 at 5.5. On that sheet 44,477 rows are at
the Wilson value and 8,049 are below it because the count model bound bit
first. A row where the two disagree is not a broken sheet; it is the model
working.

The `_COUNT_MARKETS_EXCLUDED` families (percentages) have no count model
fitted, and there `p_low` **is** plain Wilson.

Do not compute either yourself: `p_low` is a field on every `StatsSheetRow`,
and it is already the order the artifact's rows arrive in. Read `row.p_low` and
multiply by 100. If the ranking ever looks wrong to you, check `p_low` against
`analyze.py`, not against this paragraph.

Wilson penalises thin samples on its own, which is why nothing is sorted on
`hit_rate`: 6/6 is a hit rate of 1.000 but a `p_low` of 0.610, and 19/21 is
0.905 but 0.711 — so **19/21 ranks above 6/6** even though it has a worse raw
rate.

`sample_size` counts only observations that settle: a value sitting exactly on
the line is a push, reported in `row.pushes` and excluded from both `hits` and
`sample_size`, because it resolves neither side of that line.

````markdown
# Analiza <data>

**Run:** `<run_id>` · **Werdykt:** `<OK|PARTIAL>` · **Wygenerowano:** <UTC>
**Pokrycie:** <n> odkrytych → <n> wzbogaconych → <n> odciętych limitem
**Providerzy:** <ci, którzy realnie dali dane> · **Niedostępni:** <nazwa (kind)>
**Rynek:** <n> meczów z kursami, <n> z modelem rożnych · **Typerzy:** <n> meczów
**Superbet:** <n> wierszy z ceną na ekranie · <n> z rynkiem bez naszej linii ·
<rodziny rynków z `markets_with_no_line_overlap`, gdy niepuste>
**Kupony:** patrz `<date>_kupony.md` (Krok 6 — powstaje z tej analizy, nie odwrotnie)

> Sortowanie po kolumnie *Pewność* — to dolna granica Wilsona 95%, nie surowy
> hit rate. `sample_size` łączy obie drużyny i h2h, więc obserwacje nie są
> niezależne i ta liczba jest optymistyczną podłogą, nie gwarancją.

## Mecze

### <Gospodarz> – <Gość> · <liga> · <HH:MM UTC>
<wiersze tego meczu, mean/median, co mówią surowe obserwacje, luki z data_gaps,
sygnał rynkowy z tagiem [BZZOIRO-ODDS: <ts>], weryfikacja z tagiem
[WEB: domena, data] lub [BZZOIRO-MCP: <ts>]>

*Sędzia:* <nazwisko, `avg_yellow_per_match` i `avg_fouls_per_match` ZAWSZE z
liczbą meczów, np. „5.8 żółtej/mecz przy n=15”. Gdy `referee` jest `null` —
„sędzia jeszcze nieznany”. To kontekst przy wierszu kartek i fauli, nie liczba
w nim: nie wchodzi do `p_low` i nie podnosi tieru.>
*Braki:* <z `squad_availability`: ilu wypada po każdej stronie i kto, gdy to
zmienia typ. Prop na zawodnika z listy `unavailable` to zakład VOID, nie
przegrany — usuń go i napisz dlaczego. Gdy `availability_unknown_count` jest
wysokie, zaznacz, że obraz kontuzji jest niepełny.>
*Forma sezonowa:* <z `season_form`: `xgf`/`xga` obu stron ZAWSZE z `xg_games`.
To jedyne sezonowe xG w systemie. Gdy `group` jest ustawione, zaznacz, że
`position` to miejsce w grupie, nie w lidze.>
*Okoliczności:* <tylko gdy realnie ważą: derby, neutralny teren, długi przejazd
`travel_distance_km`, pogoda. Jedno zdanie, nie tabela.>
*Superbet:* <z `row.superbet`: cena przy linii, którą realnie wystawia, i
`min_acceptable_odds` obok niej — **tej liczby nie ma na wierszu arkusza**,
wylicza ją `coupons.required_price()` jako `round(1/p_low × TIER_MARGIN[tier], 4)`
ze stałej `TIER_MARGIN = {"CALL": 1.05, "LEAN": 1.10}` (`bet_builder_draft.py`); `WEAK`/`DROP` nie mają marży,
bo nie są zakładem. Płaskie 1.10 zaniża próg dla wierszy `CALL`. Gdy `availability` to `LINE_NOT_OFFERED` —
napisz, jaką linię ma zamiast naszej; to nie jest zły kurs, to brak zakładu.
`SCOPE_NOT_SUPPORTED` (propy zawodników) to nasze ograniczenie, nie brak u
bukmachera — nie pisz, że Superbet tego nie wystawia. Cena jest zdjęta raz, o
godzinie z `generated_at` — podaj ją.>

## Sprzeczne (DISAGREE)
<obie wartości, obaj providerzy, bez rozstrzygania>

## Zdanie publiczności (inny rynek)
<tylko gdy typerzy pokryli mecze: `public_lean` z `<data>_tipster_signal.json`,
czyli 1X2/BTTS. Zaznacz, że to inny rynek niż totale i że jednego nie przelicza
się na drugie. Pomiń sekcję, gdy krok TIPSTERS nie działał.>

## Czego zabrakło
<jeden konkret, który najbardziej osłabił dzień, i akcja, która to naprawia>

---
Bez kursu łącznego, EV i stawki — celowo. Kurs sprawdzasz sam; typ poniżej
minimalnego kursu nie jest typem.
````

In football the *Rynek* signal exists **only on `corners_total` and
`goals_total`** (docs/PLAN_BOGATE_STATYSTYKI.md Faza 1 added goals) — bzzoiro
publishes no odds and no model probability for cards, fouls, shots on target or
any of the other collected-but-unpriced families, so `—` there is the
provider's coverage, not a gap. Corners' line 11.5 always reads `—` because the
model serves only 8.5/9.5/10.5 and nothing is interpolated between lines; goals'
0.5 and 4.5 read `—` the same way against a model that serves only 1.5/2.5/3.5.

**Tennis has a signal since 2026-08-30 — when it is paid for — and it never
promotes.** `total_games` at 21.5/22.5 and `total_sets` at 2.5 can carry a real
`model_probability`, but the verdict always reads `NO_MARKET_DATA` because no
tennis price is fetched — that would cost one call per match out of a 100-a-day
bucket ENRICH has usually already drained. Report the model number, say no price
was fetched for it, and never write `[CALL, promoted by market signal]` on a
tennis row.

**There is no tennis column, and that is now stated rather than discovered.**
MARKET_CONTEXT has been football-only since 2026-09-02. Its one tennis input
was bzzoiro's tennis model, which needed a paid Sports Addon ($5/mo), answered
`402 addon_required` on 2026-09-01 and 2026-09-02, and was removed with the
rest of that provider.

So tennis rows carry **no** `market_signal` at all -- not a `NO_MARKET_DATA`
verdict, which would read as "the model and the market were compared and did
not agree" when nothing was compared. Tennis verification rests on the Superbet
offer alone. MARKET_CONTEXT now says so
— read `tennis_model_unavailable` off its `AGENT_SUMMARY` and quote it under
*Czego zabrakło*. An empty list means the column was genuinely consulted.

## Step 5bis — Read the tipsters — agent `tipster-reader`

Free, no quota, one agent call. Skip it and the coupon's *Typerzy* column keeps
reading `brak` on almost every row.

TIPSTERS collects far more than it delivers, because it only keeps a pick it can
**count** -- a total with a readable line and direction. Measured 2026-09-03:
**55 picks ingested, 39 matched to a fixture, 2 countable.** The other 37 were
1X2, BTTS or inseparable combos: a different market, not a broken one. And of
the 2 it did count, one was wrong -- `MANTOVA POWYŻEJ 9.5 STRZAŁÓW` came through
as `player_total_shots` with `subjects: ["STRZAŁÓW"]`, the Polish word for
"shots" read as a player's name, `countable: true`.

`tipster-reader` reads the raw claim text and says what each pick means, in a
closed vocabulary. **It translates and nothing else** -- it never counts,
never scores a tipster, never emits a probability or a price. The arithmetic is
`src/bet/simple_stats/tipster_consensus.py`, in ordinary deterministic code, so
two runs over one day cannot disagree about how many people picked a side.

Hand it the signal path and save what it returns:

```bash
python3 scripts/simple/save_tipster_claims.py --date <resolved> \
  --readings /tmp/readings.json     # or '-' for stdin
```

**The agent has no Write tool and the script trusts nothing it says.** Every
reading must name a pick TIPSTERS actually collected, with the claim
**byte-identical**, and must use the closed market/direction vocabulary --
`bet.simple_stats.tipster_claims` rejects a paraphrased claim, an invented
tipster, a hallucinated market, a subject who is not playing, and a total with
no line. Rejections are counted per reading and reported; nothing is repaired,
because a repaired reading is one nobody wrote and nobody can check.

Read `parser_disagreements` off the `AGENT_SUMMARY`. It was **23 of 39** on
2026-09-03, which is why the step exists; near zero would mean the agent buys
nothing and the regex fallback is enough.

Measured effect that day, agent versus regex alone: unreadable picks **12 → 2**,
one *false* consensus removed (`1. połowa lub mecz: X lub X` had been labelled
a plain `DRAW`, but it is "draw at half-time **or** at full-time" -- strictly
wider), and one true consensus added that no regex could see (`Tabilo` and
`Wygra Tabilo` both resolving to Alejandro Tabilo from the fixture's own names).

Exit 1 means some readings were rejected -- note it and carry on; the section
degrades, it does not break. If the agent was not run at all, Step 6 falls back
to the regex path exactly as before.

## Step 6 — Build the coupons file

```bash
python3 scripts/simple/build_coupons.py --date <resolved> \
  --vetoes runs/<date>/<date>_analyst_vetoes.json \
  --market-context runs/<date>/<date>_market_context.json \
  --superbet-offer runs/<date>/<date>_superbet_offer.json \
  --tipster-signal runs/<date>/<date>_tipster_signal.json \
  --tipster-claims runs/<date>/<date>_tipster_claims.json
```

`--tipster-signal` and `--tipster-claims` add the closing *Zdanie typerów*
appendix: which fixtures two or more tipsters picked the same way, and every
pick on a fixture that reached the coupon, quoted verbatim. It is a **different
market** from the totals above it, so it carries no `p_low`, no minimum odds and
no value test, and `coupons.py` never receives it -- the boundary is enforced by
call order in `build_coupons.py`, not only by convention. Both flags resolve
from `--date`; a missing claims file falls back to the regex path.

`--superbet-offer` adds the **Superbet** column to both tables and re-ranks the
singles: a row the operator's own book prices at or above its
`min_acceptable_odds` sorts above one it does not, however high the second row's
`p_low`. It never changes `p_low`, `fair_odds` or `min_acceptable_odds` — a book
shortening a line must not lower our own bar.

Rows Superbet does not carry stay in the file and say why. The cell reads
`brak linii (ma 7.5)` when the market exists at another rung, `brak rynku` when
it does not exist, `brak meczu` when no Superbet fixture matched. **Do not treat
those as low prices and do not drop them** — "Superbet has no 4.5 line for shots
on target" is the most useful sentence the file can carry on a day like
2026-08-31, and dropping the row deletes it.

`--require-superbet-value` exists and is off by default. On a normal day it
empties the file, and an empty file is strictly less information than a full one
in which every row is honestly labelled unbettable.

No network, no DB, no quota — safe to re-run. It writes `<date>_kupony.md` and
`<date>_coupons.json` and prints a JSON receipt. A missing or empty vetoes file
is the default healthy state, not an error — pass the flag regardless of
whether Step 5 found anything to veto. `--market-context` is the same: both
flags also resolve on their own from `--date` if omitted, but pass them
explicitly so a reader of this command sees every input the coupon depends on.
If `comparison_entitlement` was ever anything but `ENTITLED`/`NOT_ATTEMPTED`
anywhere in the run, the coupon file's first line warns about it
(docs/PLAN_BOGATE_STATYSTYKI.md 3bis.6) — a lapsed "Football Unlimited"
entitlement removes goals' and corners' market price and model at once, which
is also what the edge ranking in Step 6's output depends on.

**It drops fixtures that have already kicked off**, and reports how many under
`excluded.kickoff_passed`. The cutoff defaults to now and is recorded in the
artifact as `not_before`; pass `--not-before <ISO>` to set it explicitly. This
matters most on a same-day run started late: without it a match that finished
overnight sits at the top of the file with 84% confidence beside it, looking
like the best bet of the day. The freed slots refill from the sheet, so the
number of singles does not drop.

For a day that has already been played — a post-hoc review, a settle pass —
pass `--include-started`, or every row is filtered and exit code 1 reads as
"thin day" when the day was full. The script prints a hint to stderr when that
is what happened, but do not rely on noticing it.

**Report its numbers verbatim and never recompute them.** Every threshold in
that file comes from tested code (`src/bet/simple_stats/coupons.py`); a minimum
odds re-derived in prose is exactly the failure `wilson_lower_bound` exists to
prevent. If a figure looks wrong, check the function, not your arithmetic.

**Every applied veto/downgrade is in the file's header notes, with its
reason** (Faza 5e) — read them off `coupons.notes` rather than cross-checking
Step 4's report by hand; the two must agree by construction, and if they do
not that is a bug in `build_coupons`, not a reason to trust the report instead.

Exit code 1 means nothing cleared the bar. That is a real answer about a thin
day, not an error — say so plainly and still write the analysis.

### Verify every fixture that reached the coupon, through bzzoiro MCP

The script filters on the **clock** — `not_before` versus kickoff. A clock
cannot see a postponement, a venue switch or an abandoned match, so a fixture
called off an hour ago still sits in `<date>_coupons.json` looking bettable.
This is a **second, later** check than Step 4's — it exists precisely to catch
anything that changed between the analyst's read and this file being written.

So after the file is written, for each fixture in it:

```
mcp__bzzoiro__get_match_detail(match_id = <event's source_ids.bzzoiro>)
```

Read `status` (`notstarted` / `inprogress` / `finished`) and `event_date`.
Football is uncapped — a coupon of a dozen fixtures costs a dozen calls and
those are free. Then:

* `status` is anything but `notstarted`, or `event_date` no longer matches the
  artifact's `start_time` → **strike that fixture from the coupons file** and
  say why in the report. A moved kickoff invalidates the bet without changing a
  single statistic.
* the event carries no `source_ids.bzzoiro` (some other source found it alone)
  → say it could not be verified, rather than implying it was.

Report the count checked and the count struck. **Never present an unverified
coupon as verified** — silence about a check you skipped reads exactly like a
check that passed.

**Never add a combined/parlay price to that file, in any form, however hedged.**
Corners, cards, fouls and shots in one match are strongly positively correlated,
so the product of the legs understates the slip's true probability in the
direction that flatters the bet. The contract types that field `None` so it
cannot hold a value; do not reintroduce one in prose.

## Step 7 — Report back

Short. The operator opens the file, not the chat:

```
KUPONY:  runs/<date>/<date>_kupony.md  — <n> singli, <n> kuponów BB
ANALIZA: runs/<date>/<date>_analiza.md
RUN:     <run_id> · <verdict> · <n> odkrytych → <n> wzbogaconych
WETA:    <n> vetoed, <n> downgraded (0/0 if neither analyst found anything to flag) · piłka <n> / tenis <n>
SUPERBET: <n> z <n> singli osiąga minimalny kurs · <n> bez linii na ekranie
UWAGA:   <the single biggest weakness of the day, one line>
```

Do not paste either file's tables into the chat.

## Hard rules

- Never invent a number, a fixture, or an odds quote.
- Never print a combined / Bet Builder / parlay price, however hedged.
- No stake sizing. No EV. No automated placement. Ever.
- Never read, echo or log `.env` values, keys or tokens.
- Quoted `market_price` is the best of ~88 bookmakers and **there is no Superbet
  among them** — always label it as a market reference, never the operator's price.
