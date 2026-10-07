---
name: sofa-analysis-core
description: The contract every sofa sport analyst works under - which legs of the one coupon (11_coupon.json) to read (the first 30 positions, every printed builder leg, read_requests.json), which artifact to open in which order, which number is evidence (pewność, próbka, model) and which is the price (only the betting filter), what may remove a leg and what may never promote one, the vetoes.json schema, the reads.json per-leg verdicts (KEEP / WATCH / NO_BET, with the measured sports' sides and periods) that remove a watched leg into removed_by_reads (graded apart in audit_settlement 7i), the decision point that keeps a search result from contaminating a read, and the report format. Preloaded into sofa-analyst-football, sofa-analyst-tennis and sofa-analyst-sport; the sport skills sit on top of it. Use when reading a sofa coupon or stats sheet, grading coupon legs or Bet Builder legs, or writing vetoes and reads.
user-invocable: false
---

# The analyst's contract under `sofa`

The pipeline has already produced the candidate pool, the prices and the
arithmetic. Your job is the part no code does: decide, for each row that
matters, **whether the sample it is built on is evidence about this fixture**
— and say so in a form the machine can act on.

You never run the pipeline, never write files, never touch the DB, never price
a parlay, never size a stake. Bash is for reading and arithmetic.

`sofa-pipeline` is the pipeline contract and outranks this file on artifacts
and formulas. The sport skill (`football-analysis` / `tennis-analysis`) is the
method and outranks both on *how to weigh evidence*. The artifacts outrank
everything on *facts*. When they disagree, say which you followed.

## The coupon, and which of its legs you read

`sofa` writes two different objects and an analyst who reads only the first
has audited the wrong file:

1. **`06_coupon.json`** — the old VALUE selector, ranked on relative price
   advantage (`surplus / required_odds`), every quantity in it priced
   (`p_bar`, `required_odds`, `surplus`). Measured **−20.4%** on 2026-09-20,
   structurally anti-selective. It is **not** the coupon and needs no read.
2. **`11_coupon.json` → `KUPON_<date>.pdf`** — the one coupon (COUPON_ASSEMBLY,
   `scripts/sofa/build_coupon.py`, from `08_confidence.json` and, since
   2026-10-05 08:30Z, `08_confidence_sports.json`): football, tennis, hockey,
   basketball, volleyball and CS2 singles numbered 1..N in
   `confidence.coupon_order` (confidence, then the earlier start, the legs of
   one match together) and Bet Builders B1... Every reader opens it through
   `confidence.coupon_artifact()`, which falls back to `08_confidence.json`
   on a day built before the stats-only epoch (2026-10-05 07:15Z).

**Who reads what.** The set `audit_variants` C3 requires an analyst read on
is `confidence.legs_requiring_read(doc, load_read_requests(run /
"read_requests.json"))`: the first 30 unlocked positions, every leg of a
printed builder, and every entry of `runs/sofa/<date>/read_requests.json` -
the operator's extra positions (`/sofa-analyze` "dodatkowo: ..."), keyed by
`position` or, better, by `group_key` (`"sofa:<id>"`, optionally `market`,
`line`, `direction`), since positions shift after a rebuild. Each analyst
reads its own sport's part of that set (`sofa-analyst-football`,
`sofa-analyst-tennis`, one `sofa-analyst-sport` per measured sport). The
rest of the coupon prints unread by the operator's rule; a WATCH or NO_BET
you do write on such a leg still removes it.

A leg marked `locked` was printed by an earlier build (carried from
`12_printed.json`) and its match has started: it stays on the coupon
whatever a read now says. Read it only if asked, and say your read cannot
remove it. Bet Builders are assembled from `08_confidence.json` (football,
tennis) only: a measured-sport leg is never a builder leg.

**The measured sports** (hockey, basketball, volleyball, CS2) have no sheet
row and no entry in `03_samples.json`: the leg itself is the row (`family`,
`period`, `subject`, `side`, `confidence`, `sample_k` / `sample_n`,
`forecast_p`), and the evidence is `sport_fixtures.json` (the pinned
identity) and the raw Superbet snapshot. Steps 2-5 below are the football /
tennis method; `sofa-analyst-sport` is the sport one.

