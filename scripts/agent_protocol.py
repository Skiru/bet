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
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

try:
    from bet.config import get_tz
except ImportError:
    from zoneinfo import ZoneInfo
    get_tz = lambda: ZoneInfo("Europe/Warsaw")

REVIEWS_DIR = ROOT_DIR / "betting" / "data" / "agent_reviews"

# ---------------------------------------------------------------------------
# Mandatory agent behaviors — enforced for EVERY agent in EVERY step
# ---------------------------------------------------------------------------
MANDATORY_BEHAVIORS = {
    "sequential_thinking": (
        "Use sequentialthinking MCP for EVERY decision. THINK IN THE MIDDLE — "
        "when a script produces output, use sequential thinking to analyze results "
        "AS THEY ARRIVE. Scripts run 5-10 minutes; the thinking happens DURING "
        "analysis of output, not in wasted time before/after."
    ),
    "live_error_handling": (
        "If a script fails or produces unexpected output, diagnose the error "
        "immediately. Do NOT just report the error — fix it or try alternative approach."
    ),
    "data_validation": (
        "After every data fetch, validate: Is the data reasonable? Are stat values "
        "in expected ranges? Are there suspiciously many zeros or nulls?"
    ),
    "think_in_the_middle": (
        "When script output arrives: (1) Use sequentialthinking to deeply analyze "
        "the data, (2) Assess data quality, (3) Identify anomalies and gaps, "
        "(4) Decide next action with justification. Do NOT reason about expectations "
        "before a 5-10min script — reason about ACTUAL output when it arrives."
    ),
}

# ---------------------------------------------------------------------------
# Error handling protocol — structured recovery for common failures
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Reaction Patterns — structured failure → recovery mappings for agents
# ---------------------------------------------------------------------------
REACTION_PATTERNS = {
    "empty_output": {
        "trigger": "Script produces 0 candidates/events in output",
        "severity": "HIGH",
        "recovery": [
            "Check source_health DB table for blocked/failed sources",
            "Retry with alternative source or extended timeout",
            "If scan: re-run for specific sport with --sport flag",
        ],
        "escalation": "If retry also empty → escalate to user with source health report",
        "scripts_affected": ["discover_events.py", "build_shortlist.py", "deep_stats_report.py"],
    },
    "low_yield": {
        "trigger": "Enrichment/scan yield < 40% (successful / attempted)",
        "severity": "MEDIUM",
        "recovery": [
            "Trigger L3-L6 fallback enrichment for failed items",
            "Try alternative sources from source-registry.md",
            "Check if sport season ended (structural cause vs bug)",
        ],
        "escalation": "If yield still < 20% after all fallbacks → escalate to user",
        "scripts_affected": ["data_enrichment_agent.py", "discover_events.py"],
    },
    "missing_sport": {
        "trigger": "Expected sport has 0 events in scan/shortlist",
        "severity": "HIGH",
        "recovery": [
            "Re-scan that sport group only: discover_events.py --sports {sport}",
            "Check scan_urls.json for that sport's source URLs",
            "Verify sport season is active (not off-season)",
        ],
        "escalation": "If sport still missing after re-scan → check if season ended, inform user",
        "scripts_affected": ["discover_events.py", "build_shortlist.py"],
    },
    "exit_code_2": {
        "trigger": "Script exits with code 2 (critical failure)",
        "severity": "CRITICAL",
        "recovery": [
            "STOP pipeline — do NOT retry blindly",
            "Read error output carefully — identify root cause",
            "Check if --stop-on-error was set (stop_on_error flag in AgentOutput)",
        ],
        "escalation": "Immediate — show user the error and ask for guidance",
        "scripts_affected": ["all"],
    },
    "agent_summary_missing": {
        "trigger": "Script output has no AGENT_SUMMARY: line",
        "severity": "HIGH",
        "recovery": [
            "Script crashed before emitting summary — check exit code",
            "Read last 50 lines of output for Python tracebacks",
            "Check if script was run with --verbose (required for AGENT_SUMMARY)",
        ],
        "escalation": "If crash is in script logic → file bug. If data issue → fix data, retry.",
        "scripts_affected": ["all verbose-enabled scripts"],
    },
    "data_quality_mostly_minimal": {
        "trigger": ">50% of candidates have MINIMAL data quality (<4/10 data_quality_score)",
        "severity": "HIGH",
        "recovery": [
            "Enrichment failure — spawn web_research_agent.py (L7) for top-priority missing teams",
            "Check team_form DB table for empty rows",
            "Verify enrichment sources are responsive (source_health table)",
        ],
        "escalation": "If still >50% minimal after L7 → inform user, proceed with warnings",
        "scripts_affected": ["data_enrichment_agent.py", "deep_stats_report.py"],
    },
    "odds_drift": {
        "trigger": "Odds drifted >8% between API fetch and current value",
        "severity": "MEDIUM",
        "recovery": [
            "Mandatory EV re-evaluation with new odds",
            "Recalculate: EV = (hit_rate × new_odds) - 1",
            "If EV turns negative → move pick to extended pool",
        ],
        "escalation": "If EV negative → inform user, recommend SKIP",
        "scripts_affected": ["odds_evaluator.py", "fetch_odds_api.py"],
    },
    "db_connection_failure": {
        "trigger": "Cannot connect to betting.db or table missing",
        "severity": "CRITICAL",
        "recovery": [
            "Check betting/data/betting.db exists",
            "Verify DB schema with: python3 scripts/inspect_pipeline.py --step s0 --date {date}",
            "Fall back to JSON files if DB is corrupted",
        ],
        "escalation": "If DB corrupted → user must restore from backup",
        "scripts_affected": ["all DB-using scripts"],
    },
    "timeout_exceeded": {
        "trigger": "Script exceeds expected timeout (async mode returns before completion)",
        "severity": "MEDIUM",
        "recovery": [
            "Use get_terminal_output(id) to check if still progressing",
            "If progressing: wait longer (extend timeout mentally)",
            "If stuck on one item: may need to kill and retry with --sport filter",
        ],
        "escalation": "If hung >2x expected time → kill terminal, escalate to user",
        "scripts_affected": ["discover_events.py", "data_enrichment_agent.py", "deep_stats_report.py"],
    },
}

# ---------------------------------------------------------------------------
# Shared Utilities — canonical name matching for ALL pipeline scripts
# ---------------------------------------------------------------------------
SHARED_UTILITIES = {
    "name_matching": {
        "module": "from bet.utils import names_match, is_same_event",
        "names_match": "names_match(name_a, name_b, threshold=70) → float (0-100). Multi-strategy: alias resolution, token_sort_ratio, token_set_ratio, surname matching. Handles diacritics, emoji, abbreviations (NAVI→Natus Vincere, Spurs→Tottenham).",
        "is_same_event": "is_same_event(home_a, away_a, home_b, away_b, threshold=70) → bool. Uses names_match on both teams, tries normal + swapped home/away order.",
        "used_by": ["build_shortlist.py", "deep_stats_report.py", "generate_market_matrix.py", "coupon_builder.py", "gate_checker.py", "settle_on_finish.py", "odds_evaluator.py", "tipster_xref.py"],
        "note": "Discovery module (src/bet/discovery/dedup.py) uses its own DeduplicationEngine with threshold 85 + ±2h kickoff window for cross-source merging at scan time. Downstream pipeline scripts use is_same_event/names_match from bet.utils.",
    },
}

