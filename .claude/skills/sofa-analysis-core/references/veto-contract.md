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
| `context` | enum \| null | no (default null) | only with `reason_class: "CONTEXT"`, and then always set: `MOTIVATION \| ROTATION \| ABSENCES \| DERBY \| SCHEDULE \| CONDITIONS \| MORALE`; on any other class it fails validation (`MARKET` exists for reads only) |

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
| `SAMPLE_UNINFORMATIVE` | the observations do not measure this match: wrong squad, surface, format, a placeholder 0-0 (a `DEFEKT:` - core, "What a removal's reason must name") | "DEFEKT: 03_samples corners_for Lech Poznań - próbka z meczów U19" |
| `CONTEXT` | the sample is fine and the world has changed | "4-0 w pierwszym meczu; obaj trenerzy wystawiają rezerwy [WEB: sportsmole.co.uk, publ. 2026-10-27, fetched 2026-10-28 07:10Z]" |
| `PRICE` | the rung is unbettable as quoted (a side missing on the screen) | "OVER nie jest notowany na ekranie" |
| `OTHER` | none of the above - say why | |

### `context` - which kind of CONTEXT

Set it on every CONTEXT veto; the settlement audit grades each tag apart
(audit_settlement 7e, `audit_vetoes.py`).

| `context` | use when | example |
|---|---|---|
| `MOTIVATION` | what the result is worth: dead rubber, must-win, decided tie, points to defend | "rewanż przy 4-0: trener zapowiedział rezerwowy skład" (through the XI; the stake alone carries ~0) |
| `ROTATION` | rested or reserve XI | "trener zapowiedział rotację przed Ligą Mistrzów" |
| `ABSENCES` | named starters out | "obaj podstawowi stoperzy zawieszeni" |
| `DERBY` | rivalry where the sample's normal matches do not describe tonight | "derby; sędzia zmieniony na X (ogłoszone dziś)" (a changed input; derby alone carries ~0) |
| `SCHEDULE` | fatigue, travel, back-to-back, a long previous match, a postponement | "wczoraj 3h40 w pięciu setach" |
| `CONDITIONS` | weather, pitch, altitude, indoor / outdoor | "ulewa, podtopione boisko" |
| `MORALE` | dressing room, conflict, unpaid wages, a sacked coach, a boycott, fan protest | "piłkarze od trzech miesięcy bez pensji, zapowiedź bojkotu treningów" |

**A veto is sourced** (core, "What a removal's reason must name"): its
`reason` carries a real `DEFEKT: <artifact, field, what is wrong>` or a
dated tag (a CONTEXT veto always the tag, `[WEB: sportsmole.co.uk, publ.
2026-10-27, fetched 2026-10-28 07:10Z]`) - never `RYNEK:`, which is a
leg-level WATCH read only. `report_check` flags anything else (`WETO BEZ
FAKTU`). A leg under your veto takes no read. A veto written after its
match started is excluded from the grade.

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
| `reason` | non-empty str | Polish; rides on the leg as `reads`; a WATCH / NO_BET reason carries one of the marks of core "What a removal's reason must name" (`report_check`) |
| `context` | a `context` tag above, or `MARKET` (a football `RYNEK:` WATCH - required there), optional | exactly one of `MOTIVATION`, `ROTATION`, `ABSENCES`, `DERBY`, `SCHEDULE`, `CONDITIONS`, `MORALE`, `MARKET`, or null / left out when none fits - anything else (`"OTHER"`, `"NONE"`) fails validation and merge_reads refuses the report (E2E 10-29) |

A WATCH / NO_BET copies `market` / `subject` / `line` / `direction` /
`period` from the read-set leg, never retyped from the PDF.

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
  "reason": "DEFEKT: 03_samples corners_total side_a - trzy z dziesięciu obserwacji to walkowery 0-0 bez statystyk (placeholder), nie mecze"}]
```

Football / tennis read:

```json
[{"sofascore_event_id": 17009055, "market": "goals_total", "subject": "",
  "line": 3.5, "direction": "UNDER", "verdict": "WATCH", "author": "analyst",
  "context": "ABSENCES", "reason": "obaj podstawowi stoperzy Chaves zawieszeni (komunikat ligi) [WEB: ligaportugal.pt, publ. 2026-10-05 14:00Z, fetched 2026-10-06 08:40Z]; Chaves w ostatnich czterech 4/5/4/5 goli - nota, nie powód"}]
```

Football market-driver WATCH (reports from 2026-10-30; pewność 0.79, conceded
3/10 = 0.30, gap 0.49 >= 0.25, n 10 >= 8 - core threshold (a)):

```json
[{"sofascore_event_id": 15275921, "market": "corners_for", "subject": "Panathinaikos",
  "line": 3.5, "direction": "OVER", "verdict": "WATCH", "author": "analyst",
  "context": "MARKET", "reason": "RYNEK: Aris oddaje rywalom ≥4 rożne w 3/10 (style.matchup), pewność 0.79. Mechanizm: rywale Arisu dośrodkowują średnio 11 razy na mecz (style.away.means crosses przeciw), mniej niż liga - linia 3.5 wymaga rywala, który rożne oddaje"}]
```

Measured-sport read (`period` 0 = whole match):

```json
[{"sofascore_event_id": 16310568, "market": "total", "subject": "",
  "line": 3.5, "direction": "OVER", "period": 0, "verdict": "NO_BET",
  "author": "analyst", "context": "SCHEDULE",
  "reason": "mecz przełożony [WEB: dust2.us, pgl.ro, publ. 2026-10-06 08:30Z, fetched 2026-10-06 09:10Z]"}]
```
