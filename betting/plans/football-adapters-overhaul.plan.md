# Football Adapters Overhaul Plan

## Summary

Systematic improvement of all 10 football-relevant Playwright HTML adapters and 1 API client adapter in the betting pipeline. The overhaul fixes 2 weak adapters (soccerway, whoscored), enhances 4 moderate adapters (soccerstats, betexplorer, oddsportal, sofascore), improves 3 good adapters (totalcorner, forebet, flashscore), adds verbose logging to all, and updates supporting infrastructure (deep_link_discovery, live test harness, SKILL.md).

**Priority alignment:** R5 (Stats Over Outcomes) — every improvement prioritizes extracting statistical fields (corners, cards, fouls, shots) over outcome fields (winner, score).

**Downstream contract:** All adapter output flows through `normalize_adapter_output()` in `scripts/adapters/__init__.py`, which maps adapter-specific keys to the `ENRICHED_EVENT_DEFAULTS` schema. Any new fields must either map to existing schema keys or be stored in `raw`.

## Technical Context

### Adapter Interface Contract

```python
def parse(html: str, url: str) -> List[Dict]
```

**Minimum required fields:** `home`, `away`, `time`, `source_url`, `source_type`, `raw`

**Football-enriched fields (when available):**
- `league`, `sport`, `country` — event context
- `corners`, `cards`, `fouls`, `shots` — statistical markets (R5 priority)
- `match_url` — deep-link for per-match detail fetching
- `match_id` — external ID for cross-source matching
- `odds` — pre-match odds (dict with `w1`, `x`, `w2`)
- `standings` — league position (`home_pos`, `away_pos`)
- `predictions` — probability data (Forebet)
- `status`, `is_live`, `score_home`, `score_away`, `period_scores` — live state

### Normalization Layer

`scripts/adapters/__init__.py` defines `ENRICHED_EVENT_DEFAULTS` (lines 81-124) and `normalize_adapter_output()` (lines 125-220). This function:
- Maps legacy field names (`home_team` → `home`, `kickoff` → `time`, `competition` → `league`)
- Maps `sofascore_id` → `match_id`, `detail_url` → `match_url`
- Merges `corners`, `cards`, `fouls`, `shots` dicts from adapter output
- Copies Forebet-specific keys (`forebet_probs`, `forebet_prediction`, etc.)
- Stores full original event in `raw`

**Key:** New fields that match `ENRICHED_EVENT_DEFAULTS` keys are auto-copied. Non-matching fields are preserved in `raw` for downstream access.

### DB Schema (relevant tables)

- `fixtures` — `id`, `external_id`, `sport_id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff`, `status`, `score_home`, `score_away`, `source`
- `match_stats` — `fixture_id`, `team_id`, `stat_key`, `stat_value`, `source` (keys: `corners`, `fouls`, `yellow_cards`, `shots`, `shots_on_target`, `possession`)
- `team_form` — `team_id`, `stat_key`, `l10_values`, `l5_values`, `l10_avg`, `l5_avg`, `h2h_values`
- `odds_history` — `fixture_id`, `bookmaker`, `market`, `selection`, `odds`, `line`

### Call Chain

```
scan_events.py → fetch(url) → get_adapter(domain) → adapter.parse(html, url) → normalize_adapter_output() → save to JSON / DB
```

---

## Tasks (ordered by dependency)

### Phase 1: Fix Weak Adapters

These adapters currently produce minimal usable data. Fixing them adds 2 additional football data sources to the pipeline.

---

