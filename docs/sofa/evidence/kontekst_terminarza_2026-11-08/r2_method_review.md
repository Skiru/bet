# R2 - methodology review of draft_plan_v1 (schedule / fatigue into the forecast)

Read-only referee review, 2026-11-08. Code facts cite file:line, checked in this session. History volumes come from
the scratch pickle copy `F/fh.pkl` (`F/rv_month.py`: matches per month, and those with count statistics).
Severity: **BLOCKER** means the plan's conclusion would be invalid without the change. **MAJOR** means the estimate
would be biased or its uncertainty wrong. **MINOR** means a clarity or efficiency fix.

Verdict: the plan follows a sound template (season phase), but as written it would probably either find a spurious
"congestion" effect that duplicates terms already live, or judge a real effect against a baseline it cannot
fairly beat. Three BLOCKERs, all fixable before any residual is looked at.

---

## A. Where to measure (Tier 1 vs Tier 2)

### 1. BLOCKER - Tier 1 omits terms that are correlated with the exposure, so the term would double-count them

**Evidence.**
- The live centre is the rating blend followed by a chain of terms (`scripts/sofa/calibrate_from_cache.py:1271-1355`):
  - venue prior;
  - game state x exp(beta s);
  - count stretch exp(g1|s| + g2 s^2);
  - referee;
  - closeness stretch on |s|;
  - goals stretch by supremacy and phase;
  - season phase;
  - plus the form table inside the book (`:1201`).
- `centre_replay.walk` builds only W x rating + (1-W) x shrunk sample (`centre_replay.py:100-139`, `measure_season_phase.live_centre:162`). Its own docstring says it is an approximation (`:22-27`).
- Every missing stretch is a function of the supremacy s. The teams that play congested schedules (CL/EL clubs) are the big favourites with large |s|.
- So a residual against the Tier-1 centre, taken in a congested bucket, contains the stretch's residual too. The "congestion factor" would partly be a supremacy stretch, and live it would sit on top of the real stretch: double counting.
- The same applies elsewhere:
  - the referee term on cards and fouls (big matches and midweek European weeks draw a different referee pool);
  - season phase and the form table on goals (a layoff of 21 d or more is mostly a season start, `r1_evidence_literature.md` 1.2A).

**Change.**
- Do **one** Tier-2 *recording* run before any residual is examined, and fit and judge everything on its output.
  - Run it on the VACUUM copy (`r1_data_replay.md` B, pattern 2) with the installed fit's flags, `--no-write`, and a wrapper on `live_centre` that **records** the live centre for every (event, market, side). Have the wrapper also store the sample centre, the rating centre, s, phase and the referee multiplier.
  - It covers dev and hold-out in one pass, takes about 6 h, and is run once. Its output is a frozen parquet file.
- After that, every fit and look runs offline at Tier-1 speed, against the exact chain SHEET prices with.
- Use Tier 1 only for exploration and for debugging the feature code.
- The coefficient that goes live must be estimated against the recorded live centre. Never transfer a Tier-1 coefficient.
- If the 6 h run is refused, add s, |s|, s^2 and phase as covariates in the Tier-1 residual GLM. Report the fatigue coefficient with and without them. If the two differ by more than 1 SE, the Tier-1 result is void for that metric.

### 2. MAJOR - Tier 1 leaks same-day results; Tier 2 does not

**Evidence.**
- `centre_replay.walk` calls `book.update(r)` after every single match in start order (`centre_replay.py:139-147`). It does not group matches that share a start time or a day.
- So a 16:00 kickoff is forecast with the 14:00 and 15:00 results of the same day, and even with other matches at 16:00 that precede it in list order, folded into the league rate.
- `calibrate_from_cache` advances the book only to the match's UTC day start (`FootballRatingReplay.advance`, `:1222-1234`; referee reads "at the last advance - the match's UTC day start"). Live SHEET also works from the day's cut.
- The leak is not neutral for this question. Round-wide shocks are exactly the effects we want to measure: every team returning from an international break, a winter-break restart, a midweek round. These get partly absorbed into the league rate through same-round results, which shrinks the measured effect toward 0.
- The tennis rating replay has the same per-match update (`tennis_rating.replay:920-929`). Concurrent courts and "followed by" matches leak in the same way.
- `tennis_point_model.walk_forward` groups only identical start seconds (`:885-907`). That does not stop a 10:00 match that ends at 12:30 from teaching an 11:00 forecast.

