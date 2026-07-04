# ZawodTyper Deep Audit

## Code Paths Read

- `scripts/tipster_aggregator.py:195-200` builds the public daily URL using Polish month and weekday slugs.
- `scripts/tipster_aggregator.py:756-934` contains the legacy HTML parser fallback.
- `src/bet/api_clients/tipster_playwright.py:148-287` contains ZawodTyper-specific DOM extraction JavaScript.
- `src/bet/api_clients/tipster_playwright.py:888-942` contains the legacy XHR interception path.
- `src/bet/pipeline/tipster_parsers.py:29-121` contains the pure parser for intercepted `NP_ajax.php` payloads.
- `src/bet/pipeline/tipster_sources.py:8,20` marks ZawodTyper as canonical S2, parser `zawodtyper`, transport `playwright_xhr`, `accuracy_tracked=True`.
- `src/bet/pipeline/core_integration_contracts.py:30` preserves the S2 contract as `playwright_xhr` with note `XHR-first NP_ajax capture with DOM fallback`.

## URL Construction

Legacy URL builder:

- template: `https://www.zawodtyper.pl/typy-dnia-{day}-{month}-{weekday}/`
- months: `stycznia`, `lutego`, `marca`, `kwietnia`, `maja`, `czerwca`, `lipca`, `sierpnia`, `wrzesnia`, `pazdziernika`, `listopada`, `grudnia`
- weekdays: `poniedzialek`, `wtorek`, `sroda`, `czwartek`, `piatek`, `sobota`, `niedziela`

The same Polish slug logic exists twice:

- `scripts/tipster_aggregator.py:143-152,195-200`
- `src/bet/api_clients/tipster_playwright.py:950-957`

This duplication is functional today but is drift risk for future maintenance.

## What Legacy ZawodTyper Actually Does

### 1. Primary path: XHR interception

`TipsterPlaywrightClient.fetch_site()` special-cases ZawodTyper and first calls `_fetch_zawodtyper_via_xhr()`.

That path:

- opens the public daily page,
- listens for Playwright `response` events,
- filters to `NP_ajax.php` POST responses,
- parses JSON with `extract_zawodtyper_bets_payload()`,
- converts structured rows with `parse_zawodtyper_xhr_bets()`.

The payload parser explicitly expects:

- `success=true`
- `data` as a list
- row keys including `comment_id` and `match_name`

The structured bet parser keeps only `comment_type == "bet"` and deduplicates per event.

### 2. Fallback path: structural HTML parser

If XHR capture is empty or Playwright fails, legacy falls back to HTML parsing.

The fallback parser looks for:

- `id="match-name{ID}"`
- `id="type{ID}"`
- nested `.searched-in` blocks

Then it extracts match names, pick text, local block text for odds/accuracy, and limited analysis markers such as `argument`, `uzasadnienie`, `opis`, `komentarz`.

### 3. Last fallback: text block heuristics

If structural HTML yields fewer than 3 picks, the parser scans split text blocks anchored on markers like:

- `Typ dnia`
- `Typer:`
- `Mecz:`
- `Mój typ`

This is a weaker heuristic path and has higher false-positive risk than the XHR parser.

## Fields ZawodTyper Can Really Supply

From `parse_zawodtyper_xhr_bets()` the strongest evidence-backed field set is:

- `source_site`
- `tipster_name` from `author_name`
- `sport` from `discipline` via `DISCIPLINE_MAP`
- `event`, `home_team`, `away_team` from `match_name`
- `market` from `type`
- `market_type` via classifier
- `direction` via classifier
- `odds` from `rate`
- `reasoning` from cleaned `content`, optionally prefixed with author accuracy context
- `accuracy_pct` from `author_stats.ratio` when `bet_count >= 3`
- `stats_cited` from cleaned content
- `fetch_time`
- confidence label derived from `accuracy_pct` and `bet_count`

The HTML fallback can also extract:

- event and teams
- pick text
- approximate odds
- approximate accuracy from visible `%`
- limited reasoning when visible labels exist

## Required Answers

### 1. Czy ZawodTyper działał w legacy?

Yes, the repo still preserves a specific working path for ZawodTyper, and it is the most specialized legacy source in S2:

- canonical contract entry exists,
- S2 core integration contract explicitly names it,
- legacy Playwright client has ZawodTyper-only XHR interception,
- parser tests exist for `NP_ajax.php` fixtures,
- `accuracy_tracked=True` is wired from canonical source definitions.

This is strong evidence that ZawodTyper previously worked and was treated as important, not incidental.

### 2. Jakie pola realnie może dostarczać?

Strongest realistic fields from the XHR payload:

- source identifier
- tipster name
- sport
- event/home/away
- market text
- market type/direction
- reference odds
- reasoning text
- tracked accuracy percent when enough history is shown
- cited stats snippets
- fetch timestamp
- warnings/confidence metadata derived by parser

### 3. Czy daje analizy/reasoning, kurs, typ, wydarzenie, sport, skuteczność/accuracy?

Yes, with different confidence by field:

- reasoning/analysis: yes, from `content`, strongest on XHR path
- odds/kurs: yes, from `rate` on XHR or textual/block extraction in HTML fallback
- typ/market: yes, from `type`
- wydarzenie/event: yes, from `match_name`
- sport: yes, from `discipline`
- skuteczność/accuracy: yes, from `author_stats.ratio` when enough sample size is present

### 4. Czy current v2 go pomija?

Yes.

`src/bet/tipsters/source_registry.py` currently has no `zawodtyper` entry at all. Because `s2_tipsters_v2.py` iterates only `CORE_SOURCE_IDS` plus optional `RESEARCH_SOURCE_IDS`, ZawodTyper is absent from v2 fixture runs and from live-dry-run source choices.

This is the exact gap that made Pass A too narrow.

### 5. Jak bezpiecznie zbridge’ować legacy ZawodTyper do v2?

Safe minimal bridge design:

- do not reimplement live scraping in v2,
- keep legacy fetch/parsing logic as-is,
- convert legacy pick dictionaries into `bet.tipsters.contracts.TipsterPick`,
- mark every bridge output as `source_claim` / `evidence_only_not_a_bet`,
- preserve `accuracy_pct` only as source-quality metadata or warning context,
- preserve odds only as reference-only source evidence,
- reject or drop `stake`, `coupon`, `final bet`, `EV`, `Superbet combined odds` if present.

This allows ZawodTyper to exist in v2 artifacts without promoting its live transport into compliant v2 ingestion.

### 6. Ryzyka

#### robots/terms

Unknown until probe artifacts are generated. Even if robots allow the public page, terms/manual review still remain required.

#### XHR/private endpoint

Medium-to-high compliance risk.

The legacy path relies on intercepting `NP_ajax.php` POST responses. Even though traffic originates from a public page load, this still needs explicit review because it is not plain static HTML and could be considered a site-internal endpoint surface.

#### JS/Playwright

High policy risk for this pass.

Current Playwright base client uses:

- stealth user-agent/browser args,
- `playwright_stealth`,
- Cloudflare challenge handling with wait/retry.

That directly conflicts with Pass B rules for any live run.

#### affiliate/noise

Lower than some English sources, but still non-zero. The HTML fallback includes many garbage filters because public pages contain non-pick UI/noise.

#### false-positive parser

Moderate on HTML fallback, lower on XHR path.

- XHR path is structured and deduplicated by event.
- HTML fallback has structural selectors and then weaker heuristic text parsing if structural extraction is sparse.

#### rate limit

No explicit ZawodTyper-specific rate limiter exists in legacy S2. The XHR path waits 6s and may scroll for lazy loading, but does not enforce compliance-first per-domain pacing.

### 7. Jakie testy trzeba dodać?

Minimum required for Pass B bridge work:

- bridge conversion of a ZawodTyper legacy pick into v2 `TipsterPick`
- preservation of Polish diacritics in event/team names
- preservation of `accuracy_pct` as source metadata, not betting confidence
- preservation of odds as reference-only evidence
- rejection or warning-drop of `stake`, `coupon`, `EV`, `final bet`, `Superbet combined odds`
- weak/missing reasoning should reduce extraction quality and add warnings
- `decision_boundary=evidence_only_not_a_bet` in bridge-compatible output

## Bottom Line

ZawodTyper is not a speculative legacy leftover. It is a first-class canonical S2 source with dedicated transport, dedicated payload parser, explicit accuracy tracking, and existing tests. Current v2 omits it entirely, so Pass B should retain legacy behavior and add a non-promoting bridge rather than replacing or deleting the source.
