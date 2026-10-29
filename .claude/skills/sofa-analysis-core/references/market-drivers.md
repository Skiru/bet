# Market drivers - what moves each market family, and where to read it

Operator ruling 2026-10-29: for **every** leg the analyst checks the factors that drive that
market (style of play, players, crosses, statistics, format), grounded in the literature. Read
this file once before the first match; then consult the block of each market family you read.
Distilled 2026-10-29 from two literature reviews (football counts; tennis / hockey / basketball
/ volleyball / CS2). Grades: **S** solid (peer-reviewed and replicated, a rule, or arithmetic of
the Laws / format), **M** one study or several partly agreeing, **W** weak (blog, thesis,
preprint, slides, secondary citation), **F** folklore (nothing found - listed only so it is not
mistaken for evidence). A number appears only where a review read it in a source.

**How to write it.** Per market family, in the `**Czynniki rynku.**` section (football: inside
`**Styl gry i zestawienie.**`), name the drivers you checked and their values (format only, e.g.
"rożne Arisu przy posiadaniu < 50%: n=<k>, średnio <x>, linia <l>"), then the expectation in the
market's units against the line. "brak danych" is an answer; silence is not.

**What the model already holds - do not count it twice.**

| sport | held by SHEET / CONFIDENCE |
|---|---|
| football | recent rates per side; opponent correction; venue; league prior; referee's shrunk cards / fouls rate since 2026-10-21 (`referee_rule` on the row); closeness term in cards / shots totals; a footballer's shrunk share of his side's shots / SOT / fouls (`bet.sofa.player_share`); per-line curves on 33 keys |
| tennis | rating (Elo-type), surface, hold / break through SHEET's serve / return; class curves (women, team cups) |
| hockey / basketball / volleyball | the sport's score model (team ratings, league rate; basketball season restart) - **no rest term** |
| CS2 | the CS2 engine: map pool, Elo, lineup gap for unrated pairs, series mixing |

The price is the market's consensus and the best single predictor of match winners in every
sport compared (tennis: Bookmaker Consensus Model best, Elo best of the history models -
Kovalchik 2016, JQAS 12(3), S as replicated). So the check is **error detection**: what the
price and the model cannot know or misread - a stale input, a style mismatch the rates average
away, a lineup / goalie / roster / format change. It is not edge-finding.

**Removal basis:** core, "What a removal's reason must name" - football only, a `RYNEK:`
WATCH at threshold (a) (the opponent's concession k/n, operator 2026-10-29) or (b) (corners
without the ball). A k/n at the threshold is the evidence whatever the driver's grade; a driver
without one: S / M a note, W / F nothing. Tennis and the measured sports: a note.

---

## 1. Football

### 1.0 Forces on every count (read first)

| driver | effect | grade | source |
|---|---|---|---|
| Game state: trailers push, leaders sit back | losing teams have more possession (p<0.01); leader's corner rate lower; trailing-by-1 shot share 53.4% vs leading 46.6% | M (possession, corners) / W (shot shares) | Lago-Peñas & Dellal 2010; Lago 2009; Peng, Hu & Swartz 2024; Pugsley 2013 (StatsBomb blog) |
| Expected script from the price ladder | heavy favourite leads long -> its late corners / shots down, underdog's late share up | M (inference from the above) | Peng et al. 2024 (odds in the corner model) |
| Implied total goals | +16.7% corners per +1 implied goal (coef 0.1545, CrI 0.105-0.207); abs(supremacy) ~0 on the mean, widens the variance (shape CrI crosses 0) | M | Yip, Zou, Hung & Yiu 2024, JORS 75(11) |
| Home | more shots (+26% Turkey, same accuracy) and corners; home yellows x0.90 | M (counts) / S (cards, England / Big 5) / W (x0.90, slides) | Seçkin & Pollard 2008; Dawson et al. 2007; Buraimo et al. 2010; Philipson 2023 |
| Venue splits the count more than it moves the total | home cards ~10% lower, away higher; crowd size / partisanship modulate cards | M | as above; Leitner & Richlan 2021; Bryson et al. 2021 |
| Small samples regress | first-half shot attempts explain ~26-34.5% of second-half variance (MLS); SOT more repeatable than total shots; save% / shooting% ~no predictive value | W (consistent blogs) | ASA 2013 / 2015; FiveThirtyEight; StatsBomb |
| xG beats goals for prediction | out of sample, esp. small samples; shots + corners ratings beat goal ratings in O/U | S | Bréchot & Flepp; ASA 2014; Wheatcroft 2020 (IJF 36(3)) |
| Dispersion | goals VMR ~1.04; corners overdispersed VMR ~1.19 (1.10 La Liga - 1.30 UCL), clustered; team yellows underdispersed (VMR ~0.6-0.8), home / away yellows positively dependent (τb 0.08-0.18) | M (goals, corners) / W (cards) | Yip et al. 2024; Dixon & Coles 1997; Peng et al. 2024; Philipson 2023 |

**Rule at n = 10:** read a side's count against its **process inputs** (corners: crosses,
blocked shots, final-third entries, box touches; SOT: shots and shots inside the box; saves: the
opponent's SOT). A count far from what its inputs imply will probably regress - an inference
from the repeatability literature, not a measured corner result (W).

