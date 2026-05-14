# Playwright & Scraping Reference

## Stealth Pattern (canonical — ALL Playwright scripts MUST use this)
```python
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth  # v2 API

browser = p.chromium.launch(headless=True, args=[
    '--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox'
])
context = browser.new_context(user_agent="...", viewport={"width": 1920, "height": 1080})
page = context.new_page()
Stealth().apply_stealth_sync(page)  # BEFORE any page.goto()
# Async: await Stealth().apply_stealth_async(page)
```

## Block Detection (size-aware — `stealth_utils.py`)
- Real block: HTTP 403/429 + <15KB page with "zablokowany"/"access denied"
- False positive: HTTP 200 + 400KB+ page with "datadome" in bundled JS
- Use `is_actually_blocked()` from `stealth_utils.py`

## Architecture: Stealth HTML Warmup (S0.1)
- `daily_odds_warmup.py` fetches full DOMs from protected bookmakers (Betclic)
- HTML dumped to `betting/data/html_cache/{date}_betclic_{sport}.html`
- Downstream parsers do local BeautifulSoup/regex parsing — NO live API blocks
- **Rule**: Do NOT write live-scraping Playwright into main pipeline. Add new sources to warmup array instead.

## Flashscore DOM Selectors
**File**: `src/bet/api_clients/flashscore.py`

### Listing Page: `flashscore.com/{sport}/?d=YYYY-MM-DD`
- Sport slugs: `football`, `tennis`, `basketball`, `hockey`, `volleyball`
- CRITICAL: Must include `?d=YYYY-MM-DD` — otherwise returns TODAY's fixtures
- Container: `.sportName.{sport}` → children in DOM order
- League header: `.headerLeague__wrapper` → `.headerLeague__title` (name), `.headerLeague__meta` (country)
- Match row: `.event__match` → `.event__participant--home/--away`, `.event__time`, `.event__score--home/--away`
- ❌ BROKEN: `.event__header`, `.event__title--type`, `[id^='g_1_']`, `compareDocumentPosition()`

### Match Detail: `flashscore.com/match/{event_id}/#/{tab}`
- Teams: `.duelParticipant__home/away .participant__participantName`
- Stats (finished only): `[class*="stat__row"]` or `[class*="_row_"]`
- H2H: `.h2h__row` → `.h2h__homeParticipant`, `.h2h__awayParticipant`, `.h2h__result span`
- Venue: regex `VENUE:\s*\n(.+?)(?:\n|$)` on `#detail` innerText
- ⚠ wcl-prefixed classes (e.g. `wcl-bold_NZXv6`) have hashed suffixes that change across deploys — NEVER use for selectors

### Key Patterns
- Always use `page.inner_text('body')` NOT `page.content()` for text extraction
- Circuit breaker: class-level `_failures`, opens after 3, 300s cooldown
- Cookie consent: `#onetrust-accept-btn-handler`
- Cloudflare: check body text for "Just a moment", length < 500 chars = blocked

## Betclic DOM Selectors
**Spec**: `specifications/betclic-dom-selectors.md`
**Parser**: `scripts/parse_betclic_html.py`

### Listing Pages
- Event card: `sports-events-event-card` (NOT `sports-events-skeleton`)
- Teams: `[data-qa="contestant-1-label"]` / `[data-qa="contestant-2-label"]`
- Team name split: `span.ellipsis` + `span.clip` → use `get_text(separator=" ")`
- Odds: `button[betbuttontype="odd"]` → `.btn_label.is-top` (name) + `.btn_label` (odds)
- Kickoff: `.scoreboard_hour`
- Market count: `.event_betsNum` (e.g., "+24")

### Match Detail Pages
- Markets: `sports-markets-single-market` → `.marketBox_headTitle` + `.marketBox_lineSelection`
- Tabs per sport: Football has 8 (MyCombi, Top, Wynik, Strzelcy, Gole, Metoda gola, Wynik/Handicap, Statystyki)
- Only active tab renders odds in DOM

### Polish Locale
- Comma decimals: `"8,25"` → `8.25` via `polish_decimal()`
- Full market name map (~70 entries, PL→EN) in parser
- Dynamic team-prefixed markets: strip team, match base pattern

### Angular SPA Caveats
- All content client-rendered — needs `wait_for_timeout(3000-4000)` after navigation
- Max ~20 events per listing page
- Match IDs: 15-16 digit pattern (`-m1112013945405440`)
- Volleyball HTML often loads as skeleton (0 events) — not a parser bug

## SPA Content-Ready Selectors (`site_selectors.json`)
| Domain | Selector | Timeout | Settle |
|--------|----------|---------|--------|
| oddsportal.com | `.participant-name` | 8000ms | 3000ms |
| scores24.live | `.link[class*='sc-mhmn9c']` | 8000ms | 3000ms |
| atptour.com | BLOCKED by Cloudflare | — | — |
