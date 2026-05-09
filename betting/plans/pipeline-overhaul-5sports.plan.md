# Pipeline Overhaul: 14 → 5 Sports Revolution

**Created:** 2026-05-09  
**Revised:** 2026-05-09 (v4 — script audit/cleanup, web research agent, phase validation, live betting window)  
**Status:** READY FOR IMPLEMENTATION  
**Goal:** Reduce to 5 sports with massively expanded league coverage, **DEEP data** for every analyzed match (H2H, form, injuries, coach stability, league context, tipster opinions), rewritten analysis pipeline, agent methodology enforcing sequential thinking at every step, web research agent for missing data, and live betting window support.

**CORE INSIGHT FROM USER:** The problem is NOT sport count — it's **data depth and analysis quality**. A shallow scan of 14 sports produces worse results than deep analysis of 5 sports with comprehensive data per match.

---

## Table of Contents

- [Phase 1: Core Configuration](#phase-1-core-configuration) — reduce sports, expand leagues
- [Phase 2: Script Updates — Sport Reduction](#phase-2-script-updates--sport-reduction)
- [Phase 3: Source Registry Overhaul](#phase-3-source-registry-overhaul)
- [Phase 4: DATA DEPTH REVOLUTION](#phase-4-data-depth-revolution) ← **#1 PRIORITY**
- [Phase 5: ANALYSIS PIPELINE REWRITE](#phase-5-analysis-pipeline-rewrite) ← **CRITICAL**
- [Phase 6: AGENT METHODOLOGY OVERHAUL](#phase-6-agent-methodology-overhaul) ← **CRITICAL**
- [Phase 7: Instructions & Methodology](#phase-7-instructions--methodology)
- [Phase 8: League Expansion](#phase-8-league-expansion)
- [Phase 9: Source Library (src/bet)](#phase-9-source-library-srcbet)
- [Phase 10: Skills Cleanup](#phase-10-skills-cleanup)
- [Phase 11: Code Review & Validation](#phase-11-code-review--validation)
- [Phase 12: Live Test](#phase-12-live-test)

---

## Phase 1: Core Configuration

### Task 1.1 — Reduce sports list in betting_config.json

- **Type:** [MODIFY]
- **File:** `config/betting_config.json`
- **Dependencies:** None (start here)
- **Changes:**
  - Replace the 14-item `"sports"` array with exactly 5:
    ```json
    "sports": [
      "football",
      "volleyball",
      "basketball",
      "tennis",
      "hockey"
    ]
    ```
  - No other fields change (bankroll, stakes, thresholds remain).
- **Definition of Done:**
  - `sports` array contains exactly 5 entries.
  - JSON is valid (parseable).
  - No other config values were modified.

### Task 1.2 — Remove sport groups from scan_urls.json

- **Type:** [MODIFY]
- **File:** `config/scan_urls.json`
- **Dependencies:** Task 1.1
- **Changes:**
  - Remove these 6 sport groups from `"sports"` object:
    - `"handball"` (30 URLs)
    - `"baseball"` (13 URLs)
    - `"esports"` (20 URLs)
    - `"combat"` (11 URLs — covers MMA/boxing)
    - `"racket"` (19 URLs — covers table_tennis/padel)
    - `"niche"` (27 URLs — covers snooker/darts/speedway)
  - Keep: `"football"`, `"tennis"`, `"basketball"`, `"volleyball"`, `"hockey"`, `"tipsters"`
  - Keep `"shared_sources"` and `"_legacy_urls"` sections unchanged.
  - Remove `hltv.org` and `dartsorakel.com` from `"shared_sources"` if present (they serve only removed sports).
- **Definition of Done:**
  - `sports` object has exactly 6 keys: football, tennis, basketball, volleyball, hockey, tipsters.
  - All URLs in remaining groups are valid (no orphaned references to removed sport URLs).
  - JSON is valid.

### Task 1.3 — Expand scan_urls.json with new leagues

- **Type:** [MODIFY]
- **File:** `config/scan_urls.json`
- **Dependencies:** Task 1.2
- **Changes:** See [Phase 5](#phase-5-league-expansion) for the full list of URL additions per sport. This task is the EXECUTION of Phase 5 research.
- **Definition of Done:**
  - Football group has ≥220 URLs (currently ~180).
  - Tennis group has ≥45 URLs (currently ~30).
  - Basketball group has ≥60 URLs (currently ~40).
  - Volleyball group has ≥55 URLs (currently ~35).
  - Hockey group has ≥40 URLs (currently ~25).
  - All URLs follow the Flashscore pattern: `https://www.flashscore.com/{sport}/{country}/{league}/`
  - No duplicate URLs within a group.

---

## Phase 2: Script Updates

### Task 2.1 — Update agent_protocol.py

- **Type:** [MODIFY]
- **File:** `scripts/agent_protocol.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) AGENT_SKILLS_MAP → `bet-scanner` section:**
  - Change `"Verify 14-sport coverage across all scan sources"` → `"Verify 5-sport coverage across all scan sources (Football, Volleyball, Basketball, Tennis, Hockey)"`
  - Change `"Review shortlist for sport diversity (≥8 sports), ensure KEY sports ≥60%"` → `"Review shortlist for sport diversity (all 5 sports represented), ensure comprehensive league coverage per sport"`
  - Remove references to niche/combat/racket scanning skills.

  **B) AGENT_SKILLS_MAP → `bet-enricher` section:**
  - Remove `"For niche sports (snooker, darts, speedway) → use specialist sources from bet-scanning-niche skill"` from recovery_actions.

  **C) STEP_AGENT_CONFIG → `s1_scan` section:**
  - Change task: `"Verify 14-sport coverage..."` → `"Verify 5-sport coverage (Football, Volleyball, Basketball, Tennis, Hockey)..."`
  - Change detailed_instructions item 2: `"Verify all 14 sports scanned: football, tennis, basketball, volleyball, baseball, hockey, handball, mma, esports, table_tennis, snooker, darts, padel, speedway"` → `"Verify all 5 sports scanned: football, tennis, basketball, volleyball, hockey"`

  **D) STEP_AGENT_CONFIG → `s1e_shortlist` section:**
  - Change task: `"Review shortlist for sport diversity (≥8 sports), KEY sport coverage (≥60%...)..."` → `"Review shortlist for sport diversity (all 5 sports), comprehensive league coverage, verify ALL candidates included, flag missing major leagues"`
  - Change instruction 2: `"Verify ≥8 distinct sports represented"` → `"Verify all 5 sports represented (football, volleyball, basketball, tennis, hockey)"`
  - Change instruction 3: `"Calculate KEY sport percentage: (football+tennis+basketball+volleyball) / total ≥60%"` → `"Verify all 5 sports have adequate league representation; flag any sport with <3 leagues"`
  - Change recovery_actions: `"If <8 sports → re-run build_shortlist.py with --min-sports 8"` → `"If any sport missing → re-run scan for that sport group"`

  **E) STEP_AGENT_CONFIG → `s2_5_enrich` section:**
  - Remove recovery action mentioning niche sports: `"For niche sports (snooker, darts, speedway) → use specialist sources from bet-scanning-niche skill"`

  **F) STEP_AGENT_CONFIG → `s7_gate` section:**
  - Change instruction 9: `"Verify ≥5 sports in approved picks per §7.6"` → `"Verify all 5 sports represented in approved picks per §7.6"` (keep the spirit but match new reality)

  **G) SELF_HEALING_REGISTRY:**
  - Keep `espn_data` modules but remove any mentions of sports no longer supported.
  - Keep `tennis_enrichment`, `api_stats`, `odds_api`, `playwright_fetcher` as-is (they serve kept sports).

- **Definition of Done:**
  - No references to "14-sport" or "14 sports" anywhere in the file.
  - No references to snooker, darts, speedway, baseball, esports, table_tennis, handball, mma, padel in scanner responsibilities or step instructions.
  - All sport diversity thresholds updated to reflect 5-sport model.

### Task 2.2 — Update build_shortlist.py

- **Type:** [MODIFY]
- **File:** `scripts/build_shortlist.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) PROTECTED_DOMESTIC_LEAGUES:**
  - Remove `"baseball"` key entirely (npb, kbo, cpbl, lmp).
  - Keep `"football"`, `"basketball"`, `"hockey"` keys — these still have protected leagues.
  - Add `"volleyball"` key with protected leagues:
    ```python
    "volleyball": [
        "plusliga", "superlega", "ligue a", "superliga", "v-league",
        "superliga brazil", "bundesliga", "efeler",
    ],
    ```
  - Add `"tennis"` key with protected tournaments:
    ```python
    "tennis": [
        "australian open", "roland garros", "french open", "wimbledon",
        "us open", "masters", "atp 1000", "wta 1000",
    ],
    ```

  **B) COMP_TIER_KEYWORDS:**
  - Remove these keys entirely: `"handball"`, `"baseball"`, `"snooker"`, `"darts"`, `"esports"`, `"mma"`, `"table_tennis"`, `"padel"`, `"speedway"`
  - Keep and enhance: `"football"`, `"tennis"`, `"basketball"`, `"volleyball"`, `"hockey"`
  - Add more lower-division keywords to football tier 6-7:
    ```python
    (6, ["2. bundesliga", "serie b", "ligue 2", "segunda", "3. liga",
         "serie c", "national league", "league two",
         "usl championship", "nwsl", "mls next pro",
         "division 1", "division 2", "1. liga", "first division b",
         "eerste divisie", "2nd division", "3rd division"]),
    (5, ["nations league", "qualification", "friendly",
         "regionalliga", "national league north", "national league south",
         "serie d", "4th division"]),
    ```
  - Add more basketball tiers:
    ```python
    (7, ["plk", "bbl", "bcl", "fiba", "lnb", "nbl", "lnbp",
         "basket liga", "a1 ethniki", "lega 2", "pro b",
         "superleague", "bkt liga"]),
    (6, ["division 1", "liga femenina", "wbbl", "wnbl",
         "2nd division", "1st division"]),
    ```
  - Add more volleyball tiers:
    ```python
    (7, ["efeler", "superliga", "plusliga playoff", "superlega playoff",
         "division 1", "liga a1", "eredivisie", "a1 ethniki"]),
    (6, ["2nd division", "division 2", "serie a2", "1st division",
         "v-league", "mestaruusliiga"]),
    ```
  - Add more hockey tiers:
    ```python
    (7, ["allsvenskan", "mestis", "1. liga", "ligue magnus",
         "erste liga", "tipsport liga", "echl", "eihl"]),
    (6, ["division 1", "2nd division", "hockeyettan", "optibet liga"]),
    ```

  **C) TIER1_SPORTS:**
  - Change from `{"football", "volleyball", "basketball", "tennis"}` → `{"football", "volleyball", "basketball", "tennis", "hockey"}`
  - (All 5 sports are now KEY / Tier 1 — there is no Tier 2 anymore.)

- **Definition of Done:**
  - PROTECTED_DOMESTIC_LEAGUES has exactly 5 keys (one per sport).
  - COMP_TIER_KEYWORDS has exactly 5 keys (one per sport).
  - TIER1_SPORTS has 5 entries.
  - No references to any removed sport in the file.

### Task 2.3 — Update generate_market_matrix.py

- **Type:** [MODIFY]
- **File:** `scripts/generate_market_matrix.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) `_sport_from_odds_key()`:**
  - Remove mappings for: baseball, mma, handball, snooker, darts (lines 70-83).
  - Keep: soccer→football, basketball, hockey, tennis, volleyball.

  **B) MAJOR_COMPETITIONS:**
  - Remove keys: `"handball"`, `"baseball"`, `"snooker"`, `"darts"`, `"esports"`, `"table_tennis"`, `"mma"`, `"padel"`, `"speedway"`
  - Expand remaining 5 keys with more lower-division keywords:
    - Football: add `"3. liga"`, `"serie c"`, `"serie d"`, `"national league"`, `"league two"`, `"regionalliga"`, `"division 1"`, `"premier league 2"`, `"primera federacion"`, `"national"` (France), `"2. division"` (Nordic), `"postnord"`, `"obos"`, `"ykkonen"`, `"1. deild"`, `"fnl"`, `"2. liga"`, `"nike liga"`, `"prva liga"`, `"first nl"`, `"nb ii"`, `"super league 2"`, `"challenger pro league"`, `"eerste divisie"`, `"1. lig"`, more Asian: `"liga 1"` (Indonesia), `"thai league"`, `"v.league"` (Vietnam), `"persian gulf"`, `"premier league"` (generic for India/Egypt/SA)
    - Tennis: add `"challenger"`, `"itf"`, `"futures"`, `"billie jean king"`, `"laver cup"`, `"olympics"`, `"next gen"`, `"hopman"`
    - Basketball: add `"g-league"`, `"summer league"`, `"wnba"`, `"wbbl"`, `"ncaa women"`, `"basket liga"`, `"pro a"`, `"pro b"`, `"bkt"`, `"betis"`, `"a1 ethniki"`, `"premijer liga"`, `"adriatic league"`, `"aba league"`, `"copa del rey"`, `"lkl"`, `"nbl"` (Czech), `"vtb"`, `"pba"` (Philippines)
    - Volleyball: add `"serie a2"`, `"a1 ethniki"`, `"eredivisie"`, `"euromillions"`, `"division 1"`, `"1st division"`, `"mestaruusliiga"`, `"v-league"`, `"super league"` (China), `"iranian"`, `"liga a1"` (Romania)
    - Hockey: add `"echl"`, `"eihl"`, `"ligue magnus"`, `"erste liga"`, `"mestis"`, `"hockeyallsvenskan"`, `"1. liga"` (Czech), `"tipsport liga"`, `"metal ligaen"`, `"optibet liga"`, `"allsvenskan"` (hockey)

  **C) `_is_major_competition()`:**
  - Remove `ZERO_ODDS_SPORTS` set (all 8 removed sports: snooker, darts, table_tennis, esports, mma, padel, speedway, australian_football).
  - The "include all events for zero-odds sports" logic is no longer needed — all 5 remaining sports have API odds coverage.
  - Simplify: just check against MAJOR_COMPETITIONS keywords + return `True` for all events from the 5 supported sports (since we're going deep on all leagues now).

- **Definition of Done:**
  - No references to removed sports in the file.
  - MAJOR_COMPETITIONS has exactly 5 keys.
  - _sport_from_odds_key handles only the 5 sports + "football" default.
  - _is_major_competition no longer has a ZERO_ODDS_SPORTS bypass.

### Task 2.4 — Update scan_events.py

- **Type:** [MODIFY]
- **File:** `scripts/scan_events.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) RATE_LIMITED_DOMAINS:**
  - Remove `"dartsorakel.com": 2.0` (darts specialist site).
  - Remove `"hltv.org": 2.0` (esports specialist site).
  - Keep: betclic.pl, soccerstats.com, totalcorner.com.

  **B) SPORT_URL_PATTERNS:**
  - Remove keys: `"handball"`, `"snooker"`, `"esports"`, `"darts"`, `"table_tennis"`, `"mma"`, `"padel"`, `"speedway"`, `"baseball"`
  - Keep: `"tennis"`, `"basketball"`, `"hockey"`, `"football"`, `"volleyball"`

- **Definition of Done:**
  - SPORT_URL_PATTERNS has exactly 5 entries.
  - No rate limiting entries for removed-sport-only domains.
  - `detect_sport()` returns only football/tennis/basketball/volleyball/hockey or "" for unknown.

### Task 2.5 — Update ingest_scan_stats.py

- **Type:** [MODIFY]
- **File:** `scripts/ingest_scan_stats.py`
- **Dependencies:** Phase 1
- **Changes:**
  - Remove sport-specific parser functions: `_parse_handball_scores`, `_parse_baseball_scores`, `_parse_snooker_scores`, `_parse_table_tennis_scores`, `_parse_darts_scores`, `_parse_esports_scores`, `_parse_mma_scores`
  - Remove `"padel": _parse_tennis_scores` mapping.
  - Remove entries for removed sports from the parser dispatch dict.
  - Keep: football, tennis, basketball, volleyball, hockey parsers.
- **Definition of Done:**
  - Parser dispatch dict has entries only for the 5 supported sports.
  - No dead code for removed sport parsers remains.
  - File parses and runs without import errors.

### Task 2.6 — Audit remaining scripts for removed sport references

- **Type:** [MODIFY]
- **File:** Multiple scripts (grep-driven)
- **Dependencies:** Tasks 2.1-2.5
- **Changes:** Search all `scripts/*.py` for remaining references to removed sports and update/remove them. Known files:
  - `scripts/fetch_api_stats.py` — may have sport-specific API client instantiation for handball, baseball
  - `scripts/fetch_odds_api.py` — may list sport keys including removed ones
  - `scripts/fetch_odds_multi.py` — may reference removed sports for Odds-API.io
  - `scripts/deep_stats_report.py` — may have sport-specific stat tables
  - `scripts/coupon_builder.py` — may have sport-specific market rules
  - `scripts/compute_safety_scores.py` — may have sport-specific thresholds
  - `scripts/gate_checker.py` — may reference sport diversity ≥8
  - `scripts/context_checks.py` — may have sport-specific context rules
  - `scripts/evaluate_decisions.py` — may track removed sports
  - `scripts/settle_on_finish.py` — may have sport-specific settlement rules
  - `scripts/probability_engine.py` — may have sport-specific models
  - `scripts/normalize_stats.py` — may have sport-specific normalization
  - `scripts/odds_evaluator.py` — may have sport-specific logic

  **Strategy:** For each file, search for the 9 removed sport names. Where they appear in:
  - **Sport lists/dicts:** Remove the entries for removed sports.
  - **If-else chains:** Remove branches for removed sports.
  - **Config reads:** No changes needed (they read from betting_config.json which is already updated).
  - **Comments/docstrings:** Update to reflect 5 sports.

- **Definition of Done:**
  - `grep -r "snooker\|speedway\|baseball\|esports\|darts\|table_tennis\|handball\|\bmma\b\|padel" scripts/` returns zero matches in functional code (comments about migration are OK).

### Task 2.7 — Deep review of all major pipeline scripts

- **Type:** [REVIEW]
- **Dependencies:** Tasks 2.1-2.6
- **Files:** ALL scripts used in the daily pipeline methodology:
  - **Core pipeline:** `build_shortlist.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, `scan_events.py`, `generate_market_matrix.py`
  - **Data fetch:** `fetch_api_stats.py`, `fetch_odds_api.py`, `fetch_odds_multi.py`, `fetch_odds_api_io.py`, `fetch_espn_odds.py`, `fetch_espn_standings.py`, `fetch_weather.py`
  - **Enrichment:** `data_enrichment_agent.py`, `html_deep_parser.py`, `normalize_stats.py`, `context_checks.py`, `tipster_aggregator.py`, `tipster_xref.py`
  - **Analysis:** `compute_safety_scores.py`, `probability_engine.py`, `odds_evaluator.py`, `upset_risk.py`, `deep_analysis_pool.py`, `s4_stats_first_pricing.py`
  - **Settlement:** `settle_on_finish.py`, `evaluate_decisions.py`, `analyze_betclic_learning.py`
  - **Ingestion:** `ingest_scan_stats.py`, `db_data_loader.py`, `seed_deep_stats.py`, `seed_espn_data.py`
  - **Support:** `agent_protocol.py`, `utils.py`, `validate_coupons.py`, `validate_phase.py`
- **Review checklist per script:**
  1. Does it serve the 5-sport pipeline? If not → candidate for cleanup (Task 2.8)
  2. Is it called from the daily agent-driven pipeline? If not → document why it exists
  3. Does it follow R2 (DB-first, `get_db()`)? Flag violations.
  4. Does it handle errors gracefully or silently fail? Flag silent failures.
  5. Does it produce data that feeds into analysis? Document the data flow.
  6. Is it duplicated by another script? Flag overlaps.
- **Definition of Done:**
  - Every script in `scripts/` categorized: ACTIVE (used daily), UTILITY (used occasionally), STALE (candidate for cleanup)
  - Data flow diagram: which script feeds which other script
  - R2 violations flagged
  - Silent failure patterns flagged

### Task 2.8 — Clean up stale, legacy, and unused scripts

- **Type:** [MODIFY/DELETE]
- **Dependencies:** Task 2.7
- **Candidates for cleanup (to be confirmed by Task 2.7 review):**
  - `pipeline_orchestrator.py` — **⛔ BANNED** by R1. Agent IS the orchestrator. This script should be archived/deleted.
  - `smoke_playwright.py` — test/debug script, not pipeline
  - `_audit_html_profiles.py` — internal audit tool with `_` prefix
  - `validate_agent_yaml.py` — one-time validation script
  - `validate_s3_output.py` — may be stale S3 validator
  - `check_48h_repeats.py` — may be obsolete
  - `build_league_profiles.py` — may be superseded by Phase 4 league context
  - `deep_link_discovery.py` — may be one-time URL discovery tool
  - `discover_fixtures.py` — may overlap with `scan_events.py`
  - `migrate_data.py` — one-time migration, likely done
  - `parse_betclic_bets.py` — may overlap with `fetch_betclic_bets.py`
  - `enrich_tennis_stats.py` — sport-specific enrichment, may be superseded by generic `data_enrichment_agent.py`
  - `query_team.py` — debug/utility tool
  - `source_health.py` / `scan_health_report.py` — may overlap
  - `pipeline_summary.py` — may be tied to banned orchestrator
  - `data_rotation.py` — assess if still needed
  - `aggregate_and_select.py` — may overlap with `build_shortlist.py`
  - `build_stats_cache.py` — may be superseded by DB caching
- **Strategy:**
  - Do NOT delete immediately — move to `scripts/_archived/` directory
  - Add `# ARCHIVED — not used in 5-sport pipeline` header to each
  - Update any imports or references in active scripts
  - `pipeline_orchestrator.py` is the only candidate for full removal (it's actively harmful)
- **Definition of Done:**
  - Stale scripts moved to `scripts/_archived/`
  - No active script imports from archived scripts
  - `scripts/` directory contains ONLY scripts used in the daily pipeline + utilities
  - `pipeline_orchestrator.py` removed or archived with prominent warning

---

## Phase 3: Source Registry Overhaul

### Task 3.1 — Rewrite source-registry.md for 5 sports

- **Type:** [MODIFY]
- **File:** `betting/sources/source-registry.md`
- **Dependencies:** Phase 1
- **Changes:**

  **A) Remove source sections for removed sports:**
  - Remove all Tier C specialist sources that serve ONLY removed sports:
    - CueTracker (snooker)
    - DartsOrakel (darts)
    - SpeedwayEkstraliga, SpeedwayResults, ZuzelEnd (speedway)
    - Sherdog (MMA)
    - PremierPadel.com (padel)
    - GosuGamers (esports)
    - HLTV (esports)
  - Remove API clients for removed sports:
    - API-Handball (custom client)
    - API-Baseball (custom client)
  - Remove source-specific notes for removed sports in Scores24.live coverage list.

  **B) Keep and enhance sources for the 5 sports:**
  - **Football:** Keep ALL existing sources (Flashscore, Sofascore, SoccerStats, TotalCorner, WhoScored, Soccerway, Covers, API-Football, Football-Data.org, Understat, ESPN). Add notes about expanded lower-division coverage.
  - **Tennis:** Keep TennisExplorer, TennisAbstract, ATP Tour, API-Tennis. Add note about Challenger/ITF coverage.
  - **Basketball:** Keep Basketball-Reference, TeamRankings, API-Basketball, BallDontLie, nba_api. Add notes about European lower division sources (Eurobasket.com, Proballers.com).
  - **Volleyball:** Keep existing sources. Add notes about VolleyballWorld.com, CEV official site.
  - **Hockey:** Keep Hockey-Reference, API-Hockey. Add notes about EliteProspects.com, HockeyDB.com.

  **C) Update Tier A core sources coverage descriptions:**
  - OddsPortal: remove handball, baseball, snooker, darts, esports, mma, padel from coverage.
  - BetExplorer: remove same.
  - Scores24.live: update sport list to 5.
  - The-Odds-API: update "NOT covered" section (remove volleyball from not-covered — it IS covered by some bookmakers).
  - Odds-API.io: update sport count from "34 sports" to note which of the 5 are covered.
  - ESPN API: remove MMA from client registry; keep football, basketball, hockey, tennis.

  **D) Update "Source Philosophy" section:**
  - Change "Every sport has dedicated communities" focus to "Each of the 5 core sports has deep, layered source coverage."
  - Emphasize DEPTH over breadth: "With 5 sports, every league can be covered by multiple independent sources."

  **E) Add new sources for expanded coverage:**
  - **Football lower divisions:**
    - Soccerway.com — already present, add note about lower division coverage
    - Betaminic.com — statistical analysis tool, good for minor leagues
  - **Tennis expanded:**
    - LiveTennis.it — ITF/Challenger coverage
    - MatchStat.com — comprehensive match statistics
  - **Basketball expanded:**
    - Eurobasket.com — European lower divisions
    - Proballers.com — player stats across leagues
    - RealGM.com — roster transactions, stats
  - **Volleyball expanded:**
    - VolleyballWorld.com — FIVB official data
    - CEV.eu — European volleyball official
    - DataVolley — analytics platform reference
  - **Hockey expanded:**
    - EliteProspects.com — comprehensive hockey database
    - HockeyDB.com — historical stats
    - Eurohockey.com — European hockey coverage

- **Definition of Done:**
  - [x] No source entries reference removed sports as their primary purpose.
  - [x] Each of the 5 sports has ≥4 dedicated sources listed.
  - [x] New sources for lower-division coverage are documented with access notes.
  - [x] Coverage descriptions for Tier A sources are updated.

---

## Phase 4: DATA DEPTH REVOLUTION

**This is the #1 priority. The core problem with the pipeline is shallow data — not sport count. Every analyzed match MUST have: H2H for specific stats, last 5-10 match form with details, injury/suspension data, coach/roster stability, league context (standings, zone), and tipster/expert sentiment.**

### Task 4.1 — Overhaul data_enrichment_agent.py for deep extraction

- **Type:** [MODIFY]
- **File:** `scripts/data_enrichment_agent.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) Remove removed-sport references:**
  - Remove `_INDIVIDUAL_SPORTS` entries: snooker, darts, mma, table_tennis, padel, speedway
  - Remove `_FS_SPORT_SLUGS` entries: mma, table_tennis, esports
  - Remove `_SS_SPORT_SLUGS` entries: table_tennis, mma, esports
  - Remove `_build_scores24_url` mappings for removed sports
  - Remove `_primary_score_key` entries for removed sports

  **B) CRITICAL: Enhance HTML parsing for DEEP data — not just regex scores:**
  - Current `_parse_flashscore_stats()` uses fragile regex patterns that only extract basic scores
  - Replace with structured extraction:
    1. **Match results with details** — extract actual match scores (not just totals), opponents, dates, competition
    2. **H2H section** — Flashscore has a dedicated H2H tab. Extract all H2H meetings with scores, per-stat breakdowns
    3. **Form section** — extract last 10 matches with opponent name, result (W/L/D), scores, and venue (H/A)
    4. **Injuries/suspensions** — extract from match detail pages where available
  - Add new function: `_parse_flashscore_deep(html, sport)` → returns:
    ```python
    {
      "recent_form": [{"date": "...", "opponent": "...", "result": "W/L/D", "score": "2-1", "competition": "...", "venue": "H/A"}],
      "h2h_meetings": [{"date": "...", "score": "...", "competition": "...", "stats": {"corners": 8, "fouls": 22}}],
      "injuries": [{"player": "...", "status": "OUT/DOUBTFUL", "since": "..."}],
      "stats_per_match": {"corners": [7,8,5,9,6,8,7,10,5,6], "fouls": [...], ...}
    }
    ```

  **C) Add Sofascore deep extraction:**
  - Sofascore API endpoints (public, no key needed) provide rich data:
    - `/api/v1/team/{id}/events/last/0` — last 10 matches with full stats
    - `/api/v1/event/{id}/statistics` — per-match corner, fouls, shots, etc.
    - `/api/v1/event/{id}/lineups` — starting XI with injury markers
    - `/api/v1/event/{id}/h2h` — head-to-head with stats
  - Add function: `_fetch_sofascore_deep(team_name, sport)` → uses Sofascore search API to find team ID, then fetches deep data

  **D) Add ESPN deep extraction for the 5 sports:**
  - ESPN API is FREE with no rate limit. For football, it covers 36+ leagues.
  - Extend to fetch: per-match corner/fouls/shots stats (already in API but not fully used), team form, injuries
  - Add function: `_fetch_espn_deep(team_name, sport)` → fetches game logs with per-match stat breakdowns

  **E) Add enrichment completeness validation:**
  - After enrichment, validate that the team has:
    - [ ] L10 matches with actual results (not just averages)
    - [ ] At least 2 stat keys with per-match values
    - [ ] H2H data for opponent (if opponent known)
    - [ ] Competition/league context
  - If any critical data is missing → log warning and try next fallback source

- **Definition of Done:**
  - `enrich_team()` returns rich structured data, not just averaged numbers
  - H2H extraction returns per-stat breakdowns (corners in H2H meetings, not just scores)
  - At least 2 independent sources tried per team (Flashscore → Sofascore → ESPN)
  - Enrichment completeness score logged per team

### Task 4.2 — Enhance fetch_api_stats.py for deep API data

- **Type:** [MODIFY]
- **File:** `scripts/fetch_api_stats.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) Remove removed sports from FALLBACK_CHAINS:**
  - Remove keys: handball, baseball, mma, snooker, darts, table_tennis, esports, padel, speedway
  - Keep: football, basketball, hockey, tennis, volleyball

  **B) Update TIER_1_SPORTS:**
  - Change from `{"football", "volleyball", "basketball", "tennis"}` → `{"football", "volleyball", "basketball", "tennis", "hockey"}`

  **C) CRITICAL: Maximize data extraction from existing APIs:**
  - API-Football already returns: corners, shots, SOT, fouls, cards, possession, passes, saves, offsides per match
  - **Problem:** Current code may only extract subset. Audit and ensure ALL stats are captured and saved:
    - `corners` → saved to team_form
    - `fouls` → saved to team_form
    - `yellow_cards` + `red_cards` → saved separately
    - `shots` + `shots_on_target` → saved
    - `possession` → saved
  - For basketball (API-Basketball): ensure points, rebounds, assists, steals, blocks, turnovers ALL saved
  - For hockey (API-Hockey): ensure goals, shots, PP, PIM, hits, blocks, faceoffs ALL saved
  - For tennis: ensure aces, double_faults, first_serve_pct, break_points_won ALL saved
  - For volleyball: ensure points, aces, blocks, attack_kill_pct ALL saved

  **D) Add per-match storage — not just averages:**
  - Current: may only compute L10 average and discard per-match values
  - Required: save full per-match stat arrays to `team_form.l10_values` JSON field
  - This enables the three-way cross-check (L10+H2H+L5) with real data instead of precomputed averages

