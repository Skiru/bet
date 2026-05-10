---
applyTo: "betting/**/*"
---

# Analysis Methodology — Daily Protocol (Compact)

## ULTIMATE RULE: BET STATISTICS, NOT OUTCOMES

We bet on **statistical markets** (corners, fouls, shots, games, sets, points, frames, rounds) — NOT on who wins. Statistical markets accumulate throughout the match, are driven by team/player STYLE (structural), survive in-match chaos, and are systematically mispriced by bookmakers. Outcome markets (ML, winner, goals) depend on finishing luck and single moments. **Every pick must be a statistical market unless no statistical market exists for that event.**

Goal: find MISPRICED ODDS in statistical markets. EV > 0 is the only valid reason to bet.

> **Sport-specific protocols** (stats tables, upset checklists, red flags) are in [sport-analysis-protocols.instructions.md](sport-analysis-protocols.instructions.md). Load that file when performing STEP 3+ analysis.

---

## DATA ARCHITECTURE

All pipeline data is stored in SQLite DB (`betting/data/betting.db`) as the primary source. JSON files are maintained as human-readable fallbacks and debug output. Scripts use `db_data_loader.py` functions which try DB first, then JSON fallback.

**Key DB tables:**
- `fixtures` — all events for the betting day (replaces `scan_summary.json` reads)
- `odds_history` — odds from all sources (replaces `odds_api_snapshot.json` reads)
- `team_form` — L10/L5/H2H statistics per team (replaces `stats_cache/*.json` reads)
- `match_stats` — per-match raw statistics
- `analysis_results` — S3 deep stats output: market rankings, safety scores (replaces `{date}_s3_deep_stats.json`)
- `gate_results` — S7 gate check output: approved/extended/rejected (replaces `{date}_s7_gate_results.json`)
- `coupons` + `bets` — placed bets and coupon history (replaces `betclic_bets_history.json` reads)
- `league_profiles` — Bayesian priors per competition
- **`athletes`** (6,648) — player profiles: position, age, status (NBA 538, NHL 950, Football 4,160, WNBA 223)
- **`player_gamelogs`** (25,943) — game-by-game individual stats: points, rebounds, assists, goals, saves, shots. Use for player prop verification and team totals consistency. (NBA 11,599 + NHL 11,039)
- **`player_splits`** (4,716) — home/away, wins/losses, day-of-week, rest-day splits per player (NBA 1,200 + NHL 1,330)
- **`standings`** (233) — enriched league standings: form, home/away records, streaks, goal diff (NBA 30 + NHL 32 + Football 126 + WNBA 15)
- **`team_ats_records`** — Against The Spread betting records per team: W-L-P overall and by venue
- **`team_ou_records`** — Over/Under betting history: overs-unders-pushes by venue. CRITICAL for totals markets.
- **`power_index`** — ESPN power rankings (relative team strength per sport)
- **`espn_predictions`** — ESPN BPI win probability model per fixture

**Gateway module:** `scripts/db_data_loader.py` — all DB read/write functions:
- `load_fixtures_from_db()`, `load_odds_from_db()`, `load_team_form_from_db()`
- `load_analysis_results_from_db()`, `save_analysis_results_to_db()`
- `load_gate_results_from_db()`, `save_gate_results_to_db()`
- `load_betclic_history_from_db()`

**Safety score input:** `scripts/normalize_stats.py` — `build_safety_input(sport, team_a, team_b, competition)` (DB-first, JSON cache fallback)

- **`load_espn_enrichment_for_team(name, sport)`** — ATS/OU records, standings, power index for basketball/hockey
- **`load_player_gamelogs_for_team(name, sport, n=10)`** — per-player game-by-game stats for entire roster
- **`load_sport_specific_cache(sport, name)`** — sport data caches

**Sport file caches** (auto-loaded by `deep_stats_report.py`):
- `stats_cache/espn_stats/basketball/nba/athletes/` — 782 individual player stat files

**Dual-write policy:** Scripts write to BOTH DB and JSON on output. JSON = human-readable debug. DB = queryable primary store.

---

## SPORT TIERS

| Tier | Sports | Scanning | Analysis |
|------|--------|----------|----------|
| **CORE (Tier 1)** | Football, Volleyball, Basketball, Tennis, Hockey | ALL leagues/divisions/tournaments — not just top leagues. Go deep: 2nd/3rd divisions, cups, youth internationals, women's leagues, regional tournaments. Every sub-page. | Full STEPS 3-7 per candidate. |

All 5 sports are Tier 1. There is no Tier 2.

**League depth (CRITICAL):** For all 5 sports — scan beyond the obvious. Examples:
- Football: not just EPL/LaLiga/Bundesliga but also Ekstraklasa, 2. Bundesliga, Serie B, Ligue 2, Eredivisie, Belgian Pro League, Turkish Super Lig, MLS, Liga MX, K-League, J-League, women's leagues, youth tournaments.
- Volleyball: PlusLiga, SuperLega, Ligue A, women's leagues, CEV Champions League, national cups.
- Basketball: not just NBA/Euroleague but also NBP (Poland), ACB, BSL, LNB, BCL, women's leagues.
- Tennis: all ATP/WTA draws at every level (250/500/1000/GS), Challengers (but NOT ITF).
- Hockey: NHL, KHL, SHL, DEL, Liiga, Czech Extraliga, IIHF tournaments.

**Data quality requirement (R14):** Every candidate MUST have data_quality_score computed. FULL ≥7/10, PARTIAL 4-6/10, MINIMAL <4/10. Only FULL/PARTIAL in core coupons. MINIMAL goes to Extended Pool.

---

## AUTOMATED PIPELINE MODULES

The pipeline has individual scripts for each step. The ORCHESTRATOR AGENT calls them one at a time (⛔ NEVER via `pipeline_orchestrator.py` — that is BANNED):

| Step | Script | What it does |
|------|--------|-------------|
| S3 | `scripts/deep_stats_report.py` | Reads from DB (`team_form`, `match_stats` tables; JSON fallback: stats cache), runs §3.0 `rank_markets()`, generates all 10 §S3 sections per candidate. Output: DB `analysis_results` table + `{date}_s3_deep_stats.json/.md` |
| S7 | `scripts/gate_checker.py` | Programmatic 18-point gate, §7.3 red flags, §6.5 upset risk, §7.6 sport diversity, risk tier (LR/MS/HR/N), confidence scoring. Output: DB `gate_results` table + `{date}_s7_gate_results.json/.md` |
| S8 | `scripts/coupon_builder.py` | Core portfolio + combo menu + extended pool, Kelly 1/4 staking, Polish-language output, §8.2 stress test. Output: `betting/coupons/{date}.json/.md` |

**Agent role:** After each script runs, the specialist agent (bet-statistician, bet-challenger, bet-builder) REVIEWS the output using `sequentialthinking`, fills data gaps, provides qualitative analysis, and catches methodology violations. Scripts = data. Agents = analysis.

---

## SCANNING MANDATE (NEVER VIOLATE)

1. **WIDE:** ALL 5 sports every run. All sports get league-depth priority. Never say "no events" without exhausting the FULL fallback chain (see source-registry.md) + a Google search.
2. **DEEP:** Enter EVERY tournament/league for all 5 sports. Landing pages hide 80%. Count matches. Cross-validate counts between ≥2 sources (>20% discrepancy = missed events).
3. **MULTI-LEVEL:** Per candidate: Tier A stats → Tier A markets → Tier B tipsters (read REASONING) → specialist sources → context.
4. **AGGRESSIVELY:** Source fails? Log the error, try next in chain immediately. All chain sources fail? Google `"[sport] matches today site:flashscore.com OR site:sofascore.com"` or `"[tournament] schedule [date]"`. After finishing other sports, RETRY failed sources (rate limits often clear in 15-30 min). **Never declare a sport empty without trying ≥3 independent sources + 1 Google search.**
5. **COMPARE:** Every data point needs ≥2 independent confirmations.
6. **RETRY LOOP:** After the first scan pass, review `scan_errors.json` and ALL failed sources. Retry each failed source ONCE. If it works now, add its events. Log final status.

**Minimums:** ≥50 events scanned, ≥80% scan completeness, shortlist across ≥3 sports (via `build_shortlist.py --stats-first`), final picks from ≥3 sports, core coupons scale with picks (target ≥5 when 10+ approved) + ≥4 combo coupons. **Target ≥30 picks in final market matrix for user to choose from.**

**SESSION PARITY:** Session type (full/day/night) controls ONLY the event time window. Analysis depth, coupon count, all steps, all validation = IDENTICAL regardless of session.

**NO AUTO-REJECTION RULE:** The pipeline NEVER auto-rejects events based on EV, safety scores, or historical hit rates. ALL discovered fixtures with available markets are shown in the market matrix. The USER decides which to bet on. The pipeline's job is to provide maximum information — odds, safety scores, H2H data, market alternatives — not to filter down to a tiny list. **This policy is enforced at script level:** `build_shortlist.py` uses advisory flags instead of auto-rejection, ensuring all events flow through to the market matrix regardless of calculated scores.

### §SCAN.7 MAJOR TOURNAMENT PROTECTION (NEVER SKIP)

**RULE: MAJOR TOURNAMENTS WORLDWIDE ARE NEVER SKIPPED, DEPRIORITIZED, OR FILTERED.**

Active major tournaments get PRIORITY treatment across the entire pipeline:

1. **During scanning:** ALL matches from active major tournaments must be discovered. If a tournament has 8 matches today, all 8 appear in the scan — not "top 2 by odds." Use tournament-specific sub-pages, brackets, and schedule pages. Cross-check match counts.
2. **During shortlisting:** Events from major tournaments are NEVER filtered out by FIXTURE_ONLY tier, low odds coverage, or sport caps. They always make the shortlist.
3. **During analysis:** Full STEPS 3-7 for every tournament match. Tournament context matters — pressure, fatigue, elimination dynamics, bracket position.
4. **During coupon building:** Tournament matches are premium candidates. They have high public visibility on Betclic (better liquidity, more markets available).

**What counts as "major tournament":**
- Football: Champions League, Europa League, Conference League, World Cup, Euro, Copa América, Copa Libertadores, Nations League (finals), FA Cup (later rounds), Club World Cup
- Tennis: Grand Slams (Australian Open, Roland Garros, Wimbledon, US Open), Masters 1000 (Indian Wells, Miami, Monte Carlo, Madrid, Rome, Canada, Cincinnati, Shanghai, Paris)
- Basketball: NBA Playoffs, EuroLeague Final Four, FIBA World Cup, NCAA March Madness
- Volleyball: CEV Champions League, World Championship, Nations League Finals, PlusLiga Playoffs, SuperLega Playoffs
- Hockey: NHL Playoffs, Stanley Cup, IIHF World Championship

**GATE:** If a major tournament is active today AND has matches, they MUST appear in the final market matrix. If missing → scan failed → re-scan that sport specifically for the tournament.

### §SCAN.8 MINOR LEAGUE VALUE EDGE (POSITIVE SIGNAL)