**Change.**
- Any Tier-1 / tennis replay used here must update by UTC day, as live does: forecast every match of day D from the book at D 00:00Z.
- Item 1's recording run has this property already.
- Add a unit test: shuffling the order of matches within a day must not change any forecast for that day.

### 3. MAJOR - the baseline absorbs fatigue through its own updates (a contaminated rating)

**Evidence.**
- `RatingBook.update` moves attack and defence by the raw surprise of every match, rotated cup games and congested games included (`football_rating.py:1075-1130`). The shrunk sample also contains them (`centre_replay.py:139-147`).
- A team in a congested spell therefore has its rating pulled down by the spell itself. A team just out of one has a rating still depressed by it.
- So a residual against that centre is not the fatigue effect. It is the effect net of the contamination: attenuated on the congested match, and of the opposite sign on the first rested match after the spell.
- Home advantage avoids this problem because it is in both the expectation and the update. A prediction-only term does not.

**Change.**
- Pre-register two variants and report both:
  - (a) **prediction-only**: what a live term in `live_centre` can do;
  - (b) **prediction + update**: fatigue sits in the expectation that `RatingBook.update` measures the surprise against.
- Adopt (a) unless (b) is materially better. In that case (b) is a rating change and needs a rating refit and a Tier-2 replay.
- Also report the "first match after a congested spell" bucket separately. A rebound there is the signature of contamination, not of rest.

---

## B. Confounding and design

### 4. BLOCKER - "residual against the model centre" is not enough; the identification must be within-team and within-match

**Evidence.**
- The centre carries a team's level only as a slow EWMA (item 3), and it has known systematic errors by |s|. Those errors are why the stretches exist.
- Congestion is concentrated in about 100 clubs (European cups and domestic cups), in a few months (Dec-Jan, CL weeks), and in particular competitions.
- Any persistent mis-rating of those clubs (squad depth, the cup-strength link, `cup_strength.py`) loads onto "congestion". The 11-05 battery already found that most significant cells were "form and season table in disguise" (`r1_evidence_literature.md` 1.2C).

**Change.**
- Fit a Poisson / NB GLM with offset log(live centre), not bucket ratios. Three designs, each stated in the pre-registration as primary or secondary:
  1. **Within team-season (primary for `_for` metrics):**
     - Model: log mu = log centre + alpha[team x season] + beta_own f_own + beta_opp f_opp + gamma'controls.
     - Use conditional Poisson fixed effects, which are consistent with an offset (Wooldridge 1999).
     - Identification comes only from the same team being rested vs tired within one season.
     - Controls: home/away, phase, competition kind of the current match (league / domestic cup / continental), knockout, |s| spline.
  2. **Within-match contrast (robustness):**
     - Model: log(y_A / mu_A) - log(y_B / mu_B) regressed on f_A - f_B, using the y-sums form so zeros are handled (item 8).
     - Everything common to the match cancels: referee, weather, pitch, the league round, and the league-rate leak of item 2.
     - It identifies only asymmetry. Totals need design 1.
  3. **Symmetry check:**
     - Expect beta_own(attack) < 0 and the opponent's fatigue effect on its own `_for` to point the other way.
     - Estimate home and away separately. Stüttgen 2025 found congestion *improves* home defence.
     - A sign pattern that contradicts the mechanism is grounds to reject, even if the CI excludes 0.
- Report every coefficient in strata of the favourite's |s| (terciles) and for continental vs domestic congestion. An effect present only among CL clubs is a team-quality artefact until design 1 confirms it.

### 5. MAJOR - the placebo "rest AFTER the match" is badly designed

**Evidence.**
- Days to the next match has a real causal channel: managers rotate *before* a big next game, and the 11-05 battery's C11 knockout cells passed. A non-null result is therefore uninterpretable.
- It shares the team-quality confound, which is useful. But the plan has no rule for what a non-null placebo means.

