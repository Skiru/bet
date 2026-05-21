# betting-pipeline-session-readiness-audit - Implementation Plan

## Task Details

| Field            | Value |
| ---------------- | ----- |
| Jira ID          | N/A |
| Title            | Betting pipeline session readiness hardening for 2026-05-21 |
| Description      | Harden the existing bet-repo betting workflow for today's full session by aligning bet-only `.github` orchestration artifacts with runtime truth, repairing DB/JSON producer-consumer contracts across S0-S10, and making readiness verification authoritative after yesterday's rich-stat/enrichment rollout changed the expected data surfaces. |
| Priority         | High |
| Related Research | `specifications/betting-pipeline-session-readiness-audit/betting-pipeline-session-readiness-audit.research.md` |

## Proposed Solution

Treat session readiness as a contract-hardening task across three layers that already exist in `bet`:

1. **Control plane**: `.github` prompts, agents, internal-prompts, and bet-local execution instructions must describe the same step order, CLI contracts, output expectations, and pre-coupon gates that the runtime actually uses.
2. **Runtime/data plane**: the Python pipeline must preserve a coherent source of truth from settlement through coupon generation, with explicit handling for the repo's hybrid DB-first plus JSON-operational design.
3. **Verification plane**: readiness checks must be based on live DB/file evidence, rich-coverage state, and pre-coupon sidecars, not on stale `pipeline_state` assumptions.

The implementation should not redesign enrichment or add a second analysis path. Yesterday's rich-stat rollout is treated as already shipped context. This plan only adds the orchestration, observability, parity, and control-handoff fixes needed so today's coordinator can trust that richer data and can detect when that richer data is not actually consumable by S3-S8.

Key architecture decisions for the hardening work:

- Keep the current **DB-first but not DB-only** model. JSON artifacts remain operational for shortlist mutation, S3 full candidate coverage, S7 gate artifacts, and coupon sidecars.
- Make **candidate parity** explicit. If DB persistence is narrower than JSON at S3-S6, the pipeline must preserve the intended candidate universe or fail loudly.
- Make **bucket semantics** explicit. Approved, Extended Pool, and rejected candidates must survive DB and JSON round-trips without collapsing into a single status.
- Make **pre-coupon controls** durable. S7.5 Betclic validation and S7.6 repeat-loss checks must be machine-consumable by S8 rather than living only in stdout or stale prompt text.

```text
Control Plane (.github in bet only)
  orchestrate-betting-day.prompt.md
  bet-orchestrator.agent.md
  specialist agents + internal-prompts
  agent-execution-protocol.instructions.md
        |
        v
Runtime/Data Plane (scripts + src/bet/db)
  S0 settlement/learning
  S1 discovery/market matrix/shortlist
  S2 tipsters + S2.3 scrapers + S2.5 enrichment
  S3 deep stats -> S4 EV -> S5 context -> S6 upset risk
  S7 gate -> S7.5 Betclic -> S7.6 repeats -> S8 build -> S9 validate -> S10 PDF
        |
        v
Verification Plane
  inspect_pipeline.py
  validate_phase.py
  db_report.py
  agent_protocol.py / agent_output.py
```

## Current Implementation Analysis

### Already Implemented

List of existing components, functions, utilities that will be reused (with file paths):

- `orchestrate-betting-day.prompt.md` - `.github/prompts/orchestrate-betting-day.prompt.md` - current session entrypoint already uses the run-then-delegate orchestration model.
- `bet-orchestrator.agent.md` - `.github/agents/bet-orchestrator.agent.md` - current orchestrator agent already documents the S0-S10 script surface and analysis-only specialist handoff pattern.
- `AgentOutput` - `scripts/agent_output.py` - shared structured output contract for scripts that emit `AGENT_SUMMARY:{json}`.
- `inspect_pipeline.py` - `scripts/inspect_pipeline.py` - strongest existing read-only inspector for DB/files and rich-coverage state.
- `db_report.py` rich-coverage report - `scripts/db_report.py` - already exposes post-rollout `rich`, `baseline_only`, `partial`, `no_data` coverage buckets.
- `deep_stats_report.py` dual-write path - `scripts/deep_stats_report.py` plus `scripts/db_data_loader.py::save_analysis_results_to_db` - already writes S3 results to DB first, injects `fixture_id`, then writes JSON.
- `odds_evaluator.py` JSON-first fallback behavior - `scripts/odds_evaluator.py` - already encodes the correct insight that DB coverage can be narrower than S3 JSON coverage.
- `GateResultRepo` and gate loaders - `src/bet/db/repositories.py`, `scripts/db_data_loader.py`, `scripts/coupon_builder.py` - existing DB-first gate loading/persistence surfaces can be reused once status semantics are repaired.
- `validate_betclic_markets.py` plus builder sidecar load - `scripts/validate_betclic_markets.py`, `scripts/coupon_builder.py` - the runtime already converges on `betclic_market_validation_{date}.json`.
- `run_scrapers.py`, `bridge_league_to_team_form.py`, `scraper_to_team_form.py`, `data_enrichment_agent.py` - `scripts/` - the repo already has distinct S2.3, bridge, and S2.5 ownership surfaces that can be clarified rather than recreated.
- `check_48h_repeats.py` - `scripts/check_48h_repeats.py` - existing repeat-loss detection logic can be reused once it exposes a pipeline-compatible contract.