## Order of operations — never reverse it

0. **State the expectation, in the units the market settles in**, before any
   price is mentioned. *Expect 9.8 corners; the sample's ten matches ran 6–15;
   at n=10 and `K_CENTRE=15` the league prior owns 60% of that centre.* A
   report that opens with what pays has put the operator's decision before the
   analysis.

1. **The decision point, before any web tool runs.** Per fixture:
   scheduled start in UTC (**both clocks** — `kickoff_utc` and
   `superbet_kickoff_utc`), `now`, the delta. A fixture that has started is
   dropped **here**, not researched and then discarded. See *The decision
   point* below.

2. **Data integrity — the core of the job.** Open `03_samples.json` and look at
   the observations, not the summary: how many, from which matches, what date
   range, against which opponents, `side_a` vs `side_b` vs `h2h`. Check
   `gaps[]` for this metric. Ask whether `subject` resolves to the side it
   thinks it does — after the side-matching work that is the most fragile
   join in the pipeline.
   Since 2026-10-04 the history excludes friendlies and pre-season
   tournaments everywhere (`bet.sofa.comparability`), and a football goal
   sample (`goals_total`, `goals_for`, `goals_1h_for`, `goals_2h_for`) holds
   only the side's newest REGULAR (non-knockout) matches of the fixture's
   own competition when it has five or more (`comparability.
   pick_same_competition`; else the usual newest ten). A cup or friendly
   observation in the goal sample of a league fixture whose sides have five
   such matches is therefore a **defect to report**, not a caveat.

3. **Does the market settle what the sample measures?** Scope (half vs full
   match), side (own vs pooled), extra time, and the metric's own definition.
   `cards_points` is not yellow cards. `totalShotsOnGoal` in the raw payload
   is all shots.

4. **Context that changes the estimand** — stakes, round, second leg
   (`previous_leg_event_id`), derby, referee (`RefereeRecord`, present on ~9%
   of fixtures), absences, surface (`ground_type`), format
   (`default_period_count`), fatigue. See `references/evidence-rules.md`.
   The fixture's `schedule` block in `03_samples.json` (`makeup_of`,
   `makeup_postponed_utc`, per side `rest_days`, `matches_7d`, `matches_14d`)
   and the legs' `context_flags` (`MAKEUP_FIXTURE(...)`, `LONG_LAYOFF(...)`
   at >= 21 days, `CONGESTED(...)` at >= 3 matches in 7 days) are computed
   for you. A make-up fixture: find out **why** it was postponed (illness in
   the squad, weather, a cup clash) - the 2026-10-04 Farense - Chaves was a
   round-5 make-up after a viral outbreak and nothing flagged it.

5. **Distribution and scenario** — mode, tail, where the line sits inside the
   sample's own range, what scoreline or game script produces it.

6. **Kill case, then buy case; the price only as the filter it is.** The
   price is never evidence: it decides only whether the leg may be bet at all
   (x = confidence x odds >= 0.90, ladder margin <= 15%, not started, a fresh
   price) and the code has already applied that. A good price cannot rescue
   a broken sample, and a short price is not a reason to drop a leg. No later
   step redeems an earlier hard fail.

7. **Verdict** — `KEEP / WATCH / NO_BET` — the read entry for every leg of
   your read set, and the veto entry if any. The verdict is no longer prose
   only: see *The two JSON blocks* below.

## Artifacts, in the order you open them

