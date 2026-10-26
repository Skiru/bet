# Literature review: analysing sporting events for betting, for a remove-only analyst

Compiled 2026-10-26 from web search and fetch. Scope: what qualitative information moves outcomes or is under-priced; where markets are efficient or biased; how a human or LLM analyst should reason; and when information arrives.

## How to read this file

- **Evidence grade** on every item:
  - **S** (solid): peer-reviewed and/or replicated in more than one dataset.
  - **M** (moderate): one peer-reviewed study, or a working paper from a reputable series (CEPR, IZA, NBER), not replicated.
  - **W** (weak): a blog, student thesis, industry guide or preprint, or a single small sample.
- **Verification level**:
  - "abstract" means the abstract or a publisher page was read through search or fetch.
  - "secondary" means only later papers or press coverage describing the work were seen.
  - "not verified" means the item was not checked at all.
  - No full text was read. Treat effect sizes as quoted, not re-derived.
- **Implication (remove-only)**: what this means for an analyst who can only WATCH or NO_BET a leg the model proposed.
- **Coverage gaps**: no citation was invented. Where a search found nothing academic, the topic is listed as a gap. Gaps are summarised in section 5.

---

## 1. Qualitative and non-statistical information: what moves outcomes, and is it priced?

### 1.1 Home advantage, crowds and empty stadiums (COVID "ghost games")

**Bryson, Dolton, Reade, Schreyer, Singleton (2021)**, "Causal effects of an absent crowd on performances and refereeing decisions during Covid-19", *Economics Letters* 198, 109664. Links: https://discovery-pp.ucl.ac.uk/id/eprint/10115454 and https://www.iza.org/publications/dp/13578
- **Finding:** Matches without a crowd show fewer yellow cards for away players, so the home–away gap in punishments shrank. The working paper covers 6,481 matches in 17 countries, 1,498 of them without fans.
- **Grade:** M–S. It is a natural experiment and is consistent with several other papers.
- **Implication:** A crowd changes card counts more clearly than it changes results. Crowd context, such as a closed stand, a stadium ban or a neutral venue, is relevant mainly for card and foul legs that lean on home/away splits.

**Fischer & Haucap (2021)**, "Does Crowd Support Drive the Home Advantage in Professional Football? Evidence from German Ghost Games", *Journal of Sports Economics* 22(8), 982–1008. Abstract and secondary: https://www.graduiertenzentrum-medizin.hhu.de/fileadmin/redaktion/Fakultaeten/Wirtschaftswissenschaftliche_Fakultaet/DICE/Bilder/Paper.pdf
- **Finding:** Home advantage fell in Bundesliga ghost games. The working version reports that the odds did not properly reflect the change and adapted slowly or not at all.
- **Grade:** M.

**Deutscher, Winkelmann, Ötting (2021)**, "Bookmakers' mispricing of the disappeared home advantage in the German Bundesliga after the COVID-19 break", *Applied Economics* 53(26), 3054–3064. Links: https://arxiv.org/pdf/2008.05417 and https://ideas.repec.org/a/taf/applec/v53y2021i26p3054-3064.html
- **Finding:** Bookmakers were slow to adjust the odds to the vanished home advantage, which left profitable strategies open for a while.
- **Grade:** M. The sample is short: one league and the first weeks only.

**Meier, Flepp, Franck (2021)**, "Are Sports Betting Markets Semi-Strong Efficient? Evidence from the COVID-19 Pandemic", *International Journal of Sport Finance*. Link: https://fitpublishing.com/node/4991 (abstract)
- **Finding:** Bookmakers and exchanges overestimated the home side's chances in the first ghost-game period. The result is driven by the Bundesliga, the first league back, and a positive net strategy existed for about one month.
- **Grade:** M.

**Hegarty & Whelan (2022)**, "The Wisdom of No Crowds: The Reaction of Betting Markets to Lockdown Soccer Games", CEPR DP17273. Link: https://cepr.org/publications/dp17273 (abstract)
- **Finding:** Across many leagues, lines moved promptly to a smaller home edge. The adjustment was accurate on later matches, even though the first few games suggested a larger shift.
- **Grade:** M (working paper).
- **Synthesis of the four ghost-game papers:** Markets misprice a *new, unfamiliar shock* for a few weeks, then catch up. A persistent, known factor is unlikely to stay mispriced.

**Peeters & van Ours (2020/21)**, "Seasonal home advantage in English professional football 1974–2018", *De Economist*. Links: https://repub.eur.nl/pub/129977 and https://papers.tinbergen.nl/20025.pdf
- **Finding:** The absolute home advantage is 0.59–0.64 points per game, or 0.44–0.46 goals. It is similar across divisions despite very different attendances, and it has declined substantially over time.
- **Grade:** S. It covers a long panel and the trend is widely reported.
- **Implication:** Home advantage is an old, well-known factor. "They are strong at home" is never a reason to doubt a model leg; the market and the model both already carry it.

**Systematic review (PRISMA)**, "The impact of crowd effects on home advantage of football matches during the COVID-19 pandemic". Link: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10653546/
- **Status:** Only the aims were seen, so its conclusions are not verified here.

### 1.2 Referees

**Garicano, Palacios-Huerta, Prendergast (2005)**, "Favoritism Under Social Pressure", *Review of Economics and Statistics* 87(2), 208–216. Link: https://nber.org/papers/w8376 (abstract)
- **Finding:** Spanish referees lengthen stoppage time in close games when the home side trails and shorten it when the home side leads. Crowd size and composition modulate the bias.
- **Grade:** S. It is classic and widely replicated in other leagues.
- **Caveat:** Békés, Borza & Fleck (CEPR DP17924) report that the bias persisted without crowds, so pressure may also come from the host club. Link: https://cepr.org/publications/dp17924 (abstract).

