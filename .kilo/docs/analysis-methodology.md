# Analysis Methodology — Compact Reference

## Hallucination Prevention (ALL agents — mandatory)
| Sport | Risk | ONLY analyze |
|-------|------|-------------|
| Tennis | HIGH | Markets with real L10 games data per player |
| Volleyball | HIGH | Total Points O/U + Sets O/U |
| Basketball | HIGH | Total Points O/U + Handicap |
| Hockey | HIGH | Total Goals O/U + Total Shots O/U |
| Esports | HIGH | Match Winner (unless map_win_rate exists) |

## Data Depth Minimums
| Dimension | Minimum | Below = Flag |
|-----------|---------|-------------|
| L10 | ≥8 data points | PARTIAL quality |
| H2H | ≥3 meetings | H2H-BLIND (×0.7 safety penalty) |
| L5 | ≥4 data points | PARTIAL quality |

## ULTIMATE RULE: BET STATISTICS, NOT OUTCOMES
Statistical markets (corners, fouls, shots, games, sets, frames) > outcome markets (ML, winner, goals).
Statistical markets accumulate, are style-driven, shock-resistant, and mispriced.

## Data Architecture
- Primary: SQLite `betting/data/betting.db`. JSON/MD secondary.
- Key tables: fixtures, odds_history, team_form, match_stats, analysis_results, gate_results, coupons, bets.
- Gateway: `scripts/db_data_loader.py` — all DB read/write functions.

## Sport Tiers (ALL are Tier 1)
Football, Volleyball, Basketball, Tennis, Hockey — scan ALL leagues/divisions deeply.

## Hallucination Prevention
- Tennis `hallucination_risk=HIGH`: ONLY analyze markets with real L10 data.
- Volleyball HIGH: ONLY Total Points O/U and Sets O/U.
- Hockey HIGH: ONLY Total Goals O/U and Total Shots O/U.
- Basketball HIGH: ONLY Total Points O/U and Handicap.
- Esports HIGH: ONLY Match Winner (unless map_win_rate exists).

## §3.0 Market Ranking Protocol
1. List ALL bettable statistical markets for the sport.
2. Collect per market: L10 avg, H2H avg, L5 avg, bookmaker line, hit rate.
3. Safety score = min(hit_rate_L10, hit_rate_H2H). Higher = safer.
4. Rank and pick TOP market by safety score.
5. Three-Way Cross-Check: L10 + H2H + L5 must align. 2/3 conflict → DOWNGRADE. 3/3 → REJECT.

## §3.0c H2H Market-Specific Validation
H2H data MUST exist for the SPECIFIC stat being bet. Missing → H2H-STAT-BLIND, -0.5 confidence, no LR coupon.

## Pipeline Scripts
| Step | Script | Output |
|------|--------|--------|
| S3 | deep_stats_report.py | analysis_results DB + JSON/MD |
| S7 | gate_checker.py | gate_results DB + JSON/MD |
| S8 | coupon_builder.py | coupons/ JSON/MD |

## Scanning Mandate
- ALL 5 sports every run. ≥50 events scanned. ≥3 sports in final picks.
- NO AUTO-REJECTION. All events shown in matrix. User decides.
- Major tournaments: NEVER SKIP. Protected leagues: +10 score boost.
- Source fails → next in chain → Google → retry after 15 min.

## Probability Engine (Poisson)
- λ = 40% × L5_avg + 35% × L10_avg + 25% × H2H_avg
- P(Over X.5) = 1 - CDF(X, λ). Fair odds = 1/P(hit). EV = P(hit) × odds - 1.
- Kelly 1/4: stake = bankroll × f / 4 where f = (b×p - q) / b.
