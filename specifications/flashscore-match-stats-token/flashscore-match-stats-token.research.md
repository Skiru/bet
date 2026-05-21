# flashscore-match-stats-token - Analysis Result

## Task Details

| Field | Value |
|---|---|
| Jira ID | N/A |
| Title | Flashscore match stats token research |
| Description | Research how the current codebase can overcome the loss of reliable access to Flashscore match-level statistics when the `d.flashscore.com/x/feed/d_st_{event_id}` endpoint requires a rotating token that cannot be extracted reliably without a browser. Scope includes current dependencies, alternative sources, downstream impact, constraints, contradictions, and requirement-level solution directions only. |
| Priority | High |
| Reporter | User request |
| Created Date | 2026-05-20 |
| Due Date | N/A |
| Labels | research, flashscore, stats, enrichment, settlement |
| Estimated Effort | Research only |

## Business Impact

Flashscore match-level statistics are currently part of the repo's statistical-market pipeline, especially for football corners, cards, shots, and fouls. If the tokenized `d_st_` feed cannot be used reliably, the pipeline risks silent data loss, weaker enrichment, and partial loss of semi-automated settlement.

The largest business risk is not only one broken endpoint. The larger risk is hidden coupling: some workflows already rely on non-Flashscore APIs, some still assume Flashscore match pages or feeds, and some downstream reports depend on `team_form` and `match_stats` without caring which upstream source produced them. A requirements decision is needed so the repo stops mixing incompatible assumptions.

## Gathered Information

### Knowledge Base & Task Management Tools

No Jira, Confluence, Figma, or PDF sources were provided for this task.

Repository memory and internal project documentation reviewed during this research:

- `memories/repo/flashscore-enricher-implementation.md` documents that the curl_cffi Flashscore search + results-page HTML path is considered working, while Playwright was intentionally removed from the enrichment subsystem.
- `memories/repo/pipeline-knowledge-base.md` records that settlement was upgraded to semi-auto for some football stat markets via Flashscore stats and that enrichment was intentionally moved away from Playwright for Flashscore.
- `tsh-research.prompt.md`, `tsh-task-analysing`, and `tsh-codebase-analysing` were used as the required research workflow and output structure.

### Codebase

The codebase is a Python monorepo with DB-first persistence around `match_stats` and `team_form`. Match statistics reach the system through three broad routes:

1. Sport-specific API clients and scrapers.
2. Flashscore HTML/feed helpers.
3. Cache-to-DB writers and downstream consumers that treat `match_stats` and `team_form` as the stable contract.

The current Flashscore-related picture is split, not unified.

#### Flashscore access strategies in the repo

| Strategy | Key files | What it fetches | Current viability | Notes |
|---|---|---|---|---|
| `curl_cffi` + native search + results-page HTML | `scripts/flashscore_enricher.py`, `src/bet/scrapers/flashscore.py`, `scripts/flashscore_bulk_enrich.py`, `scripts/data_enrichment_agent.py` | Entity resolution via `s.flashscore.com/search`, `/results/` page HTML, embedded result feed, team-level recent stat series | Viable now, with limits | This is the path most clearly supported by repo memory and tests. It is good at lightweight team-level data and score-derived series. It is weak for tennis and not a complete deep match-stat replacement on its own. |
| `d.flashscore.com/x/feed/d_st_{match_id}` with static `x-fsign` | `scripts/flashscore_enricher.py`, called by `scripts/flashscore_bulk_enrich.py` | Match-level stat feed for corners/cards/shots/etc. | Not reliable now | This is the narrow surface described in the task. The helper still assumes a static `x-fsign` header works. Comments in the caller already admit it "may fail due to x-fsign". |
| Playwright DOM scraping of Flashscore match pages | `src/bet/api_clients/flashscore.py`, surfaced by `src/bet/api_clients/unified.py` | Match statistics, H2H, preview/form from match pages like `#/match-summary/match-statistics/0` and `#/h2h/overall` | Implemented but operationally contradictory | This path exists, but it conflicts with repo memory that Flashscore should not use Playwright in enrichment. No direct instantiation of `UnifiedAPIClient` was found in the current workspace, so this path looks more like a legacy/side-path than a current pipeline cornerstone. |
| `curl_cffi` + Flashscore match statistics page HTML | `scripts/settle_on_finish.py` | Search for event ID, then fetch `https://www.flashscore.com/match/{match_id}/#/match-summary/match-statistics/0` and regex-parse the HTML | Viable if page HTML remains fetchable | This does not use `d_st_`. It matters because removing the tokenized feed alone does not remove all Flashscore match-level dependency. Settlement still depends on Flashscore match pages. |
| Livesport search API for settlement lookup | `scripts/settle_on_finish.py` | `https://s.livesport.services/api/v2/search/?q=...` to resolve event IDs before loading Flashscore match pages | Appears viable now | This is a separate search strategy from `s.flashscore.com/search`. |

