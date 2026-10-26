# Pre-match context pass: football and tennis checklist and sources

Checked 2026-10-26. Every source was fetched with `curl` (desktop Chrome UA) and/or WebFetch.
The analyst's web pass can only remove a bet, so each item says which variable it moves and
how good the evidence is.

**Access legend**
- **OK**: static HTML holds the content.
- **JS**: shell loads, data needs JavaScript (fetchers see little).
- **CF**: Cloudflare/Incapsula challenge (403 or "Just a moment").
- **PAY**: 402/paywall.
- **DEAD**: content gone.
- **UNV**: not verified here (known from memory or a secondary source only).

**Evidence legend**
- **E+**: peer-reviewed or large-sample analysis found.
- **E~**: mixed or small-sample evidence.
- **F**: folklore or plausible mechanism, no evidence found in this pass.

---

## 1. Source reachability (verified 2026-10-26)

### Football: lineups, injuries, team news
| domain | status | what is there | notes |
|---|---|---|---|
| sofascore.com | CF (403 to curl/WebFetch) | predicted / confirmed XI, missing players | Pipeline already reads it via the bridge (`lineups_prematch.json`), so don't web-fetch it. |
| fotmob.com | JS (200, data JS-loaded) | predicted XI, injuries, ratings | WebFetch sees no fixtures. |
| flashscore.com | partly OK | fixtures with dates static; scores / lineups JS | Wide lower-league coverage. |
| rotowire.com/soccer/lineups.php | OK | confirmed XIs, injury tags OUT/QUES/SUS | Only EPL rendered statically. The filter also lists UCL, L1, LaLiga, SA, BL, MLS and Liga MX. |
| sportsgambler.com/lineups/football/ | OK | predicted XI per fixture | Approx. 60 competitions incl. Argentina, Brazil, Turkey, Eliteserien, Allsvenskan, Superliga, J1, K1, CSL and Russia. **No Poland.** |
| sportsgambler.com/injuries/football/<league>/ | OK | injuries & suspensions per club | |
| sportsmole.co.uk/football/preview/ | OK | "prediction, team news, lineups" previews | Covers LaLiga, L1, Primeira, Süper Lig and English leagues. English. |
| transfermarkt.com/.../verletztespieler/wettbewerb/<ID> | OK (curl) / blocked to WebFetch | injured players, return date | Per league. |
| transfermarkt.com/.../sperrenausfaelle/wettbewerb/<ID> | OK (curl) | "Yellow card suspension", "Risk of suspension" | Verified on PL1 (Ekstraklasa). |
| transfermarkt.pl / .co.uk | OK | same data, local language | |
| premierinjuries.com | CF | | |
| physioroom.com | DEAD | now a rehab-equipment shop, no injury table | |
| football-lineups.com, whoscored.com, fbref.com, besoccer.com, zerozero.pt / ogol.com.br / playmakerstats.com / ceroacero.es, forebet.com, 11v11.com | CF | | Unusable for an agent fetcher. |
| worldfootball.net | PAY (402) | | Was a free referee-stats source; no longer reachable. |
| footystats.org | CF (JS challenge on referee pages) | | |
| soccerway.com | OK (200) | | |
| footballcritic.com | OK (200) | | Content not checked. |
| soccerstats.com | OK | | `/referees.asp` = 404. |
| soccerbase.com | OK | | |
| bbc.com/sport/football | OK | | |
| espn.com/soccer | 202 empty | | |
| understat.com | OK | | Top-5 + RFPL only. |
| betexplorer.com, oddsportal.com | OK | | |
| promiedos.com.ar | OK | | Argentina. |
| x.com | JS | | Clubs post XIs about 60-75 min before kick-off. nitter.net answers 200 but instances are unreliable (UNV). |

