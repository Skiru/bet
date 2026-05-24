# Betting Workflow

You are maintaining a disciplined small-bankroll betting workflow, not writing casual tipster content.

## Core Rules
- Config: `config/betting_config.json` (bankroll, daily cap, sports, thresholds).
- Betclic history: `betting/data/betclic_bets_history.json` — read during §0.2 before ANY analysis (see R6).
- Bookmaker: Betclic. All picks CONDITIONAL (R12). DO NOT scrape Betclic (403).
- Timezone: Europe/Warsaw. Betting day: 06:00 today → 05:59 tomorrow.
- Always settle previous day before generating new picks.
- Never invent odds, lineups, injuries, results, or source conclusions.
- **5 core sports + 3 esports:** Football, Volleyball, Basketball, Tennis, Hockey — ALL Tier 1. CS2, Dota 2, Valorant — Tier 1 esports.
- **Coupon = core portfolio + COMBO MENU + EXTENDED POOL.** Core = unique event per coupon.
- NO AUTO-REJECTION (R3). NO AGGRESSIVE NARROWING (R4). User decides.
- Follow [analysis-methodology.instructions.md](instructions/analysis-methodology.instructions.md), [betting-artifacts.instructions.md](instructions/betting-artifacts.instructions.md), [source-registry.md](../betting/sources/source-registry.md).
- Load [sport-analysis-protocols.instructions.md](instructions/sport-analysis-protocols.instructions.md) for STEP 3+ analysis.

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
#   PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date YYYY-MM-DD --verbose
#   python3 scripts/build_shortlist.py --date YYYY-MM-DD --stats-first
#   python3 scripts/deep_stats_report.py --date YYYY-MM-DD --shortlist ...
#   python3 scripts/gate_checker.py --date YYYY-MM-DD
#   python3 scripts/coupon_builder.py --date YYYY-MM-DD
# See orchestrate-betting-day.prompt.md for the full step-by-step protocol.

# 2. Cross-validation odds (30 credits/scan, 500/month free)
python3 scripts/fetch_odds_api.py
# → produces: betting/data/odds_api_snapshot.json, odds_api_summary.csv
# For settlement: python3 scripts/fetch_odds_api.py --scores hockey

# 2a. Esports odds (FREE, no auth, Playwright-rendered bo3.gg)
python3 scripts/fetch_esports_odds.py --date YYYY-MM-DD --verbose
# → writes to DB: odds_history (bookmaker=\"bo3gg\") for CS2 + Valorant
# → matches scraped teams to DB fixtures, stores ML odds
# → run AFTER discover_events.py (needs fixtures), BEFORE odds_evaluator.py
# → use --detail for handicap/H2H from individual match pages

# 2b. Bovada odds + player props (FREE, no auth, unlimited)
python3 scripts/fetch_bovada_odds.py --verbose
# → writes DIRECTLY to DB: odds_history (bookmaker="bovada") + player_prop_lines table
# → covers: NBA/NHL/Tennis/Soccer/Volleyball/MLB with 100-1200 markets/event
# → player props: points, rebounds, assists, SOG, goals, strikeouts per player
# → run AFTER discover_events.py (needs fixtures), BEFORE odds_evaluator.py
# ⚠️ IMPLEMENTATION STATUS: Plan ready (betting/plans/bovada-integration.plan.md), code pending.

