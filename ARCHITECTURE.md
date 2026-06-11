# Project Architecture - Betting Pipeline

**Version:** 2.0  
**Last Updated:** 2026-06-10  
**Author:** Kilo

---

## Executive Summary

This document defines a modern, industry-standard reorganization for the betting pipeline project. The current structure suffers from:

1. **Namespace fragmentation** - Two parallel package hierarchies (`bet_core/` and `src/bet/`)
2. **Scattered pipelines** - Pipeline logic split across `scripts/`, `bet_core/pipeline/`, and `src/bet/pipeline/`
3. **Inconsistent naming** - `api_clients` vs `scrapers` mixing concerns
4. **Orphaned scripts** - 30+ pipeline scripts in `scripts/` with unclear ownership
5. **Test organization** - Tests mirror complex source layout instead of flat pytest layout

---

## Target Structure

```
bet/                              # Project root
├── src/
│   └── bet/                      # PRIMARY Python package (single entry point)
│       ├── __init__.py
│       ├── core/                 # Core business logic (from bet_core/)
│       │   ├── __init__.py
│       │   ├── config.py         # Configuration management
│       │   ├── exceptions.py     # Domain exceptions
│       │   └── orchestrator.py   # Pipeline orchestration
│       │
│       ├── domain/               # Domain models & business rules
│       │   ├── __init__.py
│       │   ├── models/           # Pydantic/ORM models
│       │   │   ├── __init__.py
│       │   │   ├── events.py     # Fixture, Match, Event
│       │   │   ├── odds.py       # Odds, Market
│       │   │   ├── picks.py      # Pick, Coupon, TipsterOpinion
│       │   │   └── stats.py      # MatchStats, TeamStats
│       │   ├── services/         # Domain services
│       │   │   ├── __init__.py
│       │   │   ├── tipster_aggregator.py
│       │   │   ├── odds_evaluator.py
│       │   │   └── gate_checker.py
│       │   └── repositories/     # Repository interfaces
│       │       └── __init__.py
│       │
│       ├── infrastructure/       # External integrations
│       │   ├── __init__.py
│       │   ├── api_clients/      # HTTP API clients
│       │   │   ├── __init__.py
│       │   │   ├── base.py       # BaseAPIClient, RateLimiter
│       │   │   ├── football/     # Sport-specific API clients
│       │   │   │   ├── api_football.py
│       │   │   │   ├── understat.py
│       │   │   │   └── football_data_org.py
│       │   │   ├── basketball/
│       │   │   │   ├── nba_api.py
│       │   │   │   ├── balldontlie.py
│       │   │   │   └── api_basketball.py
│       │   │   ├── hockey/
│       │   │   │   ├── nhl_api.py
│       │   │   │   ├── moneypuck.py
│       │   │   │   └── api_hockey.py
│       │   │   ├── tennis/
│       │   │   │   ├── tennis_abstract.py
│       │   │   │   └── sackmann.py
│       │   │   ├── volleyball/
│       │   │   │   └── api_volleyball.py
│       │   │   ├── odds/          # Odds-specific APIs
│       │   │   │   ├── odds_api_io.py
│       │   │   │   ├── serpapi.py
│       │   │   │   └── espn_odds.py
│       │   │   ├── multi/         # Multi-sport clients
│       │   │   │   ├── espn.py
│       │   │   │   ├── flashscore.py
│       │   │   │   └── sofascore.py
│       │   │   └── playwright/   # Playwright-based scrapers
│       │   │       ├── base.py
│       │   │       ├── oddsportal.py
│       │   │       └── tipster.py
│       │   │
│       │   ├── scrapers/          # HTML/Browser scrapers
│       │   │   ├── __init__.py
│       │   │   ├── base.py        # BaseScraper
│       │   │   ├── factory.py     # Scraper factory
│       │   │   ├── football/
│       │   │   │   └── fbref.py
│       │   │   ├── basketball/
│       │   │   │   ├── basketball_reference.py
│       │   │   │   └── nba_stats.py
│       │   │   ├── hockey/
│       │   │   │   └── hockey_reference.py
│       │   │   ├── tennis/
│       │   │   │   ├── atp_tour.py
│       │   │   │   └── jeff_sackmann.py
│       │   │   ├── volleyball/
│       │   │   │   └── volleybox.py
│       │   │   ├── esports/       # E-sports scrapers
│       │   │   │   ├── hltv.py
│       │   │   │   ├── vlr.py
│       │   │   │   └── gosugamers.py
│       │   │   └── market/        # Market validation
│       │   │       └── betclic.py
│       │   │
│       │   └── db/                # Database layer
│       │       ├── __init__.py
│       │       ├── connection.py
│       │       ├── models.py      # SQLAlchemy ORM models
│       │       ├── repositories.py # Repository implementations
│       │       ├── migrations/     # Alembic migrations
│       │       │   └── versions/
│       │       └── schemas/        # SQL schema files
│       │           └── schema.sql
│       │
│       ├── pipeline/              # Pipeline stages
│       │   ├── __init__.py
│       │   ├── state.py           # PipelineState class
│       │   ├── runner.py          # Execution orchestrator
│       │   └── stages/            # Individual stage implementations
│       │       ├── __init__.py
│       │       ├── s0_settlement.py    # Settlement
│       │       ├── s1_discovery.py     # Event discovery
│       │       ├── s2_tipsters.py      # Tipster aggregation
│       │       ├── s3_stats.py         # Statistical analysis
│       │       ├── s4_valuation.py     # Odds valuation
│       │       ├── s5_gate.py          # Gate checking
│       │       ├── s6_repeats.py       # Repeat detection
│       │       ├── s7_validation.py   # Market validation
│       │       └── s8_coupons.py       # Coupon building
│       │
│       └── utils/                 # Shared utilities
│           ├── __init__.py
│           ├── fuzzy_match.py
│           ├── resilience.py      # Retry/backoff logic
│           └── logging.py         # Structured logging
│
├── scripts/                      # CLI entry points (scripts, not library)
│   ├── __init__.py
│   ├── run_pipeline.py           # Single entry point for pipeline
│   ├── start_local_model.fish    # Local LLM server management
│   ├── stop_local_model.fish
│   └── healthcheck_local_model.fish
│
├── tests/                        # Flat pytest layout
│   ├── conftest.py
│   ├── unit/                     # Unit tests mirror src/bet structure
│   │   ├── core/
│   │   ├── domain/
│   │   ├── infrastructure/
│   │   └── pipeline/
│   └── integration/              # Integration tests
│       ├── api_clients/
│       ├── scrapers/
│       └── pipeline/
│
├── data/                         # Runtime data (gitignored)
│   ├── db/                       # SQLite databases
│   ├── cache/                    # API response cache
│   │   ├── espn/
│   │   ├── flashscore/
│   │   └── stats/
│   └── output/                   # Generated outputs
│       ├── coupons/
│       └── reports/
│
├── config/                       # Configuration files
│   ├── api_keys.json             # API credentials (gitignored)
│   ├── api_keys.example.json     # Example credentials
│   ├── betting_config.json       # Betting configuration
│   └── scan_urls.json            # Scan URLs config
│
├── docs/                         # Documentation
│   ├── architecture.md           # This file
│   ├── pipeline_guide.md         # Pipeline usage guide
│   └── api_reference.md          # API documentation
│
├── .kilo/                        # Kilo configuration (keep as-is)
├── pyproject.toml                # Project metadata & dependencies
└── README.md                     # Project overview

```

