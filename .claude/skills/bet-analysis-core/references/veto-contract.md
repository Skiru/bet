# The veto contract — `AnalystVeto` as `build_coupons.py --vetoes` consumes it

Source: `src/bet/simple_stats/bet_builder_draft.py` (`AnalystVeto`, `VetoIndex`)
and `src/bet/simple_stats/coupons.py` (`VETO_CLASS_ZERO_WEIGHT`,
`VETO_CLASS_DOUBLE_K`, `_veto_class_effect`). Pydantic `StrictBaseModel`:
**any extra key fails the whole file** (`extra_forbidden`).

## Schema

```json
{
  "event_id":     "<EventRecord.event_id, the full 64-char hash>",
  "market":       "<canonical market, e.g. cards_points_total, fouls_for, games_won>",
  "line":         7.5 | null,
  "direction":    "OVER" | "UNDER" | null,
  "action":       "VETO" | "DOWNGRADE",
  "reason_class": "SAMPLE_NOT_REPRESENTATIVE" | "LINE_ON_MODE" | "MISSING_REFEREE"
                | "ESTIMAND_WRONG" | "DATA_CONFLICT" | "OTHER",
  "reason":       "<one paragraph, Polish or English, the argument in FACT → CALC → IMPLICATION form>"
}
```

`reason_class` defaults to `OTHER` when omitted — always set it explicitly.

## Semantics

| action / class | Effect in the coupon |
|---|---|
| `VETO` | row removed (`excluded.analyst_veto`), reason echoed in the header |
| `DOWNGRADE` + `OTHER` / `LINE_ON_MODE` / `DATA_CONFLICT` | tier steps down once: `CALL→LEAN` (bar ×1.10/1.05), `LEAN→WEAK` (out of the coupon) |
| `DOWNGRADE` + `SAMPLE_NOT_REPRESENTATIVE` / `ESTIMAND_WRONG` | sample weight → **0**: row priced off Superbet's own devigged number plus the tier margin. Stays in the file, annotated, and will almost never beat its bar. Use when the sample is not evidence about this fixture but the row should remain visible |
| `DOWNGRADE` + `MISSING_REFEREE` | `k` doubled: the sample's weight halves toward the book's price |

Nothing ever touches `p_low`. `VETO` applies to singles **and** Bet Builder
legs (one `VetoIndex` shared by both paths since 2026-09-01).

## Scope: `line` and `direction`

Resolution order per row: `(line, direction)` → `(null, direction)` →
`(line, null)` → `(null, null)`. First hit wins.

- **`line: null` is the default shape.** A fault in the sample (one side
  thin, h2h dominating the misses, wrong estimand, DISAGREE, no referee,
  opponent class) is a fault at every rung. Writing a specific line lets the
  cheaper rungs survive on the same broken sample — this shipped on
  2026-09-01 (Sheffield United cards 5.5 as a CALL leg after 4.5 and 3.5 were
  vetoed) and on 2026-09-03 (América cards 7.5 after 6.5 was downgraded).
- **A specific `line` is for a per-rung fault only**, and `LINE_ON_MODE` is
  the canonical one: "5 of 20 observations are exactly 7" is about 7.5, not
  about 8.5. `LINE_ON_MODE` with `line: null` is **ignored** with a note.
- `direction: null` when the fault is direction-agnostic (fixture postponed,
  referee missing, sample not representative). Keep `direction` when the
  argument is one-sided (an OVER built on a right tail).
- A market-wide DOWNGRADE plus a per-rung VETO on the same market is legal and
  resolves as intended.

## Player props: what cannot be expressed

There is no `player_name` / `team_name` key. A prop veto for one player
resolves by `(event_id, market, line, direction)` and therefore hits **every
player** on that fixture with that market/line/direction — on 2026-09-04 that
was 20 rows, including two the same analyst had graded VALUE.

Procedure:

```bash
python3 -c "
import json,sys
rows=json.load(open('runs/<date>/<date>_event_dossiers_stats_sheet.json'))['rows']   # the FULL sheet, not _top — a line: null veto can hit a row below 0.50 that never reached top
k=('<event_id>','player_total_shots',1.5,'OVER')
hit=[r for r in rows if (r['event_id'],r['market'],r['line'],r['direction'])==k]
print(len(hit), sorted({r['player_name'] for r in hit}))"
```

