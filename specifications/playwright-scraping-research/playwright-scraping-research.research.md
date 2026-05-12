# Playwright Scraping Research - Sports Deep Data Websites

**Date:** 2026-05-12  
**Scope:** Python Playwright scraping libraries/frameworks, deep-data sports websites for football, tennis, basketball, hockey, and volleyball, and a repo-specific gap analysis for `/Users/mkoziol/projects/bet`  
**Method:** Code read of `betting/sources/source-registry.md`, `specifications/adapter-enrichment-plan.md`, `pyproject.toml`, representative adapters in `scripts/adapters/`, and `scripts/site_selectors.json`, plus general ecosystem knowledge for external libraries and sites.  
**Important limitation:** This workspace does **not** provide live web browsing or live GitHub metadata lookup. GitHub stars, last-commit dates, and some 2026 anti-bot behaviors therefore remain marked **needs verification** unless already documented in the repo.

---

## 1. Executive Summary

The current repo already has a meaningful Playwright surface, but adapter count overstates actual deep-data coverage. The codebase has 17 named adapters plus the raw fallback, yet only a small subset currently emits materially deep structured data:

- `scores24_adapter.py`: deepest current HTML adapter; extracts odds, H2H, recent form, trends, venue, surface, and tournament data from detail pages.
- `totalcorner_adapter.py`: football-only, useful for corners, cards, dangerous attacks, and total-goals lines.
- `soccerstats_adapter.py`: football league/team averages for corners, cards, and fouls.
- `whoscored_adapter.py`: partial football stat extraction, but brittle because the site is JS-heavy.
- `forebet_adapter.py`: prediction probabilities, scoreline model output, and match URLs.
- `tennisabstract_adapter.py`: deep player-rating data, but not match-level serve/return stats.

Per sport, the repo is strongest in football, workable in tennis and NHL-level hockey, partially covered in basketball via APIs, and weakest in volleyball. The best near-term uplift comes from adding better sources, not from replacing Playwright itself.

**Highest-value missing source families:**

| Priority | Source family | Why it matters |
|----------|---------------|----------------|
| 1 | CEV + VolleyballWorld + PlusLiga | Volleyball is the current weakest sport and the repo already documents an empty/underfed stats cache for it. |
| 2 | NaturalStatTrick + MoneyPuck | Hockey lacks advanced xG, shot-quality, and high-danger data despite hockey protocols explicitly depending on it. |
| 3 | UltimateTennisStatistics + deeper TennisAbstract pages | Tennis currently has H2H/surface/Elo, but not strong serve, return, and break-point splits. |
| 4 | Transfermarkt | Fills coach-change, roster, transfer, and injury-history context that the analytical workflow already expects. |
| 5 | Eurobasket + RealGM + Proballers | Biggest gap for non-NBA basketball depth, especially Europe and minor leagues. |

**Library recommendation in one sentence:** stay on Playwright as the base, add `Crawlee` if crawl breadth and retry/session/proxy control become a bottleneck, use `scrapy-playwright` only for very large historical backfills, and treat stealth tooling as tactical rather than foundational.

---

## 2. Current Repository Baseline

### 2.1 Actual adapter depth in the current repo

| Source / adapter | Repo status | Current depth | Notes |
|------------------|-------------|---------------|-------|
| Flashscore | Existing adapter | Shallow-medium | Current adapter parses listing rows, league context, standings markers, live status, scores, and match URLs, but not deep detail-page stats yet. |
| Sofascore | Existing adapter | Shallow-medium | Uses Sofascore public API for scheduled events only; does not currently pull match stats, H2H, venue, or richer event detail. |
| Scores24 | Existing adapter | Deep | Best current HTML source. Detail-page parser extracts odds, H2H, recent form, venue, surface, round, and betting trends. |
| BetExplorer | Existing adapter | Medium | Odds-oriented. Good for price comparison, weak for stats. |
| OddsPortal | Existing adapter | Medium | Odds-oriented. Current adapter is still mostly H2H pricing rather than deep statistical data. |
| Soccerway | Existing adapter | Shallow | Useful global football coverage, but current adapter mostly returns fixtures. |
| SoccerStats | Existing adapter | Medium-deep | Valuable football league/team averages for corners, cards, and fouls. |
| TotalCorner | Existing adapter | Medium-deep | Football-specific. Rich table structure already parsed for corners/cards/attacks. |
| WhoScored | Existing adapter | Medium, brittle | Pulls some visible stats, but current extraction relies on regex against JS-heavy markup. |
| TennisExplorer | Existing adapter | Medium | Match schedules, surfaces, tournament context; lacks deeper serve/return stats. |
| TennisAbstract | Existing adapter | Deep ratings only | Elo and surface-specific Elo are valuable, but current parser is limited to the Elo table. |
| Basketball-Reference | Existing adapter | Shallow | Current adapter only parses schedule-level data, not advanced team/game tables. |
| Hockey-Reference | Existing adapter | Shallow | Same issue as Basketball-Reference: schedule only, not deep team/game splits. |
| Covers | Existing adapter | Medium | Good for US-sport betting consensus and totals/spread context, not raw deep stats. |
| Betclic | Existing adapter | Medium | Odds/market extraction only. Not relevant for deep data. |

