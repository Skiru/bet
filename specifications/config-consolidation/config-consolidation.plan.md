# Config Consolidation — Implementation Plan

**Date:** 2026-05-08  
**Scope:** Fix 10 critical configuration issues across the betting pipeline  
**Risk:** LOW — all changes are internal config plumbing, no user-facing behavior change  

---

## Summary of Issues

| # | Issue | Severity | Phase |
|---|-------|----------|-------|
| 1 | Sports list truncated to 7 | CRITICAL | 1 |
| 2 | `min_safety_score` has 4 conflicting values | HIGH | 1, 3 |
| 3 | `max_legs_per_coupon` conflicts | HIGH | 1, 3 |
| 4 | `preferred_odds_range` is dead config | LOW | 1, 2 |
| 5 | `min_coupons_per_day` semantic mismatch | MEDIUM | 2, 3 |
| 6 | Dead `scan_urls.json` values | LOW | 5 |
| 7 | Six missing config keys | HIGH | 2 |
| 8 | Three keys not in BettingConfig dataclass | MEDIUM | 1 |
| 9 | Timezone hardcoded in 10+ files | MEDIUM | 4 |
| 10 | `db_path` inconsistency | MEDIUM | 1, 3 |

---

## Phase 1: BettingConfig Dataclass Overhaul

**Goal:** Make `BettingConfig` accurately represent all config keys used by the pipeline.  
**Files:** `src/bet/config.py`, `tests/conftest.py`

### Task 1.1 — Remove `[:7]` sports truncation (Issue 1)

**[MODIFY]** `src/bet/config.py`  

Current (line 43):
```python
sports=raw.get("sports", [
    "football", "volleyball", "basketball", "hockey",
    "tennis", "snooker", "speedway",
])[:7],
```

Change to:
```python
sports=raw.get("sports", [
    "football", "volleyball", "basketball", "tennis",
    "hockey", "snooker", "speedway", "baseball",
    "esports", "darts", "table_tennis", "handball",
    "mma", "padel",
]),
```

**Definition of Done:**
- [ ] `[:7]` slice removed from `load()` method
- [ ] Default sports list contains all 14 sports in correct order (KEY sports first)
- [ ] `BettingConfig.load()` returns all 14 sports when loading from production config
- [ ] Unit test passes with 14 sports

### Task 1.2 — Remove `max_legs_per_coupon` hard cap (Issue 3)

**[MODIFY]** `src/bet/config.py`  

Current (line 36):
```python
max_legs_per_coupon=min(raw.get("max_legs_per_coupon", 3), 3),  # Hard cap
```

Change to:
```python
max_legs_per_coupon=raw.get("max_legs_per_coupon", 3),
```

Also update the dataclass field comment (line 14):
```python
max_legs_per_coupon: int  # Hard cap: 3
```
→
```python
max_legs_per_coupon: int
```

**Definition of Done:**
- [ ] `min(..., 3)` hard cap removed
- [ ] Comment `# Hard cap: 3` removed from dataclass field
- [ ] Config value flows through unmodified

### Task 1.3 — Remove `preferred_odds_range` (Issue 4)

**[MODIFY]** `src/bet/config.py`

Remove from dataclass:
```python
preferred_odds_range: tuple[float, float]
```

Remove from `load()`:
```python
odds_range = raw.get("preferred_odds_range", [1.30, 3.50])
```
and:
```python
preferred_odds_range=(odds_range[0], odds_range[1]),
```

**Definition of Done:**
- [ ] `preferred_odds_range` removed from `BettingConfig` dataclass fields
- [ ] Loading logic for `preferred_odds_range` removed from `load()` method
- [ ] No references to `preferred_odds_range` remain in `src/bet/config.py`

### Task 1.4 — Add 6 missing config keys to dataclass (Issue 7)

**[MODIFY]** `src/bet/config.py`

Add to dataclass fields (after `db_path`):
```python
low_risk_coupon_max_stake_pln: float
higher_risk_coupon_max_stake_pln: float
min_legs_per_coupon: int
max_same_sport_legs_in_coupon: int
low_risk_price_gap_threshold_pct: float
higher_risk_price_gap_threshold_pct: float
```

Add to `load()` method:
```python
low_risk_coupon_max_stake_pln=raw.get("low_risk_coupon_max_stake_pln", 3.0),
higher_risk_coupon_max_stake_pln=raw.get("higher_risk_coupon_max_stake_pln", 2.0),
min_legs_per_coupon=raw.get("min_legs_per_coupon", 2),
max_same_sport_legs_in_coupon=raw.get("max_same_sport_legs_in_coupon", 2),
low_risk_price_gap_threshold_pct=raw.get("low_risk_price_gap_threshold_pct", -2.0),
higher_risk_price_gap_threshold_pct=raw.get("higher_risk_price_gap_threshold_pct", -5.0),
```