**Where (all football blocks):** dossier `style.home` / `style.away` - `.means` and `.games[]`
(last 10 competitive games: `corners` [za, przeciw], `corners_1h`, `corners_2h`, `possession`,
`crosses` [attempted za, przeciw], `box_touches`, `shots_inside_box`, `shots`,
`shots_on_target`, `offsides`, `fouls`, `saves`, `blocked_shots`, `shots_outside_box`,
`big_chances`, `xg`, `final_third_entries`, `long_balls`, `throw_ins`, `goal_kicks`), `.corners_by_own_possession.
{posiadanie_ponizej_50, posiadanie_50_plus}.{n, rozne_za, srednia}`; `style.league`
{`competition`, `games`} (absent below 30 games); `style.matchup[]` (per count leg: own k/n,
`opponent_conceded` k/n, a total's both sides' games, league `share` - k/n in the leg's
direction); `header.referee` and the row's `referee_rule`; `lineups` (predicted / confirmed,
missing / doubtful, `regulars_not_in_xi`, `player_legs`); `samples.schedule` (rest); `table`;
`head_to_head`; `market.rungs_of_leg_markets` (the legs' ladders at the offer fetch - no
line-move history for football); the web for news / weather / crowd. **Who has
the ball tonight:** Superbet's `result_1x2` / handicap ladder plus both sides' `possession`
means (teams keep less of the ball against strong opponents - Lago-Peñas & Dellal 2010, M). The
`style` window is the last 10 competitive games; the leg's próbka is SAMPLES' own selection -
they can differ.

### 1.1 Goals - total, halves, team, BTTS, score markets

| driver | effect | grade | source |
|---|---|---|---|
| Attack / defence strength (rating) | goals ~independent Poisson given strengths | S | Maher 1982; Dixon & Coles 1997; Heuer, Müller & Rubner 2010 |
| xG / shots ratings over goals | goals vs xG gap regresses | S | Bréchot & Flepp; ASA; Wheatcroft 2020 |
| Low-score dependence | 0-0 and 1-1 more frequent than independent Poisson, 1-0 / 0-1 less | S | Dixon & Coles 1997; Karlis & Ntzoufras 2003 |
| Time profile | 43% of goals in the 1st half, 57% in the 2nd (Bundesliga); minutes 1 and 46 ~50% below trend; rises after 87' | M | Heuer & Rubner 2012 |
| Score dependence | at 0-0 the last 5 min ~20% below average; the conceding side's rate ~-10% for ~10 min; home rate falls once ahead | M | Heuer & Rubner 2012; Titman et al. 2015 |
| Red card | the 11-man side scores at +88%; yellows do not change goal rates | S | Ridder et al. 1994; Červený et al. 2018 |
| Home advantage | survived ghost games, smaller (home win 44.3% -> 42.2%, 63 leagues) | S / W (CIES figure) | Pollard; CIES; Leitner & Richlan 2021 |
| Mutually beneficial draw (last group round) | more draws | M | arXiv 2601.09673 |
| Weather | no robust goals-total effect | W/F | Biology of Sport 2024 |

- **Where:** `style.*.games[].xg`, `big_chances`, `shots_on_target`, `shots_inside_box` both
  ways; `lineups` (missing striker / keeper); the goals ladder; for halves the 1st-half rate against the
  full-match line.
- **Score markets** (result + over/under, double chance, DNB, handicap, BTTS combos, clean
  sheet) are functions of the joint goal distribution: the draw and 0-goal cells are inflated by
  low-score dependence (S); result and total are correlated - never read a combo as a product of
  marginals.