- **Definition of Done:**
  - FALLBACK_CHAINS has exactly 5 sport keys
  - All 5 sports capture ALL available stat fields from their APIs
  - Per-match values saved (not just averages)
  - L10/L5/H2H values are real arrays, not single numbers

### Task 4.3 — Review & enhance html_deep_parser.py for 5 sports

- **Type:** [MODIFY]
- **File:** `scripts/html_deep_parser.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) Audit existing profiles for the 5 sports:**
  - flashscore.com — used for ALL 5 sports. Check CSS selectors still work
  - totalcorner.com — football corners/cards. Verify extraction
  - soccerstats.com — football stats. Verify extraction
  - betexplorer.com — odds/results. Verify
  - tennisexplorer.com — tennis. Verify
  - basketball-reference.com — basketball. Verify
  - hockey-reference.com — hockey. Verify

  **B) Remove profiles for removed sports:**
  - hltv.org — esports only. Remove
  - Any combat/darts/snooker-specific profiles

  **C) Add deep extraction rules per profile:**
  - For each domain profile, add extraction rules for:
    - Recent form (last 5-10 matches with scores)
    - H2H data (if available on the page)
    - Standings/league position
    - Injuries (if shown on the page)

- **Definition of Done:**
  - Profiles exist and work for all 5 sports
  - No profiles for removed sports
  - Deep extraction rules documented per domain

### Task 4.4 — Add injury/suspension data fetching

- **Type:** [MODIFY]
- **File:** `scripts/data_enrichment_agent.py` + `scripts/context_checks.py`
- **Dependencies:** Task 4.1
- **Changes:**

  - Add function `fetch_injuries(team_name, sport)`:
    - Source 1: ESPN injury reports (free API: `site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{id}/injuries`)
    - Source 2: Flashscore match page → "Injuries" section
    - Source 3: Sofascore team page → player status markers
  - Save injuries to DB: `athletes` table with `status = 'OUT'/'DOUBTFUL'`
  - In context_checks.py: check if key players are injured before gate
  - **CRITICAL for gate_checker.py gate point #4 ("Injuries/suspensions checked")**

- **Definition of Done:**
  - Injury data fetched for at least 70% of analyzed teams
  - Injury count shown in analysis report per candidate
  - Gate point #4 actually validates real injury data (not just "checked manually")

### Task 4.5 — Add coach/manager stability checking

- **Type:** [MODIFY]
- **File:** `scripts/context_checks.py`
- **Dependencies:** Task 4.1
- **Changes:**

  - Add function `check_coach_stability(team_name, sport)`:
    - Source: Flashscore team page → "Coach" section (shows current and previous coaches)
    - Source: Sofascore team page → manager info
    - Source: ESPN team page → coaching staff
  - If new coach (appointed within last 30 days) → add context flag: "NEW_COACH"
  - New coach = tactical instability → statistical markets become MORE valuable (style not established)
  - Save to `context_flags` in analysis_results

- **Definition of Done:**
  - Coach stability check runs for football and basketball
  - "NEW_COACH" flag appears when coach changed within 30 days
  - Flag shown in analysis report

### Task 4.6 — Add league context to analysis

- **Type:** [MODIFY]
- **File:** `scripts/deep_stats_report.py` + `scripts/context_checks.py`
- **Dependencies:** Phases 1-3
- **Changes:**

  - For each analyzed candidate, fetch:
    - Current standings position (from DB `standings` table or API)
    - Zone status: RELEGATION / PROMOTION / MIDTABLE / CHAMPIONSHIP
    - Points gap to next zone boundary
    - Home/away form split
  - Add section to deep_stats_report: "§S3.LEAGUE_CONTEXT"
  - Zone status affects motivation assessment:
    - RELEGATION zone → desperate, fight mode → fouls/cards likely UP
    - CHAMPIONSHIP chase → high motivation → corners/shots likely UP
    - MIDTABLE safe → dead rubber risk → statistical markets less predictable
    - PROMOTION playoff → like cup games, high intensity

- **Definition of Done:**
  - League context section appears in deep stats report
  - Zone status computed for team sports (football, basketball, volleyball, hockey)
  - Motivation flags derived from zone status

### Task 4.7 — Ensure H2H is per-STAT not just match results

- **Type:** [MODIFY]
- **File:** `scripts/normalize_stats.py` + `scripts/compute_safety_scores.py`
- **Dependencies:** Task 4.1
- **Changes:**

  **A) normalize_stats.py:**
  - Current `build_safety_input()` may only use H2H match results (scores)
  - Ensure H2H data includes per-stat values: "In last 5 H2H meetings, average corners was 9.2"
  - If per-stat H2H not available, apply the 0.7 H2H-blind penalty (already exists but verify it actually triggers)

  **B) compute_safety_scores.py:**
  - Verify three-way cross-check uses REAL per-stat H2H data
  - If H2H for specific stat is missing, the safety score must reflect this with the penalty
  - Add `h2h_stat_available: bool` field to ranking output

- **Definition of Done:**
  - H2H section in safety input contains per-stat arrays (not just match scores)
  - h2h_blind penalty correctly applied when per-stat H2H is unavailable
  - Three-way check (L10+H2H+L5) uses stat-specific data at every level

### Task 4.8 — Enhance tipster/expert opinion integration

- **Type:** [MODIFY]
- **File:** `scripts/tipster_aggregator.py` + `scripts/tipster_xref.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) tipster_aggregator.py:**
  - Remove tipster sources that only serve removed sports
  - Focus on tipster sites covering the 5 sports: Forebet, BettingClosed, Feedinco, BetIdeas, PicksWise, Sportsgambler
  - Ensure tipster ARGUMENTS are extracted (not just pick direction)
  - Extract: tipster reasoning, form assessment, injury mentions, lineup predictions

  **B) tipster_xref.py:**
  - Cross-reference tipster picks with our statistical analysis
  - Flag CONSENSUS: ≥2 tipsters agree with our pick direction → strength boost
  - Flag CONTRADICTION: tipsters disagree with stats → needs bear case review

  **C) Add expert sentiment to analysis report:**
  - Section "§S3.EXPERT_SENTIMENT" in deep_stats_report
  - Shows: tipster consensus direction, key arguments, confidence level

