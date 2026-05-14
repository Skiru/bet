# Pipeline Knowledge Base — Consolidated (May 4-14, 2026)

## ✅ CRITICAL BUGS — ALL FIXED (2026-05-14)

| Bug | File(s) | Root Cause | Fix |
|-----|---------|------------|-----|
| **A** | `scan_events.py`, `flashscore.py` | Deep enrichment in ThreadPoolExecutor → Playwright greenlet crash. Also `f.className` JS error (DOMTokenList not string). | Sequential main-thread enrichment (`--deep-workers 1`, `--deep-limit 50`). JS: `String(f.className \|\| '')`. |
| **B** | `data_enrichment_agent.py` | Thread guards skipped ALL Playwright clients in workers → 89% teams got nothing. | Phase 2 main-thread retry for failed/empty teams after thread pool pass. |
| **C** | `build_shortlist.py` | FIXTURE_ONLY scored 75 (same as STATS_ONLY for good leagues). | FIXTURE_ONLY tier score 5→0 + total score ×0.5 multiplier. |
| **D** | `deep_stats_report.py` | `--top 200` picked 144 dateless candidates first. | Sort by data_tier before applying `--top` (STATS_ONLY+ first, FIXTURE_ONLY last). |
| **E** | `odds_evaluator.py`, `utils.py` | Exact string match — "Montréal" ≠ "Montreal". | All odds sources + candidate lookup use `normalize_team_name()` (accents, hyphens, FC/SC). Fuzzy substring fallback. |

---

## ⛔ KNOWN ISSUES — TO FIX (Priority Order)

### ISSUE 1: ESPN Football/Volleyball HTTP 400 Flood (HIGH)
- **File:** `src/bet/api_clients/espn.py`, `unified.py`
- **Evidence:** Scan logs flooded with `[espn-football] HTTP 400: Failed to get events endpoint` — ~65 football leagues, ~4 volleyball leagues all returning 400.
- **Impact:** Log noise, wasted API calls (~70 per scan), slows scan by ~5-10s. ESPN football fixtures return 0 events for most leagues.
- **Fix options:** (a) cache 400 responses per league and skip for 24h, (b) reduce ESPN_LEAGUES football list to only leagues that actually return data, (c) move ESPN below Flashscore in SOURCE_PRIORITY (already is) and skip if Flashscore returned enough

### ISSUE 2: ESPN Creates New Client Per League (MEDIUM)
- **File:** `src/bet/api_clients/unified.py` line ~125
- **Evidence:** `get_fixtures()` creates `ESPNClient(sport=sport, league=league)` inside a loop for each of ~65 football leagues. Each instantiation creates new rate_limiter + session.
- **Impact:** Memory churn, inconsistent rate limiting across leagues.
- **Fix:** Create one ESPNClient per sport, iterate leagues internally.

### ISSUE 3: Flashscore Fetches Stats for Upcoming Matches (MEDIUM)
- **File:** `src/bet/api_clients/flashscore.py` → `get_fixture_stats()`, `unified.py` → `get_deep_data()`
- **Evidence:** `get_fixture_stats` navigates to match-statistics page for SCHEDULED matches → always returns 0 stats. Wastes ~6 seconds per event (Playwright page load).
- **Impact:** With `--deep-limit 50`, that's ~5 min wasted on guaranteed-empty pages.
- **Fix:** `get_deep_data()` should skip `get_fixture_stats()` for non-finished matches. Or: pass a `status` parameter and skip stats scraping.

### ISSUE 4: "Advancing to next round" Garbage in Team Names (MEDIUM)
- **File:** `src/bet/api_clients/flashscore.py` → `_JS_EXTRACT_FIXTURES`
- **Evidence:** Live test output: `"River PlateAdvancing to next round: River Plate vs Gimnasia L.P."` — Flashscore DOM concatenates "Advancing to next round" with team name.
- **Impact:** Garbage team names in scan → phantom/junk events enter shortlist.
- **Fix:** Add to `_JS_EXTRACT_FIXTURES` JS: strip "Advancing to next round" text. Also add to `build_shortlist.py` `_garbage_re` pattern.

### ISSUE 5: Flashscore Tennis Player Pages 404 (MEDIUM)
- **File:** `data_enrichment_agent.py`
- **Evidence:** Knowledge base backlog item: ALL Flashscore tennis player pages return 404. Wastes ~10 min per enrichment run.
- **Impact:** Zero tennis enrichment from Flashscore. Time wasted.
- **Fix:** Skip Flashscore enrichment for tennis sport. Use ESPN + TennisAbstract Elo instead. Add `if sport == "tennis": skip flashscore` guard.

### ISSUE 6: Flashscore H2H Selector May Be Stale (LOW)
- **File:** `src/bet/api_clients/flashscore.py` → `_JS_EXTRACT_H2H`
- **Evidence:** Live test: 2/2 events had form data but only 1/2 had H2H. H2H selector uses `.h2h__row`, `.h2h__homeParticipant` etc. — may be outdated Flashscore DOM.
- **Impact:** Missing H2H data → safety score lacks H2H cross-check (Pattern G).
- **Fix:** Debug live Flashscore H2H page, update selectors. May need `[class*="h2h"]` wildcards.

