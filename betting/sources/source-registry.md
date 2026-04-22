# Betting Source Registry

Purpose: use sources by role, not by raw count. More sources only help when each source has a clear job.

## Tier A Core Market and Price Sources

- Betclic
  Role: execution price and available markets.
  Use for: the exact bookmaker odds and stake plan.
  Never use for: main analytical justification.

- OddsPortal
  Role: market-best price, line shopping, dropping odds, value bets, archived results, standings.
  Use for: best-market comparison, price_gap_pct, movement context, and result backchecks.

- Oddspedia
  Role: odds comparison, smartbet ideas, consensus, archived odds, and cross-sport coverage.
  Use for: market comparison, consensus context, and extra market discovery.

- BetExplorer
  Role: odds comparison, results, streaks, popular bets, and odds movements.
  Use for: bookmaker comparison, results history, and market heat checks.

## Tier A Core Stats, Fixture, and Verification Sources

- Flashscore
  Role: schedules, lineups, H2H, live stats, xG and match statistics where available, and results.
  Use for: fixture confirmation, pre-match context, and settlement verification.

- Sofascore
  Role: schedules, team form, player ratings, lineups, H2H, dropping or rising odds, and cross-sport stats.
  Use for: pre-match context, verification, extra stats, and line movement cross-check.

- Covers
  Role: expert-written previews for US sports and big markets.
  Use for: NBA, NHL, MLB, NFL, UFC, and golf support and narrative checks.

- TeamRankings
  Role: algorithmic picks, rankings, trends, injuries, matchup pages, and efficiency stats.
  Use for: NBA, MLB, NFL, and college sports, especially totals and spread context.

- TennisAbstract
  Role: tennis Elo, matchup data, serve-return profiles, forecasts, and surface context.
  Use for: tennis moneyline, set handicap, game or set totals, and form quality.

- Sportsgambler
  Role: multi-sport written previews with lineups, injuries, and advanced metrics.
  Use for: football plus North American sports when a fresh preview is needed.

## Tier B Support and Consensus Sources

- Forebet
  Role: football model support and scoreline lean.
  Use for: secondary confirmation only.

- SportyTrader
  Role: football previews and broad market suggestions.
  Use for: secondary confirmation only.

- PredictZ
  Role: football scoreline and simple market support.
  Use for: secondary confirmation only.

- bettingexpert
  Role: community tipster sentiment.
  Use for: consensus alignment check and divergence warning.

- ProTipster
  Role: community and tipster aggregation.
  Use for: consensus alignment check and divergence warning.

- Oddspedia Community
  Role: consensus and popularity.
  Use for: consensus alignment check and divergence warning.

- Zawod Typer
  Role: local market awareness, tip aggregation, and injury/news early detection.
  Use for: consensus alignment check, divergence warning, and local knowledge (injuries, lineup rumors, motivation context).
  Priority: highest among community sources for Polish league and tennis events.

### Community Source Usage Rules

Community sources CANNOT create a bet on their own. They serve three functions:

1. **Consensus alignment (+confidence):** If ≥70% of community tips agree with the Tier A statistical direction, boost confidence by 0.5 (round to nearest integer). Note this in the report.
2. **Consensus divergence (red flag):** If ≥60% of community tips CONTRADICT the Tier A direction, treat as a warning. Check for information the stats might miss (injuries, lineup changes, motivation). If no explanation is found, reduce confidence by 1 or skip the pick.
3. **Early news detection:** Forum posts may contain injury/suspension/weather info before it appears in Flashscore. If a community source reports a key absence, verify with a second source before acting on it.

Always record in the report which community sources were checked and whether consensus aligned or diverged.

## Optional or Fragile Sources

- Understat
  Role: football xG and xGA.
  Use when accessible, especially for stronger football shot-quality context.

- WhoScored
  Role: football ratings and match stats.
  Use when accessible, never as the only source.

## Tier A Specialist Statistical Sources (by sport)

### Football — Corners, Cards, Fouls