- **Definition of Done:**
  - Tipster data fetched for ≥50% of analyzed candidates
  - Tipster arguments (not just picks) included in report
  - Consensus/contradiction flags generated

### Task 4.9 — Web research agent for missing data

- **Type:** [CREATE]
- **File:** `scripts/web_research_agent.py`
- **Dependencies:** Tasks 4.1-4.8
- **Rationale:** When H2H data, injury info, team form, or any critical data is MISSING after all API/scraping fallback chains are exhausted, a dedicated web research agent must search the open web to find it. This is the LAST RESORT enrichment layer.
- **Changes:**

  **A) Create `web_research_agent.py`:**
  - Input: team names, sport, specific data need (e.g. "H2H last 5 meetings", "injuries for Arsenal", "coach history for Fenerbahce")
  - Uses SerpAPI (100 req/month — use sparingly, only for gaps) or Playwright web search
  - Search strategy per data type:
    - H2H: search `"{team1} vs {team2} head to head statistics"` → parse top results
    - Injuries: search `"{team} injuries suspensions {date}"` → parse sports news sites
    - Form: search `"{team} recent results {league}"` → parse table data
    - Coach: search `"{team} coach manager {year}"` → parse news
  - Returns structured data with source URL and confidence level
  - Caches results in DB to avoid re-searching same queries

  **B) Integration points:**
  - `data_enrichment_agent.py` → after L1-L6 fallback chains fail → spawn web_research_agent
  - `deep_stats_report.py` → when building candidate profile, if H2H is missing → call web_research_agent
  - Agent protocol: add `web_research_agent` to SELF_HEALING_REGISTRY as L7 (last resort)

  **C) Rate limiting:**
  - SerpAPI: max 5 searches per pipeline run (100/month budget)
  - Playwright web search: max 10 searches per pipeline run
  - Priority: search for data that would upgrade candidate from MINIMAL to PARTIAL quality