### 2.2 Repo-verified sport coverage assessment

| Sport | Current state | Main strengths | Main gaps |
|-------|---------------|----------------|-----------|
| Football | Strongest current scraping stack | TotalCorner, SoccerStats, Scores24, WhoScored, Understat client, Flashscore/Sofascore/Soccerway coverage | Transfer context, broader xG beyond Understat, deeper Flashscore/Sofascore detail pages, FBref blocked in registry |
| Tennis | Medium | TennisExplorer, TennisAbstract Elo, Flashscore/Sofascore fixture coverage | Aces, double faults, first-serve, break-point, serve/return splits are still thin |
| Basketball | Medium for NBA, weak for Europe | ESPN, `nba_api`, Basketball-Reference as a potential base, Covers for odds context | European league depth, roster changes, advanced non-NBA team stats |
| Hockey | Medium for NHL, weak for advanced-model depth | ESPN/API-Hockey baseline, Hockey-Reference base, Scores24 coverage | NaturalStatTrick/MoneyPuck xG layer, goalie confirmations, European-league roster depth |
| Volleyball | Weakest | Flashscore/Sofascore/BetExplorer generic coverage | No dedicated deep-stat adapter, official competition stats missing, repo notes say volleyball stats cache is underfed/empty |

### 2.3 DOM and extraction patterns already understood in the repo

These patterns are grounded in current adapter code and selector inventory.

- `flashscore_adapter.py` already targets `.event__match`, `.event__homeParticipant`, `.event__awayParticipant`, `.event__time`, and score/status classes. This means listing pages are understood; detail pages are still underexploited.
- `scores24_adapter.py` already understands listing URLs like `/en/{sport}` and detail URLs like `/en/{sport}/m-{DD-MM-YYYY}-{slug}` and extracts W1/X/W2, handicap lines, totals, H2H, form, and trends.
- `totalcorner_adapter.py` already uses table-cell classes such as `td_league`, `match_home`, `match_away`, `match_goal`, `match_handicap`, and reads cards plus dangerous-attacks cells.
- `site_selectors.json` already includes consent selectors for `transfermarkt.com`, `tennisexplorer.com`, `ultimatetennisstatistics.com`, `eurobasket.com`, `naturalstattrick.com`, `moneypuck.com`, and `cev.eu`, which is a useful signal that these domains were already profiled for Playwright navigation.

---

## 3. Playwright Scraping Libraries and Frameworks (Python ecosystem)

### 3.1 Evaluation criteria

The relevant criteria for this repo are not generic web-crawling features. They are:

- Session persistence across many match-detail pages.
- Proxy rotation for fragile or rate-limited sites.
- Retry logic for transient 403/429/500 responses.
- Concurrency control for 5-sport daily scans.
- Ability to keep a Python-first stack.
- Low-friction integration with the repo's current plain-Playwright adapters.

### 3.2 Library / framework comparison

