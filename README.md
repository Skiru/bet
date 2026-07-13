# Betting Pipeline — Consolidated Power Agents

Agent-driven sports betting pipeline powered by an environment-configured local LLM server. Targets disciplined small-bankroll betting using a **Superbet manual Bet Builder** workflow, covering 8 sports: Football, Volleyball, Basketball, Tennis, Hockey, CS2, Dota 2, Valorant.

## Core Architecture

| Component | Value |
|-----------|-------|
| Model | Environment-configured (e.g., Qwen3.6-35B-A3B-4bit or similar local/cloud route) |
| Runtime | Rapid-MLX runtime is environment-configured; current local policy is Rapid-MLX 0.7.26 unless overridden by user environment |
| Context | 32768 tokens |
| Hardware | Locally served or cloud API routed |
| Database | SQLite WAL (`betting/data/betting.db`) — 28+ tables |
| Shell | Fish |
| Timezone | Europe/Warsaw (betting day 06:00–05:59) |

## Pipeline Truth Contract & Steps (S0–S10)

The complete, canonical, machine-readable pipeline definitions and agent-to-step mappings are defined in the pipeline truth contract `config/pipeline_manifest.json`.

| Step | Script / Wrapper | Manifest Agent | Purpose |
|------|------------------|-------|---------|
| S0 | `scripts/pipeline_steps/s0_settler.py` | bet-settler-postevent | Post-match settlement & historical learning |
| S1 | `scripts/pipeline_steps/s1_discover.py` | bet-researcher | Event discovery & scan |
| S1e | `scripts/pipeline_steps/s1e_event_ledger.py` | bet-researcher | Canonical materialized event-universe ledger |
| S2 | `scripts/pipeline_steps/s2_tipsters.py` | bet-researcher | Tipster aggregation |
| S2.3 | *agent_artifact* | bet-researcher | Enrichment Gap Detection |
| S2.5 | *agent_artifact* | bet-researcher | Provider Enrichment |
| S2.7 | *agent_artifact* | bet-researcher | Source Reconciliation |
| S2.9 | *agent_artifact* | bet-researcher | Data Readiness Gate |
| S3 | `scripts/pipeline_steps/s3_stats.py` | bet-modeler | Stats & Probability |
| S4 | `scripts/pipeline_steps/s4_valuator.py` | bet-modeler | Fair pricing, minimum quote, and quote-dependent EV |
| S5 | *agent_artifact* | bet-risk-gatekeeper | Context/Motivation/Risk |
| S6 | `scripts/pipeline_steps/s6_repeats.py` | bet-risk-gatekeeper | Portfolio/Repeat Guard |
| S7 | `scripts/pipeline_steps/s5_gate.py` | bet-risk-gatekeeper | Hard Approval Gate |
| S7b | `scripts/pipeline_steps/s7_validate.py` | bet-auditor | Manual Superbet market/line mapping |
| S8 | `scripts/pipeline_steps/s8_build_coupons.py` | bet-builder | Manual Superbet quote pack |
| S9 | *human_gate* | bet-risk-gatekeeper | Human-only Superbet quote and execution gate |
| S10 | *state_only* | bet-settler-postevent | Settlement Handoff |

*Note: All script steps are executed by the canonical shell-capable `bet-executor`. Code/General with Bash is reserved for engineering repair or emergency fallback. Business domain specialists do not run shell.*

## Running Pipeline via Canonical Runner

The only canonical runner is `scripts/pipeline_steps/run_daily_pipeline.py`. To run the pipeline in a dry-run/sandboxed state:

```fish
# Start local model (if running locally)
scripts/start-local-model.fish

# Stop local model
scripts/stop-local-model.fish

# Health check
scripts/healthcheck-local-model.fish

# Run pipeline via canonical daily runner
env PYTHONPATH=src:scripts .venv/bin/python3 scripts/pipeline_steps/run_daily_pipeline.py --date 2026-07-13 --run-id RUN_TEST_01 --runtime-mode DRY_RUN > /tmp/run.txt 2>&1
tail -20 /tmp/run.txt
```

