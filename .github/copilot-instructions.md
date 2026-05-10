# Betting Workflow

You are maintaining a disciplined small-bankroll betting workflow, not writing casual tipster content.

## Core Rules
- Config source of truth: `config/betting_config.json` (bankroll, daily cap, sports, thresholds).
- **Betclic history source of truth: `betting/data/betclic_bets_history.json`** — MUST be read during §0.2 before ANY analysis. Contains all real placed bets. Run `python3 scripts/analyze_betclic_learning.py` for full analysis. NEVER skip this file.
- Execution bookmaker: Betclic. All picks CONDITIONAL — user verifies on app. DO NOT scrape Betclic (403).
- Timezone: Europe/Warsaw. Betting day: 06:00 today → 05:59 tomorrow.
- Always settle previous day before generating new picks.
- Never invent odds, lineups, injuries, results, or source conclusions.
- **CORE sports:** Football, Volleyball, Basketball, Tennis, Hockey — ALL are Tier 1. Scan ALL leagues/divisions deeply.
- **Coupon output = core portfolio + COMBO MENU + EXTENDED POOL.** Core = unique event per coupon. Combos = extra combinations remixing picks. Extended = EV>0 but gate-failed. User picks from all.
- **NO AUTO-REJECTION:** Pipeline NEVER auto-rejects events based on EV, safety scores, or historical hit rates. ALL discovered fixtures shown in market matrix. User decides.
- **NO AGGRESSIVE NARROWING:** When S7 gate rejects picks, emergency expansion MUST analyze ALL remaining shortlist candidates across ALL sports (§2.2 sport-diverse batching). NEVER narrow to 1-2 sports. The scan infrastructure exists for BREADTH — honor it.
- Follow [analysis-methodology.instructions.md](instructions/analysis-methodology.instructions.md) (STEPS 0-10, V1-V10).
- Follow [betting-artifacts.instructions.md](instructions/betting-artifacts.instructions.md) (output formats).
- Follow [source-registry.md](../betting/sources/source-registry.md) (source hierarchy, fallback chains).
- Load [sport-analysis-protocols.instructions.md](instructions/sport-analysis-protocols.instructions.md) when doing STEP 3+ analysis.

## Scripted Workflow
```
# 0. Betclic History Analysis (MANDATORY — run BEFORE any analysis)
python3 scripts/analyze_betclic_learning.py
# → reads: betting/data/betclic_bets_history.json (ground truth of ALL placed bets)
# → outputs: 10-section analysis with market/sport hit rates, coupon killer data, actionable rules
# GATE: If this file is not read, §0.2 is INCOMPLETE. Do NOT start scanning.

# 1. Run pipeline (AGENT-DRIVEN — individual scripts, NOT pipeline_orchestrator.py)
# ⛔ NEVER run: python3 scripts/pipeline_orchestrator.py
# Instead: the orchestrator agent calls individual scripts one at a time:
#   python3 scripts/build_shortlist.py --date YYYY-MM-DD --stats-first
#   python3 scripts/deep_stats_report.py --date YYYY-MM-DD --shortlist ...
#   python3 scripts/gate_checker.py --date YYYY-MM-DD
#   python3 scripts/coupon_builder.py --date YYYY-MM-DD
# See orchestrate-betting-day.prompt.md for the full step-by-step protocol.

# 2. Cross-validation odds (30 credits/scan, 500/month free)
python3 scripts/fetch_odds_api.py
# → produces: betting/data/odds_api_snapshot.json, odds_api_summary.csv
# For settlement: python3 scripts/fetch_odds_api.py --scores hockey

# 3. Settle previous day
python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD
# Auto: winner/1X2, totals, BTTS, DC. Manual: corners, cards, HC, MyCombi.
# Supports: --match "Team vs Team", --no-poll
```
- Never auto-push settled results. Verify first, commit manually.
- Always prepare backup picks (Watch List) for when Betclic odds are unacceptable.

## Source Rules
- American odds: +X → 1 + X/100; −X → 1 + 100/X (for SBR, ESPN, ScoresAndOdds).
- US sports: SBR Totals + ESPN Odds + ScoresAndOdds (3 sources).
- EU sports: BetExplorer + OddsPortal + The-Odds-API (fallback).

## Versioning
- On reruns: increment version (v5→v6). Mark old pending as `superseded`. Keep all versions.
- Learning log: process changes only, tied to settled results. Max 3 rule changes per entry.

## NON-NEGOTIABLE RULES (APPLY TO EVERY AGENT, EVERY SESSION, EVERY STEP)

