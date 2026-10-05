---
description: Verify a built sofa day adversarially - the one coupon artifact (11_coupon.json, the best 30 positions, every printed builder leg, the measured-sport legs), structure and arithmetic re-derived from raw observations and raw Superbet snapshots, subject-to-side mapping, live prices, and the anti-selection distributions. Ends with the rows it would not stake - in prose and as a reads JSON array (author verifier) that is appended to reads.json and rebuilt on.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Take a built day apart. Protocol:
`docs/sofa/VERIFY_PROTOCOL.md`.

Hand this to `sofa-verifier`, which carries the full method. This command is
the short form and the checklist the report must satisfy.

Work **iteratively**: find a problem, report it, re-verify from the start.
Repeat until a full round produces no new finding.

## What is being verified

**The PDF is the coupon, and `runs/sofa/<date>/11_coupon.json` is what it
prints** (COUPON_ASSEMBLY, on a stats-only day: a build of a day >=
2026-10-05 made at or after 07:15Z, `bet.sofa.epochs`). It holds the
football and tennis legs of `08_confidence.json` and, from 08:30Z, the
hockey, basketball, volleyball and CS2 legs of `08_confidence_sports.json`,
in confidence order, numbered 1..N, the locked legs first and unnumbered,
builders B1... `06_coupon.json` is the old priced VALUE selector (`p_bar`,
`required_odds`, surplus) - it is audited, but it is not the coupon and never
the confidence; label which is which in every table.

The set you verify by hand is the one the analysts read
(`confidence.legs_requiring_read`): the first 30 unlocked positions, every
printed builder leg, and every `read_requests.json` entry. Say how many
printed positions lay beyond it, unverified.

