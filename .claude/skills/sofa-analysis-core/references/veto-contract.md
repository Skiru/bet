# `vetoes.json` and `reads.json` - schemas, matching, and how they go wrong

Both files live in `runs/sofa/<d>/` and are written only by
`scripts/sofa/merge_reads.py` from your report's ` ```json vetoes ` and
` ```json reads ` blocks. You never write them. Validate your blocks with
`merge_reads.py --dry-run` (SKILL.md, "Output contract").

## `Veto` (`src/bet/sofa/contracts.py`, strict, `extra="forbid"`)

| field | type | required | meaning |
|---|---|---|---|
| `sofascore_event_id` | int | yes | the match - an integer, not a string |
| `market` | str \| null | yes (may be null) | null = every market of the match |
| `subject` | str \| null | yes | null = every subject; `""` is the match-level subject, **not** the same as null |
| `line` | float \| null | yes | null = every line |
| `direction` | `"OVER"` \| `"UNDER"` \| null | yes | null = both. No other side and no period - a measured-sport leg takes a read, not a veto |
| `reason_class` | enum | yes | `SAMPLE_UNINFORMATIVE \| CONTEXT \| PRICE \| OTHER` |
| `reason` | str | yes | Polish; the operator reads it |
| `context` | enum \| null | no (default null) | only with `reason_class: "CONTEXT"`, and then always set: `MOTIVATION \| ROTATION \| ABSENCES \| DERBY \| SCHEDULE \| CONDITIONS`; on any other class it fails validation |

All seven required keys must be present, the null ones included. An invented
key (`action`, `player`, `event_id`) fails the whole file; `merge_reads.py`
refuses it (exit 2) so the stages never see it.

Readers: `run_coupon.py` (old VALUE selector, `VETOED`), `run_confidence.py`
(`08_confidence.json`, refusal `VETOED`), `build_coupon.py` (COUPON_ASSEMBLY,
which also applies a veto to a measured-sport leg on `family` = market and
`side` = direction, every period - `coupon_sports.apply_reads`), and SHEET,
which prices a `SAMPLE_UNINFORMATIVE` rung without its sample. Every class
removes the row outright; a veto has no softer form.

### Matching - the most general entry wins

A veto matches a row when every non-null field matches. A sample that does
not describe the match is broken at every rung, so the normal shape is
`market` / `subject` / `line` / `direction` all null, or the market with the
rest null. Narrow only for a genuinely rung-specific fault (a line on the
sample's mode). There is no override: a narrow entry never carves an
exception out of a broad one.

### The widening trap

There is no player field. A per-player concern keyed
`(event, market, line, direction)` with `subject: null` hits every subject of
the match (in the retired pipeline one such veto removed twenty players).
`subject` is the side or player exactly as the sheet wrote it. Count before
you emit:

```bash
jq -c '.[] | select(.sofascore_event_id==<id> and .market=="<market>") | [.subject,.line,.direction]' runs/sofa/<d>/05_sheet.json | sort | uniq -c
```

If the set is wider than you meant, key a narrower read (one WATCH per rung)
instead, or write it in prose and say it was not applied. The same count
applies to a read with a null field.

### `reason_class`

| class | use when | example |
|---|---|---|
| `SAMPLE_UNINFORMATIVE` | the observations do not measure this match: wrong squad, surface, format, class of opponent, a placeholder 0-0 | "dziewięć z dziesięciu meczów w drugiej lidze; dziś puchar z drużyną z ekstraklasy" |
| `CONTEXT` | the sample is fine and the world has changed | "4-0 w pierwszym meczu; obaj trenerzy wystawiają rezerwy" |
| `PRICE` | the rung is unbettable as quoted (a side missing on the screen) | "OVER nie jest notowany na ekranie" |
| `OTHER` | none of the above - say why | |

### `context` - which kind of CONTEXT

Set it on every CONTEXT veto; the settlement audit grades each tag apart
(audit_settlement 7e, `audit_vetoes.py`).

| `context` | use when | example |
|---|---|---|
| `MOTIVATION` | what the result is worth: dead rubber, must-win, decided tie, points to defend | "dwumecz rozstrzygnięty 4-0" |
| `ROTATION` | rested or reserve XI | "trener zapowiedział rotację przed Ligą Mistrzów" |
| `ABSENCES` | named starters out | "obaj podstawowi stoperzy zawieszeni" |
| `DERBY` | rivalry where the sample's normal matches do not describe tonight | "derby miasta; ostatnie trzy: 7, 8, 9 kartek" |
| `SCHEDULE` | fatigue, travel, back-to-back, a long previous match, a postponement | "wczoraj 3h40 w pięciu setach" |
| `CONDITIONS` | weather, pitch, altitude, indoor / outdoor | "ulewa, podtopione boisko" |

A CONTEXT `reason` names the source domain and its publication time, before
the decision point: `"[sportsmole.co.uk, publ. 2026-09-22 09:14 UTC] ..."`. A
veto written after its match started is excluded from the grade.

### What a veto may never be

- a promotion (nothing in `sofa` raises a row - say it in prose);
- an opinion on a market nobody priced (not a bet);
- a hedge - a caveat goes in the report, a veto removes the row;
- a duplicate of a gate the code applies (`references/evidence-rules.md`, "already
  enforced"). A football player leg carrying `player_sample_rule` is the
  exception: the code lifted that shape gate
  (`epochs.PLAYER_SAMPLE_GATES_FROM_UTC`), so the sample's shape is yours.

## `LegRead` (`src/bet/sofa/contracts.py`, strict, `extra="forbid"`)

| field | type | meaning |
|---|---|---|
| `sofascore_event_id` | int | the match |
| `market` | str \| null | as in `Veto`; a measured-sport leg's `family` (`total`, `team_total`, `handicap`, `winner`, ...) |
| `subject`, `line` | as in `Veto` | null covers every value. A sport leg's `subject` is `""`, `T1` / `T2`, a CS2 team or a player; `""` does not cover `T1`. A handicap's `line` is team 1's as stored - copy the read-set field, not the PDF |
| `direction` | str \| null | `OVER` / `UNDER` or a sport side from `contracts.READ_SIDES` (`T1`, `T2`, `DRAW`, `ODD`, `EVEN`, `YES`, `NO`, `1X`, `X2`, `12`) or an exact score `"3:1"`; anything else fails |
| `period` | int \| null, optional | hockey period, quarter, set, CS2 map; `0` the whole match (and basketball halves); null covers every period |
| `verdict` | `KEEP \| WATCH \| NO_BET` | |
| `author` | `analyst \| verifier` | you are `"analyst"` |
| `reason` | non-empty str | Polish; rides on the leg as `reads` |
| `context` | a `context` tag above, optional | leave it out when none fits |

Eight keys are required (`sofascore_event_id`, `market`, `subject`, `line`,
`direction`, `verdict`, `author`, `reason`); `period` and `context` may be
left out.

Effect (`veto.read_refusal`; `coupon_sports.apply_reads` for a sport leg):
KEEP removes nothing; WATCH removes with refusal `WATCHED`, NO_BET with
`READ_NO_BET`, into `removed_by_reads` of `11_coupon.json`, graded apart
(audit_settlement 7i, ledger `removed:reads`), never in the coupon's result.
`reads.json` is append-only: a later KEEP never undoes an earlier WATCH.
`run_confidence.py` sees only football / tennis rows: it counts a sport read
as `reads_sport` (never `UNMATCHED_READ`), and the read acts in
COUPON_ASSEMBLY - confirm it in `11_coupon.json` (`removed_by_reads`, or the
leg's `reads`). A football / tennis read matching no sheet row prints
`UNMATCHED_READ` and did nothing.

A read is a verdict on a leg, a veto a verdict on a sample. Do not file one
fault twice. A measured-sport leg always takes a read.

## Examples

Veto, the normal broad shape:

```json
[{"sofascore_event_id": 15275920, "market": "corners_total", "subject": null,
  "line": null, "direction": null, "reason_class": "SAMPLE_UNINFORMATIVE",
  "reason": "siedem z dziesięciu obserwacji sprzed zmiany trenera 12.08; trzy od tego czasu: 4, 5, 6"}]
```

Football / tennis read:

```json
[{"sofascore_event_id": 17009055, "market": "goals_total", "subject": "",
  "line": 3.5, "direction": "UNDER", "verdict": "WATCH", "author": "analyst",
  "reason": "Chaves w ostatnich czterech: 4/5/4/5 goli; mecz zaległy 5. kolejki (przełożony 6.09, choroba w kadrze)"}]
```

Measured-sport read (`period` 0 = whole match):

```json
[{"sofascore_event_id": 16310568, "market": "total", "subject": "",
  "line": 3.5, "direction": "OVER", "period": 0, "verdict": "NO_BET",
  "author": "analyst", "context": "SCHEDULE",
  "reason": "mecz przełożony [WEB: hltv.org, liquipedia.net, fetched 2026-10-06 09:10Z]"}]
```