| Tool | Category | Python support quality | GitHub stars | Last update | Maintenance status | Key features | How it could enhance this repo | Sports-scraping pros | Sports-scraping cons | Recommendation |
|------|----------|------------------------|--------------|-------------|--------------------|--------------|-------------------------------|---------------------|---------------------|----------------|
| Plain Playwright | Browser automation base | Strong, already installed | n/a | n/a | Stable foundation | Browser contexts, routing, storage state, tracing, CDP, headless/headful modes | Already the project's base. Good enough for current adapters and focused detail-page fetches. | Lowest integration risk; team already uses it; predictable debugging | You must build your own queue, retry, session-pool, and proxy orchestration | Keep as baseline |
| Crawlee (Apify) | High-level crawler framework on top of Playwright | Good native Python support; Python side is younger than the JS ecosystem | Needs verification | Needs verification | Likely active, commercial-backed | Request queue, retry policies, autoscaled concurrency, session pool, proxy rotation hooks, persistent storage | Best candidate if the repo starts crawling hundreds or thousands of match detail pages per run | Very good fit for Scores24-style detail crawling and fragile sources like Transfermarkt or official federation sites | Adds abstraction and crawler lifecycle overhead; may be more than needed for small daily fetches | Best upgrade path if crawl breadth expands |
| scrapy-playwright | Scrapy integration for Playwright | Good if the team accepts Scrapy concepts | Needs verification | Needs verification | Apparently active, needs live verification | Scrapy scheduler, request deduplication, AutoThrottle, pipelines, persistent crawl jobs with Playwright rendering per request | Useful for historical backfills, multi-page source discovery, and wide federation-site traversals | Very strong at large crawl footprints and resumable jobs | Heavy architectural shift for a repo that is currently adapter-centric, not spider-centric | Good for backfills, not first upgrade |
| playwright-stealth | Stealth patch layer | Community Python package, quality lower than Playwright itself | Needs verification | Needs verification | Community-maintained, needs live verification | Applies anti-detection patches to Playwright pages/contexts | Tactical help for sites that punish stock browser fingerprints | Low-cost additive layer; easy to test per domain | Does not solve queues, retries, proxies, or structured extraction; stealth packages can rot fast | Use tactically, not as foundation |
| playwright-extra | Plugin ecosystem around Playwright | Weak for Python; primarily a Node.js ecosystem | Needs verification | Needs verification | Node-first; Python path unclear | Plugin model, often used with stealth plugins in JS stacks | Limited value unless the repo wants to maintain a Node sidecar just for scraping | Large JS ecosystem if you were a Node shop | Poor fit for a Python-first repo; introduces cross-runtime complexity | Not recommended for this repo |
| browserless | Remote browser service / browser infrastructure | Good from Python via Playwright remote connection; not a Python library in the narrow sense | Needs verification | Needs verification | Commercial product, likely active | Remote browser pools, horizontal scaling, session lifecycle, optional proxy/fingerprint services depending on plan | Helps when local Playwright becomes the bottleneck or when IP/browser reputation matters | Good for bursty scans, CI, and remote debugging; centralizes browser infra | Adds external dependency, cost, and vendor coupling; not needed for most SSR sites | Use only after local scaling pain is real |
| nodriver | Playwright-adjacent browser automation, not Playwright-native | Good Python package, but separate stack | Needs verification | Needs verification | Apparently active, needs verification | CDP-based automation with a stronger anti-detection posture than stock Selenium-style tools | Could help against highly defended targets if Playwright fails consistently | Good stealth reputation in the Python community | Would fragment the stack away from Playwright; adapters would need a second runtime model | Keep as exception path only |
| undetected-playwright | Community stealth concept / package family | Unclear in Python, no strong mature project verified from this workspace | Needs verification | Needs verification | Uncertain | Anti-detection wrapper concept | Only relevant if a stable Python project is confirmed | If real and maintained, it could reduce detection on hostile targets | Maintenance and trustworthiness are unclear; high risk of dead-end adoption | Do not adopt without live verification |

### 3.3 Practical conclusion on libraries

For this repo, there are really three tiers:

1. **Tier 1 - adopt now if needed:** plain Playwright, optionally `Crawlee`.
2. **Tier 2 - adopt for a specific workload:** `scrapy-playwright` for large historical crawls, `browserless` for scale/ban mitigation.
3. **Tier 3 - use only tactically:** `playwright-stealth`, `nodriver`, and any unverified `undetected-playwright` package.

The repo's current problem is not that Playwright is missing stealth. The current problem is that several high-value sources are not yet integrated and many existing adapters stop at listing pages.

### 3.4 Other adjacent tools worth watching, not standardizing on yet

These are worth a live verification pass, but they are not strong enough from this workspace alone to recommend for the core stack:

- `Patchright`: Playwright-adjacent anti-detection patching concept. Python support and long-term maintenance need verification.
- `Camoufox` or similar stealth-browser bundles: potentially useful for hostile targets, but they would add browser-profile complexity and should only be considered if stock Playwright plus selective stealth fails.
- Rebrowser-style Playwright patches: more common in Node ecosystems than in Python workflows; interesting, but not a clean fit for this repo without a separate runtime decision.

---

## 4. Best Deep Data Websites by Sport

## 4.1 Football