# ---------------------------------------------------------------------------
# Database Schema Reference — compact map for agent awareness
# ---------------------------------------------------------------------------
DB_SCHEMA_REFERENCE = {
    "connection": {
        "how": "from bet.db.connection import get_db; with get_db() as conn: ...",
        "db_path": "betting/data/betting.db (SQLite)",
        "repositories": "from bet.db.repositories import SportRepo, TeamRepo, FixtureRepo, CompetitionRepo, AnalysisResultRepo, StatsRepo, GateResultRepo, CouponRepo, PipelineRepo, OddsRepo, SourceHealthRepo, ScanResultRepo, AthleteRepo, StandingRepo, TipsterRepo",
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
        "league_profiles": "id, competition_id→competitions, stat_key, season, avg_value, median_value, std_dev, sample_size — league baselines for deviation analysis (also written by scrapers module)",
        "player_season_stats": "id, athlete_id→athletes, competition_id→competitions, season, games_played, games_started, minutes_played, stats_json, per_game_json, advanced_json, source — per-player season aggregates from scrapers module",
        "standings": "id, competition_id→competitions, team_id→teams, season, rank, wins/draws/losses, goals_for/against, form(last-5-string), home/away splits, streak",
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
        "fixture_sources": "id, fixture_id→fixtures, source(sofascore/odds-api/api-football), external_id, confidence, raw_data(JSON), fetched_at — cross-references from discovery module",
        "scraper_runs": "id, scraper_name, sport, target, status(running/success/failed), records_scraped/inserted/updated, error_message, started_at, finished_at, duration_seconds — operational tracking for scrapers module",
        "source_health": "id, source_name, last_success/failure, consecutive_failures, total_requests/failures, avg_response_ms — tracks source reliability",
        "tipster_picks": "id, betting_date, source_site, tipster_name, sport, event, home_team, away_team, competition, market, market_type, direction, odds, reasoning, accuracy_pct, confidence, stats_cited(JSON), fetch_time — individual tipster picks from Playwright DOM scraping",
        "tipster_consensus": "id, betting_date, event, sport, competition, home_team, away_team, total_tipsters, consensus_market, consensus_direction, agreement_pct, statistical_picks, outcome_picks, has_reasoning, tipster_sources(JSON), confidence_adj — aggregated consensus per event",
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
        "load_tipster_picks": "TipsterRepo(conn).get_picks_by_date(date) → list[TipsterPick] with reasoning, stats_cited",
        "load_tipster_consensus": "TipsterRepo(conn).get_consensus_by_date(date) → list[TipsterConsensus] with agreement_pct, tipster_sources",
        "load_tipster_for_event": "TipsterRepo(conn).get_picks_for_event(date, home, away) → list[TipsterPick] for specific match",
    },
}

# ---------------------------------------------------------------------------
# Extended Pool Contract
# ---------------------------------------------------------------------------
# The "Extended Pool" is the set of candidates that PASSED basic viability
# checks but FAILED the full gate (data quality < FULL, safety < threshold,
# or specific zero-tolerance rule triggered).
#
# Source: gate_checker.py → run_gate() returns:
#   {"approved": [...], "extended_pool": [...], "rejected": [...]}
#
# A candidate lands in extended_pool when:
#   - data_quality_score < 7/10 (MINIMAL quality) but event is real
#   - gate_score below approval threshold but EV > 0
#   - specific ZT rule triggered (e.g., ZT#3 over-sets H2H-BLIND)
#
# Downstream: coupon_builder.py reads gate_results["extended_pool"]
# and presents them as "ROZSZERZONY WYBÓR" (Watch List) with minimum
# acceptable odds (1/safety_score). User decides whether to bet.
#
# Bucket semantics are authoritative for pipeline flow. Risk/advisory labels
# (LR/MS/HR/N, STRONG/MODERATE-style commentary, etc.) remain candidate-level
# metadata and never replace approved / extended_pool / rejected.
#
# Extended Pool picks are NEVER auto-rejected (R3). They appear in the
# coupon file with full analysis for user review.

# ---------------------------------------------------------------------------
# Self-healing tools registry — data recovery mechanisms available to agents
# ---------------------------------------------------------------------------
SELF_HEALING_REGISTRY = {
    "enrichment_agent": {
        "module": "data_enrichment_agent",
        "functions": {
            "enrich_team": "Fetch L10/L5 stats for a single team from Flashscore→ESPN fallback. Args: (team_name, sport). Returns: {status, stats_found, source}. Saves to DB + JSON cache.",
            "enrich_h2h": "Fetch H2H stats between two teams from Flashscore. Args: (team_a, team_b, sport). Returns: {status, h2h_stats, meetings_found}. Saves to DB.",
            "batch_enrich": "Enrich multiple teams in parallel. Args: (teams=[{team, sport, missing}], max_workers=4). Thread-safe with rate limiting.",
            "_detect_missing_from_shortlist": "Auto-scan shortlist for teams without cached data. Args: (date_str). Returns: [{team, sport, missing}].",
        },
        "sources": ["Flashscore (primary, 2s rate limit)", "ESPN (fallback)", "scores24 (tertiary)"],
        "rate_limits": "Thread-safe _rate_lock, per-domain minimum intervals: flashscore=2s",
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
            "fetch_espn_odds": "Fetch ESPN standings, predictions, ATS/OU records. Saves to standings + espn_predictions DB tables. NOTE: ESPN API no longer returns odds data — use for stats/standings only.",
            "fetch_espn_standings": "Fetch ESPN standings, ATS/OU records, rosters. Saves to standings + team_ats_records + team_ou_records DB tables.",
        },
        "use_when": "Missing predictions, standings, or ATS/OU records for US sports (NFL, NBA, MLB, NHL, NCAA) or football. NOT for odds — ESPN odds API returns empty data.",
    },
    "api_stats": {
        "module": "fetch_api_stats",
        "description": "LEGACY — superseded by run_scrapers.py (S2.3) + data_enrichment_agent.py (S2.5). Uses old scripts/api_clients/ module. Do NOT call in pipeline.",
        "use_when": "DEPRECATED — use run_scrapers.py + data_enrichment_agent.py instead",
    },
    "tennis_enrichment": {
        "module": "enrich_tennis_stats",
        "description": "Deep tennis L10 form + H2H via ESPN API. H2H enrichment via get_h2h_athletes(). Saves to team_form DB.",
        "use_when": "Tennis candidates missing L10 form, H2H records, or serve/return stats",
    },
    "tennis_elo": {
        "module": "fetch_tennis_elo",
        "description": "Fetch/cache TennisAbstract Elo ratings (518 ATP + 542 WTA). Cache at stats_cache/tennis_elo/. lookup_tennis_elo() in compute_safety_scores reads this.",
        "use_when": "Before pipeline — Elo cache stale or missing. Adds +1 data quality score via has_elo.",
    },
    "odds_api": {
        "module": "fetch_odds_api",
        "description": "The Odds API — cross-bookmaker odds comparison. 30 credits/scan, 500/month free.",
        "use_when": "Need independent odds validation or missing odds for specific events",
    },
    "L7_web_research": {
        "module": "scripts.web_research_agent",
        "function": "research_missing_data",
        "trigger": "All L1-L6 fallbacks exhausted, data still missing",
        "description": "Search open web for missing H2H, injury, form, coach data. Tries Gemini Search Grounding (L7a) first, then SerpAPI+Playwright (L7b).",
        "rate_limit": "5 SerpAPI + 10 Playwright per run (Gemini uses separate budget via gemini_config.json)",
    },
    "gemini_research": {
        "module": "gemini_web_research",
        "functions": {
            "research_team": "Gemini Search Grounding for team data (H2H, injuries, form, coach). Args: (team, sport, data_types, opponent). Returns: list[WebResearchResult].",
            "research_event_context": "Full event context via Gemini. Args: (home_team, away_team, sport, competition). Returns: EventContextResult.",
        },
        "trigger": "L7a — primary web research before SerpAPI/Playwright",
        "use_when": "Missing team data after L1-L6 enrichment. Replaces SerpAPI as first-choice web search.",
        "rate_limit": "Shared daily_request_limit from config/gemini_config.json",
    },
    "gemini_tipster": {
        "module": "gemini_tipster_reader",
        "functions": {
            "read_tipster_page": "Read tipster URL via Gemini and extract structured picks. Args: (url, source_site, sport_filter, date_filter). Returns: TipsterPageResult.",
            "batch_read_tipster_sites": "Read multiple tipster sites. Args: (sites, date_str, sport_filter). Returns: list[TipsterPageResult].",
        },
        "trigger": "S1 tipster aggregation when --use-gemini flag is set",
        "use_when": "Tipster HTML parsing fails or returns low yield. Feature-flagged via --use-gemini on tipster_aggregator.py.",
    },
    "gemini_news": {
        "module": "gemini_news_enrichment",
        "functions": {
            "enrich_team_news": "Injury/news/coaching enrichment for a team. Args: (team, sport, date). Returns: NewsEnrichmentResult.",
            "batch_enrich_news": "Batch enrichment for multiple candidates. Args: (candidates, date, max_workers). Returns: list[NewsEnrichmentResult].",
            "save_news_to_db": "Persist enrichment results to team_news table. Args: (results, date). Returns: int (count saved).",
        },
        "trigger": "S2.5 news enrichment step or --news flag on data_enrichment_agent.py",
        "use_when": "Missing injury reports, coaching changes, morale data. Fills L2.5 gap between scan and deep stats.",
        "saves_to": ["team_news (DB)"],
    },
    "google_sports": {
        "module": "api_clients.google_sports_client",
        "functions": {
            "get_h2h_enrichment": "Fetch H2H data from Google Sports Knowledge Panel via SerpAPI. Args: (home_team, away_team, sport). Returns: GoogleSportsEnrichment with h2h_matches, team_kgmids, live_match_data.",
            "get_h2h_enrichment_and_save": "Fetch H2H + persist to DB (fixtures, team_form, teams). Same args + saves automatically.",
            "get_normalized_h2h": "Pipeline-compatible interface returning NormalizedFixture list. Args: (home_team, away_team, sport). Returns: list[NormalizedFixture].",
        },
        "trigger": "L3.5 — H2H enrichment after API-specific sources, before generic web research",
        "use_when": "Missing H2H data after sport-specific API calls. Works for ALL 5 sports. Budget: 15 queries/run, 250/month.",
        "saves_to": ["fixtures (DB)", "team_form (DB)", "teams (DB)", "betting/data/stats_cache/google-sports/ (file cache)"],
        "rate_limit": "250 SerpAPI searches/month, max 15 per pipeline run",
    },
    "fallback_layers": [
        "L1: Scan retry with extended timeout (pipeline auto-handles)",
        "L2: Parallel S1b enrichment (odds-api.io + weather + tipsters concurrently)",
        "L3: S2.5 batch enrichment via data_enrichment_agent (Flashscore/ESPN)",
        "L3.5: Google Sports H2H via SerpAPI (google_sports_client — all 5 sports, 15 queries/run)",
        "L4: S3 batch enrichment before analysis loop",
        "L5: S3 inline extract_team_stats/extract_h2h_stats fallback (per-candidate)",
        "L6: S5 inline context fetch (weather API + ESPN injury scrape)",
        "L7a: Gemini Search Grounding — web research via gemini_web_research (primary)",
        "L7b: SerpAPI search — fallback when Gemini budget exhausted or fails",
        "L7c: Playwright direct URL fetch — last resort for specific data sources",
    ],
}