### Referees
| domain | status | content |
|---|---|---|
| statshub.com/referee/<slug>/<id> | OK | Yellow / red per game and match history, e.g. "Felix Zwayer 4.63 yellow cards/game". The best free referee card-rate source found. |
| transfermarkt.com referee profile (`/profil/schiedsrichter/<id>`) | OK (curl) | Profile pages exist. Per-competition card columns not confirmed in this pass (UNV). |
| aia-figc.it/designazioni/ | OK | "Ultime designazioni arbitrali", Serie A–C. Italian. |
| rfef.es (`/es/noticias/arbitros/designaciones`) | CF | CTA designations for Primera/Segunda. Spanish. Use a press mirror (marca.com = OK). |
| dfb.de/bundesliga/schiedsrichter | OK (200) | DFB referee section. German. |
| premierleague.com/news | OK | PGMOL appointments are published as PL news, usually early in match week (UNV timing). pgmol.co.uk did not resolve. |
| lfp.fr | OK (root) | `/arbitres` = 404. Designations page path UNV. French. |
| pzpn.pl | OK (root) | Referee subpages = 404 (path changed). Ekstraklasa "obsada sędziowska" is relayed by meczyki.pl (OK) a few days before each round. Polish. |
| tff.org | OK | Turkish "hakem atamaları" published by TFF (UNV exact page). |
| cbf.com.br/a-cbf/arbitragem/escala-de-arbitragem | OK | "Escala de Arbitragem Campeonato Brasileiro Série A 2026". Portuguese. |
| afa.com.ar | OK (root) | Designaciones page path UNV. Olé (OK) relays them. |
| worldreferee.com, footballwebpages.co.uk/referees | CF | |
| kicker.de | CF | |

### Weather, venue
| domain | status | use |
|---|---|---|
| api.open-meteo.com/v1/forecast?latitude=..&longitude=..&hourly=precipitation,wind_speed_10m,temperature_2m | OK (JSON, no key) | Hourly forecast at stadium coordinates. Best for an agent. |
| yr.no | OK | Hourly. Strong for Scandinavia. |
| meteoblue.com, wunderground.com, wetteronline.de, weather.gov (US) | OK | |
| windy.com | JS | |
| timeanddate.com/weather, accuweather.com | CF / denied | |
| stadiumdb.com, footballgroundguide.com | OK | Capacity, surface (UNV per row). |
| en.wikipedia.org "List of Eliteserien venues" | OK | Surface column (artificial / natural), "up to date as of end of 2025". |

### Local press (all OK = 200)
| country | domains |
|---|---|
| Poland | sport.pl, przegladsportowy.pl, weszlo.com, meczyki.pl |
| Poland, lower leagues and referees | 90minut.pl (http only), laczynaspilka.pl |
| Spain / Italy | marca.com, gazzetta.it |
| Turkey | fanatik.com.tr, mackolik.com |
| Brazil | ge.globo.com |
| Argentina | ole.com.ar |
| France, Germany | lequipe.fr and kicker.de are CF |

### Tennis
| domain | status | content |
|---|---|---|
| tennisexplorer.com | OK | Today's matches; player page with matches by tournament, record by surface and **injury / retirement table**. Tournament page shows surface + "Indoors". Covers ATP / WTA / Challenger / ITF. The best single agent source. |
| tennisabstract.com | OK | Player pages (`cgi-bin/player.cgi?p=`); **ATP surface-speed ratings** (`reports/atp_surface_speed.html`, `cgi-bin/surface-speed.cgi?year=2026`): ace-rate-based, tour level only, **no Challengers**. WTA report URL = 404 (UNV elsewhere). Blog = evidence. |
| wtatennis.com | OK | Tournaments, players, scores. Order-of-play page content is JS (court / time not in static HTML). Old OOP PDFs at wtafiles.wtatennis.com/pdf/draws/<yr>/<id>/OP.pdf (UNV for 2026). |
| atptour.com | CF to curl | WebFetch gets an unrendered template ("{{tournament...}}"); news articles readable via WebFetch. |
| protennislive.com | 503 / no DNS | ATP / Challenger OOP PDFs historically here (UNV). Tournament sites post OOP PDFs themselves. |
| itftennis.com | JS (empty shell to curl / WebFetch) | Calendar, draws, OOP exist but are unreadable to fetchers. |
| live-tennis.eu | CF | Live ranking and points dropping. Unreachable to fetchers. |
| matchstat.com, tennistemple.com, tennistonic.com, tennisworldusa.org | CF | |
| flashscore.com/tennis, tennis24.com | OK / partly JS | Fixtures incl. ITF. |
| tennislive.net, tennisstats.com, tennisprediction.com, coretennis.net, ultimatetennisstatistics.com, tennis.com, tennis-x.com, heavytopspin.com | OK (200) | Content depth not checked (UNV). |

