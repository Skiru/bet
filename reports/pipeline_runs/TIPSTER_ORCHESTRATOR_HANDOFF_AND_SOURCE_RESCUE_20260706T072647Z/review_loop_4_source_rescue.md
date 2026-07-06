# Loop 4 — Source Rescue Matrix Review

## 1. Lazily Discarded Sources Check
- **Verification:** All 14 sources in the registry are assigned a dedicated rescue status and entry in the certification matrix.
- **Result:** PASS. No source is labeled as a simple scraping failure; instead, they are converted into fixture-only or manual-review candidates where appropriate.

## 2. Actionability of Next Passes
- **Verification:** Every source defines realistic, actionable passes:
  - `SPORTSGAMBLER_STATIC_PREVIEW_CERTIFICATION`
  - `WINDRAWWIN_STATIC_TABLE_CERTIFICATION`
  - `TYPERSI_PUBLIC_READ_AUDIT`
  - `FEEDINCO_SHADOW_NOISE_FILTER_AUDIT`
  - `BETTINGCLOSED_JS_PUBLIC_AUDIT`
  - `FOREBET_PREDICTZ_FIXTURE_SNAPSHOT_MAINTENANCE`
  - `PICKSWISE_OLBG_BETTINGEXPERT_MANUAL_REVIEW`
- **Result:** PASS.

## 3. Allowed Probe Types
- **Verification:** Probe types (`robots_only`, `static_http_head_get`, `fixture_snapshot`, `clean_network_observation`, `none`) are clearly specified to avoid violating Crawler/compliance boundaries.
- **Result:** PASS.

## 4. Priority Allocation
- **Verification:** Strategic prioritizing is used (e.g. ZawodTyper as P0, sportsgambler/windrawwin as P1, feedinco as P2, bettingexpert/olbg as P3), aligning development resources with standard value.
- **Result:** PASS.
