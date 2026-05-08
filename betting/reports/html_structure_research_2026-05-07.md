# HTML Structure Research Report — All 14 Domains

**Generated:** 2026-05-07  
**Purpose:** Guide extraction profile fixes/creation for `scripts/html_deep_parser.py`  
**Skip:** hltv.org, atptour.com (CF-blocked per user instruction)

---

## GROUP A — Broken Profiles (need selector fixes)

### 1. tennisexplorer.com
```
STATUS: EXTRACTABLE
SPORT: tennis
FILE: 20260504T143653Z.html (907KB, 12 tables)
```

**CURRENT PROBLEM:** Profile looks for generic patterns but the actual HTML uses very specific classes.

**KEY PATTERNS:**
- **Tournament header:** `<tr class="head"> <td class="t-name" colspan="5">Main tournaments</td>`
- **Tournament row:** `<tr class="one|two"> <td class="t-name"><a href="/rome/2026/atp-men/">...Rome</a></td>`
- **Match row (player 1):** `<tr id="s0" class="one fRow"> <td class="first time" rowspan="2"><span class="upper">Yesterday<br>19:10</span></td> <td class="t-name"><a href="/player/onclin-89017/">Onclin G.</a></td> <td class="result">2</td> <td class="score">6</td> <td class="score">6</td> ...`
- **Match row (player 2):** `<tr id="s0b" class="one">` (follows player 1, shares `rowspan` cells)
- **Odds cells:** `<td class="course" rowspan="2">1.77</td> <td class="course" rowspan="2">1.97</td>` (H/A odds)
- **Match detail link:** `<a href="/match-detail/?id=3192564">info</a>`
- **Country flags:** `<span class="fl fl-it">&nbsp;</span>` (fl-{iso2})
- **Score cells:** `<td class="score">6</td>` (set scores, 5 columns)
- **Result cell:** `<td class="result">2</td>` (sets won)

**CSS SELECTORS:**
```css
table.result.flags            /* Main results table */
tr.one, tr.two                /* Alternating match rows */
td.t-name                    /* Tournament name or player name */
td.first.time                /* Match time */
td.result                    /* Sets/match result */
td.score                     /* Set scores (5 columns) */
td.course                    /* Odds (H and A) */
a[href*="/player/"]           /* Player links */
a[href*="/match-detail/"]     /* Match detail links */
span.fl.fl-{country}          /* Country flags */
```

**RECOMMENDED FIX:** Profile should iterate `table.result.flags`, pair consecutive `tr` rows (id `sN` + `sNb`), extract player names from `td.t-name a[href*="/player/"]`, scores from `td.score`, odds from `td.course`.

---

### 2. soccerstats.com
```
STATUS: EXTRACTABLE (partial — CF challenge present but content rendered)
SPORT: football
FILE: 20260504T115025Z.html (352KB, 50 tables)
```

**CURRENT PROBLEM:** Profile looks for `<th>` headers and `title` attributes, but soccerstats uses legacy `<tr class="trow1|trow2">` rows, inline CSS, and `<font>` tags. No `<th>` elements.

**KEY PATTERNS:**
- **League navigation:** `<a href="latest.asp?league=england">ENG - Premier League</a>`
- **League selector:** `<form class="leaguelist"><select class="leaguelist">`
- **Data rows:** `<tr class="trow1"> ... <tr class="trow2">` (alternating)
- **Country flags:** `<img src="data:image/png;base64,..." title="Argentina">`
- **Stat values:** Plain text in `<td>` cells, no data attributes
- **Page structure:** Old-school tables for layout, no semantic HTML
- **Ads/spacer tables:** Many `<table cellspacing="0" cellpadding="0">` spacers

**CSS SELECTORS:**
```css
tr.trow1, tr.trow2           /* Data rows (alternating) */
form.leaguelist               /* League selector form */
select.leaguelist             /* League dropdown */
a[href*="latest.asp?league="] /* League links */
td[bgcolor]                  /* Colored cells (standings) */
```