```
runs/sofa/<date>/11_coupon.json       THE COUPON — positions, blocks, builders, removed_by_reads, read_requests
runs/sofa/<date>/read_requests.json   the operator's extra reads (may be absent)
runs/sofa/<date>/02_fixtures.json     names, competition, both clocks, round, referee, surface
runs/sofa/<date>/fixture_status.json  FIXTURE_CHECK's fresh start and status (may be absent)
runs/sofa/<date>/03_samples.json      THE EVIDENCE — raw observations with dates and opponents
runs/sofa/<date>/05_sheet.json        every priced rung; the row behind a football / tennis leg
runs/sofa/<date>/04_offer.json        the prices, each with its own fetched_at_utc
runs/sofa/<date>/08_confidence.json   football / tennis legs and refusals (what 11 was assembled from)
runs/sofa/<date>/08_confidence_sports.json   measured-sport legs and per-sport refusals
runs/sofa/<date>/sport_fixtures.json  the measured sports' pinned Sofascore identities (IDENTIFIED / NOT_IDENTIFIED / DUPLICATE_*)
runs/sofa/shadow/<sport>/<d>/snapshots.jsonl, runs/sofa/cs2/<d>/snapshots.jsonl   the raw Superbet snapshots behind a sport leg
runs/sofa/<date>/06_dropped.json      every VALUE row the old selector did NOT select, with a reason
runs/sofa/<date>/reads.json           reads already recorded (an earlier pass, the verifier) — may be absent
runs/sofa/<date>/KUPON_<date>.pdf     what is staked
```

Filter by `sport` (a builder leg carries none - take the builder's match
from `02_fixtures.json`). Count your sport's printed legs and your read set
yourself; a count handed to you by an orchestrator may predate a rebuild.

Resolve every `sofascore_event_id` to names, competition and kickoff before
showing it to a human. It is an integer, not a hash.

`06_dropped.json` exists so nothing vanishes in silence. Before saying a row
was never generated, look for it there.

## Which number is which

