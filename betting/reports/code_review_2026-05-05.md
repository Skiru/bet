# Code Review: Pipeline Bugfix Session (2026-05-04 → 2026-05-05)

**Reviewer:** GitHub Copilot (Claude Opus 4.6)  
**Commit scope:** 21 files, +2030/−118 lines  
**Tests:** 395 passed (20.07s)  
**Static analysis:** All files pass AST parsing, no syntax errors  

---

## Executive Summary

The bugfix session resolves 7 bugs that caused **0/100 candidates** to have stats data. The fixes are logically sound and well-targeted. Two issues require attention: a **race condition** (low severity, cosmetic impact) and a **significant test coverage gap** for the new parallel code.

| Verdict | Area |
|---------|------|
| ✅ PASS | Correctness of Bug 1–7 fixes |
| ✅ PASS | Security (no injection vectors) |
| ⚠️ WARN | Thread safety (cosmetic race condition in deep-link dedup) |
| ❌ FAIL | Test coverage for Bugs 2, 3, 5 (no dedicated tests) |
| ✅ PASS | Code quality and readability |
| ✅ PASS | Error handling |

---

## 1. Correctness Analysis

### Bug 1: FALLBACK_CHAINS missing sports ✅
**Fix:** Expanded from 8 to 14 sports, ESPN-first ordering, TheSportsDB + SerpAPI as universal fallbacks.

- Correct: All 14 pipeline sports now have chains.
- The `competition` kwarg pass-through with `TypeError` fallback is pragmatic — avoids forcing all clients to accept the kwarg.
- Minor: SerpAPI at the end of *every* chain means it could be hit for 14 sports × 2 teams × 1 H2H = 42 calls per full pipeline run if earlier sources fail. The 250/month limit may be exhausted in ~6 pipeline runs. **Recommendation:** Consider adding a `SerpAPI` call counter / daily budget cap.

### Bug 2: Cache key format mismatch ✅
**Fix:** Handle both bare (`corners`) and split (`corners_home`/`corners_away`) formats; sum for additive stats, keep home-only for percentages.

- Logic is correct: `round(home_val + away_val, 2)` for corners/fouls/cards, `home_val` for possession.
- Edge case handled: `isinstance(home_val, (int, float))` guard prevents crash on non-numeric cached values.
- The `_PERCENTAGE_STATS` set covers the right metrics.
- **Concern:** If cache has BOTH bare `corners` AND `corners_home`, the bare key wins (earlier `if` branch). This is correct behavior but undocumented.

### Bug 3: `has_data` flag gap ✅
**Fix:** `if not has_data and safety_input and safety_input.get("markets"): has_data = True`

- Simple and correct. Ensures candidates with API-derived safety data aren't falsely counted as "no stats".

### Bug 4: Relative CACHE_DIR ✅
**Fix:** `Path(__file__).parent.parent / "betting" / "data" / "stats_cache"`

- Standard pattern, resolves regardless of CWD. Clean fix.

### Bug 5: Scan timeout ✅
**Fix:** Reduced default delay 3s→0.5s, per-domain overrides, intra-domain parallelism.

- Correct: Rate-sensitive sites (betclic.pl=2.0s, hltv.org=2.0s) get higher delays.
- `PARALLEL_SAFE_DOMAINS` limits concurrency per domain (2–3 max). Reasonable.
- `_fetch_with_timeout` prevents individual stalled pages from blocking the entire scan.

### Bug 6: Duplicate work ✅
**Fix:** Skip-if-exists for odds, weather, market_matrix, shortlist.

- Correct: Checks file existence before running expensive steps.
- The `date_compact = date.replace("-", "")` for shortlist filename matches the shell script convention.

### Bug 7: Possession stat aggregation ✅
**Fix:** `_PERCENTAGE_STATS` set; percentage stats keep home-only instead of summing.

- Correct: `possession_home (58%) + possession_away (42%) = 100%` is meaningless. Home-only is the right signal for "this team dominates possession".
- Coverage: `shot_accuracy`, `pass_accuracy`, `cross_accuracy`, `long_ball_accuracy`, `tackle_accuracy` also included — all correct.

---

## 2. Thread Safety Analysis

### scan_events.py — `_scan_domain_group` parallelism

**Architecture:**
- Level 1: `scan_urls()` runs domain groups in parallel (up to 8 workers)
- Level 2: `_scan_domain_group()` runs intra-domain URLs in parallel (2–3 workers for safe domains)

**Race Condition Found (LOW severity):**

