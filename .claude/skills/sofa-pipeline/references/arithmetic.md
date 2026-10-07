# The arithmetic — and what can and cannot be re-derived

> The rules after 2026-10-07 (line evidence - offset, price-band cap, the stand-in for a key without a curve - no refusal by name, the model packages that change `p_central`, the refit) are stated once, in `.claude/skills/sofa-pipeline/SKILL.md`, section "The 2026-10-07 rules", with the arithmetic chain beside it. Where this file names an old behaviour it is marked *(old epoch)* and that section wins.

Two separate chains produce two separate numbers, and conflating them is the
commonest analytical error in this pipeline.

- **SHEET → COUPON** asks *is this worth its price*. It ranks by `surplus`.
  Measured on 6,187 priced rows, the model **loses that argument to the price
  itself** (Brier 0.2067 against 0.1845). `p_bar`, `required_odds`,
  `surplus` and VALUE are this chain: still computed in SHEET and COUPON,
  still audited by `audit_coupon.py`, and **not the coupon's arithmetic**.
- **CONFIDENCE → COUPON_ASSEMBLY → PDF** asks *how often does this happen*.
  It ranks by measured realised rate. Over 1,868,474 settled rows the model is
  calibrated to within 0.3 pp everywhere up to about 0.90.

The second question is the one the model can answer. That is why the PDF
(from `11_coupon.json` on a stats-only day), not `06_coupon.json`, is the
product.

## Confidence without the price (stats-only epoch, from 2026-10-05 07:15Z)

```
p_central   = the statistics alone (no ladder centre, no rating x market_p blend,
              no empirical shrink to the rung's price, no handicap centre on the ladder)
confidence  = the calibration curve's realised_lo95 at p_central (Chain 2, with the K13 cap)
forecast_p  = the rating's own number ("model"): printed beside, uncalibrated, never a gate or a sort key
x           = confidence × offered_odds                  print when x >= 0.90 (NEGATIVE_LEG_EV below)
condition   : ladder margin <= 15%, odds >= 1/0.9202, not started, fresh price
order       = confidence ↓, kickoff ↑, match, market, line (confidence.coupon_order) - no price, no EV
```

From 2026-10-07 10:55Z `confidence` is the lowest of the curve + the key's
offset and the price-band cap (a key with no curve: the Wilson bound of its
own settled Superbet lines, else `NO_LINE_EVIDENCE`); the key is
`market|DIRECTION`, `<class>:` prefixed for a women's / team-cup class, and
the price band only ever lowers. The price enters only as the betting
condition (and the band cap). `MAX_DISAGREEMENT` and
`UNREACHABLE_BAR` are off; a price that moved since SHEET is re-judged at the
fresh odds (nothing upstream read it). Floor 0.70.

---

## Chain 1 — the old priced bar (`src/bet/sofa/engine.py`; still computed, not the coupon's)