---

## 2. Football checklist

Market abbreviations: G = goals, C = corners, Cards / card points, F = fouls, S = shots,
SOT = shots on target, Off = offsides, H = halves, TT = team totals, P-props = player props.

### 2a. Availability
| # | item | market / direction | evidence | best sources | timing |
|---|---|---|---|---|---|
| 1 | **Confirmed XI** | P-props: void if he does not start (Superbet), so the risk is a role or position change, not a non-start. Team counts: rotated XI → weaker side's S / C down. | Mechanical for props. Pipeline memo: real XI gave no gain on team counts (10-23). | Sofascore (bridge); club X / app; rotowire (EPL); flashscore | EPL publishes from 75' before KO (handbook rule since 2024/25). EFL embargo 60' (secondary source, UNV). UEFA sheets ~75' (UNV). Lower leagues: often only at KO. |
| 2 | **Predicted XI** | Same as 1, lower certainty | n/a | sportsgambler (≈60 comps, no PL), sportsmole previews, FotMob (JS), Sofascore predicted | 1-3 days ahead |
| 3 | **Injuries / long absences** | Key striker out → team G / S / SOT down. Key CB / GK out → opp G up. Prop player doubtful → skip prop. | E~ (rating models absorb part) | transfermarkt verletztespieler, sportsgambler injuries, rotowire (EPL tags), local press | Daily. TM updates within ~1 day (UNV). |
| 4 | **Suspensions / accumulation** | Player on 4 yellows ("diffidato", "na kartkach") may play cautiously (cards ↓, F ↓). Folklore. Some players take a "tactical" 5th yellow before an unimportant game. | F (no study found) | TM sperrenausfaelle ("Risk of suspension"), league disciplinary releases | After each round |

### 2b. Referee
| # | item | market / direction | evidence | best sources | timing |
|---|---|---|---|---|---|
| 5 | **Referee appointment** | Cards, card points, F, penalties, reds. Strongest non-numeric card driver. | E+: referees differ significantly in card rates, stable over time (Dawson et al. 2007). Match state drives cards (Buraimo et al. 2010). | §3 per country | 2-5 days before (country-specific) |
| 6 | **Referee card rate** | Cards ↑ / ↓ vs league mean (league mean ≈4.4 Y + 0.25 R across 87 leagues, CIES 2015-20, via search) | E+ (between-referee variance real) | statshub.com (OK), TM referee profile (UNV columns). worldfootball (PAY), footystats (CF). | Season to date |
| 7 | **VAR in competition or not** | VAR introduced → F ↓, Off ↓, Y ↓, stoppage time ↑. Serie A + BL (1,024 matches; Lago-Peñas). Süper Lig: F / Y / Off ↓, penalties ↑. CSL: Off / F ↓, Y unchanged. Goals: mixed (meta-analysis). | E~ / E+ (pre-post designs) | League regulations; Wikipedia season page | Static per season |

