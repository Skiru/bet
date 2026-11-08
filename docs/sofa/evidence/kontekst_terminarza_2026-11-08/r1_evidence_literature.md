# R1 - schedule / fatigue / context: prior evidence in the repo + literature

Compiled 2026-11-08, read-only. Repo facts cite file and line or artifact. Web
sources are graded: **S** = peer-reviewed and verified here (at least the abstract), **M** =
peer-reviewed but only the abstract or a summary was seen, **W** = blog, practitioner
or working paper, or a number taken from a secondary summary. Anything marked "(unverified)"
was not opened in this session.

---

## PART 1 - What the repo has already measured

### 1.1 Where context lives today

- `src/bet/sofa/schedule.py`. Per side it computes `rest_days`, `matches_7d` and `matches_14d` from cached listings: friendlies are out, and a match without statistics still counts. It also computes `makeup_of`.
  - Flags: `LONG_LAYOFF` when rest >= 21 d (`LONG_LAYOFF_DAYS`, l.45); `CONGESTED` when >= 3 matches in the 7 d before kick-off (`CONGESTED_7D`, l.47; flag text l.80-83); `MAKEUP_FIXTURE`.
  - The flags are written onto legs in `scripts/sofa/run_confidence.py` ~l.1020 (`context_flags`, together with national-age and auto-watch tags).
  - **Display only.** Nothing enters p (CLAUDE.md "context_flags ... are shown, never gated").
- `src/bet/sofa/tennis_rating.py`. The tennis Elo calibration **does** carry fatigue, inside the winner p only:
  - Features (l.95, l.473-498): `dmin78` = (minutes in the last 78 h, home - away)/60; `drest` = difference of the binary "back from > `REST_DAYS` = 21 d" (l.111); `dn7` = difference in matches in the last 7 d.
  - Context helper: `_context`, l.452-471.
- Dossier: `src/bet/sofa/dossier.py` l.319-348 gives `rest_days` and the matches in 7 / 14 d to the analysts. Display only.
- The **tennis point model** (from 11-06, 20 keys plus the per-set handicaps) and the football minute simulator carry no fatigue input. A grep for `dmin78|fatigue|rest_days` finds only schedule / dossier / contracts / report_check / tennis_rating.

### 1.2 Football - measurements on history (sample residual, no price)

**A. `measure_schedule_context.py`, 2026-10-04**

Report: `docs/sofa/history/RAPORT_2026-10-04_POROWNYWALNOSC_HISTORII.md` §K3. Full table: `data/analysis_2026-10-04_history/schedule_context.md`.

- Data: league matches 2025-08-01..2026-10-03, 293,058 for goals and 47,038 for corners.
- Residual = actual - sample mean, with a match-resampling 95% CI.

| group | goals_total residual | corners_total residual |
|---|---|---|
| all | +0.014 [+0.007, +0.022] | -0.015 [-0.044, +0.017] |
| rest 0-4 d (n 52,865 / 11,909) | +0.032 [+0.015, +0.051] | +0.017 [-0.048, +0.077] |
| rest 4-8 d | +0.012 | -0.026 |
| rest 8-15 d | +0.076 [+0.051, +0.100] | +0.086 [-0.025, +0.208] |
| rest >= 21 d (n 17,573 / 1,692) | **-0.122 [-0.155, -0.092]** | **-0.280 [-0.452, -0.108]** |
| either side >= 21 d | -0.065 [-0.086, -0.041] | -0.162 [-0.303, -0.023] |
| CONGESTED (n 627 / 53) | +0.087 [-0.067, +0.247] | +0.256 [-0.73, +1.16] |
| make-up (n 21,075) | +0.024 [-0.001, +0.048] | +0.035 [-0.071, +0.140] |

Reading:

- Short rest does **not** lower goals; it is +0.02 relative to "all".
- Long layoff lowers goals by about 0.14 and corners by about 0.27 against the sample.
- **Confound:** rest >= 21 d is mostly the season start, which the round feature below shows as -2..-4% goals.
- `CONGESTED` (>= 3 in the previous 7 d) is extremely rare: 0.2% of matches. As defined it cannot carry a correction.
- Decision: flags only. "Not known whether the market prices it, so no gate."