**RULE: LESS POPULAR LEAGUES CARRY A VALUE EDGE — THEY ARE NOT "WORSE" CANDIDATES.**

Bookmaker markets are LESS efficient for minor/lower leagues because:
- Less betting volume → less market correction → more mispricing
- Fewer sharp bettors monitoring these markets → slower line movement  
- Betclic often offers static lines (not adjusted) for smaller leagues
- Statistical patterns (corners, fouls, totals) are MORE stable in lower leagues (same teams play each other regularly, coaches don't rotate)

**Pipeline behavior:**
1. **NEVER penalize** events for being from an "obscure" league. 2. Bundesliga, Polish 1. Liga, Serie B, Ligue 2, Belgian First Division B, Swedish Allsvenskan, Norwegian Eliteserien, Danish Superliga, etc. are ALL valid and often PROFITABLE targets.
2. **Apply a VALUE BOOST** in shortlist scoring for events from non-top-5 leagues that have good statistical data coverage. These are often underpriced by bookmakers.
3. **Statistical markets in minor leagues** (corners, fouls, cards, totals) are especially strong because team styles are consistent and well-documented — fewer lineup changes, same coaches, predictable patterns.
4. **Flag to user:** In the market matrix, mark events from minor leagues with a `[VALUE]` tag so the user knows these have theoretical edge from market inefficiency.

**This does NOT mean:** randomly betting on leagues with zero data. Good data coverage + minor league = high edge. No data + minor league = skip (as normal).

### §SCAN.9 MAJOR DOMESTIC LEAGUE PROTECTION (NEVER SKIP)

**RULE: TOP DOMESTIC LEAGUES WORLDWIDE ARE NEVER SKIPPED, FILTERED, OR DEPRIORITIZED — REGARDLESS OF REGION.**

Major domestic leagues outside Europe are systematically underrepresented in the pipeline because scan sources and keyword matching favor European competitions. These leagues generate high betting volume on Betclic, have deep statistical data, and are active during Americas/Asia time windows — providing night-session coverage that European leagues cannot.

**Protected domestic leagues (MUST appear in scan when active):**

| Region | Football | Basketball | Other |
|--------|----------|------------|-------|
| 🇧🇷 Brazil | Brasileirão Serie A, Serie B, Copa do Brasil | NBB | — |
| 🇺🇸 USA | MLS | NBA | NHL (hockey) |
| 🇦🇷 Argentina | Liga Profesional, Primera Nacional | — | — |
| 🇲🇽 Mexico | Liga MX, Liga de Expansión | LNBP | — |
| 🇨🇴 Colombia | Liga BetPlay | — | — |
| 🇨🇱 Chile | Primera División | — | — |
| 🇨🇳 China | Chinese Super League (CSL) | CBA | — |
| 🇯🇵 Japan | J1 League, J2 League | B.League | — |
| 🇰🇷 Korea | K League 1, K League 2 | KBL | — |
| 🇦🇺 Australia | A-League | NBL | — |
| 🇸🇦 Saudi Arabia | Saudi Pro League (SPL) | — | — |
| 🇮🇳 India | Indian Super League (ISL) | — | — |
| 🇪🇬 Egypt | Egyptian Premier League | — | — |
| 🇿🇦 South Africa | PSL | — | — |

**Pipeline behavior:**
1. **+10 score boost** in shortlist scoring (between tournament +15 and minor league +6).
2. Events from these leagues NEVER filtered by FIXTURE_ONLY tier or sport caps.
3. **Empty competition field bypass:** If an event has a team from a protected league but the competition field is empty, infer the competition from team names and apply the boost anyway.
4. **Night session priority:** Americas and Asia leagues provide critical time-window diversity. Night sessions MUST include them.
5. **GATE:** If a protected league is active (in-season) AND has matches today but ZERO appear in the final matrix → scan coverage FAILED → investigate sources and re-scan.

**Why this matters:** The May 8 2026 pipeline had 17,480 scan results but only 18 candidates — zero from Brazil, zero from MLS main league, zero from China/Japan/Korea. The scan captured the events but aggressive filtering + empty competition fields + keyword mismatches eliminated entire continents.

---

## STEP 0: SETTLE PREVIOUS DAY + LEARN FROM HISTORY

1. Run `python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD`.
2. Auto-resolves: winner/1X2, totals, BTTS, DC. Manual: corners, cards, HC, MyCombi.
3. Update `picks-ledger.csv` (status, pnl), `coupons-ledger.csv` (status, pnl).
4. Calculate: day PnL, rolling 7-day PnL, per-market hit rates, per-league ROI.
5. **Post-mortem each LOSS:** bad thesis or variance? Record in learning log.
6. **CLV:** Record closing odds. `CLV = (closing_implied / placement_implied) - 1`. Track weekly avg.
7. Update `working_bankroll_pln` in config. If −20% from peak → reduce daily cap 25%.

### §0.2 HISTORICAL LEARNING QUERY (MANDATORY before scanning)
Before STEP 1, query the picks-ledger AND the Betclic bet history to extract actionable patterns. This takes 2 minutes and prevents repeating proven failures.

**§0.2a BETCLIC HISTORY FILE (MANDATORY — NEVER SKIP)**
```
DB: load_betclic_history_from_db() → bets + coupons tables (primary)
JSON fallback: betting/data/betclic_bets_history.json
run: python3 scripts/analyze_betclic_learning.py
```
This data contains **ALL actually placed bets** from the Betclic account (ground truth). It MUST be read (from DB first, JSON fallback) and its analyzer output applied BEFORE any analysis begins. The analyzer produces current stats — always use its live output, not memorized numbers. Core patterns (verified by data):
- Statistical markets consistently outperform outcome markets. ALWAYS prefer statistical.
- Football corners = top core market. Match winner = #1 coupon killer. DEMOTE ML to last resort.
- AKO (5+) has near-zero win rate. MAX coupon size = 4 legs. Sweet spot: AKO (2-3).
- UNDER direction outperforms OVER. Actively seek UNDER plays.
- High-stakes coupons (5+ PLN) have significantly worse win rate. Keep stakes small.

**GATE: If Betclic bet history is not read (from DB or `betclic_bets_history.json`), the §0.2 step is INCOMPLETE. Do NOT proceed to STEP 1.**

If the file is missing, run: `python3 scripts/parse_betclic_bets.py` (requires HTML export from betclic.pl/my-bets).

1. **Per-market hit rate:** Group settled picks by `market` column. Calculate win% per market type (e.g., corners: 75%, ML: 40%, BTTS: 55%). Cross-reference with Betclic history market rates. **ADVISORY ONLY** — show rates prominently in report for user awareness. NEVER auto-reject or auto-exclude any market based on hit rate alone.
2. **Per-sport hit rate:** Group by `sport`. Cross-reference with Betclic history sport rates. Any sport with <30% hit rate on 5+ picks → **FLAG for user attention** (show in report). **NEVER blanket-reject an entire sport. NEVER apply automatic confidence penalties.** <5 settled picks = insufficient sample for any sport-level action. Each candidate is analyzed individually through STEP 3-7 regardless of sport-level hit rate.
3. **Coupon failure analysis:** For each LOST coupon, identify the leg that failed. Cross-reference with Betclic §7 coupon killer analysis. Track which pick types are the "coupon killers." Show coupon killer data in report for user awareness — do NOT auto-exclude from any coupon tier.
4. **Streak check:** Any team/player appearing 3+ times in recent picks? Check if the thesis is stale or if the edge has been priced in.
5. **Betclic history cross-check (ADVISORY ONLY):** Show all market/sport hit rates from Betclic history in the report. **NEVER AUTO-REJECT any market/sport combination based on historical hit rates.** All markets must receive full STEP 3-7 analysis regardless of past performance. The user decides whether to act on low hit rate warnings.
6. **Write a 3-line summary** of what the data says today. Example: "Corners 6/8 (75%). Tennis ML 1/5 (20%) — ⚠️ low rate. Hockey totals killing coupons — ⚠️ flagged."

---

## STEP 1: SCAN — Complete Event Discovery

1. Run `python3 scripts/scan_events.py --deep --max-deep-links 30 --workers 8 --date YYYY-MM-DD` (agent-driven — NEVER use `pipeline_orchestrator.py`). Check `scan_errors.json`.
2. Run `python3 scripts/fetch_odds_api.py` for cross-validation (30 credits/scan, 500/month free).
3. Browse BetExplorer + Flashscore + OddsPortal for all 5 sports.
4. **Deep Scan (§1.2):** Click into EVERY active tournament/league. Count matches per tournament.
5. **Tournament depth (§1.3):** Major tournament active? Analyze FULL daily slate (all matches, not 1-2). ANY tournament with ≥4 matches → screen ALL.
6. **Cross-validate:** Compare event counts per sport between ≥2 sources. Discrepancy >20% → investigate.
7. Record per event: sport, competition, event, kickoff, initial odds, source.

**5-SPORT CHECKLIST (mandatory — check each):**
- **CORE (deep league scan):** Football, Tennis, Basketball, Volleyball, Hockey.

**Niche sport source fallback (BetExplorer returns empty for some sports):**
Primary: Flashscore (fixtures + odds) → scores24.live (odds + trends) → OddsPortal. BetExplorer is EXPECTED to fail for niche sports — use the other sources.

### §1.5 TIPSTER PRE-FETCH (MANDATORY — runs as part of STEP 1)

Before STEP 2 filtering, fetch TODAY's pages from ALL argument-based tipster sites using Playwright. This ensures tipster arguments are available for STEP 4 analysis.

**Execution:**
```bash
# Fetch today's tipster pages (zawodtyper uses daily URL pattern)
python3 scripts/fetch_with_playwright.py "https://zawodtyper.pl/typy-dnia-[DD]-[month-polish]-[weekday-polish]/"
python3 scripts/fetch_with_playwright.py "https://typersi.pl/"
python3 scripts/fetch_with_playwright.py "https://www.sportsgambler.com/predictions/today/"
python3 scripts/fetch_with_playwright.py "https://www.pickswise.com/tennis/"
python3 scripts/fetch_with_playwright.py "https://www.betideas.com/tips/football"
```

**Zawodtyper daily URL pattern:** `/typy-dnia-[DD]-[month]-[weekday]/` where month and weekday are in Polish lowercase (e.g., `kwietnia`, `poniedzialek`). The page is lazy-loaded — Playwright handles this.

**Parse the fetched HTML** to extract ALL tipster entries: sport, event, tipster name, pick, odds, and FULL WRITTEN ARGUMENT. Save structured output to `betting/data/{date}_s1_tipster_prefetch.md`.

**Tipster-sourced candidates:** Any tipster pick that targets a **statistical market** (corners, cards, fouls, totals, games, frames) with argument-backed data (H2H stats, corner counts, historical lines) → add to shortlist even if not found in Tier A stats scan. These picks enter STEP 3+ analysis like any other candidate.

**GATE:** If zawodtyper fetch fails → retry once after 5 min. If still fails → proceed but mark S4 as `TIPSTER-DEGRADED`. Never skip the fetch attempt.

**Source fallback chains per sport:** See [source-registry.md](../../betting/sources/source-registry.md).

**Scan Completeness Gate (§1.6):** Before STEP 2, compile per-sport event count table from ≥2 sources. Total ≥50 events, ≥6 sports with events, completeness ≥80%. If not met → go back.

### §1.9 MARKET MATRIX GENERATION (MANDATORY — after scan completeness gate)

**After scan + fixture discovery, generate the comprehensive market matrix:**
```bash
python3 scripts/generate_market_matrix.py --date YYYY-MM-DD --stats-first
```

This produces THREE files (+ DB records):
1. `betting/data/market_matrix_{date}.json` — full structured matrix (also stored in DB `fixtures` + `odds_history` tables)
2. `betting/data/market_matrix_{date}.md` — human-readable market matrix with ALL events
3. `betting/data/decision_matrix_{date}.md` — compact bettable opportunities list

**Then build the ranked shortlist:**
```bash
python3 scripts/build_shortlist.py --date YYYY-MM-DD --stats-first
```

This produces:
4. `betting/data/{date}_s2_shortlist.md` — all ranked candidates with sport diversity
5. `betting/data/{date}_s2_shortlist.json` — structured shortlist for downstream steps

**Purpose:** Bridge the gap between fixture discovery (hundreds of events) and analysis (which requires cached stats). The market matrix shows ALL discovered events with whatever data is available — odds, safety scores, scan data. Nothing is auto-rejected.

**Data tiers in the matrix:**
- **FULL:** Odds + safety stats + H2H data (best quality)
- **ODDS_RICH:** Odds from multiple sources (no deep stats yet)
- **ODDS_BASIC:** Odds from single source
- **STATS_ONLY:** Safety stats but no odds found (user checks Betclic)
- **FIXTURE_ONLY:** Fixture exists but no odds/stats attached yet

**The matrix is the PRIMARY input for STEP 2 shortlisting.** Events at ANY data tier can be shortlisted — FIXTURE_ONLY events just need manual odds lookup on Betclic. The user sees the full landscape of what's available.

**Deduplication:** The matrix generator automatically deduplicates events where the same teams appear in the same sport from multiple sources (e.g., fixtures API + scan). The entry with the best data tier is kept, and odds/safety markets from duplicates are merged in.

### §1.8 FIXTURE VERIFICATION GATE (MANDATORY — before shortlisting)

**Problem:** Tipster sites (especially ZawodTyper) frequently reference wrong opponents, wrong dates, matches already played, or events from other rounds. On 2026-04-29, 58% of the shortlist (19/33) turned out to be phantom fixtures. This wastes pipeline capacity and distorts shortlist quality metrics.

**Rule: EVERY candidate entering the S2 shortlist MUST be fixture-verified against ≥2 independent non-tipster sources.**

Verification sources (use ≥2 per candidate):
- **Odds-API snapshot** (DB `odds_history` table; JSON fallback: `odds_api_snapshot.json`) — if event has live odds from ≥3 bookmakers, it exists
- **Flashscore** — check sport-specific daily schedule page
- **BetExplorer** — check competition page for today's matches
- **Official tournament site** (ATP/WTA draws, EHF schedule, ekstraliga.pl, etc.)
- **Sofascore** — alternative fixture verification

**Tipster-only candidates (no independent fixture confirmation):**
- If tipster references an event that appears in ZERO non-tipster sources → **DO NOT SHORTLIST**. Log as `UNVERIFIED-SKIP` in S1 notes.
- If tipster references a specific round/opponent but independent sources show a different opponent → **use the independently verified opponent**. Log the tipster confusion.

**Tennis-specific (critical — highest phantom rate):**
- ATP/WTA draws change daily. Before shortlisting ANY tennis match, verify the EXACT draw pairing on the tournament's official order of play or Flashscore.
- R16 results from yesterday may make today's R4/QF pairings different from what tipsters predicted. Always check CURRENT draw state.

**Quick verification protocol (per candidate, ~15 seconds each):**
```
1. Search event in DB `odds_history` table (or fallback: odds_api_snapshot.json) → found? ✅ verified
2. Not found? → Check Flashscore daily page for that sport → found? ✅ verified
3. Not found? → Check BetExplorer competition page → found? ✅ verified
4. Not found in ANY of the above? → DO NOT SHORTLIST. Log as UNVERIFIED-SKIP.
```

**§1.8a OVERNIGHT GAME TRAP (MANDATORY — prevents phantom inclusions):**

Tipster sites (especially ZawodTyper) list tips for overnight games (01:00-06:00 CEST) that were ALREADY PLAYED the previous night. This is the #1 source of phantom fixtures.

**Detection protocol:**
1. For ANY event with kickoff time 00:00-06:00 on the ZT daily page: check if the tip was posted >12 hours ago AND the game time has already passed.
2. Look for post-game comments on the ZT page (e.g., "W plecy 97:113", results, score references) — these confirm the game is OVER.
3. Cross-check: search Flashscore for the event. If result is already posted → PHANTOM. Do NOT shortlist.
4. NBA/NHL playoff games at 01:00-04:00 CEST on a Wednesday ZT page typically played TUESDAY NIGHT (already over by Wednesday morning).

**Rule:** Events with kickoff < current_time → automatically PHANTOM unless confirmed as future event via live odds (odds_api_snapshot or BetExplorer showing active markets).

**Lesson (v5, 2026-04-29):** BOS-76ers (01:00), EDM-ANA (04:00), NYK-ATL (02:00), SAS-POR (03:30) were all on the ZT środa page but had ALREADY PLAYED Tuesday night. ZT comments confirmed results. These wasted analysis capacity in earlier versions.

**S2 shortlist MUST include a verification column:**
```
| # | Event | Fixture Verified | Verification Sources |
```
Any row with `Fixture Verified = ❌` → cannot enter shortlist.

### §1.7 EXOTIC LEAGUE PROTOCOL

**Definition:** An "exotic league" is any football competition OUTSIDE:
- Top 5 European leagues (EPL, LaLiga, Bundesliga, Serie A, Ligue 1) and their 2nd divisions
- Top established European leagues (Eredivisie, Belgian Pro League, Portuguese Primeira, Turkish Super Lig, Russian Premier, Swiss Super League, Austrian Bundesliga, Scottish Premiership, Greek Super League, Czech First League, Polish Ekstraklasa, Danish Superliga, Swedish Allsvenskan, Norwegian Eliteserien, Croatian HNL, Serbian SuperLiga, Ukrainian Premier, Romanian Liga 1)
- Primary US/MX/BR/AR/JP/KR leagues (MLS, Liga MX, Brasileirão, Argentine Primera, J-League, K-League)
- Continental club competitions (UCL, UEL, UECL, Copa Libertadores, Copa Sudamericana, AFC Champions League)

**Everything else is EXOTIC:** Peru Liga 1, Egyptian Premier League, Kings League, Uzbekistan Super League, Algerian Ligue 1, Saudi Pro League, Indian ISL, Vietnamese V-League, Faroe Islands, Gibraltar, Kosovo, all Central American leagues, all Central Asian leagues, etc.

**§1.7a BETCLIC MARKET GATE (MANDATORY — check BEFORE deep analysis):**
Before investing analysis time on ANY candidate (not just exotic — ALL candidates):
1. Check if the league/event exists on Betclic (betclic.pl relevant sport section).
2. If NO markets on Betclic → SKIP (no execution path). Log as `BETCLIC-UNAVAILABLE`.
3. If ONLY ML/1X2 on Betclic → proceed only if strong statistical edge exists AND ML is acceptable per §6.5 upset risk.
4. If statistical markets (corners, cards, totals, frames, games) exist on Betclic → proceed normally.
5. **For non-exotic leagues:** Check SPECIFIC STATISTICAL MARKET availability (e.g., fouls, team corners). Some leagues have corners but not fouls on Betclic. If the §3.0 top-ranked market doesn't exist on Betclic, use the next-ranked market that DOES exist.

**Lesson (v4, 2026-04-29):** Inter Turku vs HJK (Veikkausliiga) — fouls O22.5 was top-ranked market (safety 0.80) but Betclic does NOT offer fouls for Finnish football. This forced a last-minute market change to goals O2.5 (safety 0.60), significantly weakening the pick. CHECK BETCLIC MARKET AVAILABILITY BEFORE completing §3.0 analysis to avoid wasted effort.

**Lesson (v3, 2026-04-29):** Higgins vs Robertson — analysis assumed Betclic line 20.5 frames, but actual Betclic line was 22.5. When L10 avg = line (22.5 = 22.5), there is ZERO margin = no edge. ALWAYS verify the actual Betclic line before calculating safety scores.

**§1.7b DATA THRESHOLDS (relaxed for exotic leagues):**

| Requirement | Mainstream | Exotic |
|-------------|-----------|--------|
| H2H meetings minimum | 5 | 3 (flag as EXOTIC-THIN if <5) |
| Stat sources minimum | 3 | 2 (Flashscore/Sofascore + 1 specialist) |
| Tipster sources | ≥2 with reasoning | ≥1 (exotic leagues rarely covered by tipsters) |
| Corner/card stat source | TotalCorner + SoccerStats + Betclic | Soccerway + Flashscore match stats (fallback) |
| §3.0 market ranking | ≥3 alternative markets | ≥2 alternative markets (if data allows 3, do 3) |

Picks with EXOTIC-THIN data flags:
- CANNOT be in LR coupons
- Get −0.5 confidence adjustment
- Maximum 2 exotic picks per coupon
- Maximum 1 exotic pick per LR coupon (only if NOT EXOTIC-THIN)

**§1.7c SOURCE FALLBACK CHAIN (exotic football):**
```
Primary: Flashscore (fixture, H2H, match stats) + Sofascore (form, stats)
├── H2H thin? → Soccerway H2H + AiScore H2H
├── Corner/card stats missing? → Flashscore match-level stats (last 10 games, manual count)
├── League standings missing? → Soccerway standings + BetExplorer results
├── No SoccerStats/TotalCorner? → Betaminic (covers some exotic leagues) → Flashscore per-match corner counts (manual)
└── All fail? → Google "[league name] statistics [season]" for specialist sites
```

**§1.7d RED FLAGS SPECIFIC TO EXOTIC LEAGUES:**

| Red Flag | Description | Action |
|----------|-------------|--------|
| Match-fixing risk | League/country on known match-fixing watchlists (spotfixing.eu, IBIA alerts) | HARD REJECT for exotic leagues with active alerts. For flagged countries: skip low-division matches, only top-flight with high attendance. |
| Scheduling irregularities | Mid-week matches with no clear reason, frequent postponements, irregular kickoff times | FLAG — investigate before proceeding. Unusual schedule = potential integrity issue. |
| Extreme weather/altitude | High-altitude venues (Bolivia, Peru highlands, Central Asian cities), extreme heat (Middle East summer), monsoon season (SEA) | Adjust totals expectations. High altitude = more goals/corners. Extreme heat = fewer goals, lower pace. Monsoon = match postponement risk. |
| Kings League special rules | Shorter halves (20 min), special gameplay mechanics (shootouts, power-ups), entertainment format | SEPARATE ANALYSIS PROTOCOL. Do NOT apply standard football stats. Kings League H2H/form from previous Kings League seasons ONLY. Standard football metrics DO NOT TRANSFER. |
| Low attendance / closed doors | Matches with <1000 attendance or behind closed doors | FLAG — home advantage reduced. Adjust H/A split expectations. |
| Roster instability | Frequent mid-season transfers, loan army turnover, player migration between exotic leagues | INCREASE weight on L5 recent form (post-transfer window) over L10. Coach/roster stability check is CRITICAL. |
| Time zone mismatch | Kickoff at unusual local time (e.g., 3 AM local = potential integrity concern) | FLAG — investigate reason. Official schedule adjustments for TV are OK; unexplained off-hour matches = caution. |

**§1.7e EXOTIC LEAGUE CLASSIFICATION:**
- **Tier E1 (established exotic):** Saudi Pro League, Egyptian Premier League, Moroccan Botola, Algerian Ligue 1, UAE Pro League, Indian ISL, Colombian Liga BetPlay, Chilean Primera, Paraguayan Primera, Ecuadorian LigaPro, Peruvian Liga 1, Uzbekistan Super League, Kazakhstan Premier League, Georgian Erovnuli Liga, Kosovo Superliga, North Macedonian First League — reasonable data coverage, Flashscore/Sofascore available, BetExplorer usually has odds.
- **Tier E2 (thin data):** Bolivian Primera, Costa Rican Primera, Central American leagues, Iranian PGPL, Iraqi Stars League, Jordanian Pro League, Armenian/Azerbaijani leagues, Faroe Islands, Gibraltar, Andorra, San Marino — sparse data, limited H2H, Soccerway may be only reliable source.
- **Tier E3 (ultra-thin):** Bangladesh, Myanmar, Cambodia, Laos, Mongolia, Turkmenistan, Tajikistan, Kyrgyzstan — minimal data coverage, avoid unless strong reason and Betclic offers markets.
- **Entertainment:** Kings League — separate protocol, non-standard football rules.

Tier E3 picks require ALL of: Betclic market confirmed, ≥2 sources with data, EV > 0, and user explicit approval before placement.

---

## STEP 2: FILTER — Shortlist

**Automated shortlist generation:** `python3 scripts/build_shortlist.py --date YYYY-MM-DD --stats-first`
- Reads from DB `fixtures` + `odds_history` + `team_form` tables (fallback: `market_matrix_{date}.json`) and scores all events by: data tier, competition importance, sport tier, odds quality, tipster coverage
- Assesses sport coverage (informational per R4, never a gate). Data quality gate (R14) replaces sport diversity gate.
- Deduplicates same-team events across sources
- Produces `{date}_s2_shortlist.md` + `{date}_s2_shortlist.json` (also stored in DB; use `--top N` to cap)
- **§1.8 Fixture verification:** Each candidate is cross-referenced against DB `odds_history` table (fallback: odds_api_snapshot.json) and fixtures. Verified candidates get ✅, unverified get ⚠️. Unverified events should be manually confirmed before S3 analysis to avoid phantom fixtures.
- In STATS-FIRST mode, includes major competition FIXTURE_ONLY events for manual Betclic check

After automated generation, agent reviews and may adjust:

Remove: outside betting window, no Tier A coverage, <2h to kickoff, already started, exhibitions.
Prioritize: events WITH statistical markets (corners, totals, HC) over basic ML-only.
**Early Betclic market hint:** For niche sports (volleyball, table tennis, padel, speedway), check Betclic market availability BEFORE deep analysis. If market doesn't exist on Betclic → don't waste analysis time.
Preferred odds range: 1.30-3.50.
**Target: 50-100 events across ≥3 sports in shortlist. S3 deep analysis narrows to ~35 best picks for coupon building.** No single sport >40%.

**§2.1 MINIMUM PICK EXPANSION TRIGGER:**
If after S7 gate fewer than 4 picks survive OR fewer than 5 sports are represented in approved picks → DO NOT proceed to S8. Instead:
1. Identify ALL remaining S2 shortlist candidates that have NOT received S3 analysis — grouped by sport.
2. Process ALL of them through S3→S7 in sport-diverse batches (see §2.2). Priority: all 5 core sports with highest shortlist scores.
3. Do NOT cherry-pick only "API-verified" or "easy" events. The shortlist was built from verified fixtures — they ALL deserve analysis.
4. After expansion: re-check pick count AND sport diversity. If STILL <4 picks AND <5 sports after analyzing ALL shortlisted candidates → declare NO BET day.
5. NEVER narrow expansion to a single sport or data source. If the shortlist has 25 football + 5 volleyball + 8 handball + 14 tennis candidates, the expansion MUST cover all four — not just the sport with easiest API data.

**Lesson (v4, 2026-04-29):** v4 had only 3 picks (below minimum 4) because PK-02 (Higgins frames) was dropped for Betclic line mismatch. The pipeline should have triggered expansion rather than producing coupons with only 3 picks.

**Lesson (v4, 2026-04-30):** After S7 gate rejected all 3 initial core picks (2 phantom fixtures + 1 fabricated data), the emergency expansion only analyzed NBA playoffs + snooker + NHL — completely ignoring 25 football (UEL/UECL semifinals!), 5 volleyball (PlusLiga!), 8 handball (Bundesliga!), and 14 tennis candidates from the shortlist. 51K events were scraped but only ~8 got emergency analysis. The scan infrastructure was wasted.

### §2.2 S3 SPORT-DIVERSE BATCHING (MANDATORY — NEVER SKIP)

**Problem solved:** Without this rule, S3 analysis tends to cluster around one sport (usually basketball or the sport with easiest API data), leaving entire KEY sports unanalyzed. This wastes the extensive scan infrastructure.

**Rule: S3 MUST process candidates in SPORT-ROUND-ROBIN order, not sport-cluster order.**

Batching protocol:
1. Sort shortlist candidates by sport tier (KEY first) then by shortlist score (highest first).
2. Build S3 batches using round-robin across sports: pick the top candidate from each sport before picking the 2nd candidate from any sport.
3. Example for 100-candidate shortlist across 5 sports: Batch 1 = top football + top volleyball + top basketball + top tennis + top hockey (one per sport). Batch 2 = 2nd football + 2nd volleyball + ... Continue until all candidates are batched.
4. Process batches IN ORDER. This ensures that if S3 is interrupted or context runs out, ALL sports have at least some representation.
5. **NEVER process all candidates from one sport before starting another sport.**

**S3 Sport Coverage Gate (checked after EACH batch):**
```
Sports with ≥1 completed S3 analysis:  [X] / [Y total sports in shortlist]
Target: ALL sports covered after Batch 1.
```

**If a context window or time constraint forces partial S3:** The round-robin ensures maximum sport diversity in whatever candidates ARE analyzed. Partial S3 with 5 sports × 6 candidates each = 30 diverse picks >> 30 candidates all from basketball.

**CRITICAL: The S2 shortlist is a COMMITMENT.** Every candidate that enters the shortlist WILL receive full §3.0 analysis in S3 (see §3.0f). The only removals between S2 and S3 are PHANTOM/VOID/WRONG DATE/ALREADY STARTED — verified against ≥2 sources. Do NOT shortlist candidates you plan to skip later. If data looks thin at S2, either investigate further NOW or don't shortlist.

**§1.8 ENFORCEMENT:** Every S2 candidate MUST have passed §1.8 fixture verification (≥2 non-tipster sources). If a candidate was shortlisted without verification → REJECT at S2 gate. This prevents phantom fixtures from contaminating the shortlist and wasting S3 analysis capacity.

---

## STEP 3: STATS — Deep Analysis (per candidate)

> Load [sport-analysis-protocols.instructions.md](sport-analysis-protocols.instructions.md) for sport-specific stat tables and market decision protocols.

**Universal requirements for EVERY candidate:**
1. **H2H MANDATORY:** Last 5-10 meetings, home/away splits. H2H surprises override league position.
2. **Collect ALL stats** from sport-specific table (not some — ALL). Split by home/away.
3. **Calculate hit rates** for O/U lines.
4. **Run §3.0 STATISTICAL MARKET RANKING** (below). Rank ALL available stat markets by safety score. Choose SAFEST, not most interesting.
5. **Present TOP 2-3 markets** per match from §3.0 ranking table BEFORE choosing.
6. **NEVER default to ML/1X2.** Statistical markets ALWAYS preferred across ALL 5 sports.
7. ML only when: (1) no statistical market on Betclic AND (2) statistical edge overwhelming AND (3) price acceptable.
8. **COACH/ROSTER STABILITY CHECK (mandatory):** For EVERY candidate: Did the coach change in the last 5 matches? Any major transfers, loan returns, or squad changes in the last 14 days? New coach bounce = volatile form (first 5 games unreliable). Major roster change = stats from previous games may not apply.

### §3.0 STATISTICAL MARKET RANKING PROTOCOL (MANDATORY — NEVER SKIP)

**For EVERY candidate, BEFORE selecting a market:**

1. **List ALL bettable statistical markets** for that sport (see §3.0b table below).
2. **For EACH available market**, collect: (a) team/player L10 average, (b) H2H average for that SPECIFIC stat (last 5 meetings minimum), (c) recent form L5 average, (d) bookmaker line, (e) hit rate (how often L10 + H2H covered that line).
3. **Calculate SAFETY SCORE** per market: `safety = min(hit_rate_L10, hit_rate_H2H)`. Higher = safer. Use avg margin vs line as tiebreaker (Over: avg/line, Under: line/avg — bigger = more margin).
4. **Rank all markets** by safety score. Pick the TOP market — not your default/favorite.
5. **CONFLICT CHECK:** If H2H avg and L10 avg disagree by >20% on the same stat → FLAG. Weight recent form (L5) as tiebreaker. If L5 also conflicts with H2H → DOWNGRADE or SKIP.
6. **PRESENT the ranking table** in the analysis. Show WHY the chosen market beat alternatives.

**This means:** Football picks are NOT always corners. They could be fouls, cards, shots, throw-ins — whichever stat has the best safety score for THAT specific match. Tennis is NOT always O22.5 games — it could be U21.5, O/U sets, or game handicap. Basketball is NOT always total points — it could be team totals, quarter totals, or rebounds.

### §3.0b BETTABLE STATISTICAL MARKETS BY SPORT

> **Full table** in `bet-analyzing-statistics` SKILL.md §3.0b. Per-sport mandatory multi-market calculation tables in sport-analysis-protocols.instructions.md (§3.1M-§3.14M).
>
> **Quick reference:** Football (Fouls, Cards, Corners, Shots, Throw-ins, Goal kicks, Offsides, Goals, BTTS) | Tennis (Games, Sets, HC, Tiebreaks, Aces) | Basketball (Team pts, Quarter, Half, Total, Rebounds, 3PT) | Volleyball (Sets, Points, Set HC) | Hockey (Period, Goals, Shots, PP)

### §3.0c H2H MARKET-SPECIFIC VALIDATION (MANDATORY — NEVER SKIP)

**For EVERY selected market, you MUST have H2H data for THAT SPECIFIC STAT:**

- Picking corners? → Get H2H corner totals between these exact teams (last 3-5 meetings).
- Picking total games in tennis? → Get H2H game totals between these exact players (last 3-5 meetings, surface-filtered).
- Picking total points in basketball? → Get H2H combined scoring (last 3-5 meetings at this venue).
- Picking frame totals in snooker? → Get H2H frame counts (last 3-5 meetings).

**If H2H data for the SPECIFIC stat is unavailable:**
1. Mark pick as `H2H-STAT-BLIND` in the analysis.
2. Apply −0.5 confidence penalty.
3. The pick CANNOT be in a LR coupon.
4. Increase weight on L5 recent form as substitute.

**THREE-WAY CROSS-CHECK (mandatory for every pick):**
```
L10 AVERAGE → [value] → hit rate vs line: [X/10]
H2H AVERAGE → [value] → hit rate vs line: [X/5]
L5 RECENT  → [value] → trend: [UP/DOWN/STABLE]
ALL THREE must support the pick direction. 2/3 conflict → DOWNGRADE. 3/3 conflict → REJECT.
When H2H is unavailable, alignment shows "(H2H N/A)" — e.g. "2/2 SUPPORT (H2H N/A)".
This passes the gate but signals incomplete validation to the user.
```

### §3.0d DATA PROVENANCE (MANDATORY — NEVER SKIP)

**Every stat cited in S3 output MUST include ALL THREE:**
1. **Source name** — the exact website or tool (e.g., "SoccerStats", "TennisAbstract", "Flashscore H2H tab")
2. **Exact data point** — the specific number with context (e.g., "Liverpool avg 11.2 corners/match at home, L10 games")
3. **Fetch reference** — how the data was obtained (e.g., "web-fetch", "Playwright scan", "Odds-API snapshot")

**BANNED WORDS in S3 table cells** — if ANY of these appear as the SOLE content of a table cell, it is a STRUCTURAL VIOLATION and the candidate is REJECTED:
- "checked", "verified", "confirmed", "good", "fine", "OK", "done", "yes", "—", "N/A", "n/a", "see above"

**Examples:**
- ❌ `| Injury check | checked |` → VIOLATION
- ✅ `| Injury check | No injuries — ESPN injury report, 2026-04-28 08:30 |` → VALID
- ❌ `| H2H avg | good |` → VIOLATION
- ✅ `| H2H avg | 5.8 cards (5 meetings, Flashscore H2H) |` → VALID
- ❌ `| Safety | — |` → VIOLATION
- ✅ `| Safety | 0.70 |` → VALID

**Enforcement:** The orchestrator scans every cell in the S3 output. Banned word as sole content → auto-reject that candidate, return to bet-statistician.

### §3.0e MANDATORY PER-CANDIDATE OUTPUT TEMPLATE

> **Full template code block** in `bet-analyzing-statistics` SKILL.md. The template below is a COMPACT reference — the full version with all table formats lives in the skill.

**EVERY candidate in `{date}_s3_deep_stats.md` MUST have these 10 sections** (delimited by `══ CANDIDATE ... ══` and `══ END CANDIDATE ══`):

1. **§S3.1** H2H Analysis (market-specific) — ≥3 meetings, H2H avg, BLIND status
2. **§S3.2** Form & Stats Table — sport-specific, all columns, home/away split
3. **§S3.3** Market Ranking (§3.0) — ≥3 rows (≥4 football), Safety 0.00-1.00
4. **§S3.4** Three-Way Cross-Check — L10, H2H, L5 rows with alignment verdict
5. **§S3.5** Coach/Roster Stability — source named, date checked
6. **§S3.6** Injury/Suspension Check — source + timestamp per entry
7. **§S3.7** Top 3 Markets — from ranking with safety scores
8. **§S3.8** Recommended Market — cites §S3.3, explains WHY
9. **§S3.9** Sources Used — ≥2 rows with actual source names
10. **§S3.10** Depth Proof — 5 metrics with numbers

**VALIDATION (agent-driven via sequentialthinking):**
1. All 10 section markers present
2. §S3.3 ≥3 data rows (≥4 football), Safety values are decimal 0.00-1.00
3. §S3.4 has 3 rows with numeric values + alignment verdict
4. §S3.9 has ≥2 rows
5. No BANNED WORD (§3.0d) as sole cell content
6. §S3.6 injury check has source + timestamp
7. §S3.10 has 5 metrics with numbers

### §3.0f S3 COMPLETENESS GATE (MANDATORY — NEVER SKIP)

**EVERY candidate that survives the S2 shortlist MUST receive full §3.0 analysis. No exceptions.**

The ONLY valid reasons to remove a candidate BEFORE S3 analysis are:
1. **PHANTOM (ZT#6):** Fixture does not exist — wrong date, wrong opponent pairing, event already played. Verified against ≥2 independent sources (Odds-API, Flashscore, BetExplorer).
2. **VOID:** Fixture cannot be independently verified by ANY source outside the tipster that suggested it.
3. **WRONG DATE:** Event is not within today's betting window.
4. **ALREADY STARTED:** Event has already begun.

These pre-S3 removals are logged in a `PRE-S3 REMOVALS` table with the exact reason and verification sources.

### §3.0g ESPN PLAYER GAMELOGS — CONSISTENCY VERIFICATION (basketball/hockey)

When ESPN enrichment is available (`espn_enrichment` in S3 output for gamelogs across 2 sports), **USE IT** to verify statistical market consistency:

**Basketball:**
- Total points market → check top 3 scorers' game-by-game output. Variance > 8 pts/game → LOWER safety score for totals.
- Team total Over → check if star player had any games with <50% of typical output (injury scare, foul trouble, blowout).
- Per-player consistency metric: `std_dev / mean` — if >0.30 for key stat, team total is UNSTABLE.

**Hockey:**
- Goals market → check goalie save% by game. If starter has 2+ games with <0.880 save% → Under less reliable.
- Period goals → check if team scoring is front-loaded (P1 heavy) or back-loaded (P3 heavy) using gamelog data.

**How to use:**
```python
from db_data_loader import load_player_gamelogs_for_team
gamelogs = load_player_gamelogs_for_team("Detroit Pistons", "basketball", n=10)
# Returns list of dicts: [{player, game_date, stats: {pts, reb, ast, ...}}, ...]
```

**ALL remaining candidates after pre-S3 filtering MUST receive:**
- Full §3.0e template (all 10 sections §S3.1-§S3.10)
- §3.0 statistical market ranking with ≥3 markets
- §3.0c H2H market-specific validation
- Three-way cross-check

**S3 COVERAGE CHECK (gate before proceeding to S4):**
```
S2 shortlist count:           [N]
Pre-S3 removals (PHANTOM/VOID): [X]
Candidates requiring S3:       [N - X]
Candidates WITH completed S3:  [Y]
S3 COVERAGE:                   [Y / (N - X)] = must be 100%
```
**If S3 COVERAGE < 100% → STOP. Complete missing analyses before proceeding.**

**PRACTICAL S3 BATCHING PROTOCOL (when context window constrains full coverage):**
If the S2 shortlist has 100 candidates but S3 analysis is context-constrained, apply this priority protocol:
1. **Batch 1 (MANDATORY):** Use §2.2 round-robin — top 1 candidate per sport × all sports in shortlist (~15 candidates). This ensures every sport is represented.
2. **Batch 2:** Next top candidates per sport using round-robin. Focus on core sports (football, volleyball, basketball, tennis, hockey).
3. **Batch 3+:** Continue round-robin until all candidates analyzed OR all available context consumed.
4. **If context runs out before 100% coverage:** Document exactly which candidates were skipped and why. The skipped candidates MUST appear in the report as `S3-PENDING — not yet analyzed` (NOT silently dropped). On next rerun or continuation, start with the skipped candidates.
5. **NEVER silently drop candidates.** Every shortlisted candidate appears in one of: S3 analyzed → core/extended/rejected, S3-PENDING, or PRE-S3 REMOVAL (phantom/void).

**Tooling enforcement:** `build_shortlist.py` produces `{date}_s2_shortlist.json` (and stores in DB) with `fixture_verified` flags per candidate. The shortlist JSON/DB serves as a CHECKLIST — every `fixture_verified: true` candidate must have a matching entry in S3 output or PRE-S3 REMOVALS.

**After S3, ALL candidates with completed analysis are classified:**
- **CORE:** Passed 18-point gate fully → enters core portfolio
- **EXTENDED POOL:** Has EV > 0 but failed some gate checks → enters extended pool with bull/bear case
- **REJECTED:** EV ≤ 0, or bear > bull, or critical red flag → enters ODRZUCONE section with specific reason

**The user sees ALL three groups.** No candidate with completed §3.0 analysis and EV > 0 is silently dropped. Every analyzed candidate appears in either core, extended pool, or rejected list.

---

## STEP 3B: TIME-SENSITIVE DATA (run 2-3h before earliest event)

1. **Lineups:** Flashscore (~1h), SportoweFakty for speedway (~2-3h), DailyFaceoff for NHL goalies.
2. **Late injuries:** ESPN, team social media, ATP/WTA Order of Play.
3. **Weather:** Outdoor sports — run `python3 scripts/fetch_weather.py --date YYYY-MM-DD` (Open-Meteo API, free, no key) for automated weather data per venue. Covers temperature, precipitation, wind speed, conditions. Impact: rain → fewer corners/shots; wind → fewer goals; extreme heat → lower pace. If weather changed significantly since S3 → re-evaluate stat market direction.
4. **Odds movement:** Compare current vs analysis-time. If Betclic moved >10% → recalculate EV.
5. **If ANY finding contradicts thesis → re-evaluate. Downgrade or void if bear case strengthens.**

---

## STEP 4: TIPSTER DEEP-DIVE (per candidate)

Check ≥2 ARGUMENT-BASED tipster sites per candidate. Read WRITTEN REASONING, not bare picks.

**Sites:** ZawodTyper (PL), Typersi (PL), Meczyki (PL), OLBG (EN), PicksWise (EN), BetIdeas (EN), Sportsgambler (EN), Tipstrr (EN, verified ROI), GosuGamers (esports).

**Sport-specific tipster fallback chains (try in order until ≥2 sources found):**

| Sport | Primary | Secondary | Tertiary |
|-------|---------|-----------|----------|
| Football (PL) | ZawodTyper → Meczyki | Typersi → OLBG | Sportsgambler |
| Football (INT) | PicksWise → BetIdeas | OLBG → Sportsgambler | Typersi |
| Football (US/MX) | PicksWise | Sportsgambler | OLBG |
| Tennis | ZawodTyper → OLBG | Sportsgambler → PicksWise | Typersi |
| Basketball (EU) | Sportsgambler | ZawodTyper | Typersi |
| Basketball (US) | PicksWise | Sportsgambler | OLBG |
| Volleyball | ZawodTyper → Typersi | Sportsgambler | Meczyki |
| Hockey | PicksWise | Sportsgambler | OLBG |
| Football (Exotic SA) | Feedinco → Bettingclosed | Sportsgambler | OLBG → Google "[league] tips [date]" |
| Football (Exotic Africa/ME) | Tips180 → Feedinco | Bettingclosed → Tips180 | Sportsgambler → Google "[league] tips [date]" |
| Football (Exotic Asia) | AsiaBet → Feedinco | Bettingclosed → Tips180 | Sportsgambler → Google "[league] tips [date]" |
| Football (Exotic Europe minor) | ZawodTyper → Typersi | Feedinco → Bettingclosed | OLBG → Sportsgambler |

**Extract per tipster:** site, tipster name, specific pick, odds, reasoning summary (1-2 sentences with stats/facts cited).

**Consensus:** ≥70% agreement → +0.5 confidence. ≥60% contradiction → investigate, −1 or skip. Strong fact-based argument from 1 tipster against your thesis → investigate before finalizing.

### §4.2 STEP 4 COMPLETENESS GATE (MANDATORY)
Before proceeding to STEP 5, verify:
- [ ] Every shortlisted candidate has ≥1 tipster source with extracted reasoning.
- [ ] ≥80% of candidates have ≥2 tipster sources.
- [ ] If a candidate has 0 tipster sources after exhausting the fallback chain → mark as `TIPSTER-BLIND` in report. Still allowed but gets −0.5 confidence and CANNOT be in LR coupons.
- [ ] Record per-candidate tipster coverage in a summary table: `| Event | Sources checked | Sources with reasoning | Consensus |`
- [ ] §1.5 tipster pre-fetch HTML was used (not just web-fetch summaries).
- [ ] ALL tipster picks on statistical markets (corners, cards, games, frames, etc.) with argument-backed reasoning have been cross-referenced with shortlist.

**If <60% of candidates have ≥1 tipster source → STOP and fetch more before STEP 5.**

### §4.3 TIPSTER-SOURCED WATCHLIST PROMOTION (MANDATORY)

After STEP 4 analysis, review ALL tipster picks from the §1.5 pre-fetch that were NOT in the original shortlist. For each tipster pick that meets ALL of:
1. Targets a **statistical market** (corners, cards, fouls, totals, games, sets, frames — NOT ML/winner)
2. Has **argument-backed reasoning** with cited stats (H2H corner counts, historical line coverage, motivation context)
3. Tipster has **>55% tracked accuracy** on the site (or is a verified tipster on Tipstrr)
4. The event is within today's betting window
5. The event is available on Betclic (or likely to be)

→ **Add to LISTA OBSERWACYJNA (Watchlist)** with:
- Full tipster argument (translated to Polish if needed)
- Tipster name and accuracy % from the site
- The specific statistical data they cited
- Promotion criteria: "Wstaw jeśli: kurs Betclic ≥X.XX + potwierdzone przez ≥1 dodatkowe źródło statystyczne"

These are NOT auto-approved picks — they enter the watchlist with rich context so the user can evaluate and promote them manually.

**Blocked tipster sites:** Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV tips.

---

## STEP 5: ODDS + EV (per candidate)

1. **Market-best:** BetExplorer/OddsPortal. Cross-validate with The-Odds-API.
2. **True probability:** Pinnacle implied (strip margin) > statistical model > market consensus.
3. **EV = (true_prob × betclic_odds) − 1.** Must be > 0.
4. **Price gap:** `100 × ((betclic_odds / market_best) − 1)`. LR reject < −3%, HR reject < −5%.
5. **Line movement:** Steam moves (follow if aligned), RLM (follow sharp money).
6. **§5.5a DRIFT GATE:** If odds moved >8% from analysis → MANDATORY re-eval. No explanation → SKIP.
7. **Kelly (1/4):** `stake = (bankroll × f) / 4` where `f = (b×p − q) / b`. If f ≤ 0 → NO BET.
8. **MARKET PERFORMANCE TRACKER:** Before picking any market, check hit rate in picks-ledger AND Betclic bet history (DB `bets` + `coupons` tables; fallback: `betclic_bets_history.json`). Show rates prominently in the report. **ADVISORY ONLY** — NEVER auto-downgrade confidence or auto-exclude based on hit rates. The USER decides. Betclic history complements picks-ledger (larger sample).

**Learned caution zones (ADVISORY):** MLB totals 33% historical hit rate — ⚠️ flag for user. MLB overs ≥8.5 — ⚠️ flag for user. Show these observations prominently but NEVER auto-reject or auto-downgrade.

### §5.ALT STATS-FIRST MODE (when API odds are unavailable)

When odds APIs don't cover an event (common for: table tennis, snooker, darts, esports, padel, speedway, minor leagues), use the STATS-FIRST workflow:

1. **Complete S3 analysis normally** — safety scores, hit rates, three-way check all work WITHOUT odds.
2. **Mark the pick as `MANUAL_ODDS_CHECK`** instead of calculating EV.
3. **Output the probability portfolio** — for each market:
   - Hit rate (e.g., "O9.5 corners: 8/10 L10, 4/5 H2H = 80%")
   - Direction + margin (e.g., "avg 11.2 vs line 9.5 = +17.9% margin OVER")
   - Safety score (e.g., "0.80")
   - Suggested line range (e.g., "check Betclic for O9.5 / O10.5")
   - **Minimum acceptable odds** = `1 / hit_rate` (e.g., 80% hit rate → min odds 1.25)
   - **Poisson probability** = `P(hit)` from probability engine (e.g., "P(Over 9.5) = 87.6%")
   - **Fair odds** = `1 / P(hit)` (e.g., "Fair odds = 1.14")
4. **User workflow:**
   - Open Betclic app → find the event → check if the suggested market exists
   - Note the Betclic odds → if `odds ≥ fair_odds` → positive EV → bet
   - Quick mental EV: `P(hit) × odds > 1.0?` → YES = positive EV
5. **Skip:** price gap analysis, line movement, drift gate (no reference odds exist).
6. **Kelly staking uses Poisson probability** from probability engine: `p = P(hit), q = 1-p, b = betclic_odds - 1`. Stake = Kelly/4 as normal. Calculate AFTER user provides odds.

**STATS-FIRST picks enter the coupon output with:**
- `odds: CHECK_BETCLIC`
- `EV: MANUAL (min odds X.XX for EV>0)`
- `probability: X.XX% (Poisson/NegBin model)`
- `stake: PENDING (calculate after odds confirmed)`
- All other fields (safety, direction, hit rate, probability) filled normally.

**Generate the market matrix with:** `python3 scripts/generate_market_matrix.py --date YYYY-MM-DD --stats-first`

### §5.PROB PROBABILITY ENGINE (automated — runs in S3)

**The probability engine converts raw statistics into precise probability estimates using the Poisson distribution model.**

**Academic basis:**
- Maher (1982): Poisson model for football scoring — count-based events follow Poisson distribution
- Dixon & Coles (1997): Improved model accounting for correlation in low-scoring matches
- Generalized to ALL count-based sports markets: corners, fouls, cards, games, frames, points, etc.

**How it works:**
1. **λ estimation** (expected value) with recency weighting:
   - λ = 40% × L5_avg + 35% × L10_avg + 25% × H2H_avg
   - When H2H missing: λ = 55% × L5_avg + 45% × L10_avg
   - **Bayesian shrinkage:** When `league_profiles` data exists for the competition/stat, λ is shrunk toward the league average (stronger effect with fewer team games). Formula: `adjusted_λ = (team_games × λ + 5 × league_avg) / (team_games + 5)`
   - WHY these weights: L5 captures current form (most predictive for tactical changes), L10 captures season trend, H2H captures specific matchup dynamics (pressing team = more corners vs low block)
2. **Probability calculation:**
   - P(Over X.5) = 1 - CDF(X, λ) = 1 - Σ(k=0..X) [e^(-λ) × λ^k / k!]
   - For overdispersed data (variance/mean > 1.5): switches to negative binomial distribution
   - **NegBin uses the same weighted λ** as Poisson (not an unweighted mean of all values) — ensures consistency between models
3. **Fair odds:** fair_odds = 1 / P(hit) — the true breakeven odds
4. **True EV:** EV = P(hit) × bookmaker_odds - 1
5. **Confidence interval:** 90% bootstrap CI from 1000 resamples of match-level data
6. **Kelly 1/4 stake:** f = (b×p - q) / b, stake = bankroll × f / 4

**Script:** `python3 scripts/probability_engine.py --test` (self-test with sample data)
**Integration:** Called by the orchestrator agent during S3. Enriches every ranked market with probability, fair_odds, lambda, model_used, CI.

**Example output (football corners):**
```
Liverpool vs Arsenal — Corners Total:
Combined L10 avg: 14.9, L5: 13.6, H2H: 12.2
λ = 0.40×13.6 + 0.35×14.9 + 0.25×12.2 = 13.71

Over 9.5:  P=87.6%, fair_odds=1.14, CI=[80.4%–92.3%]
Over 10.5: P=80.4%, fair_odds=1.24, CI=[71.3%–87.2%]
Over 11.5: P=71.4%, fair_odds=1.40, CI=[59.6%–80.4%]
Over 12.5: P=61.2%, fair_odds=1.63, CI=[48.3%–71.4%]

→ If Betclic offers Over 9.5 @1.50: EV = 87.6% × 1.50 - 1 = +31.4% ✅
→ If Betclic offers Over 12.5 @1.45: EV = 61.2% × 1.45 - 1 = -11.3% ❌
```

**WHY Poisson over simple hit rate:**
- Hit rate = 8/10 = 80%. But was game #4 at 9 or 14 corners? Hit rate loses this information.
- Poisson uses the ACTUAL values (9, 14, 11, 8, etc.) and models the full distribution.
- This gives DIFFERENT probabilities for different lines from the same data.
- Hit rate says "80% over 9.5" — Poisson says "87.6% over 9.5 but only 61.2% over 12.5."

### §5.TIP TIPSTER AGGREGATION ENGINE (automated — runs in S1b)

**Parallel tipster fetching and consensus scoring from 12+ sites.**

**Script:** `python3 scripts/tipster_aggregator.py --date YYYY-MM-DD --workers 5`
**Integration:** Runs automatically in S1b (parallel enrichment step) alongside odds and weather.

**What it does:**
1. Fetches ALL tipster sites in parallel (5 concurrent workers)
2. Parses structured picks: sport, event, market, odds, reasoning, accuracy%
3. Classifies picks as "statistical" (corners, cards, games) or "outcome" (winner, ML)
4. Computes consensus: groups by event, measures agreement across tipsters
5. Generates confidence adjustments: ≥70% agreement → +0.5, ≤30% → −1.0
6. Outputs `{date}_tipster_consensus.json` and `{date}_tipster_consensus.md` (also stored in DB `analysis_results` table)

**Sites covered (12):**
- Polish: ZawodTyper, Typersi
- English: Sportsgambler, PicksWise, BetIdeas, OLBG, Tipstrr
- Exotic football: Feedinco, BettingClosed, Tips180
- Esports: GosuGamers

**Integration with S3 analysis:**
- Tipster picks targeting statistical markets with reasoning → boost shortlist priority
- Consensus data used in S7 gate check (gate #6: ≥1 tipster argument)
- §4.3 promotion: tipster picks with >55% accuracy + statistical market + cited stats → watchlist

---

## STEP 6: CONTEXT (per candidate)

- [ ] Fixture confirmed (not postponed)?
- [ ] Key absences (injuries, suspensions, rest)? — check ESPN, Flashscore, team social media.
- [ ] **Coach change in last 5 matches?** New coach = form data unreliable. Check Flashscore coach section.
- [ ] **Roster changes in last 14 days?** Transfers, loans, returns. Major signings disrupt chemistry.
- [ ] Competition context (relegation, dead rubber, cup final)?
- [ ] Fixture congestion (<72h between games)?
- [ ] Weather (outdoor sports)?
- [ ] Referee (cards/fouls markets)? — specific referee stats, not just "checked."

### §6.5 UPSET RISK ASSESSMENT (MANDATORY)

> Load [sport-analysis-protocols.instructions.md](sport-analysis-protocols.instructions.md) §6.5 for sport-specific checklists and thresholds.

Score EVERY candidate. Record: `UPSET: [X/Y] — [top 3 factors]`.
If score ≥ threshold → **ML BANNED**, statistical markets only.
**Paradox Rule:** High upset → OVER totals premium (competitive = more play). Low upset → OVERS dangerous (blowout).

---

## STEP 7: BEAR CASE + RED FLAGS + CONTRARIAN + GATE (per candidate)

### 7.1 Bear Case Template
```
PICK: [selection]
UPSET SCORE: [X/Y] — [top 3 factors]
BULL CASE: [1-2 sentences]
BEAR CASE: [1-2 sentences]
STREAK DEPENDENCY: [Y/N — if >5 games, reduce −1]
REGRESSION RISK: [xG mismatch? Overperformance?]
KEY FAILURE SCENARIO: [most likely way this fails]
20%-LOWER-ODDS TEST: [Y/N — if N, coupon leg only]
```

### §7.3 Instant Red Flags (30 seconds each)
> Load [sport-analysis-protocols.instructions.md](sport-analysis-protocols.instructions.md) §7.3. Run ALL sport-specific red flags. Any fired → REJECT, downgrade, or justify.

### §7.4 Contrarian Thinking (4 questions, EVERY pick)
1. Am I applying the right MODEL to this SPECIFIC case?
2. What's the #1 way this bet type LOSES?
3. Would I take it FRESH at CURRENT odds? (defeat anchoring)
4. What would a sharp disagree-er say?

### §7.5 PICK APPROVAL GATE (18 points, EVERY pick)
```
[ ] 1. Identity verified (full name, no slashes)
[ ] 2. WC/Q/LL / debut / stand-in / backup checked
[ ] 3. H2H ≥5 meetings checked (surface/venue splits)
[ ] 4. Injuries/suspensions/load management checked
[ ] 5. ≥2 independent sources (1 stats + 1 market)
[ ] 6. ≥1 tipster argument READ (reasoning extracted, site+name+pick logged). If 0 → TIPSTER-BLIND, −0.5 confidence, NO LR coupon.
[ ] 7. Upset risk scored (§6.5 checklist)
[ ] 8. EV > 0 calculated
[ ] 9. Odds drift <8% verified (or re-evaluated)
[ ] 10. Red flags checked (§7.3)
[ ] 11. Contrarian thinking done (§7.4)
[ ] 12. Bear case < bull case
[ ] 13. Not anchored (would take at current odds)
[ ] 14. 48h repeat check (same team+market lost → HARD REJECT)
[ ] 15. MULTI-MARKET COMPARISON: ≥3 alternative stat markets calculated for this match (§3.0). Best safety score selected.
[ ] 16. H2H STAT-SPECIFIC: H2H data for the EXACT stat being bet exists (§3.0c). If missing → H2H-STAT-BLIND, −0.5 confidence, no LR coupon.
[ ] 17. THREE-WAY ALIGNMENT: L10 avg + H2H avg + L5 recent all support pick direction. 2/3 conflict → DOWNGRADE. 3/3 conflict → REJECT.
[ ] 18. DATA QUALITY: Both teams have sufficient stat data (L10 form exists for both sides). One-sided or synthetic data → −0.5 confidence, no LR coupon.
ALL 18 PASS → APPROVED | ANY FAIL → REJECT/DOWNGRADE/WATCHLIST
```

**Advisory Tier System (assigned by gate_checker.py based on gate score):**
- **STRONG** (≤2 checks failed): High confidence — full stake
- **MODERATE** (3-5 failed): Good but gaps — standard stake
- **WEAK** (6-9 failed): Marginal — reduced stake or watchlist
- **FLAGGED** (10+ failed): Significant concerns — user must review carefully

Tiers are ADVISORY ONLY — user decides. ALL candidates shown in matrix regardless of tier.

### §7.6 POST-GATE SPORT DIVERSITY CHECK (MANDATORY — before S8)

**After S7 gate completes for ALL candidates, check sport diversity BEFORE proceeding to S8:**

```
S2 shortlist sports:               [list all sports]
S3 analyzed sports:                 [list all sports with completed S3]
S7 approved picks — sport breakdown: [sport: count]
Sports in approved picks:           [X]
```

**DIVERSITY GATE CONDITIONS:**
1. **≥3 sports in approved picks** → PASS. Proceed to S8.
2. **<3 sports in approved picks** → FAIL. Trigger §2.1 expansion on ALL unanalyzed shortlist candidates from missing sports.
3. **0 core sports (football/volleyball/basketball/tennis/hockey) in approved picks** → CRITICAL FAIL. Core sports had the most shortlist candidates — they MUST be analyzed.
4. **S3 analyzed fewer sports than S2 shortlisted** → FAIL. Every sport in the shortlist must have ≥1 candidate with completed S3.

**EXPANSION LOOP (if diversity gate fails):**
1. List all sports present in S2 shortlist but MISSING from S7 approved picks.
2. For each missing sport: take ALL unanalyzed candidates from S2 shortlist.
3. Run S3→S7 on them using §2.2 sport-diverse batching.
4. Re-check diversity gate. Repeat until PASS or all shortlist candidates exhausted.
5. **This loop has NO sport-preference bias** — football, volleyball, handball, tennis all get equal treatment.

**NEVER proceed to S8 with 0 candidates from any sport that had strong shortlist presence.** The shortlist was built from a comprehensive scan — honor that work. Sport diversity is informational (R4), but complete sport dropout warrants investigation.

---

## STEP 8: COUPONS + COMBINATION MENU

### §8.1 CORE PORTFOLIO (primary deliverable)

1. Rank approved picks: EV (highest) → confidence → price_gap.
2. **NO SINGLES.** Every pick in a coupon. Min 2 legs per coupon.
3. **UNIQUE EVENT PER COUPON (ABSOLUTE).** Each pick in ONLY ONE core coupon. Zero sharing.
4. **Coupon count = f(quality, NOT money).** Target ≥5 core coupons (requires ≥10 approved picks). Scale: 4-5 picks → 2 core, 6-7 → 3 core, 8-9 → 4 core, 10+ → 5+ core. <4 approved picks → NO BET.
5. Build diverse coupons: vary sports, markets, risk levels.
6. **Risk tier labels:** LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT. Target distribution: ≥2 LR, ≥1 MS, ≥1 HR (scale up with approved picks).
7. **Correlation check:** Same match = FORBIDDEN. Same league ≥2 = FLAG. Same narrative = REMOVE weaker.
8. Suggest stakes for ALL coupons. Total may exceed daily cap — user decides.
9. **Watchlist:** 2-3 backup picks with promotion criteria ("Promote if Betclic ≥ X.XX").

### §8.1b COMBINATION MENU (additional — user picks favorites)

After building the core portfolio, generate **additional combination coupons** that remix approved picks into new groupings. These are EXTRA options on top of the core list.

1. **Reuse allowed:** Picks from the core portfolio MAY be recombined into new coupons here. Same pick can appear in multiple menu combos.
2. **Target: 4-8 extra combos** across risk tiers (at least 2 LR, 1 MS, 1 HR).
3. **Each combo must have a distinct thesis** — don't just shuffle the same legs. Vary the angle: "all-corners combo", "safe-totals combo", "high-EV longshot", "3-sport diversifier", etc.
4. **Label clearly:** Prefix with "COMBO-" (e.g., COMBO-LR1, COMBO-MS1, COMBO-HR1) so user can distinguish core vs. menu coupons.
5. **Same rules apply:** min 2 legs, max same-sport 2, correlation check, combined odds arithmetic.
6. **User picks from the full list** (core + combos). Total suggested stakes WILL exceed daily cap — that's the point.

### §8.2 COUPON STRESS TEST (MANDATORY per coupon)
For EACH coupon, before finalizing:
1. **Probability estimate:** Multiply estimated true probabilities of all legs. P(coupon) = P(leg1) × P(leg2) × ... Example: 0.60 × 0.55 × 0.58 = 19.1%. If P(coupon) < 10% → HR only. If < 5% → consider dropping a leg or splitting.
2. **Weakest-leg identification:** Which leg has the lowest P(win)? Can it be swapped for a better pick from the approved pool WITHOUT creating correlation? If yes → SWAP.
3. **Catastrophe scenario:** Write ONE sentence: "This coupon fails if [specific scenario]." Example: "Fails if Madrid rains and corners drop below 8."
4. **Betclic market existence check:** Before building a coupon around a pick, verify the market EXISTS on Betclic. If the market doesn't exist (e.g., O20.5 games not offered, only O17.5) → drop or adjust the line.

**Coupon limits:** LR max 3.00 PLN, HR max 2.00 PLN. Max same-sport legs: 2 per coupon.

---

## STEP 9: VALIDATE V1-V10

### V1: Artifact Consistency
- pick_ids in coupon file exist in picks-ledger
- coupon_ids exist in coupons-ledger
- Stakes sum = total exposure. No duplicate IDs. UNIQUE EVENT PER COUPON in core portfolio. Combo coupons may reuse picks.

### V2: Per-Pick Sources
- Tier A stats source with specific data point?
- Tier A market source with specific odds?
- EV > 0 calculated? Confidence 1-5 justified?

### V3: Tennis
- Market hierarchy respected (games > sets > HC > ML)?
- Odds ratio ≤1.50, correct grade (STRONG/GOOD/BORDERLINE/REJECT)?
- Player identity verified? WC/Q/LL checked? Drift <8%?

### V4: Football
- Market hierarchy respected? Corner 3-source stack? BTTS >55%?

### V4b-V4k: Sport-specific checks
- V4b Volleyball: set totals checked, ML range 1.30-2.00, set handicap considered.
- V4c Esports: map pool checked, BO format noted, roster/stand-in confirmed.
- V4d Snooker: frame stats from CueTracker, format (BO) noted.
- V4e Darts: 3-dart avg, format (sets vs legs) noted.
- V4f Handball: home advantage factored (60-65%), half totals checked.
- V4g Table Tennis: ranking gap assessed, high variance noted.
- V4h MMA: finish rates checked, method of victory considered.
- V4i Padel: FIP ranking gap checked, partnership duration noted, indoor/outdoor surface.
- V4j Speedway: rider TRACK-SPECIFIC averages used (not season avg), lineup confirmed.
- V4k: Upset risk scored for EVERY candidate. ML bans enforced. Paradox Rule applied.

### V5: Coupon Structure
- Min 2 legs. Same-sport ≤2. No same-match.
- **Combined odds ARITHMETIC:** Multiply legs explicitly. Write product. Tolerance ±2%.
- Core portfolio: UNIQUE EVENT PER COUPON. Combo menu: reuse allowed.
- Core coupons scale with approved picks (2-5+). ≥4 combo coupons. Distribute across risk tiers.

### V6: Portfolio + Menu Completeness
- Core portfolio covers all approved picks (no orphans).
- Combo menu has ≥4 extra coupons with distinct theses (not reshuffled core legs).
- Multi-sport diversification within coupons. No tournament concentration.
- Total suggested stakes (core + combos) exceed daily cap — user picks.

### V7: Weaknesses
- List BORDERLINE picks, CONDITIONAL picks, weakest leg per coupon.
- V7b: Date & fixture verified for EVERY event.
- V7c: Cross-coupon integrity — core portfolio: no event in >1 coupon. Combo menu: reuse OK but no correlated narratives within single combo.

### V8: Source Completeness
- Every pick: ≥2 independent sources + ≥1 argument-based tipster.
- Sport-specific sources checked (football corners: TotalCorner+SoccerStats, tennis: TennisAbstract, hockey: NaturalStatTrick+MoneyPuck).
- H2H, injuries verified for EVERY pick.
- **V8b: H2H STAT-SPECIFIC CHECK:** For EVERY pick, H2H data for the SPECIFIC stat market exists (not just match results). If H2H-STAT-BLIND → pick is flagged, −0.5 confidence, excluded from LR coupons.
- **V8c: STATISTICAL MARKET RANKING AUDIT:** For EVERY pick, §3.0 ranking table was produced showing ≥3 alternative markets considered. If no ranking table → FAIL.

### V9: Coupon Optimization
- Picks ranked by EV×confidence. No orphan picks. No ≥3 same-market-type in coupon.
- Night coupons = night games only. Weakest-leg swap test per coupon.
- Combined odds sweet spots: 2-leg 2-4, 3-leg 4-10, 4-leg 8-20.

### V10: Final Sign-Off

**V10a: Forced Sport Enumeration** — ALL 5 sports listed with events/sources/candidates/picks. Any sport: 0 events + <3 sources → go back.

**V10b: Pick Approval Gates** — every pick passed 18-point gate (§7.5).

**V10c: Red Flags** — every pick had §7.3 checked. All fired flags addressed.

**V10d: Portfolio Damage** — if most-concentrated pick loses, ≥3 coupons survive.

**V10e: PER-PICK COMPLETENESS MATRIX (MANDATORY)**
```
| Pick ID | Tipster≥1 | H2H≥5 | H2H-Stat | StatRank | 3WayChk | Injuries | Sources≥2 | RedFlags | EV>0 | Gate18 | PASS |
|---------|-----------|--------|----------|----------|---------|----------|-----------|----------|------|--------|------|
```
- **H2H-Stat:** H2H data exists for the SPECIFIC stat being bet (§3.0c). ❌ = H2H-STAT-BLIND, −0.5 confidence, no LR coupon.
- **StatRank:** §3.0 statistical market ranking was done — ≥3 alternative markets evaluated, best safety score chosen.
- **3WayChk:** THREE-WAY CROSS-CHECK passed — L10 avg + H2H avg + L5 trend all support pick direction.
ALL 10 columns ✅ for EVERY pick. ANY ❌ → STOP, fix, re-check. **No coupon file without this matrix.**

ALL V1-V10 pass → **PORTFOLIO APPROVED.**

---

## STEP 10: ARTIFACTS

Write: report, coupon file, picks-ledger, coupons-ledger, source-log, learning-log.
Record `odds_checked_at` for every pick. Cross-check all IDs across files.

On reruns: increment version (v5→v6). Mark old pending as `superseded`. Keep all versions.

---

## ZERO TOLERANCE SHIELD — Proven Failures

| # | Failure | Root cause | Prevention |
|---|---------|-----------|-----------|
| 1 | Shelton ML lost (36 games) | ML on tennis | NEVER default to ML. O22.5 would have won. |
| 2 | Struff O22.5 lost (15 games) | Low upset risk = blowout | Paradox: LOW upset → UNDER bias. |
| 3 | Jodar O22.5 lost (16 games) | WC = binary outcome | WC/Q/LL → O22.5+ HARD REJECT. |
| 4 | Jodar identity confusion | Slash = two players | Full name + ranking + country. |
| 5 | Jodar drift +10.3% ignored | Not caught | >8% drift = MANDATORY re-eval. |
| 6 | Palmeiras date wrong | Wrong day | V7b: verify EVERY date on BetExplorer. |
| 7 | N11-01 in 5/7 coupons | Concentration | >60% → add resilience coupon. |
| 8 | ITF tennis all lost | Low-level unreliable | Skip ITF. ATP/WTA only. |
| 9 | HR1v5 odds wrong | No arithmetic | ALWAYS multiply legs explicitly. |
| 10 | Liverpool O1.5 TG vs Palace | H2H not checked | ALWAYS check H2H. Palace won ALL 3 recent. |
| 11 | PHI @ ATL direction wrong | "@" = Away @ Home confused | Verify home/away for EVERY event. |
| 12 | Basketball blanket-rejected on 0/2 | Small sample panic | NEVER blanket-reject sport on <5 picks. FLAG ≠ BAN. |
| 13 | Football defaulted to corners (fouls/cards/shots not checked) | Tunnel vision on one stat | ALWAYS run §3.0 RANKING for ALL available stats. Pick highest safety score. |
| 14 | Corner pick missing H2H corner data | H2H was match-level only | ALWAYS get H2H for the EXACT stat being bet (§3.0c). Match H2H alone ≠ stat H2H. |
| 15 | Betclic history skipped → repeated known failures | §0.2a not executed | ALWAYS read Betclic bet history (DB `bets`+`coupons` tables; fallback: `betclic_bets_history.json`) + run `analyze_betclic_learning.py` before ANY analysis. This is ground truth. |
| 16 | PSG vs Bayern cards approved without §3.0 ranking table | S3 output was narrative ("H2H avg 5.8 cards") without structured ranking table comparing cards vs corners vs fouls vs shots | §3.0e template is MANDATORY. §S3.3 ranking table must have ≥3 rows with real numbers. Orchestrator mechanically verifies section markers. |
| 17 | Narrative analysis substituted for structured template | Agent wrote paragraphs instead of filling §S3.1-§S3.10 sections with tables and numbers | Every candidate MUST have all 10 sections (§S3.1-§S3.10). Missing markers = STRUCTURAL VIOLATION = auto-reject. |
| 18 | Exotic league analyzed without Betclic market check | Full S3-S7 done on a league where Betclic has no markets | §1.7a BETCLIC MARKET GATE: Check Betclic market existence BEFORE starting deep analysis. No markets → SKIP. |
| 19 | 16/33 shortlisted candidates skipped S3 entirely | S3 only run for "top" candidates; rest silently dropped without analysis or user visibility | §3.0f S3 COMPLETENESS GATE: 100% of non-PHANTOM shortlisted candidates MUST receive full §3.0 analysis. ALL analyzed candidates appear in core, extended pool, or rejected list. User sees everything. |
| 20 | 58% shortlist was phantom fixtures (19/33) | Tipster-sourced events not verified against independent sources before shortlisting. Wrong opponents, wrong dates, matches already played | §1.8 FIXTURE VERIFICATION GATE: Every candidate must be verified against ≥2 non-tipster sources BEFORE entering S2 shortlist. Tipster-only = UNVERIFIED-SKIP. Tennis draws must be checked against current tournament state. |
| 21 | Emergency expansion narrowed to 1-2 sports (NBA+snooker), ignoring 25 football + 5 volleyball + 8 handball + 14 tennis shortlisted candidates | After S7 gate rejected initial picks, emergency re-analysis only targeted "API-verified" events from one sport instead of processing ALL remaining shortlist candidates across ALL sports | §2.1 expansion MUST cover ALL unanalyzed shortlist candidates using §2.2 sport-diverse batching. §7.6 POST-GATE CHECK verifies all shortlisted candidates were analyzed across all sports. NEVER narrow to just the sport with easiest API data. The 51K-event scan exists to provide BREADTH — use it. |

---

## COMMON MISTAKES (read before writing — entries unique to this section, not covered by Zero Tolerance Shield above)

1. Using "medium" as variant — only low-risk or higher-risk.
2. Old-style metadata in .md coupon file — metadata in ledger CSVs only.
3. Tennis ratio 1.12 as "GOOD" — it's ≤1.15 = STRONG.
4. Different confidence scores across files — one score everywhere.
5. Not flagging tournament concentration (>4 picks same tournament).
6. Labeling coupons "MEDIUM" or "ATP CLAY" — only LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT.
7. Inventing ratio grades — only STRONG, GOOD, BORDERLINE, REJECT exist.
8. Producing too few coupons — scale core with picks (2-5+), ≥4 combos = genuine choice for the user.
9. Missing Polish descriptions — every leg needs Polish parenthetical.
10. Claiming combined odds "verified" without showing arithmetic.
11. V10e matrix missing — PROTOCOL VIOLATION. Every pick must have ✅ on all 10 columns.

---

## MARKET HIERARCHY (ALL SPORTS — STATISTICAL MARKETS FIRST, ML IS LAST RESORT)

### WHY statistical markets beat outcome markets (CORE DOCTRINE)

Statistical/peripheral markets (corners, fouls, shots, points, games, sets, frames) are **fundamentally more predictable** than outcome markets (goals, ML, winner). This is not a preference — it's structural:

1. **Accumulation:** They pile up throughout the match (a team wins 5-8 corners per half regardless of score). High in-match sample = lower variance.
2. **Style-driven:** A pressing team always forces corners; a physical team always commits fouls. These are structural traits that persist even in upsets. Goals depend on finishing luck.
3. **Shock-resistant:** A red card or freak goal destroys ML but barely moves total corners/fouls/shots. Statistical markets survive in-match chaos.
4. **Mispriced:** Bookmakers focus liquidity on ML/goals. Peripheral markets get less attention = more edge for us.

**EVERY football match in shortlist MUST have ≥1 corners/fouls/shots market evaluated.** Never default to goals-only.

> **Full per-sport priority order table** in `bet-analyzing-statistics` SKILL.md and sport-analysis-protocols.instructions.md (§3.XM tables). Quick reference: Football (Fouls→Cards→Corners→Shots→…→1X2) | Tennis (Games→Sets→HC→ML) | Basketball (Team totals→Quarter→Game→Spreads→ML) | All sports: statistical markets FIRST, ML is LAST RESORT.