---

## Key Design Decisions

### 1. Single Package Namespace (`src/bet/`)

**Current Problem:**
- `bet_core/` and `src/bet/` both exist with overlapping functionality
- Import confusion: `from bet_core.db import ...` vs `from bet.db import ...`
- Both have `models.py`, `repositories.py`, causing duplication

**Solution:**
- Merge `bet_core/` into `src/bet/core/`
- Single entry point: `import bet`
- Clear hierarchy: `bet.core`, `bet.domain`, `bet.infrastructure`, `bet.pipeline`

### 2. Domain-Driven Structure

**Current Problem:**
- Business logic scattered across `scripts/` and package directories
- Models mixed with infrastructure code
- Services not clearly separated from API clients

**Solution:**
Domain-driven layers:
- **`domain/`** - Pure business logic (models, services, repository interfaces)
- **`infrastructure/`** - External integrations (APIs, scrapers, database)
- **`pipeline/`** - Pipeline orchestration and stages
- **`core/`** - Cross-cutting concerns (config, exceptions, orchestrator)

### 3. API Clients vs Scrapers Separation

**Current Problem:**
- `api_clients/` contains both HTTP API clients AND Playwright scrapers
- Scrapers scattered across sport subdirectories in both packages
- Inconsistent naming: `flashscore.py` in both `api_clients/` and `scrapers/`

