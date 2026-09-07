# The forecast card — what we expect, and how much of it is real

`runs/<date>/<date>_forecast.json` is the first artifact you open and the thing
your report leads with. Built by `scripts/simple/build_forecast.py` from the
finished sheet and dossiers; pure, so re-running it on the same two files gives
the same cards.

One card per `(event_id, market, subject)`. `subject` is `null` for a match
total, a team name for a `*_for` row, a player for a prop.

```json
{
  "match": "Barracas Central – Argentinos Juniors",
  "market": "fouls_total", "market_label": "faule (mecz)",
  "expected": 23.95, "interval_80": [16.2, 31.7], "spread": 6.05,
  "sample":   {"size": 24, "mean": 23.96, "median": 24, "min": 13, "max": 34, "weight": 0.71},
  "baseline": {"value": 23.95, "source": "league:23", "weight": 0.29},
  "grade": "MEASURED",
  "grade_reason": "over 580 settled fixtures the sample beat predicting the average by 8.5% ...",
  "reliability": {"fixtures": 580, "observations": 580, "bias": -0.53, "mae": 4.35,
                  "mae_constant": 4.75, "skill": 0.0852, "skill_comparable": true,
                  "at_75": {"claimed": 0.806, "realised": 0.857, "gap": -0.051,
                            "gap_ci": [-0.094, -0.007]},
                  "overconfident_at_75": false},
  "drivers": [{"name": "referee", "value": 21.9, "reference": 23.96, "delta": -2.06,
               "status": "PRICES_IN", "detail": "... partial r=+0.144 against the residual ..."}],
  "rungs":   [{"line": 22.5, "direction": "OVER", "p_central": 0.595, "p_honest": 0.595,
               "calibration_note": "rynek w tym przedziale raczej zaniża ...",
               "p_low": 0.351, "hits": 13, "sample_size": 24, "superbet_price": 1.83}]
}
```

`rungs` arrives **most likely first**, on `p_honest`.

## Two probabilities, and `p_honest` is the one to rank by

`p_central` is what the estimator computes. `p_honest` is that number after
**this market's own settled record at that claim**: `market_reliability.json`
carries a `calibration_curve` per scope saying what rows claiming roughly that
much really realised over every settled fixture in `runs/`, and `p_honest`
subtracts the part of the overconfidence a clustered interval puts beyond zero.

Four properties you can rely on:

* **It can only lower.** A bucket that under-claims is left alone. Raising a
  number off a bucket-level wobble would manufacture confidence nobody
  measured, and the two errors do not cost the same — too high becomes a bet,
  too low becomes a pass.
* **A well-calibrated market is untouched.** The correction is the interval's
  lower bound, so a bucket straddling zero subtracts nothing. Most of the board
  is in this state and reads `p_honest == p_central`.
* **It shrinks itself on thin evidence.** No constant: a bucket standing on
  eight matches has a wide interval and corrects almost nothing.
* **It does not replace the grade.** `WORSE_THAN_AVERAGE` says the sample loses
  to its own format's mean, and recalibration cannot fix that — the level is
  wrong, not the confidence. Read both.

`calibration_note` is the audit trail in Polish: what such rows realised, on
how many matches, and how much was taken off. Quote it when you demote a row
for its market's record rather than for something you found in the fixture.

The practical effect is that a rung sitting at the count-model clamp no longer
has to be filtered out of the ranking by hand. It stays, and it sinks by its own
measured record if that record does not support it.

## Say the expectation first, in the market's own units

"Expect 24.0 fouls, 80% between 16 and 32" is a claim one scoreboard can check.
"P(over 21.5) = 0.59" is a claim only three hundred scoreboards can check, and
the operator has one. Lead every market you grade with `expected` and
`interval_80`; the rungs come after, and the price after that.

The interval is 80% and labelled as such. It is deliberately not 95%: at 95% a
fouls card reads "24.0, somewhere between 15 and 34", which is true and trains
the reader to skip the interval.

## The grade decides what you are allowed to claim