**B. `measure_model_defects.py context`, F3.2, 2026-10-05**

Report: `docs/sofa/evidence/model_defects_2026-10-05.md` §5 (table l.40-46).

- Model: Poisson GLM with an offset, `log(lam) = log(sample mean) + a + b.x`. It is fitted on one id-parity half and scored on the other; d = log-loss(feature) - log-loss(intercept only).
- Rest / congestion:
  - goals_total **-0.00015 [-0.00023, -0.00008]** (>= 21 d coefficient -0.033 / -0.034);
  - goals_for -0.00002 [-0.00006, +0.00002];
  - corners_total -0.00007 [-0.00034, +0.00020];
  - yellow_cards_total -0.00009 [-0.00029, +0.00010].
- Make-up fixture: no effect.
- For scale:
  - **round / season phase** -0.00173 on goals_total: last two rounds about +11% goals and -6% yellows; rounds 1-3 -2..-4% goals.
  - knockout -0.00008 / -0.00018 (goals_for / yellows).
  - promoted / relegated side -0.0001.
- Decision (`AUDYT_RYNKOW_KONTEKST_2026-10-13.md` W6, l.2084-2095; C14 l.118): rest "minimal gain". It passes the criterion only for goals_total, by about 1e-4, and is not implemented. Round is the recommended feature (P1, also not implemented as of that audit).
- Caveat stated in the source: these are measured against the raw sample mean, not against the replayed `p_central`.

**C. Feature battery, 2026-11-05: the only test against the de-vigged price**

Report: `docs/sofa/evidence/bateria_statystyk_2026-11-05.md`; data `data/refit_2026-11-05_battery/results.json`.

Setup:

- Data: settled Superbet lines 09-28..11-04, football 486k rows / 12.5k matches.
- Split: development 09-28..10-22, hold-out 10-23..11-04, computed once.
- Cell model: `y ~ logit(p) + z(feature)`, ΔBrier on the hold-out with a match bootstrap.
- Multiple testing: BH q = 0.10 across 6,104 statistical cells. The feature list was frozen before the first result.

Schedule features:

- C01 home rest days, C02 away rest days, C03 rest difference, C04 back-to-back (<= 1.5 d), C05 both sides' matches in 7 d, C06 difference in 14-d matches.
- Travel: C07 / C08 (previous match in another city).

Cells that passed BH:

- **C01 / C02 (rest) in football shot families.** The coefficient is positive: more rest gives more shots.
  - shots_total: C01 -0.70 [-1.03, -0.36]e-3; C02 -0.41e-3.
  - shots_on_target_total: C01 -0.86e-3; C02 -0.62e-3.
  - shots_on_target_1h_total: C01 -1.21 [-1.89, -0.54]e-3.
  - shots_for and SOT_for: C01 -0.63 / -0.51e-3.
  - C05 shots_total -0.12e-3. C06 goals_2h_total -0.15e-3.
- Other sports: hockey double_chance C01; basketball DC / 1X2 C03; volleyball set_handicap C01 -1.19e-3.

What did not pass or did not matter:

- C04 (back-to-back) passed 0 cells.
- **Travel C07 / C08 passed 0 of 80.**
- **Every passing cell leaves the gap to the price positive:** shots_total stays about +8e-3 Brier above the price.
- The overall "everything" model per sport is not better than p alone.

Conclusion of that report: no context feature brings p to the price. The 155 BH passes are mainly form and season table in disguise.

**D. Literature and analyst docs already in the repo (not measurements)**

- `docs/sofa/history/analitycy_2026-10-26/lit_review.md` §1.3-1.4, and `sources_football_tennis.md` rows 13-16 and tennis rows 9-10.
- Their working conclusions:
  - congestion predicts rotation and injury more than results;
  - the new-manager bounce is regression to the mean, so it is not a removal reason;
  - in tennis, a long or late previous match is a WATCH reason only for legs that need the tired player to produce.
- Basketball: B2B was measured at +0.06 points, se 0.64 (`AUDYT_RYNKOW...` B7 l.89), and `b2b_delta = 0` in `score_model.py`.
- CS2 rest: no bias (±0.5..0.8 pp, `POMIAR_CS2_PLAYER_KILLS_2026-10-20.md` l.108).
- Weather: "no data in the cache" (`model_defects` §5).
- Manager change, travel distance and time zones were never measured in football or tennis.

