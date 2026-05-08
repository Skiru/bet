#!/usr/bin/env python3
"""Agent communication protocol for pipeline steps.

Each pipeline step that requires agent review writes a structured JSON
input file. Agents (via Copilot) read the input, perform qualitative
analysis, and write a review JSON response. The orchestrator reads
agent responses and merges enrichments into the pipeline state.

All files are written to: betting/data/agent_reviews/{date}/
- {step_id}_input.json  — written by pipeline after step completes
- {step_id}_review.json — written by agent (manually or via Copilot)
"""

import json
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).parent.parent
REVIEWS_DIR = ROOT_DIR / "betting" / "data" / "agent_reviews"

# ---------------------------------------------------------------------------
# Database Schema Reference — compact map for agent awareness
# ---------------------------------------------------------------------------
DB_SCHEMA_REFERENCE = {
    "connection": {
        "how": "from bet.db.connection import get_db; with get_db() as conn: ...",
        "db_path": "src/bet/db/betting.db (SQLite)",
        "repositories": "from bet.db.repositories import SportRepo, TeamRepo, FixtureRepo, CompetitionRepo, AnalysisResultRepo, StatsRepo, GateResultRepo, CouponRepo, PipelineRepo, OddsRepo, SourceHealthRepo, ScanResultRepo, AthleteRepo, StandingRepo",
    },
    "core_tables": {
        "sports": "id, name, tier(1=KEY,2=SUPPORT), stat_keys(JSON list of bettable stat keys per sport)",
        "teams": "id, sport_id→sports, name, aliases(JSON), country, venue, style_tags(JSON)",
        "competitions": "id, sport_id→sports, name, country, importance(1-10), season",
        "fixtures": "id, external_id, sport_id→sports, competition_id→competitions, home_team_id→teams, away_team_id→teams, kickoff, status, score_home, score_away, source",
        "athletes": "id, external_id, sport_id→sports, team_id→teams, name, position, status, source",
    },
    "stats_tables": {
        "team_form": "id, team_id→teams, sport_id→sports, stat_key, l10_values(JSON), l5_values(JSON), l10_avg, l5_avg, h2h_values(JSON), h2h_opponent_id→teams, trend(up/down/stable), source — PRIMARY STATS SOURCE for L10/H2H/L5 three-way cross-check",
        "match_stats": "id, fixture_id→fixtures, team_id→teams, stat_key, stat_value, source — per-match actuals",
        "league_profiles": "id, competition_id→competitions, stat_key, season, avg_value, median_value, std_dev, sample_size — league baselines for deviation analysis",
        "standings": "id, competition_id→competitions, team_id→teams, season, rank, wins/draws/losses, goals_for/against, form(last-5-string), home/away splits, streak",
        "power_index": "id, team_id→teams, sport_id→sports, rating, offensive_rating, defensive_rating, rank, source — ESPN BPI/FPI/SPI",
    },
    "analysis_tables": {
        "analysis_results": "id, fixture_id→fixtures, betting_date, has_data, best_market_name/line/direction, best_safety_score, markets_evaluated, ranking_json(full market ranking), three_way_check_json, warnings_json, stats_summary_json(ENRICHED by S4/S5/S6: ev, odds, context_flags, upset_risk), source",
        "analysis_raw_data": "id, fixture_id→fixtures, betting_date, team_a_l10_json, team_b_l10_json, h2h_meetings_json, per_market_details_json, safety_input_json — raw stat inputs for reproducibility",
        "gate_results": "id, fixture_id→fixtures, betting_date, status(STRONG/MODERATE/WEAK/FLAGGED), gate_score(0-18), gate_details_json(per-point breakdown), best_market_*, ev, risk_tier(LR/MS/HR/N), rejection_reasons_json",
        "decision_snapshots": "id, bet_id→bets, fixture_id→fixtures, chosen_market/line/direction, safety_score, all_markets_considered_json, reasoning_json, thresholds_json — pre-bet decision state for learning",
        "decision_outcomes": "id, bet_id→bets, fixture_id→fixtures, predicted_value, actual_value, deviation, result, pattern_tags_json — post-settlement outcome analysis",
    },
    "betting_tables": {
        "coupons": "id, coupon_id(e.g. C-20260508-A), coupon_type(core/combo/discovery), total_odds, stake_pln, status(pending/won/lost/partial/void), pnl_pln, betclic_ref, version",
        "bets": "id, coupon_id→coupons, fixture_id→fixtures, sport, event_name, market, selection, odds, min_odds, safety_score, hit_rate, status, pnl_pln, market_pl(Polish market name)",
        "odds_history": "id, fixture_id→fixtures, bookmaker, market, selection, odds, line, fetched_at, is_closing — tracks odds movement for CLV analysis",
    },
    "pipeline_tables": {
        "pipeline_runs": "id, date, step, status(running/completed/failed), started_at, completed_at, error_message, stats(JSON summary per step)",
        "scan_results": "id, betting_date, sport, source_domain, event_key, home_team, away_team, competition, kickoff, raw_data(JSON) — raw scan output",
        "scan_run_stats": "id, betting_date, sport, scanner_group, events_found, sources_ok/failed, deep_links_found, duration_seconds, validation_passed, gaps_description",
        "source_health": "id, source_name, last_success/failure, consecutive_failures, total_requests/failures, avg_response_ms — tracks source reliability",
    },
    "espn_tables": {
        "espn_predictions": "id, fixture_id→fixtures, home_win_pct, away_win_pct, tie_pct, predictor_json, power_index_home/away",
        "player_gamelogs": "id, athlete_id→athletes, fixture_id→fixtures, stats_json — per-game player stats",
        "player_splits": "id, athlete_id→athletes, split_type(home/away/vs_conf), stats_json — aggregated splits",
        "team_ats_records": "id, team_id→teams, sport_id, wins/losses/pushes + home/away splits — ATS (against the spread) records",
        "team_ou_records": "id, team_id→teams, sport_id, overs/unders/pushes + home/away splits — over/under records",
        "team_rosters": "id, team_id→teams, athlete_id→athletes, position, depth_rank, status",
    },
    "key_query_patterns": {
        "resolve_fixture": "FixtureRepo(conn).find_by_teams_and_date(home, away, date) → fixture.id",
        "load_team_form": "StatsRepo(conn).load_team_form(team_id, sport_id, stat_key) → TeamForm with l10/l5/h2h",
        "save_analysis": "AnalysisResultRepo(conn).save(AnalysisResult(...)) → INSERT OR REPLACE",
        "update_s4_s5_s6": "AnalysisResultRepo(conn).update_stats_summary(fixture_id, date, summary_dict) → pure UPDATE to stats_summary_json",
        "load_analysis": "from db_data_loader import load_analysis_results_from_db → returns list of analysis dicts with ev, context_flags, upset_risk",
        "save_gate": "from db_data_loader import save_gate_results_to_db",
    },
}

