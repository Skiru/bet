# Betting System Complete Rewrite — Research Report

## Task Details

| Field | Value |
|---|---|
| Title | Complete Rewrite of Betting Analysis & Coupon Generation System |
| Priority | High |
| Created Date | 2026-05-03 |
| Scope | Full system redesign: architecture, data layer, analysis pipeline, coupon generation |
| Bankroll | 47 PLN (~$12 USD) |
| Execution Bookmaker | Betclic (no API, user verifies on app) |
| Focus Sports | Football, Volleyball, Basketball, Hockey, Tennis, Snooker, Speedway |
| Timezone | Europe/Warsaw |

## Business Impact

The current system has produced **153 coupons with 489 legs** since April 21, 2026, achieving a **27.5% hit rate** and **-17.6% ROI** (total PnL: -77.35 PLN). The negative ROI demonstrates the system is not producing consistently winning coupons. A rewrite must address the fundamental analytical and architectural shortcomings while preserving the empirical learnings about which markets actually win.

The system's core value proposition — **statistical market betting** (corners, fouls, cards, totals) rather than outcome betting (match winners) — is validated by the data: statistical markets hit at 63% vs outcome markets at 45%. The winning markets (team_corners 87%, frame_totals 100%, cards 75%, UNDER picks 74%) provide a clear foundation for the new system's focus.

---

## 1. Proven Betting Approaches & Strategies

### 1.1 Value Betting Methodology

**Core principle**: A bet has positive expected value (EV) when the true probability of an outcome exceeds the implied probability from the bookmaker's odds.

$$EV = (probability \times odds) - 1$$

A bet is +EV when $EV > 0$, i.e., when $probability \times odds > 1$.

**Edge identification for statistical markets:**
- Statistical markets (corners, fouls, cards, shots totals) are priced using less sophisticated models by bookmakers than headline markets (match winner, goals totals)
- Bookmakers allocate their best pricing analysts to high-liquidity markets; statistical markets often have wider margins but also more mispricing
- Historical hit rates from L10/L5 form provide empirical probability estimates that can be compared against implied odds

