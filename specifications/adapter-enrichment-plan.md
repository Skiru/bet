# Adapter Enrichment — Technical Specification

**Version:** 1.0  
**Date:** 2026-05-11  
**Scope:** Enhance 17 scan adapters + 1 fallback to extract rich statistical data; update ingest pipeline to consume it  

---

## 1. Solution Architecture

### 1.1 Current Data Flow (broken)

```
HTML → Adapter.parse() → {home, away, time, raw}  (minimal)
    → scan_results.raw_data (DB) + scan_summary.json
    → ingest_scan_stats.py reads scan_summary.json
       → looks for form_home, form_away, h2h, odds  ← NEVER PRESENT
       → writes 0 records to team_form / stats_cache

HTML → html_deep_parser.py (second pass)
    → scan_results.raw_data.deep_parse  ← NEVER consumed by ingest
```

### 1.2 Target Data Flow

```
HTML → Adapter.parse() → [{enriched event dict with standard schema}, ...]
    → normalize_adapter_output() ← NEW normalizer in adapters/__init__.py
    → scan_results.raw_data (DB) + scan_summary.json
    → ingest_scan_stats.py reads enriched events
       → consumes: odds, form, h2h, corners, cards, standings, predictions, shots
       → writes to: team_form (stat_key per metric), stats_cache, match_stats

html_deep_parser.py continues as second-pass for additional data
```

### 1.3 Standard Enriched Event Schema

Every adapter MUST return events conforming to this schema. Missing fields should be `None`/`[]`/`{}` — NOT omitted.

```python
EnrichedEvent = {
    # === CORE (required) ===
    "home": str,                  # Home team/player name
    "away": str,                  # Away team/player name
    "time": str | None,           # Kickoff time "HH:MM" or None
    "sport": str,                 # Internal sport name: football/tennis/basketball/hockey/volleyball
    "source_url": str,            # URL that was parsed
    "source_type": str,           # Adapter identifier: "flashscore", "betclic", etc.

    # === COMPETITION (optional) ===
    "league": str | None,         # Competition name (standardized key — NOT "competition")
    "date": str | None,           # Match date "YYYY-MM-DD"

    # === ODDS (optional) ===
    "odds": {                     # None if unavailable
        "w1": float | None,       # Home win odds
        "x": float | None,        # Draw odds (None for 2-way sports)
        "w2": float | None,       # Away win odds
        "handicap_lines": [{"line": str, "odds": float}, ...],  # optional
        "total_lines": [{"line": str, "over": float, "under": float}, ...],  # optional
    } | None,

    # === FORM (optional) ===
    "form_home": [                # None or [] if unavailable
        {"result": "W|L|D", "opponent": str, "scores": [int, ...], "date": str},
    ] | None,
    "form_away": [...] | None,

    # === H2H (optional) ===
    "h2h": {                      # None if unavailable
        "matches": [{"date": str, "scores": [int, ...], "home": str, "away": str}],
        "record": {"home_wins": int, "draws": int, "away_wins": int},
    } | None,

    # === STATISTICAL MARKETS (optional — per-team averages or per-match values) ===
    "corners": {                  # None if unavailable
        "home": float | None,    # Avg corners per game (home team) OR this-match count
        "away": float | None,
        "total": float | None,   # Total corners line
        "handicap": str | None,  # Corner handicap line
    } | None,
    "cards": {                    # None if unavailable
        "yellow_home": float | None,
        "yellow_away": float | None,
        "red_home": float | None,
        "red_away": float | None,
    } | None,
    "fouls": {                    # None if unavailable
        "home": float | None,
        "away": float | None,
    } | None,
    "shots": {                    # None if unavailable
        "home": float | None,
        "away": float | None,
        "on_target_home": float | None,
        "on_target_away": float | None,
    } | None,
    "dangerous_attacks": {        # None if unavailable (totalcorner-specific)
        "home": int | None,
        "away": int | None,
    } | None,

    # === STANDINGS (optional) ===
    "standings": {                # None if unavailable
        "home_pos": int | None,
        "away_pos": int | None,
        "home_points": int | None,
        "away_points": int | None,
    } | None,

    # === PREDICTIONS (optional — model-based) ===
    "predictions": {              # None if unavailable
        "prob_home": float | None,    # Win probability % (0-100)
        "prob_draw": float | None,
        "prob_away": float | None,
        "predicted_score": str | None,
        "btts": str | None,          # "Yes" / "No"
        "over_under": str | None,    # "Over 2.5" etc.
        "avg_stat": float | None,    # Avg goals/games/sets
    } | None,

    # === MATCH METADATA (optional) ===
    "match_url": str | None,      # Detail page URL for deep fetch
    "match_id": str | None,       # Source-specific match ID
    "venue": str | None,
    "surface": str | None,        # Tennis: hard/clay/grass/carpet

    # === TENNIS-SPECIFIC (optional) ===
    "elo_home": float | None,
    "elo_away": float | None,
    "seed_home": int | None,
    "seed_away": int | None,

    # === TRENDS (optional — scores24-specific) ===
    "trends": [...] | None,       # Structured betting tips

    # === RAW (backward compat) ===
    "raw": str | dict,            # Original raw text or structured data
}
```