# 3. Settle previous day
python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD
# Auto: winner/1X2, totals, BTTS, DC.
# Semi-auto: football corners, cards, shots, fouls (via canonical DB match_stats when coverage exists).
# Manual: HC, MyCombi, unresolved stat markets without DB coverage.
# Supports: --match "Team vs Team", --no-poll
```
- Never auto-push settled results. Verify first, commit manually.
- Always prepare backup picks (Watch List) for when Betclic odds are unacceptable.

## Source Rules
- American odds: +X → 1 + X/100; −X → 1 + 100/X (for SBR, ESPN, ScoresAndOdds, Bovada).
- US sports: Bovada (primary, free, richest) + SBR Totals + ESPN Odds + ScoresAndOdds.
- EU sports: BetExplorer + OddsPortal + Odds-API.io (primary odds cross-validation).
- Esports: bo3.gg (PRIMARY, Playwright-rendered, free). VLR.gg (Valorant stats). HLTV.org (CS2 fallback, Cloudflare). `fetch_esports_odds.py` writes to DB `odds_history` (bookmaker='bo3gg').
- Player props: Bovada `player_prop_lines` table (PRIMARY). Compare vs actual L10 averages for edge detection.
- Bovada: FREE public JSON feed, no API key. Writes to DB only (R2). Client: `src/bet/api_clients/bovada.py`.
- ⚠️ Bovada integration PENDING implementation — see `betting/plans/bovada-integration.plan.md`.

## Versioning
- On reruns: increment version (v5→v6). Mark old pending as `superseded`. Keep all versions.
- Learning log: process changes only, tied to settled results. Max 3 rule changes per entry.

## NON-NEGOTIABLE RULES (APPLY TO EVERY AGENT, EVERY SESSION, EVERY STEP)

These 10 rules are PERMANENT. They override any conflicting logic in scripts, prompts, or agent reasoning. Violation = pipeline failure. Detailed specifics in [agent-execution-protocol.instructions.md](instructions/agent-execution-protocol.instructions.md).

**R1 — AGENT-DRIVEN PIPELINE:** Orchestrator RUNS scripts (async, --verbose), MONITORS via AGENT_SUMMARY, DELEGATES analysis to specialist subagents. Subagents NEVER run scripts. Always parse structured output. See `agent_protocol.py` STRUCTURED_OUTPUT_PROTOCOL.

**R2 — DB-FIRST:** Always `from bet.db.connection import get_db`. Never raw `sqlite3.connect()`. JSON = fallback only. DB has 40+ tables across 7 domains — see `agent_protocol.py` DB_SCHEMA_REFERENCE.

**R3 — NO AUTO-REJECTION:** Pipeline NEVER auto-rejects based on EV thresholds, safety scores, or hit rates. ALL candidates appear in matrix. ALL gate-failed → Extended Pool. User decides. Betclic learning = advisory only (show hit rates, never penalize). Only valid auto-rejections: phantom fixtures, wrong dates, negative EV.

**R4 — STATS-FIRST:** Statistical markets (corners, fouls, cards, shots, games, sets) ALWAYS evaluated BEFORE outcomes (ML, winner). Events without API odds still analyzed. User checks Betclic: `hit_rate × odds > 1.0 → BET`.

**R5 — LEAGUE PROTECTION:** Tournaments +15 boost, protected domestic leagues +10, minor leagues +6 VALUE BOOST. NEVER skip/deprioritize active tournaments, major leagues, or minor leagues with data. Missing protected leagues → scan FAILED.

**R6 — SELF-HEALING DATA:** 7 fallback layers (L1-L7). Missing data triggers enrichment automatically. L7 = web_research_agent.py (max 5 SerpAPI + 10 searches). Never leave data gaps unfilled without trying all layers.

**R7 — SEQUENTIAL THINKING:** Use `sequentialthinking` MCP tool for EVERY pipeline step. THINK IN THE MIDDLE: when script runs (5-10 min), analyze data quality, identify anomalies, plan next action. One call per candidate for S3-S7.

**R8 — CONDITIONAL PICKS + LIVE:** All picks CONDITIONAL — user verifies on Betclic app. DO NOT scrape Betclic (403). Odds >8% drift → re-evaluate. Live betting valid (06:00 today → 05:59 tomorrow Europe/Warsaw).

**R9 — DATA QUALITY + FLOW VERIFICATION:** Every candidate needs `data_quality_score` (FULL≥7, PARTIAL 4-6, MINIMAL<4). MINIMAL → Extended Pool. Before running ANY script: READ code, TRACE data flow, VERIFY keys/tables match next script.

**R10 — FISH SHELL + NO INLINE PYTHON:** FORBIDDEN: `python3 -c`, bash loops, heredocs. Use `run_in_terminal` for pipeline scripts (mode=async). For data inspection: use notebook cells or dedicated scripts. See `agent-execution-protocol.instructions.md` §FISH SHELL.