- Betaminic
  Role: corners per team, yellow cards per team, goals per team — tables and charts across ALL leagues.
  URLs: betaminic.com/statistics/corners-team-stats-tables/, yellow-cards-team-stats-tables/
  Use for: identifying high-corner or high-card teams across obscure leagues, backing O/U corner and card markets.
  Access: OK (no Cloudflare).

- TotalCorner
  Role: live corner predictions, corner handicap lines, corner totals, corner averages per match.
  URL: totalcorner.com/match/today
  Use for: corner handicap and total lines for today's matches, pre-match corner average context.
  Access: OK (no Cloudflare).

- SoccerStats
  Role: league-level corner stats, card stats, fouls, BTTS rates, O2.5 rates, team-by-team averages.
  URL: soccerstats.com/latest.asp?league={league}
  Leagues available: austria, england, england2, italy, spain, germany, france, netherlands, and 50+ more.
  Use for: league-level corner/card context, identifying leagues with extreme corner or card averages.
  Access: OK (no Cloudflare).

### Tennis

- TennisExplorer
  Role: player rankings, H2H records, match schedules, results, surface form, and tournament draws.
  URL: tennisexplorer.com
  Use for: H2H matchup data, surface-specific records, recent form sequences.
  Access: OK.

- TennisAbstract
  Role: Elo ratings, serve-return profiles, surface performance, forecasts, and matchup data.
  URL: tennisabstract.com
  Use for: Elo-based forecasts, serve/return quality, break rate analysis.
  Access: OK.

- UltimateTennisStatistics
  Role: deep historical stats — Elo, serve %, return %, break rate, surface filters, H2H explorer.
  URL: ultimatetennisstatistics.com
  Use for: detailed service game and return game analysis per surface, historical Elo trends.
  Access: OK.

- TennisPrediction
  Role: model-based predictions, H2H, and match odds.
  URL: tennisprediction.com
  Use for: secondary model confirmation, H2H context.
  Access: OK.

### Basketball

- Basketball-Reference
  Role: comprehensive NBA and international stats — team/player stats, advanced metrics, pace, ratings.
  URL: basketball-reference.com
  Use for: pace, offensive/defensive ratings, historical totals averages, and matchup context.
  Access: OK.

- DunksAndThrees
  Role: NBA analytics — pace, efficiency, shooting trends, lineup data.
  URL: dunksandthrees.com
  Use for: pace and efficiency context for NBA totals.
  Access: OK.

### Hockey

- Hockey-Reference
  Role: NHL and international stats — team/player stats, advanced metrics, goalie save %.
  URL: hockey-reference.com
  Use for: team GF/GA, power play %, penalty kill %, goalie performance, shot quality.
  Access: OK.

- NaturalStatTrick
  Role: NHL advanced stats — xGF, Corsi, Fenwick, shot quality, 5v5 data, goalie performance.
  URL: naturalstattrick.com
  Use for: shot-quality and expected goals context for NHL totals and moneyline.
  Access: OK.

- MoneyPuck
  Role: NHL expected goals models, win probability, game predictions, player cards.
  URL: moneypuck.com
  Use for: model-based NHL game predictions and xG totals context.
  Access: OK.

- HockeyDB
  Role: historical hockey stats, player careers, team history.
  URL: hockeydb.com
  Use for: roster context and historical team performance.
  Access: OK.

### Baseball

- BaseballSavant (Statcast)
  Role: MLB Statcast data — exit velocity, launch angle, pitch movement, sprint speed, expected stats.
  URL: baseballsavant.mlb.com
  Use for: pitcher quality (xERA, xFIP), hitter quality (xwOBA, barrel%), and totals context.
  Access: OK.

### Volleyball

- BetExplorer (Volleyball section)
  Role: volleyball odds comparison — moneyline, set totals O/U (3.5, 4.5), point totals O/U (172.5–180.5), Asian handicap.
  URL: betexplorer.com/volleyball/
  Use for: price comparison across bookmakers including Betclic, market depth check.
  Access: OK.