**Change.** Replace it with three controls that have known answers:
- **(i) Permutation null.** Within each team-season, permute the fatigue feature across the team's matches 200 times. The real beta must lie outside the 95% of the permutation distribution. This also gives an honest SE under serial correlation.
- **(ii) Lagged-exposure negative control.** Add the rest *before the team's previous match* (rest_{t-1}) beside rest_t. An acute fatigue effect predicts beta(rest_{t-1}) is about 0 given rest_t. A large coefficient means a persistent team trait.
- **(iii) Mechanism-free outcome.** Pick a metric with no plausible fatigue path but the same confounders, e.g. the opponent's offsides, or cards in a match with a referee fixed effect. It must show nothing.
- Keep "next match within 3 d (continental / cup)" as a **separate pre-registered feature**: rotation anticipation. Fixture lists are known days ahead, so it is as-of. Postponed and rescheduled next fixtures are excluded.

### 6. MAJOR - the live feature and the replay feature must be one function

**Evidence.**
- Live `schedule.py` counts **no friendlies** (docstring `:15-17`). It reads the side's own listing pages 0..4 (`:18-19`).
- Plan P1 counts friendlies and builds the calendar from the *union* of listings.
- Coverage differs too:
  - the union misses about 1.5-2.2% of real matches and 4.7% / 14.7% of sides have no listing near the date (`r1_data_replay.md` A1);
  - live fetches the fixture's teams fresh.
- A hole in the calendar looks like long rest. The history holes fall on obscure sides and early years, which is missing not at random.

**Change.**
- Write one as-of feature function in `src/bet/sofa` (or extend `schedule.py`) and use it in both the replay and the live path. Choose the friendly rule once.
- Missing data:
  - a side with `coverage=false` is dropped from the fit;
  - live, a side with `coverage=false` gets no term (x1), never a fake long rest;
  - report the exposure distribution live (last 30 days of 03_samples) vs replay. They must match within a few points per bucket.

### 7. MINOR - the remaining confounders, stated explicitly

- **Season phase.** Separate a "layoff of 21 d or more" into: season start, winter break, international break (team-level gap overlapping a FIFA window), and individual gap (makeup / postponement). They are different mechanisms, and only the international break is not already covered by the live season-phase term.
- **Regression to the mean.** Fatigue exposures are not chosen on outcome, so RTM is weak in football. In tennis it is strong (item 15).
- **Rotation.** Rotation *is* the mechanism, so do not control it away (no post-match lineups: a leak). Rotation does add variance, so see item 11.
- **Postponed matches.** Exclude matches never played from load. The rescheduled match itself is the makeup flag.
- **Live baseline.** A Sofascore start time is the realised one. Rest measured on realised dates is what live sees for past matches, which is fine. A future-fixture feature must come from a listing snapshot taken before kickoff, or be dropped.

---

## C. Leakage and periods

### 8. Leakage audit (answers Q3)

| item | finding | severity | change |
|---|---|---|---|
| intra-day updates | item 2 | MAJOR | day-gated replay |
| `assign_league_units` | league units come from **all** matches of the season, including later ones (`football_rating.py:525-557`) | MINOR (same in both arms, unrelated to fatigue) | note it; no change |
| pickle content | final 90' values, `knockout`, `awarded` (decided later); stats backfilled later appear in past samples that live may not have had cached | MINOR, symmetric | do not use `awarded` as a feature; acknowledge it |
| tennis `tier_start` | in-sample look-ahead stated in `fit_tennis_rating.py --tier-start` help | MINOR | refit at the dev cut (item 10) |
| tennis rating coefficients | `fit_coefficients` is a plain in-sample logistic over everything before the cut (`tennis_rating.py:969-994`); the installed config cut is 10-01 and includes the hold-out | **MAJOR** | the item 10 baseline refit |
| current-match retirement | excluding retired matches conditions on an outcome fatigue causes | correct estimand (Superbet refunds RETIRED), but report the retirement rate by bucket as its own outcome | - |
| earlier looks at the hold-out | the 10-04 schedule measurement used league matches 2025-08-01..2026-10-03 (`r1_evidence_literature.md` 1.2A), which covers the whole proposed hold-out; the ">= 21 d" bucket was chosen on it | **MAJOR** | item 9 |