- **Red flags:** goals UNDER where both sides' xG (for and against) is high; goals_for OVER
  built on a run where goals well exceeded xG; a 1st-half OVER between two cautious sides priced
  off full-match rates; BTTS / both-over in a low-total match read as a product (overstates the
  both-score region); a combo whose supporting stat (the favourite's shots / corners) is the
  same game state counted twice.
- **Not a driver:** momentum / a scoring streak (F); weather on goals (W/F).

### 1.2 Corners - total, team, halves, both_over, handicap

| driver | effect | grade | source |
|---|---|---|---|
| Recent own corner rates of both sides | strongest team predictors (3-match averages, coef ~0.60) - a short window carries signal, not that it is unbiased | M | Yip et al. 2024 |
| Implied total goals | +16.7% per implied goal | M | Yip et al. 2024 |
| Competition baseline | significant league effect; VMR 1.10-1.30 | M | Yip et al. 2024 |
| Team strength / who has the ball | weaker side (higher odds) waits longer for corners | M | Peng et al. 2024 |
| Game state | leading lowers the rate; losing teams get more corners (W thesis); top-six took corners winning / drawing, bottom-six mainly losing / drawing | M / W | Peng et al. 2024; Ashimolowo (thesis); Strafford et al. 2019 (abstract) |
| Home | shorter waits, small effect | M | Peng et al. 2024; Pollard & Pollard 2005 |
| Clustering | a corner often followed by another within ~0.6 min | M | Peng et al. 2024 |
| Crosses, wide play, blocked shots | mechanism of Law 17 (deflected / blocked behind); effect size unmeasured | S mechanism / F size | Laws of the Game |
| Shots on target | ~0, not significant once corners and odds are in | M | Yip et al. 2024 |
| Halves | half indicator not significant (−0.025, SE 0.048); no verified corner split by half | M | Peng et al. 2024 |

- **Where:** `style.*.games[].corners` [za, przeciw], `corners_1h` / `corners_2h`, `crosses`,
  `blocked_shots`, `final_third_entries`, `box_touches`, `possession`;
  `corners_by_own_possession`; `style.matchup[]` (own k/n vs `opponent_conceded` k/n, league
  share); `style.league`; the 1x2 / handicap and goals ladders. Use the cached half splits,
  never an assumed 45/55.
- **Red flags:** corners OVER for a side without the ball whose `posiadanie_ponizej_50.srednia`
  is under the line (core threshold (b)); corners OVER against an opponent that concedes few
  (core threshold (a) - the low block's size is F, the k/n is the evidence); corners_total OVER in a
  match priced at low total goals; a recent average inflated by one or two games trailed from
  early on (check goal minutes against the splits); a corners average well above what crosses +
  blocked shots imply (regression, W); both_over on a lopsided pair - the underdog's own line
  binds; a heavy favourite's corners_for OVER expected to lead long (Peng: leading lowers the
  rate).
- **Not a driver:** "corners predict goals" (W, ~2-3% of corners score); SOT drives corners (not
  significant); rain / wind (F); the referee (F); set-piece takers / tall players as a count
  driver (F - conversion only).

### 1.3 Cards / card points - total, team, halves, handicap, both_over, reds

| driver | effect | grade | source |
|---|---|---|---|
| Referee | referees differ significantly; Big-5 multiplicative ~x0.77 to ~x1.27 after league and team | S (exists) / W (range) | Dawson et al. 2007; Philipson 2023 (slides) |
| League | yellows per team EPL 1.60 ... La Liga 2.49 (~x1.5); cards per foul ~0.10-0.20 across 63 leagues | W but consistent | Philipson 2023; CIES WP497 |
| Team identity | team effects ~x0.6-1.4 (read off a plot) | W | Philipson 2023 |
| Venue and crowd | away side more cards; home x0.90; ghost games home yellows for fouls +26.2%; louder noise -> more away yellows (experiment). Not universal (Turkey 2005/06 no gap) | S (England / Big 5) | Dawson 2007; Buraimo 2010; Leitner & Richlan 2021; Bryson 2021; Unkelbach & Memmert 2010 |
| Game state / time | yellows rise with time, peak at goal difference 1; badly losing favourite escalates | M | Zhao & Zhang 2023; Buraimo 2010; Titman 2015 |
| Closeness / strength | sanctions higher in balanced games, weaker teams sanctioned more (secondary); fouls uncorrelated with rank gap (CSL) | W/M, conflicting | Dawson 2007 (secondary); Liu et al. 2025 |
| Derby / rivalry | EPL derbies ~26 vs 22 fouls (CI +1.4 to +5.7); Bundesliga none; Serie A excess from one rivalry | W | Harvard Sports Analysis 2015 / 2018; a Serie A study seen only via an FT / NYU summary |
| VAR | league-dependent (fewer yellows Italy / Germany / Spain..., more EPL) | W | UPM review |
| Reds | frequency not affected by margin or strength gap; no pre-match driver beyond referee and league | M | Zhao & Zhang 2023 |

- **Where:** `header.referee` (named? - none = x1 in the model; `games` / cards are his career,
  all competitions) and `referee_rule` on the row; `style.*.games[].fouls`
  both ways; the ladder (closeness); `table` and the web (derby, decider, crowd, stadium ban).
- **Already in the model:** referee shrunk rate and closeness - check only that the referee is
  named and his sample is not tiny; do not add them again.
- **Red flags:** cards OVER with an unnamed referee or one with < 10 matches on record; cards OVER
  in a lopsided match (supremacy above ~1.5 goals; M/W inference); team cards_for OVER on a home
  side in a full stadium; cards UNDER with a derby + strict referee (W + S: a WATCH at most
  through a dated fact); a La Liga / Serie A base applied to an EPL / Bundesliga fixture or the
  reverse; a single team's high card rung priced on Poisson (real distribution underdispersed -
  Poisson overstates both tails, W); both_over read as a naive product (home and away yellows
  co-move, W); 1st-half card lines are low-count - check the period splits.
- **Not a driver:** "derbies always mean more cards" (W, inconsistent); "big games / late-season
  stakes raise cards" (F); "referee biased against club X" (unsupported once volume is
  controlled, M - Constantinou et al. 2014); weather (only CSL temperature-on-fouls, M one
  league).

### 1.4 Fouls - total, team, both_over, player fouls drawn