### 2c. Conditions
| # | item | market / direction | evidence | best sources | timing |
|---|---|---|---|---|---|
| 8 | **Weather: heat** | High temperature → fewer passes / short passes. UCL: fewer counter-attack shots as temperature rises (OR 0.55). | E+ (PMC11474995; 4-league temperature / WBGT study; BL PLOS ONE 2021) | open-meteo hourly, yr.no, meteoblue | Forecast to KO hour, 0-48h |
| 9 | **Weather: rain / wind** | Plausibly fewer completed passes; direction on G / S unproven. "Wet EPL games 0.3 fewer goals" = unsourced blog. | F / E~ (no soccer study isolating rain vs goals found) | open-meteo (precipitation, wind_speed_10m, gusts) | 0-24h |
| 10 | **Snow / frozen pitch / postponement** | Postponement → refund (SETTLE rules). Snow → G ↓ (F). | F | local press, club X | Day of match |
| 11 | **Artificial turf** | Home advantage ↑ (Norway ~+2.5 pts / season, Hvattum. JQAS 2015: switchers improved. Eredivisie study). Sweden: no practical effect on goals. | E~ (mixed) | Wikipedia "List of Eliteserien venues" (surface column), stadiumdb, club sites | Static. **Eredivisie banned artificial turf from 2025-26** (eredivisie.com). Turf still at Bodø/Glimt, Molde, Tromsø etc. (end-2025 list). Russia / Switzerland / Scotland: UNV per club. |
| 12 | **Altitude** | Home G-diff ↑ ≈0.5 goal per 1,000 m difference (McSharry BMJ 2007, 1,460 internationals). Libertadores: home G ↑ when visitor ascends. Critique: confounded with team quality. | E~ / E+ | Venue altitude: Wikipedia / stadiumdb | Static (La Paz, Quito, Bogotá, Cusco, Toluca, Mexico City) |
| 13 | **Travel distance / time zones** | Away performance ↓ (F for markets) | F (not checked) | Map. Copa Libertadores / Russia / Brazil long trips. | Static |