# ---------------------------------------------------------------------------
# Agent skills & instructions map — what each agent role should load
# ---------------------------------------------------------------------------
AGENT_SKILLS_MAP = {
    "bet-scanner": {
        "role": "Scan verification & shortlist curation specialist",
        "mandatory_behaviors": MANDATORY_BEHAVIORS,
        "responsibilities": [
            "Verify 5-sport coverage across all scan sources (Football, Volleyball, Basketball, Tennis, Hockey)",
            "Cross-validate fixtures appear in ≥2 independent sources",
            "Check deep-link discovery yield and flag source failures",
            "Review shortlist for league diversity and data depth, ensure comprehensive league coverage per sport",
            "Verify ALL candidates included — NO artificial caps or auto-filtering",
            "Flag missing major leagues and tournaments (§SCAN.7 tournament protection)",
            "Flag missing major domestic leagues worldwide (§SCAN.9 — Brasileirão, MLS, Liga MX, CSL, J-League, K-League, Saudi Pro, ISL, etc.)",
            "Apply §SCAN.8 minor league value edge — never penalize 'obscure' events",
        ],
        "skills_to_load": [
            "bet-navigating-sources (source hierarchy, fallback chains, URL patterns)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§SCAN.7, §SCAN.8, §SCAN.9, §1.1-§1.8)",
        ],
        "db_reads": ["scan_results", "fixture_sources", "source_health", "fixtures", "competitions"],
        "db_writes": [],
        "can_trigger_enrichment": False,
    },
    "bet-scout": {
        "role": "Tipster cross-reference & consensus analyst (Playwright-based DOM scraping)",
        "mandatory_behaviors": MANDATORY_BEHAVIORS,
        "responsibilities": [
            "Read FULL tipster arguments from DB (reasoning column, stats_cited)",
            "Assess tipster quality: track record, reasoning depth, independence",
            "Discover analytical angles that pure stats might miss",
            "Identify consensus picks (≥2 independent tipsters agree)",
            "Promote watchlist picks with strong tipster backing",
            "Flag tipster picks that contradict statistical analysis",
            "Cross-reference tipster picks with shortlist via TipsterRepo",
        ],
        "skills_to_load": [
            "bet-navigating-sources (Tier B tipster sites, access patterns)",
        ],
        "instructions_to_follow": [
            "analysis-methodology.instructions.md (§2 tipster cross-reference)",
        ],
        "db_reads": ["tipster_picks", "tipster_consensus", "analysis_results", "fixtures"],
        "db_writes": [],
        "can_trigger_enrichment": False,
    },
    "bet-enricher": {
        "role": "Data quality guardian & self-healing enrichment specialist",
        "mandatory_behaviors": MANDATORY_BEHAVIORS,
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
        "mandatory_behaviors": MANDATORY_BEHAVIORS,
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
        "mandatory_behaviors": MANDATORY_BEHAVIORS,
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
        "mandatory_behaviors": MANDATORY_BEHAVIORS,
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
        "mandatory_behaviors": MANDATORY_BEHAVIORS,
        "responsibilities": [
            "Build core portfolio: unique event per coupon, max legs per config (default 4)",
            "Create COMBO MENU: extra combinations remixing approved picks",
            "Build EXTENDED POOL: EV>0 but gate-failed picks for user review",
            "Split by advisory tier: STRONG+MODERATE -> primary, WEAK/FLAGGED -> discovery",
            "Check hidden correlations between legs (same league, weather, surface)",
            "Run coupon stress test (§8.2) -- what if 1 leg fails?",
            "Apply V1-V10 validation suite + §S8.FINAL mechanical verification",
            "Assign risk tier labels: LR/MS/HR/N per coupon",
            "Adjust stakes by conviction -- higher conviction = closer to Kelly optimal",
            "Per-pick concentration limits -- no single pick >25% of stake",
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
    "bet-db-analyst": {
        "role": "Database specialist -- data quality, gap analysis, integrity checks",
        "mandatory_behaviors": MANDATORY_BEHAVIORS,
        "responsibilities": [
            "Run full table census -- row counts for all 28 tables",
            "Date-specific gap analysis -- fixtures without team_form, missing odds, etc.",
            "Source health monitoring -- flag sources with >20% failure rate",
            "Cross-table integrity checks -- orphaned records, missing foreign keys",
            "Pipeline state verification -- which steps ran, their status and metrics",
            "Recommend enrichment actions to fill data gaps",
        ],
        "skills_to_load": [
            "bet-querying-database (DB schema, repository classes, standard queries)",
        ],
        "instructions_to_follow": [],
        "db_reads": ["ALL 28 tables"],
        "db_writes": [],
        "can_trigger_enrichment": False,
    },
}

# ---------------------------------------------------------------------------
# Data Flow Contracts (R18) -- expected inputs/outputs per pipeline step
# ---------------------------------------------------------------------------
DATA_FLOW_CONTRACTS = {
    "s1_scan": {
        "depends_on": None,
        "requires": {
            "files": [],
            "db": [],
        },
        "produces": {
            "db": ["scan_results", "fixture_sources", "source_health", "fixtures"],
            "files": [
                "betting/data/{date}_s1_events.json",
                "betting/data/market_matrix_{date}.json",
            ],
        },
        "required_output_keys": {
            "{date}_s1_events.json": ["sports_scanned", "total_events"],
            "market_matrix_{date}.json": ["events"],
        },
    },
    "s1e_shortlist": {
        "depends_on": "s1_scan",
        "requires": {
            "files": ["betting/data/market_matrix_{date}.json"],
            "db": [],
        },
        "produces": {
            "db": ["pipeline_runs"],
            "files": ["betting/data/{date}_s2_shortlist.json"],
        },
        "required_output_keys": {
            "{date}_s2_shortlist.json": ["candidates"],
        },
        "source_of_truth": {
            "working_set": "betting/data/{date}_s2_shortlist.json",
            "ownership": "The shortlist JSON is the canonical candidate universe for S2-S8 until a later step writes a new artifact.",
        },
    },
    "s2_tipster": {
        "depends_on": "s1e_shortlist",
        "requires": {
            "files": [
                "betting/data/{date}_s2_shortlist.json",
                "betting/data/{date}_tipster_consensus.json",
            ],
            "db": [],
        },
        "produces": {
            "db": ["tipster_picks", "tipster_consensus"],
            "files": [
                "betting/data/{date}_tipster_consensus.json",
                "betting/data/{date}_tipster_consensus.md",
                "betting/data/{date}_s2_shortlist.json",
            ],
        },
        "required_output_keys": {
            "{date}_tipster_consensus.json": ["all_picks"],
            "{date}_s2_shortlist.json": ["candidates"],
        },
        "source_of_truth": {
            "working_set": "betting/data/{date}_s2_shortlist.json",
            "supporting_artifacts": [
                "betting/data/{date}_tipster_consensus.json",
                "betting/data/{date}_tipster_consensus.md",
            ],
            "ownership": "tipster_xref.py mutates shortlist candidates in place by adding tipster_support and tipster_count. Tipster consensus artifacts remain supporting evidence, not a second shortlist source of truth.",
        },
    },
    "s2_3_scrapers": {
        "depends_on": "s1e_shortlist",
        "requires": {
            "files": [],
            "db": [],
        },
        "produces": {
            "db": ["league_profiles", "player_season_stats", "match_stats", "scraper_runs"],
            "files": [],
        },
        "required_output_keys": {},
        "source_of_truth": {
            "working_set": "warehouse tables populated by run_scrapers.py",
            "ownership": "run_scrapers.py owns warehouse ingestion only. bridge_league_to_team_form.py and scraper_to_team_form.py own any projection from scraper data into team_form.",
        },
        "contract_notes": [
            "S2.3 warehouse success is not S3 readiness by itself; S2.5 must still verify shortlist-scoped team_form availability and rich coverage.",
        ],
    },
    "s2_5_enrich": {
        "depends_on": ["s2_tipster", "s2_3_scrapers"],
        "requires": {
            "files": ["betting/data/{date}_s2_shortlist.json"],
            "db": [],
        },
        "produces": {
            "db": ["team_form"],
            "files": [],
        },
        "required_output_keys": {},
        "source_of_truth": {
            "working_set": "team_form rows for shortlist teams plus shortlist-scoped rich coverage evidence",
            "supporting_artifacts": ["betting/data/stats_cache/{sport}/{team_slug}.json"],
            "ownership": "data_enrichment_agent.py owns the S3-ready team_form boundary. Scraper warehouse tables are upstream inputs, not the final readiness boundary.",
        },
    },
    "s3_deep_stats": {
        "depends_on": "s2_5_enrich",
        "requires": {
            "files": ["betting/data/{date}_s2_shortlist.json"],
            "db": ["team_form"],
        },
        "produces": {
            "db": ["analysis_results", "analysis_raw_data"],
            "files": ["betting/data/{date}_s3_deep_stats.json"],
        },
        "required_output_keys": {
            "{date}_s3_deep_stats.json": [
                "analyses", "date", "total_candidates",
                "candidates_with_data",
            ],
        },
        "source_of_truth": {
            "working_set": "betting/data/{date}_s3_deep_stats.json plus analysis_results/analysis_raw_data keyed by fixture_id",
            "ownership": "The S3 JSON preserves the full shortlist-derived candidate universe. DB rows may be narrower and must not silently replace the JSON working set downstream.",
        },
    },
    "s4_odds_eval": {
        "depends_on": "s3_deep_stats",
        "requires": {
            "files": ["betting/data/{date}_s3_deep_stats.json"],
            "db": ["analysis_results"],
        },
        "produces": {
            "db": ["analysis_results"],
            "files": [],
        },
        "required_output_keys": {},
        "source_of_truth": {
            "working_set": "analysis_results.stats_summary_json ev / odds / ev_source fields",
            "ownership": "odds_evaluator.py updates stats_summary_json via update_stats_summary(); it augments S3 output instead of replacing ranking_json or the S3 JSON working set.",
        },
    },
    "s5_context": {
        "depends_on": "s4_odds_eval",
        "requires": {
            "files": ["betting/data/{date}_s3_deep_stats.json"],
            "db": ["analysis_results"],
        },
        "produces": {
            "db": ["analysis_results"],
            "files": [],
        },
        "required_output_keys": {},
        "source_of_truth": {
            "working_set": "analysis_results.stats_summary_json.context_flags",
            "ownership": "context_checks.py appends context flags via update_stats_summary() without changing the S3 candidate universe.",
        },
    },
    "s6_upset_risk": {
        "depends_on": "s5_context",
        "requires": {
            "files": ["betting/data/{date}_s3_deep_stats.json"],
            "db": ["analysis_results"],
        },
        "produces": {
            "db": ["analysis_results"],
            "files": [],
        },
        "required_output_keys": {},
        "source_of_truth": {
            "working_set": "analysis_results.stats_summary_json.upset_risk",
            "ownership": "upset_risk.py appends upset-risk fields via update_stats_summary() without changing the S3 candidate universe.",
        },
    },
    "s5_s6_context_upset": {
        "depends_on": "s4_odds_eval",
        "requires": {
            "files": ["betting/data/{date}_s3_deep_stats.json"],
            "db": ["analysis_results"],
        },
        "produces": {
            "db": ["analysis_results"],
            "files": [],
        },
        "required_output_keys": {},
        "contract_notes": [
            "Legacy combined alias for tooling that still reasons about S5 and S6 together. Canonical per-script contracts are s5_context and s6_upset_risk.",
        ],
    },
    "s7_gate": {
        "depends_on": "s6_upset_risk",
        "requires": {
            "files": ["betting/data/{date}_s3_deep_stats.json"],
            "db": ["analysis_results"],
        },
        "produces": {
            "db": ["gate_results"],
            "files": ["betting/data/{date}_s7_gate_results.json"],
        },
        "required_output_keys": {
            "{date}_s7_gate_results.json": ["gate_results", "summary"],
        },
        "source_of_truth": {
            "working_set": "gate_results DB rows and betting/data/{date}_s7_gate_results.json",
            "buckets": ["approved", "extended_pool", "rejected"],
            "ownership": "These three buckets are the authoritative S7 handoff to S7.5/S7.6/S8. risk_tier and other advisory labels stay inside candidates as metadata.",
        },
    },
    "s7_5_betclic": {
        "depends_on": "s7_gate",
        "requires": {
            "files": ["betting/data/{date}_s7_gate_results.json"],
            "db": ["gate_results"],
        },
        "produces": {
            "db": ["betclic_markets"],
            "files": ["betting/data/betclic_market_validation_{date}.json"],
        },
        "required_output_keys": {
            "betclic_market_validation_{date}.json": ["summary", "events"],
        },
        "source_of_truth": {
            "working_set": "betting/data/betclic_market_validation_{date}.json",
            "ownership": "validate_betclic_markets.py writes the canonical S7.5 sidecar. coupon_builder.py consumes that file and records consumption in pre_coupon_controls.",
        },
    },
    "s7_6_repeats": {
        "depends_on": "s7_5_betclic",
        "requires": {
            "files": ["betting/data/{date}_s7_gate_results.json"],
            "db": ["gate_results"],
        },
        "produces": {
            "db": ["pipeline_runs"],
            "files": ["betting/data/repeat_loss_handoff_{date}.json"],
        },
        "required_output_keys": {
            "repeat_loss_handoff_{date}.json": ["date", "step", "repeat_loss_count", "findings", "artifact_path"],
        },
        "source_of_truth": {
            "working_set": "pipeline_runs[s7_6_repeat_loss_check].stats",
            "supporting_artifacts": ["betting/data/repeat_loss_handoff_{date}.json"],
            "ownership": "check_48h_repeats.py persists the durable S7.6 handoff in pipeline_runs and mirrors it to a same-day JSON artifact. coupon_builder.py consumes the DB handoff and records consumption in pre_coupon_controls.",
        },
    },
    "s8_coupons": {
        "depends_on": ["s7_5_betclic", "s7_6_repeats"],
        "requires": {
            "files": [
                "betting/data/{date}_s7_gate_results.json",
                # Optional with --skip-betclic-validation flag:
                "betting/data/betclic_market_validation_{date}.json",
                "betting/data/repeat_loss_handoff_{date}.json",
            ],
            "db": ["gate_results"],
            "skip_flag": "--skip-betclic-validation skips both S7.5/S7.6 sidecars (all picks remain CONDITIONAL per R8)",
        },
        "produces": {
            "db": ["coupons", "bets", "decision_snapshots"],
            "files": [
                "betting/coupons/{date}.md",
                "betting/coupons/{date}.json",
            ],
        },
        "required_output_keys": {
            "{date}.json": ["summary", "pre_coupon_controls"],
        },
        "source_of_truth": {
            "working_set": "betting/coupons/{date}.json + betting/coupons/{date}.md",
            "ownership": "coupon_builder.py consumes approved/extended_pool/rejected buckets plus S7.5/S7.6 controls, then records pre_coupon_controls and build summary in the coupon JSON.",
        },
    },
    "s9_validate": {
        "depends_on": "s8_coupons",
        "requires": {
            "files": ["betting/coupons/{date}.md"],
            "db": [],
        },
        "produces": {
            "db": [],
            "files": [],
        },
        "required_output_keys": {},
        "source_of_truth": {
            "working_set": "validate_coupons.py AGENT_SUMMARY and exit code",
            "ownership": "S9 is a validation-only step. No persisted artifact is guaranteed, so downstream checks should consume stdout/AGENT_SUMMARY or rerun validation.",
        },
    },
    "s10_output": {
        "depends_on": "s9_validate",
        "requires": {
            "files": [
                "betting/coupons/{date}.md",
                "betting/coupons/{date}.json",
            ],
            "db": [],
        },
        "produces": {
            "db": [],
            "files": ["betting/coupons/pdf/{date}/coupon-{date}-full.pdf"],
        },
        "required_output_keys": {},
        "source_of_truth": {
            "working_set": "betting/coupons/pdf/{date}/",
            "ownership": "generate_coupon_pdf.py writes full, section, and quick-reference PDFs under the date-scoped output directory. S10 is file-existence based because the script does not emit AGENT_SUMMARY.",
        },
    },
}

# Backward-compatible aliases for older step ids and emitted summary step names.
DATA_FLOW_CONTRACTS.update({
    "s2_xref": DATA_FLOW_CONTRACTS["s2_tipster"],
    "s2_enrich": DATA_FLOW_CONTRACTS["s2_5_enrich"],
    "s3_deep": DATA_FLOW_CONTRACTS["s3_deep_stats"],
    "s4_odds": DATA_FLOW_CONTRACTS["s4_odds_eval"],
    "s7_6_repeat_loss_check": DATA_FLOW_CONTRACTS["s7_6_repeats"],
    "s8_coupon": DATA_FLOW_CONTRACTS["s8_coupons"],
    "s8_validate_coupons": DATA_FLOW_CONTRACTS["s9_validate"],
})

# ---------------------------------------------------------------------------
# THINK-WHILE-WAITING — concrete queries for productive async work per agent
# ---------------------------------------------------------------------------
THINK_WHILE_WAITING_QUERIES = {
    "bet-scanner": {
        "description": "While discover_events.py runs (~30s), review previous scan data and source health",
        "tasks": [
            {
                "label": "Source health overview",
                "type": "sql",
                "query": "SELECT source_name, total_requests, total_failures, ROUND(total_failures*100.0/MAX(total_requests,1),1) as fail_pct FROM source_health ORDER BY total_requests DESC LIMIT 10",
                "purpose": "Identify which sources are reliable vs failing — adjust expectations for scan results",
            },
            {
                "label": "Previous scan sport distribution",
                "type": "sql",
                "query": "SELECT sport, COUNT(*) as cnt FROM scan_results WHERE betting_date='{prev_date}' GROUP BY sport ORDER BY cnt DESC",
                "purpose": "Compare today's scan against yesterday's baseline — detect coverage drops",
            },
            {
                "label": "Active tournaments in fixtures",
                "type": "sql",
                "query": "SELECT DISTINCT competition FROM fixtures WHERE date(kickoff)='{date}' AND (competition LIKE '%Champions%' OR competition LIKE '%World%' OR competition LIKE '%Grand Slam%' OR competition LIKE '%Europa%' OR competition LIKE '%Copa%')",
                "purpose": "Verify tournament protection (R7) — are major tournaments captured?",
            },
        ],
    },
    "bet-enricher": {
        "description": "While data_enrichment_agent.py runs (~10 min), review shortlist quality and existing data",
        "tasks": [
            {
                "label": "Shortlist sport distribution",
                "type": "file",
                "path": "betting/data/{date}_s2_shortlist.json",
                "action": "Count candidates per sport, identify sports with most candidates needing enrichment",
                "purpose": "Prioritize which sport's enrichment results to check first",
            },
            {
                "label": "Existing team_form coverage",
                "type": "sql",
                "query": "SELECT s.name as sport, COUNT(DISTINCT tf.team_name) as teams FROM team_form tf JOIN sports s ON tf.sport_id=s.id GROUP BY s.name ORDER BY teams DESC",
                "purpose": "Know baseline coverage before enrichment — what % improvement did enrichment add?",
            },
            {
                "label": "Source failure patterns",
                "type": "sql",
                "query": "SELECT source_name, consecutive_failures, last_failure FROM source_health WHERE consecutive_failures > 0 ORDER BY consecutive_failures DESC LIMIT 5",
                "purpose": "If a source has consecutive failures, enrichment likely failed for those teams — prepare fallback plan",
            },
        ],
    },
    "bet-statistician": {
        "description": "While deep_stats_report.py runs (~10 min), review enrichment quality and pre-load sport context",
        "tasks": [
            {
                "label": "Enrichment data quality check",
                "type": "sql",
                "query": "SELECT sport_id, stat_key, COUNT(*) as cnt, AVG(l10_avg) as avg_val FROM team_form GROUP BY sport_id, stat_key ORDER BY sport_id, cnt DESC",
                "purpose": "Understand which stat keys have deepest data — prioritize markets with most evidence",
            },
            {
                "label": "League baselines available",
                "type": "sql",
                "query": "SELECT c.name, lp.stat_key, lp.avg_value, lp.sample_size FROM league_profiles lp JOIN competitions c ON lp.competition_id=c.id WHERE lp.sample_size >= 10 ORDER BY lp.sample_size DESC LIMIT 20",
                "purpose": "Know which leagues have reliable baselines for deviation analysis in S3",
            },
            {
                "label": "Previous day's top safety scores",
                "type": "sql",
                "query": "SELECT home_team, away_team, best_market_name, best_safety_score FROM analysis_results WHERE betting_date='{prev_date}' AND best_safety_score > 6 ORDER BY best_safety_score DESC LIMIT 10",
                "purpose": "Calibrate today's scores against yesterday's — are we seeing similar ranges?",
            },
        ],
    },
    "bet-valuator": {
        "description": "While odds_evaluator.py runs (~5 min), review S3 stats and prepare EV framework",
        "tasks": [
            {
                "label": "Top safety scores from S3",
                "type": "sql",
                "query": "SELECT home_team, away_team, best_market_name, best_safety_score, markets_evaluated FROM analysis_results WHERE betting_date='{date}' AND best_safety_score > 5 ORDER BY best_safety_score DESC LIMIT 15",
                "purpose": "Pre-identify strongest statistical edges — focus EV analysis on these first",
            },
            {
                "label": "Available odds data",
                "type": "sql",
                "query": "SELECT bookmaker, COUNT(*) as cnt FROM odds_history WHERE fetched_at > datetime('now', '-24 hours') GROUP BY bookmaker ORDER BY cnt DESC",
                "purpose": "Know which bookmakers have odds loaded — determines cross-validation depth",
            },
        ],
    },
    "bet-challenger": {
        "description": "While context_checks.py / upset_risk.py run (~5 min each), review deep stats for bear case prep",
        "tasks": [
            {
                "label": "Candidates with high safety but few markets",
                "type": "sql",
                "query": "SELECT home_team, away_team, best_safety_score, markets_evaluated FROM analysis_results WHERE betting_date='{date}' AND best_safety_score > 7 AND markets_evaluated < 3",
                "purpose": "High safety + few markets = narrow analysis — these need extra scrutiny in gate",
            },
            {
                "label": "Standings context for upset risk",
                "type": "sql",
                "query": "SELECT t.name, s.rank, s.form, s.streak FROM standings s JOIN teams t ON s.team_id=t.id WHERE s.season LIKE '%2025%' OR s.season LIKE '%2026%' ORDER BY s.rank ASC LIMIT 20",
                "purpose": "Know team league positions for motivation analysis — top vs bottom, playoff contender vs relegated",
            },
        ],
    },
    "bet-scout": {
        "description": "While tipster_aggregator.py runs (~5 min), review scan data for coverage gaps",
        "tasks": [
            {
                "label": "Events with most sources",
                "type": "sql",
                "query": "SELECT home_team, away_team, sport, COUNT(DISTINCT source_domain) as sources FROM scan_results WHERE betting_date='{date}' GROUP BY home_team, away_team HAVING sources >= 2 ORDER BY sources DESC LIMIT 10",
                "purpose": "Events covered by multiple sources = higher data confidence for tipster cross-ref",
            },
            {
                "label": "Check pre-fetched HTML snapshots",
                "type": "file",
                "path": "betting/data/html_snapshots/",
                "action": "List available domain snapshots — know which tipster sites have cached data",
                "purpose": "Understand tipster data availability before aggregation results arrive",
            },
        ],
    },
    "bet-builder": {
        "description": "While coupon_builder.py runs (~5 min), review gate results and bankroll",
        "tasks": [
            {
                "label": "Gate result distribution",
                "type": "sql",
                "query": "SELECT status, COUNT(*) as cnt FROM gate_results WHERE betting_date='{date}' GROUP BY status ORDER BY cnt DESC",
                "purpose": "Know approved/extended/rejected counts — prepare portfolio strategy",
            },
            {
                "label": "Current bankroll and limits",
                "type": "file",
                "path": "config/betting_config.json",
                "action": "Read bankroll, daily_budget_min, daily_budget_max, max_legs_per_coupon",
                "purpose": "Set stake constraints before seeing coupon builder output",
            },
            {
                "label": "Recent coupon performance",
                "type": "sql",
                "query": "SELECT coupon_type, COUNT(*) as cnt, SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins, SUM(pnl_pln) as total_pnl FROM coupons WHERE created_at > datetime('now', '-7 days') GROUP BY coupon_type",
                "purpose": "Last 7 days performance by coupon type — inform today's coupon strategy",
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# Structured Output Protocol (R19) -- agent_output.py integration
# ---------------------------------------------------------------------------
STRUCTURED_OUTPUT_PROTOCOL = {
    "description": (
        "The readiness flow has three output modes: AgentOutput-backed scripts emit "
        "the canonical AGENT_SUMMARY payload, manual emitters still print AGENT_SUMMARY "
        "with script-specific flat fields, and S10 is verified by output files because "
        "generate_coupon_pdf.py does not emit AGENT_SUMMARY."
    ),
    "flags": {
        "--verbose / -v": "JSON-line events for AgentOutput-backed scripts and debug logging for some manual emitters",
        "--stop-on-error": "Halt on first critical error (exit code 2) instead of log-and-continue",
        "--sports SPORT": "Filter to sport list (discover_events.py: comma-separated; tipster_aggregator.py: --sport single)",
    },
    "agent_summary_format": {
        "_scope": "Applies only to scripts listed under agent_output_scripts",
        "step": "Script/step identifier (e.g. 'discover_events', 'gate_checker')",
        "verdict": "OK | PARTIAL | FAILED | NO_BET",
        "metrics": "Dict of step-specific counts and rates",
        "issues": "List of {level, message, ...} dicts (level: warning|error|critical)",
        "counts": "Dict with 'errors' and 'warnings' integer counts",
        "ts": "ISO 8601 timestamp of summary generation",
    },
    "exit_codes": {
        0: "Success — all operations completed normally or a valid NO_BET path was reached",
        1: "Partial/degraded or business-rule stop — results are usable but require attention",
        2: "Critical failure — stop-on-error triggered, output unreliable",
    },
    "agent_output_scripts": [
        "build_shortlist.py", "tipster_aggregator.py", "tipster_xref.py",
        "data_enrichment_agent.py", "deep_stats_report.py", "odds_evaluator.py",
        "context_checks.py", "upset_risk.py", "gate_checker.py",
        "check_48h_repeats.py", "coupon_builder.py", "validate_coupons.py",
        "inspect_pipeline.py", "fetch_odds_api.py", "fetch_odds_multi.py",
        "ingest_scan_stats.py", "parse_betclic_html.py",
    ],
    "scripts_with_verbose": [
        "build_shortlist.py", "tipster_aggregator.py", "tipster_xref.py",
        "data_enrichment_agent.py", "deep_stats_report.py", "odds_evaluator.py",
        "context_checks.py", "upset_risk.py", "gate_checker.py",
        "check_48h_repeats.py", "coupon_builder.py", "validate_coupons.py",
        "inspect_pipeline.py", "fetch_odds_api.py", "fetch_odds_multi.py",
        "ingest_scan_stats.py", "parse_betclic_html.py",
    ],
    "manual_summary_scripts": [
        "discover_events.py", "run_scrapers.py", "validate_betclic_markets.py",
    ],
    "no_summary_scripts": [
        "generate_coupon_pdf.py",
    ],
    "script_inventory": {
        "discover_events.py": {
            "emitter": "manual_agent_summary",
            "contract_step": "s1_scan",
            "summary_step": None,
            "summary_fields": ["verdict", "total_discovered", "total_after_dedup", "by_sport", "sources", "issues_count"],
        },
        "build_shortlist.py": {
            "emitter": "AgentOutput",
            "contract_step": "s1e_shortlist",
            "summary_step": "s1e_shortlist",
        },
        "tipster_aggregator.py": {
            "emitter": "AgentOutput",
            "contract_step": "s2_tipster",
            "summary_step": "s2_tipster",
        },
        "tipster_xref.py": {
            "emitter": "AgentOutput",
            "contract_step": "s2_tipster",
            "summary_step": "s2_xref",
            "notes": "Mutates betting/data/{date}_s2_shortlist.json in place with tipster_support and tipster_count.",
        },
        "run_scrapers.py": {
            "emitter": "manual_agent_summary",
            "contract_step": "s2_3_scrapers",
            "summary_step": None,
            "summary_fields": ["verdict", "scrapers_run", "scrapers_failed", "failed_sources", "results"],
        },
        "data_enrichment_agent.py": {
            "emitter": "AgentOutput",
            "contract_step": "s2_5_enrich",
            "summary_step": "s2_enrich",
        },
        "deep_stats_report.py": {
            "emitter": "AgentOutput",
            "contract_step": "s3_deep_stats",
            "summary_step": "s3_deep",
        },
        "odds_evaluator.py": {
            "emitter": "AgentOutput",
            "contract_step": "s4_odds_eval",
            "summary_step": "s4_odds_eval",
        },
        "context_checks.py": {
            "emitter": "AgentOutput",
            "contract_step": "s5_context",
            "summary_step": "s5_context",
        },
        "upset_risk.py": {
            "emitter": "AgentOutput",
            "contract_step": "s6_upset_risk",
            "summary_step": "s6_upset_risk",
        },
        "gate_checker.py": {
            "emitter": "AgentOutput",
            "contract_step": "s7_gate",
            "summary_step": "s7_gate",
        },
        "validate_betclic_markets.py": {
            "emitter": "manual_agent_summary",
            "contract_step": "s7_5_betclic",
            "summary_step": None,
            "summary_fields": ["verdict", "total_events", "with_stats", "without_stats", "unavailable_picks", "output"],
        },
        "check_48h_repeats.py": {
            "emitter": "AgentOutput",
            "contract_step": "s7_6_repeats",
            "summary_step": "s7_6_repeats",
        },
        "coupon_builder.py": {
            "emitter": "AgentOutput",
            "contract_step": "s8_coupons",
            "summary_step": "s8_coupon",
            "notes": "NO_BET is a valid verdict when approved picks are exhausted or pre-coupon controls exclude the build universe.",
        },
        "validate_coupons.py": {
            "emitter": "AgentOutput",
            "contract_step": "s9_validate",
            "summary_step": "s8_validate_coupons",
        },
        "generate_coupon_pdf.py": {
            "emitter": "none",
            "contract_step": "s10_output",
            "summary_step": None,
            "notes": "Verify file outputs under betting/coupons/pdf/{date}/ instead of waiting for AGENT_SUMMARY.",
        },
    },
    "parsing_instructions": (
        "Use script_inventory to decide how to parse a script's result. For AgentOutput-backed "
        "scripts, parse the JSON after 'AGENT_SUMMARY:' and read verdict, metrics, issues, and counts. "
        "Treat NO_BET as a valid business outcome rather than a protocol error. For manual emitters, "
        "parse the documented flat fields instead of assuming a metrics wrapper. For S10, verify files "
        "under betting/coupons/pdf/{date}/ because there is no AGENT_SUMMARY contract."
    ),
}

# ---------------------------------------------------------------------------
# Canonical Pipeline Steps — script mapping (single source of truth)
# ---------------------------------------------------------------------------
PIPELINE_STEPS = {
    "S0": {"script": "settle_on_finish.py + evaluate_decisions.py + analyze_betclic_learning.py", "description": "Settlement, decision review, and Betclic learning prerequisite"},
    "S1": {"script": "discover_events.py", "description": "Multi-source event discovery"},
    "S1.5": {"script": "build_shortlist.py", "description": "Shortlist construction + stats-first scoring"},
    "S2": {"script": "tipster_aggregator.py + tipster_xref.py", "description": "Tipster consensus plus in-place shortlist mutation"},
    "S2.3": {"script": "run_scrapers.py", "description": "Warehouse scrapers; bridge scripts own any projection into team_form"},
    "S2.5": {"script": "data_enrichment_agent.py", "description": "Shortlist-scoped team_form enrichment + rich-coverage readiness"},
    "S2T": {"script": "tipster_aggregator.py + tipster_xref.py", "description": "Legacy alias for the S2 tipster flow"},
    "S3": {"script": "deep_stats_report.py", "description": "Deep statistical analysis per candidate"},
    "S4": {"script": "odds_evaluator.py", "description": "Odds injection + EV calculation into stats_summary_json"},
    "S5": {"script": "context_checks.py", "description": "Context flags appended to stats_summary_json"},
    "S6": {"script": "upset_risk.py", "description": "Upset-risk scoring appended to stats_summary_json"},
    "S7": {"script": "gate_checker.py", "description": "18-point gate → approved / extended_pool / rejected"},
    "S7.5": {"script": "validate_betclic_markets.py", "description": "Betclic market validation sidecar"},
    "S7.6": {"script": "check_48h_repeats.py", "description": "Repeat-loss durable handoff + same-day artifact"},
    "S8": {"script": "coupon_builder.py", "description": "Portfolio construction + coupon artifacts + pre_coupon_controls"},
    "S9": {"script": "validate_coupons.py", "description": "Coupon structural validation"},
    "S10": {"script": "generate_coupon_pdf.py", "description": "Final PDF output (file-based verification)"},
}

# ---------------------------------------------------------------------------
# Agent Invocation Map — when/what each specialist agent receives (Task 4.4)
# ---------------------------------------------------------------------------
AGENT_INVOCATION_MAP = {
    "bet-scanner": {
        "trigger": "S1 complete",
        "receives": "s1_events.json (discovered fixtures)",
        "produces": "scan verdict: coverage gaps, source failures, fixture count",
    },
    "bet-enricher": {
        "trigger": "S2.5 complete (after S2 || S2.3)",
        "receives": "run_scrapers warehouse summary plus shortlist-scoped team_form/rich-coverage results",
        "produces": "readiness verdict: warehouse vs team_form coverage, bridge visibility, stale teams, source health",
    },
    "bet-scout": {
        "trigger": "S2 complete",
        "receives": "tipster consensus plus mutated shortlist tipster_support/tipster_count",
        "produces": "tipster analysis: consensus strength, shortlist mutations, contrarian angles",
    },
    "bet-statistician": {
        "trigger": "S3 complete",
        "receives": "deep_stats analysis (safety scores, market rankings)",
        "produces": "market rankings review: best bets, H2H validation, risk flags",
    },
    "bet-valuator": {
        "trigger": "S4 complete",
        "receives": "odds evaluation (EV, Kelly, price gaps)",
        "produces": "EV/drift verdict: value bets, line movements, sharp action",
    },
    "bet-challenger": {
        "trigger": "S5+S6 complete",
        "receives": "context + upset risk data",
        "produces": "bear cases: why picks might fail, upset scenarios",
    },
    "bet-gatekeeper": {
        "trigger": "S7 complete",
        "receives": "gate_results (approved/extended/rejected counts)",
        "produces": "gate audit: borderline decisions, override suggestions",
    },
    "bet-portfolio": {
        "trigger": "S8 complete (after S7.5 + S7.6)",
        "receives": "coupon data (core, combos, singles, budget, pre_coupon_controls)",
        "produces": "portfolio quality: concentration, correlation, diversity, control-consumption audit",
    },
}

# ---------------------------------------------------------------------------
# Step → Agent configuration (enhanced with full context)
# ---------------------------------------------------------------------------
STEP_AGENT_CONFIG = {
    "s1_scan": {
        "agent": "bet-scanner",
        "task": "Verify 5-sport coverage (Football, Volleyball, Basketball, Tennis, Hockey), cross-validate fixtures ≥2 sources, check source diversity, flag source failures, ensure ≥50 unique events",
        "required_input": ["{date}_s1_events.json"],
        "output_metrics": ["total_events", "sports_covered", "source_failures", "dedup_merges"],
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
        "detailed_instructions": [
            "1. Read {date}_s1_events.json — check per-sport event counts",
            "2. Verify all 5 sports scanned: football, tennis, basketball, volleyball, hockey",
            "3. Check source stats — SofaScore, Odds API, API-Football response status",
            "4. Verify dedup quality: 3-5% merges expected, >10% may indicate matching issues",
            "5. Cross-reference fixture_sources in DB — do fixtures appear from ≥2 sources?",
            "6. Flag: missing KEY sports, <50 total events, any source with 0 events",
        ],
        "recovery_actions": [
            "If sport missing → suggest re-scan with --sports filter for that sport",
            "If source dead → check API key config, suggest fallback source from source-registry.md",
        ],
    },
    "s1e_shortlist": {
        "agent": "bet-scanner",
        "task": "Review shortlist for league diversity and data depth, comprehensive league coverage, verify ALL candidates included, flag missing major leagues",
        "required_input": ["{date}_s2_shortlist.json"],
        "output_metrics": ["total_candidates", "sport_distribution", "key_sport_pct", "missing_leagues"],
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
        "detailed_instructions": [
            "1. Load shortlist JSON — count candidates per sport",
            "2. Verify all 5 sports represented (football, volleyball, basketball, tennis, hockey)",
            "3. Verify all 5 sports have adequate league representation; flag any sport with <3 leagues",
            "4. Check for §SCAN.7 tournament protection — are all active major tournaments represented?",
            "5. Verify §SCAN.8 minor league value — non-top-5 league events should have +6 boost",
            "6. Check for §SCAN.9 major domestic league protection — are Brasileirão, MLS, Liga MX, CSL, J-League, K-League, Saudi Pro League present when active?",
            "7. Ensure NO artificial caps — all candidates from aggregate must flow through",
            "8. Check fixture_verified field — flag high unverified percentage",
        ],
        "recovery_actions": [
            "If any sport missing → re-run scan for that sport group",
            "If missing tournament → check if scan captured it, may need targeted re-scan",
            "If missing protected domestic league → check scan_results for that league, may need targeted re-scan of that region's sources",
        ],
    },
    "s2_tipster": {
        "agent": "bet-scout",
        "task": "Read full tipster arguments, assess quality, and verify how tipster_xref mutated the canonical shortlist without creating a second source of truth",
        "required_input": ["{date}_tipster_consensus.json", "{date}_s2_shortlist.json"],
        "output_metrics": ["tips_loaded", "matched", "total"],
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
        "detailed_instructions": [
            "1. Read tipster aggregation — extract per-tipster picks with full reasoning",
            "2. Assess tipster quality: named expert > anonymous aggregate",
            "3. Check independence: ≥2 tipsters from different platforms agreeing = consensus",
            "4. Look for angles pure stats missed: tactical changes, managerial quotes, team news",
            "5. Verify tipster_xref.py mutated betting/data/{date}_s2_shortlist.json in place with tipster_support and tipster_count",
            "6. Treat the mutated shortlist as the working set; tipster_consensus.json remains supporting evidence only",
            "7. Flag picks where tipsters strongly disagree with statistical analysis",
        ],
    },
    "s2_5_enrich": {
        "agent": "bet-enricher",
        "task": "Review enrichment yield by sport and source, separate warehouse scraper success from team_form readiness, and verify shortlist-scoped rich coverage",
        "required_input": ["{date}_s2_shortlist.json"],
        "output_metrics": ["teams_attempted", "enriched_count", "partial_count", "failed_count", "missing_shortlist_teams"],
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
        "detailed_instructions": [
            "1. Review batch_enrich results — break down by sport and source",
            "2. For each failed enrichment: identify WHY (CAPTCHA? 404? empty page? parsing error?)",
            "3. Check if fallback sources were tried (Flashscore → ESPN)",
            "4. Validate enriched data quality: stat values within sport-normal ranges",
            "5. Separate S2.3 warehouse output from S3 readiness: run_scrapers.py fills league_profiles/player_season_stats/match_stats, but bridge_league_to_team_form.py and scraper_to_team_form.py own any projection into team_form",
            "6. Cross-reference with DB: are shortlist teams actually represented in team_form and rich-coverage reporting?",
            "7. For persistent gaps: suggest specific alternative URLs from source-registry.md",
        ],
        "recovery_actions": [
            "If Flashscore blocked → try ESPN standings for US sports",
            "If sport has 0% enrichment → check if stat_keys are defined in SPORT_STAT_KEYS",
        ],
    },
    "s3_deep_stats": {
        "agent": "bet-statistician",
        "task": "Interpret safety scores, find edge mechanisms, fetch missing stats, write ANALYTICAL REASONING per candidate",
        "required_input": ["{date}_s3_deep_stats.json"],
        "output_metrics": ["candidates_analyzed", "avg_safety_score", "top_markets"],
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
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
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
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
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
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
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
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
        "task": "Review approved / extended_pool / rejected bucket assignments, build qualitative bear cases, and keep advisory tiers separate from authoritative gate buckets",
        "required_input": ["{date}_s7_gate_results.json"],
        "output_metrics": ["total", "approved", "extended", "rejected", "sport_diversity"],
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
        "detailed_instructions": [
            "1. Read gate_results — review approved, extended_pool, and rejected buckets as the authoritative S7 handoff",
            "2. For approved picks: build a BEAR CASE — what single event could kill this pick?",
            "3. For extended_pool picks: explain what blocks approval and what would move the pick into the approved bucket",
            "4. For rejected picks: confirm rejection reasons are explicit and not just hidden behind advisory labels",
            "5. Audit assumptions: is sample size adequate? Is H2H relevant? Is trend stable?",
            "6. Historical analogies: similar picks in betclic_bets_history.json — what happened?",
            "7. Bayesian update: combine statistical confidence with context/upset adjustments",
            "8. IMPORTANT: risk_tier and commentary are informational metadata. Bucket semantics (approved / extended_pool / rejected) are what S7.5, S7.6, and S8 consume.",
            "9. Verify league diversity and data depth in approved picks",
        ],
        "data_quality_validation": True,
    },
    "s8_coupons": {
        "agent": "bet-builder",
        "task": "Review portfolio strategically, build from approved picks after S7.5/S7.6 controls, and preserve extended_pool as a watch-list surface instead of a hidden rejection bucket.",
        "required_input": ["{date}_s7_gate_results.json"],
        "optional_input": ["betclic_market_validation_{date}.json", "repeat_loss_handoff_{date}.json"],
        "skip_flag": "--skip-betclic-validation (skips S7.5+S7.6, all picks CONDITIONAL per R8)",
        "output_metrics": ["gate_approved", "gate_extended", "gate_rejected", "singles", "core_coupons", "combos"],
        "think_in_the_middle": True,
        "error_handling": "ERROR_HANDLING_PROTOCOL",
        "validate_output": True,
        "detailed_instructions": [
            "1. Build the core portfolio from approved picks only, after consuming the S7.5 Betclic sidecar and S7.6 repeat-loss handoff",
            "2. Preserve extended_pool as a separate watch-list surface for user review; do not collapse it into rejection semantics",
            "3. Check hidden correlations: same league (weather/fixture congestion), same surface, same timezone",
            "4. Create COMBO MENU: 2-3 alternative combinations remixing the best approved picks",
            "5. Run coupon stress test (§8.2): simulate each leg failing — does coupon still make sense?",
            "6. Apply V1-V10 validation: V1(ID format), V2(no duplicate events), V3(odds check), V4(stake limits), V5(sport diversity), V6(correlation), V7(risk tier), V8(market validity), V9(arithmetic), V10(placement order)",
            "7. §S8.FINAL mechanical check: verify all arithmetic, cross-check safety scores vs gate results, and verify pre_coupon_controls are recorded in the coupon JSON",
            "8. Assign risk tiers: LR(low risk), MS(medium safety), HR(high reward), N(neutral)",
            "9. Per-pick concentration: no single pick >25% of total stake",
            "10. If approved picks are exhausted after S7.5/S7.6, treat NO_BET as a valid session outcome rather than a protocol failure",
            "11. Format output per betting-artifacts.instructions.md (Polish market names, coupon tables)",
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
        "written_at": datetime.now(get_tz()).isoformat(),
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
