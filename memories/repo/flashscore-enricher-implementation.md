# Flashscore Enricher Implementation

## Purpose

`scripts/flashscore_enricher.py` is a standalone Flashscore extraction module.
It is designed to be imported by another module without dragging in DB logic,
the full enrichment agent, or Playwright-heavy dependencies.

This file is the source of truth for the current implementation as of 2026-05-14.

## Design Goals

- Keep Flashscore logic self-contained.
- Avoid circular imports with `data_enrichment_agent.py`.
- Use native Flashscore search instead of DuckDuckGo fallback.
- Use `curl_cffi` browser impersonation to bypass passive TLS fingerprint blocks.
- Return parsed data to the caller; persistence belongs to the caller.

## Entry Points

### `_get_flashscore_entity(team_name: str, sport: str) -> tuple`

Purpose:
- Resolves Flashscore participant metadata before any page fetch.

What it returns:
- `(entity_type, slug, entity_id)`
- `entity_type` is usually `team` or `player`
- `slug` is the Flashscore URL slug
- `entity_id` is the opaque Flashscore participant id used in the URL

How it works:
- Calls the native endpoint:
  `https://s.flashscore.com/search/?q=...&l=1&sid=...&pid=1&f=1;1`
- Sends header:
  `x-fsign: SW9D1eZo`
- Uses `curl_cffi.requests.get(..., impersonate="chrome110")`
- Parses the JSONP-like wrapper returned by the endpoint
- Picks the first `results[]` item with `type == "participants"`
- Interprets `participant_type_id == 2` as `player`, otherwise `team`

Sport id mapping used by search:
- `football -> 1`
- `tennis -> 2`
- `basketball -> 3`
- `hockey -> 4`
- `volleyball -> 12`

### `_try_flashscore(team_name: str, sport: str) -> tuple`

Purpose:
- End-to-end stat fetch for a single team or player.

What it returns:
- `(stats_dict, error_or_none)`

Flow:
1. Resolve `(entity_type, slug, entity_id)` via `_get_flashscore_entity()`.
2. Build results-page URL:
   `https://www.flashscore.com/{entity_type}/{slug}/{entity_id}/results/`
3. Apply local `_rate_limit("flashscore.com")`.
4. Fetch HTML with `curl_cffi` and `impersonate="chrome110"`.
5. Reject pages that are too short or contain a JS challenge marker.
6. Parse HTML via `_parse_flashscore_stats()`.
7. Return parsed stats or a precise error string.

Important:
- The module does not save anything to DB.
- The caller is responsible for caching, DB writes, retries, and fallback order.

### `_parse_flashscore_stats(html: str, sport: str) -> dict`

Purpose:
- Extracts per-stat numeric series from already fetched HTML.

Return shape:
- `{stat_key: [float, float, ...]}`

Parsing strategy:
- Cap HTML at 2 MB to reduce regex cost.
- For each stat key configured for the sport, call `_extract_stat_values()`.
- If no sport-specific stat series is found, fall back to score extraction via `_extract_match_scores()`.
- Run `_validate_stat_values()` to remove impossible values.

### `_parse_flashscore_deep(html: str, sport: str) -> dict`

Purpose:
- Extracts structured context from HTML already fetched by the caller.

Return shape:
```python
{
    "recent_form": [...],
    "h2h_meetings": [...],
    "injuries": [...],
    "stats_per_match": {...},
}
```

What it currently does well:
- Captures some injury markers.
- Reuses stat extraction for `stats_per_match`.
- Falls back to score totals if no richer stat rows are found.

What it does not guarantee:
- Strong H2H extraction from the `/results/` page.
- Reliable recent-form extraction from every Flashscore DOM variant.

This function is useful only if the caller understands which Flashscore page was fetched.
On the current `/results/` page, `stats_per_match` is the most reliable field.

## Internal Helpers

### `_rate_limit(domain)`
- Simple in-process rate limiter.
- Current delay: `1.5s` between requests per domain.
- Prevents bursty back-to-back Flashscore calls from the same process.

### `_slugify(name)`
- Lowercases the name.
- Removes non-ASCII alphanumerics except spaces and dashes.
- Collapses whitespace/underscores into `-`.

Note:
- `_slugify()` is not the primary resolution mechanism anymore.
- The production path uses native search, because guessed slugs are too brittle.