**Definition of Done:**
- [ ] All 6 fields added to `BettingConfig` dataclass
- [ ] All 6 fields loaded in `load()` with correct defaults
- [ ] Defaults match current hardcoded values in scripts

### Task 1.5 — Add 3 coupon-limit keys to dataclass (Issue 8)

**[MODIFY]** `src/bet/config.py`

Add to dataclass fields:
```python
max_core_coupons: int
max_combo_coupons: int
max_singles: int
```

Add to `load()`:
```python
max_core_coupons=raw.get("max_core_coupons", 15),
max_combo_coupons=raw.get("max_combo_coupons", 20),
max_singles=raw.get("max_singles", 50),
```

**Definition of Done:**
- [ ] All 3 fields added to `BettingConfig` dataclass
- [ ] All 3 fields loaded in `load()` with correct defaults matching `betting_config.json`

### Task 1.6 — Update `min_safety_score` default (Issue 2)

**[MODIFY]** `src/bet/config.py`

The config.py default of 0.60 conflicts with the JSON value of 0.45. The JSON is authoritative. Change the fallback default to match:

Current (line 39):
```python
min_safety_score=raw.get("min_safety_score", 0.60),
```

Change to:
```python
min_safety_score=raw.get("min_safety_score", 0.45),
```

Also update the comment (line 17):
```python
min_safety_score: float  # Default: 0.60
```
→
```python
min_safety_score: float
```

**Definition of Done:**
- [ ] Default changed from 0.60 to 0.45
- [ ] Comment `# Default: 0.60` removed
- [ ] JSON value (0.45) remains authoritative

### Task 1.7 — Update test fixture (all issues)

**[MODIFY]** `tests/conftest.py`

Update the `config()` fixture (lines 225-240) to match the new dataclass:

```python
@pytest.fixture
def config():
    """BettingConfig with test defaults."""
    return BettingConfig(
        bankroll_pln=50.0,
        daily_exposure_range=(5.0, 15.0),
        max_stake_pln=2.0,
        max_legs_per_coupon=3,
        min_coupons_per_day=3,
        min_safety_score=0.45,
        timezone="Europe/Warsaw",
        sports=[
            "football", "volleyball", "basketball", "tennis",
            "hockey", "snooker", "speedway", "baseball",
            "esports", "darts", "table_tennis", "handball",
            "mma", "padel",
        ],
        db_path=":memory:",
        low_risk_coupon_max_stake_pln=3.0,
        higher_risk_coupon_max_stake_pln=2.0,
        min_legs_per_coupon=2,
        max_same_sport_legs_in_coupon=2,
        low_risk_price_gap_threshold_pct=-2.0,
        higher_risk_price_gap_threshold_pct=-5.0,
        max_core_coupons=15,
        max_combo_coupons=20,
        max_singles=50,
    )
```

**Definition of Done:**
- [ ] `preferred_odds_range` removed from fixture
- [ ] All new fields added with correct test defaults
- [ ] Sports list has all 14 sports
- [ ] `min_safety_score` set to 0.45
- [ ] All existing tests pass with updated fixture

---

## Phase 2: JSON Config Updates

**Goal:** Align `betting_config.json` with the dataclass and add missing keys.  
**Files:** `config/betting_config.json`

### Task 2.1 — Remove `preferred_odds_range` from JSON (Issue 4)

**[MODIFY]** `config/betting_config.json`

Remove:
```json
"preferred_odds_range": [1.3, 3.5],
```

**Definition of Done:**
- [ ] Key removed from JSON
- [ ] No script references `preferred_odds_range` from config dict (verified via grep)

### Task 2.2 — Add 6 missing keys to JSON (Issue 7)

**[MODIFY]** `config/betting_config.json`

Add after `"max_singles": 50`:
```json
"low_risk_coupon_max_stake_pln": 3.0,
"higher_risk_coupon_max_stake_pln": 2.0,
"min_legs_per_coupon": 2,
"max_same_sport_legs_in_coupon": 2,
"low_risk_price_gap_threshold_pct": -2.0,
"higher_risk_price_gap_threshold_pct": -5.0
```

**Definition of Done:**
- [ ] All 6 keys present in `betting_config.json`
- [ ] Values match the defaults scripts currently hardcode

### Task 2.3 — Add `max_picks_per_day` key (Issue 5)