- [ ] **Task 1.1** [MODIFY] `scripts/adapters/soccerway_adapter.py` — Rewrite with Soccerway-specific DOM parsing

  **File:** `scripts/adapters/soccerway_adapter.py`

  **Current state:** Generic table parsing with heuristic team name detection. No stats, no country extraction, unreliable match_url. Falls back to `raw_parse` frequently.

  **Changes:**

  1. **Add country extraction from URL path.** Soccerway URLs follow `/national/{country}/{league}/` pattern.
     ```python
     def _extract_country_from_url(url: str) -> str:
         # Pattern: /national/england/premier-league/ → "England"
         m = re.search(r'/national/([a-z-]+)/', url)
         if m:
             return m.group(1).replace('-', ' ').title()
         # Pattern: /international/{tournament}/ → ""
         return ""
     ```

  2. **Add competition extraction from URL and page headers.** Parse `<h1>` or breadcrumb elements containing league names. Also extract from URL path segments.

  3. **Improve match row detection.** Soccerway uses `<tr>` elements with specific data attributes. Target:
     - `tr` with class containing `match` or with `data-timestamp` attribute
     - `td` cells with class `score-time` (time/score), `team-a` (home), `team-b` (away)
     - Alternative: `td` with `<a>` links containing `/teams/` in href for team names

  4. **Add reliable match_url extraction.** Look for `<a>` tags with `href` matching `/matches/YYYY/MM/DD/{slug}/` within each match row. Prefix with `https://int.soccerway.com` if relative.

  5. **Add `country` field to output dict.**

  6. **Populate `sport: "football"` always** (Soccerway is football-only).

  **Expected output fields after change:** `home`, `away`, `time`, `score`, `league`, `country`, `sport`, `match_url`, `source_url`, `source_type`, `raw`

  **Definition of done:**
  - [ ] Adapter extracts ≥80% of matches from `https://int.soccerway.com/matches/2026/05/12/`
  - [ ] `country` field populated for ≥90% of matches (from URL path or league header)
  - [ ] `match_url` populated for ≥90% of matches (absolute URL to match detail page)
  - [ ] `league` field populated for ≥95% of matches
  - [ ] No regressions: existing tests still pass
  - [ ] Fallback to `raw_parse` only when both strategies fail

---

