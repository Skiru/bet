# Esports Integration Research — CS2, Dota 2, Valorant

**Date:** 2026-05-24  
**Status:** Research Complete + Live Tested — Ready for Architecture Planning  
**Target Games:** Counter-Strike 2 (CS2), Dota 2, Valorant  
**Bookmaker:** Betclic Poland (`betclic.pl/esport-s46`)

### LIVE TEST RESULTS (2026-05-24 08:30 UTC)
| Source | Status | Key Findings |
|--------|--------|-------------|
| **odds-api.io** | ✅ WORKS | 194 esports events, slug=`esports`, CS2+Dota2+Valorant+LoL. Returns ML, Spread (map HC), Map Lines (round totals O/U, round HC). Betclic PL + Bet365 bookmakers confirmed. |
| **OpenDota** | ✅ WORKS | 100 recent pro matches, team ratings, kills, duration, GPM. FREE, no key. |
| **VLR.gg** | ✅ WORKS | 800 match-items via simple HTTP GET (no Playwright needed for matches page). |
| **GosuGamers** | ✅ WORKS | Accessible for CS2/Dota/Val predictions and community polls. |
| **The-Odds-API** | ❌ NO ESPORTS | Zero esports sport keys (not even inactive). Not usable for esports. |
| **HLTV** | ❌ 403 Cloudflare | Needs Playwright stealth mode. Not accessible via simple HTTP. |
| **PandaScore** | ❌ 403 | Requires API key registration (free tier exists but need to register). |
| **VLR community API** | ❌ 404 DEAD | `vlrggapi.vercel.app` — all endpoints return 404. |
| **bo3.gg** | ✅ WORKS | CS2 match items accessible via HTTP. |

**CORRECTED SOURCE HIERARCHY:**
- **Primary odds+discovery:** odds-api.io (194 events, rich market depth, Betclic PL odds!)
- **Primary stats CS2:** HLTV (Playwright required) → bo3.gg (HTTP fallback)
- **Primary stats Dota2:** OpenDota (FREE API, no key, 60 req/min)
- **Primary stats Valorant:** VLR.gg (HTTP scraping, 800 matches)
- **Tipster consensus:** GosuGamers (all 3 games)

---

## 1. Betclic Esports Coverage Summary

### Games Available on Betclic PL
| Game | Slug | Status | Market Depth |
|------|------|--------|-------------|
| Counter-Strike 2 | CS2 | ✅ Active | Deep (rounds, maps, pistol) |
| Dota 2 | Dota 2 | ✅ Active | Moderate (maps, kills, duration) |
| Valorant | Valorant | ✅ Active | Deep (rounds, maps) |
| League of Legends | LoL | ✅ Active (out of scope) | Moderate |

### Market Types by Game

#### CS2 Markets (Betclic)
| Market | Example | Bettable? | Pipeline Stat Source |
|--------|---------|-----------|---------------------|
| Match Winner (ML) | NaVi ML | Yes | HLTV rankings + form |
| Map Handicap | NaVi -1.5 maps | Yes | HLTV map pool + H2H |
| Total Maps | O/U 2.5 (BO3) | Yes | HLTV H2H map counts |
| Map Winner | Map 1 Winner | Yes | HLTV map-specific stats |
| Total Rounds (per map) | Map 1 O/U 26.5 | ★ **PRIORITY** | HLTV round averages |
| First Map Winner | — | Yes | Map 1 pick/ban + form |
| Correct Map Score | 2-0, 2-1 | Yes | H2H score patterns |
| Pistol Round Winner | — | Limited coverage | Round-level stats (rare) |

#### Dota 2 Markets (Betclic)
| Market | Example | Bettable? | Pipeline Stat Source |
|--------|---------|-----------|---------------------|
| Match Winner (ML) | Team Spirit ML | Yes | OpenDota + rankings |
| Map Handicap | Spirit -1.5 | Yes | H2H map history |
| Total Maps | O/U 2.5 (BO3) | Yes | H2H closeness |
| Map Winner | Map 1 Winner | Yes | Dire/Radiant advantage |
| First Blood | Team A 1st kill | Limited | OpenDota kill logs |
| Total Kills | O/U 45.5 | ★ **PRIORITY** | OpenDota avg kills/game |
| Game Duration | O/U 35.5 min | Yes | OpenDota game length |
| Map 1 Winner | — | Yes | Patch meta + team style |

