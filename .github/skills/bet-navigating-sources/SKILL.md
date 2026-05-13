---
name: bet-navigating-sources
description: "Navigate the betting source ecosystem — Tier A stats, Tier A markets, Tier B tipsters, Tier C specialists. Provides fallback chains per sport, blocked source lists, access notes, Playwright navigation tips, and URL patterns. Use when scanning events, fetching odds, checking tipster sites, or verifying results across 5 core sports (football, volleyball, basketball, tennis, hockey) plus archived chains for additional sports."
user-invokable: false
---

# Navigating Betting Sources

Guides agents through the multi-tier source ecosystem for all 5 core sports (football, volleyball, basketball, tennis, hockey). Ensures fallback chains are followed, blocked sources are avoided, and source-specific quirks are handled.

## Source Philosophy

Every sport has dedicated statistical databases, market sources, and prediction communities. Never reject a sport for "lack of sources" — search specialist sources instead. Every data point needs ≥2 independent confirmations.

## Source Tiers

| Tier | Role | Examples | Rule |
|------|------|----------|------|
| **A — Markets** | Execution price, odds comparison, line shopping | Betclic (execution), BetExplorer, OddsPortal, The-Odds-API, SBR, ESPN Odds, ScoresAndOdds | Backbone for pricing decisions |
| **A — Stats** | Fixtures, H2H, lineups, live stats, xG, results | Flashscore, TennisAbstract, Basketball-Reference, NaturalStatTrick | Backbone for analysis |
| **B — Tipsters** | Argument-based consensus, angle discovery, local knowledge | ZawodTyper, Typersi, OLBG, PicksWise, BetIdeas, Meczyki, Sportsgambler, Tipstrr, GosuGamers | CANNOT create a bet alone — supports/warns |
| **C — Specialists** | Sport-specific deep dives | TotalCorner, Betaminic, CueTracker, DartsOrakel, BaseballSavant, DailyFaceoff | Deep domain data |

## Blocked Sources (NEVER attempt)

Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV tips (stats pages OK).

## Fallback Chains by Sport

When a source fails (403/empty/timeout), try the next in chain immediately. All fail? Google search. After finishing other sports, RETRY failed sources (rate limits clear in 15-30 min).

### Market Sources (odds comparison)

| Sport | Primary | Secondary | Tertiary |
|-------|---------|-----------|----------|
| Football | BetExplorer | OddsPortal | The-Odds-API |
| Tennis | BetExplorer | OddsPortal | The-Odds-API |
| Basketball (EU) | BetExplorer | OddsPortal | The-Odds-API |
| Basketball (US) | SBR | ESPN Odds | ScoresAndOdds |
| Hockey | SBR | ESPN Odds | ScoresAndOdds |
| Baseball *(archived)* | SBR | ESPN Odds | ScoresAndOdds |
| Volleyball | BetExplorer | OddsPortal | — |
| Esports *(archived)* | BetExplorer | GosuGamers | — |
| Snooker/Darts *(archived)* | BetExplorer | OddsPortal | — |
| Handball *(archived)* | BetExplorer | OddsPortal | — |
| Table Tennis *(archived)* | BetExplorer | — | — |
| Padel *(archived)* | BetExplorer | — | — |
| Speedway *(archived)* | BetExplorer | — | — |
| MMA *(archived)* | BetExplorer | Tapology | — |

### Stats Sources

**PRIMARY SCAN SOURCE: Flashscore** (via `UnifiedAPIClient` in `scan_events.py`)
- Used by `scan_events.py` to discover ALL events for all 5 sports
- Deep enrichment via `get_match_preview()` (form + H2H) and `get_fixture_stats()`
- Covers: football, tennis, basketball, hockey, volleyball — global scope
- HTTP + Playwright stealth fallback, 2s rate limit between requests

**ENRICHMENT SOURCES** (used by `data_enrichment_agent.py` to fill gaps after scan):

| Sport | Primary | Secondary | Specialist |
|-------|---------|-----------|------------|
| Football | ESPN API | scores24 (HTTP) | TotalCorner (corners), TransferMarkt (roster) |
| Tennis | TennisAbstract | TennisExplorer | TennisPrediction |
| Basketball (NBA) | Basketball-Reference | ESPN | DunksAndThrees |
| Basketball (EU) | Eurobasket.com | BetExplorer standings | Flashscore H2H |
| Hockey | NaturalStatTrick (BLOCKED 403, use MoneyPuck as primary) | Hockey-Reference, MoneyPuck | DailyFaceoff (goalies) |
| Volleyball | Flashscore (scan data) | ESPN | CEV, PlusLiga |

### Tipster Sources

| Sport | Primary | Secondary | Tertiary |
|-------|---------|-----------|----------|
| Football (PL) | ZawodTyper | Typersi → Meczyki | OLBG |
| Football (INT) | PicksWise → BetIdeas | OLBG → Sportsgambler | Typersi |
| Tennis | ZawodTyper | Typersi → PicksWise | Tipstrr |
| Basketball (EU) | Sportsgambler | ZawodTyper | Typersi |
| Basketball (US) | PicksWise | Sportsgambler | OLBG |
| Volleyball | ZawodTyper → Typersi | Sportsgambler | Meczyki |
| Hockey | PicksWise | Sportsgambler | OLBG |
| Baseball | PicksWise | Sportsgambler | OLBG |
| Esports | GosuGamers | Tipstrr | BO3.gg |
| Snooker | Sportsgambler → OLBG | Tipstrr | — |
| Darts | Sportsgambler → OLBG | Tipstrr | — |
| Handball | Sportsgambler | ZawodTyper | OLBG |
| Table Tennis | Sportsgambler | OLBG | Tipstrr |
| MMA | Sportsgambler | PicksWise | Tipstrr |
| Padel | Google "[event] prediction" | Sportsgambler | — |
| Speedway | ZawodTyper | Typersi | Google "[event] tips" |