```
prior   = league baseline, else global baseline      config/sofa_league_baselines.json
w_c     = n / (n + K_CENTRE)                         football 15.0, tennis 5.0  (FITTED 2026-10-03; unchanged at the 2026-10-07 refit)
centre  = w_c·sample_mean + (1 − w_c)·prior          (= sample_mean when no baseline exists)

p_central:
    tennis rated markets -> 0.25·rating + 0.75·market_p       (note TENNIS_RATING; old epoch only)
    tennis empirical, priced -> w·hits/n + (1−w)·market_p, w = n/(n+30)   (old epoch only)
    stats-only epoch: tennis from the sample's own estimator, no market_p;
                      from 2026-10-07 14:05Z games_won_for / handicap_games / most_games
                      from the rating's neighbours alone, games_total = 0.5·rating + 0.5·NB
    other empirical    -> frequency around the shifted centre
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
— that is the check that matters. On an old-epoch row a priced tennis rung
was pulled onto the price: `TENNIS_RATING` 0.25·rating + 0.75·`market_p`
(`W_TENNIS_RATING`), `P_SHRUNK_TO_PRICE` w·hits/n + (1−w)·`market_p` with
w = n/(n+30) (`K_TENNIS_LADDER_CENTRE`). On a stats-only row (`epoch:
"stats_only"`) `p_central` must not move with `market_p` at all. Re-derive
from the row's epoch and notes.

### Three things that look wrong and are not

1. `centre` ≠ `sample_mean`. It is the mean after shrinkage; the difference is
   `K_CENTRE` working. At football `K_CENTRE = 15` a sample of n=8 contributes
   **35%** of its own centre — so before trusting any `*_1h_*` / `*_2h_*` row,
   compute `n/(n+15)` and say out loud how much of it is the league prior.
2. `ladder_centre` / `ladder_sigma` describe **the bookmaker's ladder**. A
   `ladder_sigma` of 0.003 is a normal value for a ladder, not a suspiciously
   tight distribution of ours.
3. For an old-epoch tennis row, `p_central` is a blend with the price (see
   above), not the raw hit rate. Football goes through a negative binomial and will differ — but a gap above
   ~15 pp means the league prior, not the team, is doing the work.

### The devig is power, not proportional

Proportional devigging overstated long shots by ~7 pp and understated
favourites by ~7 pp. `market_p` is the power devig.

---

## Chain 2 — confidence (`src/bet/sofa/confidence.py`)

```
curve      = Calibration.realised(market, p_central, sport, direction, klass) -> realised_lo95
             (history curves, refitted 2026-10-07 on the replayed history; line evidence then lowers it - above)
K13 (stats-only, cap_market_by_thin): where thin_by_market_direction has a bucket for (market, direction, p),
    confidence = min(lo95 of the curve chosen, lo95 of the thin direction bucket)   - for by_market and the pools
```

K13 because a curve joining OVER and UNDER overstates a thin direction: on
2026-10-05 `corners_1h_total|UNDER` at p 0.75–0.80 had a thin direction bucket
of n = 225 (lower bound 0.663) under the 400-row `min_market_bucket`, so the
lookup fell to the two-direction `by_market` curve (n = 428, lower bound
0.712) and printed 0.712 >= 0.70. With the cap it is 0.663 →
`BELOW_CONFIDENCE_FLOOR`. A capped leg reads `calibrated_on:
market_thin:<market>|<direction>`.

The **lower bound** of what rows claiming that much actually did. Lookup order:
the market's own curve → (refuse if `p` is at or above that market's measured
ceiling) → the **sport's** pool → the global pool. When none covers the bucket
the leg is **refused** (`NOT_CALIBRATED`) rather than served the model's own
number — falling back to `p` is exactly the untested claim this module exists
to stop making.

**A market in `confidence.AWAITING_OWN_CURVE` never reaches a pool:** with no
curve of its own it is refused (`NOT_CALIBRATED`) - from 2026-10-07 10:55Z it
instead reads the Wilson bound of its own settled Superbet lines, else
`NO_LINE_EVIDENCE` (a derived joint likewise: `DERIVED_CURVES` is off, so it
has no curve at all). That set holds the football
player props (claimed 0.776, realised 0.624 on the pooled curve), the new
per-half / saves / throw-in / goal-kick / tackle markets, and since 2026-09-30
the tennis per-set serve markets `{aces,double_faults,serve_points}_set{1,2}_{for,total}`
(`TENNIS_PER_SET_SERVE`) - which, reading the games-only tennis pool, claimed
0.777 and realised 149/253 = 0.589 - and the full-match serve points
`serve_points_for` / `serve_points_total` (`TENNIS_SERVE_POINTS`): 15/31 =
0.484 against 0.782 claimed. The per-set GAMES markets and the full-match aces
/ double faults have their own curves and are not in it. The guard lapses by itself once `fit_confidence`
gives the market a curve of its own.

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
MAX_DISAGREEMENT     = 0.10       p_central − market_p above this is refused - old epoch only (off in stats_only)
MIN_BUILDER_SAMPLE   = 10         observations, not `sample_size`
MAX_BUILDER_SAMPLE_AGE_DAYS = 180
MIN/MAX_BUILDER_LEGS = 2 / 4
BUILDER_CORRELATION_HAIRCUT = 0.12
```