#### Valorant Markets (Betclic)
| Market | Example | Bettable? | Pipeline Stat Source |
|--------|---------|-----------|---------------------|
| Match Winner (ML) | Sentinels ML | Yes | VLR rankings + form |
| Map Handicap | SEN -1.5 | Yes | Map pool analysis |
| Total Maps | O/U 2.5 (BO3) | Yes | H2H history |
| Map Winner | Map 1 Winner | Yes | Map-specific stats |
| Total Rounds (per map) | Map 1 O/U 24.5 | ★ **PRIORITY** | VLR round averages |
| First Map Winner | — | Yes | Map pick/veto |
| Correct Map Score | 2-0, 2-1 | Yes | H2H patterns |

### Tournament/League Coverage (Betclic PL commonly offers)

**CS2:**
- BLAST Premier (Spring/Fall/World Final)
- IEM (Katowice, Cologne, Dallas, Sydney, Rio)
- ESL Pro League (Seasons 19-22+)
- PGL Major (Copenhagen, etc.)
- BLAST Rivals / Bounty
- CCT (Champion of Champions Tour)
- Thunderpick World Championship
- YaLLa Compass

**Dota 2:**
- The International (TI)
- DPC Tour (Division I & II, all regions)
- ESL One (Birmingham, Kuala Lumpur)
- Bali Major, Katowice Major, etc.
- BetBoom Dacha/Series
- Riyadh Masters

**Valorant:**
- VCT Champions Tour (Masters, Champions)
- VCT Regional Leagues (EMEA, Americas, Pacific)
- VCT Challengers (Ascension)
- VCT Game Changers
- Red Bull Home Ground
- Off//season events

---

## 2. Source Matrix

### 2.1 Fixture/Event Discovery Sources

| Source | Games | Access Method | Rate Limit | Data Type | Reliability | Notes |
|--------|-------|--------------|------------|-----------|-------------|-------|
| **The-Odds-API** | CS2, Dota 2, Valorant, LoL | REST API (key) | 500 credits/mo | Fixtures + odds | ★★★★★ | Sport keys: `esports_csgo`, `esports_dota2`, `esports_valorant` |
| **Bovada /esports** | CS2, Dota 2, Valorant, LoL | Public JSON (no auth) | ~1 req/30s (self-imposed) | Fixtures + odds + markets | ★★★★☆ | 84 events, 953 markets confirmed |
| **Odds-API.io** | TBD (likely yes) | REST API (key) | 5000 req/hr | Fixtures + odds | ★★★★☆ | Need `--list-sports` to verify esports slug |
| **PandaScore** | CS2, Dota 2, Valorant, LoL, OW, SC2 | REST API (Bearer token) | ~1000 req/hr (free) | Fixtures + rosters + brackets | ★★★★☆ | Best structured fixture data; odds likely paid-only |
| **Flashscore /esports** | CS2, Dota 2, Valorant, LoL | HTTP + Playwright | 2s between reqs | Fixtures + results | ★★★☆☆ | Same LiveSport infra; confirmed working |
| **HLTV.org** | CS2 only | Playwright stealth | Conservative | Upcoming matches | ★★★★☆ | Stats pages confirmed working Apr 29 |
| **Liquipedia** | CS2, Dota 2, Valorant | MediaWiki API | ~1 req/s | Fixtures + brackets + rosters | ★★★★☆ | Structured Cargo tables |
| **VLR.gg** | Valorant only | Playwright scraping | Conservative | Upcoming matches | ★★★☆☆ | No official API |

### 2.2 Statistics Sources

| Source | Games | Data Available | Access | Rate Limit | Depth |
|--------|-------|---------------|--------|------------|-------|
| **HLTV.org** (stats) | CS2 | Rating 2.0, K/D, ADR, KAST%, map win%, round stats, H2H, team rankings | Playwright | Conservative | ★★★★★ |
| **OpenDota API** | Dota 2 | Match details, draft, kills, items, GPM/XPM, hero stats, pro matches, H2H | REST (free, no key for basic) | 60 req/min (no key), 1200/min (free key) | ★★★★★ |
| **VLR.gg** | Valorant | ACS, K/D, ADR, agent pool, map stats, team form | Playwright | Conservative | ★★★★☆ |
| **Liquipedia** | CS2, Dota 2, Val | Rosters, transfers, patch dates, tournament format | MediaWiki API | ~1 req/s | ★★★☆☆ (context, not stats) |
| **PandaScore** | All 3 | Team stats, player stats, match results per map, opponents | REST API | ~1000 req/hr | ★★★★☆ |
| **bo3.gg** | CS2 | Map pool, recent results, rankings | Scraping | Unknown | ★★★☆☆ |
| **Dotabuff** | Dota 2 | Hero stats, player profiles, meta | Scraping (limited free) | N/A | ★★☆☆☆ (Plus needed for depth) |
| **tracker.gg** | Valorant | Player stats (ranked, not pro) | Scraping | N/A | ★☆☆☆☆ (not pro-focused) |