### ISSUE 7: Gemini News (--news) Produces 0 Results (LOW)
- **File:** `scripts/gemini_news_enrichment.py`
- **Evidence:** Knowledge base backlog item. Unknown if module actually runs or fails silently.
- **Impact:** Zero news context for team_news table.
- **Fix:** Debug `batch_enrich_news()` — check Gemini API key, response parsing, error handling.

### ISSUE 8: Lower-League Teams 404 on Flashscore (LOW)
- **File:** `data_enrichment_agent.py`
- **Evidence:** Many minor league teams (Indian state leagues, 4th divisions) consistently 404 on Flashscore.
- **Impact:** Wasted Playwright time per run. Same teams fail every day.
- **Fix:** Maintain a `known_missing_teams.json` cache. If a team 404'd in last 7 days, skip Flashscore and go to next source.

### ISSUE 9: scan_events db_scan_results=0 on Re-run (COSMETIC)
- **File:** `scripts/scan_events.py`
- **Evidence:** AGENT_SUMMARY shows `db_scan_results: 0` on re-runs — ScanResultRepo.bulk_insert likely deduplicates.
- **Impact:** Misleading metric. Not a functional bug.
- **Fix:** Log "X skipped as duplicates" instead of just returning 0.

---

## Data Funnel (2026-05-14 actual numbers)
```
1203 scanned → 0% with deep data from scan
506 shortlisted → 448 FIXTURE_ONLY (88%), 58 STATS_ONLY (12%)
200 fed to deep_stats → 144 no data, 56 with data → 98 analyzable
After S4-S7 gates → 3-4 viable core picks
```

---

## Enrichment Architecture

### Layer Priority
1. **DB team_form** (primary) — 200K+ entries, per-stat l10_avg/l5_avg/count
2. **JSON stats_cache** — `betting/data/stats_cache/{sport}/{slug}.json`, `_home`/`_away` suffixes
3. **ESPN** — 11.5K+ gamelogs, standings, ATS/OU records (basketball/hockey/baseball)
4. **Niche sport caches** — esports/darts/table_tennis player form
5. **Scan data ingestion** — `ingest_scan_stats.py` bridges scan → stats_cache + DB
6. **data_enrichment_agent.py** — Flashscore direct/search, Sofascore, scores24.live

### Key Limitations
- ESPN: no soccer player gamelogs, no handball/snooker/darts/table_tennis/esports/padel
- Betclic: always 403 — NEVER scrape
- 7 sports have ZERO API odds: snooker, darts, table_tennis, esports, mma, padel, speedway
- Football API odds: only ~92/4292 events covered (use stats-first mode R10)

### Enrichment Backlog
- Items moved to "KNOWN ISSUES" section above: tennis 404 (ISSUE 5), Gemini news (ISSUE 7), thread-guarded clients (fixed in BUG B Phase 2), lower-league 404 (ISSUE 8)

---

## Safety Score Patterns (A-I)

| Pat | Rule | Cap |
|-----|------|-----|
| A | Directional conflict detection | — |
| B | Knockout/continental SF/Final | 0.65-0.70 |
| C | Sport volatility (baseball/hockey/basketball) | 0.55/0.60/0.70 |
| D | Concentration (>2 coupons, >25% budget) | flag |
| E | Data tier (youth 0.60, state 0.55, women 0.60, 2nd div 0.70) | varies |
| F | Line sensitivity P(hit) tables | ±0.5/±1/±1.5/±2 |
| G | Evidence requirements (safety ≥0.80 needs ≥10 L10 + H2H) | — |
| H | **One-sided data** | **hard cap 0.40** |
| I | **Small sample (<8 games in L10)** | **hard cap 0.50** |

---

## Data Quality Traps (proven killers)

1. **Synthetic data** — `db-synthetic` fabricates L10 from sparse data → cap at 0.50 safety
2. **Cache key mismatches** — `corners_home`/`corners_away` vs bare `corners` → check both
3. **Standard line collision** — basketball team [95-110] vs combined [195-225] → separate dicts
4. **Market-matched EV** — ML odds applied to corners prob = impossible EV → match market types
5. **JSON overwrite between steps** — S4 overwrote S3 full file → read JSON first, DB fallback
6. **DB status case** — "APPROVED" vs "approved" → use `UPPER(status)` always
7. **Compound penalty death spiral** — H2H×synthetic×one-sided = 0.245 → floor at 0.40
8. **UPSET_THRESHOLDS int vs float** — 55 (int) vs 0.55 (float) → keep consistent units
9. **L5 trend wrong slice** — L10 most-recent-first, `[:5]` = L5 (not `[-5:]`)
10. **Dedup ignores team order** — use `min(home,away)|max(home,away)|date` for dedup key

---

## Pipeline Architecture (current)

