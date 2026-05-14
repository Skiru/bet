# Pipeline Knowledge Base — Consolidated (May 4-14, 2026)

## ⛔ CRITICAL BUGS TO FIX (Priority Order)

### BUG A: Beast Mode Scan Produces ZERO Deep Data (2026-05-14)
- **File:** `scripts/scan_events.py`
- **Evidence:** `global_events_api.json` 1203 events, ALL with `form=null, h2h=null, odds=null`
- **Impact:** CATASTROPHIC — `ingest_scan_stats.py` has nothing to ingest → 0 new team_form rows
- **Fix:** Investigate beast_mode logic — does it navigate match detail pages? Flashscore structure change? `--parallel-sport` prevents deep scraping?

### BUG B: Enrichment Only Reaches 11% of Candidates (2026-05-14)
- **File:** `scripts/data_enrichment_agent.py`
- **Evidence:** 506 shortlisted → only 58 got STATS_ONLY tier. DB has form for 5,964/35,103 teams (17%)
- **Fix:** Enrichment must target ALL shortlisted teams regardless of DB presence. Create team_id entries for new teams, fetch form from ESPN/Flashscore, ingest into team_form.

### BUG C: FIXTURE_ONLY Scores Same as STATS_ONLY (75.0) (2026-05-14)
- **File:** `scripts/build_shortlist.py`
- **Impact:** `--top 200` picks 144 dateless candidates alongside 56 with real stats
- **Fix:** (a) deprioritize FIXTURE_ONLY (score × 0.5), OR (b) `--data-tier STATS_ONLY` flag, OR (c) sort by data_tier FIRST

### BUG D: deep_stats --top 200 Artificial Limit (2026-05-14)
- **Fix:** Use `--top 500` or filter to STATS_ONLY candidates first

### BUG E: Odds Evaluator Name Matching Broken (2026-05-12)
- **Evidence:** 0.5% auto-match rate. "Montreal Canadiens" vs "Montréal Canadiens"
- **Fix:** Fuzzy matching with Levenshtein ≤ 3 or normalized containment

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

### Enrichment Backlog (non-critical, fix later)
1. **Skip Flashscore for tennis** — ALL player pages 404, wastes ~10 min
2. **Gemini News (--news) produced 0 results** — investigate if phase ran
3. **Thread-guarded clients (TotalCorner, Scores24) skip ALL worker threads** — need second pass on main thread
4. **Lower-league teams 404 on Flashscore** — maintain "known-missing" cache

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