| Site | Deep data available | Rendering / DOM notes | Anti-bot / access | Login / subscription | Coverage / freshness | Existing project status | Sports-use verdict |
|------|---------------------|-----------------------|-------------------|----------------------|----------------------|-------------------------|--------------------|
| Understat | xG, xGA, shot-level data, team and match advanced metrics; strongest xG layer in the current stack | Public site typically exposes data through script-embedded JSON rather than requiring heavy DOM interaction; Playwright usually not necessary | Low-moderate; repo already uses Python client rather than browser scraping | No login for public data | Top 6 EU leagues only; strong post-match freshness | **API client exists**; no HTML adapter required today | Keep as xG backbone; not a Playwright priority unless client limitations emerge |
| Transfermarkt | Transfers, squad values, injuries history, coaching changes, roster turnover, contract info | Mostly SSR table pages plus cookie consent; good candidate for table extraction rather than pixel scraping | Moderate; cookie wall and some rate sensitivity are likely | Public browsing usually works without login; some features may be limited | Very broad global football coverage; useful even in lower divisions | **No adapter**; selector profile exists in `site_selectors.json` | High-value missing source because it fills context the pipeline already expects |
| SoccerStats | Corners, cards, fouls, BTTS, over/under rates, home/away splits, league averages | Table-driven SSR pages; adapter-enrichment plan already treats it as a stat source | Access in repo is documented as intermittent HTTP 500 rather than hard bot-blocking | No login | Broad football league coverage; not truly live, but good prematch context | **Existing adapter** with medium-deep value | Enrich current adapter rather than replace it |
| TotalCorner | Corners, corner handicaps, corner counts, dangerous attacks, live-style pressure signals, total-goals lines | Repo already understands the table row structure (`match_home`, `match_away`, `match_handicap`, etc.) | Repo documents access as OK via Playwright | No login needed for public pages | Strong for today's matches and corner markets; high freshness | **Existing adapter** with meaningful depth | One of the best current football sources; should be deepened before adding lower-value alternatives |
| WhoScored | Possession, shots, shots on target, passes, lineups, player ratings, formations, richer team/match stats | JS-heavy SPA; current adapter uses best-effort regex against rendered text, which is brittle | Moderate; JS heaviness is the main operational challenge | Public browsing usually works | Strongest in major leagues, weaker in obscure leagues | **Existing adapter**, partial depth | Useful for top-league detail, but not the first football priority because other gaps are larger |
| Soccerway | Fixtures, standings, H2H, squad lists, and often referee context | Mostly SSR and parseable by tables/links | Low-moderate | No login | Very broad global coverage and especially useful for exotic leagues | **Existing adapter**, currently shallow | High-value enrichment target because the site breadth is already proven in the registry |
| Flashscore | Fixtures, H2H, live match stats, result context, and detail-page data across many leagues | Listing DOM is already understood in the repo; deeper detail pages remain largely untapped | Moderate; JS-heavy | Public pages; no login required for core browsing | Very broad and fresh, including live | **Existing adapter**, currently listing-oriented | Good enrichment target, especially for detail pages and live-window checks |
| Sofascore | Team form, lineups, ratings, scheduled events, match stats, some odds context | Better treated as API-backed SPA than as raw DOM scraping | Moderate | Public access usually works without login | Broad multi-sport coverage, very fresh | **Existing adapter** but only uses scheduled-events API | Strong enrichment target through deeper API endpoints, not through heavier DOM scraping |
| FBref | Standard tables, shooting, possession, misc, keeper, and xG-rich tables for many competitions | Mostly SSR, often table-centric; some content can be hidden in comment-wrapped HTML blocks | **Repo registry marks FBref as 403** from current environment | No login for public pages | Broad coverage and very strong analytical depth | **No adapter**; registry currently marks it blocked | High upside, but experimental unless access can be stabilized |
| FootyStats | Team-level attack/defense, corners, cards, xG-like summary views on some pages | Mixed access; team pages may be more accessible than landing pages | **Repo registry marks main pages as 403**; individual team pages only sometimes work | Premium gating on some data | Broad global coverage | **No adapter**; fallback only | Useful only as opportunistic fallback, not as a core source |

**Football conclusion:**

- The repo already covers football better than the other four sports.
- The highest-value missing football source is `Transfermarkt`, not another odds site.
- The highest-value football adapter upgrades are deeper `Sofascore`, deeper `Flashscore`, and richer `Soccerway` detail parsing.
- `FBref` has major upside but remains access-risky because the repo already records it as blocked.

## 4.2 Tennis