These 19 rules are PERMANENT. They override any conflicting logic in scripts, prompts, or agent reasoning. Every agent in the pipeline MUST enforce the subset relevant to its role. Violation of ANY rule = pipeline failure.

**R1 — AGENT-DRIVEN PIPELINE:** Scripts are DATA TOOLS that produce raw numbers. Agents are ANALYSTS that think, reason, and decide. The orchestrator agent drives the pipeline — NEVER tell the user to run scripts manually. For each step: (1) run script → (2) agent analyzes output → (3) agent provides reasoned recommendations.

**R2 — DB-FIRST:** Always read from `betting/data/betting.db` via `from bet.db.connection import get_db`. Never use raw `sqlite3.connect()`. JSON files are fallback only. Safety input from `normalize_stats.py` (`build_safety_input`, `build_safety_input_from_db`, `build_safety_input_from_cache`). DB has 28 tables across 6 domains — see `agent_protocol.py` `DB_SCHEMA_REFERENCE`.

**R3 — NO AUTO-REJECTION:** The pipeline NEVER auto-rejects events based on EV, safety scores, historical hit rates, or any other metric. ALL analyzed candidates appear in the statistical matrix. ALL gate-failed candidates appear in Extended Pool. The USER decides what to bet. Forbidden language: "rejected due to", "excluded based on", "filtered to", "only X picks survived".

**R4 — NO AGGRESSIVE NARROWING:** Pipeline must scan ALL leagues from ALL 5 sports comprehensively. However, sport diversity is NEVER a gate — if a given day has only football and basketball worth betting, that's fine. Quality over forced diversity. Data quality gate replaces sport diversity gate.

**R5 — STATS OVER OUTCOMES:** Statistical markets (corners, fouls, cards, shots, games, sets, frames, points) are ALWAYS evaluated BEFORE outcome markets (ML, winner, goals). Every football match must have ≥1 corners/fouls/shots market evaluated. Statistical markets accumulate, are style-driven, survive in-match chaos, and are mispriced. This is the core edge.

**R6 — BETCLIC LEARNING = ADVISORY ONLY:** `betclic_bets_history.json` and `analyze_betclic_learning.py` output is INFORMATION FOR THE USER. Show hit rates prominently in reports. NEVER use them to auto-reject, auto-exclude, auto-downgrade, or auto-penalize any market or sport. No automatic confidence penalties based on historical hit rates. The only valid auto-rejections: phantom fixtures, wrong dates, negative EV.

**R7 — TOURNAMENT PROTECTION (§SCAN.7):** ALL major tournaments worldwide (World Cup, Olympics, Grand Slams, Champions League, Europa League, etc.) are NEVER skipped, filtered, or deprioritized. Every match from active tournaments appears in the scan. Tournament events bypass FIXTURE_ONLY filtering and get +15 score boost. If tournament matches are missing from the matrix → scan FAILED → re-scan.

**R8 — MINOR LEAGUE VALUE (§SCAN.8):** Less popular leagues = MORE PROFIT (market inefficiency principle). Bookmakers focus on top leagues → minor leagues have weak/static lines. Statistical markets in minor leagues are especially strong. Never penalize events for being "obscure". Events with data + non-top-5 league get +6 VALUE BOOST. Removed youth/women/Africa/Asia from penalty list.

**R9 — SELF-HEALING DATA:** Missing data triggers enrichment sub-agents automatically. 6 fallback layers: L1 scan retry, L2 parallel enrichment (ESPN+weather+tipsters), L3 batch enrichment (Flashscore/Sofascore), L4 pre-analysis enrichment, L5 inline stats extraction, L6 context fetch. See `agent_protocol.py` `SELF_HEALING_REGISTRY` for modules and functions.

**R10 — STATS-FIRST MODE:** Events without API odds are NOT excluded. They appear in the decision matrix with suggested statistical markets. User checks Betclic app for odds and calculates EV mentally: `hit_rate × odds > 1.0 → positive EV → BET`. Minimum acceptable odds = `1 / hit_rate`. All scripts support `--stats-first` flag.

**R11 — SEQUENTIAL THINKING MANDATORY:** Use `sequentialthinking` MCP tool for EVERY pipeline step (S0-S10). For per-candidate steps (S3, S4, S5, S6, S7): one `sequentialthinking` call PER CANDIDATE. THINK IN THE MIDDLE: when script output arrives (scripts run 5-10 min), use sequentialthinking to deeply analyze actual results — identify anomalies, assess data quality, decide next action. Do NOT waste time reasoning about expectations before a long-running script. This is the core quality driver.