### Why `MAX_DISAGREEMENT` existed (old epoch)

Off in the stats-only epoch (operator decision D1, 2026-10-05): confidence no
longer reads the price, so the gap to it is no longer the gate. The evidence
that made it a gate:

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

(`odds_product`, `odds_after_haircut` and `ev_after_haircut` are internal: the
stakeable test only. sofa prints no builder price - the PDF says "sprawdź na
ekranie Superbetu".)

```
product_p   = Π confidence_i                       independence ACROSS quantities (lambda 0.95–1.02)
combined_p  = min(product_p, empirical_joint)      the joint may demote, never promote
odds_product     = Π offered_odds_i
odds_after_haircut = odds_product · (1 − 0.12)     or the operator's screen price, which wins
ev_after_haircut   = combined_p · odds_after_haircut − 1
is_stakeable = best_for_fixture and combined_p · odds_after_haircut >= 0.90   (stats-only, stakeable_rule "x>=0.90"; internal - since 2026-10-05 no builder price is printed or reported, the operator reads the screen)
is_stakeable = best_for_fixture and ev_after_haircut > 0                       (old epoch: a builder without stakeable_rule)
```

**One leg per quantity family, not per market.** In the stats-only epoch
(K10) that leg is chosen by confidence, the pool is ordered by confidence and
the builders by `combined_probability`; `best_for_fixture` is the highest
`combined_probability`. Because the 2-, 3- and 4-leg builders are prefixes of
one pool, it is nearly always the 2-leg one. Before the epoch the leg was
chosen by **leg EV** (choosing by confidence was then choosing by shortness of
price and put a negative-EV leg into 530 of 2026-09-19's family slots); the
price filter x >= 0.90 on every leg is what now keeps that out.
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

## Chain 3 — the measured sports (`src/bet/sofa/sport_confidence.py`)

```
p_model    = score_model.line_probability (hockey, basketball, volleyball) / cs2_engine (CS2) - no price
curve      = realised_lo95 (Wilson) of p_model's bucket in the day's sport calibration
             (sport_confidence.calibration_path_for: main file or staged .next.json); a bucket with n < 200 (MIN_BUCKET) is unused;
             old epoch: only an admitted key (family|side) prints, and a key whose out-of-sample confidence
             overstates realised by > 0.03 (MAX_OVERSTATEMENT) is not admitted
confidence = (from 2026-10-07 10:55Z) min(curve + offset, price-band cap) as for football / tennis; no curve at p -> the key's own
             settled lines (Wilson / design effect, >= 50 lines and 15 games) else NO_LINE_EVIDENCE
forecast_p = p_model ; sample_hit_rate = sample_k / sample_n (shown, never a gate)
print when confidence >= 0.70, odds >= 1.0867, group margin <= 15%, x = confidence × odds >= 0.90
```

No curve and no line evidence → `NOT_CALIBRATED` / `NO_LINE_EVIDENCE`. The
calibration is fitted by `fit_sport_confidence.py --before <d>`, between days
only; the evidence by `fit_line_evidence.py` (`refresh_line_evidence.py`
every morning).

---

## The one loop where a day affects the next

```
history of events / statistics ──► calibrate_from_cache.py (replay) ──► data/sofa.db ──► fit_constants.py / fit_confidence.py ──► config/*.json ──► 05_sheet
05_sheet + results ──► 07_settled.json ──► data/sofa.db ──► (audit of a curve; the line evidence's settled Superbet lines)
```

Nothing else carries state between days (since 2026-10-07 the curves are
fitted on the replayed HISTORY, never on our own settled days; the settled
Superbet lines feed only the line evidence). That is why a stale config file is
both silent and expensive: `sofa_league_baselines.json` shipped corners priors
24–32% too high for two days, and at the then `K_CENTRE = 25` those priors
owned 76% of the centre on half-match rows. Check `fitted_from` and `half_match_coherence`
before trusting a sheet.
