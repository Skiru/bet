# Skill: Reading HTML Snapshots for Deep Data Extraction

## Purpose

This skill teaches agents HOW to read and extract rich statistical data from saved Playwright HTML snapshots stored in `betting/data/{domain}/`. The adapters in `scripts/adapters/` perform initial parsing during scan, but only extract basic fixture data (home, away, time). The HTML contains much richer data that goes unextracted.

**When to use:** During S1-ingest, S2.5 enrichment, or when self-healing data gaps. When a candidate has missing stats, check if HTML snapshots from its source domain contain the needed data.

## Architecture

```
Playwright fetch → HTML saved to betting/data/{domain}/*.html
                     ↓
Adapter parse (shallow): {home, away, time, league}
                     ↓
html_deep_parser.py (deep): match IDs, odds, stats, form, predictions
                     ↓
DB enrichment: scan_results.raw_data + team_form
```

**Script:** `python3 scripts/html_deep_parser.py --date YYYY-MM-DD [--domains dom1,dom2] [--dry-run] [--report]`

**Profiles configured:** flashscore.com, totalcorner.com, soccerstats.com, forebet.com, betexplorer.com, covers.com, basketball-reference.com, hockey-reference.com, betclic.pl, tennisexplorer.com

## Per-Domain Extraction Guide

### flashscore.com (ALL sports)

**Snapshot location:** `betting/data/flashscore.com/*.html`
**Volume:** 3,000+ snapshots, ~1-2 MB each

**Key CSS patterns:**
| CSS Class/ID | Data | Currently Extracted | Deep Parse Extracts |
|---|---|---|---|
| `id="g_1_XXXXXXXX"` | Match ID | NO | YES — enables Flashscore API for H2H/lineups |
| `event__match` | Match container | YES | — |
| `event__homeParticipant` | Home team | YES | — |
| `event__awayParticipant` | Away team | YES | — |
| `event__time` | Kickoff time | YES | — |
| `event__score--home/away` | Score | PARTIALLY | YES — FT + part scores |
| `event__part` | Set/period scores | NO | YES |
| `headerLeague__title-text` | League name | PARTIALLY | YES — full hierarchy |
| `headerLeague__category-text` | Country | NO | YES |

**Agent action:** When a candidate is missing H2H data, extract its `flashscore_match_id` (format: `g_1_XXXXX`) from the saved HTML. This ID can be used to construct Flashscore API URLs for deep stats.

### totalcorner.com (Football only)

**Snapshot location:** `betting/data/totalcorner.com/*.html`
**Critical for:** Corner, card, and dangerous attack stats

**Key CSS patterns:**
| CSS Class | Data | Currently Extracted | Deep Parse Extracts |
|---|---|---|---|
| `td.match_home` | Home team | YES | — |
| `td.match_away` | Away team | YES | — |
| `td.match_handicap` | Corner handicap line | YES | — |
| Corner count cell | FT corners "5-3(4-2)" | PARTIAL (FT only) | YES — HT corners too |
| Yellow/red spans in team cells | Card counts | NO | YES |
| `[N]` in team name | League position | NO | YES |
| DA cells | Dangerous attacks | NO | YES |

**Extraction pattern for HT corners:**
```
Text: "5 - 3(4-2)"
  FT: home=5, away=3
  HT: home=4, away=2
Regex: (\d+)\s*-\s*(\d+)\s*\((\d+)\s*-\s*(\d+)\)
```

### soccerstats.com (Football only)

**Snapshot location:** `betting/data/soccerstats.com/*.html`
**Critical for:** Season averages (corners/game, cards/game, fouls/game)

**Extraction strategies:**
1. **Title-attribute cells:** `<td title="Corners per game">5.2</td>` — find cells with stat-related titles
2. **Stat tables with headers:** Tables whose `<th>` headers contain "Corner", "Card", "Foul", "Goal", "Shot"
3. **Home/Away splits:** Usually in format `home_avg / away_avg / total_avg`