#### Direct code paths that depend on Flashscore match-level stats or the `d_st_` feed

| Code path | Dependency type | Current role | Impact if `d_st_` is gone | Impact if all Flashscore match-page stats are removed |
|---|---|---|---|---|
| `scripts/flashscore_enricher.py::_fetch_match_statistics()` | Direct `d_st_` feed | Fetches per-match stat feed and parses it into stat arrays | Direct break | Direct break |
| `scripts/flashscore_bulk_enrich.py::_try_flashscore_deep()` | Calls `_fetch_match_statistics()` after parsing recent match IDs from `/results/` | Enriches team-level `team_form` with corners/cards/shots deep stats | Direct break | Direct break |
| `src/bet/api_clients/flashscore.py::get_fixture_stats()` | Flashscore match page via Playwright | Returns per-event stat rows | Unaffected by `d_st_` specifically | Breaks |
| `src/bet/api_clients/flashscore.py::get_h2h()` and `get_match_preview()` | Flashscore match pages via Playwright | Deep preview/H2H context | Unaffected by `d_st_` specifically | Breaks |
| `src/bet/api_clients/unified.py::get_fixture_stats()` | Routes football stats through `totalcorner` then `flashscore` | Legacy football stats chain | Unaffected by `d_st_` specifically | Breaks if it falls through to Flashscore |
| `src/bet/api_clients/unified.py::get_deep_data()` | Uses Flashscore preview + match stats | Legacy deep-data contract | Unaffected by `d_st_` specifically | Breaks |
| `scripts/settle_on_finish.py::_fetch_flashscore_match_stats()` | Flashscore match statistics page HTML | Semi-auto settlement for football stat markets | Unaffected by `d_st_` specifically | Breaks |
| `src/bet/api_clients/volleyball_data.py::fetch_match_stats()` | Stale Flashscore delegation | Volleyball helper that still expects Flashscore match stats | Unclear, but stale anyway | Breaks or remains stale |

#### Downstream workflows impacted if the tokenized match-stats endpoint is no longer usable

Directly impacted by loss of `d_st_`:

- `scripts/flashscore_bulk_enrich.py` loses its only deep-stat expansion path beyond the `/results/` page.
- Any `team_form` rows written by that script for corners/cards/shots become less complete or disappear.

Indirectly impacted through weaker `team_form` / `match_stats` coverage:

- `scripts/data_enrichment_agent.py` is not a direct `d_st_` consumer, but it still coexists with Flashscore fallback logic and shares the same downstream tables.
- `src/bet/stats/enrichment.py` computes `team_form` from per-fixture stats and DB caches. It already prefers ESPN and API-Sports, so it is structurally less exposed.
- `scripts/fetch_api_stats.py` persists per-match arrays to both `match_stats` and `team_form`, making these tables the shared contract for downstream consumers.
- `scripts/build_stats_cache.py` and `scripts/db_data_loader.py` bridge cache and DB representations for the same statistical outputs.
- `scripts/deep_stats_report.py` reads `team_form` first. Any reduction in stored stat coverage reduces analysis quality even when the report never calls Flashscore directly.
- `scripts/evaluate_decisions.py` reads actual outcomes from `match_stats`; weaker historical population reduces learning quality for stat markets.
- `scripts/build_league_profiles.py` aggregates from `match_stats`; sparse match stats mean weaker league priors.
- `src/bet/db/repositories.py::StatsRepo` is the stable storage contract for both `match_stats` and `team_form`; anything upstream that changes source strategy should preserve these contracts.

Important distinction:

- Losing `d_st_` is a narrow break with a narrow direct blast radius.
- Removing Flashscore match-level stats entirely is a wider product decision that affects settlement and some legacy deep-data paths.

#### Already-implemented non-Flashscore alternatives for match stats by sport

| Sport | Source | Current coverage | Apparent viability now | Notes |
|---|---|---|---|---|
| Football | ESPN (`src/bet/api_clients/espn.py`) | Corners, fouls, yellow/red cards, shots, shots on target, possession, offsides, saves, passing/cross/tackle/interception metrics, goals | Strong | Already the primary path in `src/bet/stats/enrichment.py`. No API key. Good replacement candidate for many football stat markets. |
| Football | API-Football (`src/bet/api_clients/api_football.py`) | Corners, fouls, yellow/red cards, total shots, shots on target, possession, offsides, saves | Strong if budget/key available | Already implemented and normalized. Good direct replacement candidate for football match stats. |
| Football | TotalCorner (`src/bet/api_clients/totalcorner.py`) | Corner-focused data, plus dangerous-attacks style context | Narrow but usable | Good only for corner-heavy workflows. It is not a general match-stat replacement. It is Playwright-based. |
| Football | Understat (`src/bet/api_clients/understat_client.py`) | xG and shot counts | Supplement only | Useful for shot/xG workflows, not for corners/cards/fouls. |
| Football | Sofascore (`src/bet/api_clients/sofascore.py`) | Broad football stat map including possession, shots, fouls, cards, saves, tackles, passes, crosses, dribbles, big chances | Promising but not currently in primary chains | Implemented as a generic stats API. Not wired into current `FALLBACK_CHAINS` or `STATS_PRIORITY`. |
| Football | Football-Data.org (`src/bet/api_clients/football_data_org.py`) | No per-match detailed stats | Not viable for this problem | Exists in fallback chain, but explicitly returns empty stats. |
| Football | BetExplorer / Soccerway / OddsPortal | No usable per-fixture stats (H2H or odds only) | Not viable for this problem | These are not match-stat replacements. |
| Basketball | ESPN | Rebounds, offensive/defensive rebounds, assists, steals, blocks, turnovers, fouls, fast-break points, points in paint, FG/3PT/FT percentages, points | Strong | Already normalized and broad. |
| Basketball | API-Basketball | Points, rebounds, assists, steals, blocks, turnovers, FG/3PT/FT percentages, offensive/defensive rebounds, fast-break points, points in paint, fouls | Strong if budget/key available | Good direct replacement candidate. |
| Basketball | NBA API (`src/bet/api_clients/nba_api_client.py`) | Points, rebounds, assists, steals, blocks, turnovers, FG/3PT/FT percentages | Strong for NBA only | Useful if basketball scope can be league-specific. |
| Hockey | ESPN | Blocks, hits, takeaways, shots, power-play goals/opportunities, faceoffs won/pct, giveaways, penalties, PIM, goals | Strong | Good direct replacement candidate for NHL-oriented flows. |
| Hockey | API-Hockey | Goals, shots, power-play goals, PIM, hits, blocks, faceoff pct | Strong if budget/key available | Good direct replacement candidate. |
| Hockey | MoneyPuck / ScraperNHL | Advanced season aggregates (Corsi, Fenwick, xG, on-ice stats), not per-match stat rows | Supplement only | Good for advanced enrichment, not a direct replacement for per-fixture market settlement. |
| Tennis | ESPN | Sets won, games won, total sets from linescores | Limited | Good for score-derived markets, weak for richer serve/return markets. |
| Tennis | SofaScore Tennis (`src/bet/api_clients/sofascore_tennis.py`) | Aces, double faults, first serve %, first/second serve points won, break points won/saved, hold %, break %, total games won, streaks, total points won | Strong | Best implemented non-Flashscore tennis replacement in the current repo. |
| Tennis | Tennis Abstract (`src/bet/api_clients/tennis_abstract.py`) | Aces, double faults, 1st serve %, 1st/2nd serve win %, break points saved/faced, hold %, break %, tiebreak and serve/return context | Strong | Already used as a supplementary tennis path in `data_enrichment_agent.py`. |
| Tennis | Sackmann (`src/bet/api_clients/sackmann_adapter.py`) | Aces, double faults, first serve %, first/second serve win %, break points saved/faced, surface/round context | Strong for historical serve stats | Good structured historical source. |
| Tennis | API-Tennis (`src/bet/api_clients/api_tennis.py`) | Would cover aces/DF/serve/break stats, but client is marked NXDOMAIN/deprecated | Not viable now | Explicitly disabled. |
| Volleyball | ESPN | Kills, aces, blocks, digs, assists, errors, hitting %, points, attack volume | Strong | Good existing replacement candidate. |
| Volleyball | API-Volleyball | Points, total points, aces, blocks, attack %, sets won, errors | Strong if budget/key available | Good structured replacement candidate. |
| Cross-sport | Scores24 (`src/bet/api_clients/scores24.py`) | H2H summary / trends from detail URL, not full match stats | Supplement only | Useful for context, not a direct match-stat replacement. |
| Cross-sport | Google Sports / SerpAPI | H2H and search enrichment; no usable `get_fixture_stats(fixture_id)` path | Supplement only | Helpful for discovery/context, not direct match-stat replacement. |