**[MODIFY]** `config/betting_config.json`

Add a dedicated key for the maximum number of picks per day:
```json
"max_picks_per_day": 50
```

This separates the "minimum coupons to produce" concept (`min_coupons_per_day: 3`) from the "maximum picks cap" concept (`max_picks_per_day: 50`). The current `min_coupons_per_day` value of 3 stays — it means "try to produce at least 3 coupons". The new `max_picks_per_day` replaces the semantic misuse in `aggregate_and_select.py`.

50 is chosen because R3 (NO AUTO-REJECTION) means we should never artificially cap picks — the user decides. This is effectively "no practical cap" while still having a safeguard.

**Definition of Done:**
- [ ] `max_picks_per_day` key added to JSON
- [ ] `min_coupons_per_day` retained with value 3 (it has a different semantic)

---

## Phase 3: Script Reads Alignment

**Goal:** Make scripts read config values instead of using conflicting hardcodes.  
**Files:** `scripts/coupon_builder.py`, `scripts/aggregate_and_select.py`, `scripts/agent_protocol.py`

### Task 3.1 — Fix `coupon_builder.py` default for `max_legs_per_coupon` (Issue 3)

**[MODIFY]** `scripts/coupon_builder.py`

Three locations hardcode default `4` for `max_legs_per_coupon`:

Line 396:
```python
max_legs = config.get("max_legs_per_coupon", 4)
```
→
```python
max_legs = config.get("max_legs_per_coupon", 3)
```

Line 561:
```python
def _merge_orphan_legs(orphans: list, coupons: list, max_same_sport: int, bankroll: float = 50.0,
                       max_legs: int = 4):
```
→
```python
def _merge_orphan_legs(orphans: list, coupons: list, max_same_sport: int, bankroll: float = 50.0,
                       max_legs: int = 3):
```

Line 568:
```python
def _try_insert_into_coupon(pick: dict, coupons: list, max_same_sport: int, bankroll: float = 50.0,
                            max_legs: int = 4):
```
→
```python
def _try_insert_into_coupon(pick: dict, coupons: list, max_same_sport: int, bankroll: float = 50.0,
                            max_legs: int = 3):
```

Line 690:
```python
max_legs = config.get("max_legs_per_coupon", 4)
```
→
```python
max_legs = config.get("max_legs_per_coupon", 3)
```

**Definition of Done:**
- [ ] All 4 occurrences of `default 4` for max_legs changed to `3`
- [ ] Value matches `betting_config.json` value of 3

### Task 3.2 — Fix `coupon_builder.py` hardcoded `min_safety_score` (Issue 2)

**[MODIFY]** `scripts/coupon_builder.py`

Line 1834:
```python
"min_safety_score": 0.55,
```
→
```python
"min_safety_score": config.get("min_safety_score", 0.45),
```

Note: Verify that `config` dict is in scope at line 1834. If not, the `0.55` should be changed to `0.45` as a static fallback matching the JSON config.

**Definition of Done:**
- [ ] Hardcoded `0.55` replaced with config read or aligned fallback `0.45`
- [ ] No hardcoded `min_safety_score` values remain in `coupon_builder.py` that conflict with config

### Task 3.3 — Fix `aggregate_and_select.py` semantic mismatch (Issue 5)

**[MODIFY]** `scripts/aggregate_and_select.py`

Line 424:
```python
max_picks = config.get("min_coupons_per_day", 5)
```
→
```python
max_picks = config.get("max_picks_per_day", 50)
```

**Definition of Done:**
- [ ] `min_coupons_per_day` no longer misused as `max_picks`
- [ ] New key `max_picks_per_day` read with default 50
- [ ] Pick allocation is no longer artificially capped at 5

### Task 3.4 — Fix `agent_protocol.py` text conflicts (Issues 3, 10)

**[MODIFY]** `scripts/agent_protocol.py`

Fix max legs text (line 286):
```python
"Build core portfolio: unique event per coupon, max 8 legs",
```
→
```python
"Build core portfolio: unique event per coupon, max legs per config (default 3)",
```

Fix same text at line 486:
```python
"1. Build core coupons from STRONG+MODERATE picks — 1 event per coupon, max 8 legs",
```
→
```python
"1. Build core coupons from STRONG+MODERATE picks — 1 event per coupon, max legs per config",
```

Fix db_path (line 32):
```python
"db_path": "src/bet/db/betting.db (SQLite)",
```
→
```python
"db_path": "betting/data/betting.db (SQLite)",
```

