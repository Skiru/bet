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

| Domain | Adapter | Expected Output Fields | Live Test |
|--------|---------|----------------------|-----------|
| flashscore.com | `flashscore_adapter` | player1, player2, time, tournament | Standard |
| tennisexplorer.com | `tennisexplorer_adapter` | home, away, match_url, period_scores, source_type="tennisexplorer" | **302 matches/page, 94% match_url coverage** |
| tennisabstract.com | `tennisabstract_adapter` | Elo ratings per-surface, source_type="tennisabstract_elo", `_elo_only=True` | **518 ATP + 542 WTA** |
| atptour.com | `atptour_adapter` | scores, rankings, draw brackets, source_type="atptour" | **Needs Playwright (403 with requests)** |
| oddsportal.com | `oddsportal_adapter` | match_winner odds, set betting | Standard |
| scores24.live | `scores24_adapter` | H2H data, form, trends | Standard |
| forebet.com | `forebet_adapter` | prediction probabilities | Standard |
| betclic.pl | `betclic_adapter` | decimal odds | ⚠ Always 403 |

### Adapter Architecture

- **TennisExplorer** uses **two rows per match** (one row per player) — adapter pairs consecutive player rows
- **TennisAbstract** returns **Elo records** (not fixtures) — quarantined with `_elo_only=True`, fetched separately via `scripts/fetch_tennis_elo.py`
- **ATP Tour** requires Playwright for JS-rendered content
- **Player detection** uses `/player/` href pattern (562 links/page), with bookmaker link filtering and seed number stripping
- **Deep link patterns** registered in `deep_link_discovery.py` for `/match-detail/`, `/head-to-head/`, tournament pages

## Data Quality Standards

- **Minimum events per day:** 30
- **Required stat keys:** `games_won`, `sets_won`, `total_games` (reliably produced by ESPN linescores)
- **Desired stat keys:** `aces`, `double_faults`, `first_serve_pct`, `break_points_won` (present when ESPN has detailed match stats)
- **Multi-source threshold:** ≥2 sources confirming each event
- **Data freshness:** Same-day data only
- **Elo data:** 518 ATP + 542 WTA players with per-surface ratings (hard_elo, clay_elo, grass_elo)
- **H2H sources:** ESPN athlete-vs-athlete API (wired via `enrich_tennis_stats.py`), Scores24 detail pages
- **Surface normalization:** `surface` field now in normalization whitelist (T2 fix)
- **Stat validation:** `tennis_scanner.py` `validate_event()` reports stat_coverage ratio and missing keys

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

- **ESPN tennis gap:** Only returns sets_won/games_won/total_games (3/7 keys) from linescores. Detailed match stats (aces, DFs, serve %) available for ~43% of matches.
- **H2H via ESPN:** Wired through `enrich_tennis_stats.py` → `ESPNStatsClient.get_h2h_athletes()`. Works when athlete IDs are resolvable.
- **TennisAbstract Elo integration:** Fetched via `scripts/fetch_tennis_elo.py`, cached at `betting/data/stats_cache/tennis_elo/`. Wired into data quality score via `compute_safety_scores.py` `has_elo` parameter and `lookup_tennis_elo()` function.
- **Surface detection:** TennisExplorer doesn't embed surface in match table rows — surface comes from tournament detail pages via deep links or enrichment.
- **ATP Tour 403:** `atptour.com` blocks requests-based fetching. Must use Playwright (browser rendering) for ATP Tour data.
- **Qualifier rounds:** Many matches feature qualifiers with zero historical data.
- **Walkovers/retirements:** Tennis has high withdrawal rate — check for WO/RET status. `_is_player_name` skips "Retired", "Walkover" labels.
- **Bookmaker link noise:** TennisExplorer embeds bookmaker links (bet365, 1xBet, Unibet, bwin) in match rows — adapter filters these via regex + skip list.

## Deep Data Requirements (v4 Pipeline)

For every scanned fixture, the scanner MUST attempt to collect:
1. H2H between players (last 5 meetings minimum) with per-stat breakdowns
2. Recent form (last 10 matches) with opponents, results, scores  
3. Current ranking and recent ranking trajectory
4. Key injuries/fitness concerns
5. Per-match statistical data (not just averages)

## Data Quality Validation

After scan completes, validate per fixture:
- Has ≥2 independent source confirmations?
- Has form data for BOTH players?
- Has at least 1 statistical data source (API or deep parse)?
- THINK IN THE MIDDLE: use sequentialthinking to evaluate scan quality