| driver | effect | grade | source |
|---|---|---|---|
| League and referee | calling threshold differs; fouls drop under VAR in several leagues | M | §1.3 sources |
| Possession | you foul without the ball and are fouled with it ("very strong" correlation, ~1,000 games, paywalled) | W | Tomkins Times |
| Game state / time | fouls rise with time, fall as goals accumulate | M | Zhao & Zhang 2023 |
| Derby | EPL +1.4 to +5.7 fouls (95% CI) | W | Harvard Sports Analysis |
| Temperature, season stage | cool (≤ 20°C) 30.7 vs 27.6-27.9 fouls; rounds 1-10 30.5 vs 28.1 (CSL) | M (one league) | Liu et al. 2025 |
| Strength gap | no correlation (r = −0.011) | M | Liu et al. 2025 |
| Player fouls drawn | no football study (F); basketball analogue: ball time, drives / dribbles | F / W | Cleaning the Glass |

- **Where:** `style.*.games[].fouls`, `possession`; the ladder; the referee; for player fouls
  drawn the leg's próbka and `lineups.player_legs` (XI / bench / missing).
- **Red flags:** a ball-dominant favourite's fouls_for OVER (expected > 60% of the ball, its
  fouls in high-possession games under the line); both_over - the ball-dominant side's line
  binds; player fouls drawn OVER on a player who may not start or is in a new role, or whose
  recent count came against high-foul opponents / a strict referee not present tonight; a sample
  under 10 starts is mostly noise.

### 1.5 Shots / shots on target - total, team, both_over SOT, player

| driver | effect | grade | source |
|---|---|---|---|
| Team shot rates | the most repeatable team signal; SOT more repeatable year to year than total shots | W (consistent) | ASA 2013 / 2015 |
| Shots / SOT over goals | shots + corners ratings beat goals in O/U (~+0.8% per bet over 12 years, 10 leagues) | M | Wheatcroft 2020 / 2021 |
| Game state | trailer out-shoots (TSR 53.4% at −1) | W | Pugsley 2013 |
| Home | +26% shots, same accuracy (Turkey) | M | Seçkin & Pollard 2008 |
| Weather | counter-attack shots fall with heat (OR 0.55, UCL) | M (one study) | Biology of Sport 2024 |
| Shooting accuracy per player | ~0 repeatability; shots per 90 most repeatable striker metric, SOT per 90 second | W | StatsBomb |
| Player shots | team volume x player share (in the model); minutes dominate the count | W/F (no prop study) | - |

- **SOT = shots x accuracy:** build it from `shots` and `shots_inside_box` /
  `shots_outside_box`, not from past SOT ratios alone.
- **Where:** `style.*.games[].shots`, `shots_on_target`, `shots_inside_box`,
  `shots_outside_box`, `blocked_shots`, `xg`, `big_chances` both ways; for a player
  `lineups.player_legs` and the web (role, minutes, manager change).
- **Red flags:** SOT OVER where the side's SOT / shots in the last 10 runs well above its season
  or league norm (accuracy is noise - regresses); a heavy favourite's shots_for OVER (leads
  early and slows; the leader's TSR 46.6%, W); both_over SOT - the underdog's line binds, check
  its away SOT against top-half sides; a shots line inflated by opponent reds in the sample; a
  player shots OVER after a role change, a return from injury (minutes cap) or a manager change
  (shares stable only within a role).

### 1.6 Goalkeeper saves - total, team

- **Mechanism (S, definition):** saves = opponent SOT − goals from them. Volume (the opponent's
  expected SOT) is the driver; the keeper's save rate is mostly noise (consecutive 100-SOT
  samples r ~0.13, ~0.23 xG-based; W, StatsBomb).
- **Where:** `style.*.games[].saves`; the opponent's `shots_on_target` for and this side's
  against; `xg` against; `lineups` (a backup keeper changes little about volume).
- **Red flags:** saves OVER on a keeper whose opponent rarely shoots on target (the favourite's
  keeper); a saves line justified by a high save%; the underdog keeper's OVER - volume rises
  with the favourite's shots, but a favourite that leads shoots less.
- **Not a driver:** "an in-form keeper makes more saves" (F, contrary to the repeatability
  evidence).

### 1.7 Offsides - total, team

| driver | effect | grade | source |
|---|---|---|---|
| League | Bundesliga / La Liga higher than EPL / Ligue 1; falling over 10 seasons | M | Zhao 2021, Front. Psychol. 12:719270 |
| VAR era | fewer offsides after VAR | M | Zhao 2021; Turkey study |
| Winning teams commit more offsides | discriminant analysis, La Liga | M | Lago-Peñas et al. 2010 |
| Opponent's high line / trap | practitioner cases only | W/F | - |
| Runs in behind / through balls | no study | F | - |

- **Where:** `style.*.games[].offsides` [own, and the opponent's conceded through
  `style.matchup`]; web for the manager's defensive line.
- **Red flags:** an offsides OVER priced on an old season (before a manager change or VAR - the
  trend is down); an opponent with a deep block (no room behind; mechanism only, F - a note).

### 1.8 Throw-ins / goal kicks / tackles (both_over), player tackles

- **Mechanism (S, Laws 15-16):** A's goal kicks track B's off-target shots, over-hit crosses and
  long balls; throw-ins track touchline out-of-play events (long balls, aerial duels, direct
  play). Tackles need the opponent to have the ball (S mechanical; StatsBomb / Wyscout
  possession-adjust).