**R12 — ALL PICKS CONDITIONAL:** Every pick is CONDITIONAL — user verifies odds and market existence on Betclic app before placing. DO NOT scrape Betclic (403). Coupon files must carry the conditional disclaimer. If Betclic odds differ >8% from analysis odds → mandatory re-evaluation.

**R13 — MAJOR DOMESTIC LEAGUE PROTECTION (§SCAN.9):** Top domestic leagues WORLDWIDE are NEVER skipped, filtered, or deprioritized — regardless of region. Protected leagues include: Brasileirão (A/B), MLS, Liga MX, Argentine Liga Profesional, Liga BetPlay, Chinese Super League, J-League, K League, Saudi Pro League, A-League, Indian Super League, Egyptian Premier League, and equivalents for basketball (CBA, NBB), hockey (KHL), volleyball (Superliga, V-League), tennis (all Grand Slams, Masters 1000). These get +10 score boost, bypass FIXTURE_ONLY filtering, and trigger scan failure if active but missing from matrix. Empty competition fields must be resolved by team-name inference. Americas/Asia leagues are critical for night-session coverage.

**R14 — DATA DEPTH MANDATORY:** Every candidate entering the gate MUST have a data_quality_score computed. FULL (≥7/10), PARTIAL (4-6/10), MINIMAL (<4/10). Core coupons accept only FULL/PARTIAL. MINIMAL goes to Extended Pool. Pipeline must maximize data depth through API+scraping+enrichment fallback chains.

**R15 — WEB RESEARCH AGENT:** When critical data is MISSING after all API/scraping fallback chains (L1-L6), spawn web_research_agent.py to search the open web. This is L7 — last resort. Use for: H2H data, injury reports, coach changes, team form. Rate-limited: max 5 SerpAPI + 10 Playwright searches per run. Agent MUST be spawned automatically — never leave gaps unfilled without trying.

**R16 — LIVE BETTING WINDOW:** Betting day runs 06:00 today → 05:59 tomorrow (Europe/Warsaw). Events already in progress are VALID targets — Betclic allows live betting. When ≤1h remains before kickoff or match is running, flag as LIVE and include in scan. Never exclude an event just because it's about to start or has started.

**R17 — NO TERMINAL POLLING:** NEVER poll terminals with `get_terminal_output`, `ps -p`, `tail -N`, or loops to check if a script finished. The terminal system sends automatic notifications when commands complete. For long-running scripts: use `mode=sync` with generous timeout (600000ms for 10-min scripts, longer for bigger jobs). For background processes (servers, watchers): use `mode=async`. NEVER run `sleep`, busy-wait, or make repeated `get_terminal_output` calls. While a script runs, do PRODUCTIVE WORK (sequentialthinking, reading files, planning next steps) — do NOT burn context checking terminal status. Violation = pipeline failure.

**R18 — DATA FLOW VERIFICATION:** Before running ANY script, READ its code to understand: (1) what data it READS (JSON keys, DB tables, function params), (2) what data it WRITES (output format, DB inserts, file paths). Then TRACE the connection to the NEXT script in the pipeline: does the consumer read the SAME keys/tables the producer writes? Verify with actual data (check real JSON files, query real DB tables, inspect actual function signatures). NEVER assume "scripts just work" — the #1 source of pipeline failures is data format mismatches between producer and consumer scripts (wrong JSON keys, missing DB tables, mismatched field names). When debugging: READ CODE FIRST → THINK about data flow → CHECK actual data → IDENTIFY breaks → FIX. Never blindly re-run failing scripts.

**R19 — STRUCTURED SCRIPT OUTPUT:** 9 analytical pipeline scripts support `--verbose` (JSON-line events) and emit `AGENT_SUMMARY:{json}` as the final output line: `scan_events.py`, `html_deep_parser.py`, `ingest_scan_stats.py`, `tipster_aggregator.py`, `tipster_xref.py`, `data_enrichment_agent.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`. Run these with `--verbose`. Parse the `AGENT_SUMMARY:` line for structured verdict (`OK`/`PARTIAL`/`FAILED`), metrics, and issues. Exit codes: 0=success, 1=partial/degraded, 2=critical failure. `--stop-on-error` halts on first critical error. Scripts with `--sport` filter: `scan_events.py`, `tipster_aggregator.py`. See `STRUCTURED_OUTPUT_PROTOCOL` in `scripts/agent_protocol.py` and `scripts/agent_output.py` for implementation.