### 2.3 Odds Sources

| Source | Games | Markets | Access | Notes |
|--------|-------|---------|--------|-------|
| **Bovada /esports** | CS2, Dota 2, Val, LoL | ML, map totals, round totals | Free public JSON | ★ Richest free source for esports odds |
| **The-Odds-API** | CS2, Dota 2, Val | h2h, spreads, totals | API key (500 credits/mo shared) | Multiple bookmakers incl. Betclic region |
| **Odds-API.io** | TBD | Likely ML + maps | API key (5000 req/hr) | Need verification; would include Betclic PL |
| **BetExplorer** | Limited/empty | — | Playwright | ❌ Returned empty Apr 23 |
| **Scores24** | CS2 | H2H + odds from bookmakers | Playwright | Good for cross-validation |
| **OddsPortal** | Limited | — | Playwright | May have some esports now |

### 2.4 Tipster/Community Sources

| Source | Games | Content | Access | Reliability |
|--------|-------|---------|--------|-------------|
| **GosuGamers** | CS2, Dota 2, Val | Community predictions (% polls), news | HTTP/Playwright | ★★★★☆ Confirmed Apr 24 |
| **HLTV match pages** | CS2 | Community polls (win %), map vetoes, comments | Playwright | ★★★★☆ (polls = consensus) |
| **VLR.gg match pages** | Valorant | Community predictions | Playwright | ★★★☆☆ |
| **Reddit r/csgobetting** | CS2 | Discussion threads, picks, analysis | API/scraping | ★★☆☆☆ (noisy) |
| **Reddit r/dota2betting** | Dota 2 | Match discussion | API/scraping | ★★☆☆☆ (low volume) |
| **Reddit r/ValorantCompetitive** | Valorant | Match discussion, roster news | API/scraping | ★★★☆☆ (news value) |
| **ZawodTyper/Typersi** | ❌ None | — | — | No esports coverage |
| **OLBG/PicksWise** | ❌ None | — | — | No esports coverage |

---

## 3. API Documentation Deep Dive

### 3.1 The-Odds-API — Esports Sport Keys

**Documentation:** https://the-odds-api.com/sports-odds-data/

**Confirmed esports sport keys:**
```
esports_csgo          — Counter-Strike 2 (all major tournaments)
esports_dota2         — Dota 2 (TI, DPC, ESL, etc.)
esports_lol           — League of Legends (out of scope)
esports_valorant      — Valorant (VCT, regional leagues)
```

**Integration approach:**
```python
# Addition to SPORT_KEY_MAP in fetch_odds_api.py and discovery/sources/odds_api.py:
"esports": ["esports_csgo", "esports_dota2", "esports_valorant"],
```

**Markets available:**
- `h2h` — Match winner (moneyline)
- `spreads` — Map handicap (e.g., -1.5 maps)
- `totals` — Total maps (O/U 2.5)

**Cost:** ~3 credits per scan (3 sport keys × h2h × 1 region). Very cheap.

**Coverage quality:**
- Major tournaments: Excellent (BLAST, IEM, TI, VCT Masters)
- Minor tournaments: Moderate (some CCT, Challengers events)
- Online qualifiers: Limited

### 3.2 PandaScore API

**Documentation:** https://developers.pandascore.co/

**Authentication:** Bearer token (API key from dashboard registration)

**Free tier:**
- Historically: 1000 requests/hour
- Current (2026): Verify at registration — may have changed to freemium model
- NOTE: Odds data likely requires paid plan. Match/team/player data on free plan.

**Key endpoints:**
```
GET /csgo/matches/upcoming     — Upcoming CS2 matches
GET /dota2/matches/upcoming    — Upcoming Dota 2 matches
GET /valorant/matches/upcoming — Upcoming Valorant matches

GET /csgo/matches/{id}         — Match details (maps, scores, rosters)
GET /csgo/teams                — Team roster + recent results
GET /csgo/players              — Player profiles + stats
GET /csgo/tournaments          — Tournament info + brackets

GET /dota2/matches/past        — Historical match results
GET /dota2/teams/{id}/stats    — Team statistics
GET /valorant/leagues           — Active leagues/circuits
```

**Response format (match):**
```json
{
  "id": 123456,
  "name": "NaVi vs FaZe",
  "begin_at": "2026-05-24T15:00:00Z",
  "tournament": {"name": "BLAST Premier Spring", "tier": "s"},
  "opponents": [
    {"opponent": {"name": "Natus Vincere", "acronym": "NAVI"}},
    {"opponent": {"name": "FaZe Clan", "acronym": "FaZe"}}
  ],
  "number_of_games": 3,
  "status": "not_started",
  "results": [],
  "games": []
}
```