### To Be Modified

List of existing code that needs changes or extensions (with file paths and description of changes):

- `validate_phase.py` - `scripts/validate_phase.py` - replace legacy `pipeline_state` hard gates, align step IDs with the current pipeline, and validate live DB/file/readiness surfaces including rich coverage and pre-coupon controls.
- `inspect_pipeline.py` - `scripts/inspect_pipeline.py` - extend readiness reporting for S2.3 bridge visibility, S3-S6 parity, S7 bucket parity, and S8 pre-coupon sidecar consumption.
- `db_report.py` - `scripts/db_report.py` - keep rich-coverage output authoritative for post-enrichment readiness and integrate it into implementation verification expectations.
- `gate_checker.py` - `scripts/gate_checker.py` - persist explicit bucket/status semantics so Extended Pool does not disappear on DB-first resume.
- `db_data_loader.py` and `GateResultRepo` - `scripts/db_data_loader.py`, `src/bet/db/repositories.py` - repair dead JSON fallback assumptions and align DB loaders with bucketed S7 results.
- `coupon_builder.py` - `scripts/coupon_builder.py` - preserve gate parity on DB-first loads and consume S7.5/S7.6 controls explicitly.
- `deep_stats_report.py`, `odds_evaluator.py`, `context_checks.py`, `upset_risk.py` - `scripts/` - unify candidate-loading behavior so partial DB persistence cannot silently shrink the working candidate set.
- `run_scrapers.py`, `bridge_league_to_team_form.py`, `scraper_to_team_form.py`, `data_enrichment_agent.py` - `scripts/` - expose machine-readable bridge/team_form readiness so the orchestrator can tell when scraper success is not S3 readiness.
- `agent_protocol.py` and `agent_output.py` - `scripts/` - update declared step contracts, sidecars, and summary expectations to match runtime truth.
- `.github` orchestration artifacts in bet - `.github/prompts/orchestrate-betting-day.prompt.md`, `.github/agents/bet-orchestrator.agent.md`, `.github/internal-prompts/bet-enrich.prompt.md`, `.github/internal-prompts/bet-tipsters.prompt.md`, `.github/internal-prompts/bet-gate.prompt.md`, `.github/internal-prompts/bet-portfolio.prompt.md`, `.github/internal-prompts/bet-validate.prompt.md`, `.github/agents/bet-enricher.agent.md`, `.github/agents/bet-builder.agent.md`, `.github/instructions/agent-execution-protocol.instructions.md` - synchronize step order, CLI usage, AGENT_SUMMARY assumptions, rich-coverage gates, S7.5 filename, S7.6 handoff, settlement/learning prerequisite gates, and model/execution guidance where it affects readiness.
- `check_48h_repeats.py` - `scripts/check_48h_repeats.py` - add a durable same-day handoff and resolve the prompt/runtime CLI mismatch (`--date` is currently documented but not implemented).

### To Be Created

List of new components, functions, utilities that need to be built from scratch:

- Shared S3 candidate parity loader/checker - likely added in `scripts/db_data_loader.py` or an adjacent runtime helper so S4/S5/S6 can consume one canonical candidate-loading contract.
- Durable S7.6 repeat-loss handoff contract - a date-scoped artifact or equivalent canonical store that S8 can consume automatically.
- Focused regression tests covering readiness hardening - new test modules for `validate_phase.py`, gate-results round-trip, S3-S6 candidate parity, and S7.5/S7.6 pre-coupon controls.

## Open Questions

