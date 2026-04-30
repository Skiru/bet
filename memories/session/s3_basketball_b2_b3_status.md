# Session: S3 Deep Stats B2-B3 Basketball

## Completed
- **B2: Detroit Pistons vs Orlando Magic** (NBA Playoffs R1 Game 2)
  - Full 10-section §S3 analysis written to `20260429_s3_deep_stats.md`
  - Safety scores via `compute_safety_scores.py` — JSON input: `stats_input_b2_det_orl.json`
  - Top market: Total Points Over 210.5 (safety 0.60, 3/3 alignment)
  - Alt: ORL Team Total Over 105.5 (safety 0.60, 3/3 alignment)
  - KEY RISK: Playoff Game 1 was only 182 total (vs 225 reg season H2H avg)

- **B3: Cleveland Cavaliers vs Toronto Raptors** (NBA Playoffs R1 Game 2)
  - Full 10-section §S3 analysis written to `20260429_s3_deep_stats.md`
  - Safety scores via `compute_safety_scores.py` — JSON input: `stats_input_b3_cle_tor.json`
  - Top market: TOR Team Total Over 107.5 (safety 0.67, 3/3 alignment)
  - Alt: CLE Points Allowed Over 109.5 (safety 0.67, 3/3 alignment)
  - KEY RISK: Quickley OUT (16.4 PPG) for series + playoff scoring drop

## Data Sources Used
- Basketball-Reference: DET/2026, ORL/2026, CLE/2026, TOR/2026
  - Full L10 game logs, season stats, H2H, injuries, roster
- Flashscore: Euroleague fixtures/results, Eliteserien fixtures/standings

## Blocked Sources
- SoccerStats: Cookie consent walls on ALL pages (England, Norway, Portugal, Brazil)
- FBref: HTTP 403 on Eliteserien stats page
- EuroleagueBasketball.net: Cookie wall, no data returned
- API quotas: ALL exhausted (api-football 100/100, api-basketball 100/100, api-hockey 100/100)

## Remaining (not completed)
- **B1: Real Madrid vs Hapoel Tel Aviv** — Euroleague data limited to recent scores/bracket
- **B4: Le Mans vs JL Bourg** — No LNB Pro A data fetched
- **F6-F10: Football** — Only goals/form data from Flashscore; NO corners/fouls/cards
  - F7 (Tromsø vs Brann): Tromsø 1st (19pts, 6W1D, 14:2), beat Brann 2-1 away already
  - Brann struggling (1W 1D 4L visible)
- Other sports: Snooker, Hockey, Volleyball, Handball, Speedway, MLB, Esports

## Key Findings
- Both NBA Playoff Game 1s had identical 182-point totals — massive scoring drop from regular season
- CLE scores only 100.3 PPG vs TOR (vs 120.4 general) — TOR dominates this matchup
- DET lost Game 1 despite being #1 seed (60-22) — ORL's deep roster (Banchero, Bane, Wagner) competitive
- TOR's Quickley OUT is a major factor for B3 analysis