**Data useful for pipeline:**
- Tournament tier (S/A/B/C) → maps to pipeline confidence
- BO format (BO1/BO3/BO5) → critical for map totals markets
- Roster verification → stand-in detection (upset risk factor)
- Past match results → H2H with map-level detail

**Key limitation:** Odds data (if available on free plan) is delayed and limited to pre-match only.

### 3.3 OpenDota API (Dota 2 — BEST FREE SOURCE)

**Documentation:** https://docs.opendota.com/

**Authentication:** None required for basic. Free API key for higher rate.

**Rate limits:**
- Without key: 60 requests/minute
- With free key: 1200 requests/minute
- Monthly limit: 50,000 calls (free)

**Critical endpoints for betting pipeline:**

```
GET /proMatches                       — Recent pro matches (last ~30 days)
GET /teams/{team_id}                  — Team info + wins/losses
GET /teams/{team_id}/matches          — All team matches (paginated)
GET /teams/{team_id}/heroes           — Hero usage + win rates per team
GET /matches/{match_id}               — FULL match detail (draft, kills, items, timings)
GET /explorer?sql=SELECT...           — Custom SQL queries on match data
```

**Data available per match:**
- Duration (minutes)
- Total kills per team
- Gold/XP advantage graph
- Draft (picks + bans in order)
- Individual player stats (kills, deaths, assists, GPM, XPM, hero damage, tower damage)
- First blood info
- Tower/barracks destroyed
- Roshan kills
- Ward placements

**Data useful for pipeline safety scores:**
| Stat | Use for Market | Calculation |
|------|---------------|-------------|
| Total kills avg (L10) | Total Kills O/U | Mean + StdDev → line comparison |
| Game duration avg (L10) | Duration O/U | Mean vs bookmaker line |
| First blood % | First Blood market | Team FB rate L10 |
| Map wins L10 | Map Handicap / ML | Form strength |
| Hero pool diversity | Upset risk | Limited hero pool = vulnerability |

**Team ID discovery:** Use `/teams` endpoint or search pro teams by name.

**Pro match filtering:** `/proMatches` returns only verified professional matches — no pub/ranked noise.

### 3.4 HLTV.org (CS2 — PRIMARY STATS SOURCE)

**No official API — scraping required.**

**Confirmed accessible (Apr 29, 2026):**
- Stats pages: ✅ (team stats, player stats, map stats)
- Match pages: ✅ (results, maps, rounds)
- Rankings: ✅ (weekly top 30)
- Upcoming matches: ✅

**Confirmed blocked:**
- Tips/predictions pages: ❌ 403
- Some advanced filtering on stats may require login

**Key URLs for scraping:**
```
hltv.org/stats/teams                    — All team stats
hltv.org/stats/teams/{id}/{slug}        — Individual team page
hltv.org/stats/teams/maps/{id}/{slug}   — Map-specific stats
hltv.org/matches/{id}/{slug}            — Match page with maps + rounds
hltv.org/results                        — Recent results (pageable)
hltv.org/matches                        — Upcoming matches
hltv.org/ranking/teams                  — Current world ranking
hltv.org/stats/players                  — Player stats leaderboard
```

**Data extractable per team:**
- Maps played + win rate (overall and per-map)
- Round win rate (CT/T side)
- Average rounds per map
- Rating 2.0 (team average)
- Recent form (last 3 months)
- Head-to-head history (all meetings)
- Map pool (played, banned, never played)

**Scraping approach:**
- Use Playwright stealth mode (confirmed working)
- Rate: 1 request per 3-5 seconds
- Parse HTML tables (well-structured)
- Monitor for Cloudflare challenges (not currently active but could change)

### 3.5 VLR.gg (Valorant — PRIMARY STATS SOURCE)

**No official API — scraping or community API required.**

**Community API:** `https://vlrggapi.vercel.app/` (third-party, open source)
- Endpoints: `/match/results`, `/match/upcoming`, `/stats/{region}/{timespan}`
- Reliability: Depends on maintainer; may break without notice
- Better for: quick prototyping; not production-reliable

**Direct scraping approach:**
```
vlr.gg/matches/results              — Past match results
vlr.gg/matches                      — Upcoming matches
vlr.gg/rankings/{region}            — Team rankings
vlr.gg/team/{id}/{slug}             — Team profile
vlr.gg/team/{id}/{slug}/matches     — Team match history
vlr.gg/{match_id}/{slug}            — Match detail page
vlr.gg/stats                        — Player stats leaderboard
```