| #   | Question | Answer | Status |
| --- | -------- | ------ | ------ |
| 1   | Should S10 PDF generation be a blocking part of today's build-phase readiness gate? | This plan assumes yes for "full betting session readiness" because `generate_coupon_pdf.py` exists and S10 is in the official step map. If the user defines readiness as validated markdown/JSON coupons only, B-phase gating should be downgraded from FAIL to WARN. | ❓ Open |
| 2   | What is the preferred persistence form for S7.6 repeat-loss handoff? | Default recommendation: a date-scoped, machine-readable artifact consumed by `coupon_builder.py`, because it is the smallest safe change on top of the current hybrid DB/JSON pipeline. A DB-only implementation is viable but broader. | ❓ Open |
| 3   | Should bet-local model routing be normalized everywhere? | No. Only contradictions that affect today's orchestration readiness should be resolved in touched bet `.github` files. Broader model cleanup is out of scope. | ✅ Resolved |
| 4   | Should yesterday's rich-stat work be reopened in this slice? | No. Yesterday's rollout is treated as existing context. This plan only adds readiness gates, bridge visibility, and parity fixes that sit on top of it. | ✅ Resolved |

## Technical Context

Project conventions, coding standards, and patterns discovered during planning. Downstream agents MUST read this section instead of re-discovering the same context.

### Project Instructions

- `.github/copilot-instructions.md` - agent-driven pipeline only; never use `pipeline_orchestrator.py`; DB-first via `get_db()`; no auto-rejection; stats-first; self-healing data; verify producer/consumer contracts before changing scripts; Betclic checks are conditional and must not be treated as scraped source-of-truth outside approved flows.
- `.github/instructions/agent-execution-protocol.instructions.md` - applies to `.github/agents/bet-*.agent.md`; fish shell only; no inline terminal Python; sequentialthinking boot/self-audit; use Pylance-first for data inspection. This file currently still contains a stale `Gemini 3.1 Pro (Preview)` execution note that conflicts with bet-local agent model declarations and current session reality.
- `memories/repo/pipeline-knowledge-base.md` - `src/bet/api_clients/` is canonical; Branch B DB-backed settlement is final; recent orchestrator fixes already landed, so this plan must build on top of that state rather than reintroducing older paths.
- User-scope constraint for this task - modify only `/Users/mkoziol/projects/bet`; `copilot-collections` is reference-only and not an implementation target.

### Architecture & Patterns

- The repo is a hybrid Python pipeline with SQLite plus operational JSON artifacts. Runtime truth is split across `.github` orchestration files, `scripts/` pipeline code, `src/bet/db/` repositories, and `betting/data/` artifacts.
- Canonical DB access is `src/bet/db/connection.py:get_db()`; repository classes under `src/bet/db/repositories.py` are the preferred access pattern.
- JSON artifacts are still operational, not just report outputs. Important live artifacts include `market_matrix_{date}.json`, `{date}_s2_shortlist.json`, `{date}_s3_deep_stats.json`, `{date}_s7_gate_results.json`, `betclic_market_validation_{date}.json`, and weather/tipster JSON fallbacks.
- `deep_stats_report.py` writes markdown first, saves analysis results to DB through `save_analysis_results_to_db()`, then writes JSON after `fixture_id` injection. Downstream S4-S6 logic relies on that injected identifier.
- `odds_evaluator.py` intentionally prefers S3 JSON over DB because DB `analysis_results` can be narrower than the full shortlist-derived S3 universe.
- `context_checks.py` and `upset_risk.py` currently load DB first and fall back to JSON only when DB is empty, which creates a silent narrowing risk when DB is only partial.
- `run_scrapers.py` writes warehouse tables such as `league_profiles`, `player_season_stats`, and `scraper_runs`. It does not make S3 ready by itself because S3 reads `team_form` and `match_stats`.
- Bridge helpers (`bridge_league_to_team_form.py`, `scraper_to_team_form.py`) and `data_enrichment_agent.py` are the current surfaces that can influence S3-consumable stat truth after scrapers run.
- Rich-stat readiness now uses `bet.stats.fallback_chains.RICH_COMPLETION_POLICY` plus `bet.stats.rich_coverage` buckets: `rich`, `baseline_only`, `partial`, `no_data`.
- `gate_checker.py` outputs bucketed JSON with `approved`, `extended_pool`, and `rejected`, while `coupon_builder.py` expects exactly that nested structure on the input side.
- `agent_output.py` defines the canonical `AGENT_SUMMARY:{json}` format, but not every script uses it. Internal prompts must distinguish AGENT_SUMMARY-producing scripts from scripts that still require human-readable metric parsing.

### Tech Stack

- Python `>=3.11` (`pyproject.toml`).
- SQLite database at `betting/data/betting.db`.
- Key Python dependencies already present in scope: `requests`, `beautifulsoup4`, `playwright`, `lxml`, `google-genai`, `pydantic`, `sqlalchemy`, `rapidfuzz`, `aiosqlite`.
- Test runner: `pytest` with `testpaths = ["tests"]`.
- The repo also contains a Next.js dashboard under `dashboard/`, but UI work is explicitly out of scope for this task.

### Code Style & Standards

