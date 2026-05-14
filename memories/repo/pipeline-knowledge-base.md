# Pipeline Knowledge Base — Consolidated (May 4-14, 2026, updated 2026-05-14 PM)

## ✅ CRITICAL BUGS — ALL FIXED (2026-05-14)

| Bug | File(s) | Root Cause | Fix |
|-----|---------|------------|-----|
| **A** | `scan_events.py`, `flashscore.py` | Deep enrichment in ThreadPoolExecutor → Playwright greenlet crash. Also `f.className` JS error (DOMTokenList not string). | Sequential main-thread enrichment (`--deep-workers 1`, `--deep-limit 50`). JS: `String(f.className \|\| '')`. |
| **B** | `data_enrichment_agent.py` | Thread guards skipped ALL Playwright clients in workers → 89% teams got nothing. | Phase 2 main-thread retry for failed/empty teams after thread pool pass. |
| **C** | `build_shortlist.py` | FIXTURE_ONLY scored 75 (same as STATS_ONLY for good leagues). | FIXTURE_ONLY tier score 5→0 + total score ×0.5 multiplier. |
| **D** | `deep_stats_report.py` | `--top 200` picked 144 dateless candidates first. | Sort by data_tier before applying `--top` (STATS_ONLY+ first, FIXTURE_ONLY last). |
| **E** | `odds_evaluator.py`, `utils.py` | Exact string match — "Montréal" ≠ "Montreal". | All odds sources + candidate lookup use `normalize_team_name()` (accents, hyphens, FC/SC). Fuzzy substring fallback. |

---

## ⛔ KNOWN ISSUES — ALL FIXED (2026-05-14, Phase 3)

| Issue | File(s) | Root Cause | Fix |
|-------|---------|------------|-----|
| **1+2** | `unified.py` | ESPN created new client per league + 400 flood for ~65 leagues | Reuse 1 ESPNClient per sport, cache 400/404 failures in-memory |
| **3** | `unified.py`, `scan_events.py` | `get_fixture_stats()` on scheduled matches → guaranteed empty | Skip stats for `status="scheduled"`, pass status through chain |
| **4** | `flashscore.py` | "Advancing to next round" concatenated in team name from DOM | JS regex strip in `_JS_EXTRACT_FIXTURES` |
| **5** | `data_enrichment_agent.py` | Flashscore player pages 404 for all tennis players | Skip `_try_flashscore()` for `sport == "tennis"` |
| **6** | `flashscore.py` | `.h2h__row` selector stale | Added `[class*="h2h"]` wildcard fallback selectors |
| **7** | `gemini_news_enrichment.py` | 0 results logged without diagnostics | Added success/empty/error counters to batch_enrich_news |
| **8** | `data_enrichment_agent.py` | Lower-league teams 404 repeatedly every run | `known_missing_teams.json` cache with 7-day TTL |
| **9** | `scan_events.py` | `db_scan_results=0` on re-run misleading | Log "X skipped as duplicates", add `db_scan_attempted` metric |

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

### API Clients (2026-05-14)
- **unified.py** routes: Football(Flashscore→BetExplorer→Soccerway→ESPN), Tennis(Flashscore→Scores24→ESPN)
- **ESPN Site API** now uses **HTTPS** (was HTTP) — all endpoints confirmed working
- **ESPN `get_espn_league_for_competition()`** now uses **fuzzy substring matching** (was exact only). Matches "PKO BP Ekstraklasa"→pol.1, "La Liga EA Sports"→esp.1, etc. Longest-key-first to avoid ambiguity.
- **New clients:** BetExplorerClient(HTTP), OddsPortalClient(Playwright), TotalCornerClient(Playwright), Scores24Client(Playwright), SoccerwayClient(HTTP)
- **BetExplorer/Soccerway** `get_fixture_stats()` and `get_h2h()` are **stubs** (return `[]`, log debug). Only useful for fixture discovery + odds.
- **Sofascore Playwright fallback** now **reuses shared browser** (`_pw_browser` class-level cache) instead of launching/destroying per 403 request. Call `SofascoreClient.close_playwright()` for cleanup.
- **Disabled:** TheSportsDB, BallDontLie, API-Tennis
- **Sport adapters (2026-05-12):** Hockey=MoneyPuck PRIMARY, Tennis=TennisAbstract Elo, Basketball=Basketball-Reference enhanced