| Site | Deep data available | Rendering / DOM notes | Anti-bot / access | Login / subscription | Coverage / freshness | Existing project status | Sports-use verdict |
|------|---------------------|-----------------------|-------------------|----------------------|----------------------|-------------------------|--------------------|
| TennisExplorer | H2H, schedules, results, surface context, rankings, lower-tier draws | Mostly SSR tables with player links and round headers; current adapter already handles this pattern | Low-moderate | Public | Strong ATP/WTA/Challenger/ITF breadth; good for prematch context | **Existing adapter** | Keep and enrich, especially for deeper H2H and draw parsing |
| TennisAbstract | Elo, surface Elo, forecast context, matchup and player-profile stats, serve/return intelligence on player pages | Elo table is SSR and already parsed; deeper player pages likely table-driven too | Low-moderate | Public | Very useful for prematch strength and surface context | **Existing adapter** but only for Elo table | High-value enrichment target; current adapter leaves a lot of value on the table |
| UltimateTennisStatistics | Elo, serve %, return %, hold/break rates, H2H explorer, surface filters, historical performance splits | Likely dynamic tables/dashboard, but repo already has consent selectors profiled; live DOM still needs verification | Low-moderate, needs live verification | Public access appears available; premium status for some views needs verification | ATP coverage is strong; WTA breadth needs verification | **No adapter**; selector profile exists | Best missing tennis source for serve/return and break-point-style markets |
| ATP Tour official | Draws, order of play, rankings, official results, some player/match stats | Modern JS-heavy site; likely better approached through network/API inspection than naive DOM scraping | Moderate | Public | Official and timely, especially for tournament schedule completeness | **No adapter** | Very good for fixture completeness and official match stats |
| WTA official | Same class of value as ATP: draws, schedules, rankings, official match information | Modern JS-heavy site; API/network inspection likely preferable | Moderate | Public | Official and timely for WTA events | **No adapter** | Good complement to ATP official, especially for draw completeness |
| Flashscore Tennis | Live scores, results, H2H, broad tournament coverage including ITF | JS-heavy, but the repo already parses listing structures | Moderate | Public | Very broad and very fresh | **Existing adapter**, currently shallow | Good support source, but not the source that fixes the current tennis stat gap |
| Jeff Sackmann datasets | Historical match, ranking, and draw data; excellent offline reference for long-horizon modeling | Not a Playwright target; static dataset workflow is a better fit | n/a | Public datasets | Excellent historical depth, not a live-data source | **No integration** | Very high-value offline supplement, but outside the Playwright scraping lane |

**Tennis conclusion:**

- Current tennis scraping is strong on fixture/H2H/surface identity and weak on serve/return depth.
- The best missing live-web target is `UltimateTennisStatistics`.
- The best existing-source upgrade is deeper `TennisAbstract` player-page extraction.
- ATP/WTA official pages are good for draw integrity and official stat confirmation.

## 4.3 Basketball

| Site | Deep data available | Rendering / DOM notes | Anti-bot / access | Login / subscription | Coverage / freshness | Existing project status | Sports-use verdict |
|------|---------------------|-----------------------|-------------------|----------------------|----------------------|-------------------------|--------------------|
| Basketball-Reference | Team/game logs, advanced stats, pace, offensive/defensive ratings, lineup and historical tables | Mostly SSR table pages; current adapter only uses the schedule table | Low-moderate | Public | Excellent for NBA and historical depth | **Existing adapter**, currently shallow | Strong enrichment target because the site itself is richer than the current parser |
| NBA.com/stats | Official pace, advanced team/player stats, tracking-style splits, game logs | Modern SPA with network-driven data; scraping DOM is usually worse than using network/API methods | Moderate | Public | Highest official NBA freshness | **No adapter**, but `nba_api` already covers much of the value | Lower priority for Playwright because API access already exists |
| Eurobasket | European league standings, team/player stats, schedules, rosters across many leagues | Likely a mix of SSR tables and navigation pages; repo already has consent selectors profiled | Low-moderate | Public | Very broad European coverage; strong non-NBA value | **No adapter**; selector profile exists | One of the best missing basketball sources |
| RealGM Basketball | Rosters, transactions, schedules, standings, historical league/team context | Mostly parseable page structure; likely less dynamic than NBA.com | Low-moderate | Public | Good NBA and international roster/schedule context | **No adapter** | Good complement to Eurobasket, especially for roster changes |
| Proballers | Global player/team database, career history, season-by-season stats across many leagues | Live DOM needs verification; likely mixed SSR/JS | Needs verification | Public access appears available; premium state needs verification | Broad global league coverage | **No adapter** | Medium-high value for international depth, but needs a live DOM check first |
| StatMuse | Natural-language stat retrieval, useful for quick question-driven lookups | Query-driven UI rather than table-first crawling; not ideal for systematic scraping | Moderate; likely rate-limited for bulk use | Public | Strong for ad hoc NBA/NHL queries | **No adapter** | More useful as analyst tooling than as a production batch scraper |