**Buraimo, Forrest, Simmons (2010)**, "The 12th man? Refereeing bias in English and German soccer", *JRSS A*. Link: https://eprints.lancs.ac.uk/id/eprint/45039 (abstract)
- **Finding:** After controlling for the in-game score and earlier cards, there is crowd-related home bias in cards in Germany. Splitting matches by betting-market favourite/underdog status gives evidence of referee bias in both leagues.
- **Grade:** M–S.

**Kruse & Maennig**, Hamburg Discussion Paper 64 (Bundesliga yellow cards). Link: https://econpapers.repec.org/paper/hcewpaper/064.htm
- **Finding:** Referee characteristics, the home effect, a derby, and whether the team is winning all matter for cards.
- **Grade:** W–M (working paper, secondary).

**Referee assignment and betting prices:** No academic study was found on whether card and foul markets price the named referee.
- **Implication:** The referee effect on cards is real. Our model already carries an as-of shrunk referee rate. An analyst should NOT veto on "strict referee" anecdotes; that would double-count. Veto only when the referee *changed* after the sheet was built, and only on card/foul legs.

### 1.3 Altitude, travel, jet lag, rest

**McSharry (2007)**, "Effect of altitude on physiological performance: a statistical analysis using results of international football games", *BMJ* 335:1278. Link: https://www.bmj.com/content/335/7633/1278 (abstract)
- **Finding:** Across 1,460 international matches, each 1,000 m of altitude difference shifts goal difference by about 0.5 goals. Example: Bolivia v Brazil home-win probability is about 0.825, against 0.537 at equal altitude.
- **Grade:** M. Critics argue that team-quality confounding remains.
- **Implication:** Relevant for South American qualifiers, Libertadores, Liga MX (Azteca, Toluca) and Bolivian or Ecuadorian clubs. Only veto when the model sample is altitude-blind *and* the leg depends on the away side's output.

**Song, Severini, Allada (2017)**, "How jet lag impairs Major League Baseball performance", *PNAS* 114:1407–1412. Link: https://pmc.ncbi.nlm.nih.gov/articles/PMC5307448
- **Finding:** About 20 years of MLB data. Eastward jet lag hurts more than westward, and the effects are "sufficiently large to erase the home field advantage". The authors call the effects "subtle".
- **Grade:** M–S. It is peer-reviewed; Joly's PNAS letter disputes causality.

**Ashman, Bowman, Lambrinos (2010)**, *Journal of Sports Economics* 11(6), 602–613. Link: https://ideas.repec.org/a/sae/jospec/v11y2010i6p602-613.html (abstract)
- **Finding:** Over 19 NBA seasons, home teams on the second night of a back-to-back, facing a visitor with one or two days of rest, performed poorly *against the spread*. The penalty was larger after eastward travel.
- **Grade:** M.
- **Caveat:** It is an old sample (pre-2010). Whether the effect persists or survives the vig is not shown.

**Esteves et al.?** (authors not verified), "Basketball performance is affected by the schedule congestion: NBA back-to-backs under the microscope", *European Journal of Sport Science* 21(1), 26–35 (2021). Link: https://lida.sport-iat.de/ta/Record/4069360
- **Finding:** In 2016/17, win probability rose significantly from a back-to-back to one rest day. Extra days beyond one added nothing.
- **Grade:** M. It covers a single season.

**NBA load management:** Only a preprint (arXiv 2402.12400, player box-score effects) and student work were found. No peer-reviewed estimate of how resting healthy starters affects team win probability turned up. **Gap.**

**Carling, Dupont et al. (2012, 2016)**, fixture congestion in football. Links: https://knowledge.lancashire.ac.uk/id/eprint/14080/ and https://bjsm.bmj.com/content/50/12/764
- **Finding (BJSM 2016):** Injury rates and patterns change in congested cycles (two matches within three days, or three within four days). The 2012 IJSM study (8 matches in 26 days) was found, but its conclusion was not verified.
- **Grade:** M for injury risk. There is no betting-market test.
- **Implication:** Congestion predicts rotation and injuries more than it predicts the result. It matters for player props (a starter rested means the prop is voided or the player is subbed early) and for team-count legs only through who plays.

### 1.4 Coach changes ("new-manager bounce")