- **Definition of Done:**
  - `web_research_agent.py` exists and can find H2H, injury, form, coach data via web search
  - Integrated as L7 fallback in enrichment pipeline
  - Rate-limited to protect API budgets
  - Results cached in DB
  - Agent can be spawned by orchestrator: "Missing H2H for Team A vs Team B — spawning web research agent"

---

## Phase 5: ANALYSIS PIPELINE REWRITE

**The analysis pipeline must produce DEEP, well-reasoned analysis per candidate — not shallow number-crunching. Every candidate must have a comprehensive data profile before entering the gate.**

### Task 5.1 — Rewrite deep_stats_report.py for real deep analysis

- **Type:** [MODIFY]
- **File:** `scripts/deep_stats_report.py`
- **Dependencies:** Phase 4
- **Changes:**

  **A) Eliminate shortlist-fallback analysis:**
  - Current: if `build_safety_input()` returns None, falls back to `_ranking_from_shortlist_markets()` which uses precomputed shallow data
  - New behavior: if safety input is None → trigger enrichment sub-agent → retry → only then fall back
  - The shortlist-precomputed safety data should be the LAST resort, not the default

  **B) Enhance the 10-section report (§S3.1-§S3.10) with NEW sections:**
  - §S3.1: Match Identity — full team names, league, round, venue ✓ (exists)
  - §S3.2: Market Ranking Table — all stat markets ranked by safety ✓ (exists)
  - §S3.3: Three-Way Cross-Check — L10+H2H+L5 alignment ✓ (exists)
  - §S3.4: H2H Deep Dive — **ENHANCED**: per-stat H2H, not just match results. Show actual corners/fouls/etc. in past meetings
  - §S3.5: Recent Form — **ENHANCED**: show actual last 5-10 matches with opponents, scores, and stat breakdowns
  - §S3.6: League Context — **NEW**: standings position, zone, motivation assessment
  - §S3.7: Injuries & Roster — **NEW**: key absences, recent returns, coach stability
  - §S3.8: Expert Sentiment — **NEW**: tipster consensus, key arguments
  - §S3.9: Risk Assessment — upset risk score, bear case, red flags ✓ (exists)
  - §S3.10: Recommendation — market, direction, confidence, minimum odds ✓ (exists)

  **C) Remove removed-sport references:**
  - Remove `_primary_score_key` entries for removed sports
  - Remove any sport-specific analysis branches for removed sports
  - Update `extract_team_stats()` to remove ESPN/niche fallbacks for removed sports

  **D) Add data completeness indicator per candidate:**
  - Show: DATA_QUALITY = FULL / PARTIAL / MINIMAL
  - FULL: L10+H2H+L5+injuries+context = all present
  - PARTIAL: L10+L5 present, H2H or context missing
  - MINIMAL: only L10 averages, no H2H, no context
  - MINIMAL candidates get flagged prominently — user should treat with extra caution

- **Definition of Done:**
  - Reports contain 10 sections with real data (not placeholders)
  - H2H section shows actual per-stat data from past meetings
  - Form section shows actual match list with opponents and scores
  - Data quality indicator computed and shown per candidate
  - No shortlist-fallback used unless enrichment genuinely fails after retries

### Task 5.2 — Remove sport diversity gate, add data quality gate

- **Type:** [MODIFY]
- **File:** `scripts/gate_checker.py`
- **Dependencies:** Phase 4
- **Changes:**

  **A) Remove sport diversity gate entirely:**
  - Remove `KEY_SPORTS` set definition (was: football, volleyball, basketball, tennis)
  - Update `ALL_SPORTS` to 5 sports only
  - Change `check_sport_diversity()`: remove `len(approved_sports) >= 5` check entirely
  - Make diversity INFORMATIONAL only — show sport distribution but never block picks
  - **User's words: "Do not have such thing like minimum 4 sports — it's nonsense because it might be that there are no volleyball nor tennis matches but worthy lower leagues from Asia, USA, South America"**

  **B) Add DATA QUALITY gate (new):**
  - New function: `check_data_quality(candidate)` → returns PASS/WARN/FAIL
  - PASS: has L10+H2H+L5 data, safety_score > 0.4, ≥3 markets evaluated
  - WARN: missing H2H OR L5, safety_score 0.3-0.4, ≥2 markets evaluated
  - FAIL: only precomputed shortlist data, safety_score < 0.3, <2 markets
  - FAIL candidates go to Extended Pool, not core coupons
  - WARN candidates get prominent warning label in coupon

  **C) Remove sport diversity from §7.6 enforcement:**
  - The `passes_diversity` field should always be `True` (or remove the check)
  - No more "EXPANSION NEEDED" based on sport count

- **Definition of Done:**
  - `check_sport_diversity()` is informational only — never blocks picks
  - New `check_data_quality()` function validates data depth per candidate
  - Gate report shows data quality distribution instead of sport diversity
  - Pipeline never rejects picks for "not enough sports"

### Task 5.3 — Enhance coupon_builder.py

- **Type:** [MODIFY]
- **File:** `scripts/coupon_builder.py`
- **Dependencies:** Task 5.2
- **Changes:**

  **A) Remove removed sports:**
  - Remove SPORT_EMOJI entries for 9 removed sports
  - Keep: football, basketball, tennis, volleyball, hockey

  **B) CRITICAL: No event duplication across coupons:**
  - Current: same event may appear in multiple core coupons
  - New rule: each event appears in AT MOST 1 core coupon
  - Combos can remix events from different coupons but still: each combo is unique combination
  - Add deduplication check: track used events, skip duplicates

  **C) Quality-first coupon construction:**
  - Sort candidates by data quality (FULL > PARTIAL > MINIMAL) then by safety score
  - FULL data quality candidates get priority placement in core coupons
  - MINIMAL data quality candidates go to Extended Pool only
  - Show data quality label per pick in coupon output

- **Definition of Done:**
  - No event appears in more than 1 core coupon
  - Data quality label shown per pick
  - Only FULL/PARTIAL data quality picks in core coupons
  - MINIMAL goes to Extended Pool

### Task 5.4 — Add mandatory data quality thresholds

- **Type:** [MODIFY]
- **File:** `scripts/compute_safety_scores.py`
- **Dependencies:** Task 4.7
- **Changes:**

  - Add `data_quality_score` computation per candidate:
    - +2 for L10 data present with ≥8 data points
    - +2 for H2H data present with ≥3 meetings
    - +1 for L5 trend available
    - +1 for injury data checked
    - +1 for league context available
    - +1 for tipster data available
    - +1 for odds cross-validated from ≥2 sources
    - +1 for three-way cross-check alignment
    - Score: 0-10. FULL ≥7, PARTIAL 4-6, MINIMAL <4
  - This score is independent of safety score — it measures DATA AVAILABILITY not pick quality

- **Definition of Done:**
  - `data_quality_score` computed and attached to every candidate
  - Score breakdown visible in analysis report
  - Score feeds into coupon builder quality sorting

---

## Phase 6: AGENT METHODOLOGY OVERHAUL

**Every agent must use sequential thinking, react to errors in real-time, and provide reasoned analysis — not just run scripts and report numbers.**

### Task 6.1 — Update agent_protocol.py with enhanced agent behaviors

- **Type:** [MODIFY]
- **File:** `scripts/agent_protocol.py`
- **Dependencies:** Phase 2
- **Changes:**

  **A) Add MANDATORY_BEHAVIORS to each agent in AGENT_SKILLS_MAP:**
  ```python
  "mandatory_behaviors": {
      "sequential_thinking": "Use sequentialthinking MCP for EVERY decision. THINK IN THE MIDDLE — when a script produces output, use sequential thinking to analyze results AS THEY ARRIVE. Scripts run 5-10 minutes; the thinking happens DURING analysis of output, not in wasted time before/after.",
      "live_error_handling": "If a script fails or produces unexpected output, diagnose the error immediately. Do NOT just report the error — fix it or try alternative approach.",
      "data_validation": "After every data fetch, validate: Is the data reasonable? Are stat values in expected ranges? Are there suspiciously many zeros or nulls?",
      "think_in_the_middle": "When script output arrives: (1) Use sequentialthinking to deeply analyze the data, (2) Assess data quality, (3) Identify anomalies and gaps, (4) Decide next action with justification. Do NOT reason about expectations before a 5-10min script — reason about ACTUAL output when it arrives.",
  }
  ```

  **B) Update STEP_AGENT_CONFIG with enhanced instructions:**
  - Every step must include: "Use sequentialthinking to analyze script output when it arrives (THINK IN THE MIDDLE)"
  - Every step must include: "If script fails → diagnose → fix → retry (do not just report)"
  - Every step must include: "Validate output data quality before proceeding"

  **C) Update all references from "14 sports" to "5 sports"** (from original plan Phase 2)

  **D) Remove sport diversity requirements:**
  - Change s1e_shortlist task from "sport diversity (≥8 sports)" to "league diversity and data depth"
  - Remove "≥5 sports" requirement from s7_gate
  - Add data quality validation to s7_gate

- **Definition of Done:**
  - Every agent role has `mandatory_behaviors` defined
  - Every step has sequential thinking requirement
  - Every step has error handling protocol
  - No sport diversity minimums anywhere

### Task 6.2 — Add live error handling protocol

- **Type:** [MODIFY]
- **File:** `scripts/agent_protocol.py`
- **Dependencies:** Task 6.1
- **Changes:**

  Add new section `ERROR_HANDLING_PROTOCOL`:
  ```python
  ERROR_HANDLING_PROTOCOL = {
      "script_failure": {
          "action": "Read error message → identify root cause → fix if possible → retry",
          "common_fixes": {
              "ConnectionError": "Rate limited or blocked. Wait 30s, try alternative source.",
              "JSONDecodeError": "Corrupt cache or empty response. Delete cache, retry.",
              "KeyError": "API response schema changed. Log and try fallback source.",
              "TimeoutError": "Source too slow. Try next fallback in chain.",
              "FileNotFoundError": "Cache/data file missing. Run enrichment first.",
          },
      },
      "empty_data": {
          "action": "Source returned empty data. Trigger enrichment for missing teams. Try alternative sources.",
          "threshold": "If >50% candidates have MINIMAL data quality → enrichment failed → escalate to user.",
      },
      "quality_regression": {
          "action": "If data quality is WORSE than previous run → compare with DB history → identify what changed.",
      },
  }
  ```

- **Definition of Done:**
  - Error handling protocol defined with specific actions per error type
  - Agents can reference this protocol during pipeline execution
  - Common fixes documented for rapid diagnosis

