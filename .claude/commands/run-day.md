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
| `GO: quota corroborates all N` | Run with `--max-events 40` |
| `GO with --max-events N` | Run with **exactly** that N |
| `GO, but nothing will be corroborated` | Run, and say up front every row will be `SINGLE_SOURCE` |
| `NO-GO: no usable provider` | **STOP.** Report each blocked provider's `kind`. Write no file |

`understat` and `sackmann` are permanently dead upstreams. Never report them as
today's problem.

**If `highlightly` shows `quota_exhausted`, say so before quoting any coverage
number.** It is the dominant *discovery* source, so exhausting it shrinks the
slate itself rather than just the corroboration: measured 2026-08-28, the same
date gave 348 events with it available and 80 without — a 77% smaller day. Those
fixtures are missing from DISCOVER, not capped out of ENRICH, so they appear
nowhere in `by_readiness` and look like they were never scheduled.

## Step 2 — Run the pipeline

```bash
python3 scripts/simple/run_pipeline.py --date <resolved> -v --max-events <N>
```

DISCOVER → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE, one `run_id`.

**Never** pass `--skip-preflight`. Do not pass `--skip-market-context` or
`--skip-tipsters` unless the operator asked — both are optional columns and both
are excluded from the run verdict, so `market_context: FAILED` or
`tipsters: PARTIAL` in `step_verdicts` is **not** a reason to stop. Note it and
carry on.

Stop only on `FAILED` or `PRECONDITION_FAILED` from a non-optional step. Report
what a human must change and write no files — a coupons file with no coupons in
it is worse than its absence.

## Step 3 — Backfill once, then re-analyse

Read `enrich_metrics.by_readiness`. If any event is `BLOCKED` or `PARTIAL`, run
**exactly one** backfill pass:

```bash
python3 scripts/simple/run_enrich.py \
  --event-list runs/<date>/<date>_event_list.json \
  --output-dir runs/<date> \
  --backfill-from runs/<date>/<date>_event_dossiers.json \
  --max-events <BLOCKED+PARTIAL count> -v
```

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

```bash
ls runs/<date>/<date>_market_context.json runs/<date>/<date>_tipster_signal.json

python3 scripts/simple/run_analyze.py \
  --dossier runs/<date>/<date>_event_dossiers.json \
  --output-dir runs/<date> \
  --market-context runs/<date>/<date>_market_context.json \
  --tipster-signal runs/<date>/<date>_tipster_signal.json -v
```

## Step 4 — Build the coupons file

```bash
python3 scripts/simple/build_coupons.py --date <resolved>
```

No network, no DB, no quota — safe to re-run. It writes `<date>_kupony.md` and
`<date>_coupons.json` and prints a JSON receipt.

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

Exit code 1 means nothing cleared the bar. That is a real answer about a thin
day, not an error — say so plainly and still write the analysis.

**Never add a combined/parlay price to that file, in any form, however hedged.**
Corners, cards, fouls and shots in one match are strongly positively correlated,
so the product of the legs understates the slip's true probability in the
direction that flatters the bet. The contract types that field `None` so it
cannot hold a value; do not reintroduce one in prose.

## Step 5 — Analysis — agent `bet-analyst`

Hand it the date and ask for the per-match read. Its standing obligations:
cross-check the DB for other `run_id`s on that date, print the per-side
`a/b/h2h` split for every row, probe before claiming DB depth, and verify each
fixture is still on — preferring the **bzzoiro MCP tools** (`search_matches`,
`get_match_detail`) over WebFetch, since they hit the same paid provider the
pipeline uses.

Two things about those MCP tools, both learned the hard way on 2026-08-28:

* **A refreshed token does not reach a running session.** The MCP client binds
  its credential at session start, so a `${BZZORIO_KEY}` updated mid-session
  keeps returning `requires re-authorization (token expired)` while
  `run_pipeline.py` works fine off the same `.env`. The session must be
  restarted. If the analyst reports that error, put it in the run report rather
  than treating its thinner verification as a judgement it made.