- Flashscore (Volleyball section)
  Role: volleyball schedules, live scores, results, H2H.
  URL: flashscore.com/volleyball/
  Use for: fixture confirmation, results, and settlement.
  Access: OK.

- Sofascore (Volleyball section)
  Role: volleyball team form, player stats, match stats.
  URL: sofascore.com/volleyball
  Use for: form context and match analysis.
  Access: OK.

### Multi-Sport Odds and Analytics

- Covers
  Role: expert previews, odds, and picks for NBA, NHL, MLB, NFL, and more.
  URL: covers.com
  Use for: narrative and preview context for US sports.
  Access: OK.

- StatMuse
  Role: natural language sports queries — NBA, NHL, MLB, NFL stats on demand.
  URL: statmuse.com
  Use for: quick stat lookups across multiple sports.
  Access: OK.

### Blocked Sources (Cloudflare / 403)

The following were tested and are NOT accessible via Playwright headless:
- FootyStats (footystats.org) — 403
- FBRef (fbref.com) — 403
- FCTables (fctables.com) — 403
- WhoScored (whoscored.com) — 403
- KenPom (kenpom.com) — blocked
- Baseball-Reference (baseball-reference.com) — blocked
- FanGraphs (fangraphs.com) — blocked
- TeamRankings (teamrankings.com) — blocked
- ActionNetwork (actionnetwork.com) — blocked
- VolleyBox (volleybox.net) — blocked

- FCTables
  Role: football over, under, BTTS, form, and table patterns.
  Use when accessible, never as the only source.

- Action Network
  Status: not a core source in this setup because extraction reliability was poor in testing.

- Any generic 404-prone or blocked tip page
  Status: optional at best, never core.

## Sport Playbooks

- Football
  Minimum stack: Flashscore or Sofascore plus OddsPortal, Oddspedia, or BetExplorer plus one of Forebet, SportyTrader, PredictZ, or Sportsgambler when helpful.
  Preferred markets: totals, team totals, BTTS, double chance, draw no bet, and selective corners.

- Basketball
  Minimum stack: Covers or TeamRankings plus OddsPortal, Oddspedia, or BetExplorer.
  Preferred markets: totals, spreads, and selected moneylines.

- Baseball
  Minimum stack: TeamRankings or Covers plus OddsPortal, Oddspedia, or BetExplorer.
  Preferred markets: totals and selective moneylines.

- Hockey
  Minimum stack: Covers or TeamRankings plus OddsPortal, Oddspedia, or BetExplorer.
  Preferred markets: totals and selective moneylines.

- Tennis
  Minimum stack: TennisAbstract plus OddsPortal or Oddspedia plus BetExplorer or Sportsgambler when helpful.
  Preferred markets: moneyline, set handicap, game totals, and set totals.

## Settlement Sources

- Primary settlement sources: Flashscore and Sofascore.
- Secondary settlement sources: bookmaker settled market plus OddsPortal or BetExplorer archived results.
- Use two sources whenever possible.
- If only one reliable source is available, note it explicitly in the daily report and ledger notes.

## Hard Source Rules

- A final pick must have at least one Tier A stats or fixture source and one Tier A market or price source.
- Tier B sources can strengthen or weaken confidence by at most one level, but they cannot create a bet on their own.
- Community sources (bettingexpert, ProTipster, Oddspedia Community, Zawod Typer) can adjust confidence by ±1 level based on consensus alignment/divergence, but cannot be the primary reason for a pick.
- If Tier A sources materially disagree on the core read, skip the bet unless the disagreement is clearly explained and the stake is reduced.
- If the only support comes from consensus or tipster pages, skip the bet.
- If community consensus strongly diverges from Tier A direction (≥60% opposite), note the divergence in the report and investigate before proceeding.
- Record source outages and partial availability in the daily source log.
- Bookmaker bonuses, promos, and affiliate content are irrelevant to pick quality.