**DATA STRUCTURE:** This is a league-overview page. Actual per-team stats require navigating to league-specific pages. The main page provides league links and potentially standings tables. Data extraction must handle positional column parsing (columns identified by order, not by class/id).

**RECOMMENDED FIX:** Profile should identify tables by surrounding text context (e.g., find `<b>` headers preceding tables), parse `tr.trow1/trow2` rows by column position, extract league links for further scraping.

---

### 3. covers.com
```
STATUS: EMPTY_SHELL (homepage — no match data)
SPORT: multi-sport (US focus: NFL, NBA, MLB, NHL)
FILE: 20260507T220649Z.html (1150KB, 0 tables)
```

**CURRENT PROBLEM:** The captured file is the covers.com HOMEPAGE, which contains only navigation/menu structure (header, subnav, footer). Zero match data, zero odds, zero tables.

**KEY PATTERNS:**
- **Navigation structure:** `.covers-CoversSubNav2-visible-links` (sport subnav)
- **Sport menu items:** `.covers-CoversDesktop-sporticon.basketball-icon`, `.football-icon`, etc.
- **Content is JS-rendered:** All match cards are loaded via JavaScript
- **Relevant CSS classes found (but empty):** `.covers-CoversHomepage-topSportsbooks`
- **No `data-testid` or `data-qa` for match data**

**CSS SELECTORS (for match pages, not this file):**
```css
.game-card, .matchup, .event-card    /* Expected on subpages */
.covers-CoversSubNav2-visible-links  /* Sport navigation links */
```

**DATA:** This file is NOT useful for extraction. Need to capture sport-specific pages like `/nba/odds/` or `/mlb/matchups/`.

**RECOMMENDED FIX:** Mark this profile as requiring sport-specific URLs. Current profile's card-based extraction is correct in approach but the HTML files captured are homepage-only.

---

### 4. betexplorer.com
```
STATUS: EXTRACTABLE
SPORT: multi-sport (football primary, also tennis, hockey, volleyball, baseball)
FILE: 20260504T120226Z.html (1233KB, 2 tables)
```

**CURRENT PROBLEM:** Profile searches for `class="match"` on `<tr>` elements but actual rows have NO class — they're plain `<tr>` inside `<table class="table-main">`.

**KEY PATTERNS:**
- **Main table:** `<table class="table-main">`
- **Tournament header row:** `<tr class="js-tournament"><th class="h-text-left" colspan="2"><a class="table-main__tournament"><i><img src=".../198.svg" alt="England"></i>England: Professional Development League</a></th><th class="table-main__odds">1</th><th class="table-main__odds">X</th><th class="table-main__odds">2</th></tr>`
- **Match data row:** `<tr><td class="h-text-left"><span class="table-main__time">15:00</span><a href="/football/england/professional-development-league/huddersfield-bournemouth/vPiw84vf/">Huddersfield U21 - Bournemouth U21</a></td><td class="table-main__streams h-text-right"></td><td class="table-main__odds" data-oid="9vjurxv464x0xrcs5h"><button>3.06</button></td><td class="table-main__odds" data-oid="..."><button>3.71</button></td><td class="table-main__odds" data-oid="..."><button>2.04</button></td></tr>`
- **Odds attribute:** `data-oid="9vjurxv464x0xrcs5h"` — unique odds ID per outcome
- **Time:** `<span class="table-main__time">15:00</span>`
- **Match URL pattern:** `/football/{country}/{league}/{home}-{away}/{matchid}/`
- **Sport IDs (JS config):** football=1, tennis=2, hockey=4, volleyball=12, baseball=6

**CSS SELECTORS:**
```css
table.table-main                          /* Main odds table */
tr.js-tournament                          /* Tournament header row */
a.table-main__tournament                  /* Tournament name+link */
span.table-main__time                     /* Match time */
td.table-main__odds                       /* Odds cell */
td.table-main__odds[data-oid]             /* Odds with ID */
td.table-main__odds button                /* Odds value (text content) */
td.table-main__result                     /* Match result (if available) */
td.table-main__partial                    /* Partial scores */
```

