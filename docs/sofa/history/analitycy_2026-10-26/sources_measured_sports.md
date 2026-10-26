# Pre-match context checklist and sources: hockey, basketball, volleyball, CS2

Researched 2026-10-26 (web search plus fetches from this machine). Audience: sofa
analyst agents doing the web context pass. They may only **remove** a leg, so every
item below is something that can make a printed leg wrong, never something that
promotes one.

## Legend

**Source status** (what was actually checked, 2026-10-26):
- **V**: fetched, and the content was confirmed by WebFetch or curl (what the page shows is described).
- **R**: reachable only (HTTP 200 to curl with a browser UA); the content was not inspected for the item.
- **B**: blocked to automated fetch. 403 = Cloudflare / bot wall, 429 = rate limited. Usable only through WebSearch result snippets or a real browser.
- **S**: seen only as WebSearch results (the URLs exist; the pages were not fetched).
- **U**: unverified, from prior knowledge. Do not rely on it until it has been checked.

**Evidence grade** for the claimed effect:
- **E**: measured (a study or a dataset, cited).
- **E-**: weak (blog-level data or a small sample).
- **A**: arithmetic or the rules (follows mechanically).
- **F**: folklore or plausible but unmeasured. Use it only as a WATCH reason through the leg's variable.

**Direction notation**: ↓ lowers the variable (totals, a team's points, a player's
line), ↑ raises it, "var↑" means more variance (bad for low-line UNDERs and for
handicaps on the favourite).

---

## 0. Access facts that matter for an agent (measured 2026-10-26)