- **Evidence:** Big-5 2022/23 ~39 throw-ins per match (Stone et al. 2025, M); EPL ~35 (2023/24)
  to ~43 earlier; falling with short goal kicks (W); long goal kicks end in a throw-in within 5
  events far more than short ones (285 vs 46 sequences, W); after the 2019 law change J-League
  long goal kicks 14.2 -> 8.85 per match, EPL short share 28% -> 40% (W).
- **Where:** the leg's próbka and `style.*.games[].throw_ins` / `goal_kicks` [za, przeciw] (no tackles in `style`);
  proxies in `style.*.games[]`: the opponent's `shots` minus `shots_on_target` minus
  `blocked_shots` (≈ off target, arithmetic), `crosses` attempted, `long_balls`; `possession`
  and the ladder for tackles.
- **Red flags:** both_over goal kicks where the favourite rarely concedes shots (its goal-kick
  line depends on the underdog's off-target shots); a throw-ins line priced from before a
  build-up manager or the short-goal-kick era; a player tackles OVER on the ball-dominant
  favourite (few tackle chances); a tackles sample from another position.

### 1.9 Penalties - total, team

| driver | effect | grade | source |
|---|---|---|---|
| Attacking volume / time in the box | once possession and box time are controlled, home status alone is no penalty bias | M | Constantinou, Fenton & Pollock 2014 |
| Home and crowd | more disputed / incorrect penalties to the home side; crowd proximity modulates | M | Dohmen 2008 |
| VAR | more penalties awarded (Turkey; EPL window) | W/M | - |

- **Where:** `style.*.games[].box_touches`, `shots_inside_box` both ways; the referee (rare
  events - shrink hard); league VAR status (web).
- **Red flags:** penalties_for YES on a low-box-touch underdog; any penalty leg resting on a
  referee's "penalty-happy" record from < ~30 matches (an inference from count noise, not a
  measured cut).
- **Not a driver:** a raw ~70% home share of penalties (W, unadjusted for volume).

---

## 2. Tennis

**Mechanism (S, maths):** under iid points, hold% follows from p(server wins a point); games,
sets, tiebreaks and the match follow hierarchically (O'Malley 2008; Newton & Keller 2005; Newton
& Aslam 2009). iid is a good approximation
- deviations small, stronger for weaker players (Klaassen & Magnus 2001, S).
A meeting's serve% = server's serve% combined with the returner's return%, relative to tour
average (Barnett & Clarke 2005, S). The hold curve is steep near p 0.6-0.7: small serve errors
blow up in set-score and tiebreak markets.

**Where (all tennis):** `02_fixtures.json` `default_period_count` and the dossier
`header.best_of` (format); `header.surface`; the read-set leg fields (estimator, sample, notes);
dossier `sides` (form), `samples.schedule` (rest); the web (event rules: match tiebreak, no-ad;
injury, MTO, strapping, retirement in the last 2 weeks, doubles withdrawal; the previous match's
length and finish time; travel between surfaces / continents).

| family | drivers (grade, source) | red flags |
|---|---|---|
| **games total, player games, games handicap** | two high holds -> long sets, more 7-5 / 7-6 -> OVER; large serve+return gap -> 6-0 / 6-1 / 6-2 -> UNDER and the stronger player's share up (S, maths of 1.1); surface moves aces ~53-145% of average but serve points won stays >= ~90% of average - second-order for totals (M, Tennis Abstract speed ratings; the 90% point from search summaries of the series); altitude: more aces / serve points won (M, 122 matches, weaker on clay); women hold less -> more breaks, fewer tiebreaks (direction S; numbers W, forum) | UNDER on two close-rated big servers; OVER on a strong mismatch where the favourite is the better returner; a "hard" leg at an event that plays slow, priced from season-wide hard samples; a serve sample under ~10 matches on the surface not shrunk; men's hold rates on a women's leg; OVER on a player who retired in his last match |
| **sets total, set score** | format decides the support: Bo5 {3,4,5}, Bo3 {2,3} (S, rule; the pipeline refuses unknown Bo5); Bo5 amplifies the favourite (70% Bo3 ≈ 63.7% per set ≈ 74.4% Bo5, S maths); a large gap -> P(2-0) up; even pair -> highest variance | a men's Slam leg priced by a Bo3 estimator or the reverse (Davis / United Cup, qualifying vary); a match tiebreak in place of set 3 (doubles, some ITF / team events) changing every games line |
| **per-set games / handicaps, set winner** | p(set2) ≈ p(set1) ≈ p_set pre-match (nothing conditions it); momentum small and uncertain once ability is modelled (W-M: Klaassen & Magnus 2003 as cited; arXiv 2009.05830 preprint) | set-2 games read like set-1 after a medical issue / retirement risk (a structural difference, not momentum) |
| **winner / match handicap** | rating gap - the price holds it; disagreement with the price is more likely the sheet's error (S: Kovalchik 2016 as summarised; NTU men odds best, women a weighted Elo composite best on accuracy, M; WElo better on 60k matches, M as author claim); favourite-longshot bias: short favourites slightly under-priced on average, strongest between low-ranked players, later rounds (S: Forrest & McHale 2007; Lahvička 2014) - direction only, small | a winner leg far from the price with no stale input to explain it; a fatigue spot: 4+ h match the day before, back-to-back days with an early second match (TA: x1.07 after < 1:30 vs x0.76 after >= 4:30 against Elo, 7,200 Slam matches, M confounded; women's risk after 3-set rounds, W) |
| **aces, double faults** | event speed (ace-based, Monte Carlo 0.50 ... Chengdu 1.57, M); altitude (M); serve markets are kept off the SHEET replay (model-state) | aces leg read off the nominal surface instead of the event's own ace history; first week of a new surface (thin, old samples) |
| **tiebreak (total / in a set, 7-6)** | frequency follows both holds (S, 1.1); results ~random beyond serve / return, regress year to year (M, TA two analyses); serving first negligible (ATP 50.8% vs 48.8% expected, 5,200 TBs; M); pressure: hold at 4-5 ATP −1.4%, at 5-6 WTA −5.2% - slightly fewer TBs than iid (M); servers win ~3.4% fewer points in a TB (M) | tiebreaks_total OVER in a WTA match between two weak servers; a leg leaning on a player's tiebreak record |