# ---------------------------------------------------------------------------
# Self-healing tools registry — data recovery mechanisms available to agents
# ---------------------------------------------------------------------------
SELF_HEALING_REGISTRY = {
    "enrichment_agent": {
        "module": "data_enrichment_agent",
        "functions": {
            "enrich_team": "Fetch L10/L5 stats for a single team from Flashscore→Sofascore fallback. Args: (team_name, sport). Returns: {status, stats_found, source}. Saves to DB + JSON cache.",
            "enrich_h2h": "Fetch H2H stats between two teams from Flashscore. Args: (team_a, team_b, sport). Returns: {status, h2h_stats, meetings_found}. Saves to DB.",
            "batch_enrich": "Enrich multiple teams in parallel. Args: (teams=[{team, sport, missing}], max_workers=4). Thread-safe with rate limiting.",
            "_detect_missing_from_shortlist": "Auto-scan shortlist for teams without cached data. Args: (date_str). Returns: [{team, sport, missing}].",
        },
        "sources": ["Flashscore (primary, 2s rate limit)", "Sofascore (fallback, 3s rate limit)"],
        "rate_limits": "Thread-safe _rate_lock, per-domain minimum intervals: flashscore=2s, sofascore=3s",
        "saves_to": ["team_form (DB)", "betting/data/stats_cache/{sport}/{team_slug}.json (file cache)"],
    },
    "playwright_fetcher": {
        "module": "fetch_with_playwright",
        "functions": {
            "fetch": "Fetch any URL via headless Chromium. Args: (url, save_snapshot=True). Returns: HTML string or None. Handles anti-bot, retries, timeouts.",
        },
        "use_when": "Agent needs raw HTML from any sports data source not covered by other tools",
    },
    "espn_data": {
        "modules": {
            "fetch_espn_odds": "Fetch ESPN odds/predictions for a sport. Saves to odds_history + espn_predictions DB tables.",
            "fetch_espn_standings": "Fetch ESPN standings, ATS/OU records, rosters. Saves to standings + team_ats_records + team_ou_records DB tables.",
        },
        "use_when": "Missing odds, predictions, standings, or ATS/OU records for US sports (NFL, NBA, MLB, NHL, NCAA) or football",
    },
    "api_stats": {
        "module": "fetch_api_stats",
        "description": "API-Football fixture + team stats. Saves to fixtures + team_form DB tables.",
        "use_when": "Missing fixture data or team form for football/soccer matches",
    },
    "tennis_enrichment": {
        "module": "enrich_tennis_stats",
        "description": "Deep tennis data from Flashscore — serve %, break points, tiebreak records. Saves to team_form DB.",
        "use_when": "Tennis candidates missing serve/return stats for ace/double-fault/tiebreak markets",
    },
    "odds_api": {
        "module": "fetch_odds_api",
        "description": "The Odds API — cross-bookmaker odds comparison. 30 credits/scan, 500/month free.",
        "use_when": "Need independent odds validation or missing odds for specific events",
    },
    "fallback_layers": [
        "L1: Scan retry with extended timeout (pipeline auto-handles)",
        "L2: Parallel S1b enrichment (ESPN odds + weather + tipsters concurrently)",
        "L3: S2.5 batch enrichment via data_enrichment_agent (Flashscore/Sofascore)",
        "L4: S3 batch enrichment before analysis loop",
        "L5: S3 inline extract_team_stats/extract_h2h_stats fallback (per-candidate)",
        "L6: S5 inline context fetch (weather API + ESPN injury scrape)",
    ],
}

