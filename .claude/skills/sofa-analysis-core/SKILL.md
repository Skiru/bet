---
name: sofa-analysis-core
description: The contract every sofa analyst (football, tennis, measured sports) works under - read exactly the legs of the read_set file the caller names, in a fixed artifact order; evidence vs price; what may remove a leg (never promote); the decision point and the obligatory web context pass; the vetoes / reads blocks and the report-file output contract.
user-invocable: false
---

# The analyst's contract

For each leg you are given, decide whether the evidence behind it describes
**this** match, in a form the machine applies. `sofa-pipeline` (preloaded)
holds the coupon identity, the channels, the read-set definition and the hard
rules - not repeated here. The sport skill
(`football-analysis` / `tennis-analysis`) is the method and wins on how to
weigh evidence; the artifacts win on facts. Model facts (which switches and
curves are on, mixed days): `.claude/skills/sofa-pipeline/references/model-state.md`.

You never run the pipeline, never touch the DB or `config/`, never price a
parlay, never size a stake. Bash is for reading, arithmetic and the one
heredoc that writes your report.

## Input - the read set file

The caller names one file: `runs/sofa/<d>/read_set/read_set_<sport>[_<i>].json`
(written by `scripts/sofa/read_set.py`). It is a JSON array of compact legs:

| field | meaning |
|---|---|
| `sofascore_event_id`, `group_key` (`sofa:<id>`), `match`, `competition`, `kickoff_utc` | the match |
| `market`, `subject`, `line`, `direction`, `period` | the leg's key - copy these into your read exactly (a sport leg: `market` = family, `direction` = side, `period` = period / quarter / set / map; a handicap `line` is team 1's, `T1` / `T2` the side) |
| `superbet_market`, `superbet_selection` | Superbet's words - name the leg with them |
| `confidence`, `offered_odds`, `price_gap` | pewność, the price, the over-price flag |
| `position`, `locked` | coupon position (a builder leg has none); `locked` = printed before its start, stays whatever you say |
| `in_set` | `required` (C3 needs your read) or `buffer` (the next matches; read them the same way); a chat slip's file (`read_set_slip_<sport>.json`, the `/kupon` loop) holds `slip` (on the slip) or `slip_reserve` (its replacements) - read them the same way |
| `model_p`, `forecast_p`, `calibrated_on`, `sample_size`, `sample_hit_rate`, `sample_oldest_days`, `sample_newest_days`, `context_flags`, `superbet_event_id`, `source_date` | the leg's numbers - use them before any lookup (a field is absent when null) |
| `dossier` | the match's fact sheet path (below, first artifact) |
| `prior_analysis` | the match was analysed earlier today (`report`, `recorded_at_utc`, `web_tags`, `context_pass`, `full_pass_report`, `full_pass_at_utc`): read that section first and do a **delta pass** (`references/context-pass.md`, "Budget and the delta pass") |

**Read exactly those legs - every one gets a read.** Never recompute the
read set or rebuild the pipeline's gates to guess what would print. If
the file or `11_coupon.json` is missing, stop and say so. A `locked` leg:
read it only if it is in the file, and say your read cannot remove it.

Anything else on the leg (`market_p`, `overround`, `one_sided_market`, ...) is
on the coupon leg, not in the read-set file. Pull one match's legs:

```bash
.venv/bin/python -c "import json,sys; d=json.load(open(sys.argv[1]))
for s in d['singles']+d['removed_by_reads']:
  if str(s['sofascore_event_id'])==sys.argv[2]: print(json.dumps({k:v for k,v in s.items() if k not in ('sample_observations','reads')},ensure_ascii=False))
" runs/sofa/<d>/11_coupon.json <sofascore_event_id>
```

A builder leg sits in `builders[].legs` (market, subject, line, direction,
confidence, odds only); its match is the builder's.

## Artifacts, in this order (all under `runs/sofa/<d>/`)

Shapes (list vs object): `sofa-pipeline` `references/artifacts.md`, "Artifact shapes".