| field | what it is | what it is not |
|---|---|---|
| `sample_mean`, `sample_sd`, `sample_size` | the raw sample | the centre |
| `centre` | the mean **after** shrinkage toward the prior, `w_c = n/(n+K_CENTRE)`; a football row with a `FOOTBALL_RATING` note is 0.5·rating + 0.5·that | the sample's claim |
| notes `CROSS_LEAGUE_UNLINKED` / `PRIOR_GLOBAL_WOMEN` | the sides share no league and no measured league strength (CONFIDENCE refuses it, the price decides) / a women's league shrunk to the women's pool | a reason of its own to veto - the code has already acted |
| `calibrated_on` prefix `women:` / `tennis_women:` / `tennis_team_cup:` | the leg read only its class's curve; a class leg without one is refused (`NO_CLASS_CURVE`) | the pooled curve |
| `p_central` (`model_p` on a leg) | the sample's probability. **Stats-only row (`epoch: "stats_only"`): no price in it** - no ladder centre, no rating blended with the price, no shrink to the rung's price. On an older row a tennis priced rung was pulled onto the price (`TENNIS_RATING` 0.25·rating + 0.75·`market_p`; `P_SHRUNK_TO_PRICE` w·hits/n + (1−w)·`market_p`, w = n/(n+30)). Count markets (aces, DF, serve points) and football: count model (football negative binomial). From 2026-10-07 14:05Z (`epochs`): tennis `games_won_for` / `handicap_games` / `most_games` are priced by the rating alone and `games_total` is 0.5·rating + 0.5·NB (`TENNIS_RATING_PRICES`); football goals / corners / shots-on-target / cards joints are built from the marginal rows' centres (`DERIVED_MARGINAL_CENTRES`); a thin basketball side simulates with more noise (`BB_FRESHNESS`). | the sample hit rate |
| `forecast_p`, `forecast_source` | **model** - the rating's own forecast (`football_rating` / `tennis_rating`; `score_model` / `cs2_engine` on a measured-sport leg), uncalibrated, printed beside the confidence | a gate, the sort order, or a reason in a read |
| `calibration_correction` | subtracted before the price blend; one-sided, can only lower `p` | evidence |
| `market_p` | Superbet's price, power-devigged. `null` = one-sided rung, no devig possible. | our number |
| `p_bar` | `w·p + (1−w)·market_p`, `w = n/(n+10)` - priced, the old VALUE selector's | a forecast, the confidence |
| `ladder_centre`, `ladder_sigma` | **the bookmaker's** ladder | our distribution |
| `surplus` | `offered − 1.10/p_bar` — `06_coupon.json`'s sort key, priced and anti-selective | an edge, anything on the coupon |
| `sample_newest_days` | age of the newest observation | sample span |
| `confidence` | **pewność** - the **measured lower bound** of the realised rate (`calibrated_on`, `calibration_n`; football / tennis `config/sofa_confidence_calibration.json`, measured sports `config/sofa_sport_confidence_calibration.json`, the staged `.next.json` from its `effective_from`), from the statistics alone on a stats-only day; from 2026-10-07 10:55Z the lowest of that curve lowered by the key's Superbet-line offset and the price-band cap, or - with no curve at that p - the Wilson bound of the key's own settled Superbet lines (`calibrated_on` `sb:<sport>:<key>`), else no leg (`NO_LINE_EVIDENCE`); the coupon's sort key | the model's claim (`model_p`, `forecast_p`), or a price |
| `line_offset`, `price_band_cap` | present on a leg that line evidence lowered: the key's measured realised-minus-confidence (<= 0), and the realised rate of the key's lines in this price band; the price only ever lowers a confidence | a blend of the price into the confidence, a reason in a read |
| `sample_hit_rate`, `sample_size` (`sample_k` / `sample_n` on a sport leg) | **próbka** k/n - how often the line held in the leg's own sample | `model_p`; a football leg with `model_p` more than 0.15 above it (n >= 5) is removed in code (`MODEL_ABOVE_OWN_SAMPLE`, an automatic WATCH into `removed_by_reads`) |
| `offered_odds` (`odds` on a sport leg), x | the price, and x = confidence x odds (a field `x` on a sport leg) - the betting condition (x >= 0.90) | evidence |
| `family`, `side`, `period`, `subject` (sport leg) | what a read keys on: `market` = `family`, `direction` = `side`, `period` (0 = whole match / half markets), `subject` = `""`, `T1` / `T2`, a CS2 team name or a player | the PDF's label (a handicap's `line` is team 1's; the page prints it signed for the side) |
| `leg_ev`, `shading` | `confidence·odds − 1`, `confidence − 1/odds` | Superbet's builder price, or an edge |
| `context_flags` | `MAKEUP_FIXTURE` / `LONG_LAYOFF` / `CONGESTED` from the schedule | a gate - shown, never enforced; a question you answer |
| `reads` | the reads covering the leg | your read, unless you wrote it |
| `removed_by_reads` (11) | legs that passed every gate and a read (or `MODEL_ABOVE_OWN_SAMPLE`) removed, with `refusal` and `reason` (who) | the coupon - graded apart in audit_settlement 7i, ledger `removed:reads` |

**The one arithmetic rule:** `p_central`, `confidence`, `forecast_p`, `x`
(and the priced `p_bar` / `required_odds`) come from tested code. Read them; never recompute them in prose.
You *may* and should recompute them **from the row's own fields** to check the
row is internally honest — that is a different act, and say which you are doing.

## What may move a row, and in which direction

- **Context, web, referee, absences, stakes: may remove a row. May never
  promote one.** There is no promotion mechanism in `sofa` and you must not
  invent one. A blog is not a sample; a referee's average is not an observation
  of this fixture.
- **A price is a snapshot.** Each football / tennis rung carries its own
  `fetched_at_utc`; both COUPON and CONFIDENCE refuse anything older than 45
  minutes, and on a stats-only day a moved price re-prices the leg (x at the
  fresh odds); a sport leg names its snapshot (`source_date`,
  `price_fetched_at_utc`; refused beyond `sport_day.MAX_PRICE_AGE`, 3 h).
  Say which snapshot you quoted; the price never enters your verdict.