### 2d. Schedule and stakes
| # | item | market / direction | evidence | best sources | timing |
|---|---|---|---|---|---|
| 14 | **Fixture congestion / midweek Europe** | Rotation ↑ (fewer players 75-90'). Result effect mixed: Spanish UCL study no effect. Buchheit 20-yr study "may not" hurt. Verheijen 40% fewer wins after 2 days (UNV original). | E~ | Club fixture list (flashscore, TM) | Days-since-last-match is computable from Sofascore. Pipeline flags `CONGESTED`. |
| 15 | **Cup prioritisation / weakened XI in cup** | Big rotation → favourite's TT / S ↓ | F (mechanism via XI) | Predicted XI, coach press conference (local press) | 1-2 days |
| 16 | **New manager** | Bounce = regression to the mean (van Ours / Tinbergen. EUR study. Besters et al.) | E+ (no causal effect) | Local press, TM coach page | — so not a reason to remove a leg |
| 17 | **Dressing room, wages unpaid, crisis (MORALE)** | Collapse risk → G against ↑ (F). Lower leagues: unpaid wages, walk-outs, forfeits (refund risk). | F | Local press only (weszlo, sport.pl, fanatik, ge.globo, ole) | Days |
| 18 | **Derby** | F ↑ (EPL derbies 25.95 vs 22.38 fouls / match, n=50, blog). Derby effect on yellows (Kruse & Maennig WP). Not uniform: Derby d'Italia below SA mean. | E~ | Rivalry known; local press | Static |
| 19 | **Title / relegation / European stakes** | Pipeline flags STAKES_* = display only | E~ (not measured here) | Standings (flashscore, Sofascore) | Last ~8 rounds |
| 20 | **Dead rubber / end of season** | Effort ↓ → G variance ↑, cards ↓ (F) | F (no study found in this pass) | Standings | Last 3-4 rounds |
| 21 | **2nd leg / aggregate** | Team ahead protects → its S ↓, opp S / C ↑. Late-game chase → cards ↑. | F (mechanism; game-state card effect E+ per Buraimo) | Aggregate score on flashscore / UEFA | Static |
| 22 | **Empty stadium / fan ban / away-fan ban** | Away yellows ↑ relative to closed doors (crowd → referee favours home: about +⅓ away yellow / match with fans, Reade et al. 2022. Bryson 23 leagues: away yellows ↓ without fans, score unchanged). | E+ for cards, E~ for goals | Federation / UEFA disciplinary releases. PL: "zakaz wyjazdowy" in local press. | Days |

### 2e. Coach and team style
| # | item | market / direction | evidence | best sources | timing |
|---|---|---|---|---|---|
| 23 | **Coach style: pressing, set pieces, corners, offside line** | C / F / Off tendencies | Better taken from stats (already in samples) than from web text | Sofascore stats | — |
| 24 | **Pitch dimensions / poor pitch** | Small pitch → C / F? | F | Local press | — |
| 25 | **Women / youth / reserve** | Line-ups rarely published. Reserve sides change with first-team needs. | F | Club sites, laczynaspilka.pl / 90minut.pl (PL lower), federation sites | Often none before KO |

**Card accumulation thresholds (one-match ban)**
| competition | rule | status |
|---|---|---|
| Premier League | 5 Y within club's first 19 games (1), 10 within 32 (2), 15 (3), 20 → commission. Cups separate. | Verified: FA discipline site + legionreport 2026-07 |
| EFL | 5 in first 19 | Verified (secondary) |
| Ligue 1 (2025-26) | 5 Y, any number of matches. Previously 3 in 10. | Verified: ligue1.com |
| LaLiga | 5 Y (1), 10 (2) | Secondary sources |
| Serie A | 5 Y | Secondary sources; one older source says 4, treat as outdated |
| Bundesliga | 5 Y | Secondary sources (bundesliga.com FAQ relates) |
| UEFA club comps | 3rd, 5th, 7th… Y. Reset after QF. | Secondary source |
| MLS | 5 Y | Secondary source |
| Ekstraklasa, Süper Lig, Brasileirão, Argentina, Scandinavia | — | **UNV**: not found. Check PZPN / TFF / CBF disciplinary regulations. Polish association cups: 2 Y = 1 match (kpzpn 2023/24). |

---

## 3. Referee appointments by country

| country | official source | status | relay / press | when published |
|---|---|---|---|---|
| England | premierleague.com news (PGMOL) | OK | BBC | Early in match week (UNV) |
| Spain | rfef.es Designaciones (CTA) | CF | marca.com (OK) | Few days before (UNV) |
| Germany | dfb.de/bundesliga/schiedsrichter | OK | kicker (CF) | UNV |
| Italy | aia-figc.it/designazioni/ | OK | gazzetta.it | ~2 days before (UNV) |
| France | lfp.fr | OK root, page UNV | lequipe (CF) | UNV |
| Poland | pzpn.pl (subpage moved) | 404 | meczyki.pl (OK) | "obsada sędziowska" per kolejka, a few days ahead |
| Turkey | tff.org | OK, page UNV | fanatik, mackolik | UNV |
| Brazil | cbf.com.br/a-cbf/arbitragem/escala-de-arbitragem | OK (2026 Série A page) | ge.globo | UNV |
| Argentina | afa.com.ar | OK root, page UNV | ole.com.ar | UNV |

The pipeline already reads the referee from Sofascore `/event` about 48h before kick-off (CLAUDE.md). The web
pass adds value only where Sofascore has no referee, or to check a late change.

---

## 4. Tennis checklist

### 4a. Schedule, surface, conditions
| # | item | market / direction | evidence | best sources | timing |
|---|---|---|---|---|---|
| 1 | **Order of play / court / start time / "not before"** | Late finish → next-day fatigue. Night session indoors / outdoors conditions. | n/a (fact) | Tournament site OOP PDF. WTA site (JS). ATP site (CF). itftennis (JS). tennisexplorer / flashscore times. | Evening before |
| 2 | **Surface and speed** | Aces ↑, holds ↑ → games totals ↑, tie-breaks ↑, handicaps narrower on fast courts | E+ (ace-based speed ratings; tour-level only) | tennisabstract surface-speed (ATP only, no Challengers); tennisexplorer surface / indoors | Season |
| 3 | **Indoor vs outdoor** | Indoor: more unreturned serves (+~3 pp for Auger-Aliassime, small sample) → aces ↑, games ↑ | E~ (one-player analysis; no tour-wide study found) | tennisexplorer tournament page ("Indoors") | Static |
| 4 | **Altitude** (Bogotá, Quito, Gstaad, Kitzbühel, São Paulo, Madrid ~650 m) | Aces ↑, serve points won ↑ (122 ATP 250 matches, UCAM study). Gstaad / São Paulo fastest clay (ace-based). | E+ / E~ | Venue altitude | Static |
| 5 | **Balls** | Heavier / fluffier balls slow play → aces ↓ | F (player complaints; not measured here) | Tournament site, news | UNV |
| 6 | **Weather: wind** | Plausibly first-serve % ↓, aces ↓, breaks ↑ → games? Unmeasured. | F (no quantification found) | open-meteo at venue | Hours |
| 7 | **Weather: heat** | Retirement risk ↑, long matches. **ATP heat rule from 2026**: WBGT ≥30.1°C → 10-min break after set 2 (Bo3). >32.2°C suspension. WTA rule since 1992 (thresholds UNV). | Rule = fact. Effect on markets F. | atptour.com news (readable via WebFetch), open-meteo | Hours |
| 8 | **Rain delay / suspension, moved indoors** | Changes conditions mid-match | F | Live sites | Live |

### 4b. Player condition
| # | item | market / direction | evidence | best sources | timing |
|---|---|---|---|---|---|
| 9 | **Previous match duration / finish time** | Next-match win% fell 61.4% (1:00-1:29 prior) → 31.9% (≥4:30) in men's Slams, unadjusted for skill. Women's: 3-set prior wins → higher loss risk later (2006). | E~ (confounded) | tennisexplorer / flashscore match times | Previous day |
| 10 | **Travel between tournaments** | Week-1 after long-haul / surface switch → upset risk (F). Opponent travel fatigue strengthens home advantage (2025 ATP study). | E~ | Player's last event (tennisexplorer) | Days |
| 11 | **Injury, MTO, retirement history** | Retirement → void per Superbet (pipeline RETIRED refund). Partial-injury play → games ↓ / handicaps blow out. | E~ (no market study) | tennisexplorer player injury / retirement table (verified); player social, news | Days |
| 12 | **Withdrawals / lucky loser** | LL / alternate gets in late; prep unknown | F | Draw updates (tournament site, flashscore) | Hours |

### 4c. Motivation and format
| # | item | market / direction | evidence | best sources | timing |
|---|---|---|---|---|---|
| 13 | **Ranking points defending / dropping** | Motivation (F) | F | live-tennis.eu (CF); ATP / WTA rankings | Weekly |
| 14 | **Motivation at small events / appearance fee / tanking** | Favourite effort ↓ → handicap risk | F | News | Days |
| 15 | **Home player** | +2-3% wins vs ranking expectation (Koning 1991-2009). Gucciardi & Ruberti 2025: real, larger for less experienced players, persisted without crowds. Raw home win% low because of wildcards. | E+ | Nationality vs venue | Static |
| 16 | **Qualifier / match-fit** | Qualifiers have played 2-3 matches on site (acclimatised) vs fatigue | F | Draw | Static |
| 17 | **Format** | Bo5 at men's Slams (pipeline `BEST_OF_FIVE_NOT_MODELLED`). Some exhibitions / Next Gen short sets. Final-set tie-break rules: Slams 10-point at 6-6. Davis / BJK Cup and United Cup formats. Doubles match-tie-break. | Fact | Tournament rules | Static |
| 18 | **ITF data sparsity** | Little beyond scores. Pre-match context mostly unavailable. | n/a | tennisexplorer (results, injury table, surface), flashscore; itftennis.com is JS-only | — |

For ITF and low Challengers, treat the lack of context as normal, not as a reason to remove a leg. The only checks
that reliably exist are recent results and retirements, surface / indoors, and a long previous match.

---

## 5. Evidence references (found in this pass)

**Weather**
- UCL meteorology and technical performance (2024): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11474995/
- Bundesliga situational / environmental factors (2021): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7943014/
- Temperature / WBGT in 4 leagues: https://www.sponet.de/sponet/Record/4091799?lng=en

**Pitch, altitude**
- Artificial turf, Norway: https://link.springer.com/article/10.1007/s10645-019-09332-2
- Artificial turf, Norway (JQAS): https://www.degruyterbrill.com/document/doi/10.1515/jqas-2014-0046/html
- Artificial turf, Sweden: https://idrottsforum.org/ramme150615
- Eredivisie turf ban: https://eredivisie.com/news/no-more-artificial-turf-in-the-eredivisie-from-the-2025-26-season/
- Altitude, McSharry (BMJ): https://www.bmj.com/content/335/7633/1278
- Altitude, Libertadores: https://www.jhse.ua.es/article/view/2023-v18-n1-conmebol-libertadores-cup-altitude-impact-goals-resu

**Referees, crowds, VAR**
- Referee consistency (Dawson et al.): https://research-portal.uea.ac.uk/en/publications/are-football-referees-really-biased-and-inconsistent-evidence-on-/
- Referee bias, England / Germany (Buraimo et al.): https://eprints.lancs.ac.uk/id/eprint/45039
- Empty stadiums (Leeds): https://www.leeds.ac.uk/news/article/4894/how_empty_stadiums_affected_football_during_pandemic
- Empty stadiums, Eredivisie: https://papers.tinbergen.nl/24014.pdf
- VAR meta-analysis: https://repository.essex.ac.uk/38196/1/rogerson-et-al-2024-meta-analysis-of-the-effects-of-var-on-goals-scored-and-home-advantage-in-football.pdf
- VAR in Serie A / Bundesliga: https://lida.sport-iat.de/ta/Record/4063687?lng=en

**Schedule, manager, derby**
- Congestion (Kitman Labs): https://go.kitmanlabs.com/rs/633-QEV-085/images/Study_Mid_Week-European_Matches.pdf
- Congestion (Huddersfield): https://www.hud.ac.uk/news/2020/november/football-fixture-congestion-new-study/
- New manager (Tinbergen): https://papers.tinbergen.nl/25054.pdf
- New manager (EUR): https://www.eur.nl/en/news/irrational-managerial-changes-remain-norm-europes-top-football-leagues
- Derby fouls (EPL): https://harvardsportsanalysis.org/2015/01/premier-league-do-derbies-feature-more-aggression
- Derby, yellow cards (Kruse & Maennig): https://econpapers.repec.org/paper/hcewpaper/064.htm

**Tennis**
- Time on court: https://tennisabstract.com/blog/?p=2301
- Sets played in previous rounds: https://lida.sport-iat.de/ta/Record/3039576?lng=en
- Altitude (UCAM): https://repositorio.ucam.edu/handle/10952/5980
- Surface speed: https://www.tennisabstract.com/cgi-bin/surface-speed.cgi?year=2026
- Indoor serve: https://www.tennisabstract.com/blog/?p=7655
- Home advantage (Gucciardi & Ruberti 2025): https://iris.uniupo.it/handle/11579/215763
- ATP heat rule: https://www.atptour.com/en/news/new-heat-rule-effective-from-2026

**Rules**
- PL accumulated cautions: https://fadiscipline.thefa.com/support/solutions/articles/77000395983
- Ligue 1 suspensions: https://ligue1.com/en/articles/l1_article_2840-
- League thresholds summary (2026-07): https://legionreport.com/how-many-yellow-cards-before-suspension/
- EPL lineup 75-minute rule: https://liverpoolfc.com/news/explained-premier-league-changes-2024-25-season

## 6. Not verified / open
- Exact referee-designation page URLs and publication days: LFP, TFF, AFA, PZPN, DFB.
- Card thresholds for Ekstraklasa, Süper Lig, Brasileirão, Argentina, Nordic leagues.
- Current turf lists: Allsvenskan, Russia, Switzerland, Scotland.
- WTA heat-rule thresholds, WTA surface-speed source, protennislive OOP availability.
- Transfermarkt referee card columns.
- No source quantifies rain / wind on goals, corners or shots, or wind on aces. Treat those as folklore and do not
  remove a leg on weather alone, except a postponement risk or extreme heat (retirement).
