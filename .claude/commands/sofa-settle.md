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
.venv/bin/python scripts/sofa/ensure_bridge.py      # brings the bridge up if it is down, then runs check_bridge.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only CS2_SETTLE   # CS2 shadow; exit 1 = retry later, never blocks SETTLE. ONLY when runs/sofa/cs2/daily_<date>.done exists or the pid in daily_<date>.pid is not running (the loop settles at 05:00Z itself; a cs2_watchdog.py retries hourly only if one was started for that date - `pgrep -f cs2_watchdog` - and then do not run it by hand)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <date> --only SHADOW_SETTLE   # ONLY when no loop for that date is alive: runs/sofa/shadow/daily_<date>.pid gone or its pid not running (the loop settles at 05:15Z itself; two at once lose updates)
```

`PARTIAL` is the normal verdict. Read `07_settle_skips.json`: **a row that
could not be graded is not a loss.** Counting a blind row as a loss understates
the model exactly as much as counting it as a win overstates it.

`run_settle.py --date <D-1> --include-unpriced` also grades rows Superbet
never quoted — the flag is the stage script's, **not** `run_pipeline.py`'s, so
it is unreachable through `--only SETTLE`. They cannot reach
the `K_PRICE` fitter, but they are real forecasts and they are the only way to
say what the whole board did.

## 1b — every variant, and the ledger (every day)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_sport_coupon.py --from <date-1> --to <date>   # the day before too: its legs after 00:00Z settle into <date>'s file
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py --from <date-1> --to <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <date> --to <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <date> --to <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <date-1> --to <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <date-7> --to <date>    # read it: one table per variant, never pooled
```

One ledger row per (date, variant) in `runs/sofa/ledger/results.jsonl`;
re-running a date replaces its rows. Each variant stands alone - official,
wariant, sport:<sport>, multi, `rule:<sport>` (the price-only rule replayed
on the day, chosen before the outcome) - and `measure:<sport>` records the
price against the outcome (`favourite_side` two-way lines only, comparable
across the 09-30 cutover; `by_shape`, `by_family`, `players` beside it).
Exit 0 = graded as far as the settles allow (pending legs are shown in the
table, never an exit code); 1 = a `MISMATCH` (two graders disagree on a leg -
a defect, name it) or an unreadable file (named in the table); 2 = a crash,
or for `record_results.py` a missing database. A leg after 00:00Z settles
into the next day's file and is graded the morning after (the loops' 05:00Z
/ 05:15Z steps settle D and D-1 and record both days), so the next run's
`--from <date-1>` closes it too. Before the sport's SETTLE has written
`settled.json`, `measure:<sport>` is absent, not pending - check every
`measure:*` row is present.

## 2 — read it, in the right order

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settlement.py --date <date>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_day_deep.py --date <date>
```

**Section 7c of `audit_settlement` is the PDF coupon's real result.** Sections
7 and 7b are input material — legs and candidates — **not bets**. Reporting 7
or 7b as the day's result is the same error as calling `06_coupon.json` the
coupon, and it has inverted a day before.

Report the paths separately and never pool them: the VALUE singles
(−20.4% on 2026-09-20), the PDF (+8.2% the same day), and WARIANT (7d).

`audit_day_deep` answers the two questions after: per market, was the miss
**systematic** or **dispersion**; and **would today's gates still have made
yesterday's bet?** A gate that cannot be shown to have removed a real loss is
decoration. Never judge one on hit rate — 92.5% winners once returned −3.5%.

### 2b — the niche scanner (evidence, not a bet list)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_niches.py --from 2026-09-17 --to <date>
```

Run it after settlement, then re-run `audit_settlement` so section 7h reads the
new artifact. It asks whether any league x market x direction cell beats
Superbet's price **out of sample and over its own margin** (walk-forward,
shrunk toward market and price, Benjamini-Hochberg over every cell scanned).
Read it as evidence: "BRAK NISZY" is the expected and honest answer at this
data volume. A **candidate** is a thing to measure further, never a leg; a
**watch-list** cell is not even that. Never feed it into COUPON, CONFIDENCE,
SHEET or the vetoes, never move a gate or constant because of it, and never
pool 7h with 7c or 7d.

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
WARIANTY: WARIANT <u> · CS2 <u> · HOKEJ <u> · KOSZ <u> · SIATKA <u> · WSZYSTKIE <u> j. (osobno) · pending <n>
POMIAR:   <sport>: fair p <p> vs trafione <h> (<gap> pp, n=<sides>) per sport
LEDGER:   <n> wierszy zapisanych dla <date>
RYNKI:    <families that lost, systematic vs dispersion>
BRAMKI:   <per gate: caught / cost / missed>
NISZE:    <verdict (section 7h) · candidates · selector OOS ROI vs baseline>
FIT:      <re-fitted or not, and why>
UWAGA:    <the one thing that would change tomorrow's run>
```

A settled result is a fact about the day, **not about the decision that made
it**. Never let "it won" into the reasoning for the next one.
