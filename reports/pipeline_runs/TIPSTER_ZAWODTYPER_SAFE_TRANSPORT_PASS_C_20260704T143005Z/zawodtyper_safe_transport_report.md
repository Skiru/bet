# ZawodTyper Safe Transport Pass C Report

This report summarizes the implementation and results for the safe, compliance-first ZawodTyper shadow transport (Pass C).

## 1. Execution Metadata
* **Branch**: `feat/tipster-zawodtyper-safe-transport-pass-c`
* **Pass Date**: 2026-07-04
* **Step**: `TIPSTER_ZAWODTYPER_SAFE_TRANSPORT_PASS_C`
* **Directory**: `reports/pipeline_runs/TIPSTER_ZAWODTYPER_SAFE_TRANSPORT_PASS_C_20260704T143005Z`

## 2. Core Implementation
1. **Unification of URL Builder**: Added `build_zawodtyper_daily_url(date)` inside `src/bet/tipsters/zawodtyper.py` using the canonical Polish weekday and month slug maps.
2. **Safe, Direct Parser**: Added `extract_zawodtyper(doc)` in `src/bet/tipsters/zawodtyper.py` to parse both intercepted `NP_ajax.php` JSON payloads (for XHR-level testing/snapshots) and static public HTML pages (via robust tag-end matching that avoids cross-tag lazy matches).
3. **No Stealth/Playwright Imports**: Ensured no references to Playwright, headless browser wrappers, stealth evasions, login, premium or CAPTCHA/Cloudflare bypass libraries exist in the new transport.
4. **Extractor Integration**: Integrated the parser into `dispatch_extract` inside `src/bet/tipsters/extractors.py`.
5. **Live Dry-Run Selector**: Updated `s2_tipsters_v2_live_dry_run.py` to allow passing any registered source ID (like `zawodtyper`) to `--source`.

## 3. Security & Compliance Gates
* **Fail-Closed Gate**: Because `zawodtyper` is missing from `docs/pipeline/tipster_terms_review.local.json`, the dry-run execution safely skips live fetching:
  * Log: `[live-dry-run][zawodtyper] SKIP missing_required_review_flags:terms_reviewed,robots_reviewed,public_html_only,no_auth_no_premium_no_bypass`
  * Exit Code: `0`
  * Total Picks: `0`
  * SQLite Rows Saved: `0`
* **Evidence-Only Boundary**:
  * All parsed records convert seamlessly through the S2 legacy bridge (`convert_legacy_pick_to_v2()`).
  * Odds are strictly reference-only.
  * Tipster accuracy (`accuracy_pct`) is stored purely as source-quality metadata.
  * All picks are hardcoded to `decision_boundary=evidence_only_not_a_bet` and can never become final bets, coupons, or stakes.

## 4. Test Verification
All 41 unit tests in `tests/tipsters/` passed successfully (100% green rate):
```
41 passed, 2 warnings in 0.08s
```
Compilation check of all affected files succeeded with zero warnings or errors.
