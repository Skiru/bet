# The arithmetic — and what can and cannot be re-derived

Two separate chains produce two separate numbers, and conflating them is the
commonest analytical error in this pipeline.

- **SHEET → COUPON** asks *is this worth its price*. It ranks by `surplus`.
  Measured on 6,187 priced rows, the model **loses that argument to the price
  itself** (Brier 0.2067 against 0.1845).
- **CONFIDENCE → PDF** asks *how often does this happen*. It ranks by measured
  realised rate. Over 1,868,474 settled rows the model is calibrated to within
  0.3 pp everywhere up to about 0.90.

The second question is the one the model can answer. That is why the PDF, not
`06_coupon.json`, is the product.

---

## Chain 1 — the price bar (`src/bet/sofa/engine.py`)

```
prior   = league baseline, else global baseline      config/sofa_league_baselines.json
w_c     = n / (n + K_CENTRE)                         football 25.0, tennis 2.0  (FITTED)
centre  = w_c·sample_mean + (1 − w_c)·prior          (= sample_mean when no baseline exists)

p_central:
    empirical-frequency metrics (tennis, some others)
                       -> p_empirical_raw(hits, n)       == the sample's own hit rate
    football counts    -> negative binomial around `centre`
    everything else    -> normal, support floored at −0.5

p       = max(0.01, p_central − max(0, calibration_correction))
w       = n / (n + K_PRICE)                          K_PRICE = 10.0, status NOT_FITTED
p_bar   = w·p + (1 − w)·market_p                     market_p = power-devigged offered price
required_odds = 1.10 / p_bar                         LEAN margin; CALL would be 1.05
surplus = offered_odds − required_odds
edge    = p_central − market_p
verdict = VALUE when offered_odds > required_odds
```

`config/sofa_engine_constants.json` carries each constant with a `status`. A
constant with no data is `null` and `NOT_FITTED`, never a borrowed default —
and the engine then falls back to its documented starting behaviour. Every row
says so in `notes` via `UNFITTED_CONSTANTS`. **Never strip that note.**

### Why `K_PRICE` is `NOT_FITTED` and why that is correct

The Brier curve is monotone all the way to `w = 0`: the further the blend
moves toward the price and away from the model, the better it scores. There is
no interior optimum to find. The plateau rule therefore refuses to name a
value, and that refusal is information — it says the model loses to the price
on this question. A fitted-looking number here would be a lie.

### Re-deriving a row

Everything above is reproducible **from the row's own fields**, and
`audit_coupon.py` does exactly that:

```
required_odds == 1.10 / p_bar
surplus       == offered_odds − required_odds
edge          == p_central − market_p
p_bar         == w·(p_central − calibration_correction) + (1 − w)·market_p,  w = n/(n+10)
```

**What cannot be re-derived:** `pred_sd` is not written to the row, so
`p_central` itself is only reproducible approximately from `centre` and
`sample_sd` (measured: 5 of 63 rows landed outside a 0.024 tolerance). Rebuild
`p_central` against **the sample's own hit rate** in `03_samples.json` instead
— that is the check that matters, and for tennis the two must be *equal*.

### Three things that look wrong and are not

1. `centre` ≠ `sample_mean`. It is the mean after shrinkage; the difference is
   `K_CENTRE` working. At `K_CENTRE = 25` a football sample of n=8 contributes
   **24%** of its own centre — so before trusting any `*_1h_*` / `*_2h_*` row,
   compute `n/(n+25)` and say out loud how much of it is the league prior.
2. `ladder_centre` / `ladder_sigma` describe **the bookmaker's ladder**. A
   `ladder_sigma` of 0.003 is a normal value for a ladder, not a suspiciously
   tight distribution of ours.
3. For tennis, `p_central` **equals** the sample hit rate by construction.
   Football goes through a negative binomial and will differ — but a gap above
   ~15 pp means the league prior, not the team, is doing the work.

### The devig is power, not proportional

Proportional devigging overstated long shots by ~7 pp and understated
favourites by ~7 pp. `market_p` is the power devig.

---

## Chain 2 — confidence (`src/bet/sofa/confidence.py`)

```
confidence = Calibration.realised(market, p_central, sport).realised_lo95
```

The **lower bound** of what rows claiming that much actually did. Lookup order:
the market's own curve → (refuse if `p` is at or above that market's measured
ceiling) → the **sport's** pool → the global pool. When none covers the bucket
the leg is **refused** (`NOT_CALIBRATED`) rather than served the model's own
number — falling back to `p` is exactly the untested claim this module exists
to stop making.

