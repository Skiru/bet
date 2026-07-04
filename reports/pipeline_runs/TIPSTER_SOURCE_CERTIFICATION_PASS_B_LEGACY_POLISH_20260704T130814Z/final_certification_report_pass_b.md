# Final Certification Report — Pass B Legacy Polish and Existing S2

## 1. Why Pass A missed ZawodTyper and Typersi

Pass A was scoped around the new v2 source registry and bundle paths. That registry covered selected v2 sources and kept `pickswise` as manual review only, but it did not include the canonical legacy Polish S2 sources from `src/bet/pipeline/tipster_sources.py`:

- `zawodtyper`
- `typersi`
- `betideas`

Because `scripts/pipeline_steps/s2_tipsters_v2.py` iterates `CORE_SOURCE_IDS` plus optional `RESEARCH_SOURCE_IDS`, any source absent from `src/bet/tipsters/source_registry.py` was invisible to v2 fixture runs and live-dry-run selection. That is why ZawodTyper and Typersi were omitted despite still being canonical legacy S2 sources.

## 2. Full legacy source inventory

See:

- `legacy_source_inventory.json`
- `legacy_source_inventory.md`

Key gap summary:

- `zawodtyper`: missing from v2 before Pass B
- `typersi`: missing from v2 before Pass B
- `betideas`: missing from v2 before Pass B
- `pickswise`: present only as manual-review entry, not legacy bridge-aware
- `sportsgambler`, `feedinco`, `bettingclosed`: already present in v2

## 3. ZawodTyper deep audit

See `zawodtyper_deep_audit.md`.

Bottom line:

- Legacy clearly treated ZawodTyper as a first-class source.
- It has dedicated public daily URL construction, dedicated XHR interception logic, dedicated payload parsing, tracked accuracy support, and existing parser fixture tests.
- The strongest field set comes from `NP_ajax.php` payload rows: event, teams, sport, pick type, odds, reasoning text, tipster name, accuracy metadata, and stats cited.
- Current v2 omitted it entirely before Pass B.
- Safe Pass B action is bridge-plus-registry visibility, not promotion.

## 4. Typersi audit

Typersi is canonical legacy S2 but materially weaker than ZawodTyper:

- Present in `tipster_sources.py` and `core_integration_contracts.py`
- No dedicated parser path in legacy S2
- Playwright path falls through to `_JS_EXTRACT_GENERIC`
- HTTP fallback falls through to `parse_generic_tipster_html`
- No Typersi-specific parser fixtures or v2 extractor

Result: Typersi should be retained and registered, but it still needs public fixture snapshots and source-specific parsing proof.

## 5. Robots probe results

See `robots_probe_legacy_sources.json`.

Observed highlights:

- `zawodtyper`: robots allowed the generated daily page; HTTP 200; local review missing; status `MANUAL_TERMS_REVIEW_REQUIRED`
- `typersi`: robots allowed `/`; HTTP 200; local review missing; status `MANUAL_TERMS_REVIEW_REQUIRED`
- `pickswise`: robots allowed configured URLs; some legacy URLs now 404 or redirect; local review missing; status `MANUAL_TERMS_REVIEW_REQUIRED`
- `betideas`: robots allowed configured URLs; some legacy `/tips/*` URLs redirect to `/betting-tipsters/*`, some 404; local review missing; status `MANUAL_TERMS_REVIEW_REQUIRED`
- `sportsgambler`: robots allowed; target redirected to `/betting-tips/`; local review still `manual_review_required`
- `feedinco`: robots blocked `*` for target probe; status `BLOCKED_BY_ROBOTS`
- `bettingclosed`: robots probe was inconclusive because `RobotFileParser.read()` hit connection reset despite `robots.txt` being fetchable via direct HTTP; status `ROBOTS_INCONCLUSIVE`

## 6. Legacy smoke result

No legacy live smoke was executed.

Reasons:

- `.venv-tipster-v2/bin/python scripts/tipster_aggregator.py --help` already fails on missing `requests`
- legacy ZawodTyper Playwright path inherits stealth and Cloudflare handling from `PlaywrightBaseClient`, which violates Pass B policy
- `scripts/pipeline_steps/s2_tipsters.py` has no source filter, so wrapper execution would overfetch if used directly

Artifacts:

- `legacy_zawodtyper_smoke_stdout.txt`
- `legacy_zawodtyper_smoke_stderr.txt`
- `legacy_zawodtyper_smoke_exit.txt`

Pass B smoke verdict: `LEGACY_SMOKE_BLOCKED_BY_STEALTH_POLICY`

## 7. Bridge implementation summary

Implemented:

- `src/bet/tipsters/legacy_bridge.py`
- `tests/tipsters/test_legacy_bridge.py`

Registry/doc updates:

- `src/bet/tipsters/source_registry.py`
- `docs/pipeline/TIPSTER_SCRAPER_V2_IMPLEMENTATION_BUNDLE.md`

Bridge behavior:

- converts legacy pick dict/object to v2 `TipsterPick`
- normalizes legacy source ids
- maps market family, direction, and line conservatively
- preserves odds as reference-only evidence
- preserves `accuracy_pct` as source-quality metadata only
- drops forbidden fields such as stake/coupon/EV/final-bet surfaces with warnings
- stamps evidence-only decision boundary via valuable signals and downstream legacy adapter compatibility
- does not add any legacy source to `CORE_SOURCE_IDS`

## 8. Test output

`pytest`:

- `33 passed, 2 warnings in 0.05s`
- warnings are existing pytest config warnings for `asyncio_default_fixture_loop_scope` and `asyncio_mode`

`compileall`:

- PASS with no output

## 9. Source decisions

See `source_status_decisions_pass_b.json`.

Decision summary:

- `zawodtyper`: `LEGACY_CONFIGURED_NEEDS_FIXTURE_SNAPSHOTS`
- `typersi`: `LEGACY_CONFIGURED_NEEDS_FIXTURE_SNAPSHOTS`
- `pickswise`: `MANUAL_REVIEW_ONLY`
- `betideas`: `MANUAL_REVIEW_ONLY`
- `sportsgambler`: `MANUAL_REVIEW_ONLY`
- `feedinco`: `BLOCKED_BY_ROBOTS`
- `bettingclosed`: `MANUAL_REVIEW_ONLY`

All promotions remain `false` in this pass.

## 10. Explicit safety assertions

During Pass B:

- stealth used: no
- CAPTCHA/Cloudflare bypass used: no
- login/auth/premium/VIP used: no
- private APIs used: no
- bookmaker redirects followed: no
- robots respected: yes
- EV/stake/coupon/final bet produced: no
- Superbet combined odds produced: no

## 11. Recommendation

This pass is safe to commit and merge as an audit-plus-bridge-preparation change set.

What it accomplishes safely:

- restores visibility of omitted legacy S2 sources in the v2 registry without promotion
- preserves ZawodTyper as a kept legacy candidate instead of silently dropping it
- adds a tested evidence-only bridge for legacy pick conversion
- documents why live legacy smoke was blocked rather than bypassing policy

What it does not claim:

- no compliant live certification of ZawodTyper or Typersi yet
- no production promotion of any legacy source
- no approval to use stealth/XHR interception in compliant v2 live fetch