* **Do not verify a fixture by team name.** `search_matches`' `team` filter is
  ignored server-side — a query for "Bayern" comes back with unrelated fixtures,
  and matching on the returned names then silently finds nothing. Every event in
  `EVENT_LIST` already carries `source_ids.bzzoiro`; pass that to
  `get_match_detail` and read `status` and `event_date`. That is exact, and it
  catches a postponement or a moved kickoff, which a clock filter cannot.

That verification carries WebFetch's ceiling: it may veto or downgrade a row,
never promote one, never enter `p_low`. The one promotion in this system belongs
to `row.market_signal` from the artifact, because that number is quota-tracked
and evidence-bundled.

## Step 6 — Write `runs/<date>/<date>_analiza.md`

**You write this file, not the analyst.** `bet-analyst` has no Write tool by
construction — an agent that can rewrite the artifacts it is judging can quietly
launder a bad day into a good one. It returns the markdown body; you save it.

Polish, because the operator reads it. Overwrite if it exists; the artifacts it
describes were overwritten too.

**Confidence % is `p_low` × 100** — the Wilson lower bound at 95% on
`hits`/`sample_size`, never the raw `hit_rate`. It is the sort key for the whole
file, descending.

Do not compute it yourself: it is a field on every `StatsSheetRow`, written by
`wilson_lower_bound()` in `src/bet/simple_stats/analyze.py`, and it is already
the order the artifact's rows arrive in. Read `row.p_low` and multiply by 100.

It penalises thin samples on its own, which is why nothing is sorted on
`hit_rate`: 6/6 is a hit rate of 1.000 but a `p_low` of 0.610, and 19/21 is
0.905 but 0.711 — so **19/21 ranks above 6/6** even though it has a worse raw
rate. If the ranking ever looks wrong to you, check `p_low` against the
function, not against this paragraph.

`sample_size` counts only observations that settle: a value sitting exactly on
the line is a push, reported in `row.pushes` and excluded from both `hits` and
`sample_size`, because it resolves neither side of that line.

````markdown
# Analiza <data>

**Run:** `<run_id>` · **Werdykt:** `<OK|PARTIAL>` · **Wygenerowano:** <UTC>
**Pokrycie:** <n> odkrytych → <n> wzbogaconych → <n> odciętych limitem
**Providerzy:** <ci, którzy realnie dali dane> · **Niedostępni:** <nazwa (kind)>
**Rynek:** <n> meczów z kursami, <n> z modelem rożnych · **Typerzy:** <n> meczów
**Kupony:** `<date>_kupony.md` — <n> singli, <n> kuponów BB

> Sortowanie po kolumnie *Pewność* — to dolna granica Wilsona 95%, nie surowy
> hit rate. `sample_size` łączy obie drużyny i h2h, więc obserwacje nie są
> niezależne i ta liczba jest optymistyczną podłogą, nie gwarancją.

## Mecze

### <Gospodarz> – <Gość> · <liga> · <HH:MM UTC>
<wiersze tego meczu, mean/median, co mówią surowe obserwacje, luki z data_gaps,
sygnał rynkowy z tagiem [BZZOIRO-ODDS: <ts>], weryfikacja z tagiem
[WEB: domena, data] lub [BZZOIRO-MCP: <ts>]>

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

The *Rynek* signal exists **only on `corners_total`** — bzzoiro publishes no
odds and no model probability for cards, fouls or shots on target, so `—` there
is the provider's coverage, not a gap. Line 11.5 always reads `—` because the
model serves only 8.5/9.5/10.5 and nothing is interpolated between lines.

## Step 7 — Report back

Short. The operator opens the file, not the chat:

```
KUPONY:  runs/<date>/<date>_kupony.md  — <n> singli, <n> kuponów BB
ANALIZA: runs/<date>/<date>_analiza.md
RUN:     <run_id> · <verdict> · <n> odkrytych → <n> wzbogaconych
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
