# Flashscore DOM Selectors & Scraping Reference (May 2026)

## Overview
Flashscore uses Playwright-stealth DOM scraping. No API feeds available (flashscore.ninja returns empty).
File: `src/bet/api_clients/flashscore.py`

## Anti-Bot
- **Stealth:** `from playwright_stealth import Stealth; Stealth().apply_stealth_sync(page)` (v2 API)
- **Cookie consent:** `#onetrust-accept-btn-handler` — dismiss before extraction
- **Cloudflare:** Check `page.content()` for "Just a moment" text. Use `page.inner_text('body')` for length check (avoids counting JS/HTML noise). Threshold: `< 500 chars` = blocked
- **User agents:** Rotate from `stealth_utils.USER_AGENTS`
- **Rate limiting:** 2s minimum between requests via shared `RateLimiter`
- **Circuit breaker:** Class-level `_failures` counter, opens after 3 consecutive failures, auto-resets after 5 min cooldown

## Page Structure

### Listing Page: `flashscore.com/{sport}/?d=YYYY-MM-DD`
- **CRITICAL:** Must include `?d=YYYY-MM-DD` in URL, otherwise always returns TODAY's fixtures
- Sport slugs: `football`, `tennis`, `basketball`, `hockey`, `volleyball`

#### Container Hierarchy
```
div.leagues--live
  └── div.sportName.{sport}          ← one per sport group (e.g., "sportName soccer")
       ├── div.headerLeague__wrapper  ← league header
       │    ├── a.headerLeague__title ← league name text (e.g., "Premier League")
       │    └── div.headerLeague__meta ← country text (e.g., "ENGLAND:" — strip trailing colon)
       ├── div.event__match            ← match row
       ├── div.event__match            ← match row
       ├── div.headerLeague__wrapper   ← next league
       └── ...
```

#### Match Row Selectors (`.event__match`)
- **ID format:** `g_{sport_id}_{event_id}` — strip prefix with regex `^g_\d+_`
  - Sport ID prefixes: football=1, tennis=2, basketball=3, hockey=4, volleyball=12
- **Team names:**
  - Primary: `.event__participant--home`, `.event__participant--away`
  - Fallback (legacy): `.event__homeParticipant`, `.event__awayParticipant`
- **Time:** `.event__time` — returns "HH:MM" format
- **Scores:** `.event__score--home`, `.event__score--away`
- **Status:** `.event__stage--block` — text values: "FT", "AET", "Pen.", "After ET", "Finished", etc.
- **Live flag:** Class `event__match--live` on the match div

#### OLD/BROKEN Selectors (DO NOT USE)
- ❌ `.event__header` — does NOT exist. Use `.headerLeague__wrapper`
- ❌ `.event__title--type`, `.event__title--name` — do NOT exist
- ❌ `[id^='g_1_']` — football-only. Use `.event__match` class
- ❌ `compareDocumentPosition()` for header lookup — fragile. Walk siblings in DOM order instead

### Match Detail Page: `flashscore.com/match/{event_id}/#/{tab}`
Tabs: `match-summary`, `match-summary/match-statistics/0`, `h2h/overall`

#### Match Info
- **Teams:** `.duelParticipant__home .participant__participantName`, `.duelParticipant__away .participant__participantName`
- **Start time:** `.duelParticipant__startTime`
- **Scores:** `.duelParticipant__score .detailScore__wrapper span:first-child` (home), `:last-child` (away)
- **Tournament:** Try in order:
  1. `.tournamentHeader__country a`
  2. `.tournamentHeader__country`
  3. `[class*="tournamentHeader__title"]`
  4. `.breadcrumb`
  - None of these currently match on detail pages — tournament comes back empty
  - ❌ Do NOT fall back to `document.title` — contains garbled concatenated text

#### H2H (`#/h2h/overall`)
- **Rows:** `.h2h__row`
- **Home/Away:** `.h2h__homeParticipant`, `.h2h__awayParticipant`
- **Score:** `.h2h__result span` (index 0=home, 1=away)
- **Date:** `.h2h__date`