# ---------------------------------------------------------------------------
# Agent skills & instructions map — what each agent role should load
# ---------------------------------------------------------------------------
AGENT_SKILLS_MAP = {
    "bet-scanner": {
        "role": "Scan verification & shortlist curation specialist",
        "responsibilities": [
            "Verify 14-sport coverage across all scan sources",
            "Cross-validate fixtures appear in ≥2 independent sources",
            "Check deep-link discovery yield and flag source failures",
            "Review shortlist for sport diversity (≥8 sports), ensure KEY sports ≥60%",
            "Verify ALL candidates included — NO artificial caps or auto-filtering",
            "Flag missing major leagues and tournaments (§SCAN.7 tournament protection)",
            "Apply §SCAN.8 minor league value edge — never penalize 'obscure' events",
        ],
        "skills_to_load": [
            "bet-navigating-sources (source hierarchy, fallback chains, URL patterns)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§SCAN.7, §SCAN.8, §1.1-§1.8)",
        ],
        "db_reads": ["scan_results", "scan_run_stats", "source_health", "fixtures", "competitions"],
        "db_writes": [],
        "can_trigger_enrichment": False,
    },
    "bet-scout": {
        "role": "Tipster cross-reference & consensus analyst",
        "responsibilities": [
            "Read FULL tipster arguments (not just pick summaries)",
            "Assess tipster quality: track record, reasoning depth, independence",
            "Discover analytical angles that pure stats might miss",
            "Identify consensus picks (≥2 independent tipsters agree)",
            "Promote watchlist picks with strong tipster backing",
            "Flag tipster picks that contradict statistical analysis",
        ],
        "skills_to_load": [
            "bet-navigating-sources (Tier B tipster sites, access patterns)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§2 tipster cross-reference)",
        ],
        "db_reads": ["analysis_results", "fixtures"],
        "db_writes": [],
        "can_trigger_enrichment": False,
    },
    "bet-enricher": {
        "role": "Data quality guardian & self-healing enrichment specialist",
        "responsibilities": [
            "Review enrichment yield by sport and source",
            "Identify sports/leagues with persistent data gaps",
            "Suggest alternative sources for failed enrichments",
            "Verify enriched data quality (stat values within expected ranges)",
            "Flag teams that consistently fail enrichment (need manual source discovery)",
            "Ensure enriched data flows correctly to DB (team_form table)",
        ],
        "skills_to_load": [
            "bet-navigating-sources (all tiers, fallback chains per sport)",
            "bet-analyzing-statistics (data quality validation)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§2.5 enrichment)",
        ],
        "db_reads": ["team_form", "teams", "sports", "source_health"],
        "db_writes": ["team_form (via data_enrichment_agent)"],
        "can_trigger_enrichment": True,
        "enrichment_tools": ["enrich_team", "enrich_h2h", "batch_enrich"],
    },
    "bet-statistician": {
        "role": "Deep statistical analyst & market ranking specialist",
        "responsibilities": [
            "Interpret safety scores and identify edge mechanisms",
            "Perform §3.0 STATISTICAL MARKET RANKING per candidate",
            "Execute THREE-WAY CROSS-CHECK: L10 avg + H2H avg + L5 trend must ALL align",
            "§3.0c H2H MARKET-SPECIFIC VALIDATION: verify H2H data exists for exact stat being bet",
            "Calculate ALL available stat markets per match, pick highest safety score",
            "Apply sport-specific mandatory multi-market calculation tables",
            "Write ANALYTICAL REASONING per candidate (not just numbers)",
            "Flag candidates with insufficient data for reliable analysis",
            "If stats missing → trigger enrichment via data_enrichment_agent before analysis",
        ],
        "skills_to_load": [
            "bet-analyzing-statistics (§3.0 protocol, safety score calculation, H2H validation)",
            "bet-applying-sport-protocols (per-sport stat tables, mandatory markets, upset checklists)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§3-§3.0c, STEP 3)",
            "sport-analysis-protocols.instructions.md (per-sport §XM tables)",
        ],
        "db_reads": ["team_form", "match_stats", "league_profiles", "standings", "analysis_results", "analysis_raw_data", "fixtures", "teams", "sports", "power_index"],
        "db_writes": ["analysis_results", "analysis_raw_data"],
        "can_trigger_enrichment": True,
        "enrichment_tools": ["enrich_team", "enrich_h2h"],
        "key_principle": "We bet on STATISTICAL MARKETS — corners, fouls, cards, shots, games, sets, points > match winners. EVERY football match must have ≥1 corners/fouls/shots market evaluated.",
    },
    "bet-valuator": {
        "role": "Odds evaluation & expected value specialist",
        "responsibilities": [
            "Cross-validate pricing across sources (BetExplorer, OddsPortal, The-Odds-API, ESPN)",
            "Calculate EV for each candidate: EV = (hit_rate × odds) - 1",
            "Detect odds drift >8% → mandatory re-evaluation",
            "Apply Kelly 1/4 criterion for stake sizing",
            "Assess edge durability — will the line still be available at placement time?",
            "Calculate relative value vs closing line (CLV potential)",
            "For stats-first mode: calculate minimum acceptable odds = 1 / hit_rate",
            "Merge EV, odds into analysis_results.stats_summary_json via update_stats_summary()",
        ],
        "skills_to_load": [
            "bet-evaluating-odds (EV calculation, Kelly, drift detection, American odds conversion)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§4 odds evaluation, §5.ALT stats-first)",
        ],
        "db_reads": ["analysis_results", "odds_history", "fixtures", "espn_predictions"],
        "db_writes": ["analysis_results (update_stats_summary for ev/odds fields)"],
        "can_trigger_enrichment": True,
        "enrichment_tools": ["fetch_odds_api (30 credits/scan)"],
    },
    "bet-challenger": {
        "role": "Devil's advocate, context analyst & risk assessor",
        "responsibilities": [
            "S5: Assess REAL market impact of weather, injuries, venue, referee, motivation",
            "S5: Model motivation effects — tournament stage, relegation battle, dead rubber",
            "S5: Identify compounding risk factors (multiple flags on same event)",
            "S6: Score upset risk using sport-specific checklists with numerical thresholds",
            "S6: Apply Paradox Rule — heavy favorites in low-motivation spots",
            "S7: Build qualitative BEAR CASES per candidate — what could go wrong?",
            "S7: Audit statistical assumptions — sample size, recency, opponent quality",
            "S7: Find historical analogies from past betting results",
            "S7: Bayesian-update confidence based on context + upset risk",
            "Merge context_flags/upset_risk into analysis_results.stats_summary_json",
        ],
        "skills_to_load": [
            "bet-applying-sport-protocols (upset risk checklists, instant red flags §7.3)",
            "bet-analyzing-statistics (safety score validation)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§5 context, §6 upset risk, §7 gate)",
        ],
        "db_reads": ["analysis_results", "gate_results", "fixtures", "standings", "espn_predictions", "team_form"],
        "db_writes": ["analysis_results (update_stats_summary for context_flags/upset_risk)", "gate_results"],
        "can_trigger_enrichment": True,
        "enrichment_tools": ["fetch_espn_standings (injury/roster data)", "fetch (weather URLs via Playwright)"],
    },
    "bet-builder": {
        "role": "Portfolio construction & coupon validation specialist",
        "responsibilities": [
            "Build core portfolio: unique event per coupon, max 8 legs",
            "Create COMBO MENU: extra combinations remixing approved picks",
            "Build EXTENDED POOL: EV>0 but gate-failed picks for user review",
            "Split by advisory tier: STRONG+MODERATE → primary, WEAK/FLAGGED → discovery",
            "Check hidden correlations between legs (same league, weather, surface)",
            "Run coupon stress test (§8.2) — what if 1 leg fails?",
            "Apply V1-V10 validation suite + §S8.FINAL mechanical verification",
            "Assign risk tier labels: LR/MS/HR/N per coupon",
            "Adjust stakes by conviction — higher conviction = closer to Kelly optimal",
            "Per-pick concentration limits — no single pick >25% of stake",
        ],
        "skills_to_load": [
            "bet-building-coupons (portfolio rules, V1-V10, §S8.FINAL, correlation checks)",
            "bet-formatting-artifacts (coupon table structure, Polish market names, ID generation)",
            "bet-evaluating-odds (Kelly 1/4 for stake sizing)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§8 coupon building, §S8.FINAL)",
            "betting-artifacts.instructions.md (output formats)",
        ],
        "db_reads": ["analysis_results", "gate_results", "fixtures", "odds_history", "coupons", "bets"],
        "db_writes": ["coupons", "bets", "decision_snapshots"],
        "can_trigger_enrichment": False,
    },
}