## 1 - the machine checks

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <date>
```

`audit_coupon` (exit 0 nothing found, 1 findings) checks `05_sheet.json` /
`06_coupon.json` - the priced selector's structure (every VALUE row is in the
coupon or in `06_dropped.json` with a reason; **zero rows vanish in
silence**), its arithmetic from each row's own fields
(`required_odds == 1.10/p_bar`, `surplus == offered - required`,
`edge == p_central - market_p`, `p_bar` from `p_central`, the correction and
`market_p`) and the anti-selection distributions. And is
`UNFITTED_CONSTANTS` still on every row? **Never strip it.**

`audit_variants` (exit 0 none, 1 findings, 2 a file could not be read):

- **C1** the artifact is of its profile, not older than `05_sheet.json` /
  `vetoes.json` / `reads.json`, and the PDF is not older than it;
- **C2** every printed single obeys its dials (floor 0.70, confidence x odds
  >= 0.90, margin <= 15%, not started at build); a locked single is checked
  against `printed_under`;
- **C3** every leg of the read set has an `author: "analyst"` read, and no
  printed leg carries WATCH / NO_BET;
- **U1** the fresh singles stand in `confidence.coupon_order`, numbered 1..N,
  locked ones first and unnumbered; **U2** every fresh football / tennis
  single carries the stats-only epoch; **U3** every fresh measured-sport leg
  re-derived from the raw Superbet snapshot as it stood when
  `08_confidence_sports.json` was built: odds, price time and age, group
  margin <= 15%, x >= 0.90, confidence = the calibration bucket of its model
  probability.

A finding is a defect. "nothing to check" is not a pass - say what existed.
Lines under `notes (not defects):` are not findings and not a pass - list
them.

## 2 - what the audit cannot do

A row whose fields are all mutually consistent and all built on the wrong
sample passes the audit. So, for every leg of the read set:

1. **Rebuild from `03_samples.json`** - n, the sample's hits against the
   line, observation dates, opponents - and compare with the leg's
   `confidence`, `sample_hit_rate` and the sample k/n. On a stats-only day
   `p_central` comes from the statistics alone: no tennis rating blend
   (`TENNIS_RATING`), no shrink to the rung's price (`P_SHRUNK_TO_PRICE`), no
   ladder centre. A stats-only row carrying those notes, or a `p_central`
   that moves with its `market_p`, is a defect. `forecast_p` ("model") is
   uncalibrated and shown beside - never a gate, never a reason.
2. **`MODEL_ABOVE_OWN_SAMPLE`:** a football leg whose `model_p` sits more
   than 0.15 above its own sample's hit rate (n >= 5,
   `confidence.MAX_OWN_SAMPLE_GAP`) is removed in code; one printed is a
   defect. Re-derive the hit rate; do not trust the field.
3. **Check `subject` maps to the side it claims**, with an independent matcher
   that folds diacritics. This is the most fragile join in the pipeline.
4. **Re-ask Superbet** for every leg's live price through `OfferFetcher`, and
   read the odds payload a second time by hand.
5. **Check the match has not started on the earliest clock** (RESOLVE's,
   Superbet's own start signal, and FIXTURE_CHECK's fresh `/event` start in
   `fixture_status.json`); a printed match postponed / cancelled / abandoned
   must be `FIXTURE_NOT_AS_SCHEDULED`.
6. **Sport legs:** the identity in `sport_fixtures.json` (pinned
   `sofascore_event_id`, `home_is_team1` against Superbet's T1, the start
   within the hour), the side and period as printed, and that the market
   settles the way its label says (regulation vs overtime, a fixed-format
   friendly). U3 did the arithmetic; the live re-ask is yours.

**Locked legs are not defects.** A leg printed before its match started is
kept as printed (`locked: true`, `printed_at_utc`, `printed_under`) - the
operator's rule. Check only that it was printed before its earliest start;
never NO_BET or WATCH a locked leg for being locked or started. A refusing
read that now covers a locked leg is a note, not a defect.

`pred_sd` is not on the row, so `p_central` reproduces only approximately from
`centre` and `sample_sd` (5 of 63 rows outside 0.024 once). That is a known
limit, not a finding.

## 3 - anti-selection, the most important test

The coupon is ordered by confidence, so the test is where the confidence
concentrates. Count, for the printed legs:

- **by market** - concentration in the weakest measurement (thin samples,
  a curve read from a pool, a thin direction bucket) is an artifact, not an
  edge;
- **by sample size** - describe `n < 8` separately;
- **by league** - fourth tiers and youth over-represented means lack of data
  is winning;
- **by `calibrated_on`** - which curve each leg read, and how many legs one
  curve carries;
- **sample age** - staleness and confidence are not independent.

## 4 - the report

1. fixtures through each stage, and every stage's verdict;
2. the coupon's legs by sport, market, league, sample size and
   `calibrated_on`; the priced `06_coupon.json` separately;
3. before/after for anything re-derived;
4. **which guards had an opportunity to fire.** If the run went clean, say a
   guard was **not tested** - never that it works;
5. **the list of legs you would not stake even though the pipeline printed
   them, with the reason for each.** This is the deliverable. Give it in
   prose and, at the very end, as one fenced ```json array of `LegRead`
   (`src/bet/sofa/contracts.py`, strict, `extra="forbid"`; `author:
   "verifier"`, `verdict: "NO_BET"` for a defect - wrong side, wrong
   identity, stale / wrong price, arithmetic that does not reproduce - and
   `"WATCH"` for a judgement; a sport leg names its `direction` as the side
   and its `period`; `[]` when empty). Schema and example:
   `.claude/agents/sofa-verifier.md`.

The verifier writes no file. Whoever ran it **appends** that array to
`runs/sofa/<date>/reads.json` (validated as `list[LegRead]`, then
`load_reads`) and rebuilds: `run_confidence.py` -> `build_coupon.py` ->
`build_coupon_pdf.py`, then re-runs `audit_variants.py` (C1, C3 clean). WATCH
and NO_BET both remove the leg into `removed_by_reads` (graded apart,
audit_settlement 7h, never in the coupon's result). On a past day whose
legs have started, do not rebuild: report the array as not applied.

End with a verdict and **no stake recommendation**. A coupon can be technically
correct and still not worth staking: `UNFITTED_CONSTANTS` stays on every row.
The stake decision is the operator's.

Retired 2026-10-05: the WARIANT and the separate sport coupons with their
assembly. For a day before that morning, `audit_variants` S1-S5 / M1-M3 still
check those historical files; from the cutover they are notes.
