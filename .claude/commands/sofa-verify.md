---
description: Verify a built sofa day adversarially — structure, arithmetic re-derived from raw observations, subject-to-side mapping, live Superbet prices, and the anti-selection distributions. Ends with the rows it would not stake.
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

## 2 — what the audit cannot do

A row whose fields are all mutually consistent and all built on the wrong
sample passes the audit. So, for every row the PDF stakes and every single
with `surplus > +0.40`:

1. **Rebuild from `03_samples.json`** — n, mean, hits against the line,
   observation dates, opponents. Then walk the chain by hand.
2. **Check `p_central` against the sample's own hit rate.** Tennis
   `sets_total` and `games_won_for` use the empirical frequency, so they must
   be **equal**. Football goes through a negative binomial and will differ —
   a gap above ~15 pp means the league prior is doing the work, and
   `n/(n+25)` says how much.
3. **Check `subject` maps to the side it claims**, with an independent matcher
   that folds diacritics. This is the most fragile join in the pipeline.
4. **Re-ask Superbet** for every leg's live price through `OfferFetcher`, and
   read the odds payload a second time by hand.
5. **Check the match has not started on the earlier clock.** COUPON uses
   `min(kickoff_utc, superbet_kickoff_utc)`; CONFIDENCE reads Sofascore's
   alone. Look for any staked leg sitting in that gap.

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
   them, with the reason for each.** This is the deliverable.

End with a verdict and **no stake recommendation**. A coupon can be technically
correct and still not worth staking: `K_PRICE` and `MAX_LADDER_SIGMA` are
`NOT_FITTED` and every row says so. The stake decision is the operator's.