# ---------------------------------------------------------------------------
# Step → Agent configuration (enhanced with full context)
# ---------------------------------------------------------------------------
STEP_AGENT_CONFIG = {
    "s1_scan": {
        "agent": "bet-scanner",
        "task": "Verify 14-sport coverage, cross-validate fixtures ≥2 sources, check deep-link discovery yield, flag source failures, ensure ≥50 unique events",
        "required_input": ["scan_summary.json"],
        "output_metrics": ["total_events", "sports_covered", "source_failures", "deep_link_yield"],
        "detailed_instructions": [
            "1. Read scan_summary.json — check per-sport event counts",
            "2. Verify all 14 sports scanned: football, tennis, basketball, volleyball, baseball, hockey, handball, mma, esports, table_tennis, snooker, darts, padel, speedway",
            "3. Check source_health — any source with >3 consecutive failures needs flagging",
            "4. Verify deep-link discovery yield >20% (deep links found / seed URLs scanned)",
            "5. Cross-reference scan_results in DB — do fixtures appear from ≥2 sources?",
            "6. Flag: missing KEY sports, <50 total events, >20% source failure rate",
        ],
        "recovery_actions": [
            "If sport missing → suggest re-scan with extended timeout for that sport group",
            "If source dead → check source_health DB table, suggest fallback source from source-registry.md",
        ],
    },
    "s1e_shortlist": {
        "agent": "bet-scanner",
        "task": "Review shortlist for sport diversity (≥8 sports), KEY sport coverage (≥60% Football/Tennis/Basketball/Volleyball), verify ALL candidates included, flag missing major leagues",
        "required_input": ["{date}_s2_shortlist.json"],
        "output_metrics": ["total_candidates", "sport_distribution", "key_sport_pct", "missing_leagues"],
        "detailed_instructions": [
            "1. Load shortlist JSON — count candidates per sport",
            "2. Verify ≥8 distinct sports represented",
            "3. Calculate KEY sport percentage: (football+tennis+basketball+volleyball) / total ≥60%",
            "4. Check for §SCAN.7 tournament protection — are all active major tournaments represented?",
            "5. Verify §SCAN.8 minor league value — non-top-5 league events should have +6 boost",
            "6. Ensure NO artificial caps — all candidates from aggregate must flow through",
            "7. Check fixture_verified field — flag high unverified percentage",
        ],
        "recovery_actions": [
            "If <8 sports → re-run build_shortlist.py with --min-sports 8",
            "If missing tournament → check if scan captured it, may need targeted re-scan",
        ],
    },
    "s2_tipster": {
        "agent": "bet-scout",
        "task": "Read FULL tipster arguments, assess quality, check independence, discover angles stats missed, promote watchlist picks",
        "required_input": ["tipster_aggregation_{date}.json"],
        "output_metrics": ["tipster_count", "event_coverage", "consensus_picks"],
        "detailed_instructions": [
            "1. Read tipster aggregation — extract per-tipster picks with full reasoning",
            "2. Assess tipster quality: named expert > anonymous aggregate",
            "3. Check independence: ≥2 tipsters from different platforms agreeing = consensus",
            "4. Look for angles pure stats missed: tactical changes, managerial quotes, team news",
            "5. Identify watchlist picks that have tipster backing → promote to shortlist",
            "6. Flag picks where tipsters strongly disagree with statistical analysis",
        ],
    },
    "s2_5_enrich": {
        "agent": "bet-enricher",
        "task": "Review enrichment yield by sport and source, identify persistent data gaps, suggest alternative sources for failed enrichments, verify enriched data quality",
        "required_input": ["{date}_s2_shortlist.json"],
        "output_metrics": ["teams_attempted", "enriched_count", "partial_count", "failed_count", "source_breakdown"],
        "detailed_instructions": [
            "1. Review batch_enrich results — break down by sport and source",
            "2. For each failed enrichment: identify WHY (CAPTCHA? 404? empty page? parsing error?)",
            "3. Check if fallback sources were tried (Flashscore → Sofascore → ESPN)",
            "4. Validate enriched data quality: stat values within sport-normal ranges",
            "5. Cross-reference with DB: are team_form rows actually populated?",
            "6. For persistent gaps: suggest specific alternative URLs from source-registry.md",
        ],
        "recovery_actions": [
            "If Flashscore blocked → try Sofascore, then ESPN standings for US sports",
            "If sport has 0% enrichment → check if stat_keys are defined in SPORT_STAT_KEYS",
            "For niche sports (snooker, darts, speedway) → use specialist sources from bet-scanning-niche skill",
        ],
    },
    "s3_deep_stats": {
        "agent": "bet-statistician",
        "task": "Interpret safety scores, find edge mechanisms, fetch missing stats, write ANALYTICAL REASONING per candidate",
        "required_input": ["{date}_s3_deep_stats.json"],
        "output_metrics": ["candidates_analyzed", "avg_safety_score", "top_markets"],
        "detailed_instructions": [
            "1. For EACH candidate in s3_deep_stats.json:",
            "   a. Review ranking_result — which market has highest safety score?",
            "   b. Verify THREE-WAY CROSS-CHECK: L10 avg + H2H avg + L5 trend ALL support pick direction",
            "   c. Check §3.0c: does H2H data exist for the EXACT stat being bet?",
            "   d. Calculate ALL available stat markets — don't just take first acceptable one",
            "   e. For football: MUST evaluate ≥1 of corners/fouls/shots/cards markets",
            "2. Write ANALYTICAL REASONING per candidate — explain WHY the edge exists",
            "3. Flag candidates with <3 data points in any dimension (L10, H2H, L5)",
            "4. If stats missing → check team_form DB, then trigger enrich_team/enrich_h2h",
            "5. Cross-reference with league_profiles — is the team above/below league average?",
        ],
        "recovery_actions": [
            "If team_form empty → call enrich_team(team_name, sport)",
            "If H2H missing → call enrich_h2h(team_a, team_b, sport)",
            "If league_profiles empty → check if build_league_profiles.py has been run",
        ],
    },
    "s4_odds_eval": {
        "agent": "bet-valuator",
        "task": "Cross-validate pricing across sources, reason about mispricing, assess edge durability, calculate relative value",
        "required_input": ["{date}_s3_deep_stats.json"],
        "output_metrics": ["candidates_with_ev", "avg_ev", "ev_positive_count"],
        "detailed_instructions": [
            "1. For each candidate with safety_score > 0:",
            "   a. Check odds_history DB for available odds from multiple bookmakers",
            "   b. Check espn_predictions for ML probability baseline",
            "   c. Calculate EV = (hit_rate × odds) - 1 where hit_rate = safety_score/10",
            "   d. For stats-first mode: minimum_acceptable_odds = 1 / hit_rate",
            "   e. Check for drift: if odds moved >8% since last fetch → re-evaluate",
            "2. Cross-validate: do BetExplorer, OddsPortal, The-Odds-API agree within 5%?",
            "3. Assess edge durability: sharp money? public money? injury-driven?",
            "4. Apply Kelly 1/4 for suggested stake sizing",
            "5. Update analysis_results.stats_summary_json with ev, ev_source, odds via update_stats_summary()",
        ],
        "recovery_actions": [
            "If no odds available → flag for stats-first mode, calculate minimum acceptable odds",
            "If only 1 odds source → fetch_odds_api.py for cross-validation (costs 30 credits)",
        ],
    },
    "s5_context": {
        "agent": "bet-challenger",
        "task": "Assess REAL market impact of context flags, model motivation effects, identify compounding risk factors",
        "required_input": ["{date}_s3_deep_stats.json", "weather_{date}.json"],
        "output_metrics": ["weather_flags", "injury_flags", "motivation_adjustments"],
        "detailed_instructions": [
            "1. Read weather data — flag wind >30 km/h (outdoor sports), rain (corners impact), extreme heat",
            "2. Check injuries/suspensions — key player absence changes WHICH markets, not just ML",
            "3. Model motivation: tournament stage, relegation zone, dead rubber, derby, rest days",
            "4. Identify compounding risks: bad weather + key injury + away team + bad form = HIGH risk",
            "5. For EACH context flag: estimate market-specific impact (e.g., rain → corners likely ↑)",
            "6. Update analysis_results.stats_summary_json with context_flags via update_stats_summary()",
        ],
        "recovery_actions": [
            "If weather data missing → use fetch_weather.py for outdoor venues",
            "If injury data missing → scrape ESPN injury report via Playwright",
        ],
    },
    "s6_upset_risk": {
        "agent": "bet-challenger",
        "task": "Score upset risk with sport-specific contextual reasoning, apply Paradox Rule",
        "required_input": ["{date}_s3_deep_stats.json"],
        "output_metrics": ["high_risk_count", "medium_risk_count", "low_risk_count"],
        "detailed_instructions": [
            "1. For each candidate: run sport-specific upset risk checklist (§6 in sport protocols)",
            "2. Apply numerical thresholds per sport (e.g., tennis: surface mismatch +2, H2H losing record +3)",
            "3. Check Paradox Rule: heavy favorite (>1.30 odds) in low-motivation scenario → HIGH upset risk",
            "4. Cross-reference with team form trend — declining form = higher upset risk",
            "5. Score: LOW (0-3), MEDIUM (4-6), HIGH (7+) → store as upset_risk in stats_summary",
            "6. Instant red flags (§7.3): if triggered → automatic FLAGGED tier in gate",
        ],
    },
    "s7_gate": {
        "agent": "bet-challenger",
        "task": "Review advisory tier assignments, build qualitative bear cases, audit assumptions, find historical analogies, Bayesian-update confidence",
        "required_input": ["{date}_s7_gate_results.json"],
        "output_metrics": ["approved_count", "strong_count", "moderate_count", "weak_count", "rejected_count"],
        "detailed_instructions": [
            "1. Read gate_results — review tier assignments (STRONG/MODERATE/WEAK/FLAGGED)",
            "2. For STRONG picks: build BEAR CASE — what single event could kill this pick?",
            "3. For MODERATE picks: identify what would promote them to STRONG",
            "4. For WEAK/FLAGGED picks: are they unfairly penalized? Check if gate criteria are too strict",
            "5. Audit assumptions: is sample size adequate? Is H2H relevant? Is trend stable?",
            "6. Historical analogies: similar picks in betclic_bets_history.json — what happened?",
            "7. Bayesian update: combine statistical confidence with context/upset adjustments",
            "8. IMPORTANT: Advisory tiers are INFORMATIONAL — user decides. No auto-rejection.",
            "9. Verify ≥5 sports in approved picks per §7.6",
        ],
    },
    "s8_coupons": {
        "agent": "bet-builder",
        "task": "Review portfolio strategically, check hidden correlations, adjust stakes by conviction, V1-V10 + §S8.FINAL. Review DISCOVERY tier picks for promotion.",
        "required_input": ["{date}.json"],
        "output_metrics": ["coupon_count", "total_legs", "total_stake", "discovery_count"],
        "detailed_instructions": [
            "1. Build core coupons from STRONG+MODERATE picks — 1 event per coupon, max 8 legs",
            "2. Check hidden correlations: same league (weather/fixture congestion), same surface, same timezone",
            "3. Create COMBO MENU: 2-3 alternative combinations remixing the best picks",
            "4. Build EXTENDED POOL (discovery tier): WEAK/FLAGGED picks with EV>0 for user review",
            "5. Run coupon stress test (§8.2): simulate each leg failing — does coupon still make sense?",
            "6. Apply V1-V10 validation: V1(ID format), V2(no duplicate events), V3(odds check), V4(stake limits), V5(sport diversity), V6(correlation), V7(risk tier), V8(market validity), V9(arithmetic), V10(placement order)",
            "7. §S8.FINAL mechanical check: verify all arithmetic, cross-check safety scores vs gate results",
            "8. Assign risk tiers: LR(low risk), MS(medium safety), HR(high reward), N(neutral)",
            "9. Per-pick concentration: no single pick >25% of total stake",
            "10. Format output per betting-artifacts.instructions.md (Polish market names, coupon tables)",
        ],
    },
}