**RECOMMENDED FIX:** Replace `row.find_all("tr", class_=re.compile(r"match"))` with iterating ALL `<tr>` inside `table.table-main`. Match rows are plain `<tr>` with `<td class="h-text-left">` containing team link. Tournament context comes from preceding `<tr class="js-tournament">`. Extract odds from `<td class="table-main__odds"> <button>` text.

---

### 5. betclic.pl
```
STATUS: EXTRACTABLE (Angular SPA — server-rendered content available)
SPORT: multi-sport
FILE: 20260505T102735Z.html (891KB, 0 tables)
```

**CURRENT PROBLEM:** Profile is partially functional. HTML uses Angular components with `data-qa` attributes.

**KEY PATTERNS:**
- **Navigation:** `<header-base-desktop data-qa="navBar">`
- **Event card container:** `<div class="cardEvent_content"><div class="event">`
- **Event image:** `<div class="event_img"><img bcdkimagefallback="" ...>`
- **Scoreboard:** `<div class="scoreboard is-line has-teamLogos is-retrocompat"><div class="scoreboard_wrapper"><span data-qa="boosted-odds-match-name">Liga Mistrzów 2025-26</span></div></div>`
- **Odds selection:** Elements with `data-qa="boosted-odds-select*"`
- **Key data-qa values (241 hits):** `navBar`, `commonLogo`, `boosted-odds-match-name`, `boosted-odds-select*`
- **Match name in scoreboard:** `<span data-qa="boosted-odds-match-name">`
- **Score elements:** `<div class="scoreboard_date">`, `<div class="scoreboard_info">`
- **JSON data block:** `<script type="application/json">` contains API response data with bet info

**CSS SELECTORS:**
```css
div.event                                 /* Event container */
div.cardEvent_content                     /* Event card content */
div.scoreboard                           /* Scoreboard wrapper */
span[data-qa="boosted-odds-match-name"]  /* Match/league name */
div.scoreboard_date                      /* Date display */
div.scoreboard_info                      /* Score info */
[data-qa]                                /* All data-qa elements */
script[type="application/json"]          /* JSON data block */
```

**RECOMMENDED FIX:** Parse the JSON `<script type="application/json">` block which contains structured API responses. Also scan `[data-qa]` elements for match names, odds values. Current profile's approach of finding `data-qa` is correct; ensure it also parses the JSON block.

---

## GROUP B — Missing Profiles (need new profiles)

### 6. sofascore.com
```
STATUS: EXTRACTABLE (Next.js SSR — full JSON data in __NEXT_DATA__)
SPORT: multi-sport (tennis page captured)
FILE: 20260504T115504Z.html (3334KB, 1 table)
```

**KEY PATTERNS:**
- **Primary data source:** `<script id="__NEXT_DATA__" type="application/json">` — contains FULL structured JSON with rankings, match data, sport/category metadata
- **JSON structure:** `{"props":{"pageProps":{"initialProps":{"sport":"tennis","category":"atp","initialRankingsData":{"rankingType":{"sport":{"id":5,"slug":"tennis","name":"Tennis"},"category":{"name":"ATP","slug":"atp"...`
- **Styled-components:** CSS classes are hashed (e.g., `sc-4g7sie-0 gMBPyP`) — NOT reliable for selectors
- **Table:** `<table class="w_100% bd-cl_separate">` with utility classes (Tailwind-like)
- **Data attributes:** `data-testid` used for test hooks, `data-status`, `data-id`, `data-selected`
- **Sport IDs (from JSON):** tennis=5

**CSS SELECTORS:**
```css
script#__NEXT_DATA__                      /* Primary: JSON data blob */
[data-testid]                            /* Test IDs for specific elements */
table.w_100\\%                            /* Rankings table (utility classes) */
```

**RECOMMENDED EXTRACTION:** Parse `__NEXT_DATA__` JSON entirely. This contains complete structured data (rankings, fixtures, H2H, etc.) without needing CSS selectors. Fall back to `[data-testid]` elements for any client-rendered content.

---