**Definition of Done:**
- [ ] All "max 8 legs" references updated to reference config
- [ ] `db_path` text matches actual path `betting/data/betting.db`
- [ ] No conflicting guidance in agent_protocol.py text

---

## Phase 4: Timezone Utility

**Goal:** Eliminate hardcoded `"Europe/Warsaw"` across 10+ scripts.  
**Files:** `src/bet/config.py` (add utility), 10+ script files

### Task 4.1 — Create timezone utility function

**[MODIFY]** `src/bet/config.py`

Add at module level (after the `BettingConfig` class):
```python
from zoneinfo import ZoneInfo

def get_timezone() -> str:
    """Return configured timezone string. Reads from config, falls back to Europe/Warsaw."""
    try:
        cfg = BettingConfig.load()
        return cfg.timezone
    except Exception:
        return "Europe/Warsaw"

def get_tz() -> ZoneInfo:
    """Return configured timezone as ZoneInfo object."""
    return ZoneInfo(get_timezone())
```

**Definition of Done:**
- [ ] `get_timezone()` returns timezone string from config
- [ ] `get_tz()` returns `ZoneInfo` object
- [ ] Graceful fallback to `"Europe/Warsaw"` if config can't load

### Task 4.2 — Update scripts to use timezone utility

**[MODIFY]** Each of the following files — replace `ZoneInfo("Europe/Warsaw")` with import + call:

| File | Lines | Current | New |
|------|-------|---------|-----|
| `scripts/pipeline_summary.py` | 37, 42 | `ZoneInfo("Europe/Warsaw")` | `get_tz()` |
| `scripts/pipeline_orchestrator.py` | 512, 643, 1346, 1423, 1487, 1587, 1594 | `ZoneInfo("Europe/Warsaw")` | `get_tz()` |
| `scripts/scan_events.py` | 147 | `ZoneInfo("Europe/Warsaw")` | `get_tz()` |
| `scripts/tipster_aggregator.py` | 763, 920 | `ZoneInfo("Europe/Warsaw")` | `get_tz()` |
| `scripts/agent_protocol.py` | 567 | `ZoneInfo("Europe/Warsaw")` | `get_tz()` |
| `scripts/coupon_builder.py` | 394 | `config.get("timezone", "Europe/Warsaw")` | Keep (already reads config) |
| `scripts/fetch_weather.py` | 96 | `"timezone": "Europe/Warsaw"` | Keep (API parameter, not internal) |

For each script, add import:
```python
from bet.config import get_tz
```

Then replace:
```python
ZoneInfo("Europe/Warsaw")
```
with:
```python
get_tz()
```

**Note:** `coupon_builder.py` (line 394) already reads timezone from config dict — no change needed. `fetch_weather.py` (line 96) sends timezone to an external API — keep as-is.

**Definition of Done:**
- [ ] All internal `ZoneInfo("Europe/Warsaw")` usages replaced with `get_tz()`
- [ ] Import added to each modified file
- [ ] `coupon_builder.py` and `fetch_weather.py` left unchanged (already correct)
- [ ] All scripts still function correctly (no circular imports)

---

## Phase 5: Dead Config & DB Path Cleanup

**Goal:** Remove unused config values, align DB path.  
**Files:** `config/scan_urls.json`, `config/betting_config.json`, `src/bet/db/connection.py`

### Task 5.1 — Document dead `scan_urls.json` values (Issue 6)

**[MODIFY]** `config/scan_urls.json`

Add a top-level note marking `timeout_minutes`, `max_deep_links`, `dedicated_sources` as reference-only:

Change the description field:
```json
"description": "Scan URLs grouped by sport for per-sport scanners"
```
→
```json
"description": "Scan URLs grouped by sport for per-sport scanners. NOTE: timeout_minutes, max_deep_links, dedicated_sources are reference metadata — scanners use their own hardcoded values per sport-scanning skill."
```

**Rationale:** Removing these values would be a larger diff touching all 14 sport blocks. They serve as documentation of intended scanning parameters even though scanners don't read them. Marking them as reference-only is the pragmatic fix.

**Definition of Done:**
- [ ] Description updated to note reference-only status
- [ ] No scanner code changed (values remain unused as before)

### Task 5.2 — Align DB path in `connection.py` (Issue 10)

**[MODIFY]** `src/bet/db/connection.py`

Current (lines 12-14):
```python
DEFAULT_DB_PATH = (
    Path(__file__).parent.parent.parent.parent / "betting" / "data" / "betting.db"
)
```