Always count against the **full** sheet (`_event_dossiers_stats_sheet.json`),
not `_top`. A `line: null` entry resolves against every row of that market on
the fixture, including ones below the 0.50 floor that never reached the top
file — undercounting there means the widened veto silently touches rows you
never saw.

If the count is larger than the players you mean, **do not emit the entry**.
Write the objection in the analysis as `WATCH (nie zastosowano — weto nie
potrafi nazwać zawodnika)` so the operator sees it. The same applies to a
`*_for` row when only one of the two sides is at fault and both sides' rows
share market/line/direction — count first; if both sides are legitimately
covered by the reason (as with the Grenal fouls), say so in the reason.

## Worked entries

```json
[
  {"event_id": "3a01…d45a", "market": "fouls_total", "line": null, "direction": "UNDER",
   "action": "DOWNGRADE", "reason_class": "SAMPLE_NOT_REPRESENTATIVE",
   "reason": "FACT: both misses in n=21 are the two previous Grenals (43, 39 fouls); third gave 33. CALC: conditional on this fixture the record is 1/3 under 36.5, not 19/21; 43 and 39 are +2.2σ/+1.6σ against the additive centre 27.8. IMPLICATION: the pooled sample is not evidence about a derby second leg. RISK: referee averages 27.5 fouls over 49 matches, which argues the other way — hence DOWNGRADE, not VETO."},

  {"event_id": "3a01…d45a", "market": "cards_points_total", "line": 7.5, "direction": "UNDER",
   "action": "DOWNGRADE", "reason_class": "LINE_ON_MODE",
   "reason": "5/20 observations are exactly 7 and 2 are 8 (sample max 8); two of three previous derbies gave exactly 7. 8.5 and 9.5 UNDER stand (20/20, max below line)."},

  {"event_id": "8c4f…3a89", "market": "cards_points_total", "line": null, "direction": null,
   "action": "DOWNGRADE", "reason_class": "MISSING_REFEREE",
   "reason": "referee_id null at ANALYZE and still null in get_match_detail at 12:40Z; in this league the spread between officials exceeds one card a match and the line sits 1.5 cards above the median."},

  {"event_id": "8c4f…3a89", "market": "cards_points_total", "line": null, "direction": "UNDER",
   "action": "DOWNGRADE", "reason_class": "DATA_CONFLICT",
   "reason": "DISAGREE lies on the line: Ponte Preta 2026-08-14 is 6 by one provider and 8 by the other against a 6.5 rung; the collapse chose 6, giving 20/21; at 8 it is 19/21 and the required price (~1.53) exceeds the offer (1.47)."},

  {"event_id": "c8c7…0d96", "market": "games_won", "line": null, "direction": "OVER",
   "action": "DOWNGRADE", "reason_class": "ESTIMAND_WRONG",
   "reason": "games_won conditions on nothing about the opponent: the 9-match sample [7,12,12,12,12,12,13,15,19] was built against WTA-125/qualifying fields; tonight's opponent is a two-time slam finalist who won R1 6-1 6-3 [WEB: usopen.org, fetched 2026-09-03]. Scenario A (favourite pulls away: 6-3 6-4 = 7 games) is the modal outcome and loses every rung."},

  {"event_id": "…", "market": "total_games", "line": null, "direction": null,
   "action": "VETO", "reason_class": "OTHER",
   "reason": "fixture moved: get_match_detail status=postponed at 11:02Z; artifact start_time 2026-09-03T19:00Z."}
]
```

## What is *not* a veto

- A caveat you would print beside a row you still recommend.
- Disagreement with a price. The bar is not yours to move.
- A tier you would have computed differently. Read `tier_for_row`'s rule;
  if you think it is wrong, that is a code finding for *Czego zabrakło*.
- A tennis `NO_REFERENCE_SOURCE` ceiling or a `predicted` XI cap — already
  applied by code; restating it as a DOWNGRADE double-counts it.
