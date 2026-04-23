# User Betting Preferences

## Core Philosophy
- **STATYSTYKI SĄ NAJWAŻNIEJSZE — to zasada #1 i jest bezwzględna**
- BTTS i Over/Under goli to NIE SĄ rynki statystyczne — to rynki golowe. UNIKAĆ.
- Deep statistical analysis across ALL leagues and sports, not just top matches
- Statistical markets are PRIMARY — corners, cards, fouls, shots BEFORE goals
- Goals markets (O2.5, U2.5, BTTS) are LAST RESORT only when NO statistical market exists AND no other match has stats
- Less popular leagues = better value (Austrian BL, Championship, lower divisions)
- Pattern-based: find teams/leagues with extreme statistical profiles (high corners, leaky defense, etc.)
- Multi-sport always: football + volleyball + tennis + basketball + hockey + baseball
- 5 coupons preferred output format
- If today's board has no corners/cards → look at esports (map totals), snooker (frames), tennis (games), volleyball (sets) BEFORE using BTTS/goals

## Market Hierarchy per Sport — AGENT MUST FIGURE THIS OUT INDEPENDENTLY
Agent must proactively identify which statistical markets are most inefficient per sport.
User does NOT tell you what to bet — YOU research and decide based on data.

### Football
1. Corners (match, 1H, team, Asian line) — PRIMARY
2. Cards (match, team, player) — PRIMARY
3. Fouls (match, team) — PRIMARY
4. Shots on target / total shots — PRIMARY
5. Team totals (goals per team) — SECONDARY
6. BTTS — LAST RESORT
7. Over/Under goals — LAST RESORT

### Tennis
1. Total games (O/U 20.5, 21.5, 22.5) — PRIMARY
2. Set totals (O/U 2.5 sets) — PRIMARY
3. Games handicap (-3.5 games etc.) — PRIMARY
4. Aces / double faults (where available) — PRIMARY
5. Set handicap — SECONDARY
6. ML (only 1.50-2.50 range with Elo/surface backing) — SECONDARY

### Basketball (NBA)
1. Total points (match O/U) — PRIMARY
2. Spreads / handicaps — PRIMARY
3. Quarter totals (Q1/Q3 O/U) — PRIMARY
4. Team totals (over X.5 pts per team) — PRIMARY
5. Player props (rebounds, assists) — if available on Betclic
6. ML — LAST RESORT

### Hockey (NHL)
1. Total goals (O/U 5.5, 6.5) — PRIMARY
2. Period totals (P1 O/U 1.5) — PRIMARY
3. Shots on goal (team/match) — PRIMARY (where available)
4. ML (only with goalie confirmation + form) — SECONDARY

### Volleyball
1. Total sets (O/U 3.5) — PRIMARY
2. Total points (O/U 170.5 etc.) — PRIMARY
3. Set handicap (-1.5 sets) — PRIMARY
4. Individual set score (O/U 44.5 pts in set 1) — PRIMARY
5. ML — SECONDARY (only heavy favorites)

### Snooker
1. Total frames (O/U) — PRIMARY
2. Frame handicap (-2.5 frames) — PRIMARY
3. Century breaks (O/U) — if available
4. ML — SECONDARY

### Esports (CS2/LoL/Dota2/Valorant)
1. Map totals (O/U 2.5 maps) — PRIMARY
2. Map handicap (-1.5 maps) — PRIMARY
3. Total rounds (O/U 26.5 rounds per map) — PRIMARY
4. ML — SECONDARY (only with strong form data)

### Darts
1. Total legs (O/U) — PRIMARY
2. 180s (O/U) — PRIMARY
3. Checkout percentage — if available
4. ML — SECONDARY

### Handball
1. Total goals (O/U 50.5) — PRIMARY
2. Handicap — PRIMARY
3. Half totals — PRIMARY

### Table Tennis
1. Total points — PRIMARY
2. Set handicap — PRIMARY
3. ML — SECONDARY

### MMA/UFC
1. Method of victory (KO/TKO, submission, decision) — PRIMARY
2. Over/Under rounds — PRIMARY
3. ML — SECONDARY

### Baseball (MLB)
1. Total runs (O/U) — PRIMARY
2. Run line (handicap) — PRIMARY
3. First 5 innings (F5 O/U) — PRIMARY
4. ML — SECONDARY (only with starting pitcher analysis)

## Source Stack (football corners)
Three sources required for high-confidence corner pick:
1. TotalCorner — match-level corner totals and handicaps
2. SoccerStats — league-level corner rankings and averages
3. Betclic Statystyki — verified odds from HTML snapshots (EPL, LaLiga, Bundesliga only)

## What User Does NOT Want
- Generic O2.5 goals as the default pick
- Popular matches everyone bets on without deep analysis
- Lazy single-source analysis
- Blocked sources (Forebet, Windrawwin, etc.) — see source-registry.md
- Same-sport-only coupons when multi-sport is possible

## Workflow
- Agent provides picks with minimum acceptable odds
- User checks on Betclic app and reports actual odds
- Agent substitutes if Betclic odds fall below threshold
- CONDITIONAL picks: mark with min threshold, user verifies

## Bankroll
- Working bankroll: ~32 PLN (check actual balance)
- Daily cap: 4-8 PLN (from config)
- Max single stake: 2.00 PLN
- Preferred: leave unused bankroll if board is weak

## Betclic Technical Notes
- Statystyki tab: corners/cards/fouls/shots — only EPL, LaLiga, Bundesliga
- Championship, Austrian BL, Coppa Italia, Coupe de France: NO Statystyki tab
- Rate limit: 403 after ~20-30 Playwright requests. Clears after ~15 min.
- DO NOT scrape Betclic for odds. All picks use CONDITIONAL thresholds — user verifies on app.