| file | what you take from it |
|---|---|
| `analyses.json` (only for a leg with `prior_analysis`) | the earlier section of the match: the `jq` of `references/context-pass.md` (the section and the full pass it cites) - its dossier and context findings are yours to cite, then only what changed since |
| `dossier/<sport>_<event id>.json` (the leg's `dossier`) | **first, whole, per match**: form, rest, table, h2h, Sofascore's pre-match lineup and absences (`lineups`: predicted is not confirmed; an absent regular is at most a WATCH through the leg's variable, never a promotion), venue and its local hour, referee / ranking / CS2 roster and map pool, Superbet line moves, every leg of the match, the web checklist - blocks and per-sport reading: `references/dossier.md`; no field = "brak dossier" |
| `11_coupon.json` | the leg's full row (above), `removed_by_reads`, `builders`, `peer`, `price_gap` |
| `02_fixtures.json` | names, competition, round, both clocks, `identity`, referee, `ground_type`, `default_period_count`, `previous_leg_event_id` |
| `fixture_status.json` | FIXTURE_CHECK's fresh start and status (`events.<id>`) |
| `03_samples.json` | **the evidence** (football / tennis): per metric `side_a` / `side_b` / `h2h` observations, `players`, `gaps`, `schedule` |
| `05_sheet.json` | the sheet row behind a football / tennis leg: `p_central`, `centre`, notes, rule markers |
| `04_offer.json` | the ladder and each rung's `fetched_at_utc` |
| `sport_fixtures.json`, `runs/sofa/{shadow/<sport>,cs2}/<source_date>/snapshots.jsonl` | measured sports: pinned identity, raw Superbet snapshot |
| `reads.json`, `vetoes.json` (a chat slip also `reads_slip.json`, `vetoes_slip.json`) | what earlier passes said - **not evidence**: form your verdict first, then compare; name a disagreement with an earlier KEEP in the reason (WATCH / NO_BET win over KEEP by design) |

Filter big files to the event id (`jq`, a one-liner) - never `cat`. Show
names, not bare `sofascore_event_id`s.

## Which number is which

| on the leg | what it is | use |
|---|---|---|
| `confidence` (**pewność**) | the history curve applied to the statistics' probability (`model_p` = the sheet's `p_central`), lowered by line evidence (`line_offset`, `price_band_cap`, `cap:` / `sb` in `calibrated_on`); the curve is already calibrated on replayed history (`calibrated_on`, `calibration_n` count replayed rows) | the claim |
| `sample_hit_rate` x `sample_size` (`sample_k` / `sample_n` on a sport leg) (**próbka** k/n) | how often the line held in the leg's own raw sample - a weaker number than the confidence it fed | evidence about the sample, read it |
| `forecast_p` (**model**), `forecast_source` | the rating's uncalibrated number; on several families it **is** `model_p` (sport skill) | shown, never a reason |
| `offered_odds`, x = confidence x odds | the price and the betting condition (x >= 0.90), already applied | never evidence for or against a leg |
| `price_gap` | confidence above 1/odds + 0.03: such legs realised about at their price | annotation, quote at the price |
| `context_flags`, `stakes`, `peer` | schedule flags, table-stakes direction, the surer leg of a match at a similar price | questions you answer, never gates |

Recompute a number only **from the row's own fields** (say so). Never present `p_bar`, `surplus`,
`required_odds` or `odds_if_product` as anything on the coupon.

## Order of operations - never reverse it

0. **Expectation first, in the market's units**, before any price ("expect
   9.8 corners; the ten matches ran 6-15").
1. **Decision point** (below) - drop what has started.
2. **Data integrity** - the observations, not the summary: n, dates,
   opponents, side, `gaps[]`; does `subject` resolve to the side it claims?
3. **Does the market settle what the sample measures** - scope (half / match /
   regulation), side, extra time, the metric's own definition.
4. **Context that changes the estimand** - stakes, second leg, derby,
   referee, absences, surface, format, schedule.
5. **Distribution and scenario** - mode, tail, the line, the settling script.
6. **Kill case, then buy case.** No later step redeems an earlier hard fail.
7. **Verdict** - one read per leg, a veto where the sample is broken.

## What may move a leg

- A read or veto **only removes** - never promotes, raises or admits.
- Never quote the model or the price as a reason to keep or remove.
- Never veto or WATCH for a gate the code already applied
  (`references/evidence-rules.md`, "already enforced"); say "kod już to
  odrzucił" and move on.
- A settled result of another day never enters a read.
- Refunds (moved past the deadline, awarded, retired, walkover, cancelled)
  settle at 0 u.; a withdrawal announced before the start is read material.

## The decision point - before any web tool runs

1. Per match: start in UTC on **both clocks** (`kickoff_utc`,
   `superbet_kickoff_utc`; FIXTURE_CHECK's start where present), `now`, the
   delta. Take the earlier clock. Print them.
2. **A match already started is not researched** - drop it here.
3. **Every match not yet started gets a context pass on the web** (operator
   2026-10-20): news and facts, conditions (weather at the local hour),
   morale and the backstage, what the result is worth, opinions - starting
   from the dossier's `web_checklist` and your sport's **mandatory checks**
   (`references/sources-<sport>.md`; the index `references/context-sources.md`).
   Before searching, write the match's **kill facts** - what would break its
   legs - and search for those (more information raises confidence faster
   than accuracy). A leg with `prior_analysis` gets the delta pass. Each match
   section has **Kontekst (web)**, "nic istotnego dla tych nóg" included; a
   KEEP whose match had no pass is not a read. Protocol, budget and examples:
   `references/context-pass.md`; the evidence behind it: `references/literature.md`.
4. **Weight**: the pass looks for a **defect of the leg as printed** or a
   **fact newer than the price** acting through the leg's variable; what the
   model and the price already hold (home advantage, the referee's rate,
   form, table, rest) is no reason unless its input changed. A fact on two
   independent domains may carry a NO_BET; one domain, an opinion or a mood
   report at most a WATCH, through this leg's variable (name the mechanism).
   Measured 10-13..10-25: removals by opinion realised like the kept legs
   (`references/literature.md`, section 1). Every claim tagged
   `[WEB: <domain>, publ. <time>, fetched <UTC>]`. A KEEP `reason` names the
   expectation in the market's units, a dossier fact and the context
   finding - never a bare "15/18".
5. **Titles and snippets are content**: a leaked result - name it, mark the
   claim `CANNOT VERIFY`.
6. A source that is unreachable or needs re-authorisation: stop retrying and
   list the checks you did not make.
7. **A past or finished day** (re-read, replay): no web search at all - the
   result would leak. Everything outside the artifacts is `UNVERIFIED`.

Where context lives: `references/context-sources.md`. Never fetch odds from
the web or another bookmaker; Superbet's price in the artifacts is the only one.

## Verdicts and the two blocks

| verdict | effect |
|---|---|
| `KEEP` | stays; records the read (a leg in the set without a read fails C3) |
| `WATCH` | removed into `removed_by_reads` - a fact newer than the price on one domain, or an opinion, acting through the leg's variable by a named mechanism; or an artifact fact the code does not see ("DEFEKT: …" - a sample from another surface / venue / squad than tonight's) |
| `NO_BET` | removed - a defect, or a fact confirmed by two domains |

- **Vetoes** (football / tennis only): a sample that does not describe the
  match, or a context that breaks every rung - normally keyed with
  `market` / `subject` / `line` / `direction` null. Do not write the same
  fault twice as a veto and a NO_BET.
- **Reads**: one `LegRead` per leg of your file, `author: "analyst"`; a
  KEEP may cover a (market, direction) family (`line: null`) with the
  expectation against its lines - never a match-wide `market: null` KEEP.
- **What a removal's reason must name**: a fact newer than the price with a
  dated tag (`[WEB: domena, publ. <data>, fetched <czas>]`; unknown date =
  `publ. ?`, which is not newer than anything) or an artifact defect written
  `DEFEKT: <artifact, field, what is wrong>`. **Never a removal by itself**:
  h2h, form, a streak, the table, the model vs the own sample or
  `forecast_p` (the code's `MODEL_ABOVE_OWN_SAMPLE` already decides), a weak
  rating bridge between leagues (`CROSS_LEAGUE_UNLINKED` decides),
  `price_gap`, your own estimate near the confidence, "BUY ≈ KILL"
  (measured 10-13..10-25: such removals realised like the kept legs;
  10-26: 19 of 24 WATCHes were of this kind). Write them in the section as
  notes. `report_check` refuses a removal without one of the two marks.
- **Count what a null hits**: `subject: null` covers every subject of the
  match (no player field). Key a player leg to the player as the leg writes him.

Schemas, matching rules, every `reason_class` and `context` tag, worked
examples: `references/veto-contract.md` (read it before writing the first
entry of the day).

## Output contract

1. Write **exactly one** report, in Polish, to the path the caller gave -
   that path wins, wherever it is (normally
   `runs/sofa/<d>/<d>_analiza_<sport>[_<part>][_r<n>].md`) - with **one** Bash
   heredoc (`cat > <path> <<'MD' ... MD`). Splitting is the caller's job (one
   read-set part = one report); never split yours. If the path holds another
   report, take the next free `_r<n>` - never overwrite one. Your own report
   you may rewrite until the caller has merged it. Write no other file in the
   repo or `runs/`; scratch goes to `${TMPDIR:-/tmp}`.
2. Report structure:
   1. **Nagłówek** - read-set file, `11_coupon.json` `epoch`, legs read
      (required / buffer / asked by the operator), the snapshot time, the one
      sentence the bettor must read first.
   2. **Mecze** - one section per match in your sport skill's event-protocol
      format; every argument FAKT -> RACHUNEK -> IMPLIKACJA -> RYZYKO; every
      non-artifact statement tagged. **The match heading carries the token
      `sofa:<sofascore_event_id>`** (`### Home – Away — <rozgrywki> · sofa:15275920`):
      `merge_reads.py` files the section under that match in `analyses.json`,
      and the HTML view / the PDF appendix show it at the match's legs. The
      section is what the operator reads behind a leg: dense, no artifact
      tables copied (the page shows the numbers) - at most ~4,000
      characters a match, more only for a builder match or a removal.
   3. **Zdjęte** - each WATCH / NO_BET, one line, Superbet's words.
   4. **Czego zabrakło** and **NIE PODANO** - every check you could not make.
   5. ` ```json vetoes ` (football / tennis; `[]` is normal), then
      ` ```json reads ` - bare arrays, labelled exactly so.
3. Validate (read-only; no pipe that hides the exit code):
   `PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <d> --report <path> --author analyst --dry-run > "${TMPDIR:-/tmp}/mr_<sport>.txt" 2>&1; echo exit=$?`
   (a chat slip's file `read_set_slip_*.json`: add `--slip --read-set <that file>`;
   `UNMATCHED_READ` / `LEG_WITHOUT_READ` = a key that hits no leg / a leg you missed)
   then `grep -v CARRIED "${TMPDIR:-/tmp}/mr_<sport>.txt" | tail -15`, and
   the depth check `PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_analyst_report.py --report <path>`
   (exit 1 = rewrite what it lists; the PostToolUse hook runs it on every
   report you write and sends you the same list). Exit 2 = a block does not
   validate: rewrite your report and re-run; `UNMATCHED_VETO` = your keys hit
   no sheet row.
4. Return to the caller at most 12 lines: the path, legs read, KEEP / WATCH /
   NO_BET counts, the veto count, anything the caller must act on (a match
   moved, a defect in an artifact, legs you did not reach).

Never lead with a 0.5 UNDER tautology. Never write `pewniak`, `banker`,
`musi wejść`.

## Hard rules (analyst-specific)

- Every number traces to an artifact, a command you ran, or arithmetic you show.
- Never present a `FUZZY` identity as confirmed, a thin sample as actionable,
  or `NO_LADDER_CHECK` as a passed check.
- `combined_probability` of a builder is a probability, never a price.