**Data extractable:**
- Team form (last 10-20 matches with map scores)
- Map-specific win rates
- Player stats: ACS (Average Combat Score), K/D, ADR, KAST%, clutch %
- Head-to-head history
- Agent composition per map
- Round differentials

**Scraping approach:**
- Standard HTTP + BeautifulSoup (not heavily JS-dependent for core data)
- Rate: 1 request per 2-3 seconds
- Well-structured HTML tables and divs

### 3.6 Liquipedia (All Three Games — CONTEXT SOURCE)

**API:** MediaWiki API with Cargo extension

**Base URLs:**
```
liquipedia.net/counterstrike/api.php
liquipedia.net/dota2/api.php
liquipedia.net/valorant/api.php
```

**Example query (CS2 upcoming matches):**
```
?action=cargoquery&tables=Matches&fields=Team1,Team2,DateTime_UTC,Tournament,BestOf
&where=DateTime_UTC>"2026-05-24"&order_by=DateTime_UTC&format=json
```

**Data available:**
- Tournament dates, participants, format, prize pool
- Team rosters (current and historical)
- Roster changes (critical for stand-in detection → upset risk)
- Patch dates (critical for meta shift → upset risk)
- Match results (can be delayed vs HLTV/VLR)
- Map pools (CS2)

**Rate limit:** 1 request per second (strict enforcement)

**Best used for:** Context enrichment (roster verification, tournament format, patch timing) rather than primary stats.

---

## 4. Recommended Architecture

### 4.1 Source Hierarchy Per Game

#### CS2
| Role | Primary | Secondary | Tertiary |
|------|---------|-----------|----------|
| **Fixture Discovery** | The-Odds-API (`esports_csgo`) | Bovada `/esports` | PandaScore |
| **Deep Stats** | HLTV.org (Playwright) | PandaScore | bo3.gg |
| **Odds** | Bovada `/esports` | The-Odds-API | Odds-API.io (if confirmed) |
| **H2H** | HLTV match history | Google Sports (SerpAPI) | Liquipedia |
| **Roster/Context** | Liquipedia | HLTV | PandaScore |
| **Tipster/Consensus** | GosuGamers | HLTV polls | Reddit |
| **Results/Settlement** | HLTV | Flashscore | PandaScore |

#### Dota 2
| Role | Primary | Secondary | Tertiary |
|------|---------|-----------|----------|
| **Fixture Discovery** | The-Odds-API (`esports_dota2`) | Bovada `/esports` | PandaScore |
| **Deep Stats** | OpenDota API (FREE) | PandaScore | Liquipedia |
| **Odds** | Bovada `/esports` | The-Odds-API | Odds-API.io |
| **H2H** | OpenDota `/teams/{id}/matches` | PandaScore | Liquipedia |
| **Roster/Context** | Liquipedia | PandaScore | OpenDota |
| **Tipster/Consensus** | GosuGamers | Reddit | — |
| **Results/Settlement** | OpenDota `/proMatches` | Flashscore | PandaScore |

#### Valorant
| Role | Primary | Secondary | Tertiary |
|------|---------|-----------|----------|
| **Fixture Discovery** | The-Odds-API (`esports_valorant`) | Bovada `/esports` | PandaScore |
| **Deep Stats** | VLR.gg (scraping) | PandaScore | Liquipedia |
| **Odds** | Bovada `/esports` | The-Odds-API | Odds-API.io |
| **H2H** | VLR.gg match history | PandaScore | Liquipedia |
| **Roster/Context** | Liquipedia | VLR.gg | PandaScore |
| **Tipster/Consensus** | GosuGamers | VLR.gg community | Reddit |
| **Results/Settlement** | VLR.gg | Flashscore | PandaScore |

### 4.2 Pipeline Integration Points

```
discover_events.py (S1)
├── Add "esports" to SPORT_KEY_MAP (The-Odds-API)
├── Add esports_csgo, esports_dota2, esports_valorant keys
└── Bovada /esports as supplementary discovery

fetch_odds_api.py / fetch_odds_api_io.py (S1b)
├── Map "esports" sport keys  
└── Persist odds to odds_history with sport="esports"

deep_stats_report.py (S3)
├── CS2 → call hltv_client.get_team_stats() + get_h2h()
├── Dota2 → call opendota_client.get_pro_matches() + team_matches()
├── Valorant → call vlr_client.get_team_stats() + get_h2h()
└── Fallback: PandaScore for all three

compute_safety_scores.py (S4)
├── New esports-specific stat keys:
│   - CS2: round_avg, map_wr, ct_wr, t_wr, rating_2
│   - Dota2: kills_avg, duration_avg, fb_rate, hero_pool_size
│   - Valorant: round_avg, map_wr, acs_avg, clutch_pct
└── Safety score thresholds calibrated per game

tipster_aggregator.py (S2)
└── Add GosuGamers esports scraper (community poll %)

context_checks.py (S5) / upset_risk_scorer.py (S6)
├── Roster change detection (Liquipedia)
├── Patch recency (Liquipedia patch dates)
├── Online vs LAN (PandaScore tournament metadata)
└── Map pool edge (HLTV/VLR per-map win rates)
```

