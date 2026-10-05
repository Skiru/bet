---
description: Verify a built sofa day adversarially — structure, arithmetic re-derived from raw observations, subject-to-side mapping, live Superbet prices, and the anti-selection distributions. Ends with the rows it would not stake - in prose and as a reads JSON array (author verifier) that is appended to reads.json and rebuilt on.
argument-hint: dzisiaj | wczoraj | YYYY-MM-DD
---

Take a built day apart. Protocol:
`docs/sofa/VERIFY_PROTOCOL.md`.

Hand this to `sofa-verifier`, which carries the full method. This command is
the short form and the checklist the report must satisfy.

Work **iteratively**: find a problem, report it, re-verify from the start.
Repeat until a full round produces no new finding.

## What is being verified

**The PDF is the coupon.** `06_coupon.json` holds VALUE singles whose measured
record is −20.4% on 2026-09-20 against the PDF's +8.2% the same day. Verify
both and label which is which in every table.

## 1 — the machine check

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <date>
```

Exit 0 = nothing found, 1 = findings. It checks:

- **Structure:** every coupon row is `VALUE` on the sheet; every VALUE row is
  either in the coupon or in `06_dropped.json` with a reason. **Zero rows may
  vanish in silence.**
- **Arithmetic, from each row's own fields:** `required_odds == 1.10/p_bar`,
  `surplus == offered − required`, `edge == p_central − market_p`,
  `p_bar == w·(p_central − calibration_correction) + (1−w)·market_p`.
- **Anti-selection distributions.**

Also check the caps actually bound: did a row fall out to `MAX_PER_FIXTURE` or
`FAMILY_SLOT_TAKEN` despite a larger surplus than one that was kept? Count
`ABOVE_MEASURED_CEILING` — it fires where a market's own settled history
refuses to describe the probability the row claims. And is
`UNFITTED_CONSTANTS` still on every row? **Never strip it.**

## 1b — the variants

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <date>
```

The four sport coupons re-derived from their raw snapshots (prices, devig,
rule, the selection replayed) and WARIANT WSZYSTKIE against its sources. A
finding is a defect. "nothing to check" is not a pass. C1 also fails an
`08_confidence*` older than `reads.json`; C3 (days from 2026-10-05) fails a
leg the official PDF prints without an analyst's read in `reads.json`, or
despite a WATCH / NO_BET read.

## 1c — the WARIANT

`08_confidence_wariant.json` → `KUPON_<date>_WARIANT.pdf` (floor 0.65,
confidence x odds >= 0.90, margin <= 15%, every single printed):
`audit_variants` C1/C2 checks its freshness, its profile and each printed
single's rule (floor, confidence x odds >= min_ev, margin, not started at
build), but no script re-derives its legs from the samples and `audit_coupon`
never opens it. Apply the checks in 2 to every position it prints that the
official PDF does not, and report it separately, never pooled with the
coupon.

## 2 — what the audit cannot do

A row whose fields are all mutually consistent and all built on the wrong
sample passes the audit. So, for every builder the PDF stakes, the best 30
official singles (the first 30 of `singles` - since 2026-10-05 the PDF prints
all of them, ~300; say how many lay beyond and were not verified) and every
single with `surplus > +0.40`:

1. **Rebuild from `03_samples.json`** — n, mean, hits against the line,
   observation dates, opponents. Then walk the chain by hand.
2. **Check `p_central` against the sample's own hit rate.** Tennis: re-derive
   it from the row's notes (`TENNIS_RATING`: 0.25 x rating + 0.75 x
   `market_p`; `P_SHRUNK_TO_PRICE`: w x hits/n + (1-w) x `market_p`,
   w = n/(n+30)) - see `sofa-verifier` 2a. Football goes through a negative
   binomial and will differ — a gap above ~15 pp means the league prior is
   doing the work, and `n/(n+25)` says how much. Since 2026-10-04 every leg
   carries `sample_hit_rate`, and a football leg more than 0.15 above it
   (n >= 5) is refused by the official profile in code
   (`MODEL_ABOVE_OWN_SAMPLE`, flagged in the WARIANT's `context_flags`): an
   official football leg past that gap is a defect. Re-derive the hit rate
   from `03_samples.json`; do not trust the field.
3. **Check `subject` maps to the side it claims**, with an independent matcher
   that folds diacritics. This is the most fragile join in the pipeline.
4. **Re-ask Superbet** for every leg's live price through `OfferFetcher`, and
   read the odds payload a second time by hand.
5. **Check the match has not started on the earlier clock.** COUPON and
   CONFIDENCE both gate on `min(kickoff_utc, superbet_kickoff_utc)` + 15 min;
   check that no staked leg violates it.

`pred_sd` is not on the row, so `p_central` reproduces only approximately from
`centre` and `sample_sd` (5 of 63 rows outside 0.024 once). That is a known
limit, not a finding.

## 3 — anti-selection, the most important test

`coupon.py` ranks on relative price advantage (`surplus / required_odds`,
breadth-first across fixtures), and every measure of surplus grows as `p` is
overstated. Count:

- VALUE **by market** — concentration in the weakest measurement (thin samples,
  uncheckable ladders, no market curve) is an artifact, not an edge;
- VALUE **by `sample_size`** — at small `n`, `w = n/(n+10)` makes the row a
  statement about the price, not about the model. Describe `n < 8` separately;
- VALUE **by league** — fourth tiers and youth over-represented means lack of
  data is winning;
- **the surplus distribution** — above +0.40 is suspect by definition;
- **sample age** — staleness and surplus are not independent.

## 4 — the report

1. fixtures through each stage, and every stage's verdict;
2. coupon rows by market, league, `sample_size`, `surplus` — singles and PDF
   separately;
3. before/after for anything re-derived;
4. **which guards had an opportunity to fire.** If the run went clean, say a
   guard was **not tested** — never that it works;
5. **the list of rows you would not stake even though the pipeline picked
   them, with the reason for each.** This is the deliverable. Give it in
   prose and, at the very end, as one fenced ```json array of `LegRead`
   (`src/bet/sofa/contracts.py`; all nine keys, `author: "verifier"`,
   `verdict: "NO_BET"` for a defect - wrong side, stale / wrong price,
   arithmetic that does not reproduce - and `"WATCH"` for a judgement; `[]`
   when empty). Schema and example: `.claude/agents/sofa-verifier.md`.

The verifier writes no file. Whoever ran it **appends** that array to
`runs/sofa/<date>/reads.json` (validated as `list[LegRead]`, then
`load_reads`), rebuilds COUPON, `run_confidence.py` + `build_coupon_pdf.py`
for both profiles and `run_multi_coupon.py`, and re-runs `audit_coupon.py`
and `audit_variants.py` (C1, C3 clean). NO_BET then removes the leg from the
coupon and the WARIANT; WATCH removes it from the coupon and keeps it,
marked `WATCH (verifier): <reason>`, in the WARIANT. On a past day whose
window has closed, do not rebuild: report the array as not applied.

End with a verdict and **no stake recommendation**. A coupon can be technically
correct and still not worth staking: `K_PRICE` and `MAX_LADDER_SIGMA` are
`NOT_FITTED` and every row says so. The stake decision is the operator's.