#### Match Statistics (`#/match-summary/match-statistics/0`)
- Only available for FINISHED matches (returns empty for scheduled)
- **Primary extraction:** `[class*="stat__row"]` or `[class*="_row_"]` with `[class*="stat__"]` cells (3+ cells = home/cat/away)
- **Fallback:** `[class*="wcl-statistics"]` with `:scope > div, :scope > span` direct children only
- **Last resort:** Text parsing of `#detail` innerText — look for stat triplets (name, home_value, away_value)

#### Form Data (W/D/L)
- **Primary:** `.detailTeamForm__team` with `.detailTeamForm__icon` — currently returns empty
- **Fallback:** `[title*="win/draw/loss"]` icons — positional split (unreliable, flagged with `_fallback: true`)
- **Status:** Form extraction does NOT work on current Flashscore DOM — returns `[]` for both teams

#### Venue
- Extracted from `#detail` innerText via regex: `VENUE:\s*\n(.+?)(?:\n|$)`
- Works for football matches (e.g., "Etihad Stadium")

### Team Results Page: `flashscore.com/team/{team_slug}/results/`
- Same container structure as listing: `.sportName > div` with `.headerLeague__wrapper` and `.event__match` siblings
- Uses same selectors as listing for team names and scores

## Key Patterns & Lessons

### Resource Management
- Always use try/finally to close `ctx` (browser context) — even in `except APIError` branches
- Wrap `ctx.new_page()` and `Stealth().apply_stealth_sync(page)` in try/except to close ctx on failure
- Support `with FlashscoreClient() as fs:` context manager pattern
- `__del__` as last-resort safety net (unreliable under GC)

### Data Quality Guards
- **Empty IDs:** Skip events where `event_id` is empty string — breaks dedup and downstream lookups
- **Status detection:** Check both `status` text AND `score_home`/`score_away` presence. Expand beyond FT/AET to include cancelled/postponed/walkover statuses
- **Form data:** Log when positional fallback is used (`_fallback: true`) — data may be swapped

### Iteration Pattern (CORRECT)
```javascript
// Iterate .sportName groups → children in DOM order
const sportGroups = document.querySelectorAll('.sportName');
for (const group of sportGroups) {
    let currentLeague = '', currentCountry = '';
    for (const child of group.children) {
        if (child.classList.contains('headerLeague__wrapper')) {
            // Update league/country state
        }
        if (child.classList.contains('event__match')) {
            // Extract match data with current league/country
        }
    }
}
```

### wcl- Prefixed Classes
Flashscore uses a "Web Component Library" (wcl) with hashed class names like `wcl-bold_NZXv6`, `wcl-scores-simple-text-01_-OvnR`. These hashes change across deploys — never use them for selectors. Use the stable semantic classes instead.

## Fixture Counts (May 2026, typical day)
| Sport | Fixtures |
|-------|----------|
| Football | ~225 |
| Tennis | ~568 |
| Basketball | ~75 |
| Hockey | ~15 |
| Volleyball | ~7 |

## Applying These Patterns to Other Integrations

### Sofascore (`sofascore.py`)
- Uses XHR interception pattern (intercepts API responses)  
- If Sofascore DOM changes, apply the same approach: debug script → find containers → iterate in order
- Key difference: Sofascore has `_is_sofascore_id()` guard — numeric IDs only

### Betclic (`parse_betclic_html.py`)
- Uses pre-cached HTML files, not live Playwright
- DOM spec in `specifications/betclic-dom-selectors.md`
- Polish locale — needs market name mapping (PL→EN)

### General Debugging Protocol
1. Write a small debug script that dumps DOM structure (parent/child classes, IDs, text samples)
2. Find the container pattern (what groups matches by league?)
3. Find team name selectors (try multiple: `--home`, `__home`, `Participant`)
4. Find header/league selectors (check for `headerLeague`, `tournamentHeader`, `event__header`)
5. Test with ALL 5 sports — selectors often differ between sports
6. Check for `wcl-` hashed classes — never depend on those
7. Always pass date in URL if the site supports it — default is "today"