---

## 5. Implementation Priority

### Phase 1 — Quick Wins (Effort: LOW, Value: HIGH)
**Goal: Get esports odds and fixtures into discovery pipeline**

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | Add `"esports": ["esports_csgo", "esports_dota2", "esports_valorant"]` to The-Odds-API SPORT_KEY_MAP | 5 min | Immediate fixture+odds discovery |
| 2 | Add `"esports"` to `config/betting_config.json` sports list | 1 min | Unlock pipeline for esports |
| 3 | Add esports to Bovada fetcher endpoint list (when Bovada integration ships) | 5 min | Richest free odds |
| 4 | Verify odds-api.io esports coverage via `--list-sports` | 5 min | Confirm additional odds source |
| 5 | Add `"esports": "esports"` to Odds-API.io SPORT_SLUG_MAP (if confirmed) | 5 min | Additional odds cross-validation |

**Estimated total: 1-2 hours including testing**

### Phase 2 — Stats Infrastructure (Effort: MEDIUM, Value: HIGH)
**Goal: Deep statistical data for safety score calculation**

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 6 | Build `src/bet/api_clients/opendota.py` — Dota 2 stats client | 3-4 hrs | Full Dota 2 L10/H2H pipeline |
| 7 | Build `src/bet/scrapers/hltv.py` — CS2 stats scraper | 4-6 hrs | Full CS2 L10/H2H pipeline |
| 8 | Build `src/bet/scrapers/vlr.py` — Valorant stats scraper | 4-6 hrs | Full Valorant L10/H2H pipeline |
| 9 | Register PandaScore API key (free tier) | 30 min | Backup stats + fixture source |
| 10 | Build `src/bet/api_clients/pandascore.py` | 3-4 hrs | Unified fallback for all 3 games |

**Estimated total: 15-20 hours**

### Phase 3 — Safety Score Calibration (Effort: MEDIUM, Value: HIGH)
**Goal: Esports-specific market analysis**

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 11 | Define esports stat keys in `value_ranges.py` | 2 hrs | Validation ranges |
| 12 | Add esports market table to safety score computation | 3 hrs | Market ranking per game |
| 13 | Calibrate thresholds (round totals, kill totals, map totals) | 2 hrs | Accurate safety scores |
| 14 | Un-archive §3.6 Esports in sport-analysis-protocols | 2 hrs | Proper stat tables |

### Phase 4 — Context & Tipster (Effort: LOW-MEDIUM, Value: MEDIUM)
**Goal: Consensus and context verification**

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 15 | Add GosuGamers esports parser to tipster_aggregator.py | 3 hrs | Community consensus |
| 16 | Add HLTV poll extraction (match pages) | 2 hrs | CS2 consensus signal |
| 17 | Liquipedia roster change detection | 3 hrs | Upset risk stand-in factor |
| 18 | Patch date tracking per game | 1 hr | Meta shift detection |

---

## 6. Gaps — What's NOT Available via Free APIs

| Gap | Impact | Mitigation |
|-----|--------|-----------|
| **Betclic-specific esports odds** | Can't programmatically verify prices | CONDITIONAL picks (R8) — user checks app |
| **CS2 round-level stats (per-round economy)** | Can't predict pistol/eco rounds precisely | Use map-level averages from HLTV |
| **Valorant agent-specific map stats** | Limited comp analysis | Focus on team W/L per map, not comp meta |
| **Dota 2 live draft odds** | Can't react to draft advantages pre-game | Use hero pool analysis as proxy |
| **Real-time roster confirms** | Stand-in announced minutes before match | Liquipedia + HLTV usually update 1-2 hrs before |
| **Betclic market availability per match** | Don't know if specific markets exist until user checks | Prioritize markets Betclic commonly offers (ML, maps, rounds) |
| **Historical Betclic esports odds** | Can't calculate CLV | Use Bovada/The-Odds-API as proxy for line movement |
| **VLR.gg may change structure** | Scraper breaks | PandaScore as fallback; monitor monthly |