This computes the path as `<repo>/betting/data/betting.db` by traversing from `src/bet/db/connection.py` up 4 levels. Verify this resolves correctly:
- `connection.py` is at `src/bet/db/connection.py`
- `.parent` = `src/bet/db/`
- `.parent.parent` = `src/bet/`
- `.parent.parent.parent` = `src/`
- `.parent.parent.parent.parent` = repo root

This is actually correct — it does resolve to `<repo>/betting/data/betting.db`. The issue is just the agent_protocol.py text saying `src/bet/db/betting.db` which is wrong. That is fixed in Task 3.4.

No code change needed in `connection.py`. Mark this sub-issue as resolved by Task 3.4.

**Definition of Done:**
- [ ] Verified `connection.py` DEFAULT_DB_PATH resolves to `betting/data/betting.db` ✓
- [ ] `agent_protocol.py` text fixed in Task 3.4 ✓

---

## Phase 6: Validation

**Goal:** Verify all changes work together.

### Task 6.1 — Run existing tests

```bash
cd /Users/mkoziol/projects/bet && python3 -m pytest tests/ -x -q
```

**Definition of Done:**
- [ ] All existing tests pass
- [ ] No import errors from circular dependencies (Phase 4 timezone utility)

### Task 6.2 — Verify config loads correctly

```bash
cd /Users/mkoziol/projects/bet && python3 -c "
from bet.config import BettingConfig, get_timezone, get_tz
cfg = BettingConfig.load()
print(f'Sports: {len(cfg.sports)} — {cfg.sports}')
print(f'max_legs_per_coupon: {cfg.max_legs_per_coupon}')
print(f'min_safety_score: {cfg.min_safety_score}')
print(f'max_core_coupons: {cfg.max_core_coupons}')
print(f'min_legs_per_coupon: {cfg.min_legs_per_coupon}')
print(f'timezone: {get_timezone()}')
print(f'tz: {get_tz()}')
assert len(cfg.sports) == 14
assert cfg.max_legs_per_coupon == 3
assert cfg.min_safety_score == 0.45
assert not hasattr(cfg, 'preferred_odds_range')
print('ALL CHECKS PASSED')
"
```

**Definition of Done:**
- [ ] 14 sports loaded
- [ ] `max_legs_per_coupon` = 3 (no hard cap)
- [ ] `min_safety_score` = 0.45
- [ ] `preferred_odds_range` not present
- [ ] All 6 new keys accessible
- [ ] Timezone utility returns correct value

### Task 6.3 — Grep for remaining conflicts

```bash
# Verify no remaining preferred_odds_range usage
grep -r "preferred_odds_range" scripts/ src/ --include="*.py"

# Verify no remaining [:7] truncation
grep -n "\[:7\]" src/bet/config.py

# Verify no "max 8 legs" in agent_protocol
grep -n "max 8 legs" scripts/agent_protocol.py

# Verify db_path text
grep -n "src/bet/db/betting.db" scripts/agent_protocol.py
```

**Definition of Done:**
- [ ] Zero results from all grep checks

---

## Dependency Graph

```
Phase 1 (dataclass) ──→ Phase 2 (JSON) ──→ Phase 3 (script reads)
                                              ↓
Phase 4 (timezone utility) ←──────────────────┘
                                              ↓
Phase 5 (cleanup) ←───────────────────────────┘
                                              ↓
Phase 6 (validation) ←────────────────────────┘
```

Phases 1-3 are sequential (each depends on prior). Phase 4 can be done after Phase 1. Phase 5 can be done after Phase 3. Phase 6 is last.

---

## Files Modified Summary

| File | Changes |
|------|---------|
| `src/bet/config.py` | Remove `[:7]`, remove `min()` cap, remove `preferred_odds_range`, add 9 fields, fix default, add timezone utility |
| `config/betting_config.json` | Remove `preferred_odds_range`, add 7 keys |
| `tests/conftest.py` | Update fixture to match new dataclass |
| `scripts/coupon_builder.py` | Fix 4× default `4`→`3`, fix hardcoded `0.55`→config read |
| `scripts/aggregate_and_select.py` | Fix `min_coupons_per_day` misuse → `max_picks_per_day` |
| `scripts/agent_protocol.py` | Fix "max 8 legs" text, fix db_path text |
| `scripts/pipeline_summary.py` | Use `get_tz()` |
| `scripts/pipeline_orchestrator.py` | Use `get_tz()` (7 locations) |
| `scripts/scan_events.py` | Use `get_tz()` |
| `scripts/tipster_aggregator.py` | Use `get_tz()` (2 locations) |
| `config/scan_urls.json` | Update description to note reference-only fields |

**Total:** 11 files, ~50 individual edits
