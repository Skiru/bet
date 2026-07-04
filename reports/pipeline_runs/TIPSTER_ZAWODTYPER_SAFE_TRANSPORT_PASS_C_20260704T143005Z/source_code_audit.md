# ZawodTyper Source Code Audit

This audit documents the findings from analyzing the legacy S2 code paths and the design of the safe Pass C transport for ZawodTyper.

## 1. URL Builder
The daily URL construction for ZawodTyper is defined in `scripts/tipster_aggregator.py:195-200` as `build_zawodtyper_url(date)`. It builds the daily URL using one canonical Polish slug template:
* **Template**: `https://www.zawodtyper.pl/typy-dnia-{day}-{month}-{weekday}/`
* **Polish Months**: `1: "stycznia"`, `2: "lutego"`, `3: "marca"`, `4: "kwietnia"`, `5: "maja"`, `6: "czerwca"`, `7: "lipca"`, `8: "sierpnia"`, `9: "wrzesnia"`, `10: "pazdziernika"`, `11: "listopada"`, `12: "grudnia"`
* **Polish Weekdays**: `0: "poniedzialek"`, `1: "wtorek"`, `2: "sroda"`, `3: "czwartek"`, `4: "piatek"`, `5: "sobota"`, `6: "niedziela"`

This logic was previously duplicated in `src/bet/api_clients/tipster_playwright.py:950-957`. In Pass C, this has been unified and placed cleanly into `src/bet/tipsters/zawodtyper.py` as `build_zawodtyper_daily_url(date)`.

## 2. XHR Endpoints Observed in Code
The primary legacy data pathway for ZawodTyper resides in `src/bet/api_clients/tipster_playwright.py:888-942` under the `_fetch_zawodtyper_via_xhr` function:
* **Endpoint Name/Path**: `NP_ajax.php`
* **HTTP Method**: `POST`
* **Type of Endpoint**: It is a **public-page XHR** endpoint. While anyone can load the website in a browser and trigger the Vue SPA AJAX call to retrieve structured bets, the endpoint is classified as an XHR endpoint rather than static public HTML. As such, direct HTTP fetching of this endpoint carries compliance risks and requires explicit review.

## 3. Parser Function & Expected Fields
The parser for intercepted `NP_ajax.php` JSON payloads is located in `src/bet/pipeline/tipster_parsers.py` as `parse_zawodtyper_xhr_bets()`.

### Expected Fields in Raw JSON Payload:
* `success`: boolean (must be `true`)
* `data`: list of bets/comments
* `comment_type`: string (filtered to `"bet"`)
* `match_name`: string (e.g., `"Polska - Niemcy"`, split to find `home_team` and `away_team`)
* `content`: string (analysis/reasoning)
* `discipline`: string (mapped via `DISCIPLINE_MAP` to find sport, e.g., `"Piłka Nożna"` -> `"football"`)
* `type`: string (market text, e.g., `"Obie strzelą (BTTS)"`)
* `rate`: float/string (odds)
* `author_name`: string (tipster's pseudonym)
* `author_stats`: object (containing `bet_count` and `ratio` to compute tipster accuracy)

In Pass C, the parsed results are seamlessly converted to compliant v2 `TipsterPick` structures through `legacy_bridge.convert_legacy_pick_to_v2()`.

## 4. Exact Stealth Dependency Path to Avoid
The legacy client `TipsterPlaywrightClient` inherits from `PlaywrightBaseClient` (`src/bet/api_clients/playwright_base.py`):
1. `PlaywrightBaseClient` injects anti-bot evasions:
   * Uses stealth browser arguments (`--disable-blink-features=AutomationControlled`).
   * Configures fake user agents and screen dimensions.
   * Utilizes the `playwright_stealth` library.
   * Performs Cloudflare challenge detection, waiting, and automatic retry loops.
2. In Pass C, we **absolutely avoid** this entire inheritance and import path. The safe transport uses standard python stdlib `urllib` or compliance-first `fetch_public_html` which does not contain stealth, bypasses, logins, or cookie handling.

## 5. Missing Source Selector Problem
In legacy S2, running the wrapper step `s2_tipsters.py` always triggers parallel aggregation for all configured sources. There is no built-in `--source` command-line argument. This makes testing individual safe transports extremely difficult and risks broad live scraping of uncertified sites.
Pass C addresses this by adding a `--source` filter in `s2_tipsters_v2_live_dry_run.py`, and providing a clean selector extension design in `legacy_source_selector_design.md` for the legacy scripts.