### 1.4 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Normalizer at write boundary | One chokepoint maps old→new field names; un-upgraded adapters still work |
| `None` for missing fields vs omit | Explicit presence lets ingest distinguish "not available" from "not extracted" |
| `odds` as dict, not list | Named keys (w1/x/w2) are unambiguous; lists are positional and error-prone |
| `league` standardized key | Adapters currently use `league`, `competition`, or neither. Single key. |
| `source_type` per adapter | Enables per-source hit rate tracking in DB |
| Deep parser NOT removed | Second-pass extraction catches what adapters miss from initial HTML |

---

## 2. Implementation Plan

### Phase 1: Schema & Normalizer Infrastructure

**Goal:** Create the normalizer function that maps legacy adapter output to the standard schema. This is the foundation — once deployed, even un-upgraded adapters produce usable output.

---

#### Task 1.1 — `[MODIFY]` `scripts/adapters/__init__.py`: Add normalizer + schema definition

**File:** `scripts/adapters/__init__.py`

**Changes:**
1. Add `ENRICHED_EVENT_DEFAULTS` dict — the complete schema with all fields set to `None`/`[]`/`{}`
2. Add `normalize_adapter_output(event: dict, source_type: str) -> dict` function that:
   - Starts with a copy of `ENRICHED_EVENT_DEFAULTS`
   - Maps legacy field names to standard fields:
     - `home_team` → `home`, `away_team` → `away`
     - `kickoff` → `time`
     - `competition` → `league`
     - `source` → `source_url` (when it's a URL)
     - `url` → `source_url`
     - `forebet_probs` → `predictions.prob_home/prob_draw/prob_away`
     - `forebet_prediction` → `predictions.predicted_winner`
     - `forebet_score` → `predictions.predicted_score`
     - `forebet_avg` → `predictions.avg_stat`
     - `corner_handicap` → `corners.handicap`
     - `corner_count` → `corners.home/corners.away` (parse "5-3" format)
     - `total_goals_line` → `odds.total_lines`
     - `odds_structured` → merge into `odds` dict
     - `consensus` → map spread/total/moneyline into `odds`
     - `odds` (when list of strings) → convert to `{w1, x, w2}` dict
   - Sets `source_type` from parameter
   - Preserves any fields that don't have a mapping (passed through to `raw`)
3. Add `normalize_batch(events: list[dict], source_type: str) -> list[dict]` — maps over a list

**Definition of Done:**
- [ ] `normalize_adapter_output()` correctly maps all 16 known legacy field patterns
- [ ] All standard schema fields are present in output (even if `None`)
- [ ] Unknown fields are preserved in the `raw` dict
- [ ] Unit test covers mapping from each adapter's current output format
- [ ] Existing adapter output passes through without data loss

---

#### Task 1.2 — `[MODIFY]` `scripts/scanners/base_scanner.py`: Integrate normalizer into write path

**File:** `scripts/scanners/base_scanner.py`

**Changes:**
1. Import `normalize_adapter_output` from `adapters`
2. In `_parse_url()`, after calling the adapter, normalize each event:
   ```python
   events = adapter(html, url)
   domain = _domain_from_url(url)
   return [normalize_adapter_output(e, source_type=domain) for e in events]
   ```
3. This ensures ALL per-sport scanner output goes through the normalizer before DB write

**Definition of Done:**
- [ ] All events written to DB via `base_scanner` have the standard schema
- [ ] `sport` field is always populated (falls back to `self.sport_name`)
- [ ] `source_type` is always populated from domain
- [ ] Existing per-sport scanner tests still pass

---

#### Task 1.3 — `[MODIFY]` `scripts/scan_events.py`: Integrate normalizer into legacy scan path

**File:** `scripts/scan_events.py`

**Changes:**
1. Import `normalize_adapter_output` from `adapters`
2. In the section that calls adapters and builds `all_extracted`, normalize each event after adapter returns
3. This ensures the non-parallel-sport code path also produces standard output

**Definition of Done:**
- [ ] `scan_summary.json` events have standard schema fields
- [ ] Legacy single-threaded scan path produces normalized output
- [ ] No regression in scan event counts

---

### Phase 2: High-Impact Adapter Updates

These 6 adapters cover the largest data volumes and richest HTML sources.

---

#### Task 2.1 — `[MODIFY]` `scripts/adapters/flashscore_adapter.py`: Extract match IDs, form indicators, and standings

**File:** `scripts/adapters/flashscore_adapter.py` (current: ~250 lines)

**What to extract (from HTML available in listing pages):**

| Field | HTML Source | CSS/Pattern |
|-------|-----------|-------------|
| `match_id` | `<div id="g_1_XXXXXXXX">` | `el.get("id")` — regex `^g_\d+_(\w+)$` |
| `league` | `event__header` → `category-text` + `title-text` | Already partially done via `_heuristic0_event_classes` |
| `standings.home_pos` / `standings.away_pos` | League position markers `[3]` in team names | Already cleaned by regex — need to CAPTURE before cleaning |
| `score` (live matches) | `event__score--home`, `event__score--away` | `score--home` / `score--away` class |
| `sport` | URL path `/football/`, `/tennis/`, etc. | Parse from URL |

**Implementation notes:**
- In `_heuristic0_event_classes()`, extract `match_id` from element `id` attribute before building the event dict
- Capture league position from team name `[N]` pattern BEFORE stripping it
- Add score extraction for live/finished matches (useful for live betting window R16)
- Detect sport from URL path (already has `_competition_from_url` — add sport detection)

**NOT extractable from listing HTML** (requires detail page fetch):
- form_home/form_away (W/L/D sequences) — only available on match detail pages
- h2h data — only on detail pages
- odds — loaded via JS, not in static HTML

**Definition of Done:**
- [ ] `match_id` populated for matches with `g_1_*` element IDs
- [ ] `league` populated from header context in `_heuristic0_event_classes`
- [ ] `standings.home_pos` / `standings.away_pos` captured from `[N]` markers
- [ ] `sport` detected from URL path
- [ ] `source_type` = `"flashscore"`
- [ ] All existing matches continue to parse correctly (no regression in event count)

---

#### Task 2.2 — `[MODIFY]` `scripts/adapters/totalcorner_adapter.py`: Extract cards, dangerous attacks, league position, restructure corners

**File:** `scripts/adapters/totalcorner_adapter.py` (current: ~130 lines)

**What to extract (HTML is rich — totalcorner has extensive data in listing page):**

| Field | HTML Source | CSS/Pattern |
|-------|-----------|-------------|
| `corners.home` / `corners.away` | Corner count cell | Already parsed as `corner_count` "5-3" — restructure |
| `corners.handicap` | `td.match_handicap` | Already parsed as `corner_handicap` — move to corners dict |
| `corners.ht_home` / `corners.ht_away` | Corner count "5-3(2-1)" — HT in parens | Parse from pattern `\d+-\d+\((\d+)-(\d+)\)` |
| `cards.yellow_home` / `cards.yellow_away` | `<span class="yellow">N</span>` inside team cell | See deep parser profile |
| `cards.red_home` / `cards.red_away` | `<span class="red">N</span>` inside team cell | See deep parser profile |
| `dangerous_attacks.home` / `dangerous_attacks.away` | Cell with class containing "attack" or "danger" | Pattern `(\d+)\s*-\s*(\d+)` |
| `standings.home_pos` / `standings.away_pos` | `[N]` in team name cell | Capture before stripping |

**Implementation notes:**
- Refactor existing `corner_handicap`, `corner_count`, `total_goals_line` into the standard `corners` and `odds` dicts
- Add card extraction using the same logic as `TotalCornerProfile` in deep parser
- Add dangerous attack extraction
- Capture league position `[N]` from team cells before stripping brackets

**Definition of Done:**
- [ ] `corners` dict populated with home/away/handicap/total and HT values
- [ ] `cards` dict populated from yellow/red span counts
- [ ] `dangerous_attacks` dict populated when data present
- [ ] `standings.home_pos/away_pos` captured from bracket markers
- [ ] `odds.total_lines` populated from total goals line
- [ ] Backward compat: old flat keys (`corner_handicap` etc.) still present in `raw`
- [ ] No regression in match count

---

#### Task 2.3 — `[MODIFY]` `scripts/adapters/forebet_adapter.py`: Restructure into standard schema

**File:** `scripts/adapters/forebet_adapter.py` (current: ~165 lines)

**What to restructure (already extracted, just needs remapping):**

| Current Field | Target Field |
|--------------|-------------|
| `forebet_probs.home` | `predictions.prob_home` |
| `forebet_probs.draw` | `predictions.prob_draw` |
| `forebet_probs.away` | `predictions.prob_away` |
| `forebet_prediction` | `predictions.predicted_winner` |
| `forebet_score` | `predictions.predicted_score` |
| `forebet_avg` | `predictions.avg_stat` |
| `detail_url` | `match_url` |

**Additional extraction from HTML (per deep parser profile):**
- BTTS prediction: `div.btts` or `div.both` class
- Over/Under: `div.ou_` or `div.over_under` class
- Weather: `div.weather` class

**Definition of Done:**
- [ ] `predictions` dict populated with all probability values
- [ ] `predictions.btts` and `predictions.over_under` extracted when present
- [ ] `match_url` populated from detail URL
- [ ] `sport` detected from URL path
- [ ] `source_type` = `"forebet"`
- [ ] Legacy `forebet_*` keys preserved in `raw` for backward compat

---

#### Task 2.4 — `[MODIFY]` `scripts/adapters/betexplorer_adapter.py`: Restructure odds, extract league

**File:** `scripts/adapters/betexplorer_adapter.py` (current: ~95 lines)

**What to change:**

| Current | Target |
|---------|--------|
| `odds: ["2.00", "3.18", "3.65"]` (list of strings) | `odds: {w1: 2.0, x: 3.18, w2: 3.65}` (named dict) |
| No league | Extract from `table-main__tournament` rows (per deep parser profile) |
| No match_url | Extract from team link `href` |

**Additional extraction from HTML:**
- League name from tournament header rows (`tr.js-tournament`)
- Country from flag image `alt` attribute
- Match result (if available) from `table-main__result` cell
- Match detail URL from team link `href`

**Definition of Done:**
- [ ] `odds` is a dict with `w1`, `x` (when 3-way), `w2` keys
- [ ] `league` populated from tournament headers
- [ ] `match_url` populated from team link href
- [ ] `source_type` = `"betexplorer"`
- [ ] No regression in match/odds extraction

---

#### Task 2.5 — `[MODIFY]` `scripts/adapters/soccerstats_adapter.py`: Restructure stats into standard dicts

**File:** `scripts/adapters/soccerstats_adapter.py` (current: ~175 lines)

**What to restructure:**

| Current | Target |
|---------|--------|
| `stats.corners_home` / `stats.corners_away` | `corners.home` / `corners.away` |
| `stats.cards_home` / `stats.cards_away` | `cards.yellow_home` / `cards.yellow_away` |
| `stats.fouls_home` / `stats.fouls_away` | `fouls.home` / `fouls.away` |
| `data_type: "team_stats"` (league stat rows) | Mark as `stat_context: "league_average"` |

**Additional extraction:**
- Parse `title` attributes on `<td>` cells more aggressively — soccerstats uses titles like "Corners For", "Yellow Cards", "Shots on Target"
- Extract over/under percentages when available
- Extract BTTS percentages when available

**Definition of Done:**
- [ ] `corners`, `cards`, `fouls` dicts populated from match table stats
- [ ] Team stats rows produce separate entries with `stat_context: "league_average"`
- [ ] `sport` = `"football"` always set
- [ ] `source_type` = `"soccerstats"`

---

#### Task 2.6 — `[MODIFY]` `scripts/adapters/scores24_adapter.py`: Standardize detail page output

**File:** `scripts/adapters/scores24_adapter.py` (current: ~350+ lines)

**Already extracts rich data on detail pages** — this adapter is the richest. Needs field name standardization only:

| Current | Target |
|---------|--------|
| `match_info.home` / `match_info.away` | Top-level `home` / `away` (already done) |
| `odds.w1/x/w2` | Standard `odds` dict (already compatible) |
| `odds.handicap_lines` | Standard `odds.handicap_lines` (already compatible) |
| `odds.total_lines` | Standard `odds.total_lines` (already compatible) |
| `form_home` / `form_away` | Already standard format (compatible) |
| `h2h` | Already standard format (compatible) |
| `trends` | Pass through as-is |
| `match_info.surface` | Top-level `surface` |
| `match_info.venue` | Top-level `venue` |
| `match_info.tournament` | `league` |

**Changes needed:**
1. In `_parse_detail_page()`, hoist `match_info` sub-fields to top level
2. Set `source_type = "scores24"`
3. In `_parse_listing_page()`, add `sport` and `source_type` to listing events

**Definition of Done:**
- [ ] Detail page events have standard schema with odds, form, h2h hoisted to top level
- [ ] `surface`, `venue`, `league` at top level (not nested in `match_info`)
- [ ] Listing page events have `sport`, `source_type`, `league`
- [ ] No regression in event extraction

---

### Phase 3: Medium-Impact Adapter Updates

---

#### Task 3.1 — `[MODIFY]` `scripts/adapters/betclic_adapter.py`: Restructure odds, add source_type/sport

**File:** `scripts/adapters/betclic_adapter.py` (current: ~110 lines)

**Changes:**
1. Convert `odds: ["2.00", "3.18", "3.65"]` (list) → `odds: {w1: 2.0, x: 3.18, w2: 3.65}` (dict)
2. Detect sport from URL/breadcrumbs
3. Add `source_type = "betclic"`
4. Rename `competition` → `league` for consistency

**Definition of Done:**
- [ ] `odds` is named dict, not list
- [ ] `sport` populated from URL or breadcrumbs
- [ ] `source_type` = `"betclic"`
- [ ] `league` used instead of `competition`

---

#### Task 3.2 — `[MODIFY]` `scripts/adapters/oddsportal_adapter.py`: Standardize odds format

**File:** `scripts/adapters/oddsportal_adapter.py` (current: ~120 lines)

**Changes:**
1. Merge `odds` (list) and `odds_structured` (dict) into a single `odds` dict
2. Remove `market_type` (always "h2h") — encode in odds dict keys instead
3. Detect sport from URL
4. Add `source_type = "oddsportal"`

**Definition of Done:**
- [ ] Single `odds` dict with `w1`, `x` (optional), `w2`
- [ ] `sport` populated
- [ ] `source_type` = `"oddsportal"`

---

#### Task 3.3 — `[MODIFY]` `scripts/adapters/sofascore_adapter.py`: Extract richer API data

**File:** `scripts/adapters/sofascore_adapter.py` (current: ~130 lines)

**Changes:**
1. From API response, additionally extract:
   - `venue` from `ev.get("venue", {}).get("name")`
   - `round` from `ev.get("roundInfo", {}).get("round")`
   - Season from `ev.get("season", {}).get("name")`
2. Add `match_id` from `sofascore_id` (rename)
3. Add `source_type = "sofascore"`
4. Sport mapping: `ice-hockey` → `hockey` (already done)

**Definition of Done:**
- [ ] `venue` extracted when API provides it
- [ ] `match_id` populated from sofascore event ID
- [ ] `source_type` = `"sofascore"`

---

#### Task 3.4 — `[MODIFY]` `scripts/adapters/tennisexplorer_adapter.py`: Add seed, country, match_id

**File:** `scripts/adapters/tennisexplorer_adapter.py` (current: ~165 lines)

**Changes:**
1. Extract player seed numbers from name/rank cells
2. Extract player country from flag spans (per deep parser profile: `span.fl-XX`)
3. Extract match detail link → `match_id` or `match_url`
4. Map `odds` from string to float
5. Add `source_type = "tennisexplorer"`
6. Rename `url` → `source_url`

**Definition of Done:**
- [ ] `seed_home` / `seed_away` populated when available
- [ ] Player countries extracted from flag classes
- [ ] `match_url` populated from detail links
- [ ] `surface` consistently extracted
- [ ] `source_type` = `"tennisexplorer"`

---

#### Task 3.5 — `[MODIFY]` `scripts/adapters/tennisabstract_adapter.py`: Standardize Elo output

**File:** `scripts/adapters/tennisabstract_adapter.py` (current: ~130 lines)

**Changes:**
1. This adapter produces PLAYER RATING data (not match fixtures). Output format needs special handling.
2. Add `data_type: "player_ratings"` to mark non-fixture data
3. Restructure Elo fields:
   - `elo_rating` → keep as-is
   - `hard_elo`, `clay_elo`, `grass_elo` → keep as surface-specific
   - `official_rank` → keep
4. Add `source_type = "tennisabstract"`

**Definition of Done:**
- [ ] `data_type = "player_ratings"` marks non-fixture entries
- [ ] `source_type` = `"tennisabstract"`
- [ ] Elo ratings preserved in standard format
- [ ] `sport` = `"tennis"` always set

---

#### Task 3.6 — `[MODIFY]` `scripts/adapters/covers_adapter.py`: Fix field names, restructure consensus

**File:** `scripts/adapters/covers_adapter.py` (current: ~140 lines)

**Changes:**
1. Rename `home_team` → `home`, `away_team` → `away`, `kickoff` → `time`
2. Rename `source` → `source_url` (set to url parameter)
3. Restructure `consensus` → `odds`:
   - `consensus.spread` → `odds.handicap_lines[0].line`
   - `consensus.total` → `odds.total_lines[0].line`
   - `consensus.moneyline` → convert American to decimal, store in `odds.w1` or `odds.w2`
4. Add `source_type = "covers"`

**Definition of Done:**
- [ ] Standard field names: `home`, `away`, `time`, `source_url`
- [ ] `odds` dict populated from consensus data
- [ ] American odds converted to decimal
- [ ] `source_type` = `"covers"`

---

### Phase 4: Lower-Impact Adapter Updates

---

#### Task 4.1 — `[MODIFY]` `scripts/adapters/basketball_reference_adapter.py`: Fix field names, extract stats

**File:** `scripts/adapters/basketball_reference_adapter.py` (current: ~100 lines)

**Changes:**
1. Rename `home_team` → `home`, `away_team` → `away`, `kickoff` → `time`
2. Rename `source` → `source_url`
3. In schedule table parsing, extract additional `data-stat` attributes:
   - `pts` (points) for score
   - `game_remarks` for OT/postponement info
4. Extract box score stats if on game detail page (from `data-stat` attributes)
5. Add `source_type = "basketball_reference"`

**Definition of Done:**
- [ ] Standard field names
- [ ] `source_type` = `"basketball_reference"`
- [ ] `sport` = `"basketball"`
- [ ] Score extracted from `data-stat="pts"` when available

---

#### Task 4.2 — `[MODIFY]` `scripts/adapters/hockey_reference_adapter.py`: Fix field names, extract stats

**File:** `scripts/adapters/hockey_reference_adapter.py` (current: ~90 lines)

**Changes:**
1. Same field name fixes as basketball_reference
2. Extract additional `data-stat` attributes: `goals`, `shots`, `save_pct`
3. Add `source_type = "hockey_reference"`

**Definition of Done:**
- [ ] Standard field names
- [ ] `source_type` = `"hockey_reference"`
- [ ] `sport` = `"hockey"`

---

#### Task 4.3 — `[MODIFY]` `scripts/adapters/soccerway_adapter.py`: Add match_url, league improvements

**File:** `scripts/adapters/soccerway_adapter.py` (current: ~170 lines)

**Changes:**
1. Extract match detail URL from `<a>` tags inside match rows → `match_url`
2. Rename `url` → `source_url`
3. Fix: `odds` field currently gets set to `score_text` — rename to `score` and add proper `odds: None`
4. Add `source_type = "soccerway"`
5. `sport` = `"football"` (already set)

**Definition of Done:**
- [ ] `match_url` extracted from team links
- [ ] `odds` no longer contains score text (moved to `score`)
- [ ] `source_type` = `"soccerway"`
- [ ] Standard field names

---

#### Task 4.4 — `[MODIFY]` `scripts/adapters/whoscored_adapter.py`: Fix field names, restructure stats

**File:** `scripts/adapters/whoscored_adapter.py` (current: ~155 lines)

**Changes:**
1. Rename `home_team` → `home`, `away_team` → `away`, `kickoff` → `time`
2. Rename `source` → `source_url`
3. Restructure `stats` dict into standard dicts:
   - `stats.possession` → pass through
   - `stats.shots` → `shots.home`
   - `stats.shots_on_target` → `shots.on_target_home`
   - `stats.corners` → `corners.home`
4. Add `source_type = "whoscored"`

**Definition of Done:**
- [ ] Standard field names
- [ ] Stats restructured into `shots`, `corners` dicts
- [ ] `source_type` = `"whoscored"`

---

#### Task 4.5 — `[MODIFY]` `scripts/adapters/raw_adapter.py`: Add source_type, ensure schema compliance

**File:** `scripts/adapters/raw_adapter.py` (current: ~95 lines)

**Changes:**
1. Add `source_type = "raw_fallback"` to all events
2. Add `sport = None` (unknown from raw text)
3. Add `source_url = url`
4. All other enriched fields default to `None` via normalizer

**Definition of Done:**
- [ ] `source_type` = `"raw_fallback"` on all events
- [ ] Raw adapter output compatible with normalizer

---

### Phase 5: Consumer Update — `ingest_scan_stats.py`

---

#### Task 5.1 — `[MODIFY]` `scripts/ingest_scan_stats.py`: Consume new enriched fields

**File:** `scripts/ingest_scan_stats.py` (current: 593 lines)

**Changes to `ingest_event()`:**

1. **Odds processing (existing):** Already handles `odds` as dict or list — verify compatibility with new dict format. The `w1`/`x`/`w2` keys are already expected. Add handling for `handicap_lines` and `total_lines` from the odds dict.

2. **Corners ingestion (NEW):**
   ```python
   corners = event.get("corners")
   if corners and isinstance(corners, dict):
       if corners.get("home") is not None:
           # Write to team_form as stat_key="corners_per_game"
           _ingest_stat_value(sport, home, "corners_per_game", corners["home"], source_tag)
       if corners.get("away") is not None:
           _ingest_stat_value(sport, away, "corners_per_game", corners["away"], source_tag)
   ```

3. **Cards ingestion (NEW):**
   ```python
   cards = event.get("cards")
   if cards and isinstance(cards, dict):
       if cards.get("yellow_home") is not None:
           _ingest_stat_value(sport, home, "yellow_cards_per_game", cards["yellow_home"], source_tag)
       # ... same for away, red cards
   ```

4. **Fouls ingestion (NEW):** Same pattern as corners/cards.

5. **Shots ingestion (NEW):** Same pattern.

6. **Standings ingestion (NEW):**
   ```python
   standings = event.get("standings")
   if standings:
       if standings.get("home_pos") is not None:
           _ingest_stat_value(sport, home, "league_position", standings["home_pos"], source_tag)
   ```

7. **Predictions storage (NEW):** Write to a new `predictions` section in stats_cache for model-based probability data from forebet/scores24.

**New helper function `_ingest_stat_value()`:**
```python
def _ingest_stat_value(sport: str, team: str, stat_key: str, value: float, source_tag: str):
    """Write a single stat value to team_form and stats_cache."""
    existing = read_cache(sport, team)
    stat_section = existing.get("scan_stats", {}) if existing else {}
    
    # Append to running list (max 10 values)
    if stat_key not in stat_section:
        stat_section[stat_key] = {"values": [], "source": source_tag}
    stat_section[stat_key]["values"].append(value)
    stat_section[stat_key]["values"] = stat_section[stat_key]["values"][-10:]
    
    # Write to cache
    entry = existing or create_team_cache_entry(team, sport)
    entry["scan_stats"] = stat_section
    update_cache(sport, team, entry)
    
    # Dual-write to DB team_form
    if _HAS_DB:
        try:
            with get_db() as conn:
                vals = stat_section[stat_key]["values"]
                form = TeamForm(
                    id=None, team_id=_resolve_team_id(conn, team, sport),
                    sport_id=_resolve_sport_id(conn, sport),
                    stat_key=stat_key,
                    l10_values=vals[-10:], l5_values=vals[-5:],
                    l10_avg=sum(vals[-10:]) / len(vals[-10:]),
                    l5_avg=sum(vals[-5:]) / max(len(vals[-5:]), 1),
                    source=source_tag,
                )
                StatsRepo(conn).upsert_team_form(form)
        except Exception:
            pass
```

8. **Add team/sport ID resolution helpers** — `_resolve_team_id()` and `_resolve_sport_id()` using existing `TeamRepo` and `SportRepo`.

**Definition of Done:**
- [ ] `corners`, `cards`, `fouls`, `shots`, `standings` consumed and written to `team_form`
- [ ] `predictions` stored in stats_cache
- [ ] `odds.handicap_lines` and `odds.total_lines` stored
- [ ] `_ingest_stat_value()` works for both cache and DB
- [ ] Post-ingest DB verification shows new stat_key entries in team_form
- [ ] Dry-run mode works for all new fields
- [ ] Summary output includes counts for new stat types

---

#### Task 5.2 — `[MODIFY]` `scripts/scanners/merge_results.py`: Ensure enriched fields survive merge

**File:** `scripts/scanners/merge_results.py` (current: ~65 lines)

**Changes:**
1. In `merge_scan_results()`, the `raw_data` field is already passed through as the full event dict. Verify that `event.setdefault()` calls don't overwrite enriched fields with empty values.
2. Add explicit handling: when `r.raw_data` already has `odds`/`corners`/etc., don't overwrite with defaults.

**Definition of Done:**
- [ ] Enriched fields from `scan_results.raw_data` survive merge into `scan_summary.json`
- [ ] No enriched data lost during merge

---

### Phase 6: Testing

---

#### Task 6.1 — `[CREATE]` `tests/test_adapter_normalizer.py`: Unit tests for normalizer

**What to test:**
1. Each legacy adapter format → normalized output has all schema fields
2. Odds list → odds dict conversion
3. Field name mappings (home_team→home, competition→league, etc.)
4. Forebet-specific field mapping (forebet_probs→predictions)
5. TotalCorner-specific field mapping (corner_count→corners)
6. Covers consensus → odds conversion (including American→decimal)
7. Unknown fields preserved in raw
8. None/empty handling

**Definition of Done:**
- [ ] ≥20 test cases covering all adapter output formats
- [ ] All tests pass
- [ ] Edge cases: empty events, missing fields, malformed data

---

#### Task 6.2 — `[CREATE]` `tests/test_adapter_enriched_output.py`: Per-adapter output validation

**What to test:**
1. For each adapter, provide sample HTML (stored as test fixtures or inline strings)
2. Verify output matches enriched schema
3. Verify specific fields are extracted (e.g., flashscore match_id, totalcorner cards)
4. Verify `source_type` is correct per adapter
5. Verify `sport` is detected correctly

**Definition of Done:**
- [ ] One test function per adapter (17 tests minimum)
- [ ] Sample HTML fixtures for top 6 adapters (flashscore, totalcorner, forebet, betexplorer, soccerstats, scores24)
- [ ] All tests pass

---

#### Task 6.3 — `[CREATE]` `tests/test_ingest_enriched.py`: Integration test for enriched ingest

**What to test:**
1. Create a mock `scan_summary.json` with enriched events (corners, cards, odds dict, form, h2h)
2. Run `ingest_scan_stats.run()` in dry-run mode
3. Verify correct summary output (stat types ingested)
4. Run with real DB (in-memory SQLite) and verify `team_form` rows created with correct `stat_key` values

**Definition of Done:**
- [ ] End-to-end test: enriched scan_summary → ingest → team_form populated
- [ ] All new stat_keys verified: `corners_per_game`, `yellow_cards_per_game`, `fouls_per_game`, `league_position`
- [ ] Odds dict format handled correctly
- [ ] No regression on existing form/h2h ingestion

---

## 3. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| HTML injection in team names | BeautifulSoup already escapes HTML; normalizer strips control characters |
| Numeric overflow from parsed odds/stats | Plausible range validation (already exists in deep parser `PLAUSIBLE_RANGES`) — add to normalizer |
| Path traversal in source_url | source_url is used for display only, never for file operations |
| JSON injection in raw_data | raw_data is stored as JSON in DB (already sanitized by json.dumps) |

---

## 4. Quality Assurance

| Check | Tool | Gate |
|-------|------|------|
| All adapter outputs pass normalizer | `test_adapter_normalizer.py` | CI |
| Per-adapter HTML extraction | `test_adapter_enriched_output.py` | CI |
| Ingest consumes all new fields | `test_ingest_enriched.py` | CI |
| No regression in event counts | Compare scan_summary event counts before/after | Manual (first deploy) |
| DB team_form populated | Post-ingest DB verification (already in ingest) | Pipeline step |
| Type safety | mypy on normalizer and ingest changes | CI (if configured) |

---

## 5. Adapter Summary Matrix

| # | Adapter | Current Output | Key New Fields | Effort |
|---|---------|---------------|----------------|--------|
| 1 | flashscore | home,away,time,raw,league | match_id, standings, sport | M |
| 2 | betclic | home,away,time,odds[],competition,match_url | odds→dict, sport, league | S |
| 3 | totalcorner | home,away,time,corner_*,total_goals_line,league | corners{}, cards{}, dangerous_attacks{}, standings{} | M |
| 4 | forebet | home,away,time,forebet_probs/prediction/score/avg | predictions{}, btts, over_under | S |
| 5 | betexplorer | home,away,time,odds[] | odds→dict, league, match_url | S |
| 6 | oddsportal | home,away,odds[],odds_structured | odds→dict, sport | S |
| 7 | sofascore | home,away,time,league,sofascore_id | venue, match_id, round | S |
| 8 | scores24 | RICH on detail pages; basic on listing | Standardize field names only | S |
| 9 | covers | home_team,away_team,kickoff,consensus | Rename fields, odds→dict, American→decimal | S |
| 10 | basketball_ref | home_team,away_team,kickoff | Rename fields, extract data-stat | S |
| 11 | hockey_ref | home_team,away_team,kickoff | Rename fields, extract data-stat | S |
| 12 | tennisexplorer | home,away,time,odds,league,surface | seed, country, match_url | S |
| 13 | tennisabstract | RICH Elo data | Add data_type marker | XS |
| 14 | soccerstats | home,away,time,league,stats{} | corners{}, cards{}, fouls{} | S |
| 15 | soccerway | home,away,time,league | match_url, fix odds=score bug | S |
| 16 | whoscored | home_team,away_team,kickoff,stats{} | Rename, shots{}, corners{} | S |
| 17 | raw_adapter | home,away,time,raw | source_type only | XS |

**Effort key:** XS = <30 min, S = 30-60 min, M = 1-2 hours

---

## 6. Execution Order & Dependencies

```
Phase 1 (Tasks 1.1-1.3) ← MUST complete first (normalizer is foundation)
    ↓
Phase 2 (Tasks 2.1-2.6) ← Can be parallelized (independent adapters)
    ↓
Phase 3 (Tasks 3.1-3.6) ← Can be parallelized
    ↓
Phase 4 (Tasks 4.1-4.5) ← Can be parallelized
    ↓
Phase 5 (Tasks 5.1-5.2) ← Depends on Phase 1 minimum; benefits from Phase 2+
    ↓
Phase 6 (Tasks 6.1-6.3) ← Can start after Phase 1; grows with each phase
```

**Critical path:** Task 1.1 → Task 1.2 → Task 5.1 → Task 6.3

Phase 2-4 adapters are independent and can be done in any order. Phase 6 tests should be written incrementally as each adapter is updated.