`skill` is `1 - mae/mae_constant`, where the constant is **predicting that
scope's own average**. That is the honest benchmark and it reorders everything.
Against the shrinkage prior instead — `skill_vs_shrinkage_target`, kept in the
file only because an earlier pass reported it — the best-of-five tennis set
count scores **+31.0%**, because it is being compared with a
best-of-three-weighted prior of 2.40 against fixtures that average 3.79.
Measured against the 3.79 those fixtures actually produce, the same forecast
scores **−59.9%**. Beating a straw man is not skill. If a number in this file
looks surprisingly good, check which of the two you are reading.

| grade | what it means | what you may say |
|---|---|---|
| `MEASURED` | the fixture's own sample beat the average | grade rungs normally; the separation between adjacent rungs is evidence |
| `LEVEL_ONLY` | sample tied the average, **or** the market is too rare for MAE to mean anything | quote `expected`; say plainly that what separates 21.5 from 22.5 here is a fitted distribution, not observation |
| `BIASED` | forecast is off in a known direction | correct by hand and show the correction; never read a rung without it |
| `OVERCONFIDENT` | the level is fine and the **probability** is not | quote `expected`; refuse the confidence. The rungs claiming 75%+ on this market have measurably realised less |
| `WORSE_THAN_AVERAGE` | the sample makes the answer **worse** | do not grade rungs. The format/league average is the better answer. Say so and move on |
| `UNMEASURED` | never settled against a result | you may state `expected`; you may not attach a precision to it |

**A scope exists only if ANALYZE prices it.** The dossier collects far more
than the sheet does — 1H/2H splits for fouls, shots, corners, cards and
offsides, and `cards_total`, retired 2026-09-03 for counting yellows while
Superbet counts reds. An earlier version of the measurement read all of them
straight off the raw metrics, which is where "`cards_total` +0.8%",
"`fouls_2h_total` +5.9%" and "`cards_2h_total` +5.9%" came from: three numbers
about markets no row is ever built for. If you remember those figures, forget
them. They are gone and the per-participant markets they crowded out are
measured instead.

As measured on the slates in `runs/`, 29 scopes over 1,031 settled fixtures:

- **Football counting markets beat the average; every tennis market loses to
  it.** `cards_points_total` +9.7%, `fouls_total` +8.5% (580 fixtures),
  `offsides_total` +5.0%, `goals_for` +4.4%, `shots_for` +4.3%,
  `shots_on_target_for` +4.2%, `fouls_for` +3.9%, `shots_total` +3.9%,
  `cards_points_for` +3.4%, `corners_total` +3.1%, `corners_for` +2.2%, down
  to `shots_on_target_total` at +0.0%.
- **`red_cards_total` is the one football market that loses badly, at −47.0%,
  and it grades `BIASED`.** It forecasts 0.35 against an actual 0.16 over 593
  settled fixtures: bias +0.19 on a spread of 0.42. Halve it before reading
  it. Its probabilities are well calibrated all the same (88.7% claimed,
  88.3% realised) because its rungs are UNDERs on a rare event — which is
  what makes it the clearest case in the file for reading `skill` and `at_75`
  as two separate questions.
- **Goals barely move.** `goals_total` +1.0%, `goals_1h_total` +0.7%,
  `goals_2h_total` +2.8%. The sample carries little and the league baseline is
  doing most of the work — which is why `baseline.source` matters more on a
  goals card than anywhere else.
- **Per-team rows are measured now.** `*_for` markets are scored against the
  scoreboard column the subject actually owns, joined through the row's own
  `venue` field. Until 2026-09-08 they had no entry at all, so every per-team
  row shipped unmeasured and no measured rule could ever fire on one.
- **Props are measured too, and their MAE flatters them.** `player_offsides`
  +24.2%, `player_shots_on_target` +16.1%, `player_total_shots` +11.9%. Do not
  read those as "props are our best market". A market that happens 0.13 times a
  match has an MAE dominated by its base rate: predicting roughly nothing for
  everybody is close to right without discriminating between anybody. Those
  scopes carry `skill_comparable: false`, grade `LEVEL_ONLY` whatever the
  number says, and are judged on calibration instead.
- **Tennis loses to the average everywhere.** `games_won@BO5` −2.5%,
  `total_sets@BO3` −6.2%, `total_games@BO3` −8.8%, `games_won@BO3` −12.4%,
  `total_sets@BO5` −59.9%. Both available estimators are wrong and they
  disagree about the sign: the pooled centre runs 5.85 games low on
  best-of-five, the estimand-framed one 3.81 high. On 2026-09-07 four
  hand-written vetoes were needed to keep those rows off the coupon. The grade
  says it once now — do not re-derive it fixture by fixture.
