# ESPN Public API — Complete Endpoint Catalog

> Source: [github.com/pseudo-r/Public-ESPN-API](https://github.com/pseudo-r/Public-ESPN-API)  
> Last verified: 2026-03-26 (all domains returned HTTP 200 OK)  
> Coverage: **17 sports · 139 leagues · 370 v2 endpoints · 79 v3 endpoints · 6 API domains**

---

## 1. BASE URLs & DOMAINS

| Domain | Version | Purpose | Auth Required |
|--------|---------|---------|---------------|
| `site.api.espn.com` | v2/v3 | Scores, news, teams, standings (site-facing) | ❌ No |
| `sports.core.api.espn.com` | v2 | Athletes, stats, odds, play-by-play, detailed data | ❌ No |
| `sports.core.api.espn.com` | v3 | Athletes, leaders, events (richer schema) | ❌ No |
| `site.web.api.espn.com` | v3 | Search, athlete profiles, stats, gamelog, splits | ❌ No |
| `cdn.espn.com` | — | CDN-optimized live data (requires `?xhr=1`) | ❌ No |
| `now.core.api.espn.com` | v1 | Real-time news feeds | ❌ No |
| `fantasy.espn.com` | v3 | Fantasy sports leagues | 🔒 Private leagues need cookies |

### Important Notes
- **No Authentication Required** for all public endpoints
- **No Official Rate Limits** published, but excessive requests may be blocked
- **No Special Headers** needed (standard `Accept: application/json` recommended)
- **Pagination**: Collections return `count`, `pageIndex`, `pageSize`, `items[]` — use `?page=N&limit=N`
- **`$ref` links**: Core API v2 returns `$ref` URLs for related resources — follow them for detail

---

## 2. SITE API v2 — Scoreboard, Teams, News

**Pattern:** `GET https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/{resource}`

### Resources

| Resource | Description | Key Params |
|----------|-------------|------------|
| `scoreboard` | Live & scheduled events with scores | `dates`, `week`, `seasontype`, `groups`, `limit` |
| `teams` | All teams in the league | — |
| `teams/{id}` | Single team detail | — |
| `teams/{id}/roster` | Team roster (players, coaches) | — |
| `teams/{id}/schedule` | Team schedule (past + future) | `season` |
| `teams/{id}/depthcharts` | Depth chart by position | — |
| `teams/{id}/injuries` | Current injury report | — |
| `teams/{id}/transactions` | Recent transactions/moves | — |
| `teams/{id}/history` | Franchise historical record | — |
| `teams/{id}/record` | Current season record | — |
| `teams/{id}/news` | Team-specific news | — |
| `teams/{id}/leaders` | Team statistical leaders | — |
| `athletes/{id}` | Individual athlete profile | — |
| `athletes/{id}/gamelog` | Game-by-game log | — |
| `athletes/{id}/splits` | Statistical splits | — |
| `athletes/{id}/news` | Athlete news | — |
| `athletes/{id}/bio` | Athlete bio | — |
| `injuries` | **League-wide** injury report (all teams) | — |
| `transactions` | Recent signings/trades/waivers | — |
| `statistics` | League statistical leaders | — |
| `groups` | Conferences/divisions | — |
| `news` | Latest news articles | — |
| `rankings` | Rankings (college sports) | — |
| `draft` | Draft board (NFL/NBA only) | — |
| `calendar` | Season calendar (all weeks/dates) | `calendartype` |
| `calendar/offseason` | Offseason date range | — |
| `calendar/regular-season` | Regular season weeks | — |
| `calendar/postseason` | Postseason date ranges | — |
| `summary?event={id}` | **Full game summary** (boxscore, plays, leaders, predictor, odds) | — |

### ⚠️ Standings Exception
`/apis/site/v2/` returns only a **stub** for standings. Use this instead:
```
GET https://site.api.espn.com/apis/v2/sports/{sport}/{league}/standings
```

### Scoreboard Query Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `dates` | Filter by date (YYYYMMDD) or range | `20241215` or `20241201-20241231` |
| `week` | Week number (football) | `1` through `18` |
| `seasontype` | Season type | `1`=preseason, `2`=regular, `3`=postseason |
| `groups` | Conference ID (college) | `80` (Top 25), `8` (SEC) |
| `limit` | Max events | `100` |

---

## 3. SITE API v3 — Enriched Game Data

**Pattern:** `GET https://site.api.espn.com/apis/site/v3/sports/{sport}/{league}/{resource}`

| Resource | Description |
|----------|-------------|
| `scoreboard` | Scoreboard with enriched v3 schema |
| `summary?event={id}` | Enriched game summary (v3 schema) |

---

## 4. CORE API v2 — Athletes, Stats, Events, Odds

**Pattern:** `GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/{resource}`

### League-Level Resources

| Resource | Description |
|----------|-------------|
| `athletes` | Full athlete list with pagination |
| `athletes/{id}` | Single athlete |
| `athletes/{id}/statistics` | Career stats |
| `athletes/{id}/statisticslog` | Game-by-game log |
| `athletes/{id}/eventlog` | Event history |
| `athletes/{id}/contracts` | Contract info |
| `athletes/{id}/awards` | Awards |
| `athletes/{id}/seasons` | Seasons played |
| `athletes/{id}/records` | Career records |
| `athletes/{id}/hotzones` | Hot zones (baseball) |
| `athletes/{id}/injuries` | Athlete injury history |
| `athletes/{id}/vsathlete/{opponentId}` | **Head-to-head stats** (tennis H2H!) |
| `events` | Events with full detail |
| `events/{id}/competitions/{id}/odds` | **Betting odds** (spread, ML, O/U) |
| `events/{id}/competitions/{id}/probabilities` | **Win probabilities** (live) |
| `events/{id}/competitions/{id}/plays` | Play-by-play |
| `events/{id}/competitions/{id}/situation` | Current game situation (down/distance/ball) |
| `events/{id}/competitions/{id}/broadcasts` | Broadcast network info |
| `events/{id}/competitions/{id}/predictor` | ESPN game predictor |
| `events/{id}/competitions/{id}/powerindex` | ESPN Power Index for game |
| `events/{id}/competitions/{id}/competitors/{id}/linescores` | Period-by-period scores |
| `events/{id}/competitions/{id}/competitors/{id}/statistics` | Competitor stats |
| `seasons` | Season list |
| `seasons/{year}/teams` | Teams in a season |
| `seasons/{year}/coaches` | Coaching staff |
| `seasons/{year}/draft` | Draft data |
| `seasons/{year}/futures` | **Futures odds** |
| `seasons/{year}/powerindex` | Season-level Power Index / BPI |
| `standings` | League standings |
| `teams` | Teams (detailed) |
| `venues` | Venues/stadiums |
| `leaders` | Statistical leaders |
| `rankings` | Rankings |
| `franchises` | Franchise history |
| `coaches/{id}` | Individual coach profile |
| `coaches/{id}/record/{type}` | Coaching record by type |
| `tournaments` | Tournaments list |
| `season` | Current season info |
| `providers` | Odds provider list |
| `casinos` | Casino/sportsbook list |
| `positions` | Position definitions |
| `countries` | Country list |

### Season-Scoped Resources (under `seasons/{year}/types/{type}/`)

| Resource | Description |
|----------|-------------|
| `teams/{team}/ats` | **ATS records** (against the spread) |
| `teams/{team}/odds-records` | **Team odds records** (O/U, ATS) |
| `teams/{team}/statistics` | Team season stats |
| `teams/{team}/statistics/{split}` | Team stats by split |
| `teams/{team}/statistics/{split}/byathlete` | Player stats for team |
| `teams/{team}/records` | Team records (home/away/etc.) |
| `teams/{team}/leaders` | Team leaders for season |
| `teams/{team}/events` | Team events for season |
| `teams/{team}/athletes/{athlete}/statistics` | Player season stats on team |
| `teams/{team}/athletes/{athlete}/vsathlete/{opponentId}` | Player vs player (season) |
| `teams/{team}/attendance` | Team attendance |
| `groups/{group}/standings` | Group standings |
| `groups/{group}/standings/{standingType}` | Specific standing type |
| `groups/{group}/leaders` | Group leaders |
| `groups/{group}/qbr/{split}` | **QBR** (football only) |
| `leaders` | Season leaders |
| `leaders/{split}` | Leaders by split type |
| `weeks` | Season weeks |
| `weeks/{week}/events` | Week events |
| `weeks/{week}/qbr/{split}` | Weekly QBR |
| `weeks/{week}/rankings/{id}` | Week rankings |
| `weeks/{week}/powerindex` | Week power index |

### Odds-Specific Resources

| Resource | Description |
|----------|-------------|
| `{oddId}/history/{betType}` | Odds history for competition |
| `{oddId}/history/{betType}/movement` | **Odds movement** (line movement!) |
| `{id}/head-to-heads` | Head-to-head odds |
| `{id}/propBets` | **Prop bets** |
| `{id}/odds/{oddsProvider}/past-performances` | **Team past performance vs odds** |
| `{id}/predictors` | Predictor data |

### Team Resources (non-season-scoped)

| Resource | Description |
|----------|-------------|
| `{team}/events` | Team events (with date filters) |
| `{team}/injuries` | Team injuries |
| `{team}/leaders` | Team leaders |
| `{team}/coaches` | Team coaches |
| `{team}/seasons` | Team season history |
| `{team}/series/vs-opponent/{opponentId}` | **Series history vs opponent** |
| `{team}/vsathlete/{athlete}` | **Player vs team stats** |
| `{team}/calendar` | Team calendar |
| `{team}/ranks` | Team rankings |

---

## 5. CORE API v3 — Enriched Schema

**Pattern:** `GET https://sports.core.api.espn.com/v3/sports/{sport}/{league}/{resource}`

| Resource | Description |
|----------|-------------|
| `athletes` | Athletes (enriched schema) |
| `athletes/{id}` | Single athlete (enriched) |
| `athletes/{id}/statisticslog` | Game log (enriched) |
| `athletes/{id}/plays` | Athlete play history |
| `athletes/{id}/eventlog` | Athlete event log |
| `leaders` | Statistical leaders |
| `events` | League events |
| `events/{id}` | Single event |
| `events/{id}/competitions/{id}/plays` | Play-by-play |
| `events/{id}/competitions/{id}/drives` | Drives (football) |
| `events/{id}/competitions/{id}/competitors/{id}` | Competitor detail |
| `seasons/{season}` | Season info |

### v3-Exclusive Endpoints

| Endpoint | Description |
|----------|-------------|
| `https://sports.core.api.espn.com/v3/odds` | Global odds |
| `https://sports.core.api.espn.com/v3/predictions` | Win predictions |
| `https://sports.core.api.espn.com/v3/powerindex` | Power index |
| `https://sports.core.api.espn.com/v3/standings` | Global standings |
| `https://sports.core.api.espn.com/v3/featured` | Featured bets |
| `https://sports.core.api.espn.com/v3/markets/{market}` | **Bet market info** |
| `https://sports.core.api.espn.com/v3/freeagents` | Free agents |
| `https://sports.core.api.espn.com/v3/injuries` | Global injuries |
| `https://sports.core.api.espn.com/v3/broadcasts` | All broadcasts |
| `https://sports.core.api.espn.com/v3/draft` | Draft info |
| `https://sports.core.api.espn.com/v3/draft/athletes` | Draft athletes |
| `https://sports.core.api.espn.com/v3/graphql` | **GraphQL endpoint** (POST) |

### v3 Query Parameters (common across all)

Key v3-specific params: `enable`, `disable`, `_hoist`, `_nocache`, `_trace`, `lang`, `region`, `provider`, `provider.priority`, `site`, `split`, `splits`, `record.splits`, `statistic.splits`, `statistic.seasontype`, `statistic.qualified`, `bets.promotion`, `eventstates`, `eventresults`, `seek`

---

## 6. WEB API v3 — Athlete Profiles, Stats, Search

**Pattern:** `GET https://site.web.api.espn.com/apis/{path}`

| Endpoint | Description | Works For |
|----------|-------------|-----------|
| `/search/v2?query={q}&limit={n}` | Global ESPN search | All |
| `/search/v2?query={q}&sport={sport}` | Sport-scoped search | All |
| `/v2/scoreboard/header` | Scoreboard header/nav state | All |
| `/apis/common/v3/sports/{sport}/{league}/athletes/{id}/overview` | Athlete overview (stats snapshot, news, next game, **rotowire notes**) | NFL, NBA, NHL, MLB ✅ |
| `/apis/common/v3/sports/{sport}/{league}/athletes/{id}/stats` | Season stats with filters | NFL, NBA, NHL, MLB ✅; Soccer ❌ |
| `/apis/common/v3/sports/{sport}/{league}/athletes/{id}/gamelog` | Game-by-game log | NFL, NBA, MLB ✅; NHL returns 404 |
| `/apis/common/v3/sports/{sport}/{league}/athletes/{id}/splits` | Home/away/opponent splits | NFL, NBA, NHL, MLB ✅ |
| `/apis/common/v3/sports/{sport}/{league}/statistics/byathlete` | **Stats leaderboard** (all athletes ranked) | All major sports |

### Stats Leaderboard Parameters
- `category=` — stat category to sort by
- `sort=` — sort field
- `season=` — filter by season year
- `seasontype=` — 2=regular, 3=playoffs

---

## 7. CDN API — Real-Time Game Packages

**Pattern:** `GET https://cdn.espn.com/core/{sport}/{resource}?xhr=1`

⚠️ **`?xhr=1` is REQUIRED** — without it you get HTML, not JSON.

| Endpoint | Description |
|----------|-------------|
| `/{sport}/scoreboard?xhr=1` | CDN-optimized live scoreboard |
| `/{sport}/scoreboard?xhr=1&league={league}` | Soccer scoreboard (league slug required, e.g. `eng.1`) |
| `/{sport}/game?xhr=1&gameId={id}` | **Full game package** — drives, plays, win probability, boxscore, odds |
| `/{sport}/boxscore?xhr=1&gameId={id}` | Boxscore only |
| `/{sport}/playbyplay?xhr=1&gameId={id}` | Play-by-play only |
| `/{sport}/matchup?xhr=1&gameId={id}` | Matchup/comparison data |

### CDN Game Package Response Structure
Returns `gamepackageJSON` containing:
- `header` — event metadata, competitors, status
- `boxscore` — team/player statistics
- `drives` — drive summaries with plays (football)
- `plays` — all plays
- `winprobability` — `homeWinPercentage` per play
- `news` — related articles
- `standings` — relevant standings

### CDN Sport Slugs
`nfl`, `college-football`, `nba`, `mens-college-basketball`, `nhl`, `mlb`

---

## 8. NOW API — Real-Time News

**Pattern:** `GET https://now.core.api.espn.com/v1/sports/news`

| Endpoint | Description |
|----------|-------------|
| `/v1/sports/news?limit={n}` | Global real-time news feed |
| `/v1/sports/news?sport={sport}&limit={n}` | Sport-filtered news |
| `/v1/sports/news?leagues={league}&limit={n}` | League-filtered news |
| `/v1/sports/news?team={abbrev}&limit={n}` | Team-filtered news |

### Response Structure
```json
{
  "resultsCount": 1000,
  "resultsLimit": 20,
  "resultsOffset": 0,
  "feed": [
    {
      "headline": "...",
      "description": "...",
      "published": "2025-03-15T02:00:00Z",
      "type": "HeadlineNews",
      "categories": [
        { "type": "league", "id": 46, "description": "NBA" },
        { "type": "team", "id": 9, "description": "Golden State Warriors" },
        { "type": "athlete", "id": 3136776, "description": "Stephen Curry" }
      ]
    }
  ]
}
```

---

## 9. BETTING & ODDS ENDPOINTS (Detailed)

**Base:** `sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}`

### Event-Level Odds

```
GET .../events/{id}/competitions/{id}/odds
GET .../events/{id}/competitions/{id}/odds?provider.priority={n}
```

**Response Fields:**
- `provider.id`, `provider.name`, `provider.priority`
- `details` — spread description (e.g., "-3.5")
- `overUnder` — total line (e.g., 222.5)
- `spread` — spread value
- `overOdds`, `underOdds` — total odds (American)
- `awayTeamOdds.moneyLine`, `awayTeamOdds.spreadOdds`
- `homeTeamOdds.moneyLine`, `homeTeamOdds.spreadOdds`
- `homeTeamOdds.favorite`, `homeTeamOdds.underdog`
- `open.over.value`, `open.under.value`, `open.spread.home.line` — **opening lines**

### Provider IDs

| Provider | ID | Priority |
|----------|----|----------|
| Caesars | 38 | varies |
| FanDuel | 37 | varies |
| DraftKings | 41 | 1 |
| BetMGM | 58 | varies |
| ESPN BET | 68 | varies |
| Bet365 | 2000 | varies |

### Win Probabilities

```
GET .../events/{id}/competitions/{id}/probabilities
```
Returns: `homeWinPercentage`, `awayWinPercentage`, `tiePercentage`, `lastModified`, linked play

### Game Predictor

```
GET .../events/{id}/competitions/{id}/predictor
```
Returns: `gameProjection`, `teamChanceLoss` per team

### Futures

```
GET .../seasons/{year}/futures
GET .../seasons/{year}/futures/{futureId}
```
Params: `active`, `sort`, `groupId`

### ATS & Odds Records

```
GET .../seasons/{year}/types/{type}/teams/{id}/ats
GET .../seasons/{year}/types/{type}/teams/{id}/odds-records
```
Params: `opp` (opponent filter for ATS)

### Odds History & Movement

```
GET .../{oddId}/history/{betType}
GET .../{oddId}/history/{betType}/movement
```

### Prop Bets

```
GET .../{id}/propBets
```

### Past Performances

```
GET .../{id}/odds/{oddsProvider}/past-performances
```

### Head-to-Head Odds

```
GET .../{id}/head-to-heads
```

### Bet Types

```
GET .../bet-types/{betTypeId}
```

### Bet Markets (v3)

```
GET https://sports.core.api.espn.com/v3/markets/{market}
```

### Featured Bets (v3)

```
GET https://sports.core.api.espn.com/v3/featured
```
Params: `bets.promotion`

---

## 10. FANTASY SPORTS API

**Base:** `https://fantasy.espn.com/apis/v3/games/{sport}/seasons/{year}`

### Game Codes
| Sport | Code |
|-------|------|
| Football | `ffl` |
| Basketball | `fba` |
| Baseball | `flb` |
| Hockey | `fhl` |

### League Endpoints
```
GET /apis/v3/games/ffl/seasons/2024/segments/0/leagues/{league_id}
```

### Available Views (query params)
`?view=mTeam`, `?view=mRoster`, `?view=mMatchup`, `?view=mMatchupScore`, `?view=mSettings`, `?view=mDraftDetail`, `?view=mScoreboard`, `?view=mStandings`, `?view=mStatus`, `?view=kona_player_info`

### Segments
| Segment | Description |
|---------|-------------|
| `0` | Entire season |
| `1` | Playoff round 1 |
| `2` | Playoff round 2 |
| `3` | Championship |

### Auth (Private Leagues)
Private leagues require cookies: `espn_s2` and `SWID`

---

## 11. SPECIALIZED ENDPOINTS

### QBR (Quarterback Rating — Football Only)

```bash
# Season QBR by conference
GET .../seasons/{year}/types/{type}/groups/{group}/qbr/{split}
# Weekly QBR
GET .../seasons/{year}/types/{type}/weeks/{week}/qbr/{split}
# All-time QBR
GET .../{league}/qbr/{split}
```
Split values: `0`=totals, `1`=home, `2`=away  
Params: `qualified`, `sort`, `group`, `seasonType`

### Bracketology (NCAA Tournament)

```bash
GET .../tournament/{tournamentId}/seasons/{year}/bracketology
GET .../tournament/{tournamentId}/seasons/{year}/bracketology/{iteration}
```
Tournament IDs: `22`=NCAA Men's, `23`=NCAA Women's

### Power Index (BPI / SP+ / FPI)

```bash
GET .../seasons/{year}/powerindex
GET .../seasons/{year}/powerindex/leaders
GET .../seasons/{year}/powerindex/{teamId}
# By week:
GET .../seasons/{year}/types/{type}/weeks/{week}/powerindex
```
Params: `groupId`, `leaderLimit`

### Recruiting (College Sports)

```bash
GET .../seasons/{year}/recruits
GET .../seasons/{year}/classes/{teamId}
GET .../{league}/recruiting  # recruiting seasons list
```

### Coaches

```bash
GET .../seasons/{year}/coaches
GET .../seasons/{year}/coaches/{coach}
GET .../coaches/{coachId}
GET .../coaches/{coachId}/record/{type}
GET .../seasons/{year}/types/{type}/coaches/{coach}/record
```

### Playoff Machine

```bash
GET .../seasons/{year}/playoff-machine
```
Params: `events`, `results`

### Weather (for outdoor events)

```bash
GET https://sports.core.api.espn.com/v2/zip/{zip}
```
Params: `date`, `hour`

### Talent Picks (Expert Predictions)

```bash
GET .../{league}/talentpicks
GET .../seasons/{year}/types/{type}/weeks/{week}/talentpicks
GET .../seasons/{year}/talentpickers
```

### Team Projections

```bash
GET .../seasons/{year}/teams/{team}/projection
```

### Player Season Projections

```bash
GET .../seasons/{year}/types/{type}/athletes/{athlete}/projections
```

---

## 12. COMMON QUERY PARAMETERS

| Parameter | Description | Example |
|-----------|-------------|---------|
| `dates` | Filter by date (YYYYMMDD or range) | `20241215` or `20241201-20241231` |
| `week` | Week number | `1` through `18` |
| `seasontype` | Season type | `1`=pre, `2`=regular, `3`=post, `4`=off |
| `season` | Year | `2024` |
| `limit` | Results per page | `100`, `500`, `1000` |
| `page` | Page number | `1`, `2`, ... |
| `groups` | Conference/division ID | `8` (SEC), `80` (Top 25) |
| `enable` | Inline-expand extra data | `roster`, `stats`, `injuries`, `projection` |
| `active` | Active filter | `true` / `false` |
| `lang` | Language / locale | `en`, `es`, `pt` |
| `region` | Regional content | `us`, `gb`, `au` |
| `xhr` | CDN JSON signal | `1` (REQUIRED for cdn.espn.com) |
| `calendartype` | Calendar view type | `ondays`, `offdays`, `blacklist` |
| `provider.priority` | Odds provider priority filter | `1` (DraftKings first) |
| `sort` | Sort field | varies by endpoint |
| `position` | Filter by position | varies |
| `qualified` | Qualified athletes only | `true` |
| `type` | Various type filters | varies |
| `utcOffset` | Timezone offset | `-5` |

---

## 13. SPORTS COVERAGE & LEAGUE SLUGS

### Football (`football`)
| League | Slug |
|--------|------|
| NFL | `nfl` |
| College Football | `college-football` |
| CFL | `cfl` |
| UFL | `ufl` |
| XFL | `xfl` |

### Basketball (`basketball`)
| League | Slug |
|--------|------|
| NBA | `nba` |
| WNBA | `wnba` |
| NBA G League | `nba-development` |
| NCAA Men's | `mens-college-basketball` |
| NCAA Women's | `womens-college-basketball` |
| NBL (Australia) | `nbl` |
| FIBA World Cup | `fiba` |

### Baseball (`baseball`)
| League | Slug |
|--------|------|
| MLB | `mlb` |
| NCAA Baseball | `college-baseball` |
| World Baseball Classic | `world-baseball-classic` |
| Dominican Winter League | `dominican-winter-league` |

### Hockey (`hockey`)
| League | Slug |
|--------|------|
| NHL | `nhl` |
| NCAA Men's | `mens-college-hockey` |
| NCAA Women's | `womens-college-hockey` |
| Olympics Men's | `olympics-mens-ice-hockey` |
| Olympics Women's | `olympics-womens-ice-hockey` |

### Soccer (`soccer`) — 260+ leagues!
| League | Slug |
|--------|------|
| FIFA World Cup | `fifa.world` |
| UEFA Champions League | `uefa.champions` |
| English Premier League | `eng.1` |
| English Championship | `eng.2` |
| English League One | `eng.3` |
| English FA Cup | `eng.fa` |
| Spanish LALIGA | `esp.1` |
| German Bundesliga | `ger.1` |
| Italian Serie A | `ita.1` |
| French Ligue 1 | `fra.1` |
| Dutch Eredivisie | `ned.1` |
| Portuguese Liga | `por.1` |
| Belgian Pro League | `bel.1` |
| Turkish Super Lig | `tur.1` |
| Scottish Premiership | `sco.1` |
| MLS | `usa.1` |
| Liga MX | `mex.1` |
| Argentine Liga | `arg.1` |
| Brazilian Serie A | `bra.1` |
| Saudi Pro League | `ksa.1` |
| Japanese J.League | `jpn.1` |
| Australian A-League | `aus.1` |
| UEFA Europa League | `uefa.europa` |
| UEFA Conference League | `uefa.europa.conf` |
| CONMEBOL Libertadores | `conmebol.libertadores` |
| Africa Cup of Nations | `caf.nations` |

### Tennis (`tennis`)
| Tour | Slug |
|------|------|
| ATP | `atp` |
| WTA | `wta` |

### Volleyball (`volleyball`)
| League | Slug |
|--------|------|
| NCAA Men's | `mens-college-volleyball` |
| NCAA Women's | `womens-college-volleyball` |

### Golf (`golf`)
| Tour | Slug |
|------|------|
| PGA TOUR | `pga` |
| LPGA | `lpga` |
| DP World Tour | `eur` |
| LIV Golf | `liv` |
| Champions Tour | `champions-tour` |
| Korn Ferry Tour | `ntw` |
| TGL | `tgl` |

### Racing (`racing`)
| Series | Slug |
|--------|------|
| Formula 1 | `f1` |
| IndyCar | `irl` |
| NASCAR Cup | `nascar-premier` |
| NASCAR Xfinity | `nascar-secondary` |
| NASCAR Truck | `nascar-truck` |

### MMA (`mma`)
| Promotion | Slug |
|-----------|------|
| UFC | `ufc` |
| Bellator | `bellator` |
| LFA | `lfa` |
| KSW | `ksw` |
| (50+ more) | ... |

### Other Sports
| Sport | Slug | Leagues |
|-------|------|---------|
| Rugby Union | `rugby` | 24 leagues (numeric IDs) |
| Rugby League | `rugby-league` | NRL |
| Australian Football | `australian-football` | AFL |
| Cricket | `cricket` | ICC T20, ODI, IPL |
| Lacrosse | `lacrosse` | PLL, NLL, NCAA |
| Water Polo | `water-polo` | NCAA |
| Field Hockey | `field-hockey` | NCAA |

---

## 14. RESPONSE SCHEMAS (Key Structures)

### Scoreboard Event
```json
{
  "id": "401765432",
  "date": "2025-03-15T00:00Z",
  "name": "Boston Celtics at Golden State Warriors",
  "shortName": "BOS @ GSW",
  "status": { "type": { "name": "STATUS_FINAL", "state": "post", "completed": true } },
  "competitions": [{
    "venue": { "fullName": "Chase Center", "capacity": 18064 },
    "competitors": [{
      "homeAway": "home",
      "team": { "id": "9", "abbreviation": "GSW", "displayName": "Golden State Warriors" },
      "score": "121",
      "winner": true,
      "records": [{ "name": "overall", "summary": "42-24" }],
      "leaders": [{ "name": "points", "leaders": [{ "displayValue": "32", "athlete": { "displayName": "Stephen Curry" } }] }]
    }]
  }]
}
```

### Odds Response
```json
{
  "items": [{
    "provider": { "id": "41", "name": "DraftKings", "priority": 1 },
    "details": "-3.5",
    "overUnder": 222.5,
    "spread": -3.5,
    "overOdds": -110,
    "underOdds": -110,
    "awayTeamOdds": { "moneyLine": 140, "spreadOdds": -110, "favorite": false },
    "homeTeamOdds": { "moneyLine": -165, "spreadOdds": -110, "favorite": true },
    "open": { "over": { "value": 220.0 }, "spread": { "home": { "line": -4.5 } } }
  }]
}
```

### Athlete (Core v2)
```json
{
  "id": "3136776",
  "displayName": "Stephen Curry",
  "position": { "abbreviation": "SG" },
  "team": { "$ref": "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/teams/9" },
  "experience": { "years": 15 },
  "statistics": { "$ref": "..." }
}
```

### Standings Entry
```json
{
  "team": { "id": "2", "displayName": "Boston Celtics", "abbreviation": "BOS" },
  "stats": [
    { "name": "wins", "displayValue": "52" },
    { "name": "losses", "displayValue": "14" },
    { "name": "winPercent", "displayValue": ".788" },
    { "name": "gamesBehind", "displayValue": "-" },
    { "name": "streak", "displayValue": "W3" }
  ]
}
```

---

## 15. SPORT-SPECIFIC EXCEPTIONS & TIPS

| Sport | Exception |
|-------|-----------|
| Soccer | Scoreboard requires league slug (e.g. `eng.1`), not numeric ID |
| Soccer | Standings via core API: `sports.core.api.espn.com/v2/sports/soccer/leagues/{league}/standings` |
| Cricket | Scoreboard via core API only: `sports.core.api.espn.com/v2/sports/cricket/leagues/{league}/events` |
| Tennis | Scoreboard requires named slug (`atp`, `wta`) — numeric IDs return 400 |
| Tennis | Injuries endpoint returns **500** — not supported |
| Hockey (NHL) | Gamelog (`/athletes/{id}/gamelog`) returns **404** — use stats/splits instead |
| Golf/Tennis | Use slug-based league names, not numeric IDs |
| Rugby Union | Uses **numeric league IDs** (e.g. `180659` for Six Nations) |
| All Sports | Standings: use `/apis/v2/` NOT `/apis/site/v2/` (latter returns stub) |

---

## 16. DISCOVERY & META ENDPOINTS

```bash
# List ALL sports
curl "https://sports.core.api.espn.com/v2/sports"

# List ALL leagues (cross-sport)
curl "https://sports.core.api.espn.com/v2/ontology/leagues?limit=500"

# List ALL teams (cross-sport)
curl "https://sports.core.api.espn.com/v2/ontology/teams?limit=500"

# API documentation/listing
curl "https://sports.core.api.espn.com/v2/api-docs"

# WADL schema (full endpoint map)
curl "https://sports.core.api.espn.com/v2/application.wadl"
curl "https://sports.core.api.espn.com/v3/application.wadl"

# v3 list all sports
curl "https://sports.core.api.espn.com/v3/sports"

# v3 list all leagues
curl "https://sports.core.api.espn.com/v3/leagues?limit=500"

# v3 list all teams (cross-sport)
curl "https://sports.core.api.espn.com/v3/teams?limit=1000"
```

---

## 17. BETTING-PIPELINE-VALUABLE ENDPOINTS (Hidden Gems)

These are the endpoints most valuable for a sports betting pipeline that aren't commonly known:

| Endpoint | Value for Betting |
|----------|-------------------|
| `.../odds/{oddsProvider}/past-performances` | Historical team performance vs the line — ATS trending |
| `.../events/{id}/competitions/{id}/probabilities` | ESPN's live win probability model — compare to market |
| `.../events/{id}/competitions/{id}/predictor` | Pre-game prediction with % — implied probability |
| `.../seasons/{year}/powerindex` | BPI/SP+ rankings — model-based power ratings |
| `.../athletes/{id}/vsathlete/{opponentId}` | H2H stats (tennis especially!) |
| `.../teams/{id}/series/vs-opponent/{opponentId}` | Series history between two teams |
| `.../seasons/{year}/futures` | Championship/division futures odds |
| `.../seasons/{year}/types/{type}/teams/{id}/ats` | ATS record (against the spread) |
| `.../seasons/{year}/types/{type}/teams/{id}/odds-records` | Full O/U and spread record |
| `.../{oddId}/history/{betType}/movement` | **Line movement tracking** |
| `.../propBets` | Prop bet lines |
| `.../head-to-heads` | Head-to-head odds comparisons |
| `site.web.api.espn.com/.../athletes/{id}/splits` | Home/away splits for form analysis |
| `site.web.api.espn.com/.../athletes/{id}/overview` | Rotowire notes + injury status |
| `site.web.api.espn.com/.../statistics/byathlete` | Full stat leaderboard (sort by any stat) |
| `.../seasons/{year}/teams/{team}/projection` | Team season projections |
| `.../seasons/{year}/types/{type}/athletes/{athlete}/projections` | Player projected stats |
| `cdn.espn.com/core/{sport}/game?xhr=1&gameId={id}` | Complete game package with win probability curve |
| `https://sports.core.api.espn.com/v3/markets/{market}` | Bet market definitions |
| `https://sports.core.api.espn.com/v3/featured` | ESPN's featured/promoted bets |
| `.../seasons/{year}/talentpickers` | Expert pickers + their records |
| `.../talentpicks` | Expert picks for events |
| `.../zip/{zip}?date=...&hour=...` | Weather for outdoor game venues |
| `.../seasons/{year}/types/{type}/weeks/{week}/powerindex` | Weekly power ratings changes |

---

## 18. PAGINATION PATTERNS

### Core API v2 (collections)
```json
{
  "count": 1500,
  "pageIndex": 1,
  "pageSize": 25,
  "pageCount": 60,
  "items": [
    { "$ref": "https://sports.core.api.espn.com/v2/..." },
    ...
  ]
}
```
Navigate: `?page=2&limit=100`

### Site API v2
Most return full arrays without pagination. Use `?limit=1000` for large sets.

### Now API
```json
{
  "resultsCount": 1000,
  "resultsLimit": 20,
  "resultsOffset": 0,
  "feed": [...]
}
```
Navigate: `?offset=20&limit=20`

---

## 19. RATE LIMITING & BEST PRACTICES

- **No published rate limits** — but implement respectful delays (1-2s between requests)
- **Caching strongly recommended** — scoreboards update every ~15s during games
- **CDN endpoints** (`cdn.espn.com`) are optimized for high-frequency access
- **Core API** (`sports.core.api.espn.com`) likely has stricter limits — cache aggressively
- **Error codes**: 429 = rate limited, 404 = not found, 500 = server error
- **Retry strategy**: exponential backoff (1s, 2s, 4s) on 5xx errors
- **User-Agent**: set a reasonable UA string to avoid blocks

---

## 20. QUICK REFERENCE — MOST USEFUL CALLS

```bash
# Today's scoreboard (any sport)
curl "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"

# Specific date
curl "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates=20260522"

# Game odds
curl "https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{eventId}/competitions/{eventId}/odds"

# Game summary (everything in one call)
curl "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary?event={eventId}"

# Full game package (CDN — most data in one call)
curl "https://cdn.espn.com/core/{sport}/game?xhr=1&gameId={eventId}"

# Team injuries
curl "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{teamId}/injuries"

# Standings
curl "https://site.api.espn.com/apis/v2/sports/{sport}/{league}/standings"

# Player stats + rotowire
curl "https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{id}/overview"
```