**Basketball conclusion:**

- The repo is not missing NBA data as badly as it is missing European and minor-league basketball structure.
- `Eurobasket` is the clearest missing high-impact source.
- `RealGM` is the best roster and transaction complement.
- `Basketball-Reference` should be enriched before chasing harder dynamic sites.

## 4.4 Hockey

| Site | Deep data available | Rendering / DOM notes | Anti-bot / access | Login / subscription | Coverage / freshness | Existing project status | Sports-use verdict |
|------|---------------------|-----------------------|-------------------|----------------------|----------------------|-------------------------|--------------------|
| Hockey-Reference | Team/game logs, goalie stats, team splits, schedule and box-score context | Mostly SSR table pages; current adapter only uses schedules | Low-moderate | Public | Strong NHL depth, less useful for broader Europe coverage | **Existing adapter**, currently shallow | Worth enriching, but not enough on its own |
| NaturalStatTrick | xG, xGF/xGA, Corsi, Fenwick, high-danger chances, special-teams splits, goalie data | Commonly table-driven query pages; likely easier to scrape than full SPA dashboards | Low-moderate; repo already profiles consent selectors | Public | NHL-focused, strong analytical depth | **No adapter**; selector profile exists | Best missing hockey source, full stop |
| MoneyPuck | xG model outputs, win probabilities, team/player cards, shot-quality views | Likely a mix of charts/tables and JS-rendered views; live DOM still needs verification | Low-moderate; repo already profiles consent selectors | Public | NHL-focused and model-rich | **No adapter**; selector profile exists | Very strong secondary advanced source after NaturalStatTrick |
| EliteProspects | Rosters, player profiles, transfers, depth charts across NHL and European leagues | Likely SSR profile and roster pages | Moderate | Public with some premium areas possible | Broad global hockey coverage | **No adapter** | High-value for roster context, especially outside NHL |
| QuantHockey | Historical leaderboards, team/player stats, situational tables | Likely SSR table-driven site; live DOM needs verification | Low-moderate, needs verification | Public | Good for historical and league-wide quantitative context | **No adapter** | Useful but secondary to NaturalStatTrick and MoneyPuck |
| HockeyDB | Historical player/team data and roster history | Traditional SSR-style pages | Low | Public | Deep historical archive rather than advanced modern analytics | **No adapter** | Good support source, not the main analytical upgrade |

**Hockey conclusion:**

- The biggest hockey gap is advanced shot-quality modeling, not fixture coverage.
- `NaturalStatTrick` should be the first new hockey adapter.
- `MoneyPuck` is the next-best complement for model cross-checks.
- `EliteProspects` matters because the pipeline also cares about roster and player availability context.

## 4.5 Volleyball

| Site | Deep data available | Rendering / DOM notes | Anti-bot / access | Login / subscription | Coverage / freshness | Existing project status | Sports-use verdict |
|------|---------------------|-----------------------|-------------------|----------------------|----------------------|-------------------------|--------------------|
| VolleyballWorld | Official FIVB tournaments, rankings, match center, team stats, schedules, competition context | Likely modern SPA with API-backed pages; live DOM/network inspection still needed | Moderate, needs verification | Public browsing appears available | Highest-value international volleyball source | **No adapter** | Top missing volleyball source |
| CEV | Official European club competitions, standings, team stats, match reports, Champions League/CEV Cup context | Repo already profiles consent selectors; likely page-driven with JS-enhanced match centers | Low-moderate | Public | Very strong for European club competitions | **No adapter**; selector profile exists | Top missing volleyball source, especially for club competitions |
| Flashscore Volleyball | Fixtures, results, H2H, live score context | JS-heavy, but listing DOM is already partly understood through the generic Flashscore adapter | Moderate | Public | Broad and fresh | **Existing adapter**, shallow | Useful support source, but not the fix for the current volleyball data gap |
| Sofascore Volleyball | Form context, scheduled events, some match detail potential through API endpoints | Better approached through public API/network inspection than through raw DOM | Moderate | Public | Broad and fresh | **Existing adapter** but shallow | Good immediate enrichment target |
| PlusLiga | Official Polish league standings, team stats, player info, match reports | Official site likely table/content-page based; repo already has cookie selectors for it | Low-moderate | Public | High-value local-league source for a Betclic PL workflow | **No adapter**; selectors exist for the domain | Very strong local priority even if it is not globally broad |
| VolleyMob | Editorial coverage, match previews, rankings, some stats/news content | Likely content/article-driven rather than structured table-first | Low-moderate | Public | Broad but less structured than official sources | **No adapter** | Medium value; better as narrative supplement than as primary structured stat source |
| Volleyball-Movies | Reported to contain volleyball stats and match information, but structured depth needs live verification | DOM and structured-data quality need verification | Needs verification | Needs verification | Coverage/freshness need verification | **No adapter** | Low priority until verified |

