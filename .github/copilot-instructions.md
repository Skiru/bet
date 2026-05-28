# Betting Workspace Constitution

This repository uses Copilot customizations to run a disciplined small-bankroll betting workflow. It is not a casual tipster workspace.

## Ownership Model

- agent = WHO owns the task, delegation boundary, and tool use.
- skill = HOW reusable workflow mechanics or domain methods are applied.
- prompt = WHAT workflow entry point or task framing is being requested.
- instructions = RULES that apply consistently across the active surface.

## Canonical Owners

| Concern | Canonical owner |
| --- | --- |
| Project constitution, repo-wide constraints, model standard, memory boundary | this file |
| Always-on execution behavior for bet agents | [agent-execution-protocol.instructions.md](instructions/agent-execution-protocol.instructions.md) |
| Reusable workflow mechanics, delegation flow, routing, resume/stop gates | [bet-orchestrating-workflows/SKILL.md](skills/bet-orchestrating-workflows/SKILL.md) |
| Betting analysis methodology | [analysis-methodology.instructions.md](instructions/analysis-methodology.instructions.md) |
| Sport-specific analysis rules | [sport-analysis-protocols.instructions.md](instructions/sport-analysis-protocols.instructions.md) |
| Hard reject lessons from settled losses | [betting-mistakes-rules.instructions.md](instructions/betting-mistakes-rules.instructions.md) |
| Formatting rules for reports, coupons, ledgers, and artifact wording | [betting-artifacts.instructions.md](instructions/betting-artifacts.instructions.md) |
| Domain HOW layers for statistics, sources, odds, coupons, settlement, and DB work | `bet/.github/skills/bet-*/SKILL.md` |
| Primary repo memory | `/memories/repo/` and `/memories/session/` |

## Active Model Standard

- Primary pipeline model: Google Gemini 3.5 Flash via Kilo Code (`google/gemini-3.5-flash`).
- Context: 1M tokens, free tier (1,500 RPD, 15 RPM via direct Google Gemini provider).
- Autocomplete: Codestral 22B via Continue.dev (`mistralai/codestral-22b-v0.1`).
- Stale model literals (GPT-5.4, Claude Opus 4.6, gemma-4-31b, qwen3.6-27b, laguna-m.1) are invalid in the active `.github` tree.

## Repo-Wide Constraints

- Bookmaker: Betclic. All picks are conditional until the user verifies the market and odds in the Betclic app.
- Do not scrape Betclic.
- Timezone: Europe/Warsaw. Betting day runs from 06:00 to 05:59 local time.
- Always settle the previous betting day before generating new picks.
- Never invent odds, lineups, injuries, results, source conclusions, or statistical values.
- Coverage scope: Football, Volleyball, Basketball, Tennis, Hockey, CS2, Dota 2, Valorant.
- Coupon model: core portfolio + combination menu + extended pool. Core coupons use unique events.
- No auto-rejection or aggressive narrowing based on hit rates, safety scores, or historical performance. The user decides. Only invalid fixtures, wrong dates, and negative-EV positions may be auto-removed.
- Statistical markets come before outcome markets. Missing bookmaker odds do not cancel analysis.
- Use the DB-first architecture: `from bet.db.connection import get_db` and repository layers. JSON, CSV, and Markdown outputs are secondary artifacts.
- The orchestrator is the pipeline. Do not run `python3 scripts/pipeline_orchestrator.py`.
- Reruns create new versions. Preserve history and mark superseded pending artifacts instead of overwriting them.

## Workflow Boundary

- Prompts keep only the entry-point-specific flow, inputs, and output expectations for their workflow.
- Agents keep role identity, collaboration boundaries, and canonical references.
- Skills keep reusable execution mechanics or domain methodology.
- Instructions keep rules that must stay always-on across activations.

If a workflow detail is shared across more than one prompt or agent and is not a repo-wide rule, it belongs in the workflow skill rather than in this file.

## Memory Boundary

- Root memory under `/memories/repo/` and `/memories/session/` is the primary persistent memory system.
- `.github/memories/` may contain only short repo-local facts that help customizations route work. It must not duplicate rulebooks, full workflow manuals, or policy surfaces already owned elsewhere.

## Required Canonical Loads

- Load [analysis-methodology.instructions.md](instructions/analysis-methodology.instructions.md) for betting analysis.
- Load [sport-analysis-protocols.instructions.md](instructions/sport-analysis-protocols.instructions.md) for sport-specific analysis work.
- Load [betting-mistakes-rules.instructions.md](instructions/betting-mistakes-rules.instructions.md) during S3, S5, S7, and S8 work.
- Load [betting-artifacts.instructions.md](instructions/betting-artifacts.instructions.md) when producing coupons, reports, ledgers, or settlement artifacts.

## Session Expectations

- The orchestrator runs individual scripts, monitors outputs, and delegates interpretation to specialist agents.
- Specialists analyze finished outputs and domain evidence unless the active prompt explicitly makes them the direct operator.
- Output quality is measured by evidence, reasoning, and traceability, not by terminal completion alone.