**Solution:**
Clear separation by transport mechanism:
- **`infrastructure/api_clients/`** - HTTP-based APIs (REST, JSON responses)
- **`infrastructure/scrapers/`** - HTML/Browser-based scrapers (Playwright, BeautifulSoup)

### 4. Sport-Specific Subdirectories

**Current Problem:**
- `scrapers/` uses sport subdirs (`basketball/`, `football/`)
- `api_clients/` is flat with sport prefixes in filenames
- Inconsistent pattern: `nba_api_client.py` vs `basketball/nba_api_scraper.py`

**Solution:**
Consistent sport hierarchy in both:
```
api_clients/
├── football/
├── basketball/
├── hockey/
├── tennis/
└── volleyball/

scrapers/
├── football/
├── basketball/
├── hockey/
├── tennis/
└── volleyball/
```

### 5. Pipeline Scripts Consolidation

**Current Problem:**
- 32 scripts in `scripts/` directory
- Pipeline steps (`s0-s8`) are thin wrappers calling other scripts
- `_runner.py` utility buried in `scripts/pipeline_steps/`
- No clear entry point for running the pipeline

**Solution:**
- Move pipeline logic into `src/bet/pipeline/stages/`
- Keep only CLI entry points in `scripts/`
- Single `run_pipeline.py` entry point with stage selection

**Before:**
```bash
python scripts/pipeline_steps/s0_settler.py --date 2026-06-10
python scripts/pipeline_steps/s1_discover.py --date 2026-06-10
```

**After:**
```bash
python -m bet.pipeline run --stage s0 --date 2026-06-10
python -m bet.pipeline run --stage s1 --date 2026-06-10
# Or run all:
python -m bet.pipeline run --all --date 2026-06-10
```

### 6. Data Directory Standardization

**Current Problem:**
- `betting/data/` at root level (confusing next to `betting/coupons/`)
- Stats cache in `betting/data/stats_cache/`
- Databases in `betting/data/`
- No clear separation between runtime data and generated outputs

**Solution:**
Rename and relocate:
```
data/
├── db/              # SQLite databases
├── cache/           # API response cache
└── output/          # Generated outputs (coupons, reports)
```

### 7. Test Structure

**Current Problem:**
- Tests mirror the complex source structure
- `tests/scrapers/basketball/`, `tests/scrapers/football/`
- Root `tests/` directory has 73 test files mixed with test directories

**Solution:**
Flat pytest structure with semantic grouping:
```
tests/
├── unit/            # Unit tests by module
└── integration/     # Integration tests by concern
```

Each test file path mirrors the source:
- `src/bet/infrastructure/api_clients/football/api_football.py`
- `tests/unit/infrastructure/api_clients/football/test_api_football.py`

---

## Migration Plan

### Phase 1: Preparation (Risk: Low)
1. Create new directory structure (empty directories)
2. Create `__init__.py` files with proper exports
3. Update `pyproject.toml` with new package layout
4. Document current import usage (grep for `from bet.`, `from bet_core.`)

### Phase 2: Package Merge (Risk: Medium)
1. Move `bet_core/` → `src/bet/core/`
2. Move `bet_core/db/` → `src/bet/infrastructure/db/`
3. Move `bet_core/pipeline/` → `src/bet/pipeline/`
4. Update all imports: `from bet_core.` → `from bet.core.`

### Phase 3: Infrastructure Reorganization (Risk: Medium)
1. Create sport subdirectories in `api_clients/`
2. Move files by sport:
   - `api_clients/api_football.py` → `api_clients/football/api_football.py`
   - `api_clients/nba_api_client.py` → `api_clients/basketball/nba_api.py`
3. Update all imports referencing moved clients