### 1.3 Printed legs - the 10-31 cell study (hit vs price, no confidence column)

Sources:

- `docs/sofa/evidence/kupon_od_nowa_2026-10-31/batches/C_evidence_other/cells.csv`
- Protocol: `.../PROTOCOL.md`
- Library: `bt_lib.py`

Setup:

- Data: legs of the printed coupons 10-13..10-30, decision snapshot >= 30 min before the start, legs not removed by a read.
- Splits: dev 10-13..10-24, val 10-25..10-28, hold 10-29..10-30 (the context cells were not taken to hold-out).

Column meanings (header):

- `hit` = realised rate.
- `inv` = mean 1/odds (the price, with margin).
- `lift_pp` = hit - inv.
- **`excess_pp`** = the cell's lift minus the whole split's lift in the same 0.05 1/odds band. This is the "good 1.20 vs bad 1.20" measure.
- `p_excess` = one-sided bootstrap p (by match) for excess <= 0. n < 100 = suspicion.
- **There is no confidence column.** Hit vs confidence cannot be read from this file. The file also says "~x.count_leg", meaning legs without a `metric`, i.e. not count legs.

| cell | split | n legs (matches) | hit | 1/odds | lift pp [CI] | excess pp [CI] | p |
|---|---|---|---|---|---|---|---|
| pooled ctx_none | dev | 32,551 (5,239) | .781 | .826 | -4.5 [-5.0,-3.9] | -0.3 [-0.8,+0.3] | .82 |
| | val | 10,991 (1,801) | .771 | .828 | -5.7 [-6.7,-4.6] | -1.3 [-2.3,-0.3] | .99 |
| **pooled ctx_congested** | dev | 2,590 (604) | .793 | .829 | -3.6 [-5.7,-1.6] | **+0.7 [-1.4,+2.7]** | .25 |
| | val | 629 (157) | .801 | .828 | -2.6 [-6.6,+1.3] | **+1.7 [-2.3,+5.6]** | .21 |
| **pooled ctx_layoff** | dev | 585 (133) | .783 | .826 | -4.3 [-8.4,-0.4] | **-0.05 [-4.1,+3.9]** | .50 |
| | val | 199 (55) | .794 | .823 | -2.9 [-10.0,+4.1] | +1.5 [-5.6,+8.6] | .32 |
| pooled ctx_makeup | dev | 711 (111) | .779 | .829 | -5.0 [-9.0,-1.2] | -0.8 [-4.8,+3.0] | .67 |
| | val | 519 (75) | .825 | .831 | -0.6 [-5.2,+3.2] | +3.8 [-0.8,+7.6] | .06 |
| fb_noncount ctx_congested | dev | **10 (1)** | .80 | .80 | - | - | suspicion |
| fb_noncount ctx_layoff | dev | 450 (84) | .753 | .826 | -7.3 [-12.2,-3.0] | -3.0 [-7.9,+1.3] | .91 |
| | val | 79 (14) | .734 | .832 | -9.8 [-21,+1.6] | -5.4 [-16.6,+5.8] | suspicion |
| fb_noncount ctx_makeup | = pooled makeup (all football) | | | | | | |

Reading:

- No context cell has an excess interval excluding zero, in dev or in val.
- `CONGESTED` printed legs are almost never football (10 legs). Pooled congested is therefore other sports' legs. This is an inference: most likely tennis, where >= 3 matches in 7 d is normal inside a tournament.
- Football `LONG_LAYOFF` non-count legs point negative (-3 / -5 pp excess) but sit well inside noise (84 + 14 matches).
- None of these went through BH selection into the frozen rules.

### 1.4 Tennis - fatigue inside the rating

`config/tennis_rating.json`, fitted 2026-10-08 on 151,849 rated singles, cut 2026-10-01. The coefficient vector is [intercept, lp_t, lps, dmin78, drest, dn7, dform, dhigh, dtour].