**Agent action:** When analyzing football stats, check if SoccerStats HTML contains season averages for the teams. Cross-reference with L10 form data for consistency.

### forebet.com (ALL sports)

**Snapshot location:** `betting/data/forebet.com/*.html`
**Critical for:** Match predictions, probabilities, avg stats

**Key CSS patterns:**
| CSS Class | Data | Currently Extracted | Deep Parse Extracts |
|---|---|---|---|
| `a.tnmscn` | Match link with teams | YES | — |
| `span.homeTeam` / `span.awayTeam` | Team names | YES | — |
| `div.fprc` | Probabilities (1X2 or H/A) | PARTIALLY | YES — all values |
| `div.avg_sc` | Avg goals/games/sets | PARTIALLY | YES — always captured |
| `div.ex_sc` | Predicted score | PARTIALLY | YES |
| `div.predict` | Predicted winner | YES | — |
| BTTS/OU divs | BTTS and Over/Under predictions | NO | YES |

### betexplorer.com (ALL sports)

**Snapshot location:** `betting/data/betexplorer.com/*.html`
**Note:** React SPA — HTML is often empty/incomplete because odds render via JavaScript.

**Key patterns:**
- `data-odd` attribute on `<td>` elements contains odds values
- `data-*` attributes on `<tr>` match rows contain match metadata
- When JS renders, odds appear in table cells matching pattern `^\d+\.\d+$`