| site | result | consequence |
|---|---|---|
| hltv.org (matches, stats, home, rss) | **403 Cloudflare challenge** to curl and WebFetch (rss once returned 200, then a challenge) | Use WebSearch with `allowed_domains: ["hltv.org"]`: the snippets carry news, transfers and match titles. Use dust2.us / dust2.dk as the readable mirror for news |
| liquipedia.net HTML | **403** | The MediaWiki API works: `https://liquipedia.net/counterstrike/api.php?action=parse&page=<Page>&format=json&prop=wikitext` with `Accept-Encoding: gzip` and a custom UA (verified, 200). Terms: about 1 request / 2 s, **parse ≤ 1 / 30 s**, no scraping of the HTML pages, CC BY-SA attribution ([terms](https://liquipedia.net/api-terms-of-use)) |
| euroleaguebasketball.net | **429** on every path | Use basketnews.com (V, a daily EuroLeague injury report) or eurohoops.net (R) |
| khl.ru / en.khl.ru root | 403 (the root); `/news/` returned 200 but its body is JS-only | KHL game-day facts come through WebSearch or championat.com / sports.ru (R, Russian) |
| eliteprospects.com, puckpedia.com, volleybox.net, proballers.com, realgm.com/international, prosportstransactions.com, underdogfantasy.com, faceit.com | 403 | Snippets only |
| leftwinglock.com | 200, but the starting-goalie tool is **premium-only** (V) | Not a free source |
| capfriendly.com | no response (the site closed in 2024; U) | Use puckpedia (B) or team sites |
| nba.com/players/todays-lineups | 200, but the body is empty without JS (V) | Use Rotowire instead |
| nhl.com/injuries | an error page (V) | Use Rotowire or DailyFaceoff |
| bo3.gg, liiga.fi | 200, but the body is empty without JS | Not readable by WebFetch |

---

## 1. Ice hockey

### 1a. Checklist

| # | item | market variables affected and direction | evidence |
|---|---|---|---|
| H1 | **Starting goalie** (No. 1 vs backup; a call-up, an emergency or a 3rd goalie) | Backup starts: the opponent's team total ↑, the match total ↑, the favourite's handicap / winner ↓, opponent player points ↑ | E-: a back-to-back starter's sv% about .892 vs .912 rested (Leafs Nation 2020, small n); Tulsky 2013 ~11% relative drop, later work smaller (summarised by [NHL.com Kraken](https://nhl.com/kraken/news/core-concepts-examining-goalie-workload-329507592)); [Hockey-Graphs 2014](https://hockey-graphs.com/2014/12/01/goaltender-performance-vs-rest/): .905 → .897 on 1-day rest |
| H2 | **Back-to-back** (second night), especially when the same goalie plays both | The tired side's goals against ↑, its shots ↓ | E- (H1 sources); the effect is mostly through the goalie |
| H3 | **Travel direction and time zones** (westward trips; KHL trips of up to 7 time zones, Vladivostok ↔ Moscow about 9 h of flying) | The away side ↓ | E: Charest et al. 2022, 17,088 NHL games 2013-20: circadian shift and distance hurt ([Arizona](https://experts.arizona.edu/en/publications/associations-between-time-zone-changes-travel-distance-and-perfor/)); Roy & Forest 2016 abstract: westward disadvantage ([AASM](https://aasm.org/nfl-nba-and-nhl-teams-have-a-disadvantage-when-traveling-west)). KHL-specific: F |
| H4 | **Injuries / scratches** of top-6 forwards, top-4 D and the PP1 quarterback | The team total ↓; the PP-dependent player points of teammates (↓ or ↑ through redistribution) | F (direction certain, size unmeasured) |
| H5 | **Line combinations and PP units** (a player moved to PP1 or off it, to line 1 or line 4) | Player points / SOG ↑ / ↓; PP1 time is the main driver of points props | F (strong consensus; unmeasured here) |
| H6 | **Player out / healthy scratch** (a prop on a player not dressing) | Superbet's void rules apply; check the dressed roster | A |
| H7 | **AHL call-ups / assignments** (an NHL goalie sent down, an AHL team losing its starter or top scorer) | AHL team total ↓ when its best player is recalled; NHL: a call-up goalie = H1 | F; the source is team transactions |
| H8 | **Rest advantage** (3+ days vs 0) | See H2 | E- |
| H9 | **Playoff push / nothing to play for** (late season), tanking | Effort, var↑; an eliminated team may start its backup goalie (H1) | F |
| H10 | **Outdoor game** (Winter Classic / Stadium Series; European outdoor derbies) | Pace ↓ claimed; wind, ice quality; var↑ | F: only anecdotal ("usually slower", [NHL.com 2019](https://www.nhl.com/penguins/news/stadium-series-snap-shots-287134034)); no scoring data found |
| H11 | **European import / roster limits** (KHL, Liiga, DEL import counts; a goalie as one import) | Who dresses | U: the rules vary by league; not checked |
| H12 | **Coach change / goalie controversy / morale** | var↑ | F |
| H13 | **International break / Olympic or national-team windows** (European leagues pause; returning players' fatigue) | var↑ | F |
| H14 | **Empty-net propensity / score-effects** (a favourite leading late → an empty net) | Total ↑ late, puck-line favourite −1.5 ↑ | A (mechanical); the size is team-specific |

### 1b. Sources

| what | source | status | when published vs the start | language | notes |
|---|---|---|---|---|---|
| NHL starting goalies | dailyfaceoff.com/starting-goalies | **V** | Status per goalie with a timestamp; many are confirmed the day before (e.g. a confirmation stamped 2026-10-24 for a 10-25 game); "updated live"; the day's page links D-1 / D+1. Historical labels: Confirmed = the team or a beat writer; Expected = not confirmed | EN | Free; the most direct source |
| NHL lines, PP units, goalies, injuries per team | dailyfaceoff.com/teams/<team>/line-combinations | **V** | 12 F / 6 D / PP1-PP2 / goalies / IR-DTD-OUT; "last updated" timestamp; built from the last game (no morning-skate marker) | EN | Free |
| NHL lineups, confirmed goalie, lines, PP, injury statuses (OUT / IR / IR-LT / IR-NR) | rotowire.com/hockey/nhl-lineups.php | **V** | Game day | EN | Free view |
| NHL starting goalies, lines | leftwinglock.com | **V (paywalled)** | n/a | EN | Premium only; skip |
| NHL injuries | nhl.com/injuries | V (error page) | n/a | EN | Not usable |
| Team beat reporters / team X accounts (morning skate, coach's media) | x.com (team / reporter accounts) | U | Morning skate about 10:30-11:30 local time | EN | X pages render poorly to a fetch |
| AHL transactions | theahl.com (home **R**; `/stats/transactions` returned no entries to a fetch, likely JS) | R | Daily | EN | Search snippets ("<team> recalls", "assigned to") work better |
| Liiga (FIN) | liiga.fi (R, JS-only body); lineups were historically published through **Veikkaus** channels at a fixed hour (12:00) on game day ([MTV 2021-22 example](https://www.mtvuutiset.fi/artikkeli/sm-liigajoukkueen-kokoonpano-allistyttaa-veikkaus-reagoi-rajusti/9309772), S); jatkoaika.com (R) | R / S | Game day, around noon (per MTV) | FI | The noon rule was seen for one season; re-verify |
| SHL (SWE) | shl.se (R); tv4.se reports on goalie changes (S); the line-up ("matchtrupp") is released before the game | R / S | About 1 h before (per a search summary; U) | SV | |
| DEL (GER) | penny-del.org (R, redirects to /startseite); eishockeynews.de (R) | R | U | DE | |
| Czech Extraliga | hokej.cz (R); match pages "sestavy" (U) | R | U | CZ | |
| Slovak Tipos Extraliga | hockeyslovakia.sk (R); hokej.sk (no response) | R | U | SK | |
| Swiss National League | nationalleague.ch (R); hockeyfans.ch (R) | R | U | DE/FR | |
| ICE Hockey League (AUT) | ice.hockey (R); hockeynews.at (R) | R | U | DE | |
| Polish PHL | phl.pl (R); hokej.net (R) | R | U | PL | |
| KHL | khl.ru (root B, /news R, JS); championat.com/hockey (R); sports.ru/hockey (R); sport-express.ru (B) | B / R | The KHL protocol lists goalies at the game; club Telegram channels (U) | RU | Starting goalie before the game: **no verified free source**; use search snippets |
| European goalie / roster DB | eliteprospects.com | B | n/a | EN | Snippets only |
| Advanced team stats (context, not a gate) | naturalstattrick.com, moneypuck.com, hockeyviz.com, hockey-reference.com | R | Next day | EN | |

---

## 2. Basketball

### 2a. Checklist

| # | item | market variables affected and direction | evidence |
|---|---|---|---|
| B1 | **Injury / availability status** (Out / Doubtful / Questionable / Probable / GTD) of starters and stars | The team total ↓, the handicap moves; teammates' usage props ↑; a prop on a player listed Out | A (direction); the size depends on the player |
| B2 | **Load management / rest of stars** (the NBA, also EuroLeague stars in domestic games) | As B1; frequent on the 2nd night of a back-to-back | F; NBA rest rules restrict it (U) |
| B3 | **Back-to-back / rest days** | The tired side ↓ about 2 points; peak performance after 1 day of rest | E: Small (1999-00): ≥3 days vs a back-to-back = 2.26 pts, the only significant contrast ([pdf](https://www.nessis.org/nessis07/Dylan_Small.pdf)); Abolins et al. (UNC): both too little and too much rest negative ([pdf](https://our.unc.edu/wp-content/uploads/sites/1148/2023/04/TeamJuliusPeppers.pdf)); Yang et al. 2021 ([Frontiers](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2021.630769/pdf)) |
| B4 | **Travel and time zones** | The away side ↓ | E- for the NBA (Roy & Forest abstract: westward disadvantage, [AASM](https://aasm.org/nfl-nba-and-nhl-teams-have-a-disadvantage-when-traveling-west)); size unmeasured |
| B5 | **Altitude** (Denver, Utah ~1,300-1,600 m) | The home side ↑; visitors' late-game fatigue (F) | E: Denver's estimated home win probability vs an equal team about 66-67%, the largest edge in the four US leagues studied (Lopez, Matthews, Baumer; [NBA.com](https://www.nba.com/news/is-impact-of-denvers-altitude-fact-or-fiction), [MSU Denver](https://red.msudenver.edu/2018/advantage-altitude-exploring-the-largest-home-advantage-in-sports/)). Quarter-level effect: no study found (F) |
| B6 | **Minutes restriction** (a return from injury, typically capped at 15-28 min) | That player's props ↓ (points / rebounds / assists / threes / FT) | A: caps reported as 24-28 min (Curry), 28 (Davis), 15 (McDaniels) ([CBS](https://www.cbssports.com/fantasy/basketball/news/mavericks-anthony-davis-available-with-minutes-restriction-505909), [NBCS](https://www.nbcsportsbayarea.com/nba/golden-state-warriors/steve-kerr-steph-curry-nba-play-in-minutes-limit/1931403/)) |
| B7 | **Starting lineup change** (a bench player starting) | That player's props ↑; whoever was moved out ↓ | A |
| B8 | **EuroLeague double-round week** (two games in about 48 h) and a domestic game wedged between EuroLeague games | Rotation: stars rested in the domestic game → that team's total ↓ and its handicap ↓; in the EuroLeague 2nd game var↑ | E- / F: a 2017 Eurohoops table of double-week records ([Eurohoops](https://eurohoops.net/en/trademarks/398836/double-game-weeks-best-teams-best-players)); a coach describing rotation after double weeks (Ataman); no fatigue study |
| B9 | **Domestic league with a EuroLeague / EuroCup team** (ACB, LBA, BSL, Greek, ABA, LKL, BBL, PLK) | The EuroLeague team rests players in the domestic game → its handicap ↓; foreign / import limits shape the rotation | F; BSL raised its foreign limit from 5 to 7 ([Eurohoops](https://eurohoops.net/en/tbl/1670066/turkish-league-increases-foreign-players-limit-from-5-to-7), S) |
| B10 | **Tanking / nothing to play for** (late NBA season) | Blowouts: big handicaps; the tanking side's stars sit (B1) | E-: one night of 9 tank games with an average margin of 24.4 ([CBS](https://picks-s6.cbssports.com/nba/news/nba-tank-watch-rankings-wizards-kings-april-7/)); markets may over-price tanking (Penn thesis, [repo](https://repository.upenn.edu/handle/20.500.14332/49228)); 2026-27 anti-tank lottery changes (S) |
| B11 | **Garbage time** (expected blowout) | Starters' props ↓ (minutes cut); 4th-quarter / second-half total var↑; a favourite's big handicap ↓ (the bench gives points back) | F (no study found) |
| B12 | **Referee crew** (NBA) | FTA and the total ↑ / ↓ by crew | E-: per-official FTA and points averages exist (SI 2024-25 Finals previews, [SI](https://www.si.com/nba/referees-for-nba-finals-game-2)); a referee foul model per 100 possessions ([The F5](https://thef5.substack.com/p/nba-referee-database)); whether crews predict totals beyond the line is not shown → F for betting |
| B13 | **Overtime / late fouling** | Full-game totals include OT; the NBA fouls less when trailing than college does | A / E- ([Action Network](https://www.actionnetwork.com/nba/nba-foul-late-game-data-study-college-basketball)) |
| B14 | **Coach change, trade deadline, newly traded players' debut** | var↑ | F |
| B15 | **Asian / Australian leagues: import players' availability** (KBL, B.League, CBA, NBL; one import missing changes a lot) | The team total ↓ | F; the import rules differ (the KBL's are strict, [JoongAng](https://www.koreajoongangdaily.com/sports/kbl-is-too-hard-on-foreign-players/10026674), S) |
| B16 | **Season opener / early-season rust; NBA Cup games** | var↑ | F |

### 2b. Sources

| what | source | status | when vs the start | language | notes |
|---|---|---|---|---|---|
| NBA official injury report | official.nba.com/nba-injury-report-2025-26-season/ | **V** | Teams file by 17:00 local the day before (by 13:00 on game day for the 2nd of a back-to-back); a game-day update 11:00-13:00 local (08:00-10:00 for a tip-off ≤ 17:00); PDFs re-issued every 15 min | EN | The authoritative source; a PDF per snapshot. (A 2026-27 page may exist: U) |
| NBA referee assignments | official.nba.com/referee-assignments/ | **V** | **About 09:00 ET on game day**; crew chief / referee / umpire / alternate per game | EN | Free |
| NBA lineups + injury status + refs | rotowire.com/basketball/nba-lineups.php | **V** | Game day; confirmed vs expected starters, Out / Doubt / Ques, referee names | EN | Free view; no minutes-restriction flag shown |
| NBA lineups (verified / projected) | basketballmonster.com/nbalineups.aspx | **V** | Game day; projected minutes for members only | EN | Partly free |
| NBA injuries | espn.com/nba/injuries (202, R); cbssports.com/nba/injuries (R); covers.com (R) | R | Daily | EN | |
| NBA player news (restrictions, rest) | nbcsports.com/fantasy/basketball/player-news (R); fantasypros.com/nba/news (R); rotoballer.com (S); x.com/UnderdogNBA (R) | R / S | Continuous | EN | Underdog's X feed is the fastest by reputation (F); X renders poorly to a fetch |
| NBA official lineups page | nba.com/players/todays-lineups | V (empty without JS) | n/a | EN | Not usable by fetch |
| EuroLeague / EuroCup official | euroleaguebasketball.net | **B (429)** | n/a | EN | Snippets only |
| EuroLeague injuries | basketnews.com: "EuroLeague Injury Report (updated daily)" | **V** | Daily | EN | Free |
| European news | eurohoops.net (R); rotowire.com/euro pregame "Status Check" articles (S, the examples found are from 2021-22; current pages U) | R / S | Game day | EN | |
| Domestic leagues | acb.com, legabasket.it, easycredit-bbl.de, plk.pl, vtb-league.com, nbl.com.au, kbl.or.kr, cbaleague.com (all R); tbl.org.tr, b1.bleague.jp (no response) | R | U | local | Lineups / injuries: U per league |
| Rest / schedule | basketball-reference.com (R) | R | | EN | Schedule → back-to-backs, rest days |

---

## 3. Volleyball

### 3a. Checklist

| # | item | market variables affected and direction | evidence |
|---|---|---|---|
| V1 | **Starting six** (whether the regular **opposite**, **setter** or main outside hitter starts) | The favourite's set handicap ↓ and win ↓; set count / total points ↑ (more sets) when the favourite is weakened; set score 3-0 ↓ | F (direction certain by the arithmetic of a weaker side) |
| V2 | **Rested starters** in a league game wedged between **CEV** games, or in an early CEV round | As V1 | E-: "many teams rested key starters in the first round" (women's CL, [CEV fantasy article](https://www.cev.eu/articles/club-volleyball/double-the-fun-in-the-cev-champions-league-fantasy-game-with-clvolleym-throwing-off), S); bench use in the CL ([volleyball.it 2026-01](https://www.volleyball.it/2026/01/16/notizie/articolo/volleyballit-daily-roundup-january-15-2026.html), S) |
| V3 | **Foreigner / import rules** (who may be on court) | Limits a rotation when an import is out | A, per league. SuperLega (ITA): **at least 3 Italians on court**, a foreign libero counts as foreign (2016 rule, reported still in force for 2024-25, [OA Sport](https://www.oasport.it/2024/09/volley-in-superlega-2024-2025-resta-la-regola-del-numero-minimo-di-italiani-in-campo-ma-ce-chi-la-aggira/), S). Turkish Sultanlar Ligi (women): **3 foreigners on court, 2 on the bench** (an undated column, [24saat](https://www.24saatgazetesi.com/sultanlar-ligi-dolu-dizgin-ama), S; not confirmed by the TVF). PlusLiga: **not found** (U) |
| V4 | **Travel** (CEV away trips; Russian Superleague distances; Brazil) | The away side ↓ | F |
| V5 | **Dead rubber / already qualified / playoff seeding settled** | Rotation → as V1, var↑ | F |
| V6 | **Women's vs men's** | Women's: longer rallies, more sets go long? Points per set and set-count distributions differ; read only the class's own curve | F (the pipeline already separates by class) |
| V7 | **Golden set / format** (CEV knockout: a golden set after a 1-1 tie on aggregate; best-of-5 sets with a 15-point 5th) | The golden set counts in no market (the pipeline rule); the 5th set is short → total points lower than a 25-point extrapolation | A |
| V8 | **Coach change / financial trouble** (unpaid salaries are common in some leagues) | var↑ | F |
| V9 | **National-team players returning late** (start of the season after the VNL / Worlds) | The favourite ↓ early | F |

### 3b. Sources

| what | source | status | when | language | notes |
|---|---|---|---|---|---|
| PlusLiga (POL men) | **tauronliga.pl** (plusliga.pl 301-redirects there; the league now carries the TAURON name); match page `/games/action/show/id/<id>.html` with `#stats` and a "Przed Meczem" comparison | **V** | Stats after or during the match; **no lineup** visible before it | PL | The starting six before the match: not published there (as fetched) |
| Polish women | TAURON Liga Kobiet (a separate site; U); tauronliga.pl serves the men's league | U | | PL | |
| Data Project (Genius) federation sites | `<acronym>-web.dataproject.com`, e.g. lvf-web (Lithuania, V): stats per match `MatchStatistics.aspx?mID=<id>`; a "Live Score" menu (placeholder on the LVF page); pzps-web did not respond | V (pattern) | During / after the match | various | The starting rotation appears in the live / stats pages after the start, not before (U for PZPS) |
| SuperLega / A2 (ITA) | legavolley.it: calendars, "Risultati LIVE" on ww2.legavolley.it/lvc/ | **V** (the menus) | Live | IT | No pre-match six seen; volleyball.it (R) and oasport.it (S) news |
| Turkey | tvf.org.tr (R); voleybolplus.com (R) | R | | TR | |
| Russia | volley.ru (V: the federation, men's and women's Superleague calendar, news; no protocols seen) | V | | RU | |
| Brazil | cbv.com.br (R); superliga.cbv.com.br (no response) | R | | PT | |
| CEV | cev.eu (V: Live Scores and Calendar links, CL / Cup / Challenge pages, **no lineups**) | V | | EN | |
| International | volleyballworld.com (R; the FIVB VIS data model exists, [VIS SDK](https://www.fivb.org/VisSDK/Fivb.Vis.DataWPF/Fivb.Vis.DataWPF~Fivb.Vis.Volley.VolleyStatistic~Match.html), S) | R | | EN | National teams, not clubs |
| News / transfers | worldofvolley.com (R), volleymob.com (R), volleybox.net (B) | R / B | | EN | |
| Club social media | Instagram / X / Facebook of the clubs | U | Squads ("kadra meczowa") sometimes posted on game day | local | Not fetchable reliably; **no verified free pre-match starting-six source exists** for these leagues |

**Conclusion for volleyball:** the starting six is effectively unknown before the
first serve in every league checked. A pre-match read can find only injuries and
announced rest (news / club posts), a CEV double week (calendar) and the import
rules. Everything else is F.

---

## 4. CS2

### 4a. Checklist

| # | item | market variables affected and direction | evidence |
|---|---|---|---|
| C1 | **Stand-in / missing player** (illness, visa, paternity, benching) | That team's map win ↓, its map handicap ↓; the stand-in's kills prop is wrong to read from the roster player's history; series total maps: ↑ if it brings the sides closer, ↓ if it widens the gap | E-: anecdotes only (a stand-in rated 0.88 while his team won IEM Dallas 2024, [escorenews](https://escorenews.com/en/csgo/news/67386-stewie2k-finishes-first-match-after-iem-dallas-against-noname-mix-with-negative-kd-and-0-88-rating), S); no win-rate study found → direction A, size F |
| C2 | **Roster change** (a new player or IGL, < 2-4 weeks together) | var↑, the map pool shrinks | F |
| C3 | **Map pool / veto** (which maps; each team's permaban; a pick of an opponent's strong map) | Map-total rounds and map handicap depend on the map; the series map count depends on the veto | A (the veto is known only shortly before the series) |
| C4 | **Active Duty change** (a map added or removed) | The new map has thin history → var↑ | A: Anubis replaced Train (2026-01-19), **Cache replaced Overpass** from Premier Season 5 (Valve post 2026-06-22) ([Ginx](https://www.ginx.tv/en/cache-cs2-active-duty-overpass-replaced), S). Current pool (per reports): Dust2, Mirage, Inferno, Nuke, Ancient, Anubis, Cache. Verify on counter-strike.net |
| C5 | **Best-of format** (bo1 / bo3 / bo5) | Series total maps, upsets ↑ in bo1 | A (the pipeline refuses to guess bo3 when best_of is missing) |
| C6 | **MR12 and overtime** (24 rounds of regulation; OT in MR3 blocks, 4 of 6 wins, $10,000 OT money at the Majors; it **varies by event**) | Total rounds: a close map ↑ (an OT adds ≥ 4 rounds); a rounds UNDER near 21.5-24.5 is OT-sensitive | A: [Valve confirms MR12 + OT (dust2.us)](https://dust2.us/news/39261/valve-officially-confirms-mr12-and-overtime-in-competitive-play) (S); the OT start money is per event ([DatHost](https://dathost.net/docs/cs2-overtime-settings), S) |
| C7 | **LAN vs online** (ping, server location) | An online match with a ping asymmetry: the high-ping side ↓; LAN debutants / "onliners" ↓ | E-: pro interviews (ping matters most for wide peeks; "45 ping in CS2 feels like 70 in CSGO", [escorenews](https://escorenews.com/en/csgo/news/52649-twistzz-on-online-cs2-on-lan-i-would-have-time-to-react-when-holding-angles-it-seems-like-ping-plays-a-much-more-important-factor), S); "onliners" article ([dust2.us](https://www.dust2.us/news/31616/the-real-onliners-of-csgo), S); no study → F for size |
| C8 | **Visa / travel problems** (a player missing a LAN → a stand-in = C1; playing from a bootcamp with jet lag) | As C1 | F |
| C9 | **Stage stakes** (an elimination match vs already qualified; the last Swiss round for a team already through; a VRS-points chase before Major invites) | An already-qualified side ↓, var↑ | F; VRS mechanics: [Valve GitHub repo](https://github.com/ValveSoftware/counter-strike_regional_standings) (V: model, standings, invitations; updated "periodically") |
| C10 | **Patch / game update shortly before** (economy, weapons, map changes) | var↑ | F |
| C11 | **Player form** (HLTV rating over the last 3 months; an AWPer's form) | Player kills / headshot props | F as a context item (the pipeline's model reads the stats); HLTV ratings are blocked to fetch |
| C12 | **Schedule density** (two series in one day; a bo3 after a long bo3) | var↑ | F |
| C13 | **Tier-3 integrity** (match-fixing history, ESIC sanctions) | A reason to WATCH any leg | F; the source would be ESIC announcements (U) |

### 4b. Sources

| what | source | status | when | language | notes |
|---|---|---|---|---|---|
| Matches, lineups, **veto**, stats, ratings | hltv.org/matches/<id>/... (veto text, lineups and maps on the match page: U, prior knowledge) | **B** (403) | The veto appears about 0-15 min before the series (U) | EN | Snippets via `allowed_domains:["hltv.org"]` return current news / transfers / match titles (S, verified 2026-10-26: e.g. the jL stand-in for Vitality, Snax benched by GamerLegion) |
| Transfers / stand-ins | hltv.org/transfers (S); liquipedia `Portal:Transfers` (V via the API) | S / V | Continuous | EN | The Liquipedia API is the only verified machine-readable source |
| News mirror (roster news readable) | dust2.us (V: roster news such as a benching or a step-down), dust2.dk (R) | V | Continuous | EN / DA | |
| Matches by tournament | gosugamers.net/counterstrike/matches (V: teams, tournament, countdown; **no tier, no bo**) | V | | EN | |
| Matches, veto, maps | bo3.gg (200, but the body is empty without JS) | R | | EN | |
| Organisers | esl.com / pro.eslgaming.com, pgl.ro, blast.tv/cs (all R) | R | Format, bo, stage | EN | Rulebooks: the OT money and server details (U) |
| Valve rankings | github.com/ValveSoftware/counter-strike_regional_standings (**V**) | V | Periodic | EN | |
| Game updates | counter-strike.net/news (R) | R | | EN | Map pool / patch notes |
| Faceit-based leagues (tier 3) | faceit.com (B) | B | | EN | |

---

## 5. Cross-sport items

| item | variables | evidence | source |
|---|---|---|---|
| Venue / neutral site / a moved game | home advantage ↓ | A | Sofascore's `/event` venue (in the pipeline) |
| Postponement / rescheduling | refund rules | A | the pipeline's FIXTURE_CHECK |
| Weather (outdoor hockey only) | H10 | F | weather sites (U) |
| Morale, unpaid wages, ownership crisis (volleyball, lower basketball / hockey leagues) | var↑ | F | local news |
| Market moves (Superbet's own line moves) | already in the dossier | n/a | the pipeline |

## 6. Gaps and cautions

1. **No free verified pre-match source** for: a European hockey starting goalie
   (Liiga's noon release through Veikkaus is the only lead: S, one season),
   the KHL goalie, any volleyball starting six, or a CS2 veto that can be fetched
   (HLTV is blocked).
2. Most "effects" beyond goalie rest, back-to-back / travel and altitude are **F**.
   An analyst must carry them at most as a WATCH through the leg's own variable.
3. The NBA injury-report rule text read 2026-10-26 is the 2025-26 page; check
   whether a 2026-27 page supersedes it.
4. Import rules: the SuperLega and Sultanlar Ligi numbers come from press
   (2016-2025), not from the rulebooks; the PlusLiga rule was not found.
5. Liquipedia: respect the terms (≤ 1 parse / 30 s, a custom UA, gzip, no HTML scraping).