### 9. BLOCKER - the hold-out is neither unseen nor representative

**Evidence.**
- The proposed hold-out is 2026-06..10. Matches with count statistics per month (`F/rv_month.py`): Jun 1,481, Jul 2,066, Aug 8,351, Sep 9,975, Oct 10,623.
- It includes:
  - the 2026 World Cup (competition 16: 78 + 26 matches);
  - the summer leagues (Nordic, Americas, Asia) and the European qualifiers.
- It contains **no** winter congestion (Dec-Jan), no UCL knockout spring and no season end. Those are the main congestion regimes.
- The 10-04 measurement and the 10-05 / 11-05 measurements have already looked at it (item 8).
- The installed constants were fitted on data spanning it:
  - season-phase coefficients to 10-12;
  - tennis rating to 10-01;
  - form-table families selected 10-18..11-04;
  - curves on the 11-05 replay.
- Season phase is directly confounded with layoff. So the baseline is in-sample exactly where the fatigue term competes. That biases the test against the term, which is conservative, but it is not clean.

**Change.**
- **Calendar-year split**, so that both periods contain the whole seasonal cycle:

  | period | goals | count statistics (corners / shots / cards) |
  |---|---|---|
  | dev | 2024-07..2025-12, about 543k matches | effectively 2024-10..2025-12, about 53k |
  | hold-out | 2026-01..2026-10 | about 62k, about 323k goals |

- Before the hold-out is scored, re-fit on dev only every installed constant that is collinear with the exposure, in **both** arms:
  - the season-phase coefficients (cheap: `fit_season_phase` on the recorded rows);
  - the tennis rating logistic layer (`fit_tennis_rating.py --cut 2026-01-01`).
- State in the pre-registration that the 2025-08..2026-10 data were seen by the 10-04 / 10-05 measurements against the raw sample mean, and which feature choices came from them.
- Add a **prospective hold-out**: compute the frozen term live in shadow (logged, never applied) from 2026-11-09 for at least 6 weeks, which is about 15k count matches. It is the only data nobody has seen. The adoption decision needs both hold-outs to agree in sign.
- Exclude national-team matches (World Cup, qualifiers) from the fit, or make them a separate stratum. Their "rest" is a different object.

### 10. MAJOR - double use of history by the installed fits (tennis especially)

**Evidence.**
- The tennis rating coefficients, including dmin78 / drest / dn7, are in-sample through 10-01 (item 8).
- The point-model constants (`RatingParams`, `NB_SHAPE`, `SCORE_WEIGHT`, `tennis_point_model.py:433-462`) were tuned on 2025-2026 history.
- Comparing "installed rating" with "rating + new feature fitted on dev" on the hold-out is unfair to the new arm. The installed arm has seen the hold-out.

**Change.**
- Both arms are refit on dev with the identical procedure. The only difference between them is the feature.
- Hyperparameters of the point model stay as installed in both arms. That is symmetric, so say so and accept it.

---

## D. Scoring, aggregation, power

### 11. MAJOR - residual and scoring rule

**Evidence.**
- `log(y / centre)` per row is undefined at y = 0, and it is biased for small means (E log y is not log E y).
- The season-phase template already avoids this. It uses the Poisson MLE log(Σy / Σcentre) per cell (`measure_season_phase.coefficients_before:212-229`), which is exactly the GLM-with-offset solution for one dummy.

**Change.**
- **Estimation.** Use a GLM with offset (Poisson quasi-likelihood for the coefficient, NB for the score).
  - Reds, penalties and other y in {0,1}: a Bernoulli / complementary-log-log with offset log(centre), i.e. P(y >= 1) = 1 - exp(-mu).
  - Never a per-row log ratio.
  - For descriptive tables, use Pearson or deviance residuals by bucket, or the ratio of sums.