### Task 6.3 — Review and update 5 remaining sport scanning skills

- **Type:** [MODIFY]
- **Files:**
  - `.github/skills/bet-scanning-football/SKILL.md`
  - `.github/skills/bet-scanning-basketball/SKILL.md`
  - `.github/skills/bet-scanning-volleyball/SKILL.md`
  - `.github/skills/bet-scanning-tennis/SKILL.md`
  - `.github/skills/bet-scanning-hockey/SKILL.md`
- **Dependencies:** Phase 3
- **Changes per skill:**

  - Add "DEEP DATA REQUIREMENTS" section:
    ```
    For every scanned fixture, the scanner MUST attempt to collect:
    1. H2H history (last 5 meetings minimum) with per-stat breakdowns
    2. Recent form (last 10 matches) with opponents, results, scores
    3. League standings position and zone status
    4. Key injuries/suspensions
    5. Per-match statistical data (not just averages)
    ```
  - Add "DATA QUALITY VALIDATION" section:
    ```
    After scan completes, validate per fixture:
    - Has ≥2 independent source confirmations?
    - Has team form data for BOTH teams?
    - Has at least 1 statistical data source (API or deep parse)?
    ```
  - Update source URLs to include new expanded leagues from Phase 8
  - Add sequential thinking requirement: "THINK IN THE MIDDLE: when scan output arrives, use sequentialthinking to evaluate data quality, identify gaps, and decide enrichment actions"

- **Definition of Done:**
  - Each of the 5 scanning skills has deep data requirements
  - Data quality validation checklist included
  - THINK IN THE MIDDLE mandated (analyze actual output, not pre-script speculation)

### Task 6.4 — Review and update analyzing-statistics skill

- **Type:** [MODIFY]
- **File:** `.github/skills/bet-analyzing-statistics/SKILL.md`
- **Dependencies:** Phase 5
- **Changes:**

  - Add "DATA DEPTH REQUIREMENTS" section:
    ```
    Before computing safety scores, verify data completeness:
    - L10: ≥8 actual match data points (not interpolated)
    - H2H: ≥3 meetings with per-stat data
    - L5: ≥4 actual match data points
    - If any dimension has <minimum → flag as PARTIAL quality
    ```
  - Update bettable markets table to remove 9 removed sports
  - Add "REASONING BEFORE RANKING" section:
    ```
    Before computing safety scores, use sequential thinking to assess:
    1. Is the data source reliable? (API > deep parse > regex)
    2. Are the stat values in expected ranges for this sport/league?
    3. Do recent matches suggest a trend change that averages might hide?
    4. Is H2H relevant? (same teams, similar context, or very different?)
    ```
  - Enhance three-way cross-check to require REASONING not just numerical pass/fail

- **Definition of Done:**
  - Data depth requirements clearly stated
  - Removed-sport markets removed
  - Reasoning requirements added before mechanical calculations

### Task 6.5 — Review and update building-coupons skill

- **Type:** [MODIFY]
- **File:** `.github/skills/bet-building-coupons/SKILL.md`
- **Dependencies:** Task 5.3
- **Changes:**

  - Add "NO EVENT DUPLICATION" rule (prominent, bolded)
  - Add "DATA QUALITY PRIORITY" rule:
    ```
    Core coupons: ONLY FULL or PARTIAL data quality picks
    Extended pool: MINIMAL data quality picks (user decides)
    ```
  - Remove sport diversity requirement from coupon construction
  - Add "LEARN FROM FAILURES" section:
    ```
    Before building coupons, check betclic_bets_history.json:
    - Which market types have worst hit rates? → deprioritize in coupons
    - Which sport×market combos consistently fail? → flag prominently
    - Which coupon structures (2-leg vs 3-leg vs 4-leg) win most? → optimize structure
    ```
  - Update validation suite to include data quality checks

- **Definition of Done:**
  - No event duplication rule enforced
  - Data quality labels in coupon output
  - Historical learning integrated into coupon construction

---

## Phase 7: Instructions & Methodology

### Task 7.1 — Update copilot-instructions.md

- **Type:** [MODIFY]
- **File:** `.github/copilot-instructions.md`
- **Dependencies:** Phases 1-6
- **Changes:**

  **A) Core Rules section:**
  - Change `"KEY sports (Tier 1): Football, Volleyball, Basketball, Tennis"` → `"CORE sports: Football, Volleyball, Basketball, Tennis, Hockey — ALL are Tier 1. Scan ALL leagues/divisions deeply."`
  - Change `"SUPPORT sports (Tier 2): All others..."` → Remove entirely. There is no Tier 2.
  - Update `fetch_odds_api.py` settlement command: remove `baseball,hockey` → just `hockey` (or remove sport filter).

  **B) Non-negotiable rules:**
  - **R4:** COMPLETELY REWRITE. Remove sport diversity minimum entirely. New R4: `"NO AGGRESSIVE NARROWING: Pipeline must scan ALL leagues from ALL 5 sports comprehensively. However, sport diversity is NEVER a gate — if a given day has only football and basketball worth betting, that's fine. Quality over forced diversity. Data quality gate replaces sport diversity gate."` Remove `"§7.6 blocks S8 if <5 sports"` line entirely.
  - **R5:** Keep as-is (stats over outcomes applies to all 5 sports).
  - **R7:** Keep as-is (tournament protection still applies to all 5 sports).
  - **R8:** Keep as-is (minor league value is even MORE important with 5-sport depth strategy).
  - **R11:** ENHANCE: `"SEQUENTIAL THINKING MANDATORY: Use sequentialthinking MCP tool for EVERY pipeline step (S0-S10). For per-candidate steps (S3, S4, S5, S6, S7): one sequentialthinking call PER CANDIDATE. THINK IN THE MIDDLE: when script output arrives (scripts run 5-10 min), use sequentialthinking to deeply analyze actual results — identify anomalies, assess data quality, decide next action. Do NOT waste time reasoning about expectations before a long-running script. This is the core quality driver."`
  - **R13:** Update to remove baseball references: `"...and equivalents for basketball (CBA, NBB), hockey (KHL), volleyball (Superliga, V-League), tennis (all Grand Slams, Masters 1000)"`.
  - **ADD R14 — DATA DEPTH MANDATORY:** `"Every candidate entering the gate MUST have a data_quality_score computed. FULL (≥7/10), PARTIAL (4-6/10), MINIMAL (<4/10). Core coupons accept only FULL/PARTIAL. MINIMAL goes to Extended Pool. Pipeline must maximize data depth through API+scraping+enrichment fallback chains."`
  - **ADD R15 — WEB RESEARCH AGENT:** `"When critical data is MISSING after all API/scraping fallback chains (L1-L6), spawn web_research_agent.py to search the open web. This is L7 — last resort. Use for: H2H data, injury reports, coach changes, team form. Rate-limited: max 5 SerpAPI + 10 Playwright searches per run. Agent MUST be spawned automatically — never leave gaps unfilled without trying."`
  - **ADD R16 — LIVE BETTING WINDOW:** `"Betting day runs 06:00 today → 05:59 tomorrow (Europe/Warsaw). Events already in progress are VALID targets — Betclic allows live betting. When ≤1h remains before kickoff or match is running, flag as LIVE and include in scan. Never exclude an event just because it's about to start or has started."`

  **C) Scripted Workflow section:**
  - Settlement command: remove `--scores baseball,hockey` example → `--scores hockey`

- **Definition of Done:**
  - No references to 14 sports, Tier 2, or any removed sport in the file.
  - R4 rewritten: sport diversity is informational, never a gate.
  - R14 added: data quality is the new gate.
  - R15 added: web research agent as L7 fallback.
  - R16 added: live betting window 06:00-05:59, in-play events included.
  - R11 enhanced with THINK IN THE MIDDLE (reason about actual output, not pre-script expectations).
  - R13 updated to reflect 5-sport model.

### Task 7.2 — Update analysis-methodology.instructions.md

- **Type:** [MODIFY]
- **File:** `.github/instructions/analysis-methodology.instructions.md`
- **Dependencies:** Phase 1
- **Changes:**

  **A) SPORT TIERS table:**
  - Replace with single tier:
    ```
    | Tier | Sports | Scanning | Analysis |
    |------|--------|----------|----------|
    | **CORE (All Tier 1)** | Football, Volleyball, Basketball, Tennis, Hockey | ALL leagues/divisions/tournaments — go DEEP. 2nd/3rd/4th divisions, cups, women's leagues, regional tournaments. Every sub-page. | Full STEPS 3-7 per candidate. |
    ```
  - Remove the Tier 2 row entirely.

  **B) KEY sport league depth section:**
  - Add Hockey to the depth examples:
    ```
    - Hockey: not just NHL/KHL but also SHL, Liiga, DEL, Swiss NL/SL, Czech Extraliga/1.Liga, Slovak Tipsport Liga, AHL, ECHL, EIHL, Ligue Magnus, HockeyAllsvenskan, Mestis.
    ```

  **C) DB function references:**
  - Remove `load_espn_enrichment_for_team` reference to "basketball/hockey/baseball" → "basketball/hockey"
  - Remove `load_sport_specific_cache` reference to darts, Dota2, table tennis.
  - Remove stats_cache mentions for esports/dota2, darts, table_tennis.

  **D) Automated Pipeline Modules table:**
  - Update any references to "14 sports" in step descriptions.

- **Definition of Done:**
  - No Tier 2 / SUPPORT tier mentioned.
  - Hockey added as Tier 1 with league depth examples.
  - No references to removed sports in DB function descriptions.
  - No removed sport data cache paths referenced.

### Task 7.3 — Update sport-analysis-protocols.instructions.md

- **Type:** [MODIFY]
- **File:** `.github/instructions/sport-analysis-protocols.instructions.md`
- **Dependencies:** Phases 1-6
- **Changes:**
  - Remove protocol sections for removed sports. Currently contains per-sport sections (§3.1-§3.14). Remove:
    - §3.6 Handball (if exists)
    - §3.7 Baseball (if exists)
    - §3.8 Snooker (if exists)
    - §3.9 Darts (if exists)
    - §3.10 Table Tennis (if exists)
    - §3.11 Esports (if exists)
    - §3.12 MMA (if exists)
    - §3.13 Padel (if exists)
    - §3.14 Speedway (if exists)
  - Keep and optionally enhance:
    - §3.1 Football ✓
    - §3.2 Tennis ✓
    - §3.3 Basketball ✓
    - §3.4 Volleyball ✓
    - §3.5 Hockey ✓
  - Update the Sport Tiers note at top to say 5 sports, all Tier 1.
- **Definition of Done:**
  - File contains protocol sections for exactly 5 sports.
  - No references to removed sports.
  - Remaining sections are renumbered §3.1-§3.5 if needed.

### Task 7.4 — Update betting-artifacts.instructions.md

- **Type:** [MODIFY]
- **File:** `.github/instructions/betting-artifacts.instructions.md`
- **Dependencies:** Phases 1-6
- **Changes:**
  - Search for any sport-specific output format references to removed sports and remove them.
  - Update any "14 sports" or "per-sport" counts.
  - Keep coupon format, ledger format, pick format as-is (they're sport-agnostic).
- **Definition of Done:**
  - No references to removed sports in output format specifications.

---

## Phase 8: League Expansion

For each sport, specific leagues and URLs to ADD to `config/scan_urls.json`. MORE leagues = MORE data points = BETTER analysis.

### Task 8.1 — Football League Expansion

**Current:** ~180 URLs covering 40+ countries with 2-3 tiers each.
**Target:** ~250+ URLs — deeper tiers, more countries.

**New URLs to add (grouped by region):**

**A) England — deeper tiers:**
```
https://www.flashscore.com/football/england/national-league-north/
https://www.flashscore.com/football/england/national-league-south/
https://www.flashscore.com/football/england/fa-trophy/
https://www.flashscore.com/football/england/efl-trophy/
```

**B) Germany — deeper tiers:**
```
https://www.flashscore.com/football/germany/regionalliga-west/
https://www.flashscore.com/football/germany/regionalliga-nord/
https://www.flashscore.com/football/germany/regionalliga-bayern/
https://www.flashscore.com/football/germany/regionalliga-nordost/
https://www.flashscore.com/football/germany/regionalliga-suedwest/
```

**C) Italy — deeper tiers:**
```
https://www.flashscore.com/football/italy/serie-c-group-a/
https://www.flashscore.com/football/italy/serie-c-group-b/
https://www.flashscore.com/football/italy/serie-c-group-c/
```