### Data Quality Guards (2026-05-14)
- **TeamRepo.find_or_create()** now **rejects garbage team names** before DB insert: ad text (`"#100 FREE $20"`), odds strings (`"- 1.03 11.00"`), promo text, separators. Raises `ValueError` — callers should catch.
- **Stat key `_home`/`_away` convention** is BY DESIGN: `build_stats_cache.py` saves venue-split keys (`corners_home`, `corners_away`), `enrichment.py` saves base keys (`corners`). Both consumers (`deep_stats_report.py`, `normalize_stats.py`) handle both conventions correctly.

---

## Execution Protocol (what works)

### Run-Then-Delegate Model (Model A — adopted 2026-05-14)
The orchestrator runs ALL scripts and delegates analysis-only to specialist subagents.
```
ORCHESTRATOR:
1. INSPECT: pylanceRunCodeSnippet → verify inputs (R18)
2. RUN: run_in_terminal(mode=async, --verbose, timeout)
3. THINK-WHILE-WAITING: sequentialthinking + pylanceRunCodeSnippet
4. MONITOR: get_terminal_output → watch for 404/403/timeouts → react immediately
5. EXTRACT: Parse AGENT_SUMMARY:{json} + key warnings
6. VALIDATE: pylanceRunCodeSnippet → verify outputs (R18)
7. DELEGATE: runSubagent(specialist) → pass AGENT_SUMMARY + log excerpts
8. RECEIVE: specialist returns analysis-only verdict (no script execution)
9. QUALITY GATE: 5-question check
10. DECIDE: PROCEED / FIX+RETRY / ESCALATE
```

**Why this replaced the old model (2026-05-14):**
- Subagents would launch scripts then sit idle at "Preparing" (R17 violation)
- Orchestrator was blind to 404/403 errors during subagent execution
- Despite extensive rules (R17, §ASYNC DELEGATION ENFORCEMENT, pre-filled async blocks, think_while_waiting field, Q6 quality gate), subagents still didn't comply
- Root cause: adding more rules doesn't help (instruction-design-lessons.md)
- Fix: remove script execution from subagents entirely — they ONLY analyze

### Structured Subagent Verdict Format (Model A — analysis-only)
Specialist agents receive script output and return verdicts in this format:

```
## Verdict: {script_name} (analysis-only)
```subagent_verdict
verdict: APPROVED | FLAGGED | REJECTED
quality_score: 1-10
script: {script_name}
exit_code: {from orchestrator context}
execution_model: analysis-only
```
### Metrics        — ≥3 rows, from provided script output
### Anomalies      — specific anomaly + root cause
### Analysis       — agent's ORIGINAL specialist reasoning
### Impact         — what downstream step should know
### Issues         — actionable blockers or `None`
### User Summary   — 2-3 plain-language sentences for user presentation
### Data For Orchestrator — required keys: next_step_ready, quality_flags, focus_points
```

**Section classification:**
- Facts-only: `subagent_verdict`, `Metrics`, `Anomalies`, `Issues`, `Data For Orchestrator`
- Reasoning: `Analysis`, `Impact`, `User Summary`

**Orchestrator duties:**
- Parse `subagent_verdict` → `Metrics` → `User Summary` → `Data For Orchestrator`
- Present user update: step header + User Summary + 2-4 key metrics + Next line
- Maintain quality ledger: step, agent, verdict, quality_score, key handoff fact
- 5-question quality gate before accepting any verdict (see §SUBAGENT OUTPUT VERIFICATION in orchestrate-betting-day.prompt.md)

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
