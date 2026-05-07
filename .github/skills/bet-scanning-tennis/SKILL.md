---
name: bet-scanning-tennis
description: "Tennis-specific scanning — source URLs, adapter mappings, data quality requirements, timeouts, fallback chains, and validation rules."
user-invokable: false
---

# Scanning Tennis

## Source URLs

| URL | Domain | Role | Notes |
|-----|--------|------|-------|
| https://www.flashscore.com/tennis/ | flashscore.com | Fixtures | All ATP/WTA/ITF levels |
| https://www.flashscore.com/tennis/atp-singles/ | flashscore.com | Fixtures | ATP singles |
| https://www.flashscore.com/tennis/wta-singles/ | flashscore.com | Fixtures | WTA singles |
| https://www.flashscore.com/tennis/atp-doubles/ | flashscore.com | Fixtures | ATP doubles |
| https://www.tennisexplorer.com/ | tennisexplorer.com | Stats | Surface detection, match details |
| https://www.tennisexplorer.com/matches/ | tennisexplorer.com | Stats | Today's matches with surface |
| https://www.tennisabstract.com/reports/atp_elo_ratings.html | tennisabstract.com | Stats | ATP Elo ratings per-surface |
| https://www.tennisabstract.com/reports/wta_elo_ratings.html | tennisabstract.com | Stats | WTA Elo ratings per-surface |
| https://www.atptour.com/en/scores/current | atptour.com | Official | Current tournament scores |
| https://www.betclic.pl/tenis-s2 | betclic.pl | Execution | ⚠ Always 403 |
| https://www.oddsportal.com/tennis/ | oddsportal.com | Odds | Tennis odds comparison |
| https://www.forebet.com/en/tennis/predictions-today | forebet.com | Predictions | Probabilities |
| https://scores24.live/en/tennis | scores24.live | Deep | H2H + form data |

## Adapter Mapping

| Domain | Adapter | Expected Output Fields |
|--------|---------|----------------------|
| flashscore.com | `flashscore_adapter` | player1, player2, time, tournament |
| tennisexplorer.com | `tennisexplorer_adapter` | surface (clay/hard/grass), tournament tier |
| tennisabstract.com | `tennisabstract_adapter` | Elo ratings per-surface (518 players) |
| oddsportal.com | `oddsportal_adapter` | match_winner odds, set betting |
| scores24.live | `scores24_adapter` | H2H data, form, trends |
| forebet.com | `forebet_adapter` | prediction probabilities |
| betclic.pl | `betclic_adapter` | decimal odds |

## Data Quality Standards

- **Minimum events per day:** 30
- **Required stat keys:** games_won, sets_won, total_sets
- **Missing keys (known gap):** aces, double_faults, first_serve_pct, break_points_won
- **Multi-source threshold:** ≥2 sources confirming each event
- **Data freshness:** Same-day data only
- **Elo data:** 518 ATP+WTA players with per-surface ratings
- **H2H source:** Scores24 detail pages (ESPN tennis H2H is empty)

## Timeout Configuration

| Domain | Per-page Timeout | Delay Between Pages | Max Concurrent |
|--------|-----------------|--------------------:|---------------:|
| flashscore.com | 30s | 1s | 3 |
| tennisexplorer.com | 30s | 2s | 2 |
| tennisabstract.com | 20s | 1s | 2 |
| atptour.com | 30s | 2s | 1 |
| oddsportal.com | 20s | 1s | 2 |
| scores24.live | 20s | 1s | 2 |
| forebet.com | 20s | 1s | 2 |

**Total scanner timeout:** 5 minutes

## Fallback Chains

**Market odds:**
1. BetExplorer → 2. OddsPortal → 3. The-Odds-API

**Statistical data:**
1. TennisAbstract (Elo) → 2. TennisExplorer (surface/match detail) → 3. Scores24 (H2H)

**Tipsters:**
1. ZawodTyper → 2. Typersi/PicksWise → 3. Tipstrr

## Seasonal Considerations

- **ATP/WTA Tour:** Year-round (Australian Open Jan, Roland Garros May-Jun, Wimbledon Jul, US Open Aug-Sep)
- **Off-season:** Very brief (late Nov to early Jan, some exhibitions)
- **Surface rotation:** Hard (Jan-Mar, Aug-Nov) → Clay (Apr-Jun) → Grass (Jun-Jul) → Hard (Aug-Nov)
- **ITF events:** Daily, year-round (lower tier, less data)
- **Doubles:** Less coverage, fewer stats sources

## Known Issues

- **ESPN tennis gap:** Only returns sets_won/games_won/total_sets (3/7 keys). Missing aces, DFs, first serve %, break points.
- **H2H empty from ESPN:** Must use Scores24 detail pages for tennis H2H data.
- **TennisAbstract Elo not integrated:** Collected at `betting/data/tennisabstract.com/` but not yet fed into safety scores or probability engine.
- **Surface matters:** Clay specialists vs hard court — surface detection via TennisExplorer is critical for analysis.
- **Qualifier rounds:** Many matches feature qualifiers with zero historical data.
- **Walkovers/retirements:** Tennis has high withdrawal rate — check for WO/RET status.