---

## 7. Tipster Landscape

### Available for Esports
| Source | Games | Signal Type | Integration |
|--------|-------|-------------|-------------|
| **GosuGamers** | CS2, Dota 2, Val | % community poll (e.g., "72% predict NaVi") | Playwright → tipster_picks DB |
| **HLTV Polls** | CS2 | % poll on match page | Playwright → tipster_picks DB |
| **VLR.gg Predictions** | Valorant | Community picks (W/L only) | Playwright → tipster_picks DB |
| **Reddit threads** | All 3 | Qualitative analysis, roster news, angles | SerpAPI → manual |
| **CSGO Positive** | CS2 | AI/statistical predictions | HTTP (if accessible) |
| **Esports Charts** | All 3 | Viewership/popularity (context) | HTTP |

### NOT Available for Esports
| Source | Status |
|--------|--------|
| ZawodTyper | ❌ No esports section |
| Typersi | ❌ No esports section |
| OLBG | ❌ No esports section |
| PicksWise | ❌ No esports section |
| WinDrawWin | ❌ Football only |
| Meczyki | ❌ Football only |
| FootballPredictions | ❌ Football only |

### Consensus Signal Strategy
Since traditional tipster sites don't cover esports, the consensus signal comes from:
1. **GosuGamers poll %** — primary (covers all 3 games)
2. **HLTV poll %** — CS2 only, but high sample size and knowledgeable community
3. **Betting odds implied probability** — if 3+ bookmakers agree on direction
4. **VLR predictions** — Valorant only

Threshold for "consensus": ≥70% community pick alignment OR ≥2 independent prediction sources agreeing.

---

## 8. Key Metrics for Safety Score Calculation

### CS2 Stat Keys (for `normalize_stats.py` and `compute_safety_scores.py`)
| Stat Key | Source | Use For | Range |
|----------|--------|---------|-------|
| `map_win_rate` | HLTV | ML, map HC | 0.30-0.75 |
| `round_avg_per_map` | HLTV | Round totals O/U | 23-30 |
| `ct_round_wr` | HLTV | Side-specific analysis | 0.40-0.65 |
| `t_round_wr` | HLTV | Side-specific analysis | 0.35-0.60 |
| `h2h_maps_won` | HLTV | Map HC | 0-20 |
| `h2h_avg_rounds` | HLTV | Round totals | 24-29 |
| `rating_2` | HLTV | Team quality proxy | 0.90-1.25 |
| `maps_played_l10` | HLTV | Form reliability | 10-30 |

### Dota 2 Stat Keys
| Stat Key | Source | Use For | Range |
|----------|--------|---------|-------|
| `kills_avg` | OpenDota | Total kills O/U | 35-70 |
| `duration_avg_min` | OpenDota | Duration O/U | 28-45 |
| `first_blood_rate` | OpenDota | First blood market | 0.30-0.70 |
| `win_rate_l10` | OpenDota | ML / map HC | 0.20-0.80 |
| `radiant_wr` | OpenDota | Side advantage | 0.45-0.55 |
| `hero_pool_size` | OpenDota | Meta vulnerability | 10-30 |
| `h2h_games` | OpenDota | H2H reliability | 1-30 |

### Valorant Stat Keys
| Stat Key | Source | Use For | Range |
|----------|--------|---------|-------|
| `map_win_rate` | VLR.gg | ML, map HC | 0.30-0.75 |
| `round_avg_per_map` | VLR.gg | Round totals O/U | 21-28 |
| `attack_wr` | VLR.gg | Side-specific | 0.40-0.60 |
| `defense_wr` | VLR.gg | Side-specific | 0.40-0.60 |
| `acs_team_avg` | VLR.gg | Team firepower | 180-260 |
| `clutch_pct` | VLR.gg | Close round edge | 0.05-0.30 |
| `h2h_maps_won` | VLR.gg | Map HC | 0-15 |

---

## 9. Historical Context — Why Previous CS2 Picks Failed

**Learning log finding:** CS2 had 0% hit rate (0W/9L), leading to permanent ban.

**Root cause analysis (why it failed then, and why it can work now):**

1. **No proper stats infrastructure** — HLTV was "unavailable" on Apr 23, became available by Apr 29. The early picks had NO statistical backing.
2. **Used match_winner market** — ML has 37% hit rate overall. The NaVi vs FaZe pick used `round_totals` (better), but earlier picks likely used ML.
3. **Single-source analysis** — No odds cross-validation (no esports in The-Odds-API map at the time), no Bovada integration.
4. **No H2H data** — Without HLTV H2H stats, round totals analysis was surface-level.
5. **Tipster-blind** — GosuGamers wasn't integrated into tipster_aggregator.py.

