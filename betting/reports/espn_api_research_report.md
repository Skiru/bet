# ESPN Public API — Complete Research Report

**Date:** 2026-05-07  
**Source:** https://github.com/pseudo-r/Public-ESPN-API  
**Scope:** 17 sports · 139 leagues · 370 v2 endpoints · 79 v3 endpoints · 6 API domains

---

## 1. FULL ENDPOINT CATALOG

### 1.1 Base URLs (All Verified Working)

| Domain | Purpose |
|--------|---------|
| `site.api.espn.com/apis/site/v2/` | Scoreboard, teams, news, injuries, transactions, summary |
| `site.api.espn.com/apis/v2/` | **Standings** (site/v2 returns stub) |
| `site.web.api.espn.com/apis/common/v3/` | Athlete stats, gamelog, overview, splits, leaderboards |
| `sports.core.api.espn.com/v2/` | Core data — events, odds, play-by-play, athletes, coaches |
| `sports.core.api.espn.com/v3/` | Enriched athletes, leaders, betting data |
| `cdn.espn.com/core/` | Full game packages (requires `?xhr=1`) |
| `now.core.api.espn.com/v1/` | Real-time news feed |

### 1.2 Site API v2 — Universal Resources

```
GET https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/{resource}
```

| Resource | Description | Betting Value |
|----------|-------------|---------------|
| `scoreboard` | Live & scheduled events with scores | ⭐⭐⭐ Fixture discovery |
| `scoreboard?dates={YYYYMMDD}` | Date-filtered scores | ⭐⭐⭐ Historical results |
| `teams` | All teams in league | ⭐⭐ Team ID mapping |
| `teams/{id}` | Single team detail | ⭐⭐ |
| `teams/{id}/roster` | Full squad with positions, age, height, weight | ⭐⭐⭐ Roster stability |
| `teams/{id}/schedule` | Team schedule (past + future) | ⭐⭐⭐ Form analysis (L10) |
| `teams/{id}/record` | Team record (W-L) | ⭐⭐ |
| `teams/{id}/injuries` | Current injury report | ⭐⭐⭐ Key player availability |
| `teams/{id}/depthcharts` | Depth chart by position | ⭐⭐ Lineup prediction |
| `teams/{id}/transactions` | Recent moves/trades | ⭐⭐ Roster changes |
| `teams/{id}/history` | Franchise historical record | ⭐ |
| `teams/{id}/leaders` | Team statistical leaders | ⭐⭐⭐ Top performers |
| `teams/{id}/news` | Team news | ⭐ |
| `athletes/{id}` | Athlete profile | ⭐⭐ |
| `athletes/{id}/gamelog` | Game-by-game log | ⭐⭐⭐ Player form |
| `athletes/{id}/splits` | Statistical splits (home/away) | ⭐⭐⭐ Split analysis |
| `athletes/{id}/news` | Player news | ⭐ |
| `athletes/{id}/bio` | Player bio | ⭐ |
| `injuries` | **League-wide** injury report | ⭐⭐⭐ Mass injury scan |
| `transactions` | Recent signings/trades/waivers | ⭐⭐ Roster changes |
| `standings` | League standings (use `/apis/v2/` path!) | ⭐⭐⭐ League table |
| `groups` | Conferences/divisions | ⭐⭐ |
| `news` | Latest news articles | ⭐ |
| `rankings` | Rankings (college sports) | ⭐⭐ |
| `calendar` | Season calendar | ⭐ |
| `summary?event={id}` | Full game summary (boxscore + plays) | ⭐⭐⭐ Match stats |
| `statistics` | League statistical leaders | ⭐⭐⭐ |

### 1.3 Core API v2 — Deep Data

```
GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/{resource}
```