### Phase 4: Pipeline Consolidation (Risk: High)
1. Extract logic from `scripts/*.py` into `src/bet/pipeline/stages/`
2. Create `src/bet/pipeline/runner.py` as orchestrator
3. Update `scripts/pipeline_steps/sN.py` to import from `bet.pipeline`
4. Create single entry point `scripts/run_pipeline.py`

### Phase 5: Data Relocation (Risk: Low)
1. Move `betting/data/` → `data/`
2. Move `betting/coupons/` → `data/output/coupons/`
3. Move `betting/journal/` → `data/output/journal/`
4. Update all file paths in code

### Phase 6: Test Restructure (Risk: Low)
1. Create `tests/unit/` and `tests/integration/` directories
2. Move test files to match new structure
3. Update `conftest.py` for new paths

---

## Import Migration Examples

### Current → Target

| Current Import | Target Import |
|----------------|---------------|
| `from bet_core.db import connection` | `from bet.infrastructure.db import connection` |
| `from bet_core.db.models import ...` | `from bet.domain.models import ...` |
| `from bet.db.repositories import ...` | `from bet.infrastructure.db.repositories import ...` |
| `from bet.api_clients.espn import ...` | `from bet.infrastructure.api_clients.multi.espn import ...` |
| `from bet.scrapers.basketball.bball_ref import ...` | `from bet.infrastructure.scrapers.basketball.basketball_reference import ...` |
| `from scripts.pipeline_steps import _runner` | `from bet.pipeline.runner import ...` |

---

## File Count Per Directory

| Directory | Current Files | Target Files |
|-----------|---------------|--------------|
| `scripts/` | 32 Python files | 4 CLI scripts |
| `src/bet/api_clients/` | 41 files (flat) | ~45 files (organized) |
| `src/bet/scrapers/` | 24 files (partial org) | ~24 files (full org) |
| `bet_core/` | 20 files | Merged into `src/bet/` |
| `tests/` | 73 test files | ~73 tests (reorganized) |

---

## Breaking Changes

### Import Paths
All imports will change. This is intentional to create a clean namespace.

### Configuration
- `betting_config.json` path unchanged
- Database path: `betting/data/betting.db` → `data/db/betting.db`
- Coupon output: `betting/coupons/` → `data/output/coupons/`

### Scripts
- `scripts/pipeline_steps/*.py` → `src/bet/pipeline/stages/*.py`
- Scripts become thin wrappers importing from `bet.pipeline`

---

## Compatibility Layer

To ease migration, add compatibility imports in old locations:

```python
# bet_core/__init__.py (deprecated)
import warnings
warnings.warn(
    "bet_core is deprecated, use bet.core instead",
    DeprecationWarning,
    stacklevel=2
)
from bet.core import *  # Re-export everything
```

This allows gradual migration with deprecation warnings.

---

## Validation Criteria

After migration, verify:
1. `pytest tests/` - All tests pass
2. `python -m bet.pipeline run --stage s0 --dry-run` - Pipeline stages work
3. `ruff check src/` - No linting errors
4. `mypy src/bet/` - Type checking passes
5. Import audit: `grep -r "from bet_core" src/ tests/` - Returns nothing
6. Import audit: `grep -r "from scripts\." src/ tests/` - Returns nothing

---

## Timeline Estimate

| Phase | Duration | Risk |
|-------|----------|------|
| Phase 1: Preparation | 2 hours | Low |
| Phase 2: Package Merge | 4 hours | Medium |
| Phase 3: Infrastructure Reorganization | 8 hours | Medium |
| Phase 4: Pipeline Consolidation | 12 hours | High |
| Phase 5: Data Relocation | 2 hours | Low |
| Phase 6: Test Restructure | 4 hours | Low |
| **Total** | **32 hours** | |

---

## References