## Source-Specific Access Notes

| Source | Access | Notes |
|--------|--------|-------|
| Betclic | 403 — NO scraping | All picks CONDITIONAL. User verifies on app. |
| SoccerStats | Intermittent (HTTP 500) | Fallback: FootyStats team pages or Betaminic |
| FootyStats | 403 on main pages | Individual team pages sometimes work |
| HLTV | Partial | Stats pages OK. Tips/predictions → 403 |
| Covers | Partial | NBA pages empty. Other sections intermittent. |
| TeamRankings | Intermittent | Sometimes blocked. Do not rely as sole source. |
| NBA.com | JS-heavy | May need Playwright for rendering |
| The-Odds-API | API key required | 500 credits/month free. 30 credits/full scan. Key: `config/odds_api_key.txt` |

## Tipster Navigation Patterns

| Site | URL Pattern | Navigation Notes |
|------|------------|------------------|
| ZawodTyper | `/typy-dnia-[DD]-[month-PL]-[weekday-PL]/` | Lazy-loaded — scroll deeply. Search: `/szukaj?q=[team]` |
| Typersi | `/` (daily tips) | Click into individual match pages for arguments |
| Meczyki | `/typy-bukmacherskie` | Click individual match links for detailed arguments |
| BetIdeas | `/tips/football`, `/corner-betting-tips`, `/btts-tips` | `/tips/` alone returns 404 or horse racing |
| OLBG | `/tips` → sport → today | Each tip has written reason. Filter by competition |
| PicksWise | Sport → game preview pages | Expert analysis with per-game reasoning |
| Sportsgambler | `/predictions/today/` | Multi-sport written previews |

## Community Source Usage Rules

Community/tipster sources CANNOT create a bet on their own. Four valid uses:
1. **Consensus alignment** (+0.5 confidence): ≥70% agree with Tier A direction
2. **Consensus divergence** (−1 confidence or skip): ≥60% contradict Tier A direction
3. **Early news detection**: Injury/lineup info before Flashscore — verify with 2nd source
4. **Angle discovery**: Argument-based tipsters reveal angles stats miss (tactics, motivation, weather)

**Deep-dive required** (read FULL arguments, not bare picks): ZawodTyper, Typersi, OLBG, PicksWise, BetIdeas, Meczyki, Sportsgambler.

## American Odds Conversion

For SBR, ESPN, ScoresAndOdds:
- Positive +X → decimal = `1 + X/100` (e.g., +150 = 2.50)
- Negative −X → decimal = `1 + 100/X` (e.g., −150 = 1.667)

## The-Odds-API Usage

- Script: `python3 scripts/fetch_odds_api.py`
- Full scan: `--sports` flag or no args (all sports). ~30 credits.
- Settlement: `--scores baseball,hockey`
- List sports (free): `--list-sports`
- NOT covered: volleyball, esports, snooker, darts, table tennis, handball, padel, speedway

## Multi-Source Odds Aggregation (RECOMMENDED)

- Script: `python3 scripts/fetch_odds_multi.py --date YYYY-MM-DD`
- Aggregates 4 sources: The-Odds-API + API-Football + OddsPortal + BetExplorer
- Betclic odds are NEVER scraped (403). User verifies on app (R12).
- Output: `betting/data/odds_multi_sources.json` (provenance log with per-event source attribution)
- Uses `SPORT_SOURCE_PRIORITY` chains to select best odds per sport
- RECOMMENDED over single-source `fetch_odds_api.py` for comprehensive multi-bookmaker comparison

## Automated Tipster Aggregation

- Script: `python3 scripts/tipster_aggregator.py --date YYYY-MM-DD --workers 5`
- Fetches 12 tipster sites in parallel (5 concurrent workers):
  - ZawodTyper, Typersi, Sportsgambler, PicksWise, BetIdeas, OLBG
  - Tipstrr, Feedinco, BettingClosed, Tips180, GosuGamers
- Output: `betting/data/{date}_tipster_consensus.json` + `{date}_tipster_consensus.md`
- Runs automatically in S1b parallel enrichment step (alongside odds API + weather)
- Computes per-event consensus: agreement %, confidence adjustment, market classification
- Classifies tips as "statistical" (corners, totals, cards) vs "outcome" (ML, winner)
- Statistical market tips with data-backed arguments → §4.3 watchlist promotion candidates

**Integration with manual deep-dive (S4):**
The aggregator provides the FIRST PASS — structured picks + consensus. The `bet-scout` agent then performs the DEEP DIVE — reading full written arguments, extracting cited facts, investigating contradictions, and promoting statistical market picks to the watchlist.

## Connected Skills

- `bet-analyzing-statistics` — Consumes the statistical data collected via sources defined here
- `bet-applying-sport-protocols` — Sport-specific protocols that define which data points to collect from each source
- `bet-evaluating-odds` — Odds comparison requires the market source chains defined here
- `bet-settling-results` — Result verification sources (Flashscore, ESPN scores) for settlement