- **A tennis format below the floor borrows its twin and says so.**
  `total_games@BO5` sits just under 25 settled fixtures, which is exactly a US
  Open men's final. Rather than reading `UNMEASURED` there, the card borrows
  the *worse* of the other formats and prefixes the reason with "this format
  has too few settled fixtures to measure". Read it as a floor on what to
  expect, not as a measurement of this format.
- **Aces and double faults are `UNMEASURED` and will stay that way.** ESPN
  answers `statsSource: none` for tennis and the bzzoiro tennis addon is
  unpaid, so nothing settles them. A confident-looking `p_central` on an aces
  row has never once been checked against a result. `player_cards` is the same
  kind of hole for a different reason: the box score reports
  `player_yellow_cards` and `player_red_cards` separately and a second yellow
  *is* a red, so no sum of the two is the number Superbet settles.

## Certainty is measured separately from the level

The operator's own question — "what has a 75%-certain row on this market
actually done?" — is not answered by `skill`. MAE says whether the centre is in
the right place. Calibration says whether the probability the bar is computed
from is true, and that is the number with money on it.

A market can pass either and fail the other, and both directions occur.
`shots_for` has a good centre (+4.3% skill) and its rows claiming 75% or more
have realised **73.5%** against a claimed 81.4% — 7.9 points hot over 437
fixtures. `red_cards_total` is the opposite: its centre is the worst on the
board (−47.0%, forecasting 0.35 against 0.16) and its confident rows are
calibrated to within half a point.

```json
"at_75": {"rungs": 725, "fixtures": 437, "claimed": 0.8140,
          "realised": 0.7350, "gap": 0.079, "gap_ci": [0.0435, 0.1157]},
"overconfident_at_75": true
```

Two things about how that is measured, both of which had to be fixed:

- **Only the favoured side of each rung is read.** Both sides of a line are
  published and their probabilities sum to one, so averaging over both gives
  0.500 claimed against 0.500 realised on every market on the board, whatever
  the forecast does. A first version reported exactly that and it was a
  tautology, not a finding.
- **The interval is bootstrapped over fixtures, not rungs.** One match
  contributes up to forty rungs off one sample, and treating those as forty
  trials is the error that once turned a population artifact into a "+6.2pp
  corroboration effect".

The direction is worth knowing on its own: the sheet is **conservative** where
the money is and hot on the thin stuff. `fouls_total` claims 80.6% and delivers
85.7%; `shots_on_target_total` claims 84.5% and delivers 88.1%; `shots_total`,
`fouls_for`, `goals_total` all deliver more than they claim. So when a football
counting-market row says 80%, believe it. When a tennis row or a red-card row
says 87%, do not.

## Drivers are labelled, never summed

This is the rule that matters most and it is the easiest one to break, because
breaking it produces a report that reads better.

Asked raw against the actual foul count, four things predict it: the pooled
sample +0.459, the referee's own rate +0.317, the h2h mean +0.291, recent form
+0.329. Four reasons, all real.

Asked against the **residual** — what the league-aware forecast already got
wrong — they collapse:

```
fouls_total  h2h      +0.000  95% CI [-0.102, +0.106]
fouls_total  recency  +0.015  95% CI [-0.071, +0.098]
fouls_total  referee  +0.144  95% CI [-0.004, +0.292]
```

They are not four reasons. They are four descriptions of one fact — a high-foul
pairing in a high-foul league — and the sample already carries it. Writing
"over 21.5 **because** the referee books people, **and** their h2h runs high,
**and** both sides are fouling a lot lately" counts that fact three times. This
repository has paid for exactly that error twice: `p_low` realising 23 points
above its own claim, and the cross-provider corroboration effect turning out to
be an artifact of which rows have small samples.

So each driver carries a `status` and you obey it:

- **`PRICES_IN`** — the sample already knows this. Show the number as
  *agreement* or *dissent*, and never as support. Correct: "the referee runs
  21.9 fouls a match against the pairing's 24.0, which leans against the OVER —
  though this is already inside the sample's own mean." Wrong: "and the referee
  agrees, so confidence is higher."