**Agent action:** If BetExplorer HTML is empty (React didn't render), this source is unreliable for HTML parsing. Flag for API-based fallback.

### betclic.pl (ALL sports)

**Snapshot location:** `betting/data/betclic.pl/*.html`
**Critical for:** Full market odds (the adapter only extracts H2H odds)

**Key patterns:**
- `data-qa` attributes indicate market types: `data-qa="odd-home"`, `data-qa="odd-draw"`, etc.
- Market category divs contain lists of available betting markets per event
- Match detail URLs in `<a href="/event/...">` links

**Agent action:** When a candidate needs Betclic odds for non-H2H markets (handicaps, totals, BTTS), check the saved HTML for `data-qa` elements containing odds values.

### basketball-reference.com / hockey-reference.com

**Snapshot location:** `betting/data/{domain}/*.html`
**Critical for:** Deep US sports season stats

**Key pattern:** All data cells use `data-stat="stat_name"` attributes.
```html
<td data-stat="pts_per_g">112.3</td>
<td data-stat="fg_pct">.472</td>
<td data-stat="trb_per_g">44.1</td>
```

**Common stat keys:**
- Basketball: `pts_per_g`, `fg_pct`, `trb_per_g`, `ast_per_g`, `stl_per_g`, `blk_per_g`, `tov_per_g`
- Hockey: `goals`, `assists`, `pts`, `goals_against`, `save_pct`, `shutouts`

### tennisexplorer.com (Tennis)

**Snapshot location:** `betting/data/tennisexplorer.com/*.html`
**Critical for:** Surface, tournament round, player rankings/seeds

**Key patterns:**
- Player links: `<a href="/player/...">Player Name</a>`
- Surface info: Often in URL path or page header
- Seeds: `[1]`, `[Q]` markers near player names
- Round info: elements with `round` class

### covers.com (US sports)

**Snapshot location:** `betting/data/covers.com/*.html`
**Key patterns:**
- Card-based layout: classes containing `game-card`, `matchup`, `event-card`
- Spread/ML/Total: classes containing `spread`, `moneyline`, `total`, `over-under`
- Team records: classes containing `record`, `standing`, `rank`

## How Agents Should Use This Knowledge

### During S1-ingest (bet-scanner agents)
1. After scan completes, check extraction yield per domain
2. If a domain returned many events but few stats → run `html_deep_parser.py` for that domain
3. Compare deep-parsed data with adapter output — flag new data fields found

### During S2.5 enrichment (bet-enricher agent)
1. Before calling external APIs, check if saved HTML already contains the needed data
2. Run deep parser for domains where candidates have data gaps
3. Cross-reference deep-parsed stats with API-sourced stats for validation

### During S3 deep stats (bet-statistician agent)
1. When a candidate is missing corner/card/foul averages, check TotalCorner and SoccerStats HTML
2. When a tennis match needs surface info, check TennisExplorer HTML
3. Use flashscore_match_id for programmatic H2H lookups

### For self-healing (any scanner agent in healing mode)
1. If a source failed during scan but HTML was partially saved → deep-parse what exists
2. If adapter returned 0 events but HTML is non-empty → HTML structure may have changed → agent analyzes HTML to identify new patterns
3. Report new CSS class patterns to inform adapter updates

## Validation Checklist

## Agent Validation Protocol

After `html_deep_parser.py` runs, it produces:
1. **Report JSON**: `betting/data/{YYYYMMDD}_deep_parse_report.json` — per-domain results with validation and verdicts
2. **Agent review input**: `betting/data/agent_reviews/{date}/s1_html_deep_input.json` — structured task with action items

### Per-Domain Verdicts

Each domain gets a verdict:
- **PASS**: Extractions within plausible ranges, DB match rate >60%
- **WARN**: 0 extractions from existing snapshots, or 5-20% values out of range, or match rate 30-60%
- **FAIL**: >20% values out of range, or match rate <30% from >10 enrichments

### Agent Review Workflow

1. Read `s1_html_deep_input.json` — check `action_items` for WARN/FAIL domains
2. For each WARN/FAIL domain:
   - Open an HTML snapshot: `betting/data/{domain}/*.html`
   - Search for the CSS classes listed in the extraction profile (see tables above)
   - If classes EXIST but extraction is 0 → parsing logic bug (regex or iteration issue)
   - If classes DON'T EXIST → HTML structure changed, profile needs updating
3. For PASS domains, spot-check 2-3 enrichments:
   - Pick a random enrichment from the `sample` list in the report
   - Find that match in the HTML snapshot and verify values match
4. Write review to `betting/data/agent_reviews/{date}/s1_html_deep_review.json`:
```json
{
  "agent": "bet-scanner",
  "step_id": "s1_html_deep",
  "status": "approved | flagged | needs_fix",
  "domains_reviewed": {"flashscore.com": "PASS", "covers.com": "needs_fix"},
  "broken_profiles": ["covers.com — CSS class game-card no longer exists, use .event-card"],
  "false_positives": ["corners_ft_home=18 for Dortmund vs Bayern is actually correct"],
  "timestamp": "2026-05-08T14:30:00+02:00"
}
```

### Validation Checklist

Before accepting deep-parsed data:
- [ ] Team names match existing scan_results (fuzzy match OK for variations)
- [ ] Numeric values are within plausible ranges (e.g., corners 0-20, odds 1.01-100.0)
- [ ] Stat averages are per-game, not totals (SoccerStats can be ambiguous)
- [ ] Multiple snapshots from same domain don't double-count the same data
- [ ] Enrichments are timestamped with `parsed_at` for freshness tracking
- [ ] DB match rate >60% for production domains (flashscore, totalcorner, forebet)
- [ ] No FAIL verdicts in the report (or all FAILs have been investigated and resolved)

## Adding New Profiles

To add extraction for a new domain:
1. Create a new `ExtractionProfile` subclass in `scripts/html_deep_parser.py`
2. Set `domain` and optionally `sport_filter`
3. Implement `extract(html, url, soup) -> list[dict]`
4. Register in `PROFILES` dict
5. Document CSS patterns in this skill file
6. Test with: `python3 scripts/html_deep_parser.py --date YYYY-MM-DD --domains new_domain.com --dry-run --report`

<!-- SKILL:bet-reading-html:v1 -->