- **Primary score.** The full-distribution NB log score of the observed count, as the template does (`nb_logloss_vec`). It is strictly proper, line-free, and covers every line at once.
- **Secondary score.** The ranked probability score (RPS) for counts (Czado, Gneiting & Held 2009), which is less tail-sensitive. Add PIT histograms by exposure bucket to show *where* calibration fails.
- **Line-level Brier.** Only at lines **fixed independently of either arm**. Use per-family line sets taken from Superbet's historical line placement, or from the baseline centre's quantiles, and use the same set for both arms.
  - Scoring "lines where p >= 0.70" lets each arm choose its own rows. That is a selection bias.
  - The ">= 0.70 calibration not worse" rule must be evaluated on rows selected by the **baseline** p, or on both arms' rows reported separately.
- **Dispersion.** Fatigue may raise variance through rotation more than it shifts the mean. Pre-register a secondary hypothesis: alpha by exposure bucket, fitted on dev. A mean-only term cannot capture it.
- **Curves.** "Confidence equals hit rate" is the curves' job. A centre term can only add resolution.
  - The final judgement (P8) must refit the curves on dev in both arms and compare calibrated p on the hold-out.
  - Otherwise the new arm is scored through curves fitted to the old centres, which penalises it, or through the installed curves fitted on the hold-out, which flatters both.

### 12. MAJOR - multiplicity: 177 families are not 177 hypotheses

**Evidence.**
- The families are deterministic transforms of a few centres: goals full / 1H / 2H, `_for` / `_total`, handicaps and results are all functions of 2 goal centres.
- BH across about 177 x buckets treats them as separate tests. That is too strict for weak signals and meaningless for dependent ones.
- And the pass rule "CI excludes 0 per family group" has no correction across groups.

**Change.**
- **Unit of inference = mechanism x metric group.** About 5 mechanisms and about 8 groups gives about 40 confirmatory tests:
  - mechanisms:
    - M1 acute short rest (3 d or less, in hours between kickoffs);
    - M2 cumulative load (matches or minutes in 14 / 21 d);
    - M3 layoff split as in item 7;
    - M4 rest asymmetry;
    - M5 travel / time zone (exploratory only; expected null, `r1_evidence_literature.md` 2.3);
  - groups: goals, corners, shots/SOT, cards/fouls, offsides, tennis games, tennis serve, tennis winner.
- **Parametric form.** Use one monotone form per mechanism: a piecewise-linear rest capped at 10 d, not 6 free buckets.
- **Partial pooling.** Empirical-Bayes / hierarchical shrinkage across metrics within a group.
- **Hold-out multiplicity.** Holm across the confirmatory tests.
- **Families.** The family table (P6, "every family a row") stays as **descriptive** output. A family is "changed" by inheritance from its group, never by its own test.
- **Non-inferiority.** "No group worse beyond tolerance" becomes a one-sided test: the upper 95% bound of Δlog-loss per exposed row must be below δ.
  - Fix δ in the pre-registration, e.g. δ = 1e-4 nats per row for goals, scaled by group.
  - Measure it on **all** rows and on **exposed** rows separately, as the template does (`d_logloss` vs `d_logloss_phased_rows`).

### 13. MAJOR - cluster-robust uncertainty; the match bootstrap is too narrow

**Evidence.**
- The exposure is team-level and serially correlated: a congested spell lasts weeks, and a team's mis-rating persists.
- `boot_by_match` (`measure_season_phase.py:177-193`) resamples matches as independent. That understates the SE whenever errors correlate within a team-season.

**Change.**
- Use a two-way cluster bootstrap (home team x away team), or a block bootstrap by team-season. For tennis, cluster by player and tournament-week.
- Keep the match bootstrap only as a secondary comparison, to show the difference.
- The permutation null of item 5(i) is the cross-check.

### 14. MAJOR - power: decide the minimum effect of interest first

**Evidence.**
- The literature says effects are small (`r1_evidence_literature.md` "Expected effect sizes"). Prior repo gains were 1e-4..1e-3 Brier.
- The plan states no effect size it could detect.

**Change.** Put this calculation in the pre-registration. For a multiplicative term exp(c) on a NB mean mu, applied to the n_e exposed rows (Poisson/NB information):
- SE(ĉ) ≈ sqrt((1/mu + alpha) / n_e) x sqrt(DEFF), with DEFF about 1.5-2 for team clustering.
- Required n_e ≈ (z_{.975} + z_{.80})^2 x (1/mu + alpha) x DEFF / c^2 = 7.85 x (1/mu + alpha) x DEFF / c^2.