### `_extract_stat_values(html, stat_key, sport)`
- Maps stat keys to label regexes where possible.
- Scans text, table cells, stat divs, and data attributes.
- Returns up to 10 validated values.

### `_extract_match_scores(html, sport)`
- Fallback extractor when no sport-specific stat rows are found.
- Returns total-score style numbers appropriate for the sport.

### `_validate_stat_values(values, stat_key, sport)`
- Applies sport-aware sanity ranges.
- Drops values outside plausible bounds.
- Logs how many were filtered.

## Supported Sports and Current Output Keys

Configured extraction keys:
- Football: `corners`, `fouls`, `yellow_cards`, `shots_on_target`, `shots_off_target`, `ball_possession`
- Tennis: `aces`, `double_faults`, `win_1st_serve`, `break_points_saved`
- Basketball: `2_pointers`, `3_pointers`, `free_throws`, `rebounds`, `turnovers`
- Volleyball: `aces`, `blocks`, `errors`
- Hockey: `shots_on_goal`, `penalties_in_minutes`, `power_play_goals`

Observed live fallback keys from the current results-page parser:
- Football -> `goals`
- Basketball -> `points`
- Volleyball -> `total_points`
- Hockey -> `goals`
- Tennis -> no valid series parsed in the live test

## Dependency Model

Direct runtime dependencies:
- Standard library: `json`, `logging`, `re`, `threading`, `time`
- Third-party: `curl_cffi`

Notably absent by design:
- No DB imports
- No repo-layer imports
- No `data_enrichment_agent` imports
- No Playwright requirement

`curl_cffi` behavior:
- The module tries to import it.
- If missing, it installs `curl_cffi` dynamically via `pip` and retries the import.

Implication for callers:
- If you want stricter deployment behavior, move installation out of the module and into environment setup.

## Live Validation — 2026-05-14

Direct `_try_flashscore()` results:

| Case | Sport | Result | Parsed Keys | Notes |
|------|-------|--------|-------------|-------|
| Real Madrid | football | success | `goals` | Returned `[6.0, 4.0]` sample after range filtering |
| Los Angeles Lakers | basketball | success | `points` | Returned `[102.0]` sample |
| Jastrzebski | volleyball | success | `total_points` | Returned `[102.0]` sample |
| Boston Bruins | hockey | success | `goals` | Returned `[2.0, 2.0]` sample |
| Sinner | tennis | failure | none | HTML fetched, but no valid series survived parsing |

Direct `_parse_flashscore_deep()` check on Real Madrid results page:
- `recent_form: 0`
- `h2h_meetings: 0`
- `injuries: 1`
- `stats_per_match: {"goals": [...]}`

Interpretation:
- The current standalone module is reliable for lightweight stat extraction from the results page.
- It is not yet a complete deep-context extractor for H2H/form on that same page.

## Known Limitations

1. Tennis is not production-ready in the standalone parser.
2. Most successful outputs currently come from score-based fallbacks, not rich stat tables.
3. `_parse_flashscore_deep()` is page-shape dependent; `/results/` is not enough for robust H2H.
4. Regex extraction is DOM-fragile and should be treated as best-effort.
5. Dynamic `pip install` inside the module is convenient, but not ideal for deterministic deployment.

## Integration Guidance For The Next Agent

If you reuse this module in a new scraper/enricher:

1. Treat `_try_flashscore()` as the stable public entrypoint.
2. Keep DB writes outside this file.
3. Keep fallback orchestration outside this file.
4. Do not reintroduce imports from `data_enrichment_agent.py`.
5. If you need richer H2H/form, fetch dedicated match/detail pages and feed their HTML into a stronger deep parser.
6. For tennis, plan a separate path instead of assuming Flashscore results-page parsing is enough.

Recommended caller contract:
```python
stats, err = _try_flashscore(team_name, sport)
if stats:
    # caller persists stats / caches them / computes averages
else:
    # caller decides next fallback source
```

## Change Summary For This Session

The module was hardened to be reusable on its own:
- Added local rate limiting instead of relying on `data_enrichment_agent`
- Added local stat-value ranges for validation
- Removed the duplicate placeholder `_parse_flashscore_deep()` that overrode the real parser
- Added module-level documentation and explicit exported entrypoints

That is the implementation another agent should build on, not the older circular-import version.