- ~48K LoC, 153 files, 21 agents, 62 scripts, 28 DB tables
- SQLite WAL at `betting/data/betting.db`, connection: `from bet.db.connection import get_db`
- Scripts = DATA TOOLS. Agents = ANALYSTS. `src/bet/` = shared packages (db, api_clients, stats)
- `src/bet/stats/market_ranking.py` = SINGLE SOURCE OF TRUTH for SPORT_MARKETS, STANDARD_MARKET_LINES, MARKET_PL
- 14 scripts emit `AGENT_SUMMARY:{json}` with `--verbose`. Exit: 0=OK, 1=partial, 2=critical
- Gate vocabulary: status=APPROVED/EXTENDED/REJECTED, advisory_tier=STRONG/MODERATE/WEAK/FLAGGED, risk_tier=LR/MS/HR/N
- Config: `max_legs_per_coupon: 4`, `min_safety_score: 0.4`, `max_picks_per_day: 80`

### API Clients (2026-05-13)
- **unified.py** routes: Football(Flashscore→BetExplorer→Soccerway→ESPN), Tennis(Flashscore→Scores24→ESPN)
- **New clients:** BetExplorerClient(HTTP), OddsPortalClient(Playwright), TotalCornerClient(Playwright), Scores24Client(Playwright), SoccerwayClient(HTTP)
- **Disabled:** TheSportsDB, BallDontLie, API-Tennis
- **Sport adapters (2026-05-12):** Hockey=MoneyPuck PRIMARY, Tennis=TennisAbstract Elo, Basketball=Basketball-Reference enhanced

---

## Execution Protocol (what works)

### Script Monitoring Pattern (user-praised 2026-05-14)
```
1. LAUNCH: mode=async, timeout=600000
2. POLL (every 30-60s): get_terminal_output → read last 20-40 lines
3. SUMMARIZE: current activity, time elapsed, error count, progress estimate
4. ON ERROR: STOP and diagnose immediately
5. COMPLETION: When AGENT_SUMMARY seen or shell prompt returns
6. VALIDATE: pylanceRunCodeSnippet for output verification
```

### Orchestrator Execution Model (2026-05-14)
- Orchestrator RUNS + MONITORS scripts (visible to user)
- Orchestrator DELEGATES INTERPRETATION to specialist agents
- Subagent does NOT run scripts — it ANALYZES output orchestrator collected
- This preserves R1 (agent-driven) + gives user visibility

---

## Betclic Constraints
- Hockey: **Penalty Minutes NOT available** — use total goals, puck line, period totals
- Always verify exotic statistical markets exist before including in core coupons
- Standard hockey markets: ML, total goals O/U, puck line (handicap), period O/U

---

## Tennis-Specific
- ESPN provides only 4 markets: Total Games O/U, Player A/B Games O/U, Total Sets O/U
- Individual sports: min_matches=3 (not 5)
- Lucky Loser entry = HARD REJECT (ZT#22)
- Over sets without H2H = HARD REJECT (ZT#3-EXT)
- Scan 45 days back for player matches

---

## Post-Mortem: 2026-05-13 Coupon (1W/3L, -2.0 PLN) — ALL FIXED

| Bug | Fix | Pattern |
|-----|-----|---------|
| Duplicate fixtures | Dedup by normalized team names (accent-stripped, FC/SC removed) | `duplicate_fixture_conflict` |
| One-sided data | Safety hard-capped at **0.40** (Pattern H) | `missing_opponent_data` |
| Opponent quality | ZT#23 flags stat markets vs top-5 opponents (standings query) | `opponent_quality_mismatch` |
| Small sample bias | Safety capped at **0.50** when L10 <8 games (Pattern I) | `small_sample_bias` |
| Odds vs safety gap | Gate #19: flag when gap >15 percentage points | `odds_vs_safety_disagreement` |

---

## Session Lessons (process)

1. **Rule overload causes blindness** — when everything is BOLD/URGENT, nothing stands out. Fix: shorter instructions + concrete examples + per-agent "YOUR VALUE" statements
2. **Duplicated instructions get skimmed** — single source of truth in agent-execution-protocol.instructions.md
3. **Examples teach better than rules** — each internal prompt needs filled-in good output example
4. **Pre-S3 data check** — if <50% have team_form data → enrich FIRST (not after S3 fails)
5. **S2 + S2.5 parallel** — independent, run simultaneously
6. **2-3 leg coupons preferred** — AKO5/7 = 0 wins historically
7. **UNDER picks 74% hit rate** — strongest direction historically
8. **Statistical markets 63% > outcomes 45%** — team_corners 87%, cards 75%, fouls 67%

---

## HTML Deep Parser (20 profiles, 2026-05-08)
- 12,166 enrichments from 538 snapshots across 20 domains
- Key: Flashscore(9482), TennisAbstract(1060), TennisExplorer(550), Forebet(251), Basketball-Reference(250)
- Sofascore = __NEXT_DATA__ JSON, Scores24 = React Query dehydrated, Betclic = JSON script blocks
- PRIMARY_SCAN_DOMAINS fail at <30% match, others WARN at <15%