- **`SHARPENS`** — measured to reduce this market's error, interval clear of
  zero *after correcting for how many drivers are tested at once*. **Nothing
  is `SHARPENS`.** Not one driver on one market the sheet prices. The two
  entries that used to carry this label were the referee on `cards_total` and
  on `cards_1h_total` — both markets the sheet never prices at all — so "the
  ref likes giving cards" was never measured on the card market that ships.
- **`SHIFTS`** — corrects the level without sharpening anything. The referee
  blend on card totals: no effect on MAE (−0.021, CI [−0.101, +0.057]) and it
  halves the bias, −0.37 to −0.12. `analyze._blend_referee` already applied it;
  `centre_note` on the card says so. Do not apply it a second time in prose,
  and do not write a DOWNGRADE for a referee the code already blended.
- **`UNMEASURED`** — nobody checked. Context, nothing more.

**The table is one family of tests and is judged as one.** Twenty-two
(market, driver) pairs are tested, so a per-test 95% interval is expected to
throw about one spurious exclusion of zero. It threw three — `goals_total` h2h
[−0.256, −0.011], `offsides_total` h2h [+0.003, +0.253], `offsides_total`
recency [+0.002, +0.180] — each within 0.011 of containing zero, and none
survives the family-wise interval. `ci` is the plain 95% one; `status` is read
from `ci_familywise`. If you find yourself building an argument on a driver,
check that field first: a driver that clears its own test and not the family's
is the false positive it probably is.

One consequence to state plainly, because it reads like a demotion and is not:
the referee on `cards_points_total` is `PRICES_IN` (+0.148, family-wise
[−0.120, +0.419]). That centre already has the referee blended into it by
`analyze._blend_referee`, so the residual *should* have nothing left of him.
Finding nothing is the code working.

## The centre decomposition is what you quote instead of "the sample says"

```
środek = próbka 23.96 (n=24, waga 0.71) + baza 23.95 (`league:23`, waga 0.29)
```

`baseline.source` tells you which target it was pulled toward and it matters:

- `league:<id>` — that competition's own measured mean, over at least 40
  matches. Prefer this and quote the league by name.
- `venue:home` / `venue:away` — the pooled prior with the measured home/away
  offset, for a `*_for` row in a market where the split was measured.
- `pooled` — one number for every league on earth. Say so when it is doing real
  work: on 2026-09-07 the pooled `goals_1h_total` prior of 1.243 pulled an
  Argentine fixture's centre from 0.900 up to 1.014, against a Liga Profesional
  that measures **0.821** over 145 matches, and that single substitution was the
  whole edge of the day's only bet — 1.599 against a price of 1.62 became 1.688.
- `none` — nothing to shrink toward; the centre is the raw sample mean.

When `sample.weight` is high the sample is doing the work; when it is low the
baseline is. A card with `weight: 0.29` and grade `LEVEL_ONLY` is a card whose
number is mostly a league average — say that rather than attributing it to the
fixture.

## Price is a column, not a gate

The coupon's `superbet_verdict` now has three states, and the middle one exists
because the old two-state version was arbitrary:

- `VALUE` — price at or above `min_acceptable_odds`.
- `WITHIN_TOLERANCE` — under it by no more than 5%.
- `PRICED_BELOW_THRESHOLD` — under it by more.

Measured over 1,269 settled priced match-total rows: `gap >= 0%` went 63.5% for
−0.8% ROI on 52 rows; `gap >= -5%` went 72.9% for +1.3% on 144. Insisting on a
non-negative gap threw away nine of every fourteen candidates and bought
nothing. Every interval contains zero, so none of this is a profitability
claim — it is a reason not to treat the threshold as a cliff.

Note which way the win rate runs: it climbs as the gap gets *worse* (63.5% at
the top, 92.6% past −20%), because a worse gap means a shorter price. A
high-probability read sits structurally below the threshold. When the operator
asks for something safe rather than something cheap, that is where it is, and a
file gated at 0% can never show him one.

So: report the gap, never suppress a row for it, and keep "is this likely" and
"is this worth the price" as two separate sentences.