**Volleyball conclusion:**

- Volleyball is the clearest weak point in the current repo.
- Official sources matter most here: `VolleyballWorld`, `CEV`, and `PlusLiga` are the best next adapters.
- `Flashscore` and `Sofascore` should remain support layers, not the main deep-stat backbone.

---

## 5. Gap Analysis

### 5.1 High-value sources with no adapter yet

| Sport | Source | Why it is a real gap |
|-------|--------|----------------------|
| Football | Transfermarkt | The analytical workflow already expects coach/roster context; this source fills that better than existing adapters. |
| Football | FBref | High analytical upside for match/team tables and xG-rich context, but access risk is real. |
| Tennis | UltimateTennisStatistics | Best route to serve/return and break-point splits not currently covered well. |
| Basketball | Eurobasket | The cleanest answer to non-NBA team/player/standing depth. |
| Basketball | RealGM | Strong roster/transaction complement for both NBA and international contexts. |
| Hockey | NaturalStatTrick | Explicitly required by hockey analysis logic; currently missing. |
| Hockey | MoneyPuck | Critical secondary advanced-model source for NHL. |
| Hockey | EliteProspects | Roster and player context for European leagues is still thin. |
| Volleyball | VolleyballWorld | Best official global-volleyball data source currently missing. |
| Volleyball | CEV | Best official European club-volleyball source currently missing. |
| Volleyball | PlusLiga | Best local Polish-league source currently missing. |

### 5.2 Existing adapters that should be enriched before adding more sources

| Adapter | Why enrichment is attractive |
|---------|-----------------------------|
| Flashscore | Listing structure is already understood; the missing value is on detail pages, not source discovery. |
| Sofascore | Public API path is already integrated, but only at schedule depth. There is more value available before switching stacks. |
| TennisAbstract | Current parser only covers Elo tables; player pages likely hold the deeper serve/return data the tennis pipeline wants. |
| Basketball-Reference | The site itself is much richer than the current schedule-only adapter. |
| Hockey-Reference | Same issue as Basketball-Reference. |
| Soccerway | Huge breadth already documented in the registry, but the current adapter uses only a fraction of it. |
| WhoScored | Could become more valuable for top-league football if stabilized, though it is not the first repo priority. |

### 5.3 Weakest current sports by deep-data coverage

| Rank | Sport | Why |
|------|-------|-----|
| 1 | Volleyball | No dedicated deep-stat adapter, official sources missing, and repo notes already flag the stats cache as weak/empty. |
| 2 | Hockey | Baseline data exists, but advanced xG/Corsi/goalie workflow requirements are under-served without NaturalStatTrick/MoneyPuck. |
| 3 | Basketball | NBA is covered by APIs, but European and minor-league basketball remains shallow. |
| 4 | Tennis | Good fixture/H2H/Elo coverage, weak serve/return split coverage. |
| 5 | Football | Already the best-covered sport; gaps are real but not existential. |

---

## 6. Recommendations

### 6.1 Ranked opportunities by impact

Difficulty scale:

- **Low:** mostly table parsing or existing-source enrichment.
- **Medium:** moderate navigation, pagination, or detail-page traversal.
- **High:** JS-heavy pages, fragile anti-bot posture, or significant normalization work.