#### Constraints and contradictions verified in the current codebase

| Observation | Verification | Implication |
|---|---|---|
| Team-results HTML path with `curl_cffi` is still treated as working | `scripts/flashscore_enricher.py`, `src/bet/scrapers/flashscore.py`, and `tests/scrapers/test_flashscore.py` all support and test the search + `/results/` path | This is the safest currently implemented Flashscore access pattern. |
| Some code still assumes `d.flashscore.com` works with static `x-fsign` | `scripts/flashscore_enricher.py::_fetch_match_statistics()` sends `x-fsign: SW9D1eZo` directly to `d_st_` | This is the exact brittle assumption the research task calls out. |
| Some code still uses Playwright against `flashscore.com` | `src/bet/api_clients/flashscore.py` is entirely Playwright-based for stats/H2H/preview | Flashscore strategy is inconsistent across subsystems. |
| Repo memory says Flashscore should not use Playwright in enrichment | Verified in repo memory, and the current `scripts/data_enrichment_agent.py` imports only curl_cffi Flashscore helpers | The practical rule is still present in behavior, but the exact `_PLAYWRIGHT_BLOCKED_DOMAINS` symbol is no longer found in the current code search. Memory and code are aligned at the policy level, not at the exact symbol level. |
| `src/bet/stats/enrichment.py` comments still mention "If no API: scrape from Flashscore/Scores24" | The current implementation only tries ESPN and API-Sports in that module | Documentation/comments lag the code. |
| `src/bet/api_clients/unified.py` still routes football stats through `totalcorner` then `flashscore` | `STATS_PRIORITY` only defines football and ignores richer alternatives already implemented elsewhere | Unified routing is stale relative to the broader client set. |
| `src/bet/api_clients/unified.py` and `scripts/_helpers/deep_data_db_writer.py` define a deep-data contract, but no current `UnifiedAPIClient(...)` caller was found in the workspace | Code search found the contract, but no direct instantiation | This looks legacy or at least non-canonical today. |
| `src/bet/api_clients/volleyball_data.py` still assumes a `FlashscoreClient` under `bet.scrapers.flashscore` | That module exposes `FlashscoreScraper` subclasses, not `FlashscoreClient` | This is a stale or broken assumption around Flashscore match stats. |

