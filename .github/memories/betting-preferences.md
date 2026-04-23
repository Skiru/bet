# User Betting Preferences

## Core Philosophy
- Deep statistical analysis across ALL leagues and sports, not just top matches
- Statistical markets are PRIMARY — corners, cards, fouls, shots BEFORE goals
- Goals markets (O2.5, U2.5) are SECONDARY fallback only when no statistical markets available
- Less popular leagues = better value (Austrian BL, Championship, lower divisions)
- Pattern-based: find teams/leagues with extreme statistical profiles (high corners, leaky defense, etc.)
- Multi-sport always: football + volleyball + tennis + basketball + hockey + baseball
- 5 coupons preferred output format

## Market Hierarchy (football)
1. Corners (match, 1H, team) — PRIMARY
2. Cards (match, team) — PRIMARY
3. Fouls (match, team) — PRIMARY
4. Shots (match, team) — PRIMARY
5. BTTS — SECONDARY
6. Under 2.5 (defensive profiles) — SECONDARY
7. Team totals — SECONDARY
8. Double chance / Draw no bet — SECONDARY
9. Over 2.5 goals — LAST RESORT

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
- HTML snapshots in betting/data/betclic_verify/ are valid source for odds verification
- Use verify_betclic_odds.py script for automated verification