**Bruinshoofd & ter Weel (2003)**, "Manager to go? Performance dips reconsidered with evidence from Dutch football", *European Journal of Operational Research*. Secondary: https://repec.library.maastrichtuniversity.nl/bck/umamer/2001018.rdf
- **Finding:** Performance improves after a forced change, but no more than in a control group that kept its manager. The "bounce" is regression to the mean.
- **Grade:** S. The regression-to-the-mean result is replicated in several leagues (see the EUR summary: https://www.eur.nl/en/ese/news/irrational-managerial-changes-remain-norm-europes-top-football-leagues).

**Bernardo, Ruberti, Verona (2019)**, "Semi-strong inefficiency in the fixed odds betting market: underestimating the positive impact of head coach replacement in main European soccer leagues", *Quarterly Review of Economics and Finance*. Secondary: https://mpra.ub.uni-muenchen.de/66414/1/MPRA_paper_66414.pdf
- **Finding:** Covers 8,687 matches in four leagues, 2008–14. Coach replacement has a positive average effect that the odds under-price, especially in the first four games; after that the odds corrected.
- **Grade:** M. Profitability after costs was not verified.

**Galdino, Soebbing, Wicker**, Brazilian football, 379 in-season changes, *International Journal of Sport Finance*. Secondary: https://journals.fitpublishing.com/?p=2063
- **Finding:** Some exploitable inefficiencies at specific match numbers after the change.
- **Grade:** M.
- **Implication:** The two strands do not contradict each other: the market may be too pessimistic about the team that changed coach. For a remove-only analyst: a model leg *against* a team that has just changed coach (first 1–4 games) is the case where the literature points to under-pricing of that team. Consider WATCH on such legs. Never veto *for* the team because of a "bounce" narrative.

### 1.5 Motivation, dead rubbers, end-of-season incentives

**Harvard Sports Analysis Collective (2015)**, Serie B end-of-season blog post. Link: https://harvardsportsanalysis.org/2015/07/statistically-proving-corruption-in-serie-b-soccer-and-why-it-may-have-stopped/
- **Finding:** Teams with something to play for beat their odds against teams with nothing to play for in Serie B; it was not found in seven other leagues.
- **Grade:** W.

**Krieger, Pace, Clarke, Girdner**, "Anchoring, affect, and efficiency of sports gaming markets around playoff positioning", *Financial Services Review*. Link: https://openjournals.libs.uga.edu/fsr/article/view/3242
- **Finding:** NFL and NBA teams that have clinched their playoff position: betting against them was profitable at *opening* lines. Closing lines partly corrected, and most of the edge disappeared after commission.
- **Grade:** M.
- **Implication:** Motivation effects are real but are *priced by close*. A dead rubber matters to a remove-only analyst mainly through the lineup (rotation), which arrives late. A WATCH is justified when a dead rubber makes rotation likely and the leg depends on starters; a motivation story alone is not.
- **Gap:** No peer-reviewed study of football dead rubbers against bookmaker odds was found. FIFA's warning about spot-fixing risk in dead final group games is an assertion, not data.

### 1.6 Derbies

**Bäker, Mechtel, Vetter (2012)**, "Beating thy neighbor: derby effects in German professional soccer". Link: https://research.vu.nl/en/publications/beating-thy-neighbor-derby-effects-in-german-professional-soccer/
- **Finding:** Bundesliga 1999–2009. Derbies do not differ significantly in goals, results or referee grades; they are "normal" matches.
- **Grade:** M.

**Gómez-Déniz & Dávila-Cárdenes (2017)**, Spanish cards model, includes a derby factor. Link: https://accedacris.ulpgc.es/handle/10553/35413
- **Grade:** W–M. The size of the derby effect was not verified.
- **Implication:** "It's a derby, anything can happen" is not supported for goals or results. At most, card and foul legs could be affected, and that is not measured. Do not veto goal/result legs on a derby tag. (Kruse & Maennig list derby as a card factor; Bundesliga only.)

### 1.7 Weather

**Rodney J. Paul et al.**, "The Impact of Atmospheric Conditions on Actual and Expected Scoring in the NFL", *International Journal of Sport Finance*. Link: https://fitpublishing.com/node/3503
- **Finding:** Strategies on humidity and wind rejected efficiency of NFL totals, and humidity explained the gap between actual scoring and the total.
- **Grade:** M (NFL only).

**Skidmore thesis, NFL 2013–19.** Link: https://digitalcoll.skidmore.edu/record/6451
- **Finding:** Unders in high-wind divisional games were profitable; the authors expect this to disappear.
- **Grade:** W.

**Sharp Football Analysis (blog).** Link: https://www.sharpfootballanalysis.com/betting/cold-weather-impact-sports-betting-nfl-games-over-under/
- **Finding:** Overs went 58% in 40 NFL games below 20°F, suggesting the market over-adjusts for cold.
- **Grade:** W, small sample.
- **Gap:** No peer-reviewed soccer study quantifying rain or wind against goals or corners markets was found.
- **Implication:** Weather is mostly public and early. The NFL evidence hints that markets sometimes *over*-adjust. Extreme events (a waterlogged pitch, gale-force wind, snow) can justify a WATCH on totals and counts. Ordinary rain cannot.

### 1.8 Injuries, absences, lineups (football, NBA, NHL)

**No peer-reviewed event study** was found that measures football or NBA odds reacting to injury reports or confirmed lineups.

**Industry descriptions (W):**
- Action Network: books auto-scrape news and take games off the board to reprice. https://www.actionnetwork.com/education/how-injuries-affect-betting-lines-a-guide-to-market-movement
- MyBookie: expected or replaceable absences barely move prices. https://www.mybookie.ag/sports-betting-guide/how-injuries-and-starting-lineups-affect-soccer-betting-odds/

**Peeters (2018)**, "Testing the wisdom of crowds in the field: Transfermarkt valuations and international soccer results", *International Journal of Forecasting* 34(1), 17–29. Link: https://repub.eur.nl/pub/102113
- **Finding:** Crowd player valuations of the squad beat FIFA ranking and Elo for international results, with sizable betting gains in-sample.
- **Grade:** M. Replication data exist; domestic-league theses did not reproduce the gain over Elo.
- **Implication:** *Who actually plays* carries information. But national-team squads change a lot between windows, and a pre-match XI is closer to that than a season sample.

**NHL goalies:** ESPN reporting (W) — https://africa.espn.com/espn/betting/story/_/id/42470775/nhl-odds-betting-goaltending-factor
- A backup announcement moved a line from pick'em to −145.
- A DraftKings trader said the starter is priced into the team rating, so a change triggers repricing.
- No academic study of goalie-confirmation timing was found. **Gap.**

**Woodland & Woodland (2011)**, NHL totals market. Abstract: https://ideas.repec.org/a/ebl/ecbull/eb-10-00729.html
- **Finding:** Inefficient, and simple strategies were profitable.
- **Grade:** M, old.

**Implication (strong in practice, weak in the literature):** A confirmed absence that the model sample did not see is the single most defensible reason to remove a leg. Examples: a starting goalie is the backup; a team's top scorer is out for a shots or goals leg; a player prop's player is not in the XI.

### 1.9 Tennis-specific factors

**Forrest & McHale (2007)**, "Anyone for Tennis (Betting)?", *European Journal of Finance*. Link: https://salford-repository.worktribe.com/output/1446019/anyone-for-tennis-betting (abstract)
- **Finding:** Positive favourite-longshot bias across the odds range in men's tennis.
- **Grade:** S (replicated, see below).

**Lahvička (2014)**, "What causes the favourite-longshot bias? Further evidence from tennis", *Applied Economics Letters* 21(2), 90–92. Link: https://mpra.ub.uni-muenchen.de/47905/1/MPRA_paper_47905.pdf
- **Finding:** About 45,000 matches. The bias is strongest between *lower-ranked players*, in *later rounds* and in *high-profile tournaments*. The pattern is consistent with insider information and the public reacting to news.
- **Grade:** S.

**Abinzano, Muga, Santamaría (2016)**, *Applied Economics Letters* 23(8), 605–608. Link: https://academica-e.unavarra.es/handle/2454/18748
- **Finding:** The same pattern holds on exchanges, so it is not caused by bookmaker defensive pricing.
- **Grade:** M–S.

**Fatigue:**
- Tennis Abstract (Jeff Sackmann, blog, W): https://www.tennisabstract.com/blog/2017/06/02/the-negative-impact-of-time-of-court/ and https://www.tennisabstract.com/blog/2012/08/09/the-hangover-effect-of-a-marathon-fifth-set/
  - Over about 7,200 men's Slam matches, Elo-adjusted, the next-match win rate falls steeply with the previous match's duration: about 61% after under 1:30, about 32% after over 4:30.
  - Winners of a fifth set reaching 6–6 won about two-thirds as often as expected next round.
  - **Grade:** W–M. The samples are large, but it is not peer-reviewed and opponent strength is a residual confounder.
- A small 2002 Slam study found the effect of sets played in prior rounds significant for women only. Link: https://lida.sport-iat.de/ta/Record/3039576 (W–M).

**Retirement risk:** Cutmore & Knottenbelt (Imperial College) model retirement probability from the gap between Betfair markets with different retirement rules. Link: https://www.doc.ic.ac.uk/~wjk/publications/cutmore-knottenbelt-mis-2013.pdf (M).
- **Implication:** A visible injury or medical timeout earlier in the week shows up in the price.

**Kovalchik (2016)**, "Searching for the GOAT of tennis win prediction", *Journal of Quantitative Analysis in Sports* 12(3), 127–138. Link: https://www.degruyterbrill.com/document/doi/10.1515/jqas-2015-0059/html
- **Finding:** Compares 11 models on 2014 ATP matches. Elo-type models perform well, with a gap by player ranking.
- **Grade:** M. Details beyond the abstract were not verified.

**"Sports prediction and betting models in the machine learning age: The case of tennis"**, *Journal of Sports Analytics* (2021), DOI 10.3233/JSA-200463 (author Wilkens per later citations; not verified). Link: https://journals.sagepub.com/doi/10.3233/JSA-200463
- **Finding:** ML accuracy does not rise above about 70%. The betting conclusion was not verified.

**Implications for tennis:**
- Lower-tier tennis (ITF, Challenger) is where the price carries insider information and where the longshot bias is largest. A model leg that *disagrees* with the price there is the leg most likely to be wrong.
- A long or late previous match is a measured (if weakly sourced) negative that our SHEET does not model. It is a legitimate WATCH reason for legs that need the tired player to perform: his games won, a handicap, or a set win. It is not a reason for a "games over" leg.

### 1.10 CS2 and esports

**Dagaev & Stoyan (2019)**, HSE WP 216/EC/2019, CS:GO parimutuel betting. Link: https://ideas.repec.org/p/hig/wpaper/216-ec-2019.html
- **Finding:** A *reverse* favourite-longshot bias (underdogs overbet), with profitable underdog strategies in and out of sample, linked to popular teams and geography.
- **Grade:** M (working paper; a skins/parimutuel site, not a bookmaker).

**"Re-examination of eSports betting markets"**, *Journal of Intelligent & Fuzzy Systems* (2024). Link: https://journals.sagepub.com/doi/10.3233/JIFS-232932
- **Finding:** Both normal and reverse favourite-longshot bias, varying by title and tournament.
- **Grade:** M. Authors not verified.

**Sweeney et al.** (via the Tampere PlayLab summary): https://blogs.tuni.fi/playlab/game-research-highlights/esports-gambling-rooting-for-the-home-team/
- **Finding:** Favourite-longshot bias for heavy underdogs only; strongest for a European underdog against a non-European team, a home-bias angle.
- **Grade:** W (secondary only).

**HSE study**, *Journal of Economic Behavior & Organization* (per the HSE press release): https://hse.ru/en/news/991687798.html
- **Finding:** CS:GO players perform about 30% better *online* than on-site in overtime situations; the audience raises stress ("choking").
- **Grade:** M. The figure is overtime-specific, from press-release wording.
- **Implication:** LAN versus online is a real context shift. A model sample built mostly on online matches, applied to a LAN with a crowd, deserves a WATCH on close-game legs (overtime or round totals).

**Stand-ins, map pool, roster changes:** No academic study was found. **Gap.** Practitioner logic applies, as with football absences: a stand-in the sample never saw is an unseen change.

### 1.11 Volleyball

No academic study on volleyball betting-market efficiency or context factors was found in this pass. **Gap.**

---

## 2. Market efficiency: where markets are efficient and where they are biased

### 2.1 General picture

**Levitt (2004)**, "Why are gambling markets organised so differently from financial markets?", *Economic Journal* 114(495), 223–246. Link: https://ideas.repec.org/a/ecj/econjl/v114y2004i495p223-246.html
- **Finding:** Bookmakers do not balance books. They set prices and take positions, earning from better forecasting *and* from exploiting bettor biases. Bettors in his NFL contest data could not systematically beat the book.
- **Grade:** S (highly cited).

**Forrest, Goddard, Simmons (2005)**, "Odds-setters as forecasters: the case of English football", *International Journal of Forecasting*. Link: https://salford-repository.worktribe.com/output/1472154/odds-setters-as-forecasters-the-case-of-english-football
- **Finding:** About 10,000 matches. Published odds became increasingly accurate over five years, and a benchmark statistical model did not outperform them.
- **Grade:** S.

**Štrumbelj (2014)**, "On determining probability forecasts from betting odds", *International Journal of Forecasting* 30(4), 934–943. Secondary: https://pypi.org/project/shin
- **Finding:** Odds are the most accurate public forecast. Shin's de-margining beats basic normalisation because it accounts for favourite-longshot bias.
- **Grade:** S.

**Angelini & De Angelis (2019)**, "Efficiency of online football betting markets", *International Journal of Forecasting* 35(2), 712–721. Link: https://ideas.repec.org/a/eee/intfor/v35y2019i2p712-721.html
- **Finding:** 41 books, 11 leagues, 11 years. At the best available odds, 8 of 11 league markets are efficient and 3 show exploitable inefficiencies.
- **Grade:** S–M.

**Croxson & Reade (2014)**, "Information and Efficiency: Goal Arrival in Soccer Betting", *Economic Journal* 124(575), 62–91. Link: https://ideas.repec.org/a/wly/econjl/v124y2014i575p62-91.html
- **Finding:** On exchange data around goals, "prices update swiftly and fully" to clean news.
- **Grade:** S.
- **Implication:** Clean, public, sharp news (a goal, an official lineup) is priced within seconds or minutes. An analyst cannot beat the price on such news; it can only make sure the *model* has not missed it.

**Kaunitz, Zhong, Kreiner (2017)**, "Beating the bookies with their own numbers – and how the online sports betting market is rigged", arXiv:1710.02824. Link: https://arxiv.org/abs/1710.02824
- **Finding:**
  - The cross-book average of odds is a strong probability estimate.
  - Betting outlier soft-book prices against that consensus was profitable over a 10-year closing-odds simulation, a 6-month minute-by-minute simulation and 5 months of real money (about 9.9% reported in secondary coverage).
  - Accounts were then limited.
- **Grade:** M (preprint, widely reported).
- **Implication:** The *consensus price* is the strongest public forecast. Soft-book outliers relative to the consensus are where value exists, not model–price disagreement as such.

**Hubáček, Šourek, Železný (2019)**, "Exploiting sports-betting market using machine learning", *International Journal of Forecasting* 35(2), 783–796. Link: https://ideas.repec.org/a/eee/intfor/v35y2019i2p783-796.html
- **Finding:** Profit needs a model *decorrelated* from bookmaker odds, not only an accurate one. The authors report positive profit on NBA 2007–14.
- **Grade:** M.
- **Implication:** This is consistent with our finding that "model ≈ calibrated, loses the margin". Accuracy that mirrors the price earns nothing.

### 2.2 Favourite-longshot bias (FLB)

**Ottaviani & Sørensen (2008)**, "The Favorite-Longshot Bias: An Overview of the Main Explanations", *Handbook of Sports and Lottery Markets*. Link: https://www.kellogg.northwestern.edu/academics-research/research/detail/2008/the-favorite-longshot-bias-an-overview-of-the-main/
- **Content:** A survey of the explanations: misperception, informed insiders, risk preference, heterogeneous beliefs.
- **Grade:** S.

**Whelan (2024)**, "Risk Aversion and Favourite-Longshot Bias in a Competitive Fixed-Odds Betting Market", *Economica* (CEPR DP17518). Link: https://www.karlwhelan.com/Papers/EconomicaFinal.pdf
- **Finding:** Favourite-longshot bias arises even when bettors are right on average and books compete, because risk-averse books worsen longshot odds.
- **Grade:** M–S.
- **Implication:** Short prices lose the least per unit staked. This is consistent with our profit map. Longshot legs carry the most hidden margin.

**Forrest & Simmons (2008)**, "Sentiment in the betting market on Spanish football", *Applied Economics* 40(1), 119–126. Link: https://ideas.repec.org/a/taf/applec/v40y2008i1p119-126.html
- **Finding:** Fans of more popular clubs get *better* terms, which the authors read as bookmaker competition for sentiment money. Similar results in Scotland.
- **Grade:** M–S.
- **Implication:** Big-club sides can be priced generously, so the bias does not always favour fading popular teams.

**NHL** (Woodland & Woodland) shows a *reverse* favourite-longshot bias in the moneyline (https://commons.emich.edu/accfin_facsch/91, abstract not read). **CS2** shows mixed direction (section 1.10). Direction is market-specific.

### 2.3 Sides versus totals, props and niche markets

**Totals:**
- Paul & Weinbach (2002) NFL totals: efficient overall, with high totals set too high. https://ideas.repec.org/a/sae/jospec/v3y2002i3p256-263.html (M).
- Kelly & Chen: that edge disappears in 2010–18 (secondary only, not verified).
- Baryla et al. (2007), NBA, *Finance Research Letters*: totals are biased early in the season, sides are not; markets move in the right direction but do not fully remove the bias (56.72% against the closing total). https://dc.etsu.edu/etsu-works/17780 (M).
- **Synthesis:** No study was found establishing that totals are *generally* less efficient than sides. Inefficiencies are local (early season, extreme totals) and fade.

**Player props and derivatives:**
- No academic study of prop-market efficiency was found. **Gap.**
- Miller & Davidow, *The Logic of Sports Betting* (2019, practitioner book), recommend less-picked-over derivative and prop markets because main lines are a consensus of serious bettors. Excerpt: https://www.legalsportsreport.com/33079/the-logic-of-sports-betting-market-agreement-and-resistance/ (W, practitioner).
- **Implication:** Props are where public information (lineups, roles, minutes) is *least* processed, so it is also where a missed absence costs most. That cuts both ways: easier edges for sharp bettors, but larger margins for the book. Our own measurement says player props were never +EV at Superbet.

### 2.4 Timing: opening against closing, late information, CLV

**Simon (2024)**, "Inefficient Forecasts at the Sportsbook: An Analysis of Real-Time Betting Line Movement", *Management Science* 70(12), 8583–8611. Link: https://ideas.repec.org/a/inm/ormnsc/v70y2024i12p8583-8611.html (abstract via secondary)
- **Finding:** 3,681 MLB games at four books.
- Forecasts are mostly reliable, but simple strategies were significantly profitable.
- Accuracy does *not* rise monotonically toward first pitch; weekend day games were less accurate near the start than 90 minutes before.
- Lines overshoot and partly reverse.
- **Grade:** M–S (top journal, single sport).

**Gandar, Dare, Zuber, Pavlik (2005)**, *Applied Financial Economics* 15(3), college football line movement. Link: https://ideas.repec.org/a/taf/apfiec/v15y2005i3p143-152.html
- **Finding:** Bettors move lines on public signals (polls, indices, lagged performance) that do not predict outcomes against the spread. That is noise trading.
- **Grade:** M.

**Krieger et al.** (see 1.5): an opening-line edge largely disappears by the close.

**Closing line value (CLV) as a yardstick:** No peer-reviewed test of "CLV predicts long-run profit" was found. It is standard practitioner doctrine (Buchdahl, *Squares and Sharps, Suckers and Sharks*, 2016; existence verified, content not verified: https://slugbooks.com/9780857304841-squares-and-sharps-suckers-and-sharks-the.html).
- Data Golf applies Buchdahl's calibration test and finds Pinnacle's and DraftKings' closing odds well calibrated, with the caveat that calibration alone is weak evidence of quality: https://datagolf.com/analyzing-betting-odds (W–M).
- A large-sample claim that the mean closing odds across books is a "precise estimate" of the true probability appears in secondary coverage only (not verified).

**Lineup timing (about 1 h before kick-off):** Only industry blogs were found. Their claims:
- The most volatile movement comes in the last hour before kick-off.
- Feeds lag social-media lineup news by minutes.
- Basketball reprices faster than football.

All of this is **W**; no academic event study was found. **Gap.**

**Implications for timing:**
1. News that arrives early is priced at close.
2. The price at *our* print time may predate the lineup. A leg printed hours before lineups is exposed to news that the close will absorb.
3. When the official lineup contradicts a model assumption and Superbet's price has not moved, that is the strongest case for removal.

### 2.5 Social media and single-source news

**Brown, Rambaccussing, Reade, Rossi (2018)**, "Forecasting with social media: evidence from tweets on soccer matches", *Economic Inquiry* 56(3), 1748–1763. Link: https://ueaeprints.uea.ac.uk/id/eprint/64244/
- **Finding:** About 13.8 million tweets on 372 EPL matches. Aggregate tweet tone carried information not yet in Betfair prices, mostly in the seconds after goals and red cards. Certain journalists' tweets carried similar information.
- **Grade:** M–S.
- **Implication:** Specific reliable sources (beat journalists) *lead* the price briefly. Diffuse "opinion" does not. Weight a named beat reporter's lineup or injury report heavily; weight forum or tipster opinion near zero.

---

## 3. Methods for a human or LLM analyst

### 3.1 Experts, tipsters and crowds

**Forrest & Simmons (2000)**, "Forecasting sport: the behaviour and performance of football tipsters", *International Journal of Forecasting* 16(3), 317–331. Secondary: https://mpra.ub.uni-muenchen.de/69687/1/MPRA_paper_69687.pdf
- **Finding:** Newspaper tipsters' forecasts are dispersed, ignore public information and do worse than "always home".
- **Grade:** S.

**Spann & Skiera (2009)**, "Sports forecasting: a comparison of the forecast accuracy of prediction markets, betting odds and tipsters", *Journal of Forecasting* 28(1), 55–72. Link: https://ideas.repec.org/a/jof/jforec/v28y2009i1p55-72.html
- **Finding:** Bundesliga. Odds and prediction markets clearly beat tipsters. A rule-based combination improves accuracy (53.7% to 56.5% correct winners), but no systematic profit at a 25% fee; the authors estimate profit would need a fee near 12% or lower.
- **Grade:** S.

**Andersson, Edman, Ekman (2005)**, "Predicting the World Cup 2002 in soccer: performance and confidence of experts and non-experts", *International Journal of Forecasting* 21(3), 565–576. Link: https://ideas.repec.org/a/eee/intfor/v21y2005i3p565-576.html
- **Finding:** Experts were no more accurate than non-experts, and a world-ranking rule beat most participants. Experts were overconfident. Giving information to non-experts raised their confidence, not their accuracy.
- **Grade:** S. A 2006 follow-up found knowledgeable participants better on scores and possession, but still more overconfident.

**Tsai, Klayman, Hastie (2008)**, "Effects of amount of information on judgment accuracy and confidence", *Organizational Behavior and Human Decision Processes* 107(2), 97–105. Link: https://ideas.repec.org/a/eee/jobhdp/v107y2008i2p97-105.html
- **Finding:** Includes a college-football study. More cues raised confidence more than accuracy (baseline about 63% correct at about 68% confidence; the gap widened with more information).
- **Grade:** S.
- **Implication for LLM analysts:** A long web context pass inflates conviction. Require a decision rule fixed *before* the search (this matches our "decide before searching" lesson).

**Brown & Reade (2019)**, "The wisdom of amateur crowds: Evidence from an online community of sports tipsters", *European Journal of Operational Research*. Link: https://ueaeprints.uea.ac.uk/id/eprint/67529/
- **Finding:** Oddsportal. Majority-crowd picks returned about +1.3% over 68,339 events. Selecting tipsters by experience or past accuracy did *not* improve returns.
- **Grade:** M–S.

**Gruettner, Wambsganss, Back (2021)**, *European Journal of International Management*, Blogabet, 1.5 million tips. Link: https://www.alexandria.unisg.ch/260293/
- **Finding:** Average yield about 3.97% was reported. Survivorship handling was not verified.
- **Grade:** W–M.

**Nigerian tipster influencers (2026)**, arXiv:2604.08251. Link: https://arxiv.org/pdf/2604.08251
- **Finding:** Three tipsters, 5,467 slips. Promoted bets lost 25.2% of stakes; a follower would lose 38.3%.
- **Grade:** W (preprint).
- **Implication:** Outside tips carry no usable signal for an individual leg. They must never be a reason to remove (or keep) a leg.

### 3.2 LLMs as forecasters

**Schoenegger et al. (2024)**, "Wisdom of the silicon crowd: LLM ensemble prediction capabilities rival human crowd accuracy", *Science Advances*. Link: https://arxiv.org/html/2402.19379v6
- **Finding:** An ensemble of 12 LLMs matched a human crowd on 31 questions, but showed acquiescence: forecasts sat above 50% although resolutions were about 50/50. Showing models the human median improved them 17–28%, but less than simply averaging.
- **Grade:** M–S.

**Schoenegger et al. (2024)**, "AI-augmented predictions: LLM assistants improve human forecasting accuracy", arXiv:2402.07862. Link: https://arxiv.org/pdf/2402.07862
- **Finding:** LLM assistance improved human accuracy by about 23%.
- **Grade:** M.

**Ding, Guo, Xu (2026)**, "FIFA World Cup 2026 as a Contamination-Free Benchmark for LLM Forecasting Agents", arXiv:2607.17765. Link: https://arxiv.org/abs/2607.17765
- **Finding:** Four frontier LLMs on 104 matches:
  - None beat the market's Brier score.
  - A flat bet on the market favourite out-earned all four combined.
  - **Betting against the market lost money for every model.**
  - ROI ranged from −18% to +10%.
- **Grade:** W–M (preprint, single tournament).

**LLM-SoccerArena (2026)**, arXiv:2607.24573. Link: https://arxiv.org/pdf/2607.24573 (secondary)
- **Finding:** The best LLM was about level with closing odds (Brier skill +0.3%, not significant).
- **Grade:** W.
- **Implication:** This directly supports our rule that an LLM analyst never promotes a leg and never "prices" a match against the market. Its value lies in *finding facts the model did not see*, not in forecasting.

### 3.3 Debiasing tools

**Kahneman & Lovallo (1993)**, "Timid choices and bold forecasts: a cognitive perspective on risk taking", *Management Science* 39(1), 17–31. Link: https://ideas.repec.org/a/inm/ormnsc/v39y1993i1p17-31.html
- **Content:** The inside view (scenario, story) produces optimistic forecasts. The outside view (reference-class base rates) corrects it.
- **Grade:** S (foundational).
- **Implication:** Every veto argument should state the base rate of the leg family, which is the model's own confidence, and what *specifically* moves it.

**Klein (2007)**, "Performing a project premortem", *Harvard Business Review* 85(9), 18–19. It relies on Mitchell, Russo & Pennington (1989) on prospective hindsight. Link: https://corporate.jasoncollins.blog/premortem
- **Finding:** Imagining that the outcome has already happened yields about 30% *more reasons*. The quality of those reasons was not shown, and Klein's "correctly identify" wording overstates it. Veinott et al. (2010) found a premortem reduced overconfidence more than pros/cons lists.
- **Grade:** M (the mechanism is solid; the 30% figure is often misquoted).
- **Implication:** A premortem ("this leg lost — why?") is useful for *generating* candidate failure facts. Each one must then be verified as a fact, not accepted as a story.

**Mellers, Tetlock et al. (2014)**, "Psychological strategies for winning a geopolitical forecasting tournament", *Psychological Science*. Link: https://www.psychologicalscience.org/journals/psychological-science/0956797614524255/
- **Finding:** Training in probabilistic reasoning (reference classes, averaging, debiasing), teaming and tracking improved calibration and resolution.
- **Grade:** S–M. A later IRT reanalysis in *Psychological Science* disputes the size of the training and teaming effects.

**Camerer (1989)**, "Does the basketball market believe in the 'hot hand'?", *American Economic Review* 79(5), 1257–1261. Link: https://resolver.caltech.edu/CaltechAUTHORS:20110211-141748791
- **Finding:** Tests whether bettors over-bet teams on streaks. The full results were not verified, and the balanced-book assumption is criticised by later work.
- **Grade:** M.
- **Implication:** "Form" and streak narratives are the classic over-weighted public signal; the market may already over-react to them.

---

## 4. Summary of solid against weak findings

| claim | grade | direction for a remove-only analyst |
|---|---|---|
| Closing or consensus odds are the best public forecast | S | Never veto because "the price is wrong" |
| Prices absorb clean public news fast (goals, lineups) | S | Value is in checking the *model* saw the news, not in beating the price |
| Tipsters and experts do not beat odds; more info means more confidence, not more accuracy | S | Ignore tips; fix the decision rule before searching |
| Favourite-longshot bias (football, tennis), strongest in low-tier tennis | S | Longshot and low-tier legs are where the price knows more |
| Home advantage real, declining, crowd-linked for cards | S | Do not veto on "strong at home" |
| Referee home bias in cards and stoppage time | S | Already in the model; veto only on a referee *change* |
| New-manager bounce is mostly regression to the mean; odds may under-price the first 1–4 games | S / M | WATCH legs *against* a team in its first games under a new coach |
| Unfamiliar shocks are mispriced for weeks (ghost games) | M | Novel situations are where the model *and* the market are both blind; prefer removal |
| Motivation and clinched-team effects exist but close at the closing line | M | Act through lineups, not stories |
| Back-to-back and eastward travel (NBA, MLB) | M | Real, partly priced; WATCH legs that need the tired side's output |
| Tennis: long previous match leads to a worse next match | W–M | WATCH legs needing the tired player's output |
| CS2: online-to-LAN pressure shift | M | WATCH close-game legs built on online samples |
| Derby effect on goals or results | M (null) | Not a veto reason for goals or results |
| Weather effects in soccer | gap | Only extreme weather; mostly priced |
| Lineup-release timing effects | W | Practitioner-consistent; the strongest practical removal case |
| Prop-market efficiency | gap | Unknown; missed absences cost most here |
| LLMs beating the market | W–M (no) | LLMs must not price; only find facts |

## 5. Not found or not verified (do not cite as evidence)

- NHL goalie-confirmation event study.
- NBA load-management effect on team win probability (peer-reviewed).
- Football lineup-announcement event study.
- Soccer weather against goals or corners markets.
- Player-prop efficiency.
- Volleyball anything.
- CS2 stand-ins and map pool.
- Football dead-rubber betting study (peer-reviewed).
- CLV-predicts-profit test (peer-reviewed).
- The "Pinnacle close is the most efficient" claim attributed to the *Journal of Sports Sciences* (not verified).
- Full texts of every paper above. Effect sizes come from abstracts or secondary summaries.

---

## Implications for analyst skills (prioritised rules)

1. **Never argue with the price.** The consensus and closing price is the best public forecast (Forrest et al. 2005; Štrumbelj 2014; Kaunitz et al. 2017). LLMs betting against the market lost in every 2026 benchmark. "The book has it wrong" is never a veto reason, and never a reason to keep a leg.
2. **The analyst's only edge is facts the model did not see.** A veto must name a concrete, verifiable fact that post-dates or escapes the model's sample: an absence, a goalie change, a stand-in, a venue change, a referee change, or a format change. A story without such a fact is a non-veto.
3. **Confirmed lineup beats everything.** When an official XI, starting goalie or roster contradicts the leg's subject (prop player not starting, backup goalie, CS2 stand-in), remove the leg or WATCH it. When the lineup is not yet out and the leg depends on one specific player starting, WATCH, unless a named reliable source confirms him.
4. **Weight sources, not volume.** One named beat journalist or the official club or league account outweighs any number of aggregator, forum or tipster posts (Brown et al. 2018). An unnamed or single-aggregator rumour carries at most a WATCH, and only on legs that depend on that player.
5. **Fix the decision rule before the web pass.** Write down which fact would flip the leg *before* searching. More information raises confidence faster than accuracy (Tsai et al. 2008; Andersson et al. 2005).
6. **Start from the base rate.** State the leg's printed confidence as the outside view, then ask what specific fact moves it and by roughly how much. No fact means no move (Kahneman & Lovallo 1993).
7. **Premortem, then verify.** Ask "this leg lost; list the three likeliest reasons", then check each one as a fact. Discard reasons that are only narrative (Klein 2007; the 30% figure counts reasons generated, not correct ones).
8. **Ignore tipsters, previews and "expert picks".** They do not beat odds, and selecting "good" tipsters does not help (Forrest & Simmons 2000; Spann & Skiera 2009; Brown & Reade 2019). They are never a veto basis.
9. **Do not double-count what the model already carries.** Home advantage, the referee's card rate, league level, form and closeness are already in the sheet. Veto on them only if the *input changed* (a new referee, a neutral venue, closed stands).
10. **Novel shocks favour removal.** When the situation is unfamiliar to both model and market (first games behind closed doors, a new format, a team's first LAN, a debut coach, an unprecedented schedule), prefer WATCH. Markets misprice such shocks for weeks (Deutscher et al. 2021; Meier et al. 2021).
11. **New coach, first 1–4 matches: WATCH legs against that team.** The literature suggests the market under-prices the post-change team. Do not veto *for* the team on a "bounce" narrative; regression to the mean explains most of it (Bruinshoofd & ter Weel 2003; Bernardo et al. 2019).
12. **Motivation acts through lineups.** A dead rubber or clinched place is a WATCH only when it makes rotation likely and the leg depends on starters or on a high-effort count. Motivation alone, with full XIs, is not a veto; the effect is priced by close (Krieger et al.).
13. **Derby is not a veto for goals or results** (Bäker et al. 2012 null). For cards and fouls, a derby is at most a context note unless measured.
14. **Fatigue and travel: a WATCH reason only for legs that need the tired side to produce.** Examples: a tennis player after a match of over 3.5–4 hours the previous day; an NBA second night of a back-to-back after eastward travel; a long eastward NHL or NBA trip. Never on a total that fatigue could push either way.
15. **Low-tier tennis and model–price disagreement means the price likely knows more.** The favourite-longshot bias and insider information are strongest in matches between low-ranked players (Lahvička 2014). If our confidence there is far above 1/odds, treat the gap as a warning, not as value (consistent with our measured anti-signal).
16. **Longshot legs carry the most hidden margin** (Whelan 2024). Do not soften scrutiny on a high-priced leg because "the value is big".
17. **Extreme conditions only.** Weather, altitude or pitch is a WATCH reason only when extreme and verifiable: a waterlogged pitch, gale wind, snow, or an altitude gap above about 2,000 m (McSharry 2007), and only on legs those conditions directly affect (totals, counts, the away side's output). Ordinary rain or heat is priced.
18. **CS2 LAN versus online:** if the sample is mostly online and the event is a LAN with a crowd, WATCH close-game legs (overtime, round totals, narrow handicaps). Add a stand-in or a roster change since the sample to the same rule.
19. **Props: the absence check is mandatory.** Props are least processed by the market and most exposed to role changes, for example a starter moved to the bench or a positional change. Verify the player's expected role before passing a prop leg.
20. **Timing awareness.** Note how many hours before the start the leg was priced. Legs printed long before lineups carry unpriced lineup risk. If decisive news (an XI, a goalie) is due before kick-off and the leg depends on it, prefer WATCH over a clean pass.
21. **One domain or one opinion means at most WATCH.** Only a confirmed fact that removes the leg's premise justifies NO_BET (the existing contract, consistent with the evidence on single-source news).
22. **Never use the result of a previous similar leg** ("it won last time", streaks, hot hand) as an argument (Camerer 1989; Gandar et al. 2005: public-signal line moves are noise).
23. **Grade yourself by tag.** Keep measuring each veto tag (MOTIVATION, ROTATION, ABSENCES, DERBY, SCHEDULE, CONDITIONS, MORALE) against the *price-band-matched* result of the removed legs. The literature predicts ABSENCES/ROTATION ≥ SCHEDULE > CONDITIONS > MOTIVATION ≈ MORALE ≈ DERBY ≈ 0. A tag that stays at zero should be demoted to "note only".