**Retirements:** 1.56 per 1,000 games men, 1.36 women; more on hard / clay than grass; rising;
ITF men vs ATP IRR 1.23 (secondary) (M, PLOS ONE 2024, 852k matches). A retirement refunds on
settlement, but a carried injury moves set 1 / games before it.

**Not a driver (tennis):** tiebreak "clutch" / specialist (F, regresses); "loses set 1, tanks
set 2" (F); per-player Bo5 multipliers (W, noisy); h2h as such; indoor / ball type as separate
drivers (F - use event speed); Court Pace Index for totals (F/W).

---

## 3. Hockey

**Where:** read-set leg fields (score model, player model); dossier `sides`, `samples.schedule`,
`table`, `market`; `lineups.*.starters` is the **dressed roster with both goalies - never the
starting goalie**; the starter comes from the web (confirmed vs projected, morning skate ~1-2 h
before), stated with its source and time.

| family | drivers (grade, source) | red flags |
|---|---|---|
| **totals, team totals** | starting goalie vs backup - the one goalie fact that clearly moves lines (books react mainly to drastic changes; W, ESPN); save% noisy, needs thousands of shots; ~30% of a goalie's deviation carries a season; above-average stays above 59.2% (S noisy / M sizes: Hockey Graphs; Macdonald et al.; FiveThirtyEight); shot attempts / xG predict goals better than goals (S, Macdonald 2012); xG ≈ score-adjusted Corsi at 20 games, better after (M, Hockey Graphs 2015); PDO / shooting% regresses to ~1.000 (S) | a backup starting the 2nd night of a back-to-back with the price unmoved since the morning (stale - a dated WEB fact); team-total OVER on a team running far above its xG (high PDO), UNDER on a low-PDO side with strong xG; a leg resting on a "hot goalie" |
| **winner, handicap (incl. −1.5)** | home ice ~54-56% (M); bubble: home win% −9.8%, home goals −6.1% (M); score effects: a 50% Corsi team ~55.1% while trailing (S exists / M size, TSN), strongest in P3; margins compress **except** empty-net goals: ENG ~7.0% of goals, ~0.40-0.42 per game in 2024-25's first quarter (W, one outlet); optimal pull earlier than practice (M: Beaudoin & Swartz 2010; Asness & Brown 2018 ~6:10 to go down 1) | a favourite −1.5 judged with no ENG term, either way; a European league read with NHL pull timing (no data, F) |
| **periods (P1 / P2 / P3 totals, period dnb)** | P2 highest-scoring (long change; +17.2% over P1 in 2023-24), P3 ≈ P1 with a goalie in net plus ENGs (M direction / W shares); `HK_LATE_GOAL_IN_MEAN` coded and off | P3 UNDER in a game with a clear favourite expected to lead late |
| **rest / schedule** (acts through every family) | B2B vs 3+ days rest: win odds x0.62 (W-M, Small 2007 slides, old); zero rest 45.0% vs 52.1% on two days, away zero rest 42.2% (W, nhlscraper); goalie on consecutive nights: a save% drop, size disputed (W); westward travel in evening games hurts visitors (M, Roy & Forest; NHL p = 0.011) | the model holds no rest term - a B2B is a note; it acts through the goalie announced since the price |
| **player PP points / player lines** | PP shooting% barely repeatable (split-season R² ~0.01; M, TSN Yost); PP shot generation more repeatable (M); PP1 deployment and PP TOI share drive PP points (M by logic, W/F size); referees even up penalty calls within a game (S exists: Abrevaya & McCulloch 2014 as cited; Beaudoin, Schulte & Swartz) | PP-points OVER on a player moved to PP2, or on the trailing side of a big favourite; PP% over 20 games as the reason |

**Not a driver (hockey):** hot-goalie streaks (M, not predictive); PP% over a short window;
team-specific home / away goal splits (F, noise); referee-crew penalty rates as a predictor (F,
descriptive only).

---

## 4. Basketball