| tier (n) | dmin78 (per hour of extra court time in 78 h) | drest (back from > 21 d, binary) | dn7 (per extra match in 7 d) |
|---|---|---|---|
| ITF (109,126) | -0.016 | -0.225 | +0.009 |
| CH (25,826) | -0.036 | -0.265 | +0.020 |
| TOUR (16,269) | -0.046 | -0.422 | +0.036 |

- At p = 0.5 on the TOUR tier:
  - 2 h more court time in the last 78 h ≈ -0.09 logit ≈ **-2.3 pp**;
  - a "rust" return ≈ **-10 pp** (ITF ≈ -5.6 pp).
- `dn7` is positive, a sign of selection: players deep in a draw won their earlier rounds.
- An earlier fit (memory `rating-models-replace-raw-samples.md`) reported z = -6.7 for fatigue and -4.1 for rust.
- This touches only the winner p and the rating-neighbour score markets. **Fatigue in the game distribution was never modelled**: `AUDYT_RYNKOW_KONTEKST_2026-10-13.md` l.911-912 lists it as a gap.
- The 11-06 point model (games per set, aces, double faults, serve points, per-set handicap) carries none of it.
- Git: features since `01be2f2a` (sofascore-plan-hardening). Football schedule since `ad3e3fe6`, review `cac29912`, measurement `380f54e8`.

### 1.5 Net prior from the repo

- **Football:**
  - Long layoff and season start are real and against the sample (goals -0.12, corners -0.28), but confounded with the round feature.
  - Short rest is about zero on goals.
  - Rest days add a small, significant amount in **shot** families against the de-vigged price, but never close the gap.
  - Travel (city change) gives nothing.
  - On printed legs, no context flag discriminates within a price band.
- **Tennis:** fatigue and rust are well established in the winner p (coefficients above). The open question is fatigue in **games / serve statistics** and in the point model. Nothing was measured there.

---

## PART 2 - Literature

### 2.1 Football: congestion and rest -> outcomes