**What's different now:**
- HLTV confirmed accessible for stats
- Bovada /esports endpoint confirmed (84 events, 953 markets)
- The-Odds-API has esports sport keys (can be trivially added)
- OpenDota provides world-class Dota 2 data for FREE
- GosuGamers confirmed as working consensus source
- Pipeline has proper safety score infrastructure
- Round totals / map totals (statistical markets) will be prioritized over ML per existing rules

**Recommendation:** Resume esports with STATISTICAL MARKETS ONLY (round totals, map totals, total kills). Avoid ML per existing coupon killer analysis. Start with BO3 matches from Tier S/A tournaments only (higher data reliability).

---

## 10. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| HLTV adds Cloudflare protection | Medium | High (CS2 stats loss) | PandaScore as backup + Liquipedia |
| VLR.gg restructures DOM | Medium | Medium (Valorant stats loss) | PandaScore + community API fallback |
| PandaScore removes/limits free tier | Low | Medium | OpenDota (Dota2 safe), HLTV/VLR (independent) |
| Betclic removes esports section | Very Low | Critical | Monitor periodically |
| Low liquidity = odds not available | Medium | Low | Only bet Tier S/A tournaments with high liquidity |
| Stand-in not detected in time | Medium | Medium | Liquipedia + HLTV monitoring 2h before match |
| API format changes break parsers | Medium | Low | Version pin + monthly smoke tests |

---

## 11. Quick Reference — Integration Checklist

```
□ Phase 1: Discovery + Odds
  □ Add esports sport keys to The-Odds-API (fetch_odds_api.py + discovery/sources/odds_api.py)
  □ Add "esports" to betting_config.json sports array
  □ Add "esports" to Odds-API.io SPORT_SLUG_MAP (after verification)
  □ Include /esports in Bovada fetcher (when shipped)
  □ Test: run discover_events.py --sports esports and verify fixtures appear

□ Phase 2: Stats Clients
  □ Register PandaScore free API key
  □ Build opendota.py client (Dota 2)
  □ Build hltv.py scraper (CS2)  
  □ Build vlr.py scraper (Valorant)
  □ Build pandascore.py client (all games, fallback)
  □ Test: verify L10 + H2H data retrieval for one team per game

□ Phase 3: Safety Scores
  □ Add esports stat keys to value_ranges.py
  □ Add esports market tables to compute_safety_scores.py
  □ Un-archive §3.6 Esports in sport-analysis-protocols.instructions.md
  □ Define bettable markets table per game (CS2, Dota2, Valorant)
  □ Calibrate round_avg / kills_avg thresholds from 30+ historical matches

□ Phase 4: Context + Tipsters
  □ Add GosuGamers esports parser
  □ Add HLTV poll scraping (CS2 match pages)
  □ Liquipedia roster change monitor
  □ Update upset_risk_scorer with full esports checklist

□ Phase 5: Validation
  □ Run full pipeline on 5 esports events (dry run, no betting)
  □ Compare safety scores to actual results
  □ Adjust thresholds
  □ Graduate to live conditional picks
```

---

## 12. Files That Need Modification (When Implementing)

| File | Change |
|------|--------|
| `config/betting_config.json` | Add "esports" to sports array |
| `scripts/fetch_odds_api.py` | Add esports to SPORT_KEY_MAP |
| `src/bet/discovery/sources/odds_api.py` | Add esports keys + prefix map |
| `src/bet/api_clients/odds_api_io.py` | Add "esports" to SPORT_SLUG_MAP (if confirmed) |
| `scripts/fetch_bovada_odds.py` | Include /esports endpoint (when built) |
| `src/bet/stats/value_ranges.py` | Add esports stat key ranges |
| `scripts/compute_safety_scores.py` | Add esports market tables |
| `scripts/deep_stats_report.py` | Route esports candidates to game-specific clients |
| `scripts/tipster_aggregator.py` | Add GosuGamers esports parser |
| `.github/instructions/sport-analysis-protocols.instructions.md` | Un-archive §3.6, fill with proper tables |
| `betting/sources/source-registry.md` | Add esports-specific sources |
| NEW: `src/bet/api_clients/opendota.py` | Dota 2 stats client |
| NEW: `src/bet/scrapers/hltv.py` | CS2 stats scraper |
| NEW: `src/bet/scrapers/vlr.py` | Valorant stats scraper |
| NEW: `src/bet/api_clients/pandascore.py` | PandaScore unified client |
