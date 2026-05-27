---
name: bet-navigating-sources
description: "Navigate the betting source ecosystem — Tier A stats, Tier A markets, Tier B tipsters, Tier C specialists. Provides fallback chains per sport, blocked source lists, access notes, Playwright navigation tips, and URL patterns. Use when scanning events, fetching odds, checking tipster sites, or verifying results across 5 core sports (football, volleyball, basketball, tennis, hockey) plus 3 esports (CS2, Dota 2, Valorant)."
user-invokable: false
---

# Navigating Betting Sources

Guides agents through the multi-tier source ecosystem for all 5 core sports + 3 esports (football, volleyball, basketball, tennis, hockey, CS2, Dota 2, Valorant). Ensures fallback chains are followed, blocked sources are avoided, and source-specific quirks are handled.

## Source Philosophy

Every data point needs ≥2 independent confirmations. Never reject a sport for "lack of sources" — search specialist sources. DB-first: check `team_form` and `stats_cache` before hitting external sources.

## Source Tiers

| Tier | Role | Examples | Rule |
|------|------|----------|------|
| **A — Markets** | Execution price, odds comparison, line shopping | Betclic (execution), BetExplorer, OddsPortal, The-Odds-API, SBR, ESPN Odds, ScoresAndOdds | Backbone for pricing decisions |
| **A — Stats** | Fixtures, H2H, lineups, live stats, xG, results | Flashscore, TennisAbstract, Basketball-Reference, MoneyPuck | Backbone for analysis |
| **B — Tipsters** | Argument-based consensus, angle discovery, local knowledge | ZawodTyper, Typersi, OLBG, PicksWise, BetIdeas, Meczyki, Sportsgambler, Tipstrr, GosuGamers | CANNOT create a bet alone — supports/warns |
| **C — Specialists** | Sport-specific deep dives | TotalCorner, Betaminic, DailyFaceoff, MoneyPuck, TennisAbstract | Deep domain data |

## Blocked Sources (NEVER attempt)

Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV tips (stats pages OK).

## Fallback Chains by Sport

When a source fails (403/empty/timeout), try the next in chain immediately. All fail? Google search. After finishing other sports, RETRY failed sources (rate limits clear in 15-30 min).

### Market Sources (odds comparison)

*Note: OddsPortal and BetExplorer are for manual/browser-only line shopping (or fixture stubs) and are no longer part of the automated odds fetching pipeline.*

| Sport | Primary | Secondary | Tertiary |
|-------|---------|-----------|----------|
| Football | The-Odds-API | odds-api.io | API-Football-Odds |
| Tennis | The-Odds-API | odds-api.io | — |
| Basketball (EU) | The-Odds-API | odds-api.io | — |
| Basketball (US) | SBR | ESPN Odds | ScoresAndOdds |
| Hockey | The-Odds-API | odds-api.io | SBR |
| Volleyball | odds-api.io | — | — |
| CS2 | bo3.gg (Playwright) | — | — |
| Valorant | bo3.gg (Playwright) | — | — |

### Stats Sources

**PRIMARY SCAN SOURCE: Event Discovery Module** (via `src/bet/discovery/` and `discover_events.py`)
- Discover ALL events for all 5 sports using 3 active APIs: Odds-API.io (primary, all 5 sports) + The-Odds-API (secondary, 4 sports w/ odds) + API-Football (tertiary, football)
- SofaScore adapter disabled (403 blocked). Deep enrichment (form, H2H, lineups) is handled SEPARATELY by scrapers/enrichment agent.

**ENRICHMENT SOURCES** (used by `data_enrichment_agent.py` to fill gaps after scan):