| study | data | finding | grade |
|---|---|---|---|
| Scoppa (2015), *J. Sports Econ.* / IZA DP 7519 (2013) "Fatigue and team performance in soccer: evidence from the FIFA World Cup and the UEFA European Championship" | national teams, World Cup 1930-2010, Euro 1960-2012 | One extra rest day matters only when rest is <= 3 days; above that, no effect. Under modern formats, no relevant effect. | M ([IZA](https://newsroom.iza.org/en/archive/research/new-evidence-from-soccer-tournaments-three-days-of-rest-are-enough)) |
| Stüttgen (2025), *J. Sports Econ.* 26(8) 887-912 "The Impact of Scheduling and Match Congestion on Team Performance" | Bundesliga 5 seasons, plus Spain and England | Two games in 4 days lower **attacking** strength (Bundesliga only). Home **defensive** strength improves under congestion. Large differences between teams and seasons. No numbers in the abstract. | M ([RePEc](https://econpapers.repec.org/RePEc:sae:jospec:v:26:y:2025:i:8:p:887-912)) |
| Buchheit, Settembre, Hader, Tarascon, McHugh, Verheijen (2022), *Sport Perf. & Sci. Reports* #175 (Kitman Labs) | top 7 leagues 2001-2021, >61,000 fixtures | CL / EL teams after a midweek European game with only 2 recovery days still win at a high rate. The home/away pattern after congestion matches the general home advantage, so "congestion and travel are unlikely to worsen the effect of match location". Descriptive only, chi-square, no model for strength. | W-M ([PDF](https://go.kitmanlabs.com/rs/633-QEV-085/images/Study_Mid_Week-European_Matches.pdf)) |
| Bengtsson, Ekstrand, Hägglund (2013), *BJSM* 47(12):743-747 | 27 teams, 11 seasons (UEFA ECIS) | <= 4 vs >= 6 days' recovery: muscle injury RR 1.32 [1.15, 1.51], total injury RR 1.09 [1.00, 1.18]. "No, or very limited, influence on team performance." | M (RR from a secondary summary) ([PubMed](https://pubmed.ncbi.nlm.nih.gov/23851296/)) |
| Dellal, Lago-Peñas, Rey, Chamari, Orhant (2015), *BJSM* 49(6):390-394 | 16 internationals, 6 games in 18 days | No difference in physical or technical output across congested games. Match injury rate higher, layoffs shorter (9.5 vs 17.5 d). | M |
| Julian, Page, Harper (2021), *Sports Med* 51:255-273, meta-analysis | 16 studies, 5 meta-analysed | **No effect on total distance.** Some decline in low / moderate-intensity distance, interpreted as pacing to protect high-intensity actions. Evidence equivocal and of low quality. | S ([PMC7846542](https://pmc.ncbi.nlm.nih.gov/articles/PMC7846542)) |
| Verheijen (2012), cited by Huddersfield | ? | "2 days of preparation -> 40% less likely to win than with 3 days" | **W, original unverified**; contradicted by the above |
| Moffat (2020), *Eur. Sport Mgmt Quarterly* | regression discontinuity at EL group-stage qualification | Europa League participation has **no** significant domestic effect in strong leagues, and a **positive** effect in weaker leagues. | M ([Durham](https://dro.dur.ac.uk/28290)) |
| Stephens & Shepherd (2019?), *J. Funct. Morphol. Kinesiol.* 4(1):2 "Playing in the UEFA Europa League does not adversely affect EPL or La Liga performance" | comparator clubs | Number of European matches not related to domestic performance | M |
| Sky Sports analysis | Premier League | EL weeks about -0.1 points per game | W |
| Goller & Krumer (2020), *EJOR* 286(2):740-754 | 10,142 matches in 4 leagues | Games on non-frequent weekdays: lower attendance and a **weaker home advantage for underdogs**. A day-of-week effect correlated with congestion. | S ([BORIS](https://boris.unibe.ch/150684)) |

**Summary of effect sizes:** on match results, rest beyond 3 days has about zero effect. With 2-3 days' rest the effect is small, hidden by squad depth, and confounded. Plausible magnitude: a few points of win-% at most; the 0.1 PPG EL penalty is weak evidence. Congestion **raises injury and rotation** (muscle injury RR ~1.3). Typical match-to-match rotation is 2-3 starters per team (Buchheit et al.; Huddersfield summary; W).

### 2.2 Football: congestion -> statistics (goals, shots, corners, cards, fouls, late goals)

- **Physical output:** total distance is unchanged (Julian 2021). The low-intensity "average" per epoch drops while peaks are kept (U23 study, Huddersfield 2020; W-M). This points to **pacing**, not collapse, so a late-goal or 2H drop is plausible but **not directly measured** in any study found. No study links congestion to goals by minute; the Spurs-after-the-international-break anecdote is W.
- **Attacking:** Stüttgen (2025) finds lower attacking strength under congestion in Germany only. This is consistent in direction with the repo's battery: rest raises shot rates by small but BH-significant amounts.
- **Cards and fouls:** no study found linking congestion to cards or fouls. The repo shows a null on yellows (-0.00009, CI over 0).
- **Long breaks:** the repo finds fewer goals and corners after >= 21 d. No external study isolates winter or international breaks on goals. Lit_review row 141 in the repo cites a Spanish UCL study with no effect (unverified).
- **Running as fatigue, in the market:** "How do bookmakers interpret running performance of teams in previous games? Evidence from the Football Bundesliga", *J. Sports Econ.* 22(3):231-250 (2021). Bookmakers' implied probabilities react to previous running data, and "tests of market efficiency ... do not reveal a profitable betting strategy". M ([RePEc](https://econpapers.repec.org/RePEc:sae:jospec:v:22:y:2021:i:3:p:231-250)). **This is the closest football test of whether the market prices fatigue: it does.**

### 2.3 Football: travel and time zones

- Oberhofer, Philippovich, Winner (2010), *J. Econ. Psychology* 31(2):200-211 ([RePEc](https://econpapers.repec.org/RePEc:eee:joepsy:v:31:y:2010:i:2:p:200-211)). Data: 6,389 Bundesliga away games, 1986-2007. Distance increases **goals conceded** by the away side, not goals scored. The effect on goal difference is non-monotonic (a squared term). M, and the data are old.
- Altitude: McSharry (2007), *BMJ* 335:1278, internationals. About 0.5 goals of goal difference per 1,000 m altitude difference. M (cited in the repo lit_review).
- Jet lag, other sports: Song, Severini, Allada (2017), *PNAS* 114:1407 (MLB, eastward travel worse, "subtle"). NBA / NHL westward-travel studies (Charest et al. 2022, NHL 17,088 games; cited in the repo's `sources_measured_sports.md`).
- For European club football: Buchheit et al. find no extra travel penalty for CL / EL clubs, and the repo battery finds city-change travel 0 of 80 cells.
- **Expected effect for European domestic leagues: about zero.** Possibly relevant for continental cups (Russia, Kazakhstan, Libertadores) and altitude.

### 2.4 Football: new-manager bounce

- van Ours & van Tuijl (2016), *Economic Inquiry* (Dutch Eredivisie): the improvement after a sacking equals what similar slumps without a sacking show, i.e. regression to the mean. M (cited).
- Besters, van Ours, van Tuijl (2016), *De Economist* (Premier League): "no effect on in-season performances, on average". M.
- van Ours (2025), Tinbergen DP 25-054, "Outcome bias in managerial decisions", top-5 leagues 2017/18-2024/25: the bounce is regression to the mean ([PDF](https://papers.tinbergen.nl/25054.pdf)). M. A Polish Ekstraklasa study (Stachniak & Wolak 2025) agrees. W-M.
- Dissent: Neil Paine (Substack): "modest gains beyond regression to the mean". W.
- **Expected effect against a rating already conditioned on recent form: about zero.** A naive "new coach" flag measured against the *sample* mean will show a spurious positive (the sample contains the slump).

### 2.5 Football: weather (for completeness)

- Heat: Bundesliga 1/2, La Liga and A-League, 1,585 matches (*Eur. J. Sport Sci.* 2025, Saarland). Fewer passes, touches and take-ons; key passes unrelated. M ([link](https://publikationen.sulb.uni-saarland.de/handle/20.500.11880/41048?locale=en)).
- UCL: temperature gives counter-attack shots OR 0.55 [0.30, 0.98]. M.
- A Charles University WP (2025): more goals in warm conditions. W, and it conflicts with the study above.
- Rain / wind: no isolating study found. The repo has no weather in its cache.

### 2.6 Tennis

| study | data | finding | grade |
|---|---|---|---|
| Sackmann, Tennis Abstract, "The Negative Impact of Time on Court" (2017) | 7,200 men's Slam matches since 2001, surface Elo expectation | Actual/expected next-match wins by the previous match's length: 1:00-1:29 **1.07**, 1:30-1:59 1.05, 2:00-2:29 0.99, 2:30-2:59 0.96, 3:00-3:29 0.97, 3:30-3:59 0.95, 4:00-4:29 **0.83** (n 188), >= 4:30 **0.76** (n 72). Raw win % 61.4 -> 31.9. Author's caveat: a short match is also a sign of form that Elo misses. Best-of-5 only. | W-M ([link](https://www.tennisabstract.com/blog/2017/06/02/the-negative-impact-of-time-of-court/)) |
| Sackmann, "The hangover effect of a marathon fifth set" (2012) | Slams | Winners of 6-6+ fifth sets won the next round about 2/3 as often as expected. Women show little effect after long third sets. | W |
| Grand Slam sets-played study, *Int. J. Perf. Anal. Sport* (DOI 10.1080/24748668.2015.11868847) | Slams | Women: +1 set more than the opponent in the previous match lowers win probability. Men: only at a +2-set difference. | M (abstract) |
| Repo `tennis_rating.json` (own fit) | 151,849 matches, all tiers, mostly best-of-3 | TOUR -2.3 pp per 2 h of extra court time in 78 h; rust after > 21 d -10 pp (ITF -5.6 pp) | in-house, out-of-sample Brier gain reported 09-18..22 for the whole rating |
| Return from injury / layoff | - | No rating-adjusted study found. Anecdotes go both ways (Federer 2017, Alcaraz 10-2026 return-game rates above career). | W |
| Travel and time zones | - | No tennis study found. The repo's source list mentions a "2025 ATP study: opponent travel fatigue strengthens home advantage" (unverified). | - |
| Surface change, consecutive weeks | - | Nothing quantitative found. Surface Elo already absorbs surface skill. | - |
| Tennis market efficiency | Betfair, 7,555 matches (Aalto thesis 2013); *Applied Economics* 2017 (DOI 10.1080/00036846.2017.1394973) | Efficiency not rejected; earlier anomalies attributed to data snooping. Women's-tennis "buzz" mispricing (IJF 2022, Stirling). | W / M |

**Games / serve statistics:** no study found linking fatigue to games total, aces or double faults. Plausible mechanisms are untested:

- the tired player's serve-hold drop shortens sets (fewer games) when he loses, and lengthens them through breaks;
- aces drop with serve speed.

Treat any such effect as unknown in sign for totals. For winner / handicap / games-won the sign is clear: the tired player is worse.

### 2.7 Market pricing of rest (other sports, as a prior)

- NBA:
  - Ashman, Bowman, Lambrinos (2010), *J. Sports Econ.* 11(6):602-613, 19 seasons: home teams on the second night of a back-to-back against a rested visitor did poorly against the spread, worse after eastward travel. M ([RePEc](https://econpapers.repec.org/RePEc:sae:jospec:v:11:y:2010:i:6:p:602-613)).
  - Later practitioner data (Action Network, Bet Labs): generic B2B fades 48-52% ATS, ROI -6.4%..+1.9%. W.
  - inpredictable (2012): about 0.75-1.25 points no-rest penalty, with no visible spread adjustment for 3-in-4. W.
- NFL:
  - Frontiers in Behavioral Economics (2024), DOI 10.3389/frbhe.2024.1479832: the rest advantage comes from practice days; "simple inefficiencies ... unlikely to last". M.
  - arXiv 2408.10867 (2024): the bye advantage shrank after the 2011 CBA, and the market prices a "mini-bye" that has no outcome effect. W-M.
  - 2002-2015 efficiency study: the market misses rest information, but not enough to profit. M (cited secondhand).
- Football: Bundesliga running data are priced (J. Sports Econ. 2021, above). **No study found of soccer odds against rest asymmetry.**
- **Prior:** the major-league closing prices largely contain schedule information. Residual edges appear only in narrow interactions (B2B + travel + rested opponent) and erode over time. Superbet prices lower tiers (ITF, minor leagues) with less care; this is a suspicion only. The repo's own finding is that disagreement with the price is an anti-signal (memory `disagreement-with-the-price-is-an-anti-signal.md`).

---

## PART 3 - Pitfalls and guards

| pitfall | how it bites here | guard |
|---|---|---|
| **Confounding by team quality / competition** | Congested football teams are the CL / EL teams: stronger, deeper squads, and they win more anyway (Buchheit: CL teams 58-65% wins). Rest differs by league (cups and midweek rounds) and by tier (tennis players deep in a draw have both more matches and higher form, hence the positive `dn7`). | Measure the residual **after** the full replayed `p_central` / rating, never the raw sample mean. Stratify or condition on competition and tier. Use a within-team contrast (same team, congested vs not). Report the sign of the effect on strong and weak teams separately. |
| **Season-phase confounding** | Rest >= 21 d ≈ season start; the round effect (-2..-4% goals at the start, +11% at the end) masks as "layoff". | Put round / phase in the same model as rest (joint GLM). Test layoff separately as an international break vs a season start. |
| **Regression to the mean** | New manager, "rested after a bad run", tennis "back from a slump": selection on a bad recent outcome. Measured against a sample that contains the slump, recovery looks causal. | Compare with matched controls in a similar slump without the event (van Ours design). Condition on the rating, which already shrinks. |
| **Rotation is the mechanism (lineups unknown at decision time)** | The effect runs through who starts. The post-match lineup is a leak. The repo's `lineups_json` is post-match; `lineups_prematch.json` exists only from 10-23 and only for read matches. | Features strictly as of the decision time. Any lineup feature uses only `lineups_prematch` with `asked_at_utc` < decision. Player props: congestion predicts *non-start* (void), not fewer shots. |
| **Look-ahead in calendars** | Rest and next-match congestion computed from a calendar that includes postponed games, matches added later, or a cancelled midweek game. "Matches in the next 3 days" (a rotation motive) is known only from the schedule as published then. | Build the calendar from listings as cached before the kick-off. Exclude postponed, cancelled and awarded games from "played". Count only *past* matches for fatigue. Use future fixtures only if their listing snapshot predates the decision. The repo battery's `as_of` test (`test_measure_feature_battery.py`) is the template. |
| **Measuring against the wrong baseline** | The repo's F3.2 and 10-04 results are against the raw sample mean. A correction for printing must beat **the price** and the current p. | Primary metric: ΔBrier / Δlog-loss of `logit(p_current) + feature` on a time hold-out. Secondary: the gap to the de-vigged price (as in the 11-05 battery). Then the printed-leg excess within a 1/odds band (10-31 protocol). |
| **Multiple comparisons** | Around 30 football and 20 tennis families x directions x several schedule definitions (rest 2/3/4 d, 3-in-7, 2-in-4, minutes, sets, travel) is hundreds of cells. The 11-05 battery expected about 305 of 6,104 cells "significant" at p < 0.05 under the null. | Freeze the feature list and definitions before looking. BH q = 0.10 over all cells. One time hold-out, run once. Prefer one pooled coefficient per mechanism (e.g. "attacking output under rest < 3 d" across shot / goal / corner families) over per-market fits. |
| **Small effects need large n** | Literature effects are a few pp at most. The repo's significant cells are about 1e-4..1e-3 Brier. On printed legs, a context cell holds 100-600 matches, so CIs run ±4-8 pp. | Power before testing: with p ≈ 0.75, detecting 2 pp needs about 2,000 independent matches. Evaluate on history (300k matches) for the model, and use settled Superbet lines (12.5k matches) only for the price comparison. A match bootstrap is mandatory (legs of one match are dependent). |
| **Rare flag definitions** | `CONGESTED` = >= 3 in the previous 7 d hits 0.2% of football matches, so it is useless as a covariate. | Use continuous rest (capped at 21 d) and a difference in rest. Define 2-in-4 / 3-in-8 windows where n is adequate. Report coverage per definition. |
| **Selection in tennis** | Recent matches and minutes are higher for players who keep winning (form), and lower for those who lost early. Walkovers and retirements break "minutes". The Sackmann caveat: a short match is a sign of strength. | Condition on the in-tournament round and the rating. Use minutes per set or the opponent-adjusted length. Treat a retirement or walkover as missing. Separate best-of-5 from best-of-3. |
| **Market already prices it** | Bundesliga running is priced, NBA B2B is mostly priced, NFL rest is priced and over-priced (mini-bye). | A feature only matters if it improves p **relative to the price**. Pre-register the price-gap test. Expect that a calibration improvement leaves ROI unchanged, as the repo saw for line curves and the price-gap offset. |
| **Interaction with existing switches** | Fatigue is already in the tennis rating (winner p). Adding it again in the point model double-counts. Football round / table switches (`FOOTBALL_FORM_TABLE`) overlap with season phase. | Ablate against the current chain. For tennis, add fatigue only to markets that do not pass through `lps` / the rating, or refit jointly. |
| **Curves refit on history, epochs** | A correction changes p, so curves fitted without it are miscalibrated. | Behind an `epochs` switch from the next day 00:00Z. Replay the rule in the refit (`fitted_from.replay_rules`). Separate ledger group. |

### Expected effect sizes, condensed

**Football:**

- Result after <= 3 d rest: about 0 to -3 pp win% (Scoppa, Bengtsson: very limited; Kitman: none for CL / EL; Sky -0.1 PPG weak).
- Attacking output under 2-in-4: negative, unquantified (Stüttgen). The repo: rest raises shot-count OVER probability by small, significant amounts.
- Goals after a >= 21 d layoff: about -0.12 goals; corners about -0.28 against the sample (repo, confounded with the season start).
- Cards / fouls: no evidence of an effect.
- Travel in Europe: about 0; altitude large but niche; new manager about 0 against a form-aware rating.

**Tennis:**

- Previous match >= 4 h (best-of-5): expected wins x0.76-0.83.
- Best-of-3 tours: the repo's own fit gives about -1.2 pp per extra hour (TOUR) and -5..-10 pp for rust after > 21 d.
- Games / serve: unknown.