```python
# Line ~210 in _fetch_single_url (runs in thread):
new_links = [sl for sl in sub_links if sl not in urls and sl not in extracted]
```

The `extracted` dict is from the *parent scope* of `_scan_domain_group`. When `intra_workers > 1`, multiple threads execute `_fetch_single_url` concurrently. Each thread reads `extracted` to check for duplicates, but `extracted` is only updated *after* `future.result()` returns in the main loop (lines 248–254).

**Impact:** Two threads may both decide to deep-fetch the same sub-link because neither has updated `extracted` yet. Result: duplicate fetches (wasted bandwidth), not data corruption — the `extracted.update(deep_items)` call in the main thread will just overwrite with the last result.

**Recommendation:** For correctness purists, use a `threading.Lock` or a shared `set` for dedup:
```python
_seen_urls = set(urls)  # pre-populate
# In _fetch_single_url:
new_links = [sl for sl in sub_links if sl not in _seen_urls]
_seen_urls.update(new_links)  # not atomic, but GIL protects simple set ops
```

**Mitigating factors:**
- CPython GIL protects dict/set integrity for simple `in` checks
- Deep-link discovery only activates for 6 specific domains
- `max_deep_links=30` caps the blast radius
- Duplicate fetches waste time but don't corrupt data

### pipeline_orchestrator.py — `_run_parallel_enrichment`

**No issues found.** Tasks are fully independent (different API endpoints, different output files). No shared mutable state between `run_odds`, `run_odds_io`, `run_weather`, `run_tipsters`, `run_espn_enrichment`. The `candidates` list is only mutated by the value-bet injection loop within `run_odds_io`, but this task operates on its own candidates copy within the scope. Actually — wait:

**Potential concern in `_inject_ev_from_odds`:** The `for c in candidates:` loop within the `io_data.get("value_bets", [])` processing directly mutates candidates from the odds-api.io parsing. But this is called AFTER `_run_parallel_enrichment` completes (it's a separate function), so no race. ✅

### scan_events.py — `_fetch_with_timeout`

Creates a `ThreadPoolExecutor(max_workers=1)` per URL fetch call. Under full load: 8 domain workers × 3 intra-domain × 1 timeout thread = **24 concurrent threads** plus the timeout wrappers. For I/O-bound Playwright fetches this is acceptable, but it's worth noting the thread count.

---

## 3. Security Analysis

### Command Injection — `run_command()` ✅ SAFE

```python
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
    return False, f"Invalid date format: {date} (expected YYYY-MM-DD)"
cmd = cmd.replace("{date}", date)
```

- Date is validated with `fullmatch` (not `match`) before interpolation — no partial match bypass.
- All command strings are hardcoded literals in the codebase.
- `shlex.split()` used for non-bash commands prevents shell metachar injection.
- `shell=True` only when prefix is `bash ` (hardcoded in step definitions).
- The step definitions at line 937 come from internal config, not user input.

### File Path Injection — Not applicable
- All file paths are constructed from validated dates and hardcoded patterns.
- No user-supplied filenames or URL components are used in file I/O paths.

### JSON Parsing — Safe
- `json.loads()` is safe for untrusted input (no code execution).
- `try/except (json.JSONDecodeError, OSError)` properly handles corrupt files.

---

## 4. Error Handling

| Location | Handling | Assessment |
|----------|----------|------------|
| `_fetch_with_timeout` | Raises `TimeoutError` | ✅ Caller catches all Exceptions |
| `_fetch_single_url` | Returns error tuple on failure | ✅ No crash propagation |
| `run_espn_enrichment` | Broad `except Exception` | ✅ Acceptable for pipeline step |
| `enrich_fixture` fallback chain | `try/TypeError` for kwarg compat | ✅ Pragmatic |
| `_inject_ev_from_odds` | `except (json.JSONDecodeError, OSError): pass` | ✅ Graceful degradation |
| Parallel futures | `future.result()` in try/except | ✅ No unhandled futures |

**Missing:** No handling for partial writes in `run_espn_enrichment` — if `json.dumps` succeeds but `write_text` is interrupted (disk full, etc.), a truncated JSON file could cause downstream parse failures. **LOW risk** (local SSD, small files).

---

## 5. Test Coverage Assessment

### Covered ✅
- Fallback chain order change (test_fetch_api_stats.py — updated assertions)
- Basic `extract_team_stats` with bare keys (test_pipeline_modules.py)
- Full candidate analysis flow (test_pipeline_modules.py)

### NOT Covered ❌

| Bug | What's Missing | Priority |
|-----|---------------|----------|
| Bug 2 | Test with split-key cache format (`corners_home`/`corners_away`) | **HIGH** — core data path |
| Bug 3 | Test `has_data=True` when safety_input has markets but slug cache misses | **MEDIUM** |
| Bug 5 | No tests for `scan_events.py` at all (parallelism, timeout, domain delays) | **HIGH** — complex concurrent code |
| Bug 7 | No test for percentage stats keeping home-only value | **HIGH** — prevents regression |
| Bug 4 | No test for CACHE_DIR path resolution (but trivial to verify) | LOW |

### Recommended Test Additions

```python
# 1. Split-key format test for deep_stats_report.py
def test_extract_team_stats_split_keys():
    """Verify corners_home + corners_away are summed correctly."""
    cache = {"form": {"l10_avg": {"corners_home": 6.8, "corners_away": 3.2}}}
    # → result["l10_avg"]["corners"] should == 10.0

# 2. Percentage stats test
def test_extract_team_stats_percentage_keeps_home_only():
    """Possession should NOT sum home+away."""
    cache = {"form": {"l10_avg": {"possession_home": 58.0, "possession_away": 42.0}}}
    # → result["l10_avg"]["possession"] should == 58.0, NOT 100.0

# 3. has_data fallback test
def test_analyze_candidate_has_data_from_safety_input():
    """has_data=True when safety_input provides markets despite empty slug cache."""

# 4. scan_events timeout test
def test_fetch_with_timeout_raises_on_stall():
    """Verify TimeoutError raised when fetch exceeds PER_PAGE_TIMEOUT."""

# 5. Intra-domain parallel test
def test_parallel_domain_no_data_loss():
    """Verify all URLs are processed when using intra-domain parallelism."""
```

---

## 6. Code Quality

### Good ✅
- Clear naming: `_PERCENTAGE_STATS`, `PARALLEL_SAFE_DOMAINS`, `DOMAIN_DELAY_OVERRIDES`
- Minimal changes — each fix is targeted, no unnecessary refactoring
- Comments explain *why* (e.g., "sum home+away for additive stats... keep home-only for percentage")
- `_convert_espn_odds_to_decimal` is clean, handles all market types

### Minor Issues

1. **`_PERCENTAGE_STATS` defined inside function** (deep_stats_report.py:104): This constant is recreated every call. Move to module level.

2. **Hardcoded sport list in `run_espn_enrichment`** (pipeline_orchestrator.py:498):
   ```python
   for sport in ["football", "basketball", "hockey", "baseball"]:
   ```
   If ESPN adds tennis/MMA support, this needs manual update. Consider importing from the ESPN adapter's supported sports list.

3. **`max_deep_links` default changed 50→30** (scan_events.py:275): This is a behavior change that could reduce fixture discovery. Document the rationale.

4. **Default `workers` changed 6→8** (scan_events.py:275): Makes sense with the faster delays, but worth noting it increases parallel pressure on targets.

---

## 7. Edge Cases

| Scenario | Handling | Status |
|----------|----------|--------|
| Corrupt cache JSON | `except (json.JSONDecodeError, OSError)` returns empty result | ✅ |
| API returns non-numeric values | `isinstance(home_val, (int, float))` guard | ✅ |
| Empty odds_api_snapshot.json | Loop iterates empty list, no crash | ✅ |
| ESPN returns American odds = 0 | `_american_to_decimal` returns None (div-by-zero avoided) | ✅ |
| All fallback chains fail for a sport | `enrich_fixture` returns un-enriched fixture | ✅ |
| Cache has bare AND split keys | Bare key wins (earlier if-branch) | ✅ (implicit) |
| `new_links` filtering with stale `extracted` | Duplicate fetch at worst | ⚠️ Low |

---

## 8. Final Verdict

**APPROVE with minor findings.**

The fixes are correct, well-structured, and address real pipeline failures. The code is production-ready for a local betting pipeline. The thread safety issue is cosmetic (duplicate fetches, not data loss). The main action item is adding targeted tests for the split-key format and percentage stat handling to prevent regressions.

### Action Items (Priority Order)

1. **[HIGH]** Add test for split-key format (`corners_home`/`corners_away` → summed total)
2. **[HIGH]** Add test for percentage stats (possession keeps home-only)
3. **[MEDIUM]** Add basic test for `scan_events._fetch_with_timeout` behavior
4. **[LOW]** Move `_PERCENTAGE_STATS` to module level in `deep_stats_report.py`
5. **[LOW]** Add SerpAPI daily budget tracking to prevent 250/month exhaustion
6. **[LOW]** Document `max_deep_links` reduction rationale (50→30)