#### Requirement-level solution directions

| Direction | Scope | Impacted files/modules | Likely risks | Acceptance criteria |
|---|---|---|---|---|
| Replace the tokenized `d_st_` feed by parsing data already present in fetched HTML/pages | Keep Flashscore, but only on the stable search/results or match-page HTML surfaces already used elsewhere | `scripts/flashscore_enricher.py`, `scripts/flashscore_bulk_enrich.py`, `src/bet/scrapers/flashscore.py`, `scripts/settle_on_finish.py`, related tests | HTML may not expose all rich stat categories for every sport; tennis remains weak; parsers remain DOM-fragile | No production path depends on `d.flashscore.com/x/feed/d_st_*`; required stat keys are explicitly documented per workflow; minimum market coverage is validated with representative samples |
| Use browser-assisted bootstrap only to obtain a reusable session/token, then keep non-browser fetching | Allow a bounded browser step solely for Flashscore auth/session bootstrap while preserving non-browser fetchers afterward | Any future shared Flashscore session layer plus `scripts/flashscore_enricher.py`, `scripts/flashscore_bulk_enrich.py`, and possibly `src/bet/api_clients/flashscore.py` if retained | Reintroduces browser operational complexity, session expiry risk, anti-bot fragility, and conflicts with existing enrichment policy | Browser use is isolated, measurable, and not part of every stats call; token/session refresh policy is explicit; failure mode is observable and bounded |
| Remove Flashscore as a match-stats dependency in affected flows and switch to existing per-sport fallback sources | Make ESPN/API-Sports/Sofascore/Tennis Abstract/etc. the canonical providers for per-match stats, while Flashscore may remain only for fixture discovery or results-page form | `src/bet/stats/enrichment.py`, `scripts/data_enrichment_agent.py`, `src/bet/stats/fallback_chains.py`, `src/bet/api_clients/unified.py`, `scripts/settle_on_finish.py`, downstream reports | Coverage gaps remain for some markets/competitions; football settlement may need explicit degradation rules; more source-specific governance is needed | Each sport has a documented canonical source matrix; unsupported markets degrade explicitly rather than silently; no hidden Flashscore dependency remains in match-stat workflows |
| Mixed strategy by workflow or by sport | Keep the working Flashscore results-page HTML path for lightweight team-form use, but move per-match stat workflows to non-Flashscore sources where coverage already exists | Combination of the modules above, plus reporting/storage modules that rely on `team_form` and `match_stats` | More moving parts; harder operational reasoning if ownership is not explicit | Each workflow has one documented source owner; storage contracts (`match_stats`, `team_form`) stay stable; duplicated or stale Flashscore paths are removed or clearly downgraded |

Current codebase fit:

- The strongest fit is a mixed strategy.
- The repo already has strong non-Flashscore per-match substitutes for basketball, hockey, tennis, and volleyball.
- Football already has good substitutes for most match stats, but settlement needs a deliberate policy because Flashscore currently covers stat-market settlement via HTML.
- Browser-assisted token bootstrap should be treated as a policy exception, not the default plan, because it conflicts with the current enrichment direction recorded in repo memory.

### Relevant Links

Relevant internal resources used for this research:

