# Architecture Contract — Current State

This document defines the authoritative architectural contract and design constraints of the active production betting pipeline.

## 1. Current Package Layering

The codebase is organized as a clean, single-package architecture under `src/bet/`:

- `src/bet/core/`: Application settings, configurations, custom exceptions, and the core Orchestrator.
- `src/bet/domain/`: Pure domain models, Pydantic/SQLAlchemy schemas, and core services like name-matching and risk evaluation.
- `src/bet/infrastructure/`: Low-level data details including provider api clients, HTML scrapers, database connections, and migrations.
- `src/bet/pipeline/`: Pipeline state tracking and stage runners.
- `src/bet/utils/`: Shared utilities (fuzzy matching, resilience wrappers, logging, and metrics).

All CLI entrypoints reside in `scripts/`, referencing the library package rather than containing standalone domain logic.

## 2. Canonical Runner and Manifest

The sole entrypoint for orchestrating a daily run is:
`scripts/pipeline_steps/run_daily_pipeline.py`

This runner is fully driven by the canonical manifest:
`config/pipeline_manifest.json`

The manifest governs:
- Detailed sequence definitions (S0, S1, S1e, S2, S2.3, S2.5, S2.7, S2.9, S3, S4, S5, S6, S7, S7b, S8, S9, S10).
- Step phases (`DATA`, `ANALYSIS_BUILD`, `EXECUTION`, `POST_EVENT`).
- Strict linear step execution modes and their inputs/outputs.
- Global and step-level hard verification rules.

## 3. Artifact, Lock and Resume Infrastructure

- **Artifact Persistence**: Steps produce explicit JSON-serialized artifacts saved inside directories configured at runtime (`BET_PIPELINE_ARTIFACT_DIR`).
- **State and Checkpoints**: The pipeline utilizes structured checkpoints to save execution states under `.kilo/state/`. Checkpoints contain branch, HEAD, active RUN_ID, and progress metrics.
- **Lock Infrastructure**: Process safety is enforced by a file lease lock with process start identity to prevent overlapping or concurrent execution.
- **Resume Capabilities**: Runs may resume from any valid state if the previous step's output is verified. Unresolved command requests block a resume to guarantee strict run integrity.

## 4. DB Schema, Migration Authority, and Historical Migration versus Active Schema Distinction

- **DB Schema Authority**: Database structure is governed strictly by SQLite WAL schemas (`src/bet/db/schema.sql`).
- **Historical Migration versus Active Schema Distinction**: All retired operator code and old tables (such as Betclic) have been permanently retired.
- **Migration Isolation**: Migration `010_betclic_markets.sql` is retained as an immutable historical artifact. Migration `021_retire_betclic_schema.sql` cleans up and retires those tables during database bootstrap/upgrade. No active Python code import or runtime query references retired tables or views. Fresh bootstraps produce zero retired objects.

## 5. Provider Registry

Governed strictly by `config/provider_registry.json`. There are exactly four registered providers:
1. `oddspapi`
2. `the-odds-api`
3. `odds-api-io`
4. `api-football-odds`

All client adapters map to this registry for timeouts, total deadlines, retry counts, backoff policies, and credential redactions.

## 6. Seven-Agent and Four-Skill Control Plane

The agentic plane is configured statically in `.kilo/agents/` and `.kilo/skills/`:

### Agents (7 Consolidated Power Agents):
1. `bet-executor`: Pipeline script orchestrator with bash permission; no business mutation.
2. `bet-researcher`: Fixture/tipster/enrichment specialist (S0, S1, S1e, S2, S2.3, S2.5, S2.7, S2.9); no bash, no picks.
3. `bet-modeler`: Calibration & probability specialist (S3, S4); no bash.
4. `bet-risk-gatekeeper`: Motivation (S5), portfolio repeat guard (S6), and hard gate (S7) specialist; no bash.
5. `bet-builder`: Coupon pack & idea grouping generator (S8); no bash.
6. `bet-auditor`: Independent verification auditor (S7b); bash allowed for targeted tests only.
7. `bet-settler-postevent`: Historical settlement & post-match learning (S10); no bash.

All agents deny explicit model pins, inheriting the active Kilo UI model.

### Skills (4 Consolidated Skills):
1. `betting-pipeline-contract`
2. `betting-evidence-contract`
3. `betting-pipeline-runtime`
4. `context-safe-agentics`

## 7. Hard Boundaries (S7b / S8 / S9)

- **S7b Boundary**: Market availability validation maps names/lines only. Under no circumstances are manual operator quote values entered, scraped, or computed.
- **S8 Boundary**: Step S8 creates manual quote card coupon idea groups. It strictly warns about correlations but never computes combined Bet Builder odds.
- **S9 Boundary**: Strictly human-only. Synthetic, simulated, or automated approvals are invalid.
- **Generated-Data Policy**: Real-world factual evidence is never synthesized. Numbers, rosters, stats, or odds are never invented.

## 8. Run Lifecycle

The betting pipeline maintains a strict separation of concerns across its run lifecycle:
1. **Infrastructure Static Certification** (This task): Verifies static truth, validation graphs, filesystems, and configurations before any process starts.
2. **Bounded Runtime Preflight**: Validates connectivity, active database status, and transport layers.
3. **Full Pipeline Run**: Executes S0-S10 daily sequence.