- Fix the contract at the owning boundary instead of adding parallel fallback paths.
- Prefer modifying existing script/load/save helpers over creating duplicate runtime utilities.
- Preserve current artifact naming patterns and date-scoped file conventions unless the plan explicitly standardizes a drifted contract.
- For DB work, prefer `get_db()` and repository classes; do not add fresh direct `sqlite3` access where the repo already has a canonical abstraction.
- `.github` specialist agents remain analysis-only. The orchestrator runs scripts; internal prompts should not instruct specialists to rerun them.
- Fish-safe commands matter in documentation and prompts. Avoid documenting unsupported shell syntax or nonexistent CLI flags.

### Testing Patterns

- Use focused pytest modules under `tests/` rather than a broad repo-wide regression run for each implementation slice.
- Treat validation scripts as executable verification surfaces, not just documentation: `inspect_pipeline.py`, `validate_phase.py`, `validate_coupons.py`, `db_report.py`.
- Prefer slice-scoped automated checks after each phase:
  - `validate_phase.py` regression tests with synthetic DB/file states
  - gate-results round-trip tests across `gate_checker.py`, `db_data_loader.py`, `GateResultRepo`, and `coupon_builder.py`
  - S3-S6 candidate parity tests for partial DB and JSON fallback cases
  - pre-coupon control tests for Betclic validation and repeat-loss handoff
- Use `.venv` and existing repo conventions for script execution. Narrow commands are expected to be fish-safe, e.g. `PYTHONPATH=src .venv/bin/python3 scripts/...` and `.venv/bin/pytest -q tests/...`.

### Database Patterns

- Relevant tables for this hardening slice: `fixtures`, `scan_results`, `team_form`, `match_stats`, `analysis_results`, `analysis_raw_data`, `gate_results`, `coupons`, `bets`, `odds_history`, `pipeline_runs`, `tipster_picks`, `tipster_consensus`, `betclic_markets`.
- `analysis_results.stats_summary_json` is the shared DB enrichment surface used by S4, S5, and S6.
- `GateResultRepo.get_extended()` currently filters `UPPER(status) = 'EXTENDED'`, so DB persistence must preserve a status vocabulary that differentiates Extended Pool from approved picks.
- `pipeline_runs` exists and can hold step stats, but current coverage is partial; `validate_phase.py` still over-relies on legacy `pipeline_state` files instead of these DB-backed signals.
- `betclic_market_validation_{date}.json` is the current runtime sidecar expected by `coupon_builder.py`.

### Additional Context

