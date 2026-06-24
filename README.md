# Betting Pipeline — Rapid-MLX + Qwen3.6-35B-A3B-4bit

Agent-driven sports betting pipeline powered by **Rapid-MLX v0.6.82** serving **Qwen3.6-35B-A3B-4bit** locally on Apple M4 Pro (48GB). Targets disciplined small-bankroll betting on Betclic, covering 8 sports: Football, Volleyball, Basketball, Tennis, Hockey, CS2, Dota 2, Valorant.

## Core Architecture

| Component | Value |
|-----------|-------|
| Model | `mlx-community/Qwen3.6-35B-A3B-4bit` (35B params, 3B active per token) |
| Runtime | Rapid-MLX v0.6.82 (`port 8000`, ~19GB VRAM) |
| Context | 32768 tokens |
| Hardware | Apple M4 Pro, 48GB unified memory |
| Database | SQLite WAL (`betting/data/betting.db`) — 28+ tables |
| Shell | Fish |
| Timezone | Europe/Warsaw (betting day 06:00–05:59) |

## Pipeline Steps (S0–S10)

For the complete, canonical, machine-readable pipeline definitions, see the [Pipeline Truth Contract](docs/pipeline/Pipeline%20Truth%20Contract.md) and `config/pipeline_manifest.json`.

| Step | Script / Wrapper | Agent | Purpose |
|------|------------------|-------|---------|
| S0 | `scripts/pipeline_steps/s0_settler.py` | bet-settler | Settlement & historical learning |
| S1 | `scripts/pipeline_steps/s1_discover.py` | bet-scanner | Event discovery & scan |
| S1e | *state_only* | bet-scanner | Shortlist construction |
| S2 | `scripts/pipeline_steps/s2_tipsters.py` | bet-scout | Tipster aggregation |
| S2.3 | *agent_artifact* | bet-enricher | Enrichment Gap Detection |
| S2.5 | *agent_artifact* | bet-enricher | Provider Enrichment |
| S2.7 | *agent_artifact* | bet-enricher | Source Reconciliation |
| S2.9 | *agent_artifact* | bet-enricher | Data Readiness Gate |
| S3 | `scripts/pipeline_steps/s3_stats.py` | bet-statistician | Stats & Probability |
| S4 | `scripts/pipeline_steps/s4_valuator.py` | bet-valuator | Valuator & CLV |
| S5 | *agent_artifact* | bet-challenger | Context/Motivation/Risk |
| S6 | `scripts/pipeline_steps/s6_repeats.py` | bet-challenger | Portfolio/Repeat Guard |
| S7 | `scripts/pipeline_steps/s5_gate.py` | bet-challenger | Hard Approval Gate |
| S7b | `scripts/pipeline_steps/s7_validate.py` | bet-test-engineer | Market Availability Validation |
| S8 | `scripts/pipeline_steps/s8_build_coupons.py` | bet-builder | Coupon construction |
| S9 | *human_gate* | bet-challenger | Human Execution Gate |
| S10 | *state_only* | bet-settler | Settlement Handoff |

## Running Scripts

```fish
# Start local model
scripts/start-local-model.fish

# Stop local model
scripts/stop-local-model.fish

# Health check
scripts/healthcheck-local-model.fish

# Run pipeline step
.venv/bin/python3 scripts/pipeline_steps/sN.py > /tmp/sN.txt 2>&1
tail -20 /tmp/sN.txt
```

## Agent Roster

| Agent | Role |
|-------|------|
| bet-orchestrator | Pipeline sequencing & delegation |
| bet-scanner | Event discovery & shortlist |
| bet-scout | Tipster consensus |
| bet-enricher | Data quality |
| bet-statistician | Market ranking & safety scores |
| bet-valuator | EV & odds |
| bet-challenger | Risk assessment & gate |
| bet-builder | Coupon construction |
| bet-settler | Settlement & PnL |
| bet-db-analyst | Database integrity |

## Database Schema

28+ tables across 7 domains:
- **Core**: sports, teams, competitions, fixtures, athletes
- **Statistics**: team_form (L10/L5/H2H), match_stats, league_profiles
- **Analysis**: analysis_results, gate_results, decision_snapshots
- **Betting**: coupons, bets, odds_history
- **Pipeline**: pipeline_runs, scan_results, fixture_sources
- **Tipster**: tipster_picks, tipster_consensus
- **External**: espn_predictions, player_splits, team_rosters

## Key Constraints

- Statistical markets before outcome markets
- Max 4 legs per coupon
- Unique events per core coupon
- Max 2 same-sport picks per coupon
- Safety floor < 0.15 = INSTANT REJECT
- All picks CONDITIONAL until user verifies in Betclic app

## Zero Tolerance Rules

Every hard rule traces to real settled losses. See `betting/rules/position-management.md` for full list.

## Directory Structure

```
betting/
    coupons/          # Daily coupon files
    data/             # betting.db + stats cache
    journal/          # Ledgers + learning log
    rules/           # Zero tolerance rules
tools/local-llm/     # Rapid-MLX configs & diagnostics
.kilo/
    prompts/          # Agent prompts
    rules/            # Pipeline rules
scripts/
    pipeline_steps/   # S0-S8 scripts
    *.fish           # Model management scripts
src/bet/             # Core Python package
config/              # API keys, betting config
```

## Model: Qwen3.6-35B-A3B-4bit

- **Type**: MoE (Mixture of Experts)
- **Experts**: 256 total, 8 active per token
- **Performance**: 71.94 tok/s decode, 12.4x cache speedup
- **Limitations**: Text-only (no images), no MTP acceleration

## Validation

All stats must trace to DB queries or file reads. Never invent odds, lineups, or statistical values. 4-pass mechanical verification before presenting coupons.