| Resource | Description | Betting Value |
|----------|-------------|---------------|
| `athletes` | Full athlete list (paginated) | ⭐⭐ |
| `athletes/{id}` | Detailed athlete profile | ⭐⭐ |
| `athletes/{id}/statistics` | Career stats | ⭐⭐⭐ |
| `athletes/{id}/statisticslog` | Game-by-game stat log | ⭐⭐⭐ Player form |
| `athletes/{id}/eventlog` | Event history | ⭐⭐ |
| `athletes/{id}/contracts` | Contract info | ⭐ |
| `athletes/{id}/awards` | Awards | ⭐ |
| `athletes/{id}/seasons` | Seasons played | ⭐ |
| `athletes/{id}/records` | Career records | ⭐ |
| `athletes/{id}/injuries` | Injury history | ⭐⭐⭐ |
| `athletes/{id}/vsathlete/{opponentId}` | **HEAD-TO-HEAD STATS** | ⭐⭐⭐⭐ H2H |
| `events` | Full event list | ⭐⭐⭐ |
| `events/{id}/competitions/{id}/odds` | **BETTING ODDS** (multiple providers) | ⭐⭐⭐⭐ |
| `events/{id}/competitions/{id}/probabilities` | Win probabilities | ⭐⭐⭐ |
| `events/{id}/competitions/{id}/plays` | Play-by-play | ⭐⭐⭐ In-game stats |
| `events/{id}/competitions/{id}/situation` | Current game situation | ⭐⭐ Live |
| `events/{id}/competitions/{id}/predictor` | ESPN game predictor | ⭐⭐⭐ Projections |
| `events/{id}/competitions/{id}/powerindex` | ESPN Power Index for game | ⭐⭐⭐ |
| `events/{id}/competitions/{id}/competitors/{id}/statistics` | Competitor stats | ⭐⭐⭐ |
| `events/{id}/competitions/{id}/competitors/{id}/linescores` | Period-by-period | ⭐⭐⭐ |
| `seasons/{year}/teams` | Teams in season | ⭐⭐ |
| `seasons/{year}/coaches` | Coaching staff | ⭐⭐ Coach stability |
| `seasons/{year}/futures` | **FUTURES ODDS** | ⭐⭐⭐ |
| `seasons/{year}/powerindex` | Season Power Index / BPI | ⭐⭐⭐ |
| `seasons/{year}/types/{type}/teams/{id}/ats` | **ATS RECORDS** | ⭐⭐⭐⭐ |
| `seasons/{year}/types/{type}/teams/{id}/odds-records` | **Team odds records** | ⭐⭐⭐⭐ |
| `standings` | Full standings | ⭐⭐⭐ |
| `teams` | Detailed teams | ⭐⭐ |
| `leaders` | Statistical leaders | ⭐⭐⭐ |
| `rankings` | Rankings | ⭐⭐ |
| `coaches/{id}` | Coach profile | ⭐⭐ |
| `coaches/{id}/record/{type}` | Coaching record | ⭐⭐ |

### 1.4 Athlete Data (site.web.api.espn.com)

```
GET https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{id}/{resource}
```

| Resource | Works For | Betting Value |
|----------|-----------|---------------|
| `overview` | NFL, NBA, NHL, MLB, Soccer(limited) | ⭐⭐⭐ Quick stats + rotowire |
| `stats` | NFL, NBA, NHL, MLB | ⭐⭐⭐ Season stats |
| `gamelog` | NFL, NBA, MLB | ⭐⭐⭐⭐ Game-by-game form |
| `splits` | NFL, NBA, NHL, MLB | ⭐⭐⭐⭐ Home/Away splits |

```
GET https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/statistics/byathlete
```
- **Stats leaderboard** with `category=` + `sort=` — ranks all athletes | ⭐⭐⭐

### 1.5 Betting & Odds Endpoints

| Endpoint | Description |
|----------|-------------|
| `events/{id}/competitions/{id}/odds` | Game odds (spread, ML, O/U from multiple providers) |
| `events/{id}/competitions/{id}/probabilities` | Win probability (live + pregame) |
| `events/{id}/competitions/{id}/predictor` | ESPN game predictor |
| `seasons/{year}/futures` | Season futures |
| `seasons/{year}/types/{type}/teams/{id}/ats` | Against-the-spread records |
| `seasons/{year}/types/{type}/teams/{id}/odds-records` | Team O/U and spread records |
| `v3/odds` | Global odds endpoint |
| `v3/predictions` | Predictions |
| `v3/featured` | Featured bets |
| `v3/trending` | Trending bets |
| `v3/markets/{market}` | Bet market details |
| `v3/promotions` | Bet promotions |