**Where:** read-set leg fields; dossier `sides`, `samples.schedule`, `lineups` (Sofascore
pre-match), `market`; the web: the official injury report at its last update (NBA: by the prior
day, updated to ~30 min before tip) against the price time; load management on B2B second
nights.

| family | drivers (grade, source) | red flags |
|---|---|---|
| **winner, handicap, total** | the margin evolves roughly as Brownian motion with drift (S, Stern 1994; the exact sigma not confirmed by the review - do not quote one); home ~2.2-2.5 pts, home win% in the .540s (M); bubble shrank home / travel effects (M); a star's absence moves the line (practitioner point values ~4-6 for a top star, W; the 2015 FRL paper's result unread); markets believe tanking occurs (M, Alberta WP) | a star ruled Out after the price was taken - the textbook stale leg (dated WEB); a leg priced before the final injury report on a team that rests stars on B2Bs |
| **quarters, halves (handicap, total, 1x2 / dnb / dc)** | scaling: a quarter's drift ~1/4 of the spread, SD ~1/2 of the full-game SD; a half's drift ~1/2, SD ~0.71 (S as maths, conditional on the model) - quarter handicaps much noisier relative to their line; late fouling breaks Brownian motion in Q4 / 2nd half (M, Shirley); blowout bench minutes compress a big favourite's Q4 / 2nd-half margin (mechanism, F size; LSports W) | a quarter edge out of proportion to the full-game spread; a big favourite −X for Q4 or the 2nd half with an expected spread over ~10 (bench quarter); a half-time draw treated as negligible without a number (F, unmeasured) |
| **rest / schedule** (acts through every family) | B2B 2nd night ≈ 1-2.5 pts of margin (M overall: Small −2.26 pts, W-M; Wharton paper (authorship unverified) +0.32 per day of rest, M; 2025-26 journalism −1.5 net rating per 100, W; preprint 44% B2B win rate partly stars resting, W); westward travel in evening games (M, NBA p < 0.0001, the strongest of three leagues); eastward beats westward on B2Bs (M) | the model holds no rest term (`b2b_delta` unset) - a B2B is a note; a WATCH only through who rests, announced since the price |
| **overtime / settlement** | full-game markets include OT; 2nd half / Q4 grade on regulation (rule, S); FIBA / Euroleague 1x2 usually on regulation - a draw possible (rule) | a leg's settlement read wrong for OT (check the market's rule, not a frequency - NBA OT rate not verified) |
| **player lines** | minutes and role; no history curve - `NO_LINE_EVIDENCE` until a family has 50 settled pre-game lines (pipeline) | a starter's prop in an expected blowout; a player whose minutes changed with a teammate's return |

**Not a driver (basketball):** Q1 margin "momentum" (W, one team); "key numbers" (W); a European
home-advantage number (none found, F).

---

## 5. Volleyball

**Mechanism (S maths / M fit):** each rally is a Bernoulli trial depending on who serves; set
and match probabilities follow exactly from (p_A serving, p_B serving) (Ferrante & Fonseca 2013;
fit on Italian top-4 2001-12). A set to 25 won by 2 is a long race: a few points of rally edge
compound into a large P(set) and a steep P(3-0) - **sets total is the family most sensitive to
small rating errors** (S maths; no empirical gap vs P(3-0) table, F).

**Where:** read-set leg fields; dossier `sides`, `table`, `samples.schedule`, `header.first_leg`
(a two-leg tie); the web: the starting six announced, a rested player, cup midweek + league
weekend, the aggregate / standings stake.

| family | drivers (grade, source) | red flags |
|---|---|---|
| **winner, set handicap, sets total, exact set score** | rating gap (above); home ~57% men / ~55% women after strength, d 0.48 / 0.43, crowd size negligible, no decline over 25 seasons (M, van Meurs et al. 2023, 6,833 matches); home edge largest in set 1 and sets 4-5 (W, one competition); sideout% correlates best with set win% (W, VNL 2019); Bayesian set / point models with home advantage (M) | team_sets_exact 3-0 for a favourite that has already qualified and played a cup match 2 days earlier; a second leg where a side needs only 2 sets (mechanism, F/W - stake via a dated fact); a dead rubber / rested starters (no study, F - plausible and large: a dated WEB fact carries it, the folklore does not) |
| **set winner, team wins a set** | sets ~iid given ratings: previous-set winner +7.83% next set (M, JHSE 2024 as summarised, likely partly ability); no carryover in World League (W); beach set 3 no edge for either earlier winner (M) | a leg leaning on momentum from the previous meeting or set |
| **points total, set points, parity, set on extra points** | men: more first-ball kills (71.1% of rallies end in <= 2 net crosses vs 58.2% women, W); men's reception better, women take more serve risk (M, Euro 2019, 1,302 sideouts); so men's sets nearer 25-23, women's more lopsided serve runs (mechanism inferred, W) | men's points distribution applied to a women's match or the reverse |
| **golden set** | a rule: the match is graded on its own sets; the golden set counts in nothing (Regulamin 5.D.3.a, pipeline) | a leg assuming the golden set changes a set count |