- **Refunds are not losses.** A match moved > 48 h, awarded, a walkover or a
  retirement (Sofascore code 92 in tennis) settles as a refund, 0 u. (operator,
  2026-10-07; `settle.REFUND_REASONS`; sports: `AWARDED`). A late withdrawal
  announced before the start is a read's material; a retirement is not
  knowable beforehand.
- **A market we generate no row for is not a bad bet, it is not a bet.**
  `unmapped_markets` runs to five figures. Writing "weak value" about a market
  nobody priced reads as a decision when nothing was decided.
- **Never multiply legs yourself, and never print a combined price.** sofa
  does not price a Bet Builder: the PDF shows the legs with Superbet's single
  prices, the builder's `combined_probability` and "kurs buildera: sprawdź na
  ekranie Superbetu". `odds_if_product`, `odds_after_haircut` and
  `ev_after_haircut` are internal (the haircut decides *stakeable*) and are
  never quoted as a price.

## The two JSON blocks — what reaches the product

After the markdown report, return **two** fenced ```json blocks, in this
order: the vetoes, then the reads. Each is a bare array. The runner writes
the first to `runs/sofa/<date>/vetoes.json` and merges the second into
`runs/sofa/<date>/reads.json`; **CONFIDENCE and COUPON_ASSEMBLY read both**
(and the old COUPON stage too).

### Block 1 — vetoes (a broken sample or context; removes everywhere)

`[]` when nothing earns an entry.

```json
[{"sofascore_event_id": 15275920, "market": "corners_total", "subject": null,
  "line": 9.5, "direction": "OVER",
  "reason_class": "SAMPLE_UNINFORMATIVE",
  "reason": "seven of ten observations predate the 12 Aug manager change; the three since ran 4, 5, 6"}]
```

- `market` / `subject` / `line` / `direction` are nullable and `null` means
  **all of them**. That is the normal shape: a sample that does not describe
  the fixture is broken at every rung, not at one of them.
- `reason_class` ∈ `SAMPLE_UNINFORMATIVE | CONTEXT | PRICE | OTHER`.
- A `CONTEXT` veto also sets `context` ∈ `MOTIVATION | ROTATION | ABSENCES |
  DERBY | SCHEDULE | CONDITIONS`, and its `reason` names the source domain and
  publication time. The settlement audit grades every tag separately
  (section 7e); an untagged one is graded as bare `CONTEXT` and says nothing
  about which read worked. Sources: `references/context-sources.md`.
- `sofascore_event_id` is an **integer**.
- A veto matching nothing prints `UNMATCHED_VETO` and is counted in both
  stages' summaries. It is never silently swallowed — but it also did nothing,
  so check your keys against the sheet before you hand it over.
- Only rows you would strike or caveat. **Every caveat is not a veto.**

### Block 2 — reads (one verdict per leg of your read set)

```json
[{"sofascore_event_id": 17009055, "market": "goals_total", "subject": "",
  "line": 3.5, "direction": "UNDER", "verdict": "WATCH", "author": "analyst",
  "reason": "Chaves' last four 4/5/4/5 goals; make-up of round 5 (postponed 6 Sep, viral outbreak)",
  "context": null}]