### 7. oddsportal.com
```
STATUS: EXTRACTABLE (Vue.js SPA — server-rendered content available)
SPORT: multi-sport
FILE: 20260506T072142Z.html (604KB, 0 tables)
```

**KEY PATTERNS:**
- **Vue.js app:** `data-v-app`, `data-v-93f7084e` (scoped style markers)
- **Event row:** `<div data-v-93f7084e="" id="h4EoUB7T" class="eventRow flex w-full flex-col text-xs" set="77311">`
- **League header:** `<div class="flex h-[30px] w-full items-center" data-testid="sport-country-league-item">`
- **Sport link:** `<a href="/football/" data-testid="header-sport-item">`
- **Country link:** `<a data-testid="header-country-item" href="/football/world/">`
- **Sport icons:** `<img src=".../sport_icons/soccer.svg" alt="Football">`
- **Tailwind CSS classes:** `flex`, `w-full`, `text-xs`, `bg-gray-med_light`, etc.
- **Zone containers:** `<div class="zone__container">`, `<div class="zone__label">`
- **56 eventRow elements, 68 data-testid="event*" elements**

**CSS SELECTORS:**
```css
div.eventRow                              /* Match/event row */
[data-testid="sport-country-league-item"] /* League header */
[data-testid="header-sport-item"]         /* Sport link */
[data-testid="header-country-item"]       /* Country link */
div.zone__container                       /* Odds zone */
div.zone__label                           /* Zone label */
```

**RECOMMENDED EXTRACTION:** Iterate `div.eventRow`, extract league context from preceding `[data-testid="sport-country-league-item"]`. Match names and odds are within the eventRow. Use `data-testid` attributes as stable selectors (more reliable than Tailwind classes).

---

### 8. scores24.live
```
STATUS: EXTRACTABLE (React SSR — JSON data in window.__REACT_QUERY_STATE__ and window.__URQL__PREFETCH__)
SPORT: multi-sport
FILE: 20260504T144008Z.html (3194KB, 0 tables)
```

**KEY PATTERNS:**
- **Primary data:** `window.__REACT_QUERY_STATE__=JSON.parse("{...}")` — dehydrated React Query cache
- **Secondary data:** `window.__URQL__PREFETCH__=JSON.parse("{...}")` — URQL GraphQL prefetch cache
- **URQL sports list:** `{"sportList":[{"__typename":"Sport","slug":"soccer"},{"__typename":"Sport","slug":"basketball"},...`
- **Styled-components:** CSS classes are hashed (e.g., `sc-17qxh4e-2 cuPJkr`) — NOT reliable
- **Data attributes:** `data-testid`, `data-device-container`
- **React Query data:** Contains location, user settings, article data

**CSS SELECTORS:**
```
None reliable — use JSON extraction only
```

**RECOMMENDED EXTRACTION:** Parse `window.__REACT_QUERY_STATE__` and `window.__URQL__PREFETCH__` JSON blobs. These contain full structured data. DOM elements use random styled-components classes that change between builds.

---

## GROUP C — Sport-Specific Sources (need new profiles)

### 9. whoscored.com
```
STATUS: EXTRACTABLE (Hypernova SSR — JSON + HTML tables)
SPORT: football
FILE: 20260504T080424Z.html (909KB, 1 table, 38 JSON embeds)
```

**KEY PATTERNS:**
- **Match table:** `<table class="grid"><tbody><tr><td class="previews-date" colspan="99">04-05-2026, Monday</td></tr>`
- **League row:** `<a href="/regions/252/tournaments/2/england-premier-league" class="level-2 iconize iconize-icon-left"><span class="ui-icon country flg-gb-eng" title="England"></span>Premier League</a>`
- **Match row:** `<tr class="alt"><td class="time">15:00</td><td colspan="99"><a href="/matches/1903411/preview/england-premier-league-2025-2026-chelsea-nottingham-forest">Chelsea vs Nottingham Forest</a></td></tr>`
- **Hypernova JSON:** `<script type="application/json" data-hypernova-key="mainnavigation"><!--{...}-->`
- **Country flags:** `<span class="ui-icon country flg-gb-eng" title="England">`
- **Match URL pattern:** `/matches/{id}/preview/{league}-{season}-{home}-{away}`
- **Player IDs:** `data-pid` attribute