| Sport | Primary | Secondary | Specialist |
|-------|---------|-----------|------------|
| Football | ESPN API (70+ leagues, play-by-play) | scores24 (HTTP) | TotalCorner (corners), TransferMarkt (roster) |
| Tennis | TennisAbstract | TennisExplorer | TennisPrediction |
| Basketball (NBA) | ESPN API (coaches, gamelogs, futures, ATS/OU) | Basketball-Reference | DunksAndThrees |
| Basketball (EU) | Eurobasket.com | BetExplorer standings | Flashscore H2H |
| Hockey | ESPN API (coaches, gamelogs, futures), api-hockey (per-game) | MoneyPuck (xG/Corsi — advisory only), Hockey-Reference | DailyFaceoff (goalies) |
| Volleyball | Flashscore (scan data) | ESPN | CEV, PlusLiga |
| CS2 | bo3.gg (Playwright — H2H, map pool) | HLTV.org (Cloudflare fallback) | Liquipedia (rosters) |
| Valorant | bo3.gg (Playwright) + VLR.gg (stats) | — | Liquipedia (rosters) |
| Dota 2 | OpenDota API | Dotabuff | Liquipedia (rosters) |

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
| Esports | GosuGamers | — | — |

## Google Sports / SerpAPI (H2H Enrichment)

**Module:** `src/bet/api_clients/google_sports_client.py` (canonical; `scripts/api_clients/` is a shim)
**Purpose:** H2H data retrieval via SerpAPI (Google search for "Team A vs Team B")
**Budget:** 15 queries/run, 250/month (shared SerpAPI free tier)
**Cache:** 48h cache in DB (`team_form.h2h_values` with `h2h_opponent_id`)
**Position in fallback chains:** After sport-specific APIs (ESPN, API-Football, etc.), before Flashscore curl_cffi last resort
**Data returned:** H2H scores, dates, competitions, recent form stats
**Triggered by:** `enrich_h2h()` in `data_enrichment_agent.py` when H2H data missing from DB
**DB function:** `db_data_loader.load_h2h_from_db(team_a, team_b, sport)` — reads cached H2H

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

→ See `bet-evaluating-odds` for conversion formulas (American → decimal).

## Odds Scripts

| Script | Purpose | Output |
|--------|---------|--------|
| `python3 scripts/fetch_odds_api.py` | The-Odds-API (~30 credits/scan) | `betting/data/odds_api_snapshot.json` |
| `python3 scripts/fetch_odds_api.py --scores hockey` | Settlement scores | JSON scores |
| `python3 scripts/fetch_odds_multi.py --date YYYY-MM-DD` | 3-source aggregation (the-odds-api + odds-api-io + api-football-odds) | `betting/data/odds_api_snapshot.json` |
| `python3 scripts/fetch_odds_api.py --list-sports` | List available sports (free) | stdout |

## Automated Tipster Aggregation

- Script: `python3 scripts/tipster_aggregator.py --date YYYY-MM-DD --use-gemini`
- Fetches 10 tipster sites sequentially via Playwright (NOT parallel — Playwright is not thread-safe). With `--use-gemini` flag: uses httpx + LM Studio extraction. HTTP fallback uses parallel fetching:
  - ZawodTyper, Typersi, Sportsgambler, PicksWise, BetIdeas, OLBG
  - Tipstrr, Feedinco, BettingClosed, Tips180
- DB: `tipster_picks` + `tipster_consensus` tables via `TipsterRepo` (PRIMARY). JSON fallback: `{date}_tipster_consensus.json` + `{date}_tipster_consensus.md`
- Runs in S2 tipster step
- Computes per-event consensus: agreement %, confidence adjustment, market classification
- Classifies tips as "statistical" (corners, totals, cards) vs "outcome" (ML, winner)
- Statistical market tips with data-backed arguments → §4.3 watchlist promotion candidates

**Integration with manual deep-dive (S4):**
The aggregator provides the FIRST PASS — structured picks + consensus. The `bet-scout` agent then performs the DEEP DIVE — reading full written arguments, extracting cited facts, investigating contradictions, and promoting statistical market picks to the watchlist.

## Source Health DB Query

```sql
SELECT source_name, total_requests, total_failures,
       ROUND(total_failures*100.0/MAX(total_requests,1),1) as fail_pct,
       last_success, last_failure
FROM source_health ORDER BY total_requests DESC;
```

## Connected Skills

| Skill | Load for |
|-------|----------|
| `bet-analyzing-statistics` | §3.0 ranking protocol that consumes the data collected via these sources |
| `bet-applying-sport-protocols` | Per-sport data requirements defining WHAT to collect |
| `bet-evaluating-odds` | American odds conversion, EV from multi-source odds comparison |
| `bet-settling-results` | Result verification via Flashscore/ESPN scores |
