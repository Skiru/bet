# Project Refactor Plan — Pipeline & DB-first

This document captures the full, detailed plan for the refactor of the repository into a DB-first architecture and a modular betting pipeline. It accompanies PR #3 (refactor/pipeline-core) and is intended to be the single-source plan for implementing the rest of the refactor program.

Purpose
- Provide a clear, executable roadmap to convert the codebase into a DB-first, stage-separated pipeline with strong contracts, safe persistence, and testable adapters.
- Ensure the repository contains no scraping code and that any bookmaker adapters are explicit, credentialed, and injectable.
- Ensure all datetimes are timezone-safe and the betting-day semantics (Europe/Warsaw, local 06:00 → next day 06:00) are enforced consistently.

High-level goals
1. Canonical DB layer: one source of truth for artifacts, versioned outputs, and non-destructive writes.
2. Modular pipeline: ingestion → normalization → feature derivation → scoring → coupon builder → settlement. Each stage pure and side-effect free.
3. Orchestrator library: thin coordinator that calls pure stages, persists artifacts via repository layer, and enforces dry-run/write gating.
4. Adapter boundaries: explicit adapter interfaces and no scrapers in repository code.
5. Agents/skills separation: map runtime agents to bet/agents and reusable skills/workflows to skills/.
6. Observability, testing, and CI: structured logging, metrics hooks, full unit/integration tests, and CI gating.
7. Secure defaults: env-driven secrets, no credentials in repo, and safe CLI defaults (dry-run).

Assumptions
- Primary language: Python 3.10/3.11.
- Local development DB: SQLite (dev default). Production should use Postgres (future migration path documented).
- Betting timezone: Europe/Warsaw.
- Bookmaker: Betclic — adapter-only in repo; no scraping.

Program of work (PRs)
- PR 1 — refactor/db-first (done): canonical DB layer, SQLAlchemy models, repository API, migrations, and core tests.
- PR 2 — refactor/pipeline-core (this PR): pydantic contracts, pure stages (ingest/normalize/features/scoring/coupon/settlement), service runner, orchestrator library (dry-run default, writes gated), adapter base, and tests.
- PR 3 — refactor/adapters: add concrete adapter implementation stubs (credentialed externally), adapter tests, and adapter configuration documentation.
- PR 4 — refactor/agents-skills: separate agent logic and skill modules, add AgentExecutionPolicy to enforce run rules.
- PR 5 — infra/tests: add GitHub Actions for test/lint, pre-commit hooks, coverage enforcement.
- PR 6 — orchestrator CLI hardening & runbook: convert CLI into safe, confirmed-run tool with runbook and release notes.
- PR 7 — migration & compatibility: shims for legacy outputs, import scripts, and migration runbook.

File-level mapping (what to expect and why)
- bet/db/
  - connection.py — get_engine, sessionmaker, get_db() context manager.
  - models.py — ORM models (Fixture, MarketOdds, Artifact). Use DateTime(timezone=True), artifact versioning.
  - repository.py — all DB access (upsert_fixture, insert_market_odds, insert_artifact, mark_artifact_superseded, list_artifacts_for_day). Implement race-safe upserts and explicit created_at UTC stamps.
- bet/pipeline/
  - contracts.py — pydantic models (RawEvent, CanonicalFixture, FixtureFeatures, Signal, Coupon, SettlementPlan). No mutable defaults; validators to normalize event_time.
  - stages/
    - ingestion.py — calls adapter.fetch_events(date) → List[RawEvent], fetched_at set to UTC.
    - normalize.py — parse event_time (ISO/epoch/datetime), fallback policy, defensive team name mapping.
    - features.py — deterministic feature derivation.
    - scoring.py — scoring logic with clamped confidence and documented replacement points for ML.
    - coupon_builder.py — produce Coupon objects (serializable).
    - settlement.py — prepare settlement plans deterministically.
  - service.py — run_single_day_pipeline() returning ephemeral results for dry-run/testing.
- bet/orchestrator.py — run_pipeline_for_date(date, adapter, dry_run=True, allow_write=False, session_maker=None, agent_id=None). Transactional persistence; mark artifact UUIDs.
- scripts/pipeline_orchestrator.py — CLI; requires --adapter dotted path; defaults to dry-run.
- bet/adapters/base.py — BookmakerAdapter abstract interface (no scraping in repo).

Data & contract rules
- All datetimes entering pipeline are normalized to timezone-aware UTC before any comparisons or persistence.
- CanonicalFixture.event_time must be timezone-aware UTC. Validation accepts:
  - datetime with tzinfo (converted to UTC),
  - ISO-8601 string,
  - integer/float epoch seconds.