**Not a driver (volleyball):** set-to-set momentum; congested fixtures as a proven effect
(college: no decline, W; the pro study's results unread); travel (F).

---

## 6. CS2

**Where:** read-set leg fields (CS2 engine, `lineup_unrated_rule`, `price_gap`); dossier
`cs2.home` / `cs2.away` - `series` (last 10), `map_pool_90d` (n, won, avg rounds per map),
`roster_latest`, `roster_new_vs_previous` (a name not in the previous series - search it),
players' kills / deaths per map; `header.best_of` (never guessed); the web: Liquipedia / HLTV
roster on match day, stand-in / coach / IGL change in the last ~30 days, LAN or online, the veto
once published, the event's OT rule.

| family | drivers (grade, source) | red flags |
|---|---|---|
| **series winner, maps handicap, team maps** | the HLTV ranking predicts results with reasonable power, gaps shrink down the ranking (M, Rejthar & Kotrba 2023); accuracy ceiling ~62-66% (W, theses) - most of the map outcome is noise; Bo3 amplifies the favourite over Bo1 (S maths) but each team picks its best map, the decider by elimination (no literature, F; `CS2_DECIDER_MAP_POSTERIOR` coded and off); market bias has no stable direction (M: reverse FLB, Dagaev & Stoyan; FLB in heavy underdogs, Sweeney et al. 2021; both, JIFS 2024) | a team-maps leg ignoring that the underdog's comfort pick is in the pool; an unknown Bo (the pipeline refuses to guess) |
| **map winner, map round handicap / total** | map-specific strength is large: optimal veto could raise map win probability up to 11% and an even match by 19.8% (M, Petri et al. 2021, modelled); the picking team wins slightly more (W, journalism); side bias: Nuke CT ~55% (CS:GO, 8,000+ games; CS2 est. 55-60%), Overpass ~55/45 CT, Anubis T-sided, Mirage / Inferno / Ancient ~50/50 (W-M, practitioner, direction consistent; patches change it); a strongly sided map with an even pair -> 13-10 / 13-11 / OT, rounds up (mechanism, W/F) | a round-handicap / total leg on "map 1" before the veto with the underdog's pick unknown; a map one side has not played in 90 days (`map_pool_90d` n small - a note with n) |
| **round totals (over 21.5 / 22.5)** | MR12: 24 regulation rounds, first to 13; OT MR3 halves (first to 4 of 6) with reset money in most events (S, rules) - mass at 13-11 / 13-12 and a long OT tail; such lines are very sensitive to P(OT); two pistols per map, round-2 conversion ~90% (W, HLTV-derived); under MR12 each pistol + conversion is a larger share - more per-map variance (S arithmetic, effect on upsets unmeasured) | an event with a non-standard OT rule (online qualifiers) priced on MR3; an over 21.5 on a mismatch |
| **roster / stand-ins** (acts through every family) | after a team switch both player and team perform worse and recover slowly (M, arXiv 2205.09693); ratings lag roster changes; stand-in size unmeasured (F) | a team priced from a rating built on a roster that no longer exists, either way (`roster_new_vs_previous` non-empty - search the name; `CS2_LINEUP_ELO_UNRATED` covers unrated lineups only) |
| **LAN vs online** | no rigorous study (W/F: a single-player 12.6% LAN drop; unnamed research on OT pressure); mechanism plausible (ping, pressure, tier-2/3 online opposition) | a rating sample mostly online under a LAN match or the reverse, under a close-game leg - a note with the sample's n |
| **player kills / deaths / assists / headshots** | the player's share and the map count; economy is an in-play driver, a team trait pre-match with no published predictive value (F pre-match; Xenopoulos et al. 2021 M in-play) | a player line on a new roster; a nickname not matched exactly (engine uses exact, then prefix) |

**Not a driver (CS2):** "pistol specialist"; crowd; pre-match economy style (F).

---

## 7. Gaps the literature does not cover - measurable on `sofa.db`

- Football corners: origin (crosses / blocks / clearances - we hold the inputs, not the cause).
- Football corners: within-match correlation of the two sides' counts.
- Football corners / cards: variance share of league vs team vs referee (random effects).
- Football: corners and shots by game state (incident minutes x half splits).
- Football: how many corners a low block concedes vs opponent possession (the size; the
  `opponent_conceded` k/n itself is the `RYNEK:` basis, operator 2026-10-29).
- Football: corner split by half per league; fouls vs possession by league.
- Football: player fouls drawn vs dribbles / touches.
- Tennis: tiebreak frequency by surface and tour; event speed vs games totals.
- Tennis: previous-match length vs games / sets totals against the rating.
- Hockey: empty-net share outside the NHL; a backup goalie vs the score model's totals.
- Basketball: big favourites' Q4 / 2nd-half margin in blowouts vs Superbet lines.
- Basketball: OT frequency by league; a European home-advantage number.
- Volleyball: rating gap vs P(3-0) / P(3-2); starters rested in low-stakes games.
- CS2: stand-in size; LAN vs online on the same teams; side bias vs total rounds.
- CS2: decider-map effects; whether MR12 changes any CS:GO-era finding.

None has a published answer the reviews could verify; until measured here, each stays a
suspicion - a note, never a removal.
