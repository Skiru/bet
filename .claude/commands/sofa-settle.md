---
description: Settle a finished sofa day, read what it actually did (section 7c is the PDF coupon's real result), and decide whether to re-fit the constants — which is a deliberate step and never happens mid-day.
argument-hint: wczoraj | YYYY-MM-DD
---

Close the one loop where a `sofa` day affects the next:

```
05_sheet + results ──► 07_settled.json ──► data/sofa.db ──► fit_constants.py ──► config/*.json ──► 05_sheet
```

Hand this to `sofa-settler`, which carries the full method. This command is the
short form.

**Only for a finished day.** SETTLE against today finds every fixture
unfinished. It needs the bridge, so run it before a live day starts, not
during one.

## 1 — settle

```bash
.venv/bin/python scripts/sofa/check_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SETTLE
```

`PARTIAL` is the normal verdict. Read `07_settle_skips.json`: **a row that
could not be graded is not a loss.** Counting a blind row as a loss understates
the model exactly as much as counting it as a win overstates it.

`run_settle.py --date <D-1> --include-unpriced` also grades rows Superbet
never quoted — the flag is the stage script's, **not** `run_pipeline.py`'s, so
it is unreachable through `--only SETTLE`. They cannot reach
the `K_PRICE` fitter, but they are real forecasts and they are the only way to
say what the whole board did.

## 2 — read it, in the right order

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settlement.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_day_deep.py --date <date>
```

**Section 7c of `audit_settlement` is the PDF coupon's real result.** Sections
7 and 7b are input material — legs and candidates — **not bets**. Reporting 7
or 7b as the day's result is the same error as calling `06_coupon.json` the
coupon, and it has inverted a day before.

Report the two paths separately and never pool them: the VALUE singles
(−20.4% on 2026-09-20) and the PDF (+8.2% the same day).

`audit_day_deep` answers the two questions after: per market, was the miss
**systematic** or **dispersion**; and **would today's gates still have made
yesterday's bet?** A gate that cannot be shown to have removed a real loss is
decoration. Never judge one on hit rate — 92.5% winners once returned −3.5%.

## 3 — re-fit only when there is a reason

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_constants.py --db-path data/sofa.db --config-dir config
```

`fit_constants.py` is **outside `DEFAULT_SEQUENCE` on purpose.** Re-fitting
mid-day breaks comparability with yesterday's run. Re-fit when the settled
table has grown materially, a coherence check is failing, or a baseline is
demonstrably wrong. **Not because a day went badly.**

After a fit, always report: `fitted_from` and how much it moved,
`half_match_coherence`, and every constant's `status`. **A `null` with
`NOT_FITTED` is the correct output, not a gap** — `K_PRICE`'s Brier curve is
monotone to `w = 0`, so there is no interior optimum and the plateau rule
refusing to name a value is information.

## 4 — config hygiene

- `config/sofa_market_reliability.json` is owned by `fit_constants.py` **only**.
  `calibrate_from_cache.py --out` writes an ungated curve for inspection and
  must never target it: when two writers shared it, an empty file overwrote a
  measured one and reported success.
- `config/sofa_league_baselines.json` — check `fitted_from` and
  `half_match_coherence`. Corners half-match priors were **24–32% too high** for
  two days; fixing them took a day's VALUE from 142 to 99, and the rows that
  vanished were exactly the ones external verification had already rejected.
- `config/sofa_confidence_calibration.json` — check each market's measured
  ceiling. A market with its own curve may **not** borrow the pooled one above
  the top of its own measured range.

## Report back

```
SETTLE:   <date> · <n> wierszy · <verdict> · <n> nierozliczonych (powody)
SINGLE:   <n> wierszy VALUE · <w>/<n> · ROI <…>
PDF:      <n> slipów (sekcja 7c) · <w>/<n> · ROI <…>
RYNKI:    <families that lost, systematic vs dispersion>
BRAMKI:   <per gate: caught / cost / missed>
FIT:      <re-fitted or not, and why>
UWAGA:    <the one thing that would change tomorrow's run>
```

A settled result is a fact about the day, **not about the decision that made
it**. Never let "it won" into the reasoning for the next one.