| Rank | Library + website combination | Impact | Difficulty | Why this should rank here |
|------|-------------------------------|--------|------------|---------------------------|
| 1 | Plain Playwright or Crawlee + CEV + VolleyballWorld + PlusLiga | Very high | Medium-high | This directly attacks the weakest current sport and aligns with repo-documented volleyball gaps. |
| 2 | Plain Playwright or Crawlee + NaturalStatTrick | Very high | Medium | This is the cleanest way to add the advanced hockey metrics the analysis workflow already wants. |
| 3 | Plain Playwright + UltimateTennisStatistics | High | Medium | Best missing source for tennis service, return, hold, break, and surface splits. |
| 4 | Plain Playwright + Transfermarkt | High | Medium | Fills coach-change, roster, transfer, and injury-history context that the workflow already references. |
| 5 | Plain Playwright + Eurobasket | High | Medium | Biggest non-NBA basketball uplift with broad league coverage. |
| 6 | Plain Playwright + deeper Sofascore API endpoints | Medium-high | Low-medium | Existing source, existing integration path, and better than adding a new source first in some cases. |
| 7 | Plain Playwright + deeper Flashscore detail-page parsing | Medium-high | Medium | The repo already knows the listing DOM. Detail pages are a natural next step. |
| 8 | Plain Playwright + MoneyPuck | Medium-high | Medium-high | Strong secondary hockey model source after NaturalStatTrick. |
| 9 | Playwright-stealth on selected domains only | Medium | Low | Good tactical support for fragile targets, but not a primary data strategy. |
| 10 | Browserless for remote execution | Medium | Medium | Only worthwhile once crawl volume, IP reputation, or CI stability becomes a real problem. |

### 6.2 Recommended library strategy for this repo

1. **Do not replace Playwright.** The repo is already invested in it and the main missing value is source coverage and deeper extraction.
2. **Add Crawlee only when the daily workload becomes multi-page and failure-prone.** It is the cleanest Python-side way to add queues, retries, sessions, and proxy hooks without rewriting everything around Scrapy.
3. **Keep stealth tooling tactical.** Use `playwright-stealth` only where a specific source proves sensitive. Do not make the entire scraping stack depend on stealth patches.
4. **Use browserless later, not first.** It is a scaling and browser-infra decision, not a data-model decision.
5. **Avoid a second browser stack unless absolutely necessary.** `nodriver` and any `undetected-playwright` option should be reserve tools, not the standard.

### 6.3 Recommended source-adoption order

1. CEV + VolleyballWorld + PlusLiga
2. NaturalStatTrick
3. UltimateTennisStatistics
4. Transfermarkt
5. Eurobasket
6. MoneyPuck
7. Flashscore detail pages
8. Sofascore deeper endpoints
9. RealGM / EliteProspects as roster-context complements
10. FBref only after access risk is revisited

### 6.4 What not to prioritize yet

- Do not standardize on `playwright-extra`; it is a poor Python fit.
- Do not move the whole scraping layer to `scrapy-playwright` unless you explicitly want a spider-based architecture.
- Do not spend the first implementation cycle chasing `FBref` or `FootyStats` while volleyball, hockey advanced analytics, and tennis serve/return depth remain open.
- Do not use Playwright where the repo already has a better API path, especially for `Understat` and much of `NBA.com` data via `nba_api`.

---

## 7. Verification Backlog

These items require live verification before implementation planning or library selection is finalized:

- Current GitHub stars and last update dates for `Crawlee`, `scrapy-playwright`, `playwright-stealth`, `browserless`, `nodriver`, and any `undetected-playwright` candidate.
- Live DOM and network behavior for `UltimateTennisStatistics`, `VolleyballWorld`, `Proballers`, `QuantHockey`, and `Volleyball-Movies`.
- Whether `FBref` is still blocked from the current environment in May 2026 or can be stabilized through browser tuning/proxying.
- Which `Sofascore` event/match endpoints expose the richest stat payloads for volleyball and hockey without requiring a more fragile browser flow.
- Whether the chosen browserless plan, if any, actually includes the proxy/session/fingerprint features needed for sports-source scraping.

---

## 8. Final Assessment

The repo does **not** need a radically different browser stack. It needs a better source portfolio and deeper extraction on sources it already touches.

The most defensible near-term move is:

1. Keep Playwright.
2. Add `Crawlee` only if retry/session/proxy orchestration becomes painful.
3. Prioritize official and analytically unique sites over anti-detection tooling.

If the goal is maximum data-quality uplift per unit of engineering effort, the best next wave is:

- Volleyball: `CEV`, `VolleyballWorld`, `PlusLiga`
- Hockey: `NaturalStatTrick`, then `MoneyPuck`
- Tennis: `UltimateTennisStatistics`, then deeper `TennisAbstract`
- Football: `Transfermarkt`, then deeper `Sofascore` / `Flashscore`
- Basketball: `Eurobasket`, then `RealGM`