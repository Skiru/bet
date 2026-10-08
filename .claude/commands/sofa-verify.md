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
(`confidence.legs_requiring_read`): the first 30 unlocked positions (from 2026-10-09 00:00Z the unit is the match: every unlocked leg of the first 30 matches of the coupon, `read_unit: "event"` in the artifact; operator, "30 wydarzeń, nie 30 rynków"), every
printed builder leg, and every `read_requests.json` entry. Say how many
printed positions lay beyond it, unverified.

## 1 - the machine checks

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <date>
```

`audit_coupon` (exit 0 nothing found, 1 findings, 2 an artifact missing)
checks `05_sheet.json` / `06_coupon.json` - not `11_coupon.json` - the priced
selector's structure (every VALUE row is in the
coupon or in `06_dropped.json` with a reason; **zero rows vanish in
silence**), its arithmetic from each row's own fields
(`required_odds == 1.10/p_bar` (or 1.05), `surplus == offered - required`,
`edge == p_central - market_p`, `p_bar` from `p_central`, the correction and
`market_p`) and the anti-selection distributions. And is
`UNFITTED_CONSTANTS` still on every row? **Never strip it.**

`audit_variants` (offline; exit 0 none, 1 findings, 2 a file could not be
read):

- **C1** the artifact is of its profile, `11_coupon.json` is not older than
  `08_confidence.json` / `08_confidence_sports.json` / `read_requests.json`,
  and the PDF is not older than it;
- **C2** every printed single obeys its dials (floor 0.70, confidence x odds
  >= 0.90, margin <= 15%, not started at build); a locked single is checked
  against `printed_under`; a printed leg whose match started is on the coupon
  (locked) or in `printed_after_start`, never gone;
- **C3** (days from 2026-10-05) every leg of the read set has an
  `author: "analyst"` read, and no printed leg - read set or not - carries
  WATCH / NO_BET;
- **U1** the fresh singles stand in `confidence.coupon_order`, numbered 1..N,
  locked ones first and unnumbered; **U2** every fresh football / tennis
  single carries the stats-only epoch; **U3** every fresh measured-sport leg
  re-derived from the raw Superbet snapshot as it stood when
  `08_confidence_sports.json` was built: the line, odds, price time and age,
  group margin <= 15%, x >= 0.90, the line inside the curve's fit, confidence
  = the calibration read of its `forecast_p` (from 2026-10-07 10:55Z lowered
  by `line_offset` and `price_band_cap`, or read from the key's own Superbet
  lines - `bet.sofa.line_evidence`; `forecast_p` is printed to 4 dp, so a p
  on a bucket edge within +-5e-5 is not a finding).

A finding is a defect. "nothing to check" is not a pass - say what existed.
Lines under `notes (not defects):` are not findings and not a pass - list
them.

## 2 - what the audit cannot do

A row whose fields are all mutually consistent and all built on the wrong
sample passes the audit. So, for every leg of the read set:

1. **Rebuild from `03_samples.json`** - n, the sample's hits against the
   line, observation dates, opponents - and compare with the leg's
   `confidence`, `sample_hit_rate` and the sample k/n. On a stats-only day
   `p_central` comes from the statistics alone: no shrink to the rung's
   price (`P_SHRUNK_TO_PRICE`), no ladder centre. A stats-only row carrying
   those notes, or a `p_central` that moves with its `market_p`, is a defect.
   One exception, from 2026-10-07 14:05Z (`TENNIS_RATING_PRICES`):
   `games_won_for`, `handicap_games` and `most_games` (not its draw) are
   priced by the tennis rating's neighbours alone, carry a `TENNIS_RATING`
   note and have `p_central` = `forecast_p`; `games_total` is half rating,
   half NB. Football goals / corners / shots-on-target / cards joints are
   built from the marginal rows' centres from the same moment
   (`DERIVED_MARGINAL_CENTRES`), basketball noise by freshness
   (`BB_FRESHNESS`). The packages `COUNT_DISPERSION`, `TENNIS_SCOPED_TABLE`, `PER_MARKET_K` are ON
   from 2026-10-09 00:00Z (`CARDS_CORRELATION` stays OFF); a SHEET row of a day
   >= 10-09 without `dispersion_rule` / `k_rule` (tennis rows: `tennis_table_rule`)
   is a defect, and one of a day < 10-09 with them is a defect (the rebuild
   re-runs SHEET for these). A `05_sheet.json` older than that moment prices the old
   estimator against the refitted curves - name it (the rebuild does not
   re-run SHEET for these switches). Detail: `.claude/agents/sofa-verifier.md`.
   `forecast_p` ("model") is uncalibrated and shown beside - never a gate,
   never a reason.
2. **`MODEL_ABOVE_OWN_SAMPLE`:** a football leg whose `model_p` sits more
   than 0.15 above its own sample's hit rate (n >= 5,
   `confidence.MAX_OWN_SAMPLE_GAP`; football, player props excluded) is
   removed in code; one printed is a defect. Re-derive the hit rate; do not
   trust the field.
3. **Check `subject` maps to the side it claims**, with an independent matcher
   that folds diacritics. This is the most fragile join in the pipeline.
4. **Re-ask Superbet** for every leg's live price through `OfferFetcher`
   (built as OFFER builds it, `ampersand_subjects` included), and read the
   odds payload a second time by hand. Read `fetcher.errors` and
   `fetcher.not_reached` first: a listing that raised or was never asked is
   CANNOT VERIFY, never "off the board".
5. **Check the match has not started on the earliest clock** (RESOLVE's,
   Superbet's own start signal, and FIXTURE_CHECK's fresh `/event` start in
   `fixture_status.json`); a printed match postponed / cancelled / abandoned
   must be `FIXTURE_NOT_AS_SCHEDULED`.
6. **Sport legs:** the identity in `sport_fixtures.json` (pinned
   `sofascore_event_id`, `home_is_team1` against Superbet's T1, the start
   within the hour), the side and period as printed, and that the market
   settles the way its label says (regulation vs overtime, a fixed-format
   friendly; basketball second half / Q4 grade on regulation, overtime does
   not count). U3 did the arithmetic; the live re-ask is yours.

**The guards are by epoch.** Before 2026-10-07 10:55Z the by-name refusals
(`refused_markets`, `admitted_*`, `DERIVED_NOT_CALIBRATABLE`, a sport key
outside `admitted`) apply and a printed leg of such a market is a defect; from
10:55Z none exists and such a leg is not a defect - the defect is a
`calibrated_on` that is neither a curve nor `sb:<sport>:<key>`, or a leg that
ignores its `line_offset` / `price_band_cap`. From 13:42Z (`line_evidence_v2`)
a no-curve leg needs 15 games in its bucket and a CS2 leg a known `best_of`.
Re-derive from `config/sofa_superbet_line_evidence.json`
(`LineEvidence.load(v2=True).read(...)`). The full list:
`.claude/agents/sofa-verifier.md`, Step 3.

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

Then `PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <date>`
(offline): a dead `capture_closing` loop means "CLV not captured" in the
report; it also shows snapshot ages, ledger `MISMATCH` and `UNVERIFIED`
fixtures.

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
`load_reads`) and rebuilds with the one rebuild command, nothing else:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <date>
```

It refreshes a stale offer / sport snapshot first (only while the day is
live), runs FIXTURE_CHECK, CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY, the
PDF and `audit_variants.py` / `audit_coupon.py` in order (C1, C3 clean).
Re-read until C3 is clean: a removed leg lets the next position into the
first 30. Never
run the stage scripts by hand for a rebuild: a hand-run CONFIDENCE on a
stale offer empties the coupon to its locked legs (2026-10-05). WATCH
and NO_BET both remove the leg into `removed_by_reads` (graded apart,
audit_settlement 7i, never in the coupon's result). On a past day whose
legs have started, do not rebuild: report the array as not applied.

End with a verdict and **no stake recommendation**. A coupon can be technically
correct and still not worth staking: `UNFITTED_CONSTANTS` stays on every row.
The stake decision is the operator's.