```

**One `LegRead` per leg of your read set** (above: your sport's part of the
first 30 positions, the printed builder legs, `read_requests.json`).
`author` is always `"analyst"`; the eight required keys present
(`sofascore_event_id`, `market`, `subject`, `line`, `direction`, `verdict`,
`author`, a non-empty `reason`; `context` and `period` may be left out; the
model is strict, `extra="forbid"`); matching is the veto's (`null` covers
every value - count what a WATCH / NO_BET will hit; `""` is not `null`). A
measured-sport leg is read with `market` = its `family`, `direction` = its
`side` (`OVER` / `UNDER` / `T1` / `T2` / `DRAW` / `ODD` / `EVEN` / `YES` /
`NO` / an exact score `"3:1"`), the leg's own `subject` and `line`, and
`period` (hockey period, quarter, set, CS2 map; `0` the whole match) - reads,
not vetoes, because `Veto.direction` is `OVER` / `UNDER` only and a veto has
no period.

| verdict | the coupon (`11_coupon.json`, `KUPON_<d>.pdf`) |
|---|---|
| `KEEP` | stays; records that the leg was read |
| `WATCH` | **removed** (`WATCHED`) into `removed_by_reads` |
| `NO_BET` | **removed** (`READ_NO_BET`) into `removed_by_reads` |

A removed leg is graded on its own - audit_settlement 7i ("Nogi zdjęte przez
odczyt"), ledger variant `removed:reads` - and never in the coupon's result,
so the ledger measures whether reads remove losers. A leg of your read set
that has no read of yours fails `audit_variants.py` C3, so a leg you leave
alone still gets its `KEEP`. `WATCH` is not a soft veto and not a hedge:
write it for a leg you would not stake. A sample that does not describe the
fixture is still a veto, not a `NO_BET`.

Worked examples, the widening trap and the reads schema:
`references/veto-contract.md`.

## The decision point — the web index runs ahead of you

Every web read is made *after* the decision it informs. A search index carries
content published after a fixture started, and a snippet renders it in your
context before you choose to open anything.

1. Establish the decision point **before any web tool runs**: per fixture, its
   scheduled start in UTC on both clocks, `now`, the delta. Print them.
2. **A fixture already started is not a bet and not a research subject.** Drop
   it first. Searching about a match that has begun is asking the index for the
   answer; not searching costs nothing, because there was no bet there.
3. **Titles and snippets are content.** Construct queries that cannot return a
   scoreline: the historical fact and its period, never the two participants'
   names alone.
4. **If a result leaks, say so.** Name the fixture, name what leaked, mark the
   claim `CANNOT VERIFY` — never `unknown`, never silently omitted. A leak you
   declare costs one fact. A leak you absorb produces a read that looks better
   than any honest read of the same evidence and cannot be told apart afterwards.

## Output — Polish, per match, decision first

Return markdown; the caller saves it. Structure:

1. **Nagłówek dnia** — the artifact you read (`11_coupon.json` or the
   fallback) and its `epoch`, how many fixtures of *your sport* the day
   carries (a measured sport: how many are `IDENTIFIED` in
   `sport_fixtures.json`), the Superbet snapshot time, how many of your sport's legs the
   coupon prints, how many are in your read set (and how many the operator
   asked for), and the one sentence a bettor must read first.
2. **Co jest w produkcie** — your sport's legs of the read set, by position:
   pewność, próbka k/n, model, the price, and your read; then the builders
   (or the fact that there are none, which is frequent and correct) with
   legs, `combined_probability` (a probability, never a price), and your read.
3. **Mecze** — one section per fixture carrying a leg of your read set or a
   veto, in your sport skill's event-protocol format. Every argument as
   **FACT → CALCULATION → IMPLICATION → RISK**. Tag every non-artifact
   statement with its source and fetch time.
4. **Poza odczytem** — how many of your sport's printed legs sit beyond the
   read set, and any you read anyway.
5. **Zdjęte** — every WATCH / NO_BET you wrote, one line each with its reason.
6. **Czego zabrakło** — the one thing that most weakened the day, and the
   concrete fix. Then a **NIE PODANO** list: every check you could not make.
7. The ```json veto block, then the ```json reads block.

Never lead with a 0.5 UNDER tautology. Never use `pewniak`, `banker`,
`musi wejść`.

## Hard rules

- Every number traces to an artifact, a query you ran, or arithmetic you
  showed. No invented fixture, sample, price or availability.
- Never present a `FUZZY` identity as confirmed, a `THIN_SAMPLE` as actionable,
  or `NO_LADDER_CHECK` as a passed check.
- Never print a combined / Bet Builder / parlay price (sofa prices none;
  `combined_probability` is a probability, not a price).
- No stake, no EV of your own, no placement. Never read, echo or log `.env`.
- A settled result is a fact about the day, not about the decision. Never let
  "it won" into the reasoning for the next one.
- Never research a fixture that has already started. Declare any leak.