- `validate_phase.py` currently hard-fails data/build validation on missing `betting/data/pipeline_state/pipeline_{date}.json`, uses stale step IDs like `s1a_discover`/`s1b_parallel`/`s1c_aggregate`, and tracks `s10_summary` instead of actual PDF output.
- `gate_checker.py` currently places Extended Pool entries in the JSON `extended_pool` bucket but still writes `status = "APPROVED"` on those entries before DB persistence.
- `db_data_loader.load_gate_results_from_db()` currently falls back to a dead JSON shape (`data.get("results", [])`) instead of the current nested `gate_results` structure.
- `check_48h_repeats.py` has no `--date` CLI even though `.github` orchestration artifacts currently document it that way.
- `.github/prompts/orchestrate-betting-day.prompt.md` still points S7.5 output to `betting/data/{date}_betclic_validation.json`, while runtime writes `betclic_market_validation_{date}.json`.
- `.github/internal-prompts/bet-enrich.prompt.md` and `.github/agents/bet-enricher.agent.md` still narrate obsolete S2.3a/S2.3b/S2.3c flows that write directly to `team_form`, which no longer matches the current runtime boundary around `run_scrapers.py`.
- `.github/internal-prompts/bet-gate.prompt.md` still claims 48h repeat checking is integrated into `gate_checker.py`, while the current runtime exposes it as a separate `check_48h_repeats.py` step.
- Several scripts now emit `AGENT_SUMMARY:{json}` despite older prompt guidance treating them as stdout-only: `tipster_aggregator.py`, `tipster_xref.py`, `build_shortlist.py`, `data_enrichment_agent.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, and `fetch_odds_multi.py`.
- Yesterday's rich-stat rollout means readiness must be judged by sport-specific richness and `team_form` usability, not only by non-zero enrichment logs or total row counts.

## Implementation Plan

### Phase 1: Align Bet-Orchestration Artifacts With Runtime Truth

#### Task 1.1 - [MODIFY] Align the top-level orchestrator prompt and agent with current step order and runtime contracts

**Description**: Update the bet-only orchestration entrypoints so the coordinator follows the same step map, filenames, CLI surface, and validation checkpoints that the runtime actually exposes today.

**Definition of Done**:

- [ ] `.github/prompts/orchestrate-betting-day.prompt.md` and `.github/agents/bet-orchestrator.agent.md` use the same current step order, including `S2 ∥ S2.3 -> S2.5` and explicit S7.5/S7.6/S8/S9/S10 sequencing.
- [ ] S7.5 filename guidance matches runtime: `betclic_market_validation_{date}.json`.
- [ ] S7.6 command guidance matches the real `check_48h_repeats.py` CLI or is updated in the same slice to match the new script contract.
- [ ] Prompt/agent validation guidance references live DB/file checks (`inspect_pipeline.py`, hardened `validate_phase.py`) instead of treating missing `pipeline_state` as authoritative failure.
- [ ] Touched files clearly distinguish scripts that emit `AGENT_SUMMARY:{json}` from scripts that require manual metric extraction from stdout.

#### Task 1.2 - [MODIFY] Refresh enrichment-side prompts and agents for post-rich-stat runtime assumptions

**Description**: Update enrichment-facing `.github` artifacts so they describe the current S2.3/S2.5 ownership boundary, bridge visibility, and rich-coverage gating instead of older bulk-enrichment paths.

**Definition of Done**:

- [ ] `.github/internal-prompts/bet-enrich.prompt.md` and `.github/agents/bet-enricher.agent.md` no longer present obsolete S2.3a/S2.3b/S2.3c team_form-writing steps as the current flow.
- [ ] Touched enrichment artifacts explicitly state that `run_scrapers.py` writes warehouse tables and that S3 readiness must be verified through `team_form`, bridge visibility, and rich-coverage reporting.
- [ ] The enrichment specialist workflow references current observability surfaces (`inspect_pipeline.py`, `db_report.py --report rich-coverage`, DB `team_form` checks) instead of stale assumptions.
- [ ] Analysis-only specialist behavior remains intact; no touched prompt tells the specialist to rerun the pipeline scripts.

#### Task 1.3 - [MODIFY] Refresh tipster/build/validation artifacts and remove bet-local execution contradictions

**Description**: Bring the remaining touched `.github` artifacts into session-readiness alignment, especially where they assume nonexistent outputs, wrong CLI flags, or contradictory execution/model guidance.

**Definition of Done**:

- [ ] `.github/internal-prompts/bet-tipsters.prompt.md` only expects structured outputs that the orchestrator can actually provide from the current scripts.
- [ ] `.github/internal-prompts/bet-validate.prompt.md`, `.github/agents/bet-builder.agent.md`, and any touched validation/gate prompts reflect the real S7.5 sidecar and the new S7.6 durable handoff.
- [ ] `.github/instructions/agent-execution-protocol.instructions.md` and any touched bet agent files no longer contain contradictory model/execution guidance that would change how today's session is orchestrated.
- [ ] All touched bet-local `.github` files stay within the bet repo and do not depend on copilot-collections edits.

### Phase 2: Make Readiness Verification Authoritative

#### Task 2.1 - [MODIFY] Replace legacy `validate_phase.py` assumptions with live session-readiness gates

**Description**: Rework `validate_phase.py` so it validates the current DB/file pipeline rather than an older `pipeline_state`-driven orchestration path.

**Definition of Done**:

- [x] Data-phase validation no longer hard-fails solely because `betting/data/pipeline_state/pipeline_{date}.json` is absent.
- [x] Step identifiers, recovery messages, and build-phase expectations align with the current S0-S10 workflow.
- [x] Validation covers current critical artifacts and contracts: market matrix, shortlist, S2/S2.3/S2.5 readiness, S3-S6 parity, S7 gate buckets, S7.5 sidecar, S7.6 handoff, S8 artifacts, S9 validation, and S10 output according to the agreed build policy.
- [x] Exit codes still preserve the blocking vs warning distinction expected by the orchestrator.
- [x] Focused regression tests cover DB-first, JSON-fallback, and mixed resume scenarios.

#### Task 2.2 - [MODIFY] Strengthen `inspect_pipeline.py` and `db_report.py` for post-enrichment session readiness

**Description**: Extend the existing observability scripts so they can prove whether yesterday's rich-stat rollout is actually usable by today's session.

**Definition of Done**:

- [x] `inspect_pipeline.py` reports S2.3 bridge/team_form readiness separately from scraper success.
- [x] `inspect_pipeline.py` reports DB-vs-JSON parity for the S3, S7, and S8 surfaces that can currently drift.
- [x] `db_report.py` rich-coverage output is sufficient to verify today's shortlist teams by sport without manual SQL.
- [x] The readiness story distinguishes `rich`, `baseline_only`, `partial`, and `no_data` and surfaces still-missing shortlist teams explicitly.

#### Task 2.3 - [MODIFY] Align `agent_protocol.py` and `agent_output.py` with current runtime contracts

**Description**: Update the declared protocol layer so prompts, agents, and scripts all describe the same step contracts and output expectations.

**Definition of Done**:

- [x] `agent_protocol.py` reflects the current step map and source-of-truth boundaries for S2 mutated shortlist handling, S2.3 bridge ownership, S4-S6 summary updates, S7 bucket semantics, S7.5 sidecar, S7.6 handoff, and S10 output.
- [x] Any AGENT_SUMMARY inventory or examples in the protocol match the scripts that actually emit structured summaries.
- [x] `agent_output.py` remains backward compatible while clarifying summary expectations for touched scripts.
- [x] Touched protocol declarations are sufficient for downstream implementation agents to reason about the updated readiness flow without rediscovery.

#### Task 2.4 - [MODIFY] Make S0 settlement and Betclic-learning readiness explicit before scan/build work

**Description**: Harden the readiness layer so settlement, decision-review, and Betclic-learning prerequisites are treated as first-class same-day gates rather than tribal knowledge in the prompt stack.

**Definition of Done**:

- [x] Touched orchestration and validation surfaces explicitly block a new session when the previous betting day has not been settled enough for learning and repeat-loss controls to be trustworthy.
- [x] Readiness output distinguishes missing settlement/learning prerequisites from later S1-S10 execution failures.
- [x] The solution reuses existing S0 scripts and artifacts (`settle_on_finish.py`, `evaluate_decisions.py`, `analyze_betclic_learning.py`, existing DB/ledger state) rather than introducing a second settlement workflow.
- [x] Focused tests or fixtures cover the expected blocking behavior for missing S0 readiness signals.

### Phase 3: Repair S7 Gate Round-Trip and Coupon Input Integrity

#### Task 3.1 - [MODIFY] Preserve explicit gate bucket semantics in `gate_checker.py`

**Description**: Change the S7 output contract so approved, Extended Pool, and rejected candidates remain distinct all the way through persistence.

**Definition of Done**:

- [x] `gate_checker.py` writes explicit bucket/status values that distinguish approved picks from Extended Pool and rejected picks.
- [x] Extended Pool reasons remain attached to candidates that are demoted for minimal data quality, synthetic data, insufficient markets, or similar watch-list conditions.
- [x] JSON and markdown outputs continue to present Extended Pool candidates in an R3-compliant way.
- [x] Focused tests cover candidates that move into Extended Pool through each current demotion path.

#### Task 3.2 - [MODIFY] Repair DB/JSON gate loading in `db_data_loader.py` and `GateResultRepo`

**Description**: Make DB-first and JSON-fallback gate loading consume the same status vocabulary and file structure.

**Definition of Done**:

- [x] `GateResultRepo` can load approved, extended, and rejected rows using the same persisted semantics written by `gate_checker.py`.
- [x] `load_gate_results_from_db()` understands the current nested `gate_results` JSON fallback structure instead of `data.get("results", [])`.
- [x] Loader output remains compatible with `coupon_builder.py` input expectations.
- [x] Round-trip tests cover DB-first resume, JSON fallback, and mixed cases where fixture IDs must be resolved or created.

#### Task 3.3 - [MODIFY] Make `coupon_builder.py` fail loudly on gate parity loss and preserve Extended Pool on resume

**Description**: Ensure S8 does not silently build from an incomplete gate universe when DB and JSON diverge.

**Definition of Done**:

- [x] `coupon_builder.py` reconstructs the same approved/extended/rejected counts from DB that S7 wrote, or it exits with an explicit blocking error.
- [x] Extended Pool candidates survive DB-first resume paths and remain visible in the build artifacts.
- [x] Builder metrics expose gate parity counts so validation/observability can assert the round-trip.
- [x] Focused tests cover DB-only resume, JSON fallback, and mismatch detection.

### Phase 4: Clarify S2.3/S2.5 Ownership and Preserve S3-S6 Candidate Parity

#### Task 4.1 - [MODIFY] Make scraper-to-`team_form` readiness visible across the S2.3/S2.5 boundary

**Description**: Expose whether scraper success actually improved S3-consumable stat coverage, without reopening yesterday's enrichment rollout.

**Definition of Done**:

- [x] Touched runtime scripts surface machine-readable metrics for scraper success, bridge execution, and resulting `team_form`/rich coverage.
- [x] Readiness checks can distinguish "warehouse improved" from "S3 ready" for the same date and shortlist scope.
- [x] No duplicate enrichment path is introduced; the fix only clarifies ownership and observability on top of the existing rollout.
- [x] The orchestrator can decide whether to proceed, bridge, or rely on S2.5 based on the new metrics.

#### Task 4.2 - [CREATE] Add a shared S3 candidate parity loader/checker for S4-S6

**Description**: Introduce one canonical candidate-loading helper so S4, S5, and S6 cannot silently diverge when DB persistence is partial.

**Definition of Done**:

- [x] A shared loader returns the candidate set together with source/parity metadata derived from S3 JSON and DB state.
- [x] `odds_evaluator.py`, `context_checks.py`, and `upset_risk.py` use the shared loader instead of incompatible ad hoc DB-/JSON-first rules.
- [x] Partial DB populations no longer silently narrow the working candidate universe; the step either preserves the JSON universe or exits with an explicit parity failure.
- [x] Focused tests cover full DB, partial DB, and JSON-only cases.

#### Task 4.3 - [MODIFY] Keep S3 dual-write and downstream summary updates consistent for gate/build consumers

**Description**: Tighten the handoff from `deep_stats_report.py` into S4-S6 and onward into S7 so candidate metadata needed by gate/build remains stable.

**Definition of Done**:

- [ ] `deep_stats_report.py` continues injecting `fixture_id` before JSON write and exposes enough metrics to verify how many candidates persisted.
- [ ] Downstream updates to `analysis_results.stats_summary_json` preserve candidate metadata needed by S7/S8 instead of overwriting or dropping it.
- [ ] Tipster, EV, context, and upset-risk enrichments round-trip into the same candidate universe.
- [ ] Observability surfaces expose candidate counts before and after each touched stage.

### Phase 5: Harden Pre-Coupon Controls and Verify Today's Run

#### Task 5.1 - [MODIFY] Standardize the S7.5 Betclic validation contract across script, builder, and orchestration docs

**Description**: Remove filename/path ambiguity and make the Betclic sidecar enforceable in the build path.

**Definition of Done**:

- [x] Runtime and touched bet `.github` docs both use `betclic_market_validation_{date}.json`.
- [x] `coupon_builder.py` applies one clear policy when the Betclic sidecar is missing or malformed for today's run.
- [x] Readiness/validation surfaces report whether the sidecar was present and actually consumed.
- [x] Focused tests cover present, missing, and malformed validation sidecars.

#### Task 5.2 - [CREATE] Add a durable S7.6 repeat-loss handoff consumed by S8

**Description**: Turn repeat-loss detection into a reusable runtime contract instead of a stdout-only advisory.

**Definition of Done**:

- [x] `check_48h_repeats.py` exposes a pipeline-compatible CLI and output contract that the orchestrator can call without undocumented arguments.
- [x] Repeat-loss findings persist in a machine-readable same-day artifact or equivalent canonical store.
- [x] `coupon_builder.py` can consume repeat-loss findings automatically and apply the existing rule set without relying on orchestrator memory alone.
- [x] Focused tests cover no-loss, matching-loss, and malformed-input cases.

#### Task 5.3 - [REUSE] Execute end-to-end readiness verification for today's run using the hardened bet surfaces

**Description**: Verify that the repaired contracts are sufficient for a same-day session without adding deployment or git workflow work.

**Definition of Done**:

- [ ] Verification covers settlement/learning readiness, S1-S2.5 artifacts, S3-S7 parity, S7.5/S7.6 handoffs, S8 build, S9 validation, and S10 output according to the agreed build policy.
- [ ] `inspect_pipeline.py` and hardened `validate_phase.py` both pass or classify non-blocking warnings clearly for the target date.
- [ ] Verification commands and expected failure interpretation are documented in implementation notes or tests, not left implicit.

#### Task 5.4 - [REUSE] Final code review by `tsh-code-reviewer`

**Description**: Run the final review after focused validation to catch residual contract drift and fail-open behavior.

**Definition of Done**:

- [ ] Review happens after the focused automated validation suite for the touched slices passes.
- [ ] Review explicitly checks DB/JSON parity, readiness-gate false positives, and fail-closed behavior for S7.5/S7.6.
- [ ] Any findings are fixed or tracked in the Changelog before the slice is considered complete.

## Security Considerations

- Fail closed when mandatory pre-coupon control artifacts are missing or malformed, especially S7.5 market validation and the new S7.6 repeat-loss handoff.
- Prefer `get_db()` and parameterized repository/database calls for touched persistence code. Do not add new raw `sqlite3` access in readiness-critical paths.
- Prevent silent state corruption by ensuring JSON fallbacks cannot override or narrow live DB state without explicit parity checks.
- Preserve auditability: gate bucket semantics, Betclic validation results, and repeat-loss exclusions must remain traceable in machine-readable artifacts or DB rows.
- Keep touched `.github` guidance consistent with allowed data-access patterns so orchestrators do not call nonexistent flags or unsafe ad hoc scripts during a live betting session.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [x] `validate_phase.py` validates the current pipeline from live DB/files and no longer false-fails on legacy `pipeline_state` alone.
- [x] Approved, Extended Pool, and rejected S7 results round-trip cleanly across `gate_checker.py`, DB persistence, JSON fallback, and `coupon_builder.py`.
- [x] S4, S5, and S6 preserve the intended S3 candidate universe or fail loudly on parity mismatch.
- [x] Scraper success is no longer mistaken for `team_form` readiness; rich coverage and bridge visibility are part of readiness gating.
- [x] S7.5 Betclic validation and S7.6 repeat-loss controls are both machine-consumable by S8.
- [x] Previous-day settlement and Betclic-learning prerequisites are enforced before the session proceeds into scan/build steps.
- [ ] Bet-local `.github` orchestration artifacts match actual script CLIs, filenames, outputs, and analysis-only boundaries.
- [ ] End-to-end readiness verification for today's run is executable from the hardened bet repo without relying on copilot-collections changes.
- [ ] Final code review passes with no unresolved contract-integrity findings.

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- Full model-routing normalization across every bet `.github` artifact, including files not touched by this readiness slice.
- Broader migration from hybrid DB/JSON operation to a single DB-only runtime.
- Comprehensive `pipeline_runs` instrumentation for every step beyond what is needed to fix today's readiness story.
- General cleanup of all remaining direct `sqlite3` usage outside the readiness-critical surfaces touched by this plan.
- Dashboard or UI surfacing of readiness metrics.

## Changelog

| Date   | Change Description |
| ------ | ------------------ |
| 2026-05-21 | Initial plan created |
| 2026-05-21 | Task 2.1 completed: `validate_phase.py` now uses live DB/file readiness gates instead of blocking on legacy `pipeline_state`, treats missing S10 PDF as warning-only per session policy, and adds focused DB-first / JSON-fallback / mixed-resume regression coverage. |
| 2026-05-21 | Task 2.4 completed: `validate_phase.py` now adds explicit S0 previous-betting-day settlement, decision-review, and Betclic-learning gates with separate S0-vs-S1-S10 blocking output, `inspect_pipeline.py` surfaces the same S0 readiness state in `inspect_s0`, and focused regressions cover unsettled previous-day state, missing decision outcomes, and S0 inspector reporting. |
| 2026-05-21 | Tasks 3.1-3.3 completed: `gate_checker.py` now persists explicit approved/extended/rejected semantics with preserved Extended Pool reasons, `db_data_loader.py`/`GateResultRepo` round-trip those buckets across DB and nested JSON fallback, and `coupon_builder.py` now blocks on S7 parity loss while exposing gate parity metrics in the S8 artifacts with focused regression coverage. |
| 2026-05-21 | Task 4.2 completed: added a shared S3 candidate parity loader in `db_data_loader.py`, switched `odds_evaluator.py`, `context_checks.py`, and `upset_risk.py` to the canonical loader, and added focused exact/subset/JSON-only regression coverage so partial DB persistence cannot silently narrow the S4-S6 candidate universe. |
| 2026-05-21 | Tasks 2.2 and 4.1 completed as one observability slice: `inspect_pipeline.py` now separates scraper warehouse activity from shortlist-scoped `team_form`/S3 readiness and reports S3/S7/S8 DB-vs-JSON parity, while `db_report.py --report rich-coverage` keeps fixture-scope totals and adds shortlist-by-sport bucket assignments plus explicit still-missing teams with focused regression coverage. |
| 2026-05-21 | Tasks 5.1 and 5.2 completed as one pre-coupon contract slice: `coupon_builder.py` now fails closed on missing/malformed `betclic_market_validation_{date}.json`, consumes S7.6 from the DB-backed `pipeline_runs[s7_6_repeat_loss_check]` handoff, records both controls as consumed in coupon JSON/summary, `check_48h_repeats.py` now exposes a `--date` pipeline CLI plus same-day artifact/DB persistence, and focused regression coverage verifies present/missing/malformed sidecars plus clear/matching/malformed repeat-loss cases. |
| 2026-05-21 | Task 2.3 completed: `agent_protocol.py` now documents the current S2 ∥ S2.3 -> S2.5 step map, canonical shortlist/bridge/summary-update/gate/sidecar/handoff/output boundaries, and a script-level AGENT_SUMMARY inventory that distinguishes AgentOutput payloads from manual summaries, while `agent_output.py` accepts `NO_BET` as a valid backward-compatible verdict with focused protocol regression coverage. |