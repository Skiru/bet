# Sport-Specific Protocols — Compact Reference

## Football §3.1
**Market hierarchy:** Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2
**Required stats:** Goals (scored/conceded, O2.5%, BTTS%), xG, Corners (team/match avg, hit rates), Cards (team/opp), Fouls (committed/drawn), Shots (total/SOT/conversion), Possession.
**Corner stack:** TotalCorner + SoccerStats + Betclic Statystyki (if available).
**§3.1M table:** Calculate Fouls, Cards, Corners, Shots, Team CK, Goals — pick highest safety.
**Close Game Rule (ZT#24):** P(draw) ≥ 25% + fouls/cards UNDER + avg within ±1.5 of line → DO NOT BET. Pick corners/shots.
**Context:** Coach change, injuries, congestion (<72h), motivation, weather, referee.

## Tennis §3.2
**Market hierarchy:** Total Games O/U → Sets O/U → Game Handicap → ML
**Required stats:** Service hold %, break rate, tiebreak win%, L10 games avg, surface win%.
**Surface matters:** Filter H2H by surface. Clay specialist vs hard-court specialist = mismatch.
**STRONG/GOOD/BORDERLINE grades:** odds ratio ≤1.15 STRONG, 1.16-1.30 GOOD, 1.31-1.50 BORDERLINE, >1.50 REJECT.

## Basketball §3.3
**Market hierarchy:** Team totals → Quarter totals → Game total → Handicap → ML
**Required stats:** Points/game, pace, off/def rating, 3PT%, FT%, rebounds, recent form L5.
**NBA ranges:** 100-130 pts/team, 190-240 total. Euroleague: 70-95 pts, 140-180 total.
**ESPN enrichment:** Use gamelogs for star player consistency. Variance >8 pts/game → LOWER safety.

## Volleyball §3.4
**Market hierarchy:** Total Points O/U → Sets O/U → Set Handicap → ML
**Required stats:** Sets won/lost, total points, aces, blocks (when available).
**Ranges:** 140-220 points (3-set), 200-280 (5-set). Aces: 2-10/team. Blocks: 5-15/team.

## Hockey §3.5
**Market hierarchy:** Total Shots O/U → Total Goals O/U → Period goals → ML
**Required stats:** Goals/game, shots/game, PP%, PK%, save%, hits, blocks.
**NHL ranges:** 2-4 goals/team, 25-40 shots/team. European: 2-5 goals.
**Goalie check:** If starter has 2+ games with <0.880 save% → Under less reliable.

## Esports §3.6
**CS2:** Total Rounds O/U → Map Winner → Match Winner. Check map pool, veto patterns.
**Dota 2:** Total Kills O/U → Map Duration O/U → ML. Meta-dependent.
**Valorant:** Map Rounds O/U → Map Winner → ML. Agent composition matters.

## §6.5 Upset Risk
Score each candidate. High upset → ML BANNED, stats only. 
Paradox: High upset → OVER premium (competitive). Low upset → UNDER bias (blowout).

## §7.3 Red Flags (instant — 30 seconds each)
Any fired → REJECT or DOWNGRADE. Sport-specific lists in full protocol document.
