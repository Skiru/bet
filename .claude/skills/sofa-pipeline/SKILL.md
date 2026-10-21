---
name: sofa-pipeline
description: The shared contract of every sofa agent (Sofascore stats + Superbet prices, one coupon a day) - which file is the coupon (11_coupon.json -> KUPON_<d>.pdf), the stage flow, the confidence and print rules, the vetoes / reads / read_requests channels, how to run scripts, the hard rules. Preloaded into every sofa agent.
user-invocable: false
---

# sofa - the shared contract

You work on `sofa`: Sofascore statistics, Superbet prices, **one coupon a day**
for every sport (football, tennis, hockey, basketball, volleyball, CS2). This
file is your whole standing brief - you do not get CLAUDE.md. The code
(`scripts/sofa/`, `src/bet/sofa/`) is the authority; where this file and the
code disagree, the code wins - say so in your report.

There is no DISCOVER, ENRICH, ANALYZE, MARKET_CONTEXT or TIPSTERS stage
(retired 2026-10-05); discovery is BOARD.

## The product

| file (`runs/sofa/<d>/`) | what it is |
|---|---|
| `11_coupon.json` | **the coupon** (COUPON_ASSEMBLY). Read it through `confidence.coupon_artifact(run_dir)` (falls back to `08_confidence.json` on a day without 11) |
| `KUPON_<d>.pdf` | **the product the operator stakes**, rendered from 11. `KUPON_<d>.html` is a filterable view of the same legs |
| `12_printed.json`, `printed/<ts>.json` | the append-only print record; a rebuild locks from the first print |
| `08_confidence.json` | football / tennis legs - the INPUT of 11 (and of SETTLE), not the coupon |
| `08_confidence_sports.json` | hockey / basketball / volleyball / CS2 legs - input of 11 |
| `06_coupon.json` | the old priced VALUE selector - **never the coupon** |
| `13_results.json` | settled result of every printed position (a view of a finished day) |

`p_bar`, `required_odds`, `surplus`, `edge` and VALUE on `05_sheet.json` /
`06_coupon.json` are the old selector's priced numbers: they never enter the
coupon, its order or its confidence. A surplus above +0.40 is suspect by
construction.

**Locked legs.** A leg printed before its match started stays on the coupon
unchanged (`locked: true`, `printed_at_utc`), whatever reads or prices came
later; a leg a rebuild removed before its start stays removed. So any PDF
render is a print - a provisional PDF locks legs - except
`build_coupon_pdf.py --out <path>` / `--with-results`, which write no print
record. A locked leg is never a
defect, and a leg printed under an earlier rule (a mixed day) is judged by the
rule of its own print clock.

## The flow

Source of truth: `DEFAULT_SEQUENCE` and `STAGE_MODULES` in
`scripts/sofa/run_pipeline.py`.

| stage | how it runs | bridge | writes |
|---|---|---|---|
| BOARD | sequence | no (1 Superbet call) | `01_board.json` |
| RESOLVE | sequence | yes | `02_fixtures.json` (both clocks) |
| OFFER (twice: before and after SAMPLES) | sequence | no | `04_offer.json` |
| SAMPLES | sequence | yes, most of the run | `03_samples.json` |
| SHEET | sequence | no (~10 min parse) | `05_sheet.json` (`p_central`, `forecast_p`) |
| COUPON | sequence (last) | no | `06_coupon.json` - not the coupon |
| SHADOW / CS2 | `--only SHADOW`, `--only CS2` (loops) | no | `runs/sofa/{shadow/<sport>,cs2}/<d>/snapshots.jsonl` |
| SPORT_IDENTITY | `--only` or `run_sport_identity.py` | yes | `sport_fixtures.json` (pinned Sofascore ids) |
| FIXTURE_CHECK | in a rebuild, before CONFIDENCE | yes | `fixture_status.json` |
| CONFIDENCE | `run_confidence.py` (no `--only`) | no | `08_confidence.json` |
| SPORT_CONFIDENCE | `--only` or `run_sport_confidence.py` | no | `08_confidence_sports.json` |
| COUPON_ASSEMBLY | `--only` or `build_coupon.py` | no | `11_coupon.json` / `.md` |
| PDF | `build_coupon_pdf.py` (no `--only`) | no | `KUPON_<d>.pdf` + `.html`, `12_printed.json` |
| SETTLE (D-1 only) | `--only SETTLE` | yes | `07_settled*.json`, `data/sofa.db` |
| SHADOW_SETTLE / CS2_SETTLE | `--only` | yes | the sport's `settled.json` |
| FIT | separate, on a DB copy, operator's go | no | `config/sofa_*.json` |