**A market with its own curve may not borrow the pooled curve above the top of
its own measured range.** Silence above a market's ceiling is evidence, not a
gap: it says the model never produces a confident prediction there that
verifies. A hole *inside* the range is different — that is a thin bucket, and
the pooled curve is a reasonable stand-in. `games_won_for` has 9,286 settled
rows and no bucket above 0.825 (its best realises 0.756); the pooled curve —
74,574 rows, almost all football counts — says 0.905 at p=0.90, and falling
through produced 12 tennis legs at a claimed rate that market has never once
been observed to deliver.

The same ceiling gates the **singles**, as `ABOVE_MEASURED_CEILING` in
`06_dropped.json`. Shared on purpose: the two paths disagreeing about one
measured fact is how a market ends up banned from the builder and dominant in
the coupon.

```
CONFIDENCE_CEILING   = 0.9202     the curve's resolution limit; there is no 98% leg
MIN_ODDS_FOR_CEILING = 1/0.9202 = 1.0867
MAX_DISAGREEMENT     = 0.10       confidence − 1/odds above this is refused
MIN_BUILDER_SAMPLE   = 10         observations, not `sample_size`
MAX_BUILDER_SAMPLE_AGE_DAYS = 180
MIN/MAX_BUILDER_LEGS = 2 / 4
BUILDER_CORRELATION_HAIRCUT = 0.12
```

### Why `MAX_DISAGREEMENT` exists

Grouped by how far the model sat above the devigged market, on 6,187 priced
rows:

| model − price | n | model says | realised |
|---|---|---|---|
| +0.00–0.05 | 1114 | 0.546 | 0.514 |
| +0.05–0.10 | 780 | 0.595 | 0.530 |
| +0.10–0.15 | 441 | 0.609 | **0.444** |
| +0.20–0.30 | 255 | 0.677 | **0.400** |
| +0.30 and up | 328 | 0.800 | **0.451** |

Past +0.10 the realised rate falls **below a coin flip** while the model's
claim keeps climbing. A leg where we say 0.81 and the book says 0.05 is not a
shaded price being offered to us, it is our own error being offered to us.

### Builder arithmetic

```
product_p   = Π confidence_i                       independence ACROSS quantities (lambda 0.95–1.02)
combined_p  = min(product_p, empirical_joint)      the joint may demote, never promote
odds_product     = Π offered_odds_i
odds_after_haircut = odds_product · (1 − 0.12)     or the operator's screen price, which wins
ev_after_haircut   = combined_p · odds_after_haircut − 1
is_stakeable = best_for_fixture and ev_after_haircut > 0
```

**One leg per quantity family, not per market**, and that one is chosen by
**leg EV**, not by confidence — choosing by confidence is choosing by shortness
of price, and it put a negative-EV leg into 530 of 2026-09-19's family slots.
A team's goals and the match total are the same quantity counted twice —
measured lambda 2.165 on 84 rung pairs, up to 8.37. Multiplying them sells two
legs as four. Families:
`goals`, `corners`, `fouls`, `cards`, `shots`, `offsides`, `games`, `aces`,
`double_faults`; an unmapped market is its own family and can still combine,
never silently merged.

**Legs must agree about tempo.** `goals UNDER` with `corners OVER` is
negatively correlated, so the product *overstates* the joint and the slip's EV
is reported too high. Legs that agree are positively correlated — the product
understates, an error in the operator's favour, and therefore allowed.

### The correlation markup is measured, not assumed

The only three builder prices this repo has ever seen off Superbet's screen
(2026-09-20):

| slip | legs | product | screen | markup |
|---|---|---|---|---|
| Inter Miami goals U5.5 + 1h U2.5 | 2 | 1.754 | 1.60 | 8.8% |
| Athletico corners 1h U6.5 + U13.5 | 2 | 1.782 | 1.50 | 15.8% |
| Flamengo 3 UNDER + corners 2h OVER | 4 | 2.364 | 1.90 | 19.6% |

12% is the middle, held flat on purpose: three observations cannot fit a curve
in leg count. The single leg on the same screen went at exactly our quoted
1.37 — **the leg prices are faithful; the money is in the join.** That haircut
is what empties most days' PDFs, and it is the most load-bearing measured
number in the pipeline.

---

## The one loop where a day affects the next

```
05_sheet + results ──► 07_settled.json ──► data/sofa.db ──► fit_constants.py ──► config/*.json ──► 05_sheet
```

Nothing else carries state between days. That is why a stale config file is
both silent and expensive: `sofa_league_baselines.json` shipped corners priors
24–32% too high for two days, and at `K_CENTRE = 25` those priors owned 76% of
the centre on half-match rows. Check `fitted_from` and `half_match_coherence`
before trusting a sheet.