**D) Spain — deeper tiers:**
```
https://www.flashscore.com/football/spain/primera-federacion-group-1/
https://www.flashscore.com/football/spain/primera-federacion-group-2/
https://www.flashscore.com/football/spain/copa-del-rey/
```

**E) France — deeper tiers:**
```
https://www.flashscore.com/football/france/national-2/
https://www.flashscore.com/football/france/coupe-de-france/
```

**F) Balkans & Southeast Europe (NEW countries):**
```
https://www.flashscore.com/football/albania/
https://www.flashscore.com/football/albania/superiore/
https://www.flashscore.com/football/bosnia-herzegovina/
https://www.flashscore.com/football/bosnia-herzegovina/premijer-liga/
https://www.flashscore.com/football/montenegro/
https://www.flashscore.com/football/montenegro/first-league/
https://www.flashscore.com/football/north-macedonia/
https://www.flashscore.com/football/north-macedonia/first-league/
https://www.flashscore.com/football/slovenia/
https://www.flashscore.com/football/slovenia/prva-liga/
https://www.flashscore.com/football/slovenia/2-snl/
https://www.flashscore.com/football/malta/
https://www.flashscore.com/football/malta/premier-league/
```

**G) Baltic states:**
```
https://www.flashscore.com/football/estonia/
https://www.flashscore.com/football/estonia/meistriliiga/
https://www.flashscore.com/football/latvia/
https://www.flashscore.com/football/latvia/virsliga/
https://www.flashscore.com/football/lithuania/
https://www.flashscore.com/football/lithuania/a-lyga/
```

**H) Eastern Europe:**
```
https://www.flashscore.com/football/belarus/
https://www.flashscore.com/football/belarus/premier-league/
https://www.flashscore.com/football/moldova/
https://www.flashscore.com/football/moldova/super-liga/
https://www.flashscore.com/football/armenia/
https://www.flashscore.com/football/armenia/premier-league/
https://www.flashscore.com/football/azerbaijan/
https://www.flashscore.com/football/azerbaijan/premier-league/
```

**I) Northern Europe — deeper tiers:**
```
https://www.flashscore.com/football/faroe-islands/
https://www.flashscore.com/football/faroe-islands/premier-league/
https://www.flashscore.com/football/iceland/2-deild/
https://www.flashscore.com/football/finland/kakkonen/
```

**J) Central Americas & Caribbean:**
```
https://www.flashscore.com/football/guatemala/
https://www.flashscore.com/football/guatemala/liga-nacional/
https://www.flashscore.com/football/el-salvador/
https://www.flashscore.com/football/el-salvador/primera-division/
https://www.flashscore.com/football/panama/
https://www.flashscore.com/football/panama/liga-panamericana/
https://www.flashscore.com/football/jamaica/
https://www.flashscore.com/football/jamaica/premier-league/
https://www.flashscore.com/football/honduras/liga-nacional/
```

**K) More Asia:**
```
https://www.flashscore.com/football/malaysia/
https://www.flashscore.com/football/malaysia/super-league/
https://www.flashscore.com/football/singapore/
https://www.flashscore.com/football/singapore/premier-league/
https://www.flashscore.com/football/philippines/
https://www.flashscore.com/football/philippines/copa-paulino-alcantara/
https://www.flashscore.com/football/bahrain/
https://www.flashscore.com/football/bahrain/premier-league/
https://www.flashscore.com/football/qatar/
https://www.flashscore.com/football/qatar/stars-league/
https://www.flashscore.com/football/kuwait/
https://www.flashscore.com/football/kuwait/premier-league/
https://www.flashscore.com/football/oman/
https://www.flashscore.com/football/oman/professional-league/
https://www.flashscore.com/football/iraq/
https://www.flashscore.com/football/iraq/premier-league/
```

**L) Africa — deeper:**
```
https://www.flashscore.com/football/south-africa/premier-soccer-league/
https://www.flashscore.com/football/tanzania/
https://www.flashscore.com/football/tanzania/premier-league/
https://www.flashscore.com/football/uganda/
https://www.flashscore.com/football/uganda/premier-league/
https://www.flashscore.com/football/zambia/
https://www.flashscore.com/football/zambia/super-league/
https://www.flashscore.com/football/zimbabwe/
https://www.flashscore.com/football/dr-congo/
https://www.flashscore.com/football/mozambique/
https://www.flashscore.com/football/rwanda/
https://www.flashscore.com/football/ethiopia/
https://www.flashscore.com/football/cote-d-ivoire/
```

**M) Continental tournaments:**
```
https://www.flashscore.com/football/africa/caf-champions-league/
https://www.flashscore.com/football/africa/caf-confederation-cup/
https://www.flashscore.com/football/asia/afc-champions-league/
https://www.flashscore.com/football/south-america/copa-libertadores/
https://www.flashscore.com/football/south-america/copa-sudamericana/
https://www.flashscore.com/football/north-central-america/concacaf-champions-cup/
https://www.flashscore.com/football/north-central-america/concacaf-nations-league/
```

**Total football URLs after expansion: ~250+**

### Task 8.2 — Tennis League Expansion

**Current:** ~30 URLs
**Target:** ~50+ URLs

**New URLs to add:**

**A) More Challenger events (explicit):**
```
https://www.flashscore.com/tennis/atp-singles/challenger-lyon/
https://www.flashscore.com/tennis/atp-singles/challenger-heilbronn/
https://www.flashscore.com/tennis/atp-singles/challenger-bordeaux/
https://www.flashscore.com/tennis/atp-singles/challenger-split/
https://www.flashscore.com/tennis/atp-singles/challenger-prague/
```

**B) More ATP & WTA tournaments:**
```
https://www.flashscore.com/tennis/atp-singles/indian-wells/
https://www.flashscore.com/tennis/atp-singles/miami/
https://www.flashscore.com/tennis/atp-singles/monte-carlo/
https://www.flashscore.com/tennis/atp-singles/madrid/
https://www.flashscore.com/tennis/atp-singles/cincinnati/
https://www.flashscore.com/tennis/atp-singles/shanghai/
https://www.flashscore.com/tennis/atp-singles/paris/
https://www.flashscore.com/tennis/wta-singles/indian-wells/
https://www.flashscore.com/tennis/wta-singles/miami/
https://www.flashscore.com/tennis/wta-singles/madrid/
https://www.flashscore.com/tennis/wta-singles/cincinnati/
https://www.flashscore.com/tennis/wta-singles/beijing/
https://www.flashscore.com/tennis/wta-singles/wuhan/
```

**C) Team events:**
```
https://www.flashscore.com/tennis/billie-jean-king-cup/
https://www.flashscore.com/tennis/laver-cup/
https://www.flashscore.com/tennis/atp-cup/
```

**D) Additional stat sources:**
```
https://www.tennisexplorer.com/ranking/atp-men/
https://www.tennisexplorer.com/ranking/wta-women/
https://matchstat.com/tennis/
```

**Total tennis URLs after expansion: ~50+**

### Task 8.3 — Basketball League Expansion

**Current:** ~40 URLs
**Target:** ~70+ URLs

**New URLs to add:**

**A) More European leagues:**
```
https://www.flashscore.com/basketball/hungary/nb-i/
https://www.flashscore.com/basketball/romania/superliga/
https://www.flashscore.com/basketball/bulgaria/nbl/
https://www.flashscore.com/basketball/slovenia/liga-nova-kbm/
https://www.flashscore.com/basketball/portugal/lbp/
https://www.flashscore.com/basketball/finland/korisliiga/
https://www.flashscore.com/basketball/sweden/basketligan/
https://www.flashscore.com/basketball/denmark/basketligaen/
https://www.flashscore.com/basketball/norway/blno/
https://www.flashscore.com/basketball/latvia/lbl/
https://www.flashscore.com/basketball/estonia/meistriliiga/
https://www.flashscore.com/basketball/slovakia/sbl/
https://www.flashscore.com/basketball/bosnia-herzegovina/premijer-liga/
https://www.flashscore.com/basketball/montenegro/premijer-liga/
https://www.flashscore.com/basketball/north-macedonia/super-liga/
https://www.flashscore.com/basketball/albania/super-liga/
https://www.flashscore.com/basketball/israel/super-league/
https://www.flashscore.com/basketball/cyprus/division-a/
```

**B) European 2nd divisions:**
```
https://www.flashscore.com/basketball/germany/pro-a/
https://www.flashscore.com/basketball/france/pro-b/
https://www.flashscore.com/basketball/italy/lega-2/
https://www.flashscore.com/basketball/spain/leb-oro/
https://www.flashscore.com/basketball/greece/a2/
https://www.flashscore.com/basketball/turkey/tbsl/
```

**C) European cross-border leagues:**
```
https://www.flashscore.com/basketball/europe/aba-league/
https://www.flashscore.com/basketball/europe/adriatic-league/
https://www.flashscore.com/basketball/europe/basketball-africa-league/
```

**D) Americas (beyond NBA):**
```
https://www.flashscore.com/basketball/mexico/lnbp/
https://www.flashscore.com/basketball/uruguay/lub/
https://www.flashscore.com/basketball/venezuela/superliga/
https://www.flashscore.com/basketball/chile/lnb/
https://www.flashscore.com/basketball/dominican-republic/lnb/
https://www.flashscore.com/basketball/puerto-rico/bsn/
```

**E) Asia-Pacific:**
```
https://www.flashscore.com/basketball/philippines/pba/
https://www.flashscore.com/basketball/indonesia/ibl/
https://www.flashscore.com/basketball/taiwan/sbl/
https://www.flashscore.com/basketball/new-zealand/nbl/
https://www.flashscore.com/basketball/india/nba-india/
```

**F) Additional sources:**
```
https://www.eurobasket.com/
https://www.proballers.com/
https://www.realgm.com/
```

**Total basketball URLs after expansion: ~70+**

### Task 8.4 — Volleyball League Expansion

**Current:** ~35 URLs
**Target:** ~60+ URLs

**New URLs to add:**

**A) More European leagues:**
```
https://www.flashscore.com/volleyball/czech-republic/
https://www.flashscore.com/volleyball/czech-republic/extraliga/
https://www.flashscore.com/volleyball/czech-republic/extraliga-women/
https://www.flashscore.com/volleyball/hungary/
https://www.flashscore.com/volleyball/hungary/extraliga/
https://www.flashscore.com/volleyball/slovakia/
https://www.flashscore.com/volleyball/slovakia/extraliga/
https://www.flashscore.com/volleyball/austria/
https://www.flashscore.com/volleyball/austria/bundesliga/
https://www.flashscore.com/volleyball/switzerland/
https://www.flashscore.com/volleyball/switzerland/nla/
https://www.flashscore.com/volleyball/sweden/
https://www.flashscore.com/volleyball/sweden/elitserien/
https://www.flashscore.com/volleyball/denmark/
https://www.flashscore.com/volleyball/denmark/volleyliga/
https://www.flashscore.com/volleyball/croatia/
https://www.flashscore.com/volleyball/croatia/superliga/
https://www.flashscore.com/volleyball/bulgaria/
https://www.flashscore.com/volleyball/bulgaria/superliga/
https://www.flashscore.com/volleyball/ukraine/
https://www.flashscore.com/volleyball/ukraine/super-league/
https://www.flashscore.com/volleyball/slovenia/
https://www.flashscore.com/volleyball/slovenia/1-a-dol/
```

**B) Americas:**
```
https://www.flashscore.com/volleyball/argentina/liga-a1-women/
https://www.flashscore.com/volleyball/chile/
https://www.flashscore.com/volleyball/chile/liga-a1/
https://www.flashscore.com/volleyball/peru/
https://www.flashscore.com/volleyball/mexico/
```

**C) Asia:**
```
https://www.flashscore.com/volleyball/china/
https://www.flashscore.com/volleyball/china/super-league/
https://www.flashscore.com/volleyball/china/super-league-women/
https://www.flashscore.com/volleyball/indonesia/
https://www.flashscore.com/volleyball/indonesia/proliga/
https://www.flashscore.com/volleyball/iran/
https://www.flashscore.com/volleyball/iran/super-league/
https://www.flashscore.com/volleyball/thailand/
https://www.flashscore.com/volleyball/thailand/premier-league/
https://www.flashscore.com/volleyball/philippines/
https://www.flashscore.com/volleyball/philippines/pvl/
```