- [Python Packaging User Guide - Src Layout](https://packaging.python.org/en/latest/discussions/src-layout/)
- [Real Python - Project Layout Best Practices](https://realpython.com/ref/best-practices/project-layout/)
- [Medium - The Cleanest Way to Structure Python Project in 2025](https://medium.com/the-pythonworld/the-cleanest-way-to-structure-a-python-project-in-2025-4f04ccb8602f)
- [KDnuggets - 5 Tips for Structuring Data Science Projects](https://www.kdnuggets.com/5-tips-structuring-data-science-projects)

---

## Appendix A: Current Directory Structure (Before)

```
bet/
├── bet_core/                    # OVERLAP: duplicates src/bet/
│   ├── db/                      # OVERLAP: duplicates src/bet/db/
│   │   ├── models.py           # DUPLICATE
│   │   ├── repository.py       # DUPLICATE  
│   │   └── connection.py       # DUPLICATE
│   ├── pipeline/               # OVERLAP: duplicates src/bet/pipeline/
│   └── utils/
├── betting/                     # CONFUSING: data directory not clearly named
│   ├── coupons/                # OUTPUT: should be in data/
│   ├── data/                   # RUNTIME: should be top-level
│   │   ├── betting.db          # DATABASE: should be data/db/
│   │   └── stats_cache/        # CACHE: should be data/cache/
│   ├── journal/                # OUTPUT: should be in data/
│   └── rules/
├── config/                      # OK: configuration directory
├── scripts/                     # PROBLEM: 32 files mixed purpose
│   ├── pipeline_steps/         # WRAPPERS: should import from src/
│   │   ├── s0_settler.py       # THIN: logic in scripts/*.py
│   │   ├── s1_discover.py
│   │   └── _runner.py          # UTILITY: buried in subdirectory
│   ├── *.py                    # LOGIC: should be in src/bet/
│   └── *.fish                  # OK: CLI scripts
├── src/                         # GOOD: src layout
│   └── bet/
│       ├── api_clients/        # FLAT: no sport organization
│       │   ├── api_football.py
│       │   ├── api_basketball.py
│       │   ├── nba_api_client.py  # INCONSISTENT: sport prefix in name
│       │   └── *.py            # MIXED: APIs + Playwright scrapers
│       ├── db/                 # OVERLAP: bet_core/db/
│       ├── scrapers/           # PARTIAL ORG: some sport dirs exist
│       │   ├── basketball/     # GOOD: sport subdir
│       │   │   └── bball_ref.py
│       │   ├── football/       # GOOD: sport subdir
│       │   │   └── fbref.py
│       │   └── *.py            # MIXED: sport-level scrapers
│       └── stats/              # OK: stats processing
└── tests/                       # OK: test directory
    ├── scrapers/
    │   ├── basketball/
    │   ├── football/
    │   └── ...
    └── *.py                    # MANY: 73 root test files
```

---

## Appendix B: Commands for Migration

### Audit Current Imports
```bash
# Find all bet_core imports
grep -r "from bet_core" src/ tests/ scripts/ > /tmp/bet_core_imports.txt

# Find all scripts imports
grep -r "from scripts\." src/ tests/ scripts/ > /tmp/scripts_imports.txt

# Find all api_clients imports
grep -r "from bet.api_clients" src/ tests/ scripts/ > /tmp/api_clients_imports.txt

# Find all scrapers imports  
grep -r "from bet.scrapers" src/ tests/ scripts/ > /tmp/scrapers_imports.txt
```

### Create New Structure
```bash
# Core directories
mkdir -p src/bet/core
mkdir -p src/bet/domain/models
mkdir -p src/bet/domain/services
mkdir -p src/bet/domain/repositories

# Infrastructure
mkdir -p src/bet/infrastructure/api_clients/{football,basketball,hockey,tennis,volleyball,odds,multi,playwright}
mkdir -p src/bet/infrastructure/scrapers/{football,basketball,hockey,tennis,volleyball,esports,market}
mkdir -p src/bet/infrastructure/db/{migrations,schemas}

# Pipeline
mkdir -p src/bet/pipeline/stages

# Utils
mkdir -p src/bet/utils

# Tests
mkdir -p tests/unit/{core,domain,infrastructure,pipeline}
mkdir -p tests/integration/{api_clients,scrapers,pipeline}

# Data
mkdir -p data/{db,cache,output}
```

### Move Files (Phase 2 - Package Merge)
```bash
# Move bet_core to src/bet/core
mv bet_core/*.py src/bet/core/
mv bet_core/utils/*.py src/bet/utils/

# Note: db/ and pipeline/ have duplicates - need manual merge
```

---

## Critical Review & Gaps

### Estimated Complexity vs Reality

**Document Claim:** 32 hours  
**Actual Complexity:**

| Metric | Count | Notes |
|--------|-------|-------|
| `from bet.api_clients` imports | **119** | Each needs manual update |
| `from bet.scrapers` imports | **117** | Each needs manual update |
| `from bet_core` imports | **87** | Each needs manual update |
| `from scripts.` imports | **19** | Low risk |
| Total import statements | **342** | **Manual edits required** |
| Python files in src/bet | **111** | Files to potentially move |
| Test files | **73** | Need path updates |

**Reality Check:** 342 import statements × 2-3 minutes each = **11-17 hours just for imports**  
Add: compilation testing, breaking changes, debugging = **20-30 hours realistic estimate**

### Gap #1: Duplicate Models Are Different

**Claim:** `bet_core/db/models.py` duplicates `src/bet/db/models.py`

**Reality:**
```
bet_core/db/models.py:  54 lines (1.9KB)
src/bet/db/models.py:   571 lines (13KB)
```

These are **NOT duplicates** - they're different files. `bet_core/db/models.py` is minimal.

**Impact:** Phase 2 is more complex - need to understand semantic differences, not just merge.

### Gap #2: Missing Migration Strategy for Kilo Config

**Claim:** `.kilo/` keep as-is.

**Reality:** `.kilo/prompts/bet-orchestrator.md` references:
- `scripts/pipeline_steps/sN.py`
- `src/bet.db.repositories`
- Import paths throughout

**Impact:** Kilo prompts must be updated alongside code migration.

### Gap #3: No Database Path Transition Plan

**Claim:** `betting/data/betting.db` → `data/db/betting.db`

**Missing:**
- What about existing production database?
- Migration script for moving data?
- Backwards compatibility for running pipeline during migration?

### Gap #4: Namespace Collision Risk

`bet_core.db.connection` and `bet.db.connection` both work currently.

After merge:
- Where does `bet_core/db/connection.py` go?
- Is it identical to `src/bet/db/connection.py`?
- Which one wins?

**Need:** File-by-file comparison matrix.

### Gap #5: Pipeline Scripts Have Side Effects

`scripts/*.py` files:
- Write to `betting/data/`
- Create state files
- Generate coupons

**Missing:** Migration must maintain exact output paths or break downstream consumers.

### Gap #6: File-by-File Comparison Matrix

| bet_core File | scripts File | Lines | Reality |
|---------------|--------------|-------|--------|
| `pipeline/stages/*.py` | `scripts/*.py` | 202 vs 8989 | **scripts has real logic** |
| `utils/time.py` | - | 31 | Only used by 2 scripts |
| `db/models.py` | - | 54 | Minimal, not used by pipeline |

**Critical Finding:** `bet_core/pipeline/stages/*.py` contains **28-line stubs** while `scripts/*.py` contains **thousands of lines** of real pipeline logic:

```
bet_core/pipeline/stages/ingestion.py:  28 lines
scripts/build_shortlist.py:           1686 lines

bet_core/pipeline/stages/scoring.py:   34 lines  
scripts/deep_stats_report.py:         2343 lines

bet_core/pipeline/stages/coupon_builder.py: 20 lines
scripts/coupon_builder.py:                    3820 lines
```

**Real Usage:**
- `bet_core` is only imported by **19 test files** (unit tests for stub code)
- **Real pipeline** runs via `scripts/*.py` → wrapped by `scripts/pipeline_steps/sN_*.py`

**Impact:** Phase 2 is **delete bet_core/**, not merge. The 6-8 hour estimate drops to 1-2 hours.

### Gap #7: No Incremental Migration Path

**Current plan:** All-or-nothing migration.

**Better approach:**
1. Create compatibility layer (`bet_core/__init__.py` re-exports from `bet.core`)
2. Migrate one module at a time
3. Run tests at each step
4. Keep old imports working via deprecation warnings

### Gap #8: Overparameterization

Proposed structure has 7+ layers of nesting:
```
src/bet/infrastructure/api_clients/football/api_football.py
```

Import: `from bet.infrastructure.api_clients.football.api_football import ...`

This is **excessive** for a 111-file codebase.

**Alternative:** Keep flatter structure:
```
src/bet/api_clients/football/api_football.py
src/bet/scrapers/football/fbref.py
```

### Gap #9: Playwright Scrapers Classification

**Claim:** Move Playwright-based scrapers to `infrastructure/scrapers/`

**Reality:** `api_clients/tipster_playwright.py`, `api_clients/oddsportal.py` are Playwright-based but currently in `api_clients/`.

**Question:** Should Playwright-based clients live in `scrapers/` or stay in `api_clients/playwright/`?

### Gap #10: Test Migration Complexity

Moving tests from:
```
tests/test_api_football.py
```

To:
```
tests/unit/infrastructure/api_clients/football/test_api_football.py
```

Requires:
- Move file
- Update imports
- Update `conftest.py` fixtures
- Update `pytest.ini` paths

---

## Recommended Simplified Approach

Based on the finding that `bet_core/db/` is a **stub** (not a duplicate), the priority order changes:

### Priority 1: Delete bet_core (High Value, Low Risk)
**Finding:** `bet_core/pipeline/stages/` contains 20-40 line stubs. Real logic is in `scripts/*.py`:

| Stub (`bet_core`) | Real Logic (`scripts`) | Lines Diff |
|-------------------|------------------------|------------|
| `stages/ingestion.py` | `discover_events.py`, `build_shortlist.py` | 28 vs 1686 |
| `stages/scoring.py` | `deep_stats_report.py` | 34 vs 2343 |
| `stages/coupon_builder.py` | `coupon_builder.py` | 20 vs 3820 |

**Action:**
1. Delete `bet_core/` - only 19 test imports, no production usage
2. Delete `tests/pipeline/test_stages.py` and related stub tests
3. Real pipeline runs via `scripts/pipeline_steps/sN_*.py` → `scripts/*.py`

**Estimated: 1-2 hours** (delete directory + remove tests)

### Priority 2: Organize api_clients by Sport (High Value, Medium Risk)
**Problem:** 41 files flat in `api_clients/` with inconsistent naming.

**Action:**
1. Create sport subdirs: `api_clients/football/`, `api_clients/basketball/`
2. Move files by sport pattern
3. Update 119 imports

**Estimated: 8-10 hours**

### Priority 3: Pipeline Scripts Consolidation (High Value, Medium Risk)
**Action:**
1. Extract logic from `scripts/*.py` into `src/bet/pipeline/stages/`
2. Keep thin wrappers in `scripts/pipeline_steps/`
3. Add single entry point

**Estimated: 10-12 hours**

### Priority 4: Skip Deep Nesting (Low Value, High Risk)
The proposed `infrastructure/` layer adds 4 characters to every import with no functional benefit.

**Recommendation:** Keep existing `src/bet/api_clients/` and `src/bet/scrapers/` organization, just add sport subdirs.

### Priority 5: Data Relocation (Low Value, Low Risk)
**Action:** Move `betting/data/` → `data/` after above phases complete.

**Estimated: 2-3 hours**

---

## GLM-5 Constraint Checklist

| Question | Answer | Impact |
|----------|--------|--------|
| Can GLM-5 handle 342 import edits? | Yes, with tool automation | Batch sed/find commands |
| Can GLM-5 test compilation? | Yes, via bash tool | Slow per-file checking |
| Can GLM-5 detect semantic conflicts? | **No** | Needs human review |
| Can GLM-5 estimate real effort? | **No** | This review provides it |
| Can GLM-5 do incremental migration? | **No** | Needs phased approach |
| Can GLM-5 understand stub vs real code? | **No** | Manual comparison required |

**Conclusion:** The 32-hour estimate was **badly wrong**. After finding that `bet_core/` is just stubs:

- **Priority 1:** Delete bet_core (1-2 hours)
- **Priority 2:** Organize api_clients by sport (8-10 hours)
- **Priority 3:** Pipeline consolidation (10-12 hours)
- **Priority 4:** Data relocation (2-3 hours)

**Total: 21-27 hours** - 30% reduction from original estimate.

The real insight is that the architecture document proposed a complex DDD structure for what is essentially:
1. A working pipeline in `scripts/*.py`
2. A stub directory `bet_core/` that should be deleted
3. Flat `api_clients/` that just needs sport subdirs

---

**END OF DOCUMENT**