## Infrastructure Certification & Lifecycle

Infrastructure certification is purely static and deterministic, clearly separated from runtime preflight and full pipeline execution.
The lifecycle stages must proceed sequentially:
1. Static Infrastructure Closure (This task)
2. Bounded Runtime Preflight
3. Full Pipeline Execution

Do not run the full S0-S8 pipeline or any live event discovery directly without completing the separate static and preflight steps.

## Active Consolidated Power Agent Roster

The legacy micro-agents have been completely retired. The architecture consists of exactly seven high-performing, single-responsibility power agents:

| Agent | Responsibility | Bash Permission | Mutation Permission |
|-------|----------------|-----------------|---------------------|
| `bet-executor` | Pipeline script execution, log capturing, gate enforcement | **allow** | **deny** |
| `bet-researcher`| Fixtures discovery, tipsters aggregation, enrichment, fact reconciliation | **deny** | **deny** |
| `bet-modeler` | S3 probabilities; S4 fair pricing, minimum quotes, and EV only with real odds | **deny** | **deny** |
| `bet-risk-gatekeeper`| Context checks (S5), portfolio risk (S6), and hard gates (S7); never human S9 | **deny** | **deny** |
| `bet-builder` | Correlation warnings, manual quote packs, and idea groups (S8) | **deny** | **deny** |
| `bet-auditor` | Database integrity audits, produced artifact verification (S7b) — **verification only** | **allow** | **deny** |
| `bet-settler-postevent`| Post-event reconciliation, learning feedback, outcome accounting (S10) | **deny** | **deny** |

## Database Schema

28+ tables across 7 domains:
- **Core**: sports, teams, competitions, fixtures, athletes
- **Statistics**: team_form (L10/L5/H2H), match_stats, league_profiles
- **Analysis**: analysis_results, gate_results, decision_snapshots
- **Betting**: coupons, bets, odds_history
- **Pipeline**: pipeline_runs, scan_results, fixture_sources
- **Tipster**: tipster_picks, tipster_consensus

## Core Constraints & Hard Boundaries

- **Zero-Tolerance Placement Boundary**: Absolutely no automated bookmaker placement is permitted. All placements must be performed manually by a human user.
- **Combined Odds Boundary**: Do not compute combined bookmaker odds within automated coupons. Combined Bet Builder odds must be retrieved from the real operator screen.
- **Preflight Gate**: All candidates remain strictly conditional and unbettable until the user manually verifies the exact market and enters a manual Superbet operator quote.
- **Human S9 Boundary**: Synthetic or agent-generated S9 approval is invalid. No Kelly/stake recommendation or executable coupon exists before real operator odds.
- **Coverage Boundary**: Missing odds or tipsters do not silently remove an event from core analysis. Every discovered event receives an explicit terminal status or reason; zero approved is valid `NO_ACTION_TERMINAL`.
- **Continuation Boundary**: Keep the same worktree and `RUN_ID` across bounded phases. Persist a safe checkpoint before an unavoidable UI/context limit and resume without repeating completed phases.
- **Roster Alignment**: Max 4 legs per coupon; unique events per core coupon; max 2 same-sport picks per coupon; safety floor < 0.15 is an instant reject.

## Directory Structure

```
betting/
    coupons/          # Daily coupon files
    data/             # betting.db + stats cache
    journal/          # Ledgers + learning log
    rules/            # Zero tolerance rules
tools/local-llm/     # Rapid-MLX configs & diagnostics
.kilo/
    agents/           # Consolidated power agent files
    docs/             # Architectural Tool Matrices and protocols
    prompts/          # Utility and developer prompts
scripts/
    pipeline_steps/   # S0-S8 scripts
    *.fish            # Model management scripts
src/bet/             # Core Python package
config/              # API keys, pipeline manifest, betting config
```

## Validation

All stats must trace to SQLite queries or file reads. Never invent odds, lineups, or statistical values. 4-pass mechanical verification before presenting coupons.
