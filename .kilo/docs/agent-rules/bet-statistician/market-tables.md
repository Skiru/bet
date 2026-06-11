# Market Calculation Tables — Statistician Reference

## Bettable Statistical Markets by Sport

### Football
Fouls O/U, Cards O/U, Corners O/U, Shots O/U, Shots on Target O/U, Throw-ins O/U,
Goal kicks O/U, Offsides O/U, Goals O/U, BTTS, Team corners O/U, Team cards O/U.
**Hierarchy:** Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → 1X2

### Tennis
Total Games O/U, Total Sets O/U, Player Games O/U, Game Handicap, Set Handicap,
Tiebreak O/U, Aces O/U (when data exists).
**Hierarchy:** Games → Sets → HC → ML

### Basketball
Total Points O/U, Team Total O/U, Quarter Totals O/U, Half Totals O/U, Rebounds O/U,
3-Pointers Made O/U, Handicap/Spread.
**Hierarchy:** Team totals → Quarter → Game total → Spreads → ML

### Volleyball
Total Points O/U, Sets O/U, Set Handicap, Team Points in Set O/U.
**Hierarchy:** Total Points → Sets → Set HC → ML

### Hockey
Total Shots O/U, Total Goals O/U, Period Goals O/U, Hits O/U, Blocks O/U, PIM O/U, PP Goals.
**Hierarchy:** Shots → Goals → Period goals → ML

### Esports (CS2/Valorant/Dota 2)
Total Rounds O/U, Map Rounds O/U, Total Maps O/U, Map Handicap, Total Kills O/U.
**Hierarchy:** Rounds → Maps → Map HC → ML

## Safety Score Calculation
```
safety = min(hit_rate_L10, hit_rate_H2H)
margin_over = (avg / line) - 1  (bigger = more buffer)
margin_under = (line / avg) - 1  (bigger = more buffer)
tiebreaker: higher margin wins when safety scores equal
```

## Probability Engine (Poisson/NegBin)
- λ = 0.40 × L5_avg + 0.35 × L10_avg + 0.25 × H2H_avg
- When H2H missing: λ = 0.55 × L5_avg + 0.45 × L10_avg
- Bayesian shrinkage: adjusted_λ = (games × λ + 5 × league_avg) / (games + 5)
- P(Over X.5) = 1 - Σ(k=0..X) [e^(-λ) × λ^k / k!]
- Overdispersed (variance/mean > 1.5) → negative binomial
- Fair odds = 1 / P(hit). EV = P(hit) × bookmaker_odds - 1.