- `scripts/flashscore_enricher.py` - standalone Flashscore helper with both working results-page parsing and the brittle `d_st_` helper.
- `scripts/flashscore_bulk_enrich.py` - only direct caller of the `d_st_` helper.
- `src/bet/api_clients/flashscore.py` - Playwright Flashscore match-page client.
- `src/bet/api_clients/unified.py` - legacy Flashscore-based stats/deep-data routing.
- `src/bet/stats/enrichment.py` - current canonical team-form enrichment path using ESPN/API-Sports first.
- `scripts/data_enrichment_agent.py` - last-resort Flashscore fallback, but only via curl_cffi results-page logic.
- `scripts/settle_on_finish.py` - Flashscore HTML match-page stats used for semi-auto football settlement.
- `src/bet/scrapers/flashscore.py` - modular curl_cffi results-page scraper.
- `src/bet/stats/fallback_chains.py` - canonical non-Flashscore source order per sport.
- `scripts/fetch_api_stats.py`, `scripts/build_stats_cache.py`, `src/bet/db/repositories.py` - shared persistence contract for `match_stats` and `team_form`.
- `scripts/deep_stats_report.py`, `scripts/evaluate_decisions.py`, `scripts/build_league_profiles.py`, `scripts/db_data_loader.py` - downstream consumers affected by upstream stat coverage.
- `memories/repo/flashscore-enricher-implementation.md` - repo memory asserting the results-page curl_cffi path works.
- `memories/repo/pipeline-knowledge-base.md` - repo memory describing recent settlement/enrichment direction changes.

### Relevant Charts & Diagrams

```text
Flashscore / other stat source
        |
        |-- direct deep enrichment: flashscore_bulk_enrich.py
        |-- canonical enrichment: stats/enrichment.py or data_enrichment_agent.py
        |-- legacy deep data: api_clients/unified.py -> deep_data_db_writer.py
        |-- settlement-only path: settle_on_finish.py
        v
   match_stats / team_form
        |
        |-- deep_stats_report.py
        |-- evaluate_decisions.py
        |-- build_league_profiles.py
        |-- db_data_loader.py
        v
   betting decisions, settlement, historical learning
```

## Current Implementation Status

### Existing Components

- Flashscore results-page helper - `scripts/flashscore_enricher.py` - can be reused for stable HTML/results-page access, but its `d_st_` helper needs modification or removal.
- Flashscore bulk deep enrichment - `scripts/flashscore_bulk_enrich.py` - needs modification because it is the only direct caller of the tokenized `d_st_` feed.
- Modular Flashscore scraper - `src/bet/scrapers/flashscore.py` - can be reused as the current non-browser Flashscore HTML strategy.
- Flashscore Playwright client - `src/bet/api_clients/flashscore.py` - needs a product/policy decision; implemented, but not clearly canonical now.
- Unified Flashscore/TotalCorner router - `src/bet/api_clients/unified.py` - needs modification or deprecation because its stats routing is stale relative to the rest of the codebase.
- Canonical enrichment module - `src/bet/stats/enrichment.py` - can be reused; already prefers non-Flashscore providers.
- Enrichment agent - `scripts/data_enrichment_agent.py` - can be reused; Flashscore is only a curl_cffi last resort here.
- Settlement flow - `scripts/settle_on_finish.py` - needs explicit scope decision if Flashscore match-page stats are reduced or removed.
- Cache/DB persistence - `scripts/fetch_api_stats.py`, `scripts/build_stats_cache.py`, `src/bet/db/repositories.py` - can be reused; this is the stable contract that any replacement strategy should preserve.
- Reporting and evaluation consumers - `scripts/deep_stats_report.py`, `scripts/evaluate_decisions.py`, `scripts/build_league_profiles.py`, `scripts/db_data_loader.py` - can be reused but will degrade if upstream stat coverage shrinks.
- Volleyball Flashscore helper - `src/bet/api_clients/volleyball_data.py` - needs extension or cleanup; it still assumes a stale Flashscore match-stats path.

### Key Files and Directories