- [ ] **Task 1.2** [MODIFY] `scripts/adapters/whoscored_adapter.py` — Rewrite for React SPA with __NEXT_DATA__ parsing

  **File:** `scripts/adapters/whoscored_adapter.py`

  **Current state:** Generic class-regex matching (`stage-header`, `home`, `away`) that fails on WhoScored's actual React DOM. Falls back to table parsing which also yields little.

  **Changes:**

  1. **Add `__NEXT_DATA__` JSON parsing as primary strategy.** WhoScored embeds page data in a `<script id="__NEXT_DATA__">` tag. Parse this JSON to extract:
     ```python
     def _parse_next_data(soup: BeautifulSoup, url: str) -> List[Dict]:
         script = soup.find("script", id="__NEXT_DATA__")
         if not script:
             return []
         data = json.loads(script.string)
         # Navigate: data["props"]["pageProps"]["matchList"] or similar
         # Extract: teams, time, league, stats from structured JSON
     ```
     - The exact JSON path depends on the page type (`/LiveScores` vs `/Matches/{date}`)
     - Extract: home, away, time, league, match_url (from match slug), match_id

  2. **Add Playwright-aware wait selectors (documented for scan_events.py callers).** WhoScored needs extra wait time for React hydration. Add a module-level constant:
     ```python
     PLAYWRIGHT_WAIT_SELECTOR = "[class*='MatchesList'], [class*='matchCard']"
     PLAYWRIGHT_EXTRA_WAIT_MS = 5000
     ```

  3. **Improve HTML fallback parsing.** If `__NEXT_DATA__` is absent (some WhoScored pages don't use it), use better CSS selectors for the rendered DOM:
     - Match containers: `div[class*="MatchCard"]`, `div[class*="matchRow"]`
     - Home team: `span[class*="home-team"]`, `[data-team-side="home"]`
     - Away team: `span[class*="away-team"]`, `[data-team-side="away"]`
     - Stats (if visible): Elements with `class*="stat"` containing corners/shots/possession text

  4. **Add match_url construction.** WhoScored match URLs follow `/Matches/{match_id}/Live/{slug}` pattern. Construct from match ID if available.

  5. **Add `league`, `country` extraction.** From `__NEXT_DATA__` JSON structure or from DOM elements with `class*="tournament"` or `class*="region"`.

  **Expected output fields after change:** `home`, `away`, `time`, `league`, `country`, `sport`, `match_url`, `match_id`, `source_url`, `source_type`, `raw`; optionally `corners`, `shots`, `possession` when visible in DOM

  **Definition of done:**
  - [ ] `__NEXT_DATA__` strategy extracts matches from `https://www.whoscored.com/LiveScores` when data is present
  - [ ] HTML fallback uses WhoScored-specific selectors (not generic regexes)
  - [ ] `match_url` populated when match IDs are available
  - [ ] `league` populated for ≥80% of matches
  - [ ] Stats extraction works when WhoScored shows per-match stat rows (possession, shots, corners)

  **Risk:** WhoScored's DOM/data structure changes frequently. The `__NEXT_DATA__` approach is more stable than HTML scraping but still fragile. Document the expected JSON paths clearly in comments.

---

### Phase 2: Enhance Moderate Adapters

These adapters work but are missing fields that downstream consumers need.

---

- [ ] **Task 2.1** [MODIFY] `scripts/adapters/soccerstats_adapter.py` — Add match_url, country, per-match links

  **File:** `scripts/adapters/soccerstats_adapter.py`

  **Changes:**

  1. **Add `match_url` extraction.** SoccerStats match rows may contain `<a>` links to team pages or match detail pages. Look for:
     - `<a>` tags in team name cells with `href` containing team slugs
     - SoccerStats uses URL patterns like `https://www.soccerstats.com/pmatch.asp?league={code}&match={id}`
     - Extract from any `<a>` in the row where `href` contains `pmatch` or `match`

  2. **Add `country` extraction.** Parse from:
     - League header text: "England - Premier League" → split on " - " → first part = country
     - URL parameter: `?league=england` → country = England
     - Page `<title>` tag often contains country name

  3. **Add per-match stat page link discovery.** SoccerStats has per-match pages (`pmatch.asp`) with detailed stats. Store these in `match_url` for deep fetching.

  4. **Ensure `source_type: "soccerstats"` is consistent** (currently uses both `source_type` and legacy `source` key — standardize).

  **Expected output fields after change:** `home`, `away`, `time`, `league`, `country`, `sport`, `match_url`, `corners`, `cards`, `fouls`, `stats`, `source_url`, `source_type`, `raw`

  **Definition of done:**
  - [ ] `country` populated for ≥80% of matches (from league header or URL)
  - [ ] `match_url` populated when per-match links exist in rows
  - [ ] Removed duplicate `source`/`url` keys (only `source_url` + `source_type`)

---

- [ ] **Task 2.2** [MODIFY] `scripts/adapters/betexplorer_adapter.py` — Add sport detection, country extraction

  **File:** `scripts/adapters/betexplorer_adapter.py`

  **Changes:**

  1. **Add sport detection from URL.** BetExplorer uses `/soccer/`, `/tennis/`, `/basketball/` etc. in URL paths:
     ```python
     def _detect_sport(url: str) -> str:
         url_lower = url.lower()
         sport_map = {"soccer": "football", "tennis": "tennis", "basketball": "basketball",
                      "volleyball": "volleyball", "hockey": "hockey"}
         for path_seg, sport in sport_map.items():
             if f"/{path_seg}/" in url_lower:
                 return sport
         return "football"
     ```

  2. **Add country extraction from league header rows.** BetExplorer tournament rows (`<tr>` with class `tournament`) contain text like "England: Premier League" or breadcrumb with country. Parse:
     - If `:` in league text → split: country = before `:`, league = after `:`
     - If ` - ` in league text → first part = country

  3. **Add `sport` and `country` fields to output dict.**

  **Expected output fields after change:** `home`, `away`, `time`, `league`, `country`, `sport`, `match_url`, `odds`, `source_url`, `source_type`, `raw`

  **Definition of done:**
  - [ ] `sport` field populated for all entries (detected from URL)
  - [ ] `country` populated for ≥90% of matches (parsed from league header)
  - [ ] No regression in odds extraction

---

- [ ] **Task 2.3** [MODIFY] `scripts/adapters/oddsportal_adapter.py` — Complete match_url extraction

  **File:** `scripts/adapters/oddsportal_adapter.py`

  **Changes:**

  1. **Ensure match_url extraction in Strategy 1 (React SPA).** Current code walks up 4 parents looking for `a[href*="/h2h/"]`. Increase to 8 parents and also check for `a[href*="/match/"]` pattern:
     ```python
     link = link_parent.find("a", href=re.compile(r"/h2h/|/match/|/details/"))
     ```

  2. **Add match_url extraction in Strategy 2 (table rows).** The table-based parsing strategy (lines ~100+) currently doesn't extract match_url. Add `<a>` search within each table row for links containing match paths.

  3. **Add `country` extraction.** OddsPortal shows country in tournament headers. Look for elements with `class*="tournament"` or `class*="country"` and parse the text.

  **Expected output fields after change:** `home`, `away`, `time`, `sport`, `odds`, `match_url`, `country`, `source_url`, `source_type`, `raw`

  **Definition of done:**
  - [ ] `match_url` populated for ≥80% of matches in both Strategy 1 and Strategy 2
  - [ ] `country` populated when tournament headers contain country info
  - [ ] No regression in odds extraction

---

- [ ] **Task 2.4** [MODIFY] `scripts/adapters/sofascore_adapter.py` — Add per-event statistics API call

  **File:** `scripts/adapters/sofascore_adapter.py`

  **Changes:**

  1. **Add `get_event_statistics(event_id)` helper function.** Calls `https://api.sofascore.com/api/v1/event/{event_id}/statistics` to fetch per-match stats:
     ```python
     def _fetch_event_stats(event_id: int) -> dict:
         """Fetch per-match statistics from Sofascore API.
         Returns dict with stat keys: corners, fouls, yellow_cards, shots, shots_on_target, possession.
         """
         url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
         resp = _requests.get(url, headers=_HEADERS, timeout=10)
         if resp.status_code != 200:
             return {}
         data = resp.json()
         # Navigate: data["statistics"][0]["groups"] → find groups by name
         # "Shots", "TVData", "Match overview" etc.
         # Each group has "statisticsItems" with "name", "home", "away"
     ```

  2. **Add optional stat fetching in `parse()`.** For fixtures with `sofascore_id`, optionally call stats endpoint for **in-progress or finished** matches (stats only available after kickoff). Guard with a flag:
     ```python
     def parse(html: str, url: str, fetch_stats: bool = False) -> List[Dict]:
     ```
     Note: This changes the function signature. Since `parse()` is called via the standard interface, `fetch_stats` defaults to `False` and must be explicitly enabled by `scan_events.py` for deep fetches.

  3. **Map Sofascore stat names to normalized keys:**
     - "Corner Kicks" → `corners`
     - "Fouls" → `fouls`
     - "Yellow Cards" → `yellow_cards` / `cards`
     - "Total Shots" → `shots`
     - "Shots on Target" → `shots_on_target`
     - "Ball Possession" → `possession`

  4. **Add `country` field from tournament category.** Already extracted as `country` in the API response (`tournament.category.name`), but not set in the output dict. Add it.

  **Expected output fields after change:** `home`, `away`, `time`, `league`, `country`, `sport`, `sofascore_id`, `source_url`, `source_type`, `raw`; optionally (when `fetch_stats=True` and match has started): `corners`, `cards`, `fouls`, `shots`

  **Definition of done:**
  - [ ] `_fetch_event_stats()` correctly parses Sofascore statistics API response
  - [ ] Stats populated for in-progress/finished matches when `fetch_stats=True`
  - [ ] `country` field always populated from tournament category
  - [ ] No additional API calls when `fetch_stats=False` (default — preserves current behavior)
  - [ ] Rate limiting: max 2 requests/second to avoid Sofascore rate limits

  **Risk:** Sofascore API may require additional headers or return 403 for stats endpoint. Test with a known event ID first.

---

### Phase 3: Enhance Good Adapters

Minor improvements to already-working adapters.

---

- [ ] **Task 3.1** [MODIFY] `scripts/adapters/totalcorner_adapter.py` — Add match_url extraction

  **File:** `scripts/adapters/totalcorner_adapter.py`

  **Changes:**

  1. **Extract match_url from row.** TotalCorner match rows contain `<a>` links to match detail pages. Look for:
     - `<a>` in `home_td` or `away_td` with `href` containing `/match/` or `/corner/` or `/detail/`
     - Alternatively, the entire `<tr>` may be wrapped in or contain a link
     ```python
     match_url = None
     for a_tag in tr.find_all("a", href=True):
         href = a_tag["href"]
         if "/match/" in href or "/corner/" in href:
             match_url = f"https://www.totalcorner.com{href}" if href.startswith("/") else href
             break
     ```

  2. **Add `match_url` to output dict.**

  **Expected output fields after change:** existing fields + `match_url`

  **Definition of done:**
  - [ ] `match_url` populated for ≥70% of matches (some rows may lack detail links)
  - [ ] No regression in corner/card/standings extraction

---

- [ ] **Task 3.2** [MODIFY] `scripts/adapters/forebet_adapter.py` — Add predicted corners/cards extraction

  **File:** `scripts/adapters/forebet_adapter.py`

  **Changes:**

  1. **Extract additional prediction data from match rows.** Forebet sometimes shows predicted corners or "over/under" lines in additional columns. Look for:
     - Elements with class containing `corner_pred` or `cards_pred` near the match row
     - `<span>` or `<div>` elements in the row container with corner/card text patterns
     ```python
     # After extracting probabilities, look for corner/card predictions
     corner_pred = row.find("div", class_=re.compile(r"corner", re.I))
     if corner_pred:
         corner_text = corner_pred.get_text(strip=True)
         # Parse "O 10.5" or "U 9.5" patterns
     ```

  2. **Add `predicted_corners` and `predicted_cards` to predictions dict** when available.

  3. **Add `country` field.** Forebet URLs contain country info: `/en/football-tips-and-predictions/{country}/`. Parse it.

  **Expected output fields after change:** existing fields + `predictions.predicted_corners`, `predictions.predicted_cards`, `country`

  **Definition of done:**
  - [ ] Predicted corners populated when Forebet shows corner predictions on the page
  - [ ] `country` populated for country-specific Forebet pages
  - [ ] No regression in probability/score prediction extraction

---

- [ ] **Task 3.3** [DEFERRED] `scripts/adapters/flashscore_adapter.py` — Match-page deep stat parsing

  **File:** `scripts/adapters/flashscore_adapter.py`

  **Note:** This task is **deferred** because Flashscore match detail pages require a separate Playwright navigation per match, which significantly increases scan time. The current adapter already extracts the best fixture-level data of any adapter. Per-match stat parsing should be implemented as part of the deep enrichment pipeline (`data_enrichment_agent.py`) rather than in the scan-phase adapter.

  **What would be needed (for future reference):**
  - Flashscore match pages (`/match/{id}/#/match-summary/match-statistics`) show per-match corners, shots, possession, cards
  - DOM uses `class*="stat__"` elements with home/away values
  - Would require `fetch(match_url)` + separate parsing function
  - Best implemented as `parse_match_detail(html, url) -> Dict` separate from `parse()`

---

### Phase 4: Add Verbose Logging

All adapters need structured logging so the pipeline agent (R17, R19) can monitor parsing progress and react to failures.

---

- [ ] **Task 4.1** [MODIFY] All 10 football adapter files — Add structured logging

  **Files:**
  - `scripts/adapters/soccerway_adapter.py`
  - `scripts/adapters/whoscored_adapter.py`
  - `scripts/adapters/soccerstats_adapter.py`
  - `scripts/adapters/betexplorer_adapter.py`
  - `scripts/adapters/oddsportal_adapter.py`
  - `scripts/adapters/sofascore_adapter.py`
  - `scripts/adapters/totalcorner_adapter.py`
  - `scripts/adapters/forebet_adapter.py`
  - `scripts/adapters/flashscore_adapter.py`
  - `scripts/adapters/scores24_adapter.py`

  **Changes (same pattern for each adapter):**

  1. **Add logger initialization at module level:**
     ```python
     import logging
     logger = logging.getLogger(__name__)
     ```

  2. **Add INFO logs in `parse()`:**
     ```python
     logger.info("[%s] Parsing %s", SOURCE_TYPE, url)
     # ... after parsing ...
     logger.info("[%s] Extracted %d matches from %s (strategy: %s)", SOURCE_TYPE, len(results), url, strategy_name)
     ```

  3. **Add WARNING logs for parsing failures:**
     ```python
     logger.warning("[%s] Failed to parse row %d: %s", SOURCE_TYPE, i, reason)
     logger.warning("[%s] Empty/short response from %s (%d chars)", SOURCE_TYPE, url, len(html))
     ```

  4. **Add DEBUG logs for per-row extraction details** (visible only when --verbose):
     ```python
     logger.debug("[%s] Row %d: home=%s, away=%s, fields=%s", SOURCE_TYPE, i, home, away, list(entry.keys()))
     ```

  5. **Log strategy selection** (which heuristic was used):
     ```python
     logger.info("[%s] Strategy '%s' yielded %d results; %s", SOURCE_TYPE, strategy_name, len(results), "using" if results else "trying next")
     ```

  **Definition of done:**
  - [ ] Every adapter logs the number of matches extracted at INFO level
  - [ ] Every adapter logs parsing failures at WARNING level
  - [ ] Strategy selection is logged (which heuristic was chosen and why)
  - [ ] Logging does not affect return values or parsing logic

---

- [ ] **Task 4.2** [MODIFY] `scripts/adapters/__init__.py` — Enhance normalization failure logging

  **File:** `scripts/adapters/__init__.py`

  **Changes:**

  1. **Add logger to __init__.py:**
     ```python
     import logging
     logger = logging.getLogger("adapters")
     ```

  2. **Enhance `normalize_adapter_output()` exception logging** (line ~218). Currently prints to stderr. Change to structured logger with field details:
     ```python
     logger.warning(
         "[normalize] Failed for %s vs %s from %s: %s | missing_fields=%s",
         event.get("home", "?"), event.get("away", "?"),
         event.get("source_type", "?"), e,
         [f for f in ["home", "away", "time"] if not event.get(f)]
     )
     ```

  3. **Add summary log after `normalize_batch()`:**
     ```python
     logger.info("[normalize] Batch of %d events: %d normalized, %d fallback-to-raw", len(events), success_count, fallback_count)
     ```

  **Definition of done:**
  - [ ] Normalization failures logged with field-level detail
  - [ ] Batch normalization logs summary count

---

### Phase 5: Infrastructure Updates

Update supporting modules to reflect adapter improvements.

---

- [ ] **Task 5.1** [MODIFY] `scripts/deep_link_discovery.py` — Add missing domain patterns

  **File:** `scripts/deep_link_discovery.py`

  **Changes:**

  Add `DOMAIN_PATTERNS` entries for 4 missing domains:

  1. **forebet.com:**
     ```python
     "forebet.com": {
         "include": [
             re.compile(r"/en/football-tips-and-predictions/[a-z-]+/?$"),  # Country pages
             re.compile(r"/en/football-tips-and-predictions-for-today/[a-z-]+/?$"),
             re.compile(r"/en/[a-z-]+-predictions/[a-z0-9-]+/?$"),  # League-specific
         ],
         "exclude": [
             re.compile(r"/en/football-predictions-stats/"),
             re.compile(r"/en/tips/"),  # Community tips, not data
             re.compile(r"/user/"),
             re.compile(r"/login"),
         ],
     },
     ```

  2. **totalcorner.com:**
     ```python
     "totalcorner.com": {
         "include": [
             re.compile(r"/league/\d+"),            # League detail pages
             re.compile(r"/match/\d+"),              # Match detail pages
             re.compile(r"/corner/\d+"),             # Corner detail pages
             re.compile(r"/match/[a-z-]+/?$"),       # Category pages (e.g., /match/today)
         ],
         "exclude": [
             re.compile(r"/user/"),
             re.compile(r"/news/"),
             re.compile(r"/premium/"),
             re.compile(r"/login"),
         ],
     },
     ```

  3. **whoscored.com:**
     ```python
     "whoscored.com": {
         "include": [
             re.compile(r"/Matches/\d+/"),           # Match detail pages
             re.compile(r"/LiveScores/?$"),           # Live scores page
             re.compile(r"/Regions/\d+/Tournaments/"), # Tournament pages
         ],
         "exclude": [
             re.compile(r"/Statistics/"),
             re.compile(r"/Players/"),
             re.compile(r"/Graphics/"),
             re.compile(r"/News/"),
             re.compile(r"/ContactUs"),
         ],
     },
     ```

  4. **soccerstats.com:**
     ```python
     "soccerstats.com": {
         "include": [
             re.compile(r"/matches\.asp"),           # Match listings
             re.compile(r"/latest\.asp"),             # Latest results
             re.compile(r"/wiede\.asp\?league="),     # League-specific stats
             re.compile(r"/pmatch\.asp\?"),           # Per-match stats
             re.compile(r"/homeaway\.asp\?league="),  # Home/away stats
         ],
         "exclude": [
             re.compile(r"/premium/"),
             re.compile(r"/user/"),
             re.compile(r"/login"),
         ],
     },
     ```

  **Definition of done:**
  - [ ] All 4 domains added to `DOMAIN_PATTERNS`
  - [ ] Each domain has both include and exclude patterns
  - [ ] `discover_deep_links()` returns relevant sub-pages for each domain

---

- [ ] **Task 5.2** [MODIFY] `scripts/_live_test_adapters.py` — Update expected fields for enhanced adapters

  **File:** `scripts/_live_test_adapters.py`

  **Changes:**

  Update `EXPECTED_FIELDS` dict (lines 54-66) to reflect new fields from Phase 1-3:

  ```python
  EXPECTED_FIELDS = {
      "flashscore.com": ["sport", "source_type", "match_id", "status", "match_url", "country"],
      "totalcorner.com": ["sport", "source_type", "corners", "cards", "match_url"],
      "forebet.com": ["sport", "source_type", "predictions", "match_url", "country"],
      "betexplorer.com": ["sport", "source_type", "odds", "country"],
      "soccerstats.com": ["sport", "source_type", "country"],
      "sofascore.com": ["sport", "source_type", "country"],
      "covers.com": ["source_type", "source_url"],
      "basketball-reference.com": ["source_type"],
      "hockey-reference.com": ["source_type"],
      "soccerway.com": ["sport", "source_type", "country", "match_url", "league"],
      "whoscored.com": ["sport", "source_type", "league"],
      "oddsportal.com": ["sport", "source_type", "match_url"],
  }
  ```

  Also add `scores24.live` to both `TEST_URLS` and `EXPECTED_FIELDS` if missing:
  ```python
  TEST_URLS["scores24.live"] = "https://scores24.live/en/soccer"
  EXPECTED_FIELDS["scores24.live"] = ["sport", "source_type", "detail_url"]
  ```

  **Definition of done:**
  - [ ] `EXPECTED_FIELDS` updated for all enhanced adapters
  - [ ] `scores24.live` added to test URLs and expected fields
  - [ ] Running `python3 scripts/_live_test_adapters.py --verbose` shows enriched field checks

---

- [ ] **Task 5.3** [MODIFY] `.github/skills/bet-scanning-football/SKILL.md` — Update adapter capabilities

  **File:** `.github/skills/bet-scanning-football/SKILL.md`

  **Changes:**

  1. **Update "Adapter Mapping" table** (around line 37) to reflect new output fields:

     | Domain | Adapter | Expected Output Fields |
     |--------|---------|----------------------|
     | flashscore.com | `flashscore_adapter` | home, away, time, league, country, match_url, match_id, status, is_live, standings, score_home, score_away, period_scores |
     | soccerstats.com | `soccerstats_adapter` | home, away, time, league, country, match_url, corners, cards, fouls, stats |
     | totalcorner.com | `totalcorner_adapter` | corner_count, corner_handicap, total_goals_line, cards, standings, dangerous_attacks, match_url |
     | soccerway.com | `soccerway_adapter` | home, away, time, league, country, match_url, score |
     | whoscored.com | `whoscored_adapter` | home, away, time, league, country, match_url, match_id, corners, shots, possession (via __NEXT_DATA__) |
     | betexplorer.com | `betexplorer_adapter` | home, away, time, league, country, sport, odds, match_url |
     | oddsportal.com | `oddsportal_adapter` | home, away, sport, odds, match_url, country |
     | scores24.live | `scores24_adapter` | match_info, odds, h2h, form_home, form_away, trends, league, sport |
     | forebet.com | `forebet_adapter` | predictions (probs, predicted_score, predicted_corners), match_url, country |
     | sofascore.com | `sofascore_adapter` | sofascore_id, league, country, sport; optionally corners, cards, fouls, shots (via stats API) |

  2. **Update "Known Issues" section** — remove issues that are fixed:
     - Remove "Soccerway shallow listing" note (after Task 1.1)
     - Update "WhoScored JS-heavy" note to mention `__NEXT_DATA__` approach
     - Add note: "Sofascore stats API may rate-limit; use sparingly"

  3. **Add "Verbose Logging" section** documenting that all adapters now log at INFO/WARNING levels.

  **Definition of done:**
  - [ ] Adapter Mapping table reflects actual output fields
  - [ ] Known Issues section updated
  - [ ] New Verbose Logging section added

---

### Phase 6: Testing & Validation

---

- [ ] **Task 6.1** [REUSE] Live test all adapters

  **Tool:** `python3 scripts/_live_test_adapters.py --verbose`

  **Process:**
  1. Run live test harness against all adapters
  2. Verify each adapter returns ≥1 match
  3. Verify enriched fields listed in `EXPECTED_FIELDS` are populated
  4. Record any failures and iterate on adapter code

  **Definition of done:**
  - [ ] All 10 football adapters return ≥1 match from live URLs
  - [ ] Expected enriched fields populated per EXPECTED_FIELDS
  - [ ] No adapter falls back to raw_parse for its test URL

---

- [ ] **Task 6.2** [VERIFY] DB compatibility — normalize_adapter_output handles new fields

  **File:** `scripts/adapters/__init__.py`

  **Process:**
  1. Review `ENRICHED_EVENT_DEFAULTS` (lines 81-124) against new fields from Phase 1-3
  2. Verify `normalize_adapter_output()` correctly maps:
     - New `country` field → `ENRICHED_EVENT_DEFAULTS["country"]` (already exists ✓)
     - New `match_url` field → `ENRICHED_EVENT_DEFAULTS["match_url"]` (already exists ✓)
     - New `corners`/`cards`/`fouls`/`shots` dicts → merge into defaults (already handled ✓)
  3. If any new field is NOT in `ENRICHED_EVENT_DEFAULTS`, either:
     - Add it to defaults (if commonly needed downstream), or
     - Confirm it's preserved in `raw` (current behavior for unmapped fields)

  **Fields to verify mapping:**
  - `country` → direct copy ✓
  - `match_url` → direct copy ✓
  - `sport` → direct copy ✓
  - `corners` → dict merge ✓
  - `cards` → direct copy ✓
  - `fouls` → direct copy ✓
  - `shots` → direct copy ✓
  - `predictions.predicted_corners` → need to check merge logic
  - `dangerous_attacks` → stored in `raw` only (OK — not in defaults)
  - `detail_url` → mapped to `match_url` ✓
  - `sofascore_id` → mapped to `match_id` ✓

  **Definition of done:**
  - [ ] All new fields from Phase 1-3 either map to existing schema keys or are preserved in `raw`
  - [ ] `predictions` dict merge handles new sub-keys (`predicted_corners`, `predicted_cards`)
  - [ ] No downstream data loss — test by running `scan_events.py` on 2-3 URLs and inspecting output JSON

---

## Dependency Graph

```
Phase 1 (Fix Weak) ──────────────────┐
  Task 1.1 soccerway ─────────────┐  │
  Task 1.2 whoscored ─────────────┤  │
                                   │  │
Phase 2 (Enhance Moderate) ────────┤  │  (all independent of Phase 1)
  Task 2.1 soccerstats ───────────┤  │
  Task 2.2 betexplorer ───────────┤  │
  Task 2.3 oddsportal ────────────┤  │
  Task 2.4 sofascore ─────────────┤  │
                                   │  │
Phase 3 (Enhance Good) ───────────┤  │  (all independent)
  Task 3.1 totalcorner ───────────┤  │
  Task 3.2 forebet ────────────────┤  │
                                   │  │
Phase 4 (Logging) ─────────────────┤  │  (depends on Phase 1-3 being done)
  Task 4.1 all adapters ──────────┤  │
  Task 4.2 __init__.py ───────────┤  │
                                   │  │
Phase 5 (Infrastructure) ─────────┤  │  (depends on Phase 1-3 for field knowledge)
  Task 5.1 deep_link_discovery ───┤  │
  Task 5.2 _live_test_adapters ───┤  │
  Task 5.3 SKILL.md ──────────────┤  │
                                   ▼  │
Phase 6 (Testing) ────────────────────┘  (depends on ALL above)
  Task 6.1 live test
  Task 6.2 DB compatibility
```

**Parallelization:** Tasks within Phase 1, Phase 2, and Phase 3 are fully independent and can be implemented in parallel. Phase 4-5 should follow Phase 1-3. Phase 6 is final validation.

---

## Changelog

| Date | Version | Description |
|------|---------|-------------|
| 2026-05-12 | v1 | Initial plan created |