**Betting Provider IDs:** Caesars (38), FanDuel (37), DraftKings (41), BetMGM (58), ESPN BET (68), Bet365 (2000)

### 1.6 CDN Game Packages

```
GET https://cdn.espn.com/core/{sport}/game?xhr=1&gameId={id}
```

Returns `gamepackageJSON` with: boxscore, drives, play-by-play, win probability, scoring, odds, matchup data.

Available views: `game`, `boxscore`, `playbyplay`, `matchup`, `scoreboard`

### 1.7 Real-Time News

```
GET https://now.core.api.espn.com/v1/sports/news?sport={sport}&limit={n}
```

Filters: `sport=`, `leagues=`, `team=`

---

## 2. SPORT COVERAGE MATRIX

### 2.1 Sports & League Slugs

| Sport | Slug | Key Leagues | # Leagues |
|-------|------|-------------|-----------|
| ⚽ Soccer | `soccer` | `eng.1`, `esp.1`, `ger.1`, `ita.1`, `fra.1`, `uefa.champions`, `usa.1` + 260+ more | 260+ |
| 🏀 Basketball | `basketball` | `nba`, `wnba`, `nba-development`, `mens-college-basketball`, `fiba`, `nbl` | 15 |
| 🏈 Football | `football` | `nfl`, `college-football`, `cfl`, `ufl`, `xfl` | 5 |
| ⚾ Baseball | `baseball` | `mlb`, `college-baseball`, `world-baseball-classic` | 13 |
| 🏒 Hockey | `hockey` | `nhl`, `mens-college-hockey`, `womens-college-hockey` | 6 |
| 🎾 Tennis | `tennis` | `atp`, `wta` | 2 |
| ⛳ Golf | `golf` | `pga`, `lpga`, `eur`, `liv`, `champions-tour` | 9 |
| 🏎️ Racing | `racing` | `f1`, `irl`, `nascar-premier` | 5 |
| 🥊 MMA | `mma` | `ufc`, `bellator`, `ksw`, `cage-warriors` + 50+ | 50+ |
| 🏉 Rugby Union | `rugby` | `world-cup`, `six-nations`, `super-rugby`, `premiership` | 24 |
| 🏉 Rugby League | `rugby-league` | `nrl`, `super-league` | 1+ |
| 🏐 Volleyball | `volleyball` | `mens-college-volleyball`, `womens-college-volleyball` | 2 |
| 🏏 Cricket | `cricket` | ICC T20, ICC ODI, IPL | varies |
| 🥍 Lacrosse | `lacrosse` | PLL, NLL, NCAA | 4 |
| 🏑 Field Hockey | `field-hockey` | FIH | 1 |
| 🤽 Water Polo | `water-polo` | FINA, NCAA | 2 |
| 🦘 Australian Football | `australian-football` | AFL | 1 |

### 2.2 Endpoint Availability Matrix

| Endpoint | Soccer | Basketball | Hockey | Baseball | Tennis | MMA | Rugby | Volleyball | Cricket | Golf |
|----------|--------|-----------|--------|----------|--------|-----|-------|-----------|---------|------|
| Scoreboard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️core | ✅ |
| Teams | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Roster | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| Injuries | ✅ | ✅ | ✅ | ✅ | ❌(500) | ❌(500) | ⚠️ | ⚠️ | ⚠️ | ❌ |
| Schedule | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Standings | ✅(/apis/v2/) | ✅ | ✅ | ✅ | ❌ | ❌ | ✅(core) | ✅ | ⚠️ | ❌ |
| Summary | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Odds | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Play-by-play | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| Athlete stats | ⚠️(core) | ✅(full) | ✅ | ✅(full) | ⚠️(core) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| Athlete gamelog | ❌ | ✅ | ❌(404) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Athlete splits | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Win probability | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ❌ |
| CDN game pkg | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Leaders | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Rankings | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ⚠️ | ✅ |
| Transactions | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| H2H (vsathlete) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| ATS records | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Power Index | ❌ | ✅(BPI) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 3. STATISTICAL DEPTH PER SPORT