- `specifications/flashscore-match-stats-token/` - research artifact directory created for this task.
- `scripts/flashscore_enricher.py` - source of truth for current standalone Flashscore logic, including both working and brittle paths.
- `scripts/flashscore_bulk_enrich.py` - only direct `d_st_` consumer.
- `scripts/settle_on_finish.py` - semi-automated settlement path for football statistical markets.
- `scripts/data_enrichment_agent.py` - practical enrichment fallback orchestration.
- `scripts/fetch_api_stats.py` - main match-stat cache/DB writer contract.
- `scripts/build_stats_cache.py` - cache-to-DB bridge for `team_form`.
- `src/bet/api_clients/` - all current structured alternatives by sport.
- `src/bet/stats/fallback_chains.py` - current non-Flashscore source priorities.
- `src/bet/stats/enrichment.py` - current canonical enrichment logic.
- `src/bet/scrapers/flashscore.py` - current curl_cffi Flashscore scraper.
- `src/bet/db/repositories.py` - `StatsRepo` persistence contract.
- `tests/scrapers/test_flashscore.py` - confirms current results-page parsing assumptions at unit-test level.

## Gap Analysis

All missing information and gaps in task description, together with provided answers.

### Question 1
#### Where does the tokenized `d_st_` dependency exist today?
Only one direct runtime path was found: `scripts/flashscore_bulk_enrich.py::_try_flashscore_deep()` calls `scripts/flashscore_enricher.py::_fetch_match_statistics()`. This is the narrow direct blast radius of the rotating-token problem.

### Question 2
#### What still works even if `d_st_` disappears?
The current curl_cffi Flashscore search + `/results/` path still appears viable for lightweight team-form extraction, and `scripts/settle_on_finish.py` uses a separate HTML match-statistics page path rather than `d_st_`. Losing the tokenized feed does not automatically remove every Flashscore-based stat workflow.

### Question 3
#### Is Playwright already prohibited for Flashscore everywhere?
No. The repo memory and enrichment direction clearly discourage or remove Playwright for Flashscore inside enrichment, but `src/bet/api_clients/flashscore.py` still implements Playwright DOM scraping of Flashscore match pages. The codebase therefore has a policy split, not a single rule.

### Question 4
#### Which decision is needed before planning: preserve Flashscore coverage or preserve workflow outcomes?
Open. The repo already has enough non-Flashscore sources to preserve many workflow outcomes, especially outside football. Planning cannot proceed cleanly until it is decided whether the requirement is:

- preserve Flashscore-equivalent match-stat coverage at all costs, or
- preserve betting workflow outcomes even if some markets change source or move to manual fallback.

### Question 5
#### Which markets and sports must remain fully automated if Flashscore match-level stats are reduced or removed?
Open. Football corners/cards/shots/fouls are the highest-risk markets because settlement currently uses Flashscore stats for them. Basketball, hockey, tennis, and volleyball already have stronger non-Flashscore replacement paths in the codebase.

### Question 6
#### Should browser-assisted token/session bootstrap be considered acceptable?
Open. The current codebase direction argues against Playwright for Flashscore inside enrichment. If a browser-assisted bootstrap is allowed, it should be treated as an explicit policy exception rather than an assumed design choice.

### Question 7
#### Should `UnifiedAPIClient` be treated as active architecture or legacy code?
Open. The client and deep-data writer contract exist, but no direct `UnifiedAPIClient(...)` caller was found in the current workspace. Planning should decide whether to modernize it or retire it.

### Question 8
#### What is the recommended planning baseline from this research?
Use a mixed strategy as the default planning baseline:

- do not depend on `d_st_` anymore;
- keep the working non-browser Flashscore results-page path only where it still adds clear value;
- make non-Flashscore sport-specific providers the canonical per-match stats sources;
- decide explicitly whether settlement may keep Flashscore HTML pages or must also move off Flashscore.