**CSS SELECTORS:**
```css
table.grid                                /* Match preview table */
td.previews-date                          /* Date header row */
a.level-2.iconize                         /* League link */
span.ui-icon.country                      /* Country flag */
td.time                                   /* Match time */
a[href*="/matches/"][href*="/preview/"]    /* Match preview link */
script[data-hypernova-key]                /* Hypernova JSON blocks */
```

**RECOMMENDED EXTRACTION:** Parse `table.grid` for match previews. Date from `td.previews-date`, league from `a.level-2`, match from `a[href*="/matches/"]`. Also parse Hypernova JSON blocks for additional structured data.

---

### 10. cuetracker.net
```
STATUS: EXTRACTABLE
SPORT: snooker
FILE: 20260504T080250Z.html (34KB, 5 tables)
```

**KEY PATTERNS:**
- **Tournament info:** `<table class="left table-small"><tr><td><span class="red"><b>Current tournament:</b></span></td><td><img class="flag flag-wales"><a href="/tournaments/welsh-amateur-championship/2026/7753">2026 Welsh Amateur Championship</a></td></tr>`
- **Country flags:** `<img src="/img/blank.gif" class="flag flag-{country}">`
- **Player links:** `<a href="https://cuetracker.net/players/colin-mitchell">Colin Mitchell</a>`
- **Tournament links:** `<a href="https://cuetracker.net/tournaments/{slug}/{year}/{id}">`
- **Season links:** `<a href="https://cuetracker.net/seasons">`
- **Navigation:** Bootstrap 4 navbar with nav-items
- **Player search:** `<input class="form-control player-finder typeahead" id="player-finder">`
- **DataTables.js** for sortable tables, **Chart.js** for visualization

**CSS SELECTORS:**
```css
table.left.table-small                    /* Info table */
img.flag.flag-{country}                   /* Country flags (flag-england, flag-wales, etc.) */
a[href*="/players/"]                       /* Player links */
a[href*="/tournaments/"]                   /* Tournament links */
span.red b                                /* Label headers */
```

**RECOMMENDED EXTRACTION:** Parse `table.left.table-small` for current tournaments and metadata. Extract player names from `a[href*="/players/"]`, tournament info from `a[href*="/tournaments/"]`, country from `img.flag` class suffix. This is a simple, well-structured page.

---

### 11. dartsorakel.com
```
STATUS: EXTRACTABLE (partial — CF challenge at end but content present)
SPORT: darts
FILE: 20260504T080248Z.html (161KB, 3 tables)
```

**KEY PATTERNS:**
- **Results table:** `<table id="latest-results-table" class="new-design-table table text-center align-middle table-hover no-footer m-0 dataTable">`
- **Table headers:** `<th class="new-design-table-header sorting text-start text-gray-400 fw-bolder fs-7 text-uppercase gs-0">`
- **Result row:** `<tr class="cursor-pointer odd" onclick="window.location='https://dartsorakel.com/match/stats/505515'">`
- **Tournament cell:** `<td class="new-design-table-data">Asian Tour 12</td>`
- **Date cell:** `<td class="new-design-table-data" style="min-width: 60px">2026-05-03</td>`
- **Winner with avg:** `<a href="/player/details/5273/paolo-nebrida" class="text-dark player-name me-1">P. Nebrida</a><span class="player-avg fs-7">(85.98)</span>`
- **Match detail URL:** `https://dartsorakel.com/match/stats/{id}`
- **Player detail URL:** `https://dartsorakel.com/player/details/{id}/{slug}`
- **Metronic UI framework, ApexCharts for stats visualization**

**CSS SELECTORS:**
```css
table#latest-results-table                /* Main results table */
td.new-design-table-data                  /* Data cell */
tr[onclick*="/match/stats/"]              /* Clickable result row */
a.player-name                            /* Player name link */
span.player-avg                          /* Player average score */
a[href*="/player/details/"]              /* Player detail link */
div.winner-avg-container                 /* Winner + average wrapper */
```

