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
  Role: community tipster support.
  Use for: sentiment check only.

- ProTipster
  Role: community and tipster aggregation.
  Use for: sentiment check only.

- Oddspedia Community
  Role: consensus and popularity.
  Use for: sentiment check only.

- Zawod Typer
  Role: local market awareness and tip aggregation.
  Use for: secondary or sentiment support only.

## Optional or Fragile Sources

- Understat
  Role: football xG and xGA.
  Use when accessible, especially for stronger football shot-quality context.

- WhoScored
  Role: football ratings and match stats.
  Use when accessible, never as the only source.

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
- If Tier A sources materially disagree on the core read, skip the bet unless the disagreement is clearly explained and the stake is reduced.
- If the only support comes from consensus or tipster pages, skip the bet.
- Record source outages and partial availability in the daily source log.
- Bookmaker bonuses, promos, and affiliate content are irrelevant to pick quality.