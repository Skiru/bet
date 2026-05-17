# Tipster Playwright Rewrite + DB-First Migration Plan

**Created:** 2026-05-17
**Status:** IN PROGRESS
**Scope:** Rewrite tipster data fetching to use Playwright, add proper DB schema/models/repo, update entire pipeline to DB-first

---

## Phase 1: DB Schema + Models + Repository [CRITICAL]

### Task 1.1 [MODIFY] — Add tipster tables to schema.sql
- **File:** `src/bet/db/schema.sql`
- Move `tipster_picks` and `tipster_consensus` from dynamic creation (`_ensure_tipster_tables` in tipster_aggregator.py) to schema.sql
- Add proper indexes (date, teams, sport, source_site)
- Bump SCHEMA_VERSION in schema.py from 8 → 9
- Add migration in schema.py for existing DBs

### Task 1.2 [MODIFY] — Add TipsterPick + TipsterConsensus models
- **File:** `src/bet/db/models.py`
- Add `TipsterPick` and `TipsterConsensus` dataclasses following existing patterns

### Task 1.3 [MODIFY] — Add TipsterRepo to repositories.py
- **File:** `src/bet/db/repositories.py`
- Add `TipsterRepo` class with:
  - `save_picks(date, picks)` — bulk insert with date cleanup
  - `save_consensus(date, entries)` — bulk insert with date cleanup
  - `get_picks_by_date(date)` → list[TipsterPick]
  - `get_consensus_by_date(date)` → list[TipsterConsensus]
  - `get_picks_for_event(date, home, away)` → list[TipsterPick]
- All SQL uses parameterized queries (R2)

### Task 1.4 [MODIFY] — Add migration for schema v8 → v9
- **File:** `src/bet/db/schema.py`
- Migration: tables already exist dynamically, so migration is just adding indexes and ensuring schema consistency

---

## Phase 2: Playwright Tipster Client [CORE]

### Task 2.1 [CREATE] — TipsterPlaywrightClient
- **File:** `src/bet/api_clients/tipster_playwright.py`
- Extends `PlaywrightBaseClient` (existing pattern in playwright_base.py)
- Methods:
  - `fetch_site(site_config, date) → list[TipsterPick]` — main entry point
  - Site-specific DOM extraction using `page.query_selector_all()`, `page.evaluate()`
  - `_extract_zawodtyper(page)` — parse structural HTML with proper selectors
  - `_extract_pickswise(page)` — parse __NEXT_DATA__ + rendered picks
  - `_extract_sportsgambler(page)` — parse match cards
  - `_extract_generic(page)` — fallback for unknown sites
  - `_extract_reasoning(page, element)` — deep reasoning extraction from DOM
  - `_extract_tipster_comments(page)` — find and extract expert analysis sections
- Features:
  - Stealth mode (playwright_stealth)
  - Cookie consent dismissal (inherited)
  - Cloudflare handling (inherited)
  - Circuit breaker (inherited)
  - Per-site wait times for JS content rendering
  - Structured data extraction from rendered DOM (not raw HTML regex)

### Task 2.2 [MODIFY] — Rewrite tipster_aggregator.py
- **File:** `scripts/tipster_aggregator.py`
- Replace `requests.get()` fetch() with TipsterPlaywrightClient
- Replace regex-based HTML parsers with Playwright DOM extraction
- Remove `_ensure_tipster_tables()` — now in schema.sql
- Use `TipsterRepo` for DB persistence instead of raw SQL
- Keep Gemini path as alternative (--use-gemini flag)
- Keep consensus computation and stats combination logic
- Keep AGENT_SUMMARY output format (R19)

---

## Phase 3: Pipeline DB-First Updates [ALIGNMENT]

### Task 3.1 [MODIFY] — Update tipster_xref.py to use TipsterRepo
- **File:** `scripts/tipster_xref.py`
- Replace raw SQL with `TipsterRepo.get_picks_by_date()`
- Keep JSON fallback as secondary path
- Use TipsterRepo.get_picks_for_event() for matching

### Task 3.2 [MODIFY] — Update agent_protocol.py
- **File:** `scripts/agent_protocol.py`
- Add tipster_picks and tipster_consensus to DB_SCHEMA_REFERENCE
- Update bet-scout agent config with new Playwright-based capabilities
- Update SELF_HEALING_REGISTRY with tipster modules

### Task 3.3 [MODIFY] — Update db_data_loader.py
- **File:** `scripts/db_data_loader.py`
- Add `load_tipster_picks_from_db(date)` function
- Add `load_tipster_consensus_from_db(date)` function

---

## Phase 4: Agent/Instruction/Skill Updates [DOCS]

### Task 4.1 [MODIFY] — Update source-registry.md
- **File:** `betting/sources/source-registry.md`
- Mark tipster sites as Playwright-based
- Update access notes with stealth/cookie handling

### Task 4.2 [MODIFY] — Update pipeline-knowledge-base.md
- **File:** `memories/repo/pipeline-knowledge-base.md`
- Add Playwright tipster migration notes

---

## Phase 5: Code Review + Security [QUALITY]

### Task 5.1 [REUSE] — Code review via tsh-code-reviewer
- Review all changed files for:
  - SQL injection (parameterized queries)
  - Resource leaks (browser/context cleanup)
  - Thread safety (Playwright is not thread-safe)
  - Error handling (graceful degradation)
  - R2 compliance (DB-first everywhere)
  - R19 compliance (AGENT_SUMMARY)
  - Security: no credential exposure, proper input sanitization

---

## Technical Context

### Existing Patterns
- `PlaywrightBaseClient` in `src/bet/api_clients/playwright_base.py` — circuit breaker, stealth, cookie dismiss, Cloudflare handling
- `TotalCornerClient` in `src/bet/api_clients/totalcorner.py` — extends PlaywrightBaseClient for DOM scraping
- `SofascoreClient` uses inline Playwright with stealth
- All DB repos follow same pattern: `__init__(conn)`, parameterized queries, dataclass models

### Key Constraints
- Playwright is NOT thread-safe — cannot use ThreadPoolExecutor for parallel fetching
- Must use sequential fetching or separate browser instances per thread
- Circuit breaker pattern essential for blocking tipster sites
- Per-site timeout must be enforced to prevent pipeline stalls
- Fish shell — no inline Python in terminal (R20)

---

## Changelog
- 2026-05-17: Plan created