**Minimum acceptable odds formula** (from user's STATS-FIRST mode):
$$odds_{min} = \frac{1}{hit\_rate}$$

Example: If team corners O3.5 hits in 8 of 10 matches (80%), minimum acceptable odds = 1.25.

### 1.2 Kelly Criterion for Small Bankrolls

The Kelly Criterion determines optimal stake sizing:

$$f^* = \frac{bp - q}{b}$$

Where $b$ = decimal odds - 1, $p$ = estimated win probability, $q$ = 1 - p.

**For small bankrolls (47 PLN), use fractional Kelly (1/4 Kelly)**:
- Full Kelly is too aggressive for small bankrolls — a single losing streak can wipe out the entire roll
- 1/4 Kelly provides ~75% of the long-run growth rate with dramatically lower variance
- With 47 PLN bankroll and 1/4 Kelly, typical stakes should be 0.50-3.00 PLN per bet

**Practical stake ranges derived from current config:**
- Low-risk coupon max: 3.00 PLN
- Higher-risk coupon max: 2.00 PLN
- Daily exposure range: 5.00-15.00 PLN

### 1.3 What Makes Coupons Win? (Accumulator Theory)

**Key findings from Betclic history analysis:**

| Coupon Type | Record | Win Rate | Verdict |
|---|---|---|---|
| AKO (2-3 legs) | Positive | ~35% | Viable — the sweet spot |
| AKO (4 legs) | Mixed | ~15% | Marginal — only with high-safety picks |
| AKO (5 legs) | 0 wins / 14 attempts | 0% | **STOP** |
| AKO (7 legs) | 0 wins / 6 attempts | 0% | **STOP** |
| Singles | Limited data | ~55% | Best hit rate but low payout |

**Principles for winning coupons:**

1. **Independence**: Legs must be statistically independent — different events, different sports, different leagues. Correlated legs (e.g., two EPL matches) reduce effective diversification.

2. **Fewer legs, higher conviction**: Each additional leg multiplies the failure probability. A 3-leg coupon with 70% per-leg hit rate has a 34.3% coupon win rate. A 5-leg coupon with the same per-leg rate drops to 16.8%.

3. **Statistical markets > outcome markets**: Corners, fouls, cards, shots accumulate throughout a match and are driven by team *style*, not individual moments of luck. A defensive team consistently concedes corners regardless of the score.

4. **UNDER bias**: The current system's UNDER picks hit at 74%. UNDER markets benefit from the "regression to mean" effect — extreme stat games are rarer than moderate ones. Bookmakers tend to set lines that attract OVER bets (more exciting), creating systematic UNDER value.

5. **Line precision matters**: The difference between O9.5 and O10.5 corners is not linear — it can be the difference between 70% and 50% hit rate. The new system must calculate hit rates for multiple lines and select the one with the best safety-to-odds ratio.

### 1.4 Small Bankroll Strategies

With 47 PLN, the approach must be:

1. **Survival first**: Never risk more than 5% of bankroll on a single coupon (max 2.35 PLN per coupon). Current config allows up to 3.00 PLN which is 6.4% — slightly aggressive.

2. **Flat staking over Kelly for tiny bankrolls**: With bankrolls under 100 PLN, the granularity of Kelly sizing becomes meaningless (0.50 PLN differences). A flat 1-2 PLN per coupon with 2-3 leg accumulators is more practical.

3. **Compound slowly**: Target 5-10% weekly growth. At 47 PLN, a winning week adds 2.35-4.70 PLN. Compounding requires discipline and accurate record-keeping.

4. **Multi-coupon diversification**: Instead of one 5-leg coupon, place three 2-leg coupons. Total risk is higher but expected return is dramatically better due to independence.

### 1.5 Which Statistical Markets Are Most Profitable?

**Empirical data from 489 legs on Betclic:**

| Market | Legs | Hit Rate | Assessment |
|---|---|---|---|
| Team Corners O/U | 15 | **87%** | Core market — highest edge |
| Frame Totals (Snooker) | 11 | **100%** | Perfect record — small sample but promising |
| Cards O/U | 12 | **75%** | Strong performer |
| Snooker (all markets) | 15 | **80%** | Sport-level edge |
| UNDER direction (all) | ~200 | **74%** | Systematic directional edge |
| Statistical markets (all) | ~310 | **63%** | Class-level edge over outcomes |
| Outcome markets (all) | ~180 | **45%** | Below breakeven |
| Runs Totals (Baseball) | 11 | 27% | Avoid |

**Why statistical markets outperform:**
- **Style-driven**: Team style (pressing, possession, direct play) is more persistent than match outcomes
- **Accumulative**: Stats accumulate regardless of game state (a team losing 3-0 still commits fouls)
- **Less sharp pricing**: Bookmakers invest less modeling effort into niche statistical markets
- **Lower public interest**: Recreational bettors don't bet on "Fouls O22.5", leaving these markets less efficient

### 1.6 How Professional Bettors Build Their Edge

1. **Specialization**: Pros focus on 1-3 sports and specific market types. The new system should treat the 7 sports as the maximum scope, not the minimum.

2. **Closing Line Value (CLV)**: The single best predictor of long-term profitability. If you consistently bet at odds higher than the closing line, you're a winning bettor — regardless of short-term results.

3. **Database-driven decisions**: Pros maintain databases of team-specific stat profiles, not just "last 10 average." They track distributions, standard deviations, home/away splits, and situational adjustments.

4. **Line shopping**: Even 2-3% better odds compound dramatically over hundreds of bets. With Betclic as the sole execution bookmaker, the system's edge must come from superior probability estimation rather than price arbitrage.

5. **Record-keeping and feedback loops**: Every bet is logged, every result is analyzed, and the model is updated. The current system has this with `picks-ledger.csv` and `betclic_bets_history.json` — this must be preserved and enhanced.

---

## 2. Available Data Sources & APIs Per Sport

### 2.1 Football

| Source | Type | Cost | Data Available | Limitations |
|---|---|---|---|---|
| **API-Football v3** (api-sports.io) | REST API | Free: 100 req/day | Corners, fouls, cards, shots, SOT, possession per match. 1000+ leagues. H2H. Standings. | 100 req/day shared across all endpoints |
| **Football-Data.org** | REST API | Free: 10 req/min | Fixtures, results, standings for 12 EU leagues | No per-match corner/foul/card stats |
| **Understat** | Python pkg | Free | xG, xGA, npxG, PPDA for top 6 EU leagues | Only EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL |
| **FBref** | Web scraping | Free | Comprehensive per-match stats, advanced metrics | Scraping required, rate-limited |
| **SoccerStats.com** | Web scraping | Free | League corner averages, team defensive profiles, home/away splits | Good for league-level aggregates |
| **TotalCorner.com** | Web scraping | Free | Corner predictions, O/U lines, team corner form | Specialist source for corner markets |
| **WhoScored.com** | Web scraping | Free | Match stats, ratings, form | Anti-scraping measures, Cloudflare |
| **Flashscore** | Web scraping | Free | Schedules, H2H, live stats, xG | JavaScript-heavy, needs Playwright |
| **Sofascore** | Web scraping | Free | Form, ratings, lineups, H2H | JavaScript-heavy |
| **Feedinco** | Web scraping | Free | BTTS/goals predictions, stats | |
| **BettingClosed** | Web scraping | Free | Closing odds, market analysis | |

**Recommended stack**: API-Football (primary stats) → Football-Data.org (fallback fixtures) → Understat (xG enrichment) → SoccerStats/TotalCorner (corner specialization via scraping)

**Key stats available**: corners, fouls, yellow cards, red cards, shots, shots on target, possession, offsides, saves — all per match, both home and away.

### 2.2 Basketball

| Source | Type | Cost | Data Available | Limitations |
|---|---|---|---|---|
| **API-Basketball** (api-sports.io) | REST API | Free: 100 req/day | Points, rebounds, assists, steals, blocks. NBA + 50+ leagues. | 100 req/day shared |
| **BallDontLie** | REST API | Free (key required) | NBA game results, player box scores, season averages | NBA only |
| **nba_api** (Python pkg) | Scraper | Free | Advanced NBA stats: pace, ORtg, DRtg, game logs | NBA only, rate-sensitive (~30 req/min) |
| **Basketball-Reference** | Web scraping | Free | Comprehensive historical stats, game logs | NBA/WNBA/NCAA only, scraping rate-limited |
| **Eurobasket.com** | Web scraping | Free | European basketball standings, results | Limited stats depth |
| **Flashscore** | Web scraping | Free | NBA, Euroleague, ACB, PLK fixtures and scores | |

**Recommended stack**: API-Basketball (primary, all leagues) → nba_api (NBA deep stats) → BallDontLie (NBA fallback)

**Key stats available**: points, rebounds, assists, FG%, 3PT%, FT%, pace, turnovers — per game.

### 2.3 Volleyball

| Source | Type | Cost | Data Available | Limitations |
|---|---|---|---|---|
| **API-Volleyball** (api-sports.io) | REST API | Free: 100 req/day | Team stats, results, set scores | Fewer leagues than football |
| **Flashscore** | Web scraping | Free | PlusLiga, SuperLega, CEV fixtures, scores, form | |
| **PlusLiga.pl** | Web scraping | Free | Polish PlusLiga detailed stats | Polish league only |
| **CEV.eu** | Web scraping | Free | European competition fixtures, results | |
| **Scores24.live** | Web scraping | Free | H2H, form, odds, trends for volleyball | Good multi-source |
| **The-Odds-API** | REST API | Free tier | **NOT covered** for volleyball | No odds data |

**Recommended stack**: API-Volleyball (primary) → Flashscore + Scores24 (form and H2H) → PlusLiga.pl (Polish league specialist)

**Key stats available**: points, aces, blocks, attack percentage, sets won, total points, errors.

**Challenge**: Volleyball has the least API coverage of the 7 focus sports. Scraping Flashscore and specialist sites is essential.

### 2.4 Hockey

| Source | Type | Cost | Data Available | Limitations |
|---|---|---|---|---|
| **API-Hockey** (api-sports.io) | REST API | Free: 100 req/day | Goals, shots, PP, PIM, hits, blocks, faceoffs. NHL + EU leagues. | 100 req/day shared |
| **NHL API** (statsapi.web.nhl.com) | REST API | Free, no key | Comprehensive NHL stats, game-by-game | NHL only, unofficial API |
| **MoneyPuck** | Web scraping | Free | Expected goals (xG), shot quality, game-level data | NHL only |
| **NaturalStatTrick** | Web scraping | Free | 5v5 stats, shot maps, Corsi, Fenwick | NHL only |
| **Hockey-Reference** | Web scraping | Free | Historical stats, game logs | NHL/international |
| **Flashscore** | Web scraping | Free | NHL, SHL, Liiga, DEL fixtures and scores | |

**Recommended stack**: API-Hockey (primary, all leagues) → NHL API (deep NHL stats) → MoneyPuck/NaturalStatTrick (advanced analytics)

**Key stats available**: goals, shots, powerplay goals, penalty minutes, hits, blocks, faceoff percentage, save percentage.

### 2.5 Tennis

| Source | Type | Cost | Data Available | Limitations |
|---|---|---|---|---|
| **TennisAbstract** | Web scraping | Free | Elo ratings, serve/return profiles, surface splits, matchup forecasts | |
| **UltimateTennisStatistics** | Web scraping | Free | Comprehensive career stats, H2H, surface form, Elo | |
| **TennisExplorer** | Web scraping | Free | Player form, rankings, match results with set scores | |
| **ATP/WTA official sites** | Web scraping | Free | Official rankings, tournament draws, player profiles | Limited stats depth |
| **Flashscore** | Web scraping | Free | ATP, WTA, Challenger fixtures, scores, H2H | |
| **The-Odds-API** | REST API | Free tier | Grand Slam odds only (seasonal keys) | Very limited tennis coverage |

**Recommended stack**: TennisAbstract (Elo + matchup analysis) → UltimateTennisStatistics (deep H2H, surface data) → TennisExplorer (form) → Flashscore (fixtures + scores)

**Key stats available**: aces, double faults, first serve %, break points won/saved, games won, service games won, return games won — by surface.

**Important learning from Betclic history**: Skip ITF/low-level tennis entirely. Only ATP/WTA main draw or strong Challengers. Match odds ratio grading (STRONG ≤1.15, GOOD 1.16–1.30, BORDERLINE 1.31–1.50, REJECT >1.50) is essential for game totals markets.

### 2.6 Snooker

| Source | Type | Cost | Data Available | Limitations |
|---|---|---|---|---|
| **CueTracker** | Web scraping | Free | Player rankings, match results, century breaks, tournament history | Most comprehensive free source |
| **Snooker.org** | Web scraping | Free | Rankings, results, tournament schedules | Less detailed than CueTracker |
| **Flashscore** | Web scraping | Free | Snooker fixtures, scores, H2H | |
| **Scores24.live** | Web scraping | Free | Snooker H2H, form, trends | |
| **The-Odds-API** | REST API | Free tier | **NOT covered** for snooker | No odds data |

**Recommended stack**: CueTracker (primary stats source) → Snooker.org (rankings, schedules) → Flashscore + Scores24 (fixtures, form)

**Key stats available**: frames won, centuries (100+ breaks), 50+ breaks, highest break, frame scoring patterns.

**Note**: Snooker has an 80% hit rate in the current system with frame totals at 100% — this sport deserves priority despite limited API coverage.

### 2.7 Speedway (Żużel)

| Source | Type | Cost | Data Available | Limitations |
|---|---|---|---|---|
| **SpeedwayEkstraliga.pl** | Web scraping | Free | PGE Ekstraliga standings, results, rider stats, heat protocols | Polish Ekstraliga only |
| **SportoweFakty.wp.pl** | Web scraping | Free | News, previews, rider form (Polish language) | News-focused, limited stats |
| **Flashscore** | Web scraping | Free | Speedway fixtures, scores | Limited coverage |
| **The-Odds-API** | REST API | Free tier | **NOT covered** for speedway | No odds data |

**Recommended stack**: SpeedwayEkstraliga.pl (primary, heat-by-heat data) → SportoweFakty (context, previews)

**Key stats available**: heat points, total team points, individual rider scores, heat results, home/away track advantage.

**Challenge**: Speedway has the most limited data infrastructure. Reliable stats are available primarily for the Polish Ekstraliga and SGP (Speedway Grand Prix). The new system needs a lightweight adapter for SpeedwayEkstraliga.pl that extracts heat protocol data.

### 2.8 Cross-Sport Sources

| Source | Sports Covered | Role |
|---|---|---|
| **Flashscore** | All 7 | Fixture discovery, scores, H2H — universal backbone |
| **Sofascore** | All except speedway | Form, ratings, odds movements |
| **Scores24.live** | All except speedway | H2H, form, trends with hit rates |
| **BetExplorer** | All 7 | Odds comparison, results, streaks |
| **OddsPortal** | All 7 | Market-best prices, line shopping, dropping odds |
| **The-Odds-API** | Football, Basketball, Hockey, Tennis (limited) | Programmatic odds retrieval |

### 2.9 Odds Sources Summary

| Source | Coverage | Access | Best For |
|---|---|---|---|
| **The-Odds-API** | Football (50 leagues), Basketball, Hockey, Tennis (Grand Slams), Baseball, MMA | Free: 500 credits/month | Cross-validation, programmatic odds |
| **API-Football /odds** | Football (1000+ leagues) | Free: 100 req/day (shared) | Deep football odds (corners O/U, cards O/U) |
| **OddsPortal** | All sports | Scraping | Market-best prices, line movement |
| **BetExplorer** | All sports | Scraping | Odds comparison, results, streaks |
| **Betclic** | All sports | Manual (403 blocks scraping) | Execution odds — user verifies on app |

---

## 3. Database Design Considerations

### 3.1 Why a Database Is Essential

The current system stores everything in flat files (300+ files in `betting/data/`). This creates:
- No deduplication (same team stats fetched repeatedly)
- No historical continuity (each day's analysis is independent)
- No efficient querying (finding "all Liverpool corners data" requires scanning dozens of files)
- No data integrity (inconsistent team names across sources)
- No incremental updates (must re-fetch everything each session)

### 3.2 Recommended Database: SQLite

For a single-user, local-first system with 47 PLN bankroll, **SQLite** is the right choice:

- Zero infrastructure (single file, no server process)
- Python stdlib support (`sqlite3` module)
- Supports up to 281 TB — more than enough
- Full SQL query capability
- Easy backup (copy one file)
- Can migrate to PostgreSQL later if needed

**NOT recommended**: PostgreSQL (overkill for single user), MongoDB (schema-less is wrong for structured sports data), Redis (not persistent enough).

### 3.3 Schema Design — Core Tables

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│     sports      │     │   competitions   │     │     teams        │
├─────────────────┤     ├──────────────────┤     ├──────────────────┤
│ id (PK)         │     │ id (PK)          │     │ id (PK)          │
│ name            │◄────│ sport_id (FK)    │     │ sport_id (FK)    │
│ tier (1|2)      │     │ name             │     │ name             │
│ stat_keys JSON  │     │ country          │     │ aliases JSON     │
└─────────────────┘     │ importance (1-5) │     │ country          │
                        │ season           │     │ venue            │
                        └──────────────────┘     │ style_tags JSON  │
                                                 └──────────────────┘
                                                          │
┌──────────────────┐     ┌──────────────────┐             │
│    fixtures      │     │  match_stats     │             │
├──────────────────┤     ├──────────────────┤             │
│ id (PK)          │     │ id (PK)          │             │
│ sport_id (FK)    │     │ fixture_id (FK)  │◄────────────┘
│ competition_id   │     │ team_id (FK)     │
│ home_team_id(FK) │     │ stat_key         │  (e.g., "corners")
│ away_team_id(FK) │     │ stat_value REAL  │  (e.g., 7.0)
│ kickoff DATETIME │     │ source           │
│ status           │     │ fetched_at       │
│ score_home INT   │     └──────────────────┘
│ score_away INT   │
└──────────────────┘

┌──────────────────┐     ┌──────────────────┐
│    odds_history  │     │     bets         │
├──────────────────┤     ├──────────────────┤
│ id (PK)          │     │ id (PK)          │
│ fixture_id (FK)  │     │ fixture_id (FK)  │
│ bookmaker        │     │ market           │
│ market           │     │ selection        │
│ selection        │     │ odds REAL        │
│ odds REAL        │     │ stake_pln REAL   │
│ line REAL        │     │ status           │
│ fetched_at       │     │ pnl_pln REAL     │
│ is_closing BOOL  │     │ coupon_id        │
└──────────────────┘     │ placed_at        │
                         │ settled_at       │
┌──────────────────┐     │ betclic_ref      │
│    team_form     │     └──────────────────┘
├──────────────────┤
│ id (PK)          │     ┌──────────────────┐
│ team_id (FK)     │     │    coupons       │
│ sport_id (FK)    │     ├──────────────────┤
│ stat_key         │     │ id (PK)          │
│ l10_values JSON  │     │ coupon_type      │
│ l5_values JSON   │     │ total_odds REAL  │
│ l10_avg REAL     │     │ stake_pln REAL   │
│ l5_avg REAL      │     │ status           │
│ trend (up|down)  │     │ pnl_pln REAL     │
│ updated_at       │     │ placed_at        │
│ source           │     │ settled_at       │
└──────────────────┘     │ betclic_ref      │
                         │ version          │
                         └──────────────────┘
```

### 3.4 Multi-Sport Schema Pattern: Entity-Attribute-Value (EAV) for Stats

The `match_stats` table uses an EAV pattern with `stat_key` + `stat_value`. This is essential for multi-sport because:
- Football has ~10 stat types (corners, fouls, cards, shots, possession...)
- Basketball has ~9 stat types (points, rebounds, assists, FG%...)
- Each sport has different relevant stats
- A fixed-column schema would require 50+ nullable columns

The tradeoff: EAV queries are slightly slower for aggregations. Mitigate with:
- `CREATE INDEX idx_match_stats_team_key ON match_stats(team_id, stat_key)`
- Materialized views (or cached queries) for L10/L5 averages
- The `team_form` table serves as a denormalized cache

### 3.5 Team Name Normalization

A critical challenge in multi-source sports data. The system already has `utils.normalize_team_name()`. The database should store:
- One canonical name per team
- An `aliases` JSON array with all known variants
- A lookup function that matches against aliases during data ingestion

Example:
```json
{
  "name": "FC Barcelona",
  "aliases": ["Barcelona", "Barca", "FCB", "FC Barcelona", "Barcelona FC", "Barça"]
}
```

### 3.6 Data Retention & TTL Policy

| Data Type | Retention | Reason |
|---|---|---|
| Team profiles | Permanent | Core reference data |
| Match stats (L10/L5) | Current season + 1 | Form-relevant window |
| H2H records | 5 years | Long-term patterns |
| Odds history | 90 days | Line movement analysis |
| Bets & coupons | Permanent | Performance tracking |
| Weather data | 7 days | Only relevant for upcoming fixtures |
| Scan artifacts (HTML) | 24 hours | Temporary; extract and discard |

---

## 4. Statistics That Actually Matter Per Sport

### 4.1 Football — Predictive Stats for Statistical Markets

**For Corners O/U:**
| Statistic | Predictive Value | Why |
|---|---|---|
| Team corners per game (home/away split) | **Very High** | Direct predictor; most persistent stat |
| Possession % | High | High-possession teams force corners through sustained attacks |
| Shots per game | High | More shots → more deflections → more corners |
| Opposition defensive style | High | Deep-block defenders concede more corners |
| Competition importance | Medium | Higher stakes → more pressing → more corners |

**For Cards O/U:**
| Statistic | Predictive Value | Why |
|---|---|---|
| Fouls committed per game | **Very High** | Cards follow fouls; direct correlation |
| Referee card average | **Very High** | Referee assignment is the strongest predictor of cards |
| Derby/rivalry flag | High | Heated matches → more fouls → more cards |
| Team aggression style | High | Pressing teams foul more in transitions |
| Match importance | Medium | Must-win situations increase tactical fouling |

**For Fouls O/U:**
| Statistic | Predictive Value | Why |
|---|---|---|
| Team fouls per game | **Very High** | Most consistent stat across matches |
| Pressing intensity (PPDA) | High | High-press teams commit more fouls in midfield |
| Pace of play | Medium | Faster games create more challenges |
| Referee foul tolerance | Medium | Some referees let play flow more |

**For Shots/SOT:**
| Statistic | Predictive Value | Why |
|---|---|---|
| Team shots per game | **Very High** | Directly predictive |
| xG (expected goals) | High | Higher xG → more shot attempts |
| Possession % | Medium-High | Ball dominance creates more shooting opportunities |
| Opposition defensive form | High | Weak defenses allow more shots |

### 4.2 Basketball — Predictive Stats for Totals

| Statistic | Predictive Value | Why |
|---|---|---|
| Pace (possessions per 48 min) | **Very High** | The #1 predictor of total points |
| Offensive Rating (ORtg) | Very High | Points per 100 possessions |
| Defensive Rating (DRtg) | Very High | Points allowed per 100 possessions |
| 3-point attempt rate | High | More 3PA → more variance in scoring |
| Free throw rate | Medium | FTs are consistent points |
| Turnovers per game | Medium | More turnovers → fewer scoring opportunities |
| Rest days | Medium | Back-to-back games reduce pace and efficiency |

**Combined formula for total points prediction:**
$$Total \approx \frac{Pace_A + Pace_B}{2} \times \frac{(ORtg_A + ORtg_B) / 2}{100}$$

### 4.3 Hockey — Predictive Stats for Goals/Totals

| Statistic | Predictive Value | Why |
|---|---|---|
| Shots per game | **Very High** | More shots → more goals |
| Save percentage (goalie) | **Very High** | Goaltending dominates hockey outcomes |
| Powerplay % | High | Efficient PP creates high-scoring situations |
| Penalty minutes per game | High | More penalties → more PP opportunities |
| Expected goals (xG) | High | Quality of chances over quantity |
| Faceoff win % | Medium | Puck possession advantage |
| Score effects | Medium | Trailing team opens up, leading team tightens |

**Key insight**: Goaltender identification is critical. A backup goalie with .890 SV% vs a starter with .920 SV% can swing a total by 1-2 goals. The system must track goaltender assignments.

### 4.4 Tennis — Predictive Stats for Games/Sets Totals

| Statistic | Predictive Value | Why |
|---|---|---|
| Match odds competitiveness ratio | **Very High** | Close odds → 3 sets likely → more games |
| First serve % | High | Higher first serve → more hold of serve → tighter sets |
| Break points saved % | High | Good servers protect serve → longer sets |
| Surface-specific win rate | High | Surface specialists perform differently on clay vs hard |
| H2H record on same surface | High | Some matchups consistently go to 3 sets |
| Elo rating difference | High | Smaller gap → more competitive match |
| Tournament round | Medium | Early rounds have more mismatches |

**Match odds ratio grading system (validated by Betclic history):**
- STRONG ≤1.15: High probability of 3 sets → bet O20.5 games
- GOOD 1.16–1.30: Moderate 3-set probability → viable but lower edge
- BORDERLINE 1.31–1.50: Risky — drop from portfolio
- REJECT >1.50: Too lopsided for game totals

### 4.5 Volleyball — Predictive Stats for Set/Point Totals

| Statistic | Predictive Value | Why |
|---|---|---|
| Sets per match average | **Very High** | Directly predicts O/U 3.5 sets |
| Attack efficiency % | High | Better attack → faster set wins |
| Ace count per set | Medium-High | Aces create quick points |
| Block effectiveness | Medium | Strong blocks can shorten or extend sets |
| Team competitiveness (ranking gap) | High | Close-ranked teams → 4-5 set matches |
| Home/away point differential | Medium | Home court matters in volleyball |

### 4.6 Snooker — Predictive Stats for Frame Totals

| Statistic | Predictive Value | Why |
|---|---|---|
| Career frame winning % | **Very High** | Consistency in frame-by-frame play |
| Century break rate | High | Frequent centuries = shorter frames = fewer frames |
| Average frame score | Medium-High | One-sided frames end quickly |
| H2H frame count history | **Very High** | Some matchups consistently go to deciding frames |
| Tournament stage | High | Later rounds feature longer best-of formats |
| Recent form (L5 tournament results) | Medium | Snooker form is streaky |

**Current system performance**: 100% hit rate on frame totals (11 legs) — maintain and prioritize this market.

### 4.7 Speedway — Predictive Stats for Heat/Points Markets

| Statistic | Predictive Value | Why |
|---|---|---|
| Home track advantage | **Very High** | Track familiarity is the #1 factor in speedway |
| Team aggregate heat points | High | Predicts total team points in a match |
| Individual rider season averages | High | Top riders consistently score 10-12 points per match |
| Gate position draw | Medium | Some tracks heavily favor inside gates |
| Weather conditions | Medium | Wet/dry dramatically affects riding style |
| Track surface condition | Medium | Slick vs grippy tracks favor different riders |

---

## 5. Architecture Recommendations

### 5.1 Parallelization Strategy

**Current problem**: Sequential scanning of 100+ URLs takes 20-40 minutes.

**Recommended approach: `asyncio` + `aiohttp` for API calls, Playwright pool for scraping**

```
                    ┌─────────────────────┐
                    │  Pipeline Scheduler  │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼─────┐ ┌──────▼──────┐ ┌──────▼──────┐
     │  Sport Group  │ │ Sport Group │ │ Sport Group │
     │  Football     │ │ Basketball  │ │ Snooker     │
     │  Volleyball   │ │ Hockey      │ │ Speedway    │
     │               │ │ Tennis      │ │             │
     └───────┬───────┘ └──────┬──────┘ └──────┬──────┘
             │                │               │
    ┌────────┼────────┐    (parallel)      (parallel)
    │        │        │
 API Calls  Scraping  Stats
 (async)    (Playwright (DB lookup
             pool)     + API fill)
```

**Implementation details:**
- Group sports into 3 parallel streams (by estimated data volume)
- Within each stream, run API calls concurrently with `asyncio.gather()`
- Maintain a Playwright browser pool of 3-5 instances for scraping
- Rate-limit per source domain (existing `RateLimiter` class can be reused)
- Target: reduce scan from 40 min to 8-12 min

### 5.2 Agent-Based Architecture

An agent-based approach where specialized agents handle different analysis concerns:

```
┌──────────────────────────────────────────────────────┐
│                    Orchestrator Agent                  │
│  (coordinates workflow, manages state, resolves deps) │
└──────────┬──────────────┬─────────────┬──────────────┘
           │              │             │
  ┌────────▼────┐ ┌───────▼──────┐ ┌───▼────────────┐
  │ Scanner     │ │ Statistician │ │ Coupon Builder  │
  │ Agent       │ │ Agent        │ │ Agent           │
  ├─────────────┤ ├──────────────┤ ├─────────────────┤
  │ Fixture     │ │ L10/L5 form  │ │ Portfolio const │
  │ discovery   │ │ H2H analysis │ │ Stake sizing    │
  │ Odds fetch  │ │ Safety scores│ │ Validation      │
  │ Source mgmt │ │ Market rank  │ │ Polish output   │
  └─────────────┘ └──────────────┘ └─────────────────┘
           │              │             │
           └──────────────┼─────────────┘
                          │
                   ┌──────▼──────┐
                   │   SQLite    │
                   │   Database  │
                   └─────────────┘
```

**Agent responsibilities:**
1. **Scanner Agent**: Discovers fixtures, fetches odds, manages source health. Runs in parallel per sport group.
2. **Statistician Agent**: Performs deep analysis per candidate. Calculates safety scores, runs three-way cross-check, ranks markets.
3. **Coupon Builder Agent**: Constructs portfolios from approved picks, manages diversification, outputs Polish-language coupons.
4. **Orchestrator**: Coordinates the pipeline, handles resume/retry, maintains state.

### 5.3 Real-Time vs Batch Processing

| Aspect | Current (Batch) | Recommended (Hybrid) |
|---|---|---|
| Fixture discovery | Once per session | Batch daily at 06:00 |
| Stats fetching | Once per session | Incremental (check DB TTL, fetch only stale) |
| Odds monitoring | One-shot | Periodic (every 2h) for closing line tracking |
| Analysis | Full re-run | Delta: only new fixtures or changed odds |
| Coupons | One-shot generation | Generate once, update if odds drift >8% |

**Recommendation**: Primarily batch with incremental updates. The database enables "only fetch what's stale" logic, reducing API usage from ~100 requests to ~20-30 per session.

### 5.4 Handling Betclic Without API

Betclic blocks automated access (403). The workflow must be:

1. **System generates picks with target lines and minimum acceptable odds** (calculated from hit rates)
2. **User opens Betclic app, navigates to the match, checks if the market exists and what odds are offered**
3. **User compares Betclic odds against minimum acceptable odds** — if Betclic odds ≥ minimum, the bet is +EV
4. **User places bet manually and records the actual odds**
5. **System updates the database with actual placed odds for CLV tracking**

**The new system should output a "shopping list"** format:
```
1. ⚽ Liverpool vs Arsenal — Rzuty rożne łącznie Powyżej 9.5
   Min odds: 1.25 | Est. odds: 1.40-1.55 | Safety: 0.80
   → Open Betclic → Piłka nożna → Premier League → Liverpool-Arsenal → Statystyki → Rzuty rożne
```

### 5.5 Simplified Pipeline (Target: 5 Steps Instead of 10)

```
STEP 1: DISCOVER (parallel, 5-8 min)
  ├── API fixture discovery (all 7 sports, concurrent)
  ├── Scrape fixtures from Flashscore (Playwright pool)
  ├── Fetch odds from The-Odds-API + API-Football
  └── DB: save fixtures, dedup, merge

STEP 2: ENRICH (incremental, 3-5 min)
  ├── For each fixture: check DB for cached stats
  ├── Fetch only stale/missing stats from APIs
  ├── Compute L10/L5 averages, safety scores per market
  └── DB: update team_form, match_stats

STEP 3: ANALYZE (fast, <1 min)
  ├── Rank all markets across all fixtures by safety score
  ├── Apply user preferences (UNDER bias, sport priorities)
  ├── Cross-reference Betclic history for market hit rates
  └── Output: ranked candidate list with min acceptable odds

STEP 4: BUILD COUPONS (fast, <1 min)
  ├── Select top picks for 2-3 leg coupons (max 3 legs!)
  ├── Enforce independence (different events, diverse sports)
  ├── Calculate stakes (flat 1-2 PLN)
  └── Output: Polish-language shopping list for Betclic app

STEP 5: SETTLE (on demand)
  ├── Check results from APIs / Flashscore
  ├── Update bet/coupon status in DB
  ├── Calculate PnL, update bankroll
  └── Refresh learning analysis
```

Total target runtime: **10-15 minutes** (down from 30-50 minutes).

---

## 6. Current System Assessment — What to Keep vs Discard

### 6.1 Components to KEEP (adapt for new architecture)

| Component | File | Reason | Adaptation Needed |
|---|---|---|---|
| **Betclic history analysis** | `analyze_betclic_learning.py` | Core learning engine with 489 legs of data. Market categorization, hit rate calculation, coupon-killer analysis. | Adapt to read from SQLite instead of JSON. Keep market category mapping. |
| **Betclic bet history data** | `betclic_bets_history.json` | Irreplaceable ground truth. 153 coupons with leg-level detail. | Import into SQLite `bets` and `coupons` tables as seed data. |
| **API client architecture** | `api_clients/` | Well-designed: base class with retry + rate limiting, factory pattern, 10+ sport clients. | Keep base_client.py, rate_limiter.py. Refactor clients to write to DB instead of JSON. |
| **Normalized data structures** | `normalize_stats.py` | `NormalizedFixture`, `NormalizedMatchStats`, `SPORT_STAT_KEYS`, market definitions per sport. | Keep dataclasses. Adapt to be ORM models or DB insertion helpers. |
| **Safety score computation** | `compute_safety_scores.py` | Deterministic, well-tested ranking algorithm. Hit rate + three-way cross-check. | Keep core algorithm. Adapt to query DB instead of JSON input. |
| **Odds API integration** | `fetch_odds_api.py` | Working The-Odds-API integration with auto-discovery, sport mapping, credit tracking. | Keep. Add DB persistence for odds history. |
| **Multi-source odds** | `fetch_odds_multi.py` + `odds_sources/` | Source priority chains, event matching, odds merging. | Keep architecture. Simplify source loading. |
| **Settlement logic** | `settle_on_finish.py` | Auto-settlement for standard markets, polling, multi-source verification. | Keep settlement logic. Adapt to update DB. |
| **Polish market translations** | `coupon_builder.py` (MARKET_PL, DIRECTION_PL) | Essential for Betclic execution. | Keep translations. Move to a translations config file. |
| **Betting config** | `config/betting_config.json` | Working config with bankroll, sports, market types, thresholds. | Keep. Reduce complexity (remove 14 sports, keep 7). |
| **Stats cache structure** | `build_stats_cache.py` | TTL-based caching with form/H2H separation. | Replace with DB queries but keep the TTL concept. |
| **Source registry** | `source-registry.md` | Comprehensive documentation of all sources with access notes. | Keep as reference documentation. |
| **Picks/coupons ledgers** | `picks-ledger.csv`, `coupons-ledger.csv` | Historical tracking data. | Import into DB tables. |

### 6.2 Components to DISCARD (replace entirely)

| Component | File(s) | Reason | Replacement |
|---|---|---|---|
| **Monolithic scan shell script** | `run_full_scan_and_prepare.sh` | 200+ URLs sequentially scraped, 40 min runtime, fragile | Parallel Python orchestrator with Playwright pool |
| **17-point gate checker** | `gate_checker.py` | Over-engineered; many gates are irrelevant or auto-pass. The system needs 5-6 meaningful checks, not 17. | Simplified 5-point quality check: (1) data quality, (2) EV > 0, (3) no 48h repeat, (4) safety score ≥ 0.60, (5) three-way alignment |
| **HTML file accumulation** | 300+ files in `betting/data/` | Unstructured, unsearchable, grows daily | Database storage for all structured data. Delete HTML after parsing. |
| **Site-specific adapters** (most) | `adapters/` (14 files) | Fragile HTML parsing that breaks with any site redesign | Keep 3-4 essential adapters (Flashscore, BetExplorer, scores24). Replace others with API-first approach. |
| **Deep link discovery** | `deep_link_discovery.py` | Crawls hundreds of sub-pages, main source of timeout | Replace with API fixture discovery + targeted scraping only |
| **10-step pipeline** | `pipeline_orchestrator.py` | S0→S1→S1b→S1c→S1d→S1e→S3→S7→S8→S9→S10 is too granular | 5-step pipeline: Discover → Enrich → Analyze → Build → Settle |
| **Market matrix generation** | `generate_market_matrix.py` | Intermediate artifact that's immediately consumed by next step | Inline into analysis step; query DB directly |
| **Shortlist building** | `build_shortlist.py` | Ranking step that could be a SQL query | Replace with `SELECT ... ORDER BY safety_score DESC LIMIT N` |
| **Coupon validation** (V1-V10) | `validate_coupons.py` | 10-point validation was needed because coupons were error-prone. With simpler 2-3 leg coupons, validation is trivial. | Inline validation in coupon builder: check arithmetic and event uniqueness. |
| **Weather fetching** | `fetch_weather.py` | Adds complexity for marginal value. Weather matters for speedway but not much for other indoor/covered sports. | Optional module, not in critical path. |

### 6.3 Components to SIMPLIFY

| Component | Current Complexity | Target Simplicity |
|---|---|---|
| Sports scope | 14 sports | 7 focus sports |
| Pipeline steps | 10 steps (S0-S10) | 5 steps |
| Gate checks | 17 points | 5-6 meaningful checks |
| Coupon types | Core + Combo Menu + Extended Pool | Core coupons only (2-3 legs each) |
| Max legs per coupon | Up to 7 | Max 3 (data shows 5+ legs = 0% win rate) |
| Scan URLs | 200+ | 30-50 (API-first, scrape only gaps) |
| Output files per session | 15-20 files | 2-3 files (coupons + summary, rest in DB) |
| Adapters | 14 site-specific | 3-4 essential (Flashscore, BetExplorer, Scores24, SpeedwayEkstraliga) |

---

## 7. Risks and Constraints

### 7.1 Technical Risks

| Risk | Impact | Mitigation |
|---|---|---|
| API rate limits (100 req/day for api-sports.io) | Cannot fetch stats for all fixtures | Prioritize by competition importance + betting opportunity; cache aggressively in DB |
| Playwright scraping breakage | Site redesigns break adapters | Minimize scraping reliance; use APIs first; keep adapters simple and maintainable |
| Betclic 403 blocks | Cannot verify odds programmatically | Accept manual verification via app; output "shopping list" format |
| SQLite concurrency | Cannot run parallel writes | Use WAL mode; batch writes; single-writer pattern |
| Data quality from free sources | Inconsistent or missing stats | Cross-validate across 2+ sources; flag low-confidence data |

### 7.2 Business Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Small bankroll (47 PLN) limits diversification | Cannot place many simultaneous coupons | Focus on 2-3 high-conviction coupons per day with flat 1-2 PLN stakes |
| Betclic market availability | Statistical markets may not exist for some matches | System outputs picks with fallback markets ranked by safety |
| Negative ROI persists after rewrite | Bankroll depletion | Enforce 20% drawdown protection; reduce to minimum stakes; focus on proven markets (team_corners, cards, frame_totals) |
| Overfitting to Betclic history | 489 legs may not be statistically significant | Track CLV and Brier scores alongside raw hit rates; continue learning |

### 7.3 Constraint Summary

- **Budget**: Zero for infrastructure (SQLite, free APIs, free scraping)
- **Execution**: Betclic only, manual placement via app
- **Time**: Timezone Europe/Warsaw, betting day 06:00-05:59
- **Bankroll**: 47 PLN — every PLN matters
- **Scope**: 7 sports maximum
- **Coupon size**: Max 3 legs (empirically validated)
- **Language**: Polish output for Betclic navigation

---

## 8. Gap Analysis — Open Questions

### Question 1: Coupon Size Limit
#### Should the new system enforce a hard maximum of 3 legs per coupon, given that 5+ leg accumulators have a 0% win rate in 20 attempts?
The data is clear (0 wins from 20 attempts with 5+ legs). Recommended: hard cap at 3 legs for core coupons. User can manually combine into larger AKOs on Betclic if desired.

### Question 2: Sport Prioritization
#### Should the system dynamically prioritize sports based on historical hit rates (e.g., snooker 80%, football 45%) or maintain equal scanning across all 7 sports?
Snooker and team corners have dramatically higher hit rates. However, snooker has limited daily fixtures. Recommended: priority scanning with dynamic weighting, but always scan all 7 sports for fixture availability.

### Question 3: Historical Data Migration
#### How much of the current 300+ files in `betting/data/` should be migrated to the new SQLite database?
Recommended: Import `betclic_bets_history.json`, `picks-ledger.csv`, `coupons-ledger.csv`, and `stats_cache/` data. Discard all HTML files, intermediate analysis files, and duplicate research files.

### Question 4: Odds Verification Workflow
#### Is the current "generate picks → user checks Betclic → user places manually" workflow acceptable, or should the system attempt to integrate more closely with Betclic?
Given Betclic's 403 blocks, manual verification is the only reliable approach. The system should optimize the "shopping list" output to minimize user effort (exact Betclic navigation paths, market names in Polish).

### Question 5: Daily Automation
#### Should the system run automatically (cron job at 06:00) or remain manually triggered?
Recommended: manual trigger with optional cron. The user should control when analysis runs. Automatic settlement can run via cron since it doesn't cost API credits.

### Question 6: Learning Feedback Loop
#### How should the system update its models based on bet outcomes? Currently learning is advisory-only (no auto-rejection based on history).
Per the user's permanent rule (stored in memory): Betclic learning data is ADVISORY ONLY. The system should display hit rates prominently but never auto-reject markets. This rule must be preserved in the rewrite.

### Question 7: Technology Stack Beyond Python
#### Should the rewrite stay pure Python or introduce other technologies (TypeScript for web UI, Go for parallel scanning, etc.)?
Recommended: Stay pure Python. The user is clearly proficient in Python. Adding languages increases maintenance burden without proportional benefit for a single-user system. Use `asyncio` for parallelism instead of Go. Skip a web UI — CLI + markdown output is sufficient for the workflow.

---

## Gathered Information Summary

### Knowledge Base & Task Management Tools
- No Jira or Confluence connected for this project
- Requirements gathered directly from user prompt and codebase analysis

### Codebase Analysis
- **Total scripts**: 30+ Python files in `scripts/`
- **Adapters**: 14 site-specific HTML parsers in `scripts/adapters/`
- **API clients**: 10 sport-specific API clients in `scripts/api_clients/`
- **Odds sources**: 5 odds providers in `scripts/odds_sources/`
- **Data files**: 300+ files in `betting/data/` (unstructured mix of JSON, CSV, HTML, MD)
- **Dependencies**: requests, beautifulsoup4, playwright, lxml, understat, nba_api
- **Config**: `config/betting_config.json` with 14 sports, 47 PLN bankroll
- **Ledgers**: `picks-ledger.csv` (100+ picks), `coupons-ledger.csv`, `learning-log.md`

### Relevant Links
- [The-Odds-API Documentation](https://the-odds-api.com/liveapi/guides/v4/) — Free tier: 500 credits/month
- [API-Football Documentation](https://www.api-football.com/documentation-v3) — Free tier: 100 req/day
- [API-Sports.io](https://api-sports.io/) — Basketball, Hockey, Volleyball, Tennis, Handball APIs — same free tier
- [SQLite Documentation](https://www.sqlite.org/docs.html) — Recommended database

### Current Implementation Status

#### Existing Components

- **Pipeline orchestrator** — `scripts/pipeline_orchestrator.py` — needs full rewrite (too many steps, sequential)
- **Betclic learning** — `scripts/analyze_betclic_learning.py` — can be reused (adapt to DB)
- **API client framework** — `scripts/api_clients/` — can be reused (well-architected base class + registry)
- **Safety score computation** — `scripts/compute_safety_scores.py` — can be reused (deterministic algorithm)
- **Stats normalizer** — `scripts/normalize_stats.py` — can be reused (dataclasses + market definitions)
- **Odds API integration** — `scripts/fetch_odds_api.py` — can be reused (working integration)
- **Settlement engine** — `scripts/settle_on_finish.py` — can be reused (adapt to DB)
- **Coupon builder** — `scripts/coupon_builder.py` — needs simplification (remove combo menu + extended pool)
- **Gate checker** — `scripts/gate_checker.py` — needs full rewrite (17 points → 5-6)
- **Scan framework** — `scripts/scan_events.py` — needs full rewrite (sequential → parallel)
- **Shell orchestrator** — `scripts/run_full_scan_and_prepare.sh` — discard (replace with Python async)
- **HTML adapters** — `scripts/adapters/` — keep 3-4, discard rest
- **Betclic history data** — `betting/data/betclic_bets_history.json` — must preserve (import to DB)
- **Configuration** — `config/betting_config.json` — can be reused (simplify sport list)
- **Source registry** — `betting/sources/source-registry.md` — keep as documentation

#### Key Files and Directories
- `scripts/api_clients/base_client.py` — Core API client abstraction with retry, rate limiting, key loading
- `scripts/api_clients/rate_limiter.py` — Per-source rate limiting implementation
- `scripts/normalize_stats.py` — Normalized data structures (`NormalizedFixture`, `NormalizedMatchStats`, `SPORT_STAT_KEYS`)
- `scripts/compute_safety_scores.py` — §3.0 deterministic market ranking algorithm
- `betting/data/betclic_bets_history.json` — 153 coupons, 489 legs of Betclic ground truth
- `betting/journal/picks-ledger.csv` — All picks with outcomes, sources, reasoning
- `betting/journal/coupons-ledger.csv` — All coupons with PnL
- `config/betting_config.json` — System configuration
- `betting/sources/source-registry.md` — Complete source documentation with access notes