def _reviews_dir(date: str) -> Path:
    """Return the agent reviews directory for a given date, creating it if needed."""
    d = REVIEWS_DIR / date
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_step_output(date: str, step_id: str, metrics: dict, artifacts: list[str], step_config: dict | None = None):
    """Write structured agent input file after a pipeline step completes.

    The output JSON includes full agent context: task description, DB schema
    reference, self-healing tools, skills to load, and detailed step-by-step
    instructions so the agent is fully self-contained.

    Args:
        date: Betting date (YYYY-MM-DD).
        step_id: Pipeline step identifier (e.g. "s3_deep_stats").
        metrics: Key numeric metrics produced by the step.
        artifacts: List of file paths to full artifacts the agent should read.
        step_config: Override for STEP_AGENT_CONFIG entry. Uses default if None.
    """
    cfg = step_config or STEP_AGENT_CONFIG.get(step_id, {})
    agent_name = cfg.get("agent", "unknown")
    agent_skills = AGENT_SKILLS_MAP.get(agent_name, {})

    payload = {
        "step_id": step_id,
        "date": date,
        "agent": agent_name,
        "role": agent_skills.get("role", ""),
        "task": cfg.get("task", ""),
        "detailed_instructions": cfg.get("detailed_instructions", []),
        "recovery_actions": cfg.get("recovery_actions", []),
        "metrics": metrics,
        "artifacts": artifacts,
        "expected_output_metrics": cfg.get("output_metrics", []),
        # Agent awareness context
        "agent_context": {
            "responsibilities": agent_skills.get("responsibilities", []),
            "skills_to_load": agent_skills.get("skills_to_load", []),
            "instructions_to_follow": agent_skills.get("instructions_to_follow", []),
            "db_reads": agent_skills.get("db_reads", []),
            "db_writes": agent_skills.get("db_writes", []),
            "can_trigger_enrichment": agent_skills.get("can_trigger_enrichment", False),
            "enrichment_tools": agent_skills.get("enrichment_tools", []),
            "key_principle": agent_skills.get("key_principle", ""),
        },
        # DB access reference
        "db_reference": {
            "connection": DB_SCHEMA_REFERENCE["connection"],
            "relevant_tables": {
                k: v for table_group in DB_SCHEMA_REFERENCE
                if table_group.endswith("_tables")
                for k, v in DB_SCHEMA_REFERENCE[table_group].items()
                if k in agent_skills.get("db_reads", []) + agent_skills.get("db_writes", [])
            },
            "query_patterns": DB_SCHEMA_REFERENCE.get("key_query_patterns", {}),
        },
        # Self-healing tools available
        "self_healing": {
            "enrichment_agent": SELF_HEALING_REGISTRY["enrichment_agent"],
            "fallback_layers": SELF_HEALING_REGISTRY["fallback_layers"],
        } if agent_skills.get("can_trigger_enrichment") else {
            "note": "This agent does not trigger enrichment directly. Flag data gaps in review for upstream resolution.",
            "fallback_layers": SELF_HEALING_REGISTRY["fallback_layers"],
        },
        "written_at": datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(),
    }
    out_path = _reviews_dir(date) / f"{step_id}_input.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out_path)


