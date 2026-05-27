# Analysis Methodology

## ULTIMATE RULE: BET STATISTICS, NOT OUTCOMES

Statistical markets (corners, fouls, shots, games, sets, points, frames, rounds) > outcome markets (ML, winner, goals). Statistical markets accumulate throughout, are driven by team STYLE (structural), survive chaos, and are systematically mispriced. Every pick must be a statistical market unless none exists.

Goal: find MISPRICED ODDS. EV > 0 is the only valid reason to bet.

## Data Architecture

Primary: SQLite `betting/data/betting.db` via `from bet.db.connection import get_db`
Secondary: JSON files for human-readable debug.

**Key Tables:**
- `fixtures` — events for betting day
- `odds_history` — odds from all sources
- `team_form` — L10/L5/H2H per team
- `match_stats` — per-match raw stats
- `analysis_results` — S3 output (market rankings, safety scores)
- `gate_results` — S7 output (approved/extended/rejected)
- `coupons` + `bets` — placed bets
- `league_profiles` — Bayesian priors per competition
- `athletes` (6,648) — player profiles
- `player_gamelogs` (25,943) — game-by-game individual stats
- `player_splits` (4,716) — home/away, wins/losses splits
- `standings` (233) — enriched league standings
- `team_ats_records` — Against The Spread records
- `team_ou_records` — Over/Under records (CRITICAL for totals)
- `power_index` — ESPN power rankings
- `espn_predictions` — BPI win probability

**Gateway:** `scripts/db_data_loader.py` — all DB read/write functions.

## Sport Tiers

ALL 5 sports are Tier 1 (full analysis): Football, Volleyball, Basketball, Tennis, Hockey.
Esports (CS2, Dota 2, Valorant) also covered.

**League depth:** Go beyond top leagues. 2nd/3rd divisions, cups, women's, youth, regional. Every sub-page.

**Data quality (R14):** FULL ≥7/10, PARTIAL 4-6/10, MINIMAL <4/10. Only FULL/PARTIAL in core coupons.

## Hallucination Prevention

**Tennis:** hallucination_risk=HIGH → only markets with real_data_keys. No invented serve stats.
**Volleyball:** hallucination_risk=HIGH → only Total Points O/U and Sets O/U.
**Hockey:** hallucination_risk=HIGH → only Total Goals O/U and Total Shots O/U.

Rule: Before citing any number, ask "Can I trace this to a file/DB query?" If NO → DELETE it.

## Safety Score

safety = f(L10_consistency, H2H_alignment, L5_trend, league_profile_prior)
Three-way cross-check: L10 + H2H + L5 must align. If 2/3 contradict → FLAG CONFLICTED.

## Market Ranking Protocol (§3.0)

For each candidate:
1. List all available statistical markets
2. Calculate safety_score for each
3. Rank by safety DESC
4. Top-ranked market = primary recommendation
5. If top market has safety < 0.30 → candidate is Extended Pool material