**RECOMMENDED EXTRACTION:** Parse `table#latest-results-table` rows. Extract match ID from `tr[onclick]` URL, tournament name from first `td`, date from second `td`, player names from `a.player-name`, averages from `span.player-avg`.

---

### 12. speedwayekstraliga.pl
```
STATUS: EXTRACTABLE (Next.js RSC — data in inline scripts)
SPORT: speedway
FILE: 20260506T071638Z.html (645KB, 5 tables)
```

**KEY PATTERNS:**
- **Next.js React Server Components:** `self.__next_f=self.__next_f||[]).push([0])` — data streamed as RSC payloads
- **Team data in JSON menu:** `{"id":"team-14-1","label":"ORLEN OIL MOTOR Lublin","url":"/druzyny/14/2026/kadra"}`
- **Tables:** `<table class="w-full table-auto overflow-x-auto">` with Tailwind utility classes
- **Emotion CSS:** `data-emotion` attribute on styled elements — hashed class names
- **Data attributes:** `data-nimg` (Next.js image), `data-precedence`
- **Table cells use Tailwind:** `class="box-content pb-[10px] pt-[6px] text-xs font-normal uppercase"`
- **Team URLs:** `/druzyny/{id}/{year}/kadra`

**CSS SELECTORS:**
```css
table.w-full.table-auto                   /* Data tables (Tailwind) */
th.box-content                            /* Table headers */
td.box-content                            /* Table data cells */
```

**RECOMMENDED EXTRACTION:** Parse inline `self.__next_f` RSC payloads for structured data (team names, rider lists, match results). The HTML tables use Tailwind classes but column positions are fixed. Extract team data from JSON fragments in script blocks.

---

### 13. gosugamers.net
```
STATUS: EXTRACTABLE (MUI React — limited data in SSR)
SPORT: esports (LoL, Valorant, CS2, Dota2)
FILE: 20260507T221349Z.html (409KB, 0 tables)
```

**KEY PATTERNS:**
- **MUI (Material-UI) components:** Classes like `MuiBox-root mui-1rr4qq7`, `MuiStack-root`
- **Match links:** `<a href="/lol/tournaments/62661-.../matches/646273-conviction-vs-blue-otter">`
- **Match URL pattern:** `/{game}/tournaments/{id}-{slug}/matches/{id}-{team1}-vs-{team2}`
- **Games found in URLs:** lol, valorant, counterstrike
- **Visible text:** Games, Articles, Tournaments, Matches, Rankings, Schedule, Results, Live
- **Minimal data-testid usage** (only `PersonIcon`)
- **Emotion CSS:** `data-emotion` attribute — hashed class names, unstable

**CSS SELECTORS:**
```css
a[href*="/matches/"]                      /* Match links */
a[href*="/tournaments/"]                  /* Tournament links */
.MuiStack-root                            /* MUI layout containers */
.MuiBox-root                              /* MUI box containers */
```

**RECOMMENDED EXTRACTION:** Parse match URLs from `a[href*="/matches/"]` to extract game type, tournament, team names (from URL slug). MUI class names include hashes but the MUI prefix is stable. Content is sparse in SSR — most data loads via client-side JS.

---

### 14. tennisabstract.com
```
STATUS: EXTRACTABLE
SPORT: tennis
FILE: 20260504T143653Z.html (286KB, 7 tables)
```

**KEY PATTERNS:**
- **Elo ratings table:** `<table id="reportable" class="tablesorter">` (jQuery tablesorter)
- **Table initialized in JS:** `$("#reportable").tablesorter({sortList: [[3,1]]})`
- **Player search:** Autocomplete with `mwplayerlist.js` data source
- **Player links (men):** `https://www.tennisabstract.com/cgi-bin/player.cgi?p=JannikSinner`
- **Player links (women):** `https://www.tennisabstract.com/cgi-bin/wplayer.cgi?p=ArynaSabalenka`
- **Rankings pages:** `/reports/atp_elo_ratings.html`, `/reports/wta_elo_ratings.html`
- **Navigation dropdown menus** with player quick links
- **Clean HTML:** No framework boilerplate, simple tables, jQuery