A football fixture with `match_rule` set in `02_fixtures.json` (identity FUZZY)
came from a fallback rule switched on 2026-10-21 - `SEARCHED_ANCHOR:*`,
`SQUAD_LEVEL_ALIAS:*`, `SHORT_NAME:*` - and is never a cached verified name:
check its game by both names before trusting a leg. A rebuild may itself run
LATE_RESOLVE (new fixtures only) and SAMPLES / SHEET `--event-ids` (open
fixtures under a sample switch); never run those stages by hand. In
`03_samples.json`, an entry with `identity_gate: "per_family"` lost only the
metric family a contradictory payload touches, not the whole past match.

Exit codes everywhere: **0 OK, 1 PARTIAL, 2 FAILED**. PARTIAL on RESOLVE /
OFFER / SAMPLES (fixture gaps) or SPORT_CONFIDENCE (a sport `NOT_CALIBRATED`)
is the normal shape of a healthy run; only FAILED stops you, and a FAILED
stage stops the stages after it (`SKIPPED`).

## Confidence and what prints

- **Confidence comes from the statistics.** SHEET keeps the price out of
  `p_central`; CONFIDENCE / SPORT_CONFIDENCE map it through history curves
  (fitted on replayed history, never on our own settled days) to a calibrated
  lower bound. Line evidence (each key's own settled Superbet lines) can only
  **lower** it: an offset and a price-band cap. A key with no curve reads the
  Wilson bound of its own lines, else `NO_LINE_EVIDENCE`.
- **The price is only the betting condition** and may only lower a confidence.
  Disagreement with the price is never evidence either way.
- `forecast_p` ("model") is the rating's uncalibrated number, `sample_hit_rate`
  / k/n ("próbka") the raw sample: both shown, never gates.
- **A leg prints** when confidence >= 0.70, x = confidence x odds >= 0.90,
  ladder margin <= 15%, odds >= 1/0.9202 = 1.0867, not started (the earliest
  of RESOLVE's, Superbet's and FIXTURE_CHECK's clocks, 15 min margin), fresh
  price (football / tennis 45 min, measured sports 3 h; a moved price
  re-prices the leg). Every passing single prints - no page limit. Order:
  confidence, then earlier start, one match's legs together.
- **Bet Builders:** one per fixture, by `combined_probability`; stakeable at
  combined p x haircut odds >= 0.90 (internal). sofa never prints a builder
  price: the PDF says "kurs buildera: sprawdź na ekranie Superbetu".
- **Annotations, never gates:** `price_gap` (`CONFIDENCE_ABOVE_PRICE`:
  confidence > 1/odds + 0.03 - such legs realised about at their price;
  football, tennis and, from 2026-10-21, CS2),
  `peer` (★ the surer of two same-price legs of a match), stakes flags,
  `context_flags` (`MAKEUP_FIXTURE`, `LONG_LAYOFF`, `CONGESTED`).

Refusals you will meet (named on the row; each is the code working):

| name | meaning |
|---|---|
| `BELOW_CONFIDENCE_FLOOR` / `NEGATIVE_LEG_EV` / `ODDS_TOO_LOW` | under 0.70 / x < 0.90 / odds < 1.0867 (sports: `BELOW_FLOOR`, `BELOW_MIN_X`, `MARGIN_TOO_HIGH`) |
| `KICKED_OFF`, `STALE_PRICE` | started (earliest clock) / price too old |
| `NO_LINE_EVIDENCE` | no curve at p and too few own settled lines - not measured yet, never a defect |
| `NOT_CALIBRATED` | no usable curve (a sport without one: exit 1, the rest builds) |
| `NO_CLASS_CURVE` | women's football / tennis, tennis team cups read only their class's curves |
| `CROSS_LEAGUE_UNLINKED` | football rating cannot compare the two leagues |
| `NOT_SETTLEABLE` | (competition, family) cell Superbet / Sofascore cannot settle |
| `SAMPLE_CROSSES_SEASON` / `STALE_SAMPLE` | oldest observation > 180 days / newest > 60 days |
| `MODEL_ABOVE_OWN_SAMPLE` | football non-prop row (player props excluded): model > own hit rate + 0.15, automatic removal into `removed_by_reads` |
| `FIXTURE_NOT_AS_SCHEDULED` | postponed / cancelled per FIXTURE_CHECK (`UNVERIFIED` = not checked, never a refusal) |
| `FRIENDLY_FIXTURE`, `NO_LEAGUE_RATE` | friendly / competition under 30 matches (measured sports) |
| `NOT_IDENTIFIED`, `TOURNAMENT_NEVER_SETTLED`, `NO_MODEL_P`, `LINE_OUTSIDE_FIT` | sport identity missing / volleyball tournament with no settled event in 14 days / no model p (incl. CS2 without `best_of`) / CS2 team-rounds line outside 9.5-12.5 |
| `market_thin:` / `cap:` in `calibrated_on` | K13 cap / price-band cap lowered the leg - a cap, not a refusal |

## The channels into the product

Only three files change what an analyst or the verifier puts into the coupon.
Nothing can **promote** a leg.

- **`vetoes.json`** (`contracts.Veto`, strict) - removes rows everywhere
  (COUPON, CONFIDENCE, COUPON_ASSEMBLY): `{sofascore_event_id, market, subject,
  line, direction, reason_class, reason, context}`; null = all values;
  `reason_class` ∈ `SAMPLE_UNINFORMATIVE | CONTEXT | PRICE | OTHER`; written
  after SHEET, before COUPON. Football / tennis analysts write vetoes
  (OVER / UNDER); a measured-sport analyst writes NO_BET reads, never vetoes
  (COUPON_ASSEMBLY still applies a matching veto to sport legs,
  `coupon_sports.apply_reads`). A veto matching no sheet row and no sport game
  is `UNMATCHED_VETO`, never swallowed; `merge_reads.py` exits 1 only for a
  fresh one (carried ones are listed `(carried)`).
- **`reads.json`** (`contracts.LegRead`, strict, append-only) - one verdict per
  read leg: `{sofascore_event_id, market, subject, line, direction, period,
  verdict, author, reason, context}`, `verdict` ∈ `KEEP | WATCH | NO_BET`,
  `author` ∈ `analyst | verifier`. **WATCH and NO_BET remove** the leg into
  `removed_by_reads` (graded apart, never in the coupon's result); KEEP removes
  nothing. A sport leg: `market` = family, `direction` = side
  (`T1|T2|DRAW|ODD|EVEN|YES|NO|1X|X2|12` or exact score "3:1"), `period` =
  period / quarter / set / CS2 map; COUPON_ASSEMBLY applies it (`reads_sport`).
- **`read_requests.json`** - the operator's extra legs: `{"group_key":
  "sofa:<id>", "market"?, "line"?, "direction"?}` (or `{"position": n}`), each
  with `requested_by`, `at_utc`. Prefer `group_key`: positions shift every rebuild.

**The read set** (`confidence.legs_requiring_read`, audit C3): every unlocked
leg of the **30 best-value matches** (value = best leg's confidence x odds, a
`price_gap` leg's confidence capped at 1/odds + 0.03), every printed builder
leg, every requested leg. A rebuild moves positions, so re-read until C3 is
clean. Never compute it by hand:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <d> [--buffer N] [--unread] [--split K]
# -> runs/sofa/<d>/read_set/read_set_<sport>[_<i>].json; --unread for every re-read pass; --split K = parts of <= K matches
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <d> --report <md> [--report <md> ...] [--author analyst|verifier] [--dry-run]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/verify_legs.py --date <d> [--all] [--live]   # mechanical defect screen per leg; never redo its checks by hand
# exit 0 merged, 1 merged with an UNMATCHED_VETO, 2 refused (nothing written)
```

**Report-file contract.** Write the whole Polish report to the path the
caller gives with ONE Bash heredoc (`cat > <path> <<'MD' ... MD`); a re-read
pass appends `_r<n>` - never overwrite another report, take the next free
suffix.

- Analyst: `runs/sofa/<d>/<d>_analiza_<sport>[_<part>].md`, ending with
  ` ```json vetoes ` (football / tennis only) and ` ```json reads `; no other file.
- Verifier: `runs/sofa/<d>/<d>_weryfikacja.md`, one ` ```json reads ` block
  (author `verifier`); it may also write `read_set.py` / `verify_legs.py`
  outputs under its own scratch `--out-dir`.
- Both: no other ```json array in the report (`merge_reads.py` refuses an
  unclassifiable one); a report without a reads block breaks the contract.
  Return only the path, legs read, KEEP / WATCH / NO_BET counts, the veto
  count and anything the caller must act on (<= 12 lines). The caller runs
  `merge_reads.py` on the path and never re-types a report or an array.

## Running things

- Interpreter: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/<x>.py`
  (install with `.venv/bin/python -m pip`, never `.venv/bin/pip`).
- **Rebuild only with** `rebuild_day.py --date <d> [--dry-run]`: it refreshes
  stale prices first (a CONFIDENCE on a > 45 min offer empties 08 to the
  locked legs), re-runs SHEET only when a rule marker is missing, then
  FIXTURE_CHECK .. PDF and the audits. Never run the stages by hand except to
  debug. A `CONFIG_CHANGED` note means the sheet was priced on other fitted
  constants: report it, do not re-run SHEET on your own.
- **The bridge** (Sofascore answers 403 to any non-browser client):
  `.venv/bin/python scripts/sofa/ensure_bridge.py` first, always. Never lower
  `MIN_INTERVAL_MS`, never set `SOFA_MAX_CONCURRENCY` below the window count,
  never hammer Sofascore from your own client; a refusal (403 / 429) means stop
  and report, not retry harder.
- **Tool output economy:** never `cat` a large JSON or log; filter with a
  Python one-liner or `jq` to the rows you need, `head` / `tail` logs, send a
  long output to a file and grep it.
- **Git:** never `git stash` (other sessions share the tree), never
  checkout / restore files you do not own, never commit unless told.

## Hard rules

- The PDF rendered from `11_coupon.json` is the coupon. Reporting
  `06_coupon.json`, `p_bar` or `08_confidence.json` as the coupon inverts the day.
- Never invent a number, a fixture, a price or an availability. Unverifiable =
  say so (`UNVERIFIED`, "nie do zweryfikowania").
- Never print a combined / Bet Builder / parlay price, and never present
  `odds_if_product` (or `ev_if_product_priced`) as one - Superbet does not
  price a slip as the product of its legs (markup 8.8-19.6%).
- No stake sizing, no automated placement. The stake is the operator's.
- Name a leg shown to the operator in Superbet's words:
  `superbet_market: superbet_selection` from `11_coupon.json`
  (`bet.sofa.superbet_names.names` for a leg of another artifact) - never a
  paraphrase ("Seattle +1.5 w 3. tercji" was misclicked as a period total).
- Never read, echo or log `.env` values.
- Curves are fitted on the history of events and statistics; our own settled
  days are an audit of a curve, never its source. Line evidence only lowers.
- Never refit or install constants or calibrations without the operator's go,
  and never into a day already built; a refit runs on a copy of the DB.
- Never strip `UNFITTED_CONSTANTS` from a row or a report.
- **Sofascore and Superbet only** - no other provider (bzzoiro included) enters
  a read, a number or a source. Superbet sport ids `190` (virtual football),
  `75` (e-football), `157` (e-hockey), `70` (e-basketball) are simulations -
  never add them.
- A settled result is a fact about the day, not about the decision that made
  it: "it won" never enters the reasoning for the next one.
- Epochs are never pooled: compare days only inside one ledger group
  (`audit_ledger.py` groups them).
- Every claim names its file and field; a skipped check is named, never "it works".
- **Measure first.** A claim about the pipeline needs an out-of-sample
  measurement on settled rows or history, else call it a suspicion. Anything that changes what prints needs a switch in
  `bet.sofa.epochs`, and only the operator moves one. You never change code,
  config or what prints.
- A pooled number must say what it pooled across. Friendlies are out of
  samples and ratings (`bet.sofa.comparability`). "History is thin" is not an
  argument before `backfill_listings.py` has run.
- **A slip assembled in chat is not a coupon and has no gates.** For any
  table the operator may stake from: when the day does not support the
  request (N slips, a target price), say no first. "Supports" is measured -
  name the settled days and N, match bootstrap. Every such table carries the
  measured chance (a `price_gap` leg at its price, never its confidence); the
  product of confidences is never the headline.

## Language

Instructions and code are English. Everything the operator reads - reports,
reasons in `vetoes.json` / `reads.json`, summaries - is **Polish**.

## References (read on demand)

- `references/stages.md` - when you run, debug or explain one stage: inputs,
  flags, refusal vocabulary, failure shapes, the audits.
- `references/artifacts.md` - when you read or check a field of any artifact
  (01..13, fixture_status, sport_fixtures, shadow / CS2 files, ledger).
- `references/arithmetic.md` - when you re-derive a number: the sheet chain,
  the confidence chain, builders, the constants table.
- `references/traps.md` - before a rebuild, a re-read, a settle or a
  report: the mistakes that have already cost money.
- `references/model-state.md` - when a leg's market, switch, curve or epoch
  matters: which model packages and switches are on, mixed days, what is
  measured and not switched on.
- `references/commands.md` - when you need a command line beyond those above
  (settle, ledger, audits, refit, measurement, backfill).