**D) Additional competitions:**
```
https://www.flashscore.com/volleyball/world/club-world-championship/
https://www.flashscore.com/volleyball/world/club-world-championship-women/
https://www.flashscore.com/volleyball/south-america/south-american-championship/
https://www.flashscore.com/volleyball/asia/asian-championship/
```

**E) Additional sources:**
```
https://www.volleyballworld.com/
https://www.cev.eu/
```

**Total volleyball URLs after expansion: ~60+**

### Task 8.5 — Hockey League Expansion

**Current:** ~25 URLs
**Target:** ~45+ URLs

**New URLs to add:**

**A) More European leagues:**
```
https://www.flashscore.com/hockey/poland/
https://www.flashscore.com/hockey/poland/ekstraliga/
https://www.flashscore.com/hockey/uk/
https://www.flashscore.com/hockey/uk/eihl/
https://www.flashscore.com/hockey/france/
https://www.flashscore.com/hockey/france/ligue-magnus/
https://www.flashscore.com/hockey/hungary/
https://www.flashscore.com/hockey/hungary/erste-liga/
https://www.flashscore.com/hockey/latvia/
https://www.flashscore.com/hockey/latvia/optibet-hokeja-liga/
https://www.flashscore.com/hockey/belarus/
https://www.flashscore.com/hockey/belarus/extraliga/
https://www.flashscore.com/hockey/italy/
https://www.flashscore.com/hockey/italy/alps-hockey-league/
https://www.flashscore.com/hockey/slovenia/
https://www.flashscore.com/hockey/slovenia/alps-hockey-league/
https://www.flashscore.com/hockey/romania/
https://www.flashscore.com/hockey/romania/erste-liga/
https://www.flashscore.com/hockey/croatia/
https://www.flashscore.com/hockey/lithuania/
```

**B) North America — deeper:**
```
https://www.flashscore.com/hockey/usa/echl/
https://www.flashscore.com/hockey/usa/ushl/
https://www.flashscore.com/hockey/canada/ohl/
https://www.flashscore.com/hockey/canada/whl/
https://www.flashscore.com/hockey/canada/qmjhl/
```

**C) International:**
```
https://www.flashscore.com/hockey/world/world-championship-u20/
https://www.flashscore.com/hockey/world/world-championship-u18/
https://www.flashscore.com/hockey/europe/champions-hockey-league/
```

**D) Additional sources:**
```
https://www.eliteprospects.com/
https://www.hockeydb.com/
https://www.eurohockey.com/
```

**Total hockey URLs after expansion: ~45+**

---

## Phase 9: Source Library (src/bet)

### Task 9.1 — Update market_ranking.py

- **Type:** [MODIFY]
- **File:** `src/bet/stats/market_ranking.py`
- **Dependencies:** Phase 1
- **Changes:**

  **A) SPORT_STAT_KEYS:**
  - Remove keys: `"handball"`, `"snooker"`, `"darts"`, `"table_tennis"`, `"esports"`, `"baseball"`, `"mma"`, `"padel"`, `"speedway"`
  - Keep: `"football"`, `"basketball"`, `"hockey"`, `"tennis"`, `"volleyball"`

  **B) Individual market constant lists:**
  - Remove: `HANDBALL_MARKETS`, `SNOOKER_MARKETS`, `DARTS_MARKETS`, `TABLE_TENNIS_MARKETS`, `ESPORTS_MARKETS`, `BASEBALL_MARKETS`, `MMA_MARKETS`, `PADEL_MARKETS`, `SPEEDWAY_MARKETS`
  - Keep: `FOOTBALL_MARKETS`, `BASKETBALL_MARKETS`, `HOCKEY_MARKETS`, `TENNIS_MARKETS`, `VOLLEYBALL_MARKETS`

  **C) SPORT_MARKETS dict:**
  - Remove entries for the 9 removed sports.
  - Keep entries for the 5 sports.

  **D) STANDARD_MARKET_LINES:**
  - Remove lines for removed sports if present.

  **E) MARKET_PL translations:**
  - Remove Polish translations for markets that only apply to removed sports (e.g., frames, centuries, legs, checkout, etc.).
  - Keep all translations needed for the 5 sports.

- **Definition of Done:**
  - SPORT_STAT_KEYS has exactly 5 keys.
  - No market constants for removed sports remain.
  - SPORT_MARKETS has exactly 5 entries.
  - File imports and runs without errors.

### Task 9.2 — Audit other src/bet modules

- **Type:** [MODIFY]
- **File:** Multiple files in `src/bet/`
- **Dependencies:** Task 9.1
- **Changes:**
  - `src/bet/stats/enrichment.py` — uses `SPORT_STAT_KEYS`, may have sport-specific enrichment logic.
  - `src/bet/db/repositories.py` — has `_FALLBACK_STAT_KEYS` and references `SPORT_STAT_KEYS`.
  - Grep `src/bet/**/*.py` for any remaining references to removed sports and clean them up.
- **Definition of Done:**
  - `grep -r "snooker\|speedway\|baseball\|esports\|darts\|table_tennis\|handball\|\bmma\b\|padel" src/bet/` returns zero matches in functional code.

### Task 9.3 — Review database integration layer

- **Type:** [REVIEW + MODIFY]
- **Files:**
  - `src/bet/db/connection.py` — DB connection management, `get_db()`
  - `src/bet/db/repositories.py` — data access layer, fallback stat keys, query patterns
  - `src/bet/db/models.py` — ORM models / table definitions
  - `src/bet/db/schema.py` / `src/bet/db/schema.sql` — schema definition
  - `scripts/db_data_loader.py` — data ingestion into DB
  - `scripts/normalize_stats.py` — `build_safety_input_from_db()`, `build_safety_input_from_cache()`
- **Dependencies:** Tasks 9.1, 9.2
- **Changes:**

  **A) Audit data flow:**
  - Map the full data path: scan → enrichment → DB storage → DB query → analysis
  - Verify R2 compliance: all scripts use `from bet.db.connection import get_db`, no raw `sqlite3.connect()`
  - Identify any scripts that bypass the DB and read/write JSON directly (should be fallback only)

  **B) Verify deep data storage:**
  - Confirm DB schema can store the new deep data from Phase 4:
    - Per-match stats (not just averages) — does the schema support match-level records?
    - H2H per-stat breakdowns — is there a table or column for stat-specific H2H?
    - Injury/suspension data — where is this stored?
    - League context (standings, zones) — table exists?
    - Coach stability data — storage mechanism?
  - If schema gaps exist → add ALTER TABLE or new tables as needed
  - Update `schema.sql` if new tables/columns are added

  **C) Review repository query patterns:**
  - `repositories.py` queries should efficiently retrieve deep data for analysis
  - Verify `_FALLBACK_STAT_KEYS` covers all 5 sports properly
  - Check for N+1 query patterns that could slow down analysis of 50+ candidates
  - Ensure `build_safety_input_from_db()` returns rich data (not just averages)

  **D) Data loader alignment:**
  - `db_data_loader.py` must ingest ALL data produced by Phase 4 enrichment scripts
  - Verify it handles: API stats, deep-parsed HTML stats, H2H data, injury data, league standings
  - Add ingestion paths for any new data types from Phase 4

- **Definition of Done:**
  - Full data flow documented: source → script → DB table → query → analysis
  - No raw `sqlite3.connect()` in any script (R2)
  - DB schema supports all Phase 4 deep data types (or migrations added)
  - Repository queries are efficient for 50+ candidate analysis
  - `build_safety_input_from_db()` returns deep data, not shallow averages
  - `db_data_loader.py` handles all new data types from Phase 4

---

## Phase 10: Skills Cleanup

### Task 10.1 — Archive removed sport scanning skills

- **Type:** [MODIFY] (rename/move)
- **File:** Multiple skill directories
- **Dependencies:** Phase 2
- **Changes:**
  - The following 6 skills serve ONLY removed sports and should be archived (not deleted — they represent documented knowledge):
    - `.github/skills/bet-scanning-baseball/` → rename to `.github/skills/_archived/bet-scanning-baseball/`
    - `.github/skills/bet-scanning-combat/` → rename to `.github/skills/_archived/bet-scanning-combat/`
    - `.github/skills/bet-scanning-esports/` → rename to `.github/skills/_archived/bet-scanning-esports/`
    - `.github/skills/bet-scanning-handball/` → rename to `.github/skills/_archived/bet-scanning-handball/`
    - `.github/skills/bet-scanning-niche/` → rename to `.github/skills/_archived/bet-scanning-niche/`
    - `.github/skills/bet-scanning-racket/` → rename to `.github/skills/_archived/bet-scanning-racket/`
  - Keep the 5 remaining scanning skills:
    - `bet-scanning-football/`
    - `bet-scanning-basketball/`
    - `bet-scanning-hockey/`
    - `bet-scanning-tennis/`
    - `bet-scanning-volleyball/`

  **Alternative (simpler):** Instead of moving, add a `# ARCHIVED — Sport removed from pipeline` header to each SKILL.md and remove them from the skills list in copilot-instructions.md.
- **Definition of Done:**
  - Removed-sport scanning skills are no longer discoverable by agents.
  - No data loss (skills are archived, not deleted).

### Task 10.2 — Update sport-analysis-protocols skill

- **Type:** [MODIFY]
- **File:** `.github/skills/bet-applying-sport-protocols/SKILL.md`
- **Dependencies:** Task 4.3
- **Changes:**
  - Update description to reference 5 sports instead of 14.
  - Remove removed-sport protocol references from the skill's body.
- **Definition of Done:**
  - Skill mentions 5 sports consistently.

### Task 10.3 — Update source navigation skill

- **Type:** [MODIFY]
- **File:** `.github/skills/bet-navigating-sources/SKILL.md`
- **Dependencies:** Task 3.1
- **Changes:**
  - Update to reference 5-sport source landscape.
  - Remove fallback chains for removed sports.
- **Definition of Done:**
  - No removed sport fallback chains in the skill.

---

## Phase 11: Code Review & Validation

**ORCHESTRATOR PROTOCOL:** After EACH phase (1-10) is implemented, the orchestrator MUST:
1. Run validation checks relevant to that phase (imports, grep, functional test)
2. Use sequential thinking (THINK IN THE MIDDLE) to analyze validation results
3. If ANY issue found → fix it → rerun the phase → revalidate
4. Do NOT proceed to next phase until current phase passes validation
5. Log phase completion with: files changed, tests passed, issues found & fixed

This is NOT optional. Skipping validation between phases causes cascading failures.

### Task 11.1 — Grep audit for removed sports

- **Type:** [REVIEW]
- **Dependencies:** All previous phases
- **Steps:**
  1. Run: `grep -rn "snooker\|speedway\|baseball\|esports\|darts\|table_tennis\|handball\|\bmma\b\|padel" --include="*.py" --include="*.json" --include="*.md" .`
  2. Review each match — should be ZERO in functional code/config.
  3. Acceptable: archive headers, migration notes, git history references.
- **Definition of Done:**
  - Zero functional references to removed sports in the codebase.

### Task 11.2 — Config validation

- **Type:** [REVIEW]
- **Steps:**
  1. Parse `config/betting_config.json` — verify 5 sports.
  2. Parse `config/scan_urls.json` — verify 6 groups (5 sports + tipsters), count URLs per group.
  3. Verify all Flashscore URLs are syntactically valid.
  4. Cross-reference: every sport in betting_config.json has a matching group in scan_urls.json.
- **Definition of Done:**
  - Config files are consistent and parseable.
  - URL counts meet targets from Phase 5.

### Task 11.3 — Import chain validation

- **Type:** [REVIEW]
- **Steps:**
  1. Run: `python3 -c "from bet.stats.market_ranking import SPORT_STAT_KEYS, SPORT_MARKETS; print(list(SPORT_STAT_KEYS.keys())); print(list(SPORT_MARKETS.keys()))"`
  2. Run: `python3 -c "from scripts.agent_protocol import STEP_AGENT_CONFIG; print('OK')"`
  3. Run: `python3 scripts/build_shortlist.py --help`
  4. Run: `python3 scripts/generate_market_matrix.py --help`
  5. Verify no import errors from removed sport references.
- **Definition of Done:**
  - All core scripts import without errors.
  - SPORT_STAT_KEYS and SPORT_MARKETS return exactly 5 keys.

### Task 11.4 — Database compatibility check

- **Type:** [REVIEW]
- **Steps:**
  1. Verify DB schema doesn't hard-code sport names (it uses sport_id references → safe).
  2. Old data for removed sports remains in DB but is simply never queried by the updated pipeline.
  3. No migration needed — the DB schema is sport-agnostic (sport names are in the `sports` table).