**CSS SELECTORS:**
```css
table#reportable                          /* Main data table */
table#reportable th                       /* Column headers (sortable) */
table#reportable td                       /* Data cells */
a[href*="/cgi-bin/player.cgi"]            /* Men's player links */
a[href*="/cgi-bin/wplayer.cgi"]           /* Women's player links */
#playersearch #tags                       /* Player search input */
```

**RECOMMENDED EXTRACTION:** Parse `table#reportable` for Elo ratings/rankings data. Columns are determined by the specific page (elo_ratings vs rankings). Extract player names and profile URLs. This is the cleanest, most parseable site in the set.

---

## GROUP D — CF-Blocked (SKIP)

### hltv.org
**STATUS:** CF_BLOCKED — Existing profile in parser, kept as-is.

### atptour.com
**STATUS:** CF_BLOCKED — No profile needed.

---

## Summary Matrix

| Domain | Status | Sport | Data Location | Tables | JSON | Stable Selectors |
|--------|--------|-------|--------------|--------|------|------------------|
| tennisexplorer.com | EXTRACTABLE | tennis | HTML tables | 12 | 0 | YES — `td.t-name`, `td.score`, `td.course` |
| soccerstats.com | PARTIAL | football | HTML tables | 50 | 0 | WEAK — `tr.trow1/trow2`, positional |
| covers.com | EMPTY_SHELL | US sports | N/A (homepage) | 0 | 0 | N/A — wrong page captured |
| betexplorer.com | EXTRACTABLE | multi | HTML table | 2 | 0 | YES — `table-main__*`, `data-oid` |
| betclic.pl | EXTRACTABLE | multi | HTML + JSON | 0 | 1 | YES — `data-qa`, `div.event` |
| sofascore.com | EXTRACTABLE | multi | `__NEXT_DATA__` JSON | 1 | 1 | JSON only — CSS hashed |
| oddsportal.com | EXTRACTABLE | multi | Vue SSR | 0 | 0 | YES — `data-testid`, `div.eventRow` |
| scores24.live | EXTRACTABLE | multi | React Query JSON | 0 | 2 | JSON only — CSS hashed |
| whoscored.com | EXTRACTABLE | football | HTML table + Hypernova JSON | 1 | 38 | YES — `table.grid`, `td.time` |
| cuetracker.net | EXTRACTABLE | snooker | HTML tables | 5 | 0 | YES — `table.left`, `a.flag` |
| dartsorakel.com | EXTRACTABLE | darts | HTML table (DataTables) | 3 | 0 | YES — `#latest-results-table`, `.player-name` |
| speedwayekstraliga.pl | EXTRACTABLE | speedway | RSC JSON + tables | 5 | 0 | WEAK — Tailwind utilities |
| gosugamers.net | EXTRACTABLE | esports | URL parsing + MUI | 0 | 0 | WEAK — MUI hashed classes |
| tennisabstract.com | EXTRACTABLE | tennis | HTML table | 7 | 0 | YES — `#reportable` |

## Priority Recommendations

1. **FIX FIRST (highest ROI):** betexplorer.com — just change row selector from `class="match"` to all `<tr>` in `table.table-main`
2. **FIX SECOND:** tennisexplorer.com — good structure, just needs paired-row logic
3. **NEW PROFILE (easy):** tennisabstract.com, cuetracker.net, dartsorakel.com — clean HTML, simple tables
4. **NEW PROFILE (medium):** whoscored.com, oddsportal.com — stable selectors available
5. **NEW PROFILE (JSON parsing):** sofascore.com, scores24.live — parse `__NEXT_DATA__`/`__REACT_QUERY_STATE__`
6. **NEW PROFILE (parse URLs):** gosugamers.net — extract match data from URL patterns
7. **DEFER:** speedwayekstraliga.pl (RSC parsing complex), covers.com (need different pages captured)