def read_agent_review(date: str, step_id: str) -> dict | None:
    """Read agent review response if it exists.

    Returns None if no review file found (pipeline proceeds without agent input).
    """
    review_path = _reviews_dir(date) / f"{step_id}_review.json"
    if not review_path.exists():
        return None
    try:
        return json.loads(review_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def merge_agent_enrichments(state: dict, review: dict) -> dict:
    """Merge agent enrichments into pipeline state.

    The review dict is expected to have:
        - agent: str
        - step_id: str
        - status: "approved" | "flagged" | "enriched"
        - flags: list[str]
        - enrichments: dict
        - timestamp: str

    Enrichments are stored in state["agent_reviews"][step_id].
    Flags are appended to state["errors"] if status == "flagged".
    """
    step_id = review.get("step_id", "unknown")
    state.setdefault("agent_reviews", {})[step_id] = {
        "agent": review.get("agent", "unknown"),
        "status": review.get("status", "unknown"),
        "flags": review.get("flags", []),
        "enrichments": review.get("enrichments", {}),
        "timestamp": review.get("timestamp", ""),
    }

    # Surface agent flags as warnings (non-blocking)
    if review.get("status") == "flagged":
        for flag in review.get("flags", []):
            state.setdefault("errors", []).append(f"[agent:{step_id}] {flag}")

    return state