| group | mu (per side) | c = 0.03 | c = 0.05 |
|---|---|---|---|
| corners | about 5, alpha about 0.05 | about 3.8k exposed rows (DEFF 1.75) | about 1.4k |
| goals | about 1.35 | about 11k | about 4k |
| cards / reds | 1 / mu dominates | reds are hopeless at these sizes | - |

- Tennis winner: 2 pp at p = 0.5 is about 0.08 logit, SE ≈ 2 / sqrt(n), so n ≈ 4.9k x DEFF matches in the exposed bucket.
- Gain if c is known exactly: about mu c^2 / (2(1 + alpha mu)) nats per exposed row. For corners at c = 0.03 that is about 2e-3, diluted by the exposure share. For a 10% bucket it is about 2e-4 per row.
- **Minimum effect of interest: |c| >= 0.03 (3% of the centre)**, or 1 pp of winner p. Below it the term is not worth a switch, an epoch and a refit, even when significant.
- Consequence: M1 short rest in football (CONGESTED is 0.2% of matches, about 2k matches a year) is underpowered on count metrics in a 10-month hold-out unless it is pooled across groups. Say so up front rather than "finding nothing".

---

## E. Forking paths

### 15. MAJOR - the "iterate until it works" risk

**Change** (pre-registration contents and rules):
1. **Commit the pre-registration** as `docs/sofa/evidence/schedule_prereg_<date>.md`. Record its git SHA and a hash of the feature module **before** the recording run. It contains:
   - mechanisms, exact feature definitions, parametric forms, controls;
   - estimand per group, the minimum effect of interest, the power table;
   - periods, metrics, the δ per group, the CI method, the multiplicity rule;
   - the adoption rule, and the explicit list of earlier looks (item 9).
2. **Three tiers of data:**
   - explore = dev 2024-07..2025-06, unlimited looks, all logged;
   - validate = dev 2025-07..2025-12, **at most 3 logged looks**, each with its spec hash;
   - hold-out = 2026-01..10, **one look**;
   - prospective shadow (item 9).
3. **Seal the hold-out.**
   - The recording run writes hold-out rows to a separate file.
   - The analysis script refuses to read it unless it is given the frozen spec hash, and it writes that hash into the output.
   - A second run with a different hash is a protocol breach and is reported as such.
4. **Cap the specifications.**
   - At most **one** specification per (mechanism, group) goes to the hold-out.
   - Changing a bucket edge, a window (7 / 14 / 21 d), the friendly rule or the control set after looking at validate counts as a new look.
5. **Report failures in full.** A failed hold-out is reported in full and the term is declined. It is not re-specified against the same hold-out. The next attempt waits for the prospective data.

---

## F. Tennis

### 16. MAJOR - refit the rating; do not add a term on top; dn7 is selection

**Evidence.**
- `_context` (`tennis_rating.py:452-471`) sums minutes only where they are present: `mins is not None`, otherwise it adds 0. So a missing duration reads as rested. Minutes coverage is 30-39% in 2025-26 (`r1_data_replay.md` A4).
- dn7 counts any match in the 7 days before. Inside a tournament that is the number of rounds **won**, which is a form signal, hence its positive sign.
- Points coverage was overstated: the plan says "near-full coverage", but r1 A4 says points are present on about 73% of events *that have a stats row*. Games played from the set score are about 100%.

**Change.**
- **Winner p.** Refit the logistic layer with redefined features, *replacing* dmin78 / dn7 rather than adding beside them:
  - workload = **games** played in the last 78 h / 7 d (full coverage), refined by points played where present, with a coverage indicator;
  - minutes only as a sensitivity check;
  - **rounds won in the current tournament** as a selection control, separate from **matches in previous tournaments within 7 d** (true load);
  - previous match's **dominance** (share of points or games won) as a form control. A long match is also a close one (the Sackmann caveat). Without this control, "workload" measures weakness.
  - Both arms are refit at the same cut (item 10).