### 3.1 Soccer (Football)

**Available from `summary?event={id}`:**
- Goals, assists, cards (yellow/red), substitutions
- Possession %, shots, shots on target, corners, fouls, offsides
- Saves, passes, tackles
- Per-player: minutes, goals, assists, shots, tackles, interceptions, key passes

**Available from Core API:**
- Team standings: points, GD, form, W/D/L home/away
- Leaders: top scorers, assists
- Play-by-play: goals, cards, subs with timestamps

**NOT available:** Advanced xG, xA, PPDA, pressing stats (use FBref/Understat for these)

### 3.2 Basketball (NBA/WNBA)

**Available from `athletes/{id}/stats` + `gamelog`:**
- GP, GS, MIN, PTS, REB, AST, STL, BLK, TO, FG%, 3P%, FT%
- Per-game and totals
- Home/Away splits
- Game-by-game log with opponent and result

**Available from summary/boxscore:**
- Per-player: MIN, FG, 3PT, FT, OREB, DREB, REB, AST, STL, BLK, TO, PF, +/-, PTS
- Team: FG%, 3P%, FT%, turnovers, rebounds, fast break pts, pts in paint, bench pts

**Special:** BPI (Basketball Power Index), ATS records, O/U records

### 3.3 Hockey (NHL)

**Available from `athletes/{id}/stats` + `splits`:**
- G, A, P, +/-, PIM, PPG, PPA, SHG, GWG, SOG, S%
- Home/Away splits
- Goalie: W, L, OTL, SV, SV%, GAA, SO

**Available from summary:**
- SOG, hits, blocks, faceoff %, power play, penalty kill
- Per-period scoring

### 3.4 Baseball (MLB)

**Available from `athletes/{id}/stats` + `gamelog`:**
- Batting: AVG, OBP, SLG, OPS, HR, RBI, R, SB, BB, SO, H, 2B, 3B
- Pitching: W, L, ERA, WHIP, K, BB, IP, H, HR, SV, HLD
- Full game-by-game logs
- Category-filtered leaderboards (`category=batting&sort=batting.homeRuns:desc`)

**Special:** ATS records, hot zones (strike zone performance)

### 3.5 Tennis (ATP/WTA)

**Available from scoreboard/summary:**
- Match results (sets, games per set)
- Tournament bracket/draw
- Rankings (ATP/WTA world ranking)
- Odds per match

**NOT available:** Aces, double faults, break points, serve %, first serve won % (use official ATP/WTA stats for these)

**Limitation:** No `injuries` endpoint (returns 500), no gamelog/splits via common/v3

### 3.6 MMA (UFC + 50+ promotions)

**Available:**
- Event cards (fighters, bouts)
- Fighter profiles
- Rankings
- Odds per bout

**NOT available:** Detailed fight stats (significant strikes, takedowns, submission attempts)

### 3.7 Volleyball

**Available:**
- Scoreboard (FIVB Men/Women + NCAA)
- Teams, roster, schedule
- Odds per match
- Rankings

**Note:** Only NCAA and FIVB leagues documented. No PlusLiga, Serie A1, etc.

### 3.8 Cricket

**Available:**
- Events via core API
- Teams, athletes, odds
- Multiple formats (T20, ODI, Test)

**Limitation:** No league slugs documented — requires discovery

---

## 4. GAP ANALYSIS — What the Project is NOT Using

### 4.1 Endpoints NOT Currently Used (HIGH VALUE)