- Signals: pick is literal 'home'|'away'|'draw', confidence in [0,1].
- All artifacts persisted use insert_artifact() and carry schema_version and metadata including generator/agent id.

Betting-day rules
- Central util: bet/utils/time.py exposing betting_day_range(date_or_dt, tz="Europe/Warsaw") -> (start_utc, end_utc) where start is local 06:00 inclusive and end local next day 06:00 exclusive.
- Use this util for artifact day-bucketing and run scheduling boundaries.

Adapters
- Adapters must implement BookmakerAdapter.fetch_events(date) -> List[dict].
- Concrete adapters are not included in this repo (no scraping). Provide instructions and a secure pattern to implement credentials via environment or secret manager.

Orchestrator safety
- Default: dry-run True. Writes only with allow_write=True and dry_run=False.
- CLI requires --adapter dotted path to concrete adapter class; refuses to run otherwise.
- Writes to DB executed inside explicit transaction: try/except with commit on success and rollback on failure; DB session always closed.

Artifact versioning & migration
- insert_artifact always creates a new artifact row with uuid and schema_version; previous rows can be marked superseded via mark_artifact_superseded() (non-destructive).
- Migration strategy: import historic JSON/CSV outputs using compatibility shim scripts; verify artifact counts and sample payloads before flipping default usage.

Testing strategy
- Unit tests for each pure stage and contract validators (pydantic). Parametrized tests to cover ISO/epoch/datetime parsing.
- Integration tests for orchestrator in-memory: dry-run and allow-write modes, assert artifacts persisted and transactionality.
- DB tests: upsert race path, mark_artifact_superseded behavior, list_artifacts_for_day using UTC ranges.
- CI: GitHub Actions to run tests on PRs and pushes to main and the feature branches.

CI Linting & style
- Use black, isort, ruff (or flake8) and mypy for stricter type checks on public APIs.
- Add pre-commit hooks to enforce formatting and static checks.

Observability & logging
- Add minimal structured logging (JSON-friendly) and per-stage timing logs.
- Avoid sensitive data in logs.

Security & compliance
- No scraping code in repo.
- Adapters must use explicit credentials; provide .env.example and document secret-management pattern.

Developer runbook (local)
1. Checkout branch and install deps:
   - python -m venv .venv && source .venv/bin/activate
   - pip install -U pip setuptools
   - pip install sqlalchemy pydantic python-dateutil pytest
2. (Optional) run migrations:
   - export DATABASE_URL="sqlite:///./bet.db"
   - python scripts/run_migrations.py
3. Run tests:
   - pytest -q
4. Dry-run orchestrator using a MockAdapter in tests or a small script:
   - Use run_pipeline_for_date(date, mock_adapter, dry_run=True, allow_write=False)
5. To persist results locally for integration testing, use an in-memory DB sessionmaker or a local sqlite file and call run_pipeline_for_date(..., dry_run=False, allow_write=True, session_maker=SessionLocal).

Acceptance checklist before merging PRs
- [ ] All unit/integration tests pass locally and in CI.
- [ ] No mutable defaults present and all pydantic validators behave as expected.
- [ ] Orchestrator dry-run leaves DB untouched; allow-write persists artifacts with UUIDs.
- [ ] No adapter concrete scraping code present in the repo.
- [ ] Runbook added and README updated with pipeline diagram and run instructions.

Estimated effort & timeline
- DB-first + canonical models: completed (PR 1).
- Pipeline stages + orchestrator library: this PR (PR 2) — 2–5 days for full polishing & full test coverage.
- Adapters, agents/skills separation, CI: 1–2 weeks across the team depending on review velocity.

Next steps (recommended immediate actions)
1. Pull refactor/pipeline-core and run the test suite in your VS Code + Copilot setup.
2. Confirm behavior of CLI (with a mock adapter) and orchestrator persistence rules.
3. Review adapters strategy and create a secured adapter skeleton outside this public repo if needed.
4. Iterate on any failing tests in CI and push fixes to refactor/pipeline-core.

Contact & review notes
- This plan and the code in refactor/pipeline-core were reviewed and hardened for the main issues (timezone handling, mutable defaults, upsert races, transactional persistence, CLI adapter safety). The remaining step is running the test suite in your environment and addressing environment-specific issues (package versions, Python minor version differences).

---

If you want, I can also:
- Update the PR body for PR #3 to include this document verbatim.
- Add a .github/workflows/ci.yml to the branch to run pytest + format checks on the PR.
- Create a small secure adapter skeleton in a separate private repo or gist (outside this public repo) and provide instructions.