- **Definition of Done:**
  - Confirmed: no DB schema changes needed.
  - Old data is harmless (orphaned but not blocking).

### Task 11.5 — Full script inventory validation

- **Type:** [REVIEW]
- **Dependencies:** Task 2.7, 2.8
- **Steps:**
  1. Verify `scripts/` contains only ACTIVE + UTILITY scripts (no stale scripts)
  2. Verify `scripts/_archived/` contains all archived scripts
  3. Verify no active script imports from `_archived/`
  4. Run all active scripts with `--help` to confirm they load without errors
  5. Verify `pipeline_orchestrator.py` is gone or archived
- **Definition of Done:**
  - Clean `scripts/` directory with only pipeline-relevant scripts
  - All scripts load without import errors

---

## Phase 12: Live Test

### Task 12.1 — Run pipeline for 2026-05-10

- **Type:** [EXECUTE]
- **Dependencies:** All previous phases complete
- **BETTING WINDOW:** 2026-05-10 06:00 → 2026-05-11 05:59 (Europe/Warsaw). Events starting within this window are valid — including live/in-play events.
- **Steps:**
  1. Settle 2026-05-09 results first:
     ```
     python3 scripts/settle_on_finish.py --betting-day 2026-05-09
     ```
  2. Run Betclic learning analysis:
     ```
     python3 scripts/analyze_betclic_learning.py
     ```
  3. Run fixture scan (agent-driven, per sport group):
     ```
     python3 scripts/scan_events.py --sport-group football --date 2026-05-10
     python3 scripts/scan_events.py --sport-group tennis --date 2026-05-10
     python3 scripts/scan_events.py --sport-group basketball --date 2026-05-10
     python3 scripts/scan_events.py --sport-group volleyball --date 2026-05-10
     python3 scripts/scan_events.py --sport-group hockey --date 2026-05-10
     ```
  4. Build market matrix:
     ```
     python3 scripts/generate_market_matrix.py --date 2026-05-10 --stats-first
     ```
  5. Build shortlist:
     ```
     python3 scripts/build_shortlist.py --date 2026-05-10 --stats-first
     ```
  6. **DATA GAP CHECK:** For candidates missing H2H or critical data → spawn `web_research_agent.py` to find it.
  7. Verify output:
     - Multiple sports in the shortlist? (depends on schedule — no minimum enforced)
     - New lower-division leagues appearing in the matrix?
     - No references to removed sports in output files?
     - Data quality scores computed per candidate?
  8. Run deep stats + gate + coupon builder.
  9. Agent reviews each step output using sequential thinking (THINK IN THE MIDDLE).
  10. Verify: no event duplication in coupons.
  11. Verify: data quality labels present on all picks.
  12. **LIVE WINDOW CHECK:** Are there events starting soon (≤1h) or in-play? Flag as LIVE, include in coupon with live betting note.

- **Definition of Done:**
  - Pipeline runs end-to-end without errors.
  - Shortlist contains events with DEEP data (H2H, form, injuries where available).
  - Lower-division leagues from new URLs appear in the fixture scan.
  - Coupon output has no removed-sport references.
  - No event appears in more than 1 core coupon.
  - Data quality labels (FULL/PARTIAL/MINIMAL) shown per pick.
  - Web research agent was spawned for data gaps (if any existed).
  - Live/in-play events flagged and included where applicable.
  - Agent provides qualitative analysis with sequential thinking at each step.

---

## Summary: File Change Matrix

| File | Phase | Type | Impact |
|------|-------|------|--------|
| `config/betting_config.json` | 1 | MODIFY | Sports list 14→5 |
| `config/scan_urls.json` | 1, 8 | MODIFY | Remove 6 groups, expand 5 with ~120 new URLs |
| `scripts/agent_protocol.py` | 2, 6 | MODIFY | 5-sport refs, agent behaviors, error handling, remove diversity gate |
| `scripts/build_shortlist.py` | 2 | MODIFY | Protected leagues, comp tiers, TIER1_SPORTS |
| `scripts/generate_market_matrix.py` | 2 | MODIFY | Sport mappings, MAJOR_COMPETITIONS |
| `scripts/scan_events.py` | 2 | MODIFY | URL patterns, rate limits |
| `scripts/ingest_scan_stats.py` | 2 | MODIFY | Remove 7 sport parsers |
| `scripts/*.py` (audit) | 2 | MODIFY | Various removed-sport references |
| `betting/sources/source-registry.md` | 3 | MODIFY | Major rewrite: remove 7 sport sections, enhance 5 |
| `scripts/data_enrichment_agent.py` | **4** | MODIFY | **Deep data extraction, Sofascore/ESPN deep fetch** |
| `scripts/fetch_api_stats.py` | **4** | MODIFY | **Maximize API data extraction, per-match storage** |
| `scripts/html_deep_parser.py` | **4** | MODIFY | **Profile audit, deep extraction rules** |
| `scripts/context_checks.py` | **4** | MODIFY | **Injuries, coach stability, league context** |
| `scripts/normalize_stats.py` | **4** | MODIFY | **Per-stat H2H, data completeness** |
| `scripts/tipster_aggregator.py` | **4** | MODIFY | **Expert sentiment extraction** |
| `scripts/deep_stats_report.py` | **5** | MODIFY | **10-section rewrite with deep data, eliminate shallow fallback** |
| `scripts/gate_checker.py` | **5** | MODIFY | **Remove sport diversity gate, add data quality gate** |
| `scripts/coupon_builder.py` | **5** | MODIFY | **No event duplication, data quality labels** |
| `scripts/compute_safety_scores.py` | **5** | MODIFY | **data_quality_score computation** |
| `.github/copilot-instructions.md` | 7 | MODIFY | R4 rewritten, R14-R16 added, R11 enhanced |
| `.github/instructions/analysis-methodology.instructions.md` | 7 | MODIFY | Sport tiers, data depth requirements |
| `.github/instructions/sport-analysis-protocols.instructions.md` | 7 | MODIFY | Remove 9 sport protocol sections |
| `.github/instructions/betting-artifacts.instructions.md` | 7 | MODIFY | Minor cleanup |
| `src/bet/stats/market_ranking.py` | 9 | MODIFY | SPORT_STAT_KEYS, markets, translations |
| `src/bet/db/*.py` | 9 | REVIEW+MODIFY | **DB integration layer: schema, repositories, data flow** |
| `scripts/db_data_loader.py` | 9 | REVIEW+MODIFY | **Ingestion paths for Phase 4 deep data** |
| `scripts/normalize_stats.py` | 9 | REVIEW | **build_safety_input_from_db() deep data** |
| `.github/skills/bet-scanning-*` (5 kept) | **6** | MODIFY | **Deep data requirements, validation checklists** |
| `.github/skills/bet-analyzing-statistics/` | **6** | MODIFY | **Data depth requirements, reasoning mandates** |
| `.github/skills/bet-building-coupons/` | **6** | MODIFY | **No duplication, data quality, historical learning** |
| `.github/skills/bet-scanning-*` (6 archived) | 10 | ARCHIVE | Move/mark as archived |
| `scripts/web_research_agent.py` | **4** | CREATE | **L7 fallback: web search for missing H2H, injuries, etc.** |
| `scripts/_archived/*` | **2** | ARCHIVE | **Stale/legacy scripts moved out of active pipeline** |
| `scripts/pipeline_orchestrator.py` | **2** | DELETE/ARCHIVE | **⛔ BANNED — agent IS the orchestrator** |

**Total files affected:** ~40  
**New phases (vs v1):** Phase 4 (Data Depth), Phase 5 (Analysis Rewrite), Phase 6 (Agent Methodology)  
**Key paradigm shift:** Quality of DATA per match > number of sports covered  
**Key additions (v4):** Script audit + cleanup, web research agent, phase validation protocol, live betting window

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Lower-division Flashscore URLs may not exist or return 404 | Validate each URL before committing; Flashscore dynamically serves country pages |
| Some days may have <5 sports active | **No minimum enforced** — quality over diversity (R4 rewritten) |
| Old DB data for removed sports may confuse queries | DB queries filter by sport from config — old data is inert |
| Betclic may not cover some lower-division leagues | Stats-first mode (R10) handles this — user checks app manually |
| Scan time may increase with more URLs | Flashscore parallel fetching (3 concurrent) mitigates; timeout per group already set |
| Deep data extraction (Phase 4) may increase pipeline runtime | Prioritize API sources (instant) over Playwright scraping (slow). Cache aggressively. |
| Sofascore/ESPN API endpoints may change | Multiple fallback sources per sport. Self-healing registry detects and logs failures. |
| H2H per-stat data may not be available for minor leagues | Apply 0.7 H2H-blind penalty honestly. PARTIAL quality label warns user. Web research agent (L7) tries to find it. |
| Agent sequential thinking adds latency | Worth it — THINK IN THE MIDDLE means no wasted time. Reasoning happens on actual output, not idle speculation. |
| Stale scripts may have hidden dependencies | Task 2.7 reviews ALL scripts before archiving. Move to `_archived/`, don't delete. |
| SerpAPI budget (100/month) consumed too fast | Web research agent rate-limited: max 5 SerpAPI + 10 Playwright searches per run. Priority: MINIMAL→PARTIAL upgrades. |
| Live/in-play events may have volatile odds | R16 flags live events. User checks Betclic app in real-time. Conditional picks still apply (R12). |
| DB schema may lack tables for deep data (Phase 4) | Task 9.3 audits and extends schema. ALTER TABLE is cheap. |

---

## Execution Order (Revised)

```
Phase 1 (config — sport reduction + league expansion)
  └→ Phase 2 (script updates — remove sports) + Phase 9 (src/bet) [parallel]
       └→ Phase 3 (source registry)
            └→ Phase 4 (DATA DEPTH REVOLUTION) ← #1 PRIORITY
                 └→ Phase 5 (ANALYSIS PIPELINE REWRITE) ← CRITICAL
                      └→ Phase 6 (AGENT METHODOLOGY OVERHAUL)
                           └→ Phase 7 (instructions & methodology)
                                └→ Phase 8 (league expansion URLs)
                                     └→ Phase 10 (skills cleanup)
                                          └→ Phase 11 (validation)
                                               └→ Phase 12 (LIVE TEST — May 10, 2026)
```

Phases 2+9 can run in parallel. Phases 4-6 are the CORE of this overhaul — they are sequential because each builds on the previous.

**PHASE VALIDATION PROTOCOL:** After each phase, orchestrator MUST:
1. Run validation (imports, grep, functional tests)
2. THINK IN THE MIDDLE — analyze results with sequential thinking
3. If issues found → fix → rerun phase → revalidate
4. Log: files changed, tests passed, issues found & resolved
5. Only proceed to next phase after validation passes

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-09 | v1 | Initial plan — 9 phases, sport reduction + league expansion |
| 2026-05-09 | v2 | **Major revision based on user feedback:** Added Phase 4 (Data Depth Revolution), Phase 5 (Analysis Pipeline Rewrite), Phase 6 (Agent Methodology Overhaul). Removed sport diversity minimum entirely. Added R14 (Data Quality). Enhanced R11 (sequential thinking + reasoning). Added data_quality_score. No event duplication in coupons. ~35 files affected (was ~25). Core paradigm shift: DATA DEPTH > sport count. |
| 2026-05-09 | v3 | **User feedback:** (1) Added Task 9.3 — DB integration layer review (data flow audit, schema gaps for deep data, repository query patterns, data loader alignment). (2) Fixed R11 — replaced "reason before/after" with "THINK IN THE MIDDLE" paradigm: reasoning happens on actual script output when it arrives, not wasted speculation before a 5-10min script. ~38 files affected. |
| 2026-05-09 | v4 | **User feedback:** (1) Task 2.7 — deep review of ALL major pipeline scripts (categorize ACTIVE/UTILITY/STALE). (2) Task 2.8 — cleanup stale/legacy scripts (archive ~18 candidates incl. banned pipeline_orchestrator.py). (3) Phase validation protocol — orchestrator validates after EACH phase, fixes & reruns if issues found. (4) Task 4.9 + R15 — web research agent (L7 fallback) for missing H2H, injuries, form data via SerpAPI/Playwright. (5) R16 — live betting window enforcement (06:00-05:59, in-play events valid, ≤1h kickoff flagged as LIVE). (6) Task 11.5 — script inventory validation. ~40 files affected. |