| Endpoint | What It Provides | Priority |
|----------|-----------------|----------|
| `athletes/{id}/vsathlete/{opponentId}` | **H2H stats between players** | 🔴 CRITICAL |
| `events/{id}/competitions/{id}/odds` | **Multi-provider odds from ESPN** (DraftKings, FanDuel, Bet365) | 🔴 CRITICAL |
| `events/{id}/competitions/{id}/probabilities` | Win probability (ESPN's model) | 🔴 HIGH |
| `events/{id}/competitions/{id}/predictor` | ESPN game predictor | 🟡 HIGH |
| `seasons/{year}/types/{type}/teams/{id}/ats` | Against-the-spread records | 🔴 CRITICAL |
| `seasons/{year}/types/{type}/teams/{id}/odds-records` | Team O/U records | 🔴 CRITICAL |
| `teams/{id}/roster` | Full roster (age, height, weight, status) | 🟡 HIGH |
| `teams/{id}/depthcharts` | Starting lineup indication | 🟡 HIGH |
| `athletes/{id}/gamelog` | Player game-by-game form | 🔴 CRITICAL |
| `athletes/{id}/splits` | Home/Away performance splits | 🔴 CRITICAL |
| `statistics/byathlete` | League-wide stat rankings | 🟡 HIGH |
| `seasons/{year}/coaches` | Coach data | 🟡 MEDIUM |
| `seasons/{year}/futures` | Futures odds | 🟡 MEDIUM |
| `seasons/{year}/powerindex` | Power ratings | 🟡 HIGH |
| `transactions` | Roster moves, signings, trades | 🟡 MEDIUM |
| `v3/predictions` | ESPN predictions | 🟡 HIGH |
| `standings` (via `/apis/v2/`) | Full standings with form, GD, etc. | 🟡 HIGH |
| CDN game package | Full matchup data | 🟡 MEDIUM |

### 4.2 Sports NOT Currently Integrated That ESPN Covers

| Sport | ESPN Coverage | Betting Relevance |
|-------|-------------|-------------------|
| 🏐 Volleyball (FIVB) | Scoreboard, odds, teams | ⭐⭐⭐ Currently bet on |
| 🏏 Cricket | Events, odds, teams | ⭐⭐ Popular betting sport |
| 🏉 Rugby Union | 24 leagues, scores, odds, standings | ⭐⭐⭐ Popular betting sport |
| 🏉 Rugby League | NRL scoreboard, odds | ⭐⭐ |
| 🏎️ Racing (F1) | Events, drivers, constructors | ⭐⭐ |
| ⛳ Golf | Leaderboard, odds, rankings | ⭐⭐ |
| 🥍 Lacrosse | Scores, teams | ⭐ Niche |
| 🦘 AFL | Scores, teams, odds | ⭐⭐ |

### 4.3 Soccer League Coverage Gap

The project currently maps a limited set of soccer leagues. ESPN covers **260+ soccer leagues** including:

**Missing from scan_urls.json that ESPN supports:**
- 🇳🇱 Eredivisie (`ned.1`), 🇧🇪 Belgian Pro League (`bel.1`)
- 🇦🇹 Austrian Bundesliga (`aut.1`), 🇨🇭 Swiss Super League (`sui.1`)
- 🇹🇷 Turkish Süper Lig (`tur.1`), 🇬🇷 Greek Super League (`gre.1`)
- 🇷🇺 Russian Premier League (`rus.1`)
- 🇺🇸 MLS (`usa.1`), 🇲🇽 Liga MX (`mex.1`)
- 🇧🇷 Brasileirão (`bra.1`), 🇦🇷 Argentine Liga (`arg.1`)
- 🇯🇵 J-League (`jpn.1`), 🇰🇷 K-League (`kor.1`)
- 🇦🇺 A-League (`aus.1`)
- All women's leagues, youth tournaments, club friendlies

---

## 5. PRIORITY RECOMMENDATIONS

### 🔴 PRIORITY 1 — Immediate Integration (Biggest Betting Value)

#### A. ESPN Odds Endpoint
```
GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/odds
```
- Returns **multi-provider odds** (DraftKings, FanDuel, BetMGM, Bet365, ESPN BET)
- Includes: spread, moneyline, over/under, opening lines
- **FREE, no API key needed, no rate limit published**
- Covers: Soccer, Basketball, Hockey, Baseball, Tennis, MMA, Rugby, Volleyball
- This is potentially more valuable than the-odds-api.com for European sports

#### B. ATS & O/U Records per Team
```
GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/types/{type}/teams/{id}/ats
GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/types/{type}/teams/{id}/odds-records
```
- Team's historical cover rate (ATS)
- Team's over/under record
- Critical for totals markets

#### C. Player Game Logs & Splits
```
GET https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{id}/gamelog
GET https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{id}/splits
```
- Game-by-game stats for L5/L10 analysis
- Home/Away splits for statistical markets
- Works for: NBA, NFL, MLB, NHL(splits only)

#### D. H2H Endpoint
```
GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/athletes/{id}/vsathlete/{opponentId}
```
- Direct head-to-head statistics
- Critical for tennis, MMA, team matchup analysis

### 🟡 PRIORITY 2 — High Value Enhancement

#### E. Win Probabilities & Predictor
```
GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/probabilities
GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/predictor
```
- ESPN's own win probability model
- Can be used as cross-validation for EV calculations

#### F. Full Standings (with form data)
```
GET https://site.api.espn.com/apis/v2/sports/soccer/{league}/standings
```
- Returns: points, GD, form string, W/D/L home/away
- Much richer than basic scoreboard data

#### G. Statistical Leaders
```
GET https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/statistics/byathlete?category={cat}&sort={field}:desc
```
- Rank all players by any stat category
- Useful for prop bets, anytime scorer markets

#### H. Power Index
```
GET https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/powerindex
```
- ESPN's team power ratings
- Available for basketball (BPI), football (SP+)

### 🟢 PRIORITY 3 — Nice to Have

#### I. Roster & Depth Charts
- Detect rotation, starting lineup changes
- Identify key player injuries early

#### J. Transactions Feed
- Detect recent trades, signings affecting team strength

#### K. Volleyball FIVB Integration
- Scoreboard via: `site.api.espn.com/apis/site/v2/sports/volleyball/fivb.m/scoreboard`
- Odds available per competition

#### L. Rugby & Cricket Integration
- Both have full endpoint support
- Both are popular betting sports

---

## 6. RESPONSE STRUCTURE — Key Fields

### Odds Response
```json
{
  "items": [{
    "provider": {"id": "41", "name": "DraftKings"},
    "spread": -3.5,
    "overUnder": 222.5,
    "overOdds": -110,
    "underOdds": -110,
    "awayTeamOdds": {"moneyLine": 140, "spreadOdds": -110},
    "homeTeamOdds": {"moneyLine": -165, "spreadOdds": -110},
    "open": {"over": {"value": 220.0}, "spread": {"home": {"line": -4.5}}}
  }]
}
```

### Athlete Gamelog Response
```json
{
  "labels": ["DATE", "OPP", "RESULT", "MIN", "FG", "3PT", "FT", "REB", "AST", "STL", "BLK", "PTS"],
  "events": [{
    "id": "401765000",
    "date": "2025-03-14T00:00Z",
    "opponent": {"id": "2", "displayName": "Boston Celtics"},
    "gameResult": "W",
    "stats": ["36", "12-24", "4-10", "4-4", "5", "7", "1", "0", "32"]
  }]
}
```

### Standings Response
```json
{
  "children": [{
    "name": "Eastern Conference",
    "standings": {"entries": [{
      "team": {"id": "2", "displayName": "Boston Celtics"},
      "stats": [
        {"name": "wins", "displayValue": "52"},
        {"name": "losses", "displayValue": "14"},
        {"name": "winPercent", "displayValue": ".788"},
        {"name": "streak", "displayValue": "W3"}
      ]
    }]}
  }]
}
```

---

## 7. QUERY PARAMETERS REFERENCE

| Parameter | Description | Example |
|-----------|-------------|---------|
| `dates` | Filter by date | `20260507` or `20260501-20260507` |
| `week` | Week number | `1` through `18` |
| `seasontype` | 1=pre, 2=regular, 3=post, 4=off | `2` |
| `season` | Year | `2026` |
| `limit` | Results per page | `100` |
| `page` | Pagination | `1` |
| `enable` | Expand inline | `roster`, `stats`, `injuries`, `projection` |
| `provider.priority` | Odds provider filter | `1` (primary) |
| `lang` | Language | `en`, `es` |
| `active` | Active filter | `true` |
| `sort` | Sort field | `batting.homeRuns:desc` |
| `category` | Stat category | `batting`, `pitching`, `general` |

---

## 8. SOCCER LEAGUE SLUGS (Complete List for Integration)

### Top European Leagues
| Country | Div | Slug |
|---------|-----|------|
| 🏴 England | 1 | `eng.1` |
| 🏴 England | 2 | `eng.2` |
| 🏴 England | 3 | `eng.3` |
| 🇪🇸 Spain | 1 | `esp.1` |
| 🇪🇸 Spain | 2 | `esp.2` |
| 🇩🇪 Germany | 1 | `ger.1` |
| 🇩🇪 Germany | 2 | `ger.2` |
| 🇮🇹 Italy | 1 | `ita.1` |
| 🇮🇹 Italy | 2 | `ita.2` |
| 🇫🇷 France | 1 | `fra.1` |
| 🇫🇷 France | 2 | `fra.2` |
| 🇳🇱 Netherlands | 1 | `ned.1` |
| 🇳🇱 Netherlands | 2 | `ned.2` |
| 🏴 Scotland | 1 | `sco.1` |
| 🇵🇹 Portugal | 1 | `por.1` |
| 🇧🇪 Belgium | 1 | `bel.1` |
| 🇹🇷 Turkey | 1 | `tur.1` |
| 🇬🇷 Greece | 1 | `gre.1` |
| 🇦🇹 Austria | 1 | `aut.1` |
| 🇨🇭 Switzerland | 1 | `sui.1` |
| 🇷🇺 Russia | 1 | `rus.1` |
| 🇺🇦 Ukraine | 1 | `ukr.1` |
| 🇵🇱 Poland | 1 | `pol.1` |
| 🇩🇰 Denmark | 1 | `den.1` |
| 🇸🇪 Sweden | 1 | `swe.1` |
| 🇳🇴 Norway | 1 | `nor.1` |

### European Cups
| Competition | Slug |
|------------|------|
| Champions League | `uefa.champions` |
| Europa League | `uefa.europa` |
| Conference League | `uefa.europa.conf` |
| Nations League | `uefa.nations` |
| Euro Championship | `uefa.euro` |

### Americas
| Competition | Slug |
|------------|------|
| MLS | `usa.1` |
| Liga MX | `mex.1` |
| Copa Libertadores | `conmebol.libertadores` |
| Copa Sudamericana | `conmebol.sudamericana` |
| Brasileirão | `bra.1` |
| Argentine Liga | `arg.1` |

### Asia/Oceania
| Competition | Slug |
|------------|------|
| J-League | `jpn.1` |
| K-League | `kor.1` |
| A-League | `aus.1` |
| Saudi Pro League | `ksa.1` |
| AFC Champions League | `afc.champions` |

---

## 9. IMPLEMENTATION NOTES

### Key Differences from the-odds-api.com
- **ESPN odds are FREE** — no API key, no credit limits
- **Opening lines included** — can calculate line movement
- **Multiple providers** — DraftKings, FanDuel, BetMGM, Bet365, ESPN BET
- **Covers more sports** — MMA, Rugby, Volleyball odds available
- **No rate limit documented** — but be respectful (cache responses)

### Caveats
- Undocumented API — may change without notice
- Soccer player stats via common/v3 are **limited** (overview only, no gamelog/splits)
- Tennis/MMA injuries return 500
- Volleyball only covers NCAA + FIVB (not PlusLiga, Serie A1, etc.)
- No handball, snooker, darts, table tennis, esports, padel, speedway coverage

### Recommended Integration Pattern
1. **Discovery:** Use scoreboard to find today's events → get event IDs
2. **Odds:** Use core API odds endpoint with event ID → multi-provider odds
3. **Stats:** Use athlete gamelog/splits for L5/L10 form analysis
4. **Form:** Use team schedule (past results) for team form
5. **Context:** Use injuries + transactions for availability data
6. **Validation:** Use ESPN predictor/probabilities as cross-check

---

## 10. SPORTS NOT COVERED BY ESPN API

The following sports in the betting pipeline have **NO ESPN coverage:**
- 🤾 Handball
- 🎱 Snooker
- 🎯 Darts
- 🏓 Table Tennis
- 🎮 Esports (CS2, LoL, Dota)
- 🏸 Padel
- 🏍️ Speedway

These must continue using existing specialized sources (Flashscore, HLTV, PaddleStat, etc.)