- **Quasi-experiment.** Compare main-draw R1 players who came through qualifying with direct entrants of similar rating. Report it as supporting evidence, not as the decision.
- **Point model.**
  - A fatigue shift on the player's serve-point logit (and return) is a separate estimator. It does not double count *within* a market, because winner p comes from the rating.
  - But do not feed the rating's winner p into the point model and also add fatigue there.
  - Report the cross-market consistency: the implied winner p from the point model vs the rating, by fatigue bucket.
- **Totals.** For games / set totals the relevant exposure is not the difference (home - away) but the **sum** and the **max**: "both tired" moves totals, not winner p. Pre-register both.

### 17. MINOR - best-of-five and previous-match format

- Men's Slam best-of-five matches are about 500 a year. The hold-out (2026-01..10) has 3 Slams, about 375 matches, which is underpowered for anything below a few pp.
- Treat best-of-five as an **exposure** (the previous match was best-of-five, workload in games), not as a separate target. The point model refuses best-of-five targets anyway (NOT_RATED).
- Report best-of-five descriptively only.
- Use workload in games or points, which already scales with format. Do not use "sets played" or "five-setter" as separate features (collinear).

---

## G. Other omissions

### 18. MINOR

- **Rest unit.** Use hours between kickoffs / 24, not calendar days. A Thursday 21:00 to Sunday 14:00 gap is 2.7 d, not 3.
- **Extra time.** The previous match's minutes (120 vs 90) should enter M2. `metrics.played_extra_time` exists. ET matches are absent from the pickle's samples but present in the listings.
- **Collinearity.** "Continental match in the previous 4 days" is nearly nested in "rest of 3 d or less". Define it as an interaction (short rest x continental travel), not a parallel feature.
- **Time zone from team country.** Multi-zone countries (RU, US, BR, KZ) make it noise. Keep it exploratory and continental-only, or wait for venue coordinates.
- **Player props.** Fatigue mostly changes *starting* (a non-starter is void), so a prop's estimand is conditional on starting. Score props only on starters, as SETTLE grades them.
- **Coverage of rows.** Tier rows need at least 5 sample values on both sides (`centre_replay.MIN_VALUES`). Promoted sides, season starts and long layoffs are under-represented. Report row coverage per exposure bucket.
- **Unreachable families.** The plan lists families no term can reach (league-rate markets, raw-sample props). Mark them "not tested" rather than "no effect".
- **Interactions with live gates.** Run P8's MODEL_ABOVE_OWN_SAMPLE check, and also check the interaction with `price_gap` / `rating_market_gap`. A centre shift changes which legs carry those flags (display only, but reads key off them).
- **Expected outcome.** The prior evidence says the most likely result is "small and real on shots/SOT and on layoff-goals, null elsewhere". The pre-registration should say that a null result is a valid deliverable.

---

## Revised plan skeleton (delta to P0-P9)

| step | change |
|---|---|
| P0 | Pre-registration per item 15, with power (14), mechanisms x groups (12), δ, the earlier looks (9) and the seal. |
| P1 | One as-of feature function shared with live (6), day-gated. Friendlies rule chosen once. Coverage flag. Hours-based rest. Layoff split (7). |
| P2 | Five mechanisms with parametric forms. Tennis: games-based load, current-tournament rounds and dominance controls, sum / max for totals (16). |
| P3 | **One Tier-2 recording run** (live centres for every row, day-gated) on the VACUUM copy (1, 2). Tier 1 only for debugging. |
| P4 | GLM with offset: team-season FE (primary), within-match contrast, symmetry, |s| strata, permutation null, lagged negative control (4, 5). Two-way cluster bootstrap (13). Variants: prediction-only vs prediction+update (3). |
| P5 | Shrunk coefficients per mechanism x group, fitted on explore + validate, frozen. Baseline constants collinear with the exposure re-fit on dev in **both** arms (9, 10). |
| P6 | NB log score primary, RPS + PIT secondary, Brier at arm-independent fixed lines, dispersion by exposure (11). Families descriptive (12). |
| P7 | Hold-out 2026-01..10, one sealed look, Holm across the confirmatory tests, non-inferiority δ, minimum effect of interest. Then **prospective shadow** of at least 6 weeks before any switch. |
| P8 | Curves refit on dev in both arms before judging calibrated p. Then the usual install path. |
