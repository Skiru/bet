# Verification of PLAN_NOWE_RYNKI_2026-11-20.md against the code (HEAD 7585bb54)

Read-only. No repository file was edited. Nothing was run against live data and no network was used; the DB was opened `mode=ro`.

Severity:
- **BLOCKER**: the plan as written cannot work or would misgrade or misprint.
- **FIX**: the plan must be corrected or completed before implementation.
- **NOTE**: worth knowing, or unconfirmed.

**Working-tree caveat.** While this check ran, the working tree held an uncommitted D (volleyball) implementation in 14 files: shadow, cs2, epochs, sport_confidence, vb_point_pricer, volleyball_point_model, leg_relations, market_coverage, superbet_names, run_shadow, run_sport_confidence, build_slip, verify_legs and audit_variants. Sections D and common were checked against a `git archive HEAD` snapshot. The A, B and C checks ran in parallel and may have read some of those 14 files mid-edit, so a line number in those files can be off by a few lines. Every BLOCKER and FIX was re-checked against HEAD: C-B1 (`football_sim_curves.py:63/120/213`), C-F1 (`fit_football_sim_curves.py:424`), B-F1 (`offer.py:557-563`) and A1 (`verify_legs.py:404-413`, `audit_variants.py:435-447`). The in-progress D code already avoids D-F1 and D-F2 below (it adds a separate `SET_MATCH_MARKETS` table, `VB_SET1_MATCH_ALLOWED`, and the flag in verify_legs / audit_variants).

---

## Common rules (section 1 and cross-market)

### COM-1 FIX - the price readers for the measured sports are described wrongly
- **Plan:** `verify_legs.py` gets the flag "dla sportów przez `parse_event`".
- **Code:** for sports, `verify_legs` never parses a payload.
  - It re-checks the family with `scf.family_of` (`scripts/sofa/verify_legs.py:404-413`, used at :457). The live re-ask is football / tennis only (:802-803 "measured-sport legs not re-asked (v1)").
  - Audit U3 reads `rsc._allowed` through `audit_variants.snapshot_family` (`scripts/sofa/audit_variants.py:435-447`).
  - `capture_closing` closes sport legs from their own snapshots (`capture_closing.py:70-76`).
  - The only sport `parse_event` callers are `run_shadow.py:220-226` and `build_slip.py:244-248`.
- **Correction:** for A and D, pass the switch to `family_of` / `allowed_markets` in three places: `run_sport_confidence._allowed` (:530-538), the `verify_legs.sport_day` closure, and `audit_variants.snapshot_family`. `capture_closing` needs nothing for sports. For B and C, one new `offer.day_flags` key covers `run_offer` :129, `build_slip` :365-367, `capture_closing` :331-333 and `verify_legs` :502.

### COM-2 FIX - byte for byte when off needs explicit serialisation work
- New optional pydantic fields serialise `null` on every row: `run_offer.py:178` uses a plain `model_dump`, and `PricedRung` has no serializer (B-F3).
- Every new leg, row or record field must be added only when set (`**({...} if ... else {})`), as `derived_rule` / `player_v2_rule` are (`run_shadow.py:252-255`, `run_sport_confidence.py:766-800`).
- New fit-script flags must default to today's behaviour. `refresh_line_evidence.py` runs `fit_sport_confidence --dry-run` every morning (A5).

### COM-3 FIX - the E2E recipe cannot run as written, for any market
- `rebuild_day.py:150` and `run_pipeline.py:182` refuse `SOFA_NOW`.
- On a finished day `rebuild_plan` schedules no OFFER step (`rebuild_plan.py:743-758`).
- A live OFFER or SHADOW for a past day asks Superbet for events that are gone, and it is network.
- Affected:
  - B: "kopia 11-19, `SOFA_NOW` 06:20Z";
  - C: "kopia 11-16, `rebuild_day.py --dry-run` musi pokazać OFFER + SHEET";
  - D: copies of 11-14 / 11-15;
  - A: "żywy `run_shadow.py` do kopii", which is live network and must be a deliberate operator decision.
- **Correction:** build the new rungs or lines offline from the recorded `unmapped_prices`, then run the single stage scripts with `SOFA_NOW` and a scratch `SOFA_RUNS_DIR`. `timeutil.py:35` refuses only the real runs dir. Unit-test the rebuild_plan triggers with a frozen clock.

### COM-4 NOTE - "after the switch the market leaves `unmapped_prices`" is only partly true
- C: DC "12" and handicap ±3.5 / ±4.5 still produce a label and stay (C-N4).
- B: the bare "Podwójne błędy" is also "kto więcej" and stays (B-F5).
- A: `reads_market` is by market id, so the whole 613 market leaves `unmapped_prices`, including the ±0.5 odds the parser refuses. They are then recorded nowhere.
- D: true; only 230059 "1.Set/Mecz" exists (7,072 records, 187 events in 399 volleyball unmapped files of 11-1x).

### COM-5 NOTE - plan references confirmed as cited
- `_audit_1023_on` (`epochs.py:3240-3245`).
- `BASKETBALL_PLAYER_V2` (`epochs.py:2268-2281`).
- `line_evidence.py:76` `MIN_EVIDENCE_BUCKET` 50 and `:99` `MIN_EVIDENCE_GAMES` 15 (plus :86-91 `MIN_OFFSET_ROWS` / `_GAMES` / `MIN_SPORT_OFFSET_GAMES`).
- `audit_ledger.EPOCH_GROUPS` :148 (last group "od 11-10") and `epoch_group` :327-328.
- `check_test_registry.py:62-66`: the evaluation script must exist; `:68-77`: `data_window.from` must be later than `registered_on`.
- `fit_sport_confidence.py` without `--out` writes the installed file (:565, :612), and the sport scripts read `SOFA_DB_PATH`.
- The documents exist: `docs/sofa/REJESTR_TESTOW.md`, `MODELE_HOKEJ_KOSZ_SIATKA.md`, `PIPELINE.md`, `CONFIG.md`, and the skills `sport-analysis`, `football-analysis`, `tennis-analysis`.

The "key with a curve reads the sport pool from day 1" statement needs one precision. Football, tennis and hockey read the price-gap offset, by d bucket, shrunk to the sport (`line_evidence.py:351-353`, `PRICE_GAP_OFFSET`). Volleyball reads the plain pooled offset.

### COM-6 NOTE - a 2026-11-22 00:00Z switch collides with nothing; the date is unrealistic
- **No collision.** The newest dated switch is `STAKES_GROUPS_FROM_UTC` 11-19, display only. The latest staged files are sport `.next.2026-11-07.json`, football `.next.2026-11-09.json` and sim `.next.2026-11-09.json`; the settleability fit is daily and football only. `calibration_path_for` / `football_sim_curves.path_for` would simply pick a new `.next.2026-11-22.json` for 11-22 and later.
- **Not realistic.** The plan's own estimate for A + C + D is 1.5-2 + 2.5 + 1.5 days, plus refits and E2E. The "one shared day D" recommendation therefore means keeping each switch `None` until all three are committed by D-1, or giving them separate ledger groups.
- **Late-window mechanics are correct:** a record's day is its file's and its clock is the fetch time. D-1's evening SHADOW fetch writes D's file with the switch off; the morning snapshot replaces it whole (`latest_pre_kickoff`).

### COM-7 NOTE - registered tests whose population grows
- The plan raises this only for `T-PRICE-EDGE-VB-RAW-FORWARD`, which exists and is REGISTERED, population "Printed volleyball singles ... every market".
- A and D also grow the population of six more tests: T-SPORT-LATE-WINDOW, T-A4-bucket-deff, T-LESSER-LOSS-flag, T-TOP-BAND-090-after-price-gap-offset, T-KUPON-PRICE-RISE-DROP and T-STABILITY-LABEL-FORWARD (A14).
- B grows T-TENNIS-DF-UNDER-FORWARD and the serve proposals (B-N5).
- Record it in the registry, or exclude legs by marker.

### COM-8 NOTE - internal inconsistencies
- Section 0 says every market is "osobny commit z własnym przełącznikiem", and also recommends one shared day D (see COM-6).
- Section 3 labels its commit steps "A kod -> E2E -> C zamrożenie", which collides with the market letters, and "D0" is undefined (B-N9).
- Acceptance 3, "the staged file differs only by the new keys", cannot hold literally: `effective_from`, `staged_change`, `curve_source` and `new_market_curves_fitted_from` change too (A4, C-F2).

---

## D - volleyball 230059 "1.Set/Mecz"

### Claims that hold (HEAD)
- **The misgrade is real.** `cs2.grade_side` (`cs2.py:544-588`) has no joint branch, so "T1/T1" reaches the two-way margin branch. The same holds for `volleyball_point_model.win_loss` (:438-460). The exact effect is in D-N1.
- **Rally pricer scope.** `vb_point_pricer.in_scope` (:65-66) is dateless, `sport == "volleyball" and market_id in VB_POINT_MODEL_MARKETS`.
- **Side class.** `side_class` (`sport_confidence.py:477-487`) maps any other side to TEAM, so "T1/T1" would become TEAM.
- **Readers that must know the market.** `reads_market` (`shadow.py:895-916`), `build_slip.py:242-248` and `leg_relations._shadow_proposition` (:484-534) do; `_shadow_spec` (:459-469) searches only `MARKETS` / `DERIVED_MARKETS`.
- **The 4-way group machinery handles a joint shape.** `run_sport_confidence` builds groups with `_group_key` (key[:4]), checks `cs2.group_fair(group_odds, _shape)` (:713) and the margin `cs2.group_overround` (:742), and applies the 15% `MAX_OVERROUND` in `price_filter` (:853). A "joint" shape in `complete_group` / `group_fair` (`devig_many`) / `group_overround` (total - 1) is enough.
- **Fixture.** `runs/sofa/2026-11-15/unmapped_prices/volleyball_20261114T070138.253746Z.jsonl.gz` exists. Event 15721202 has "ABEL/Moda (K)/ABEL/Moda (K)" 1.75, ".../Brasilia (K)" 7.9, "Brasilia (K)/ABEL/Moda (K)" 4.7 and "Brasilia (K)/Brasilia (K)" 4.4, which gives a margin of 0.1381.
- **Team names match exactly.** The snapshot (`runs/sofa/shadow/volleyball/2026-11-15/snapshots.jsonl`) has team1 "ABEL/Moda (K)" and team2 "Brasilia (K)", so matching the four `f"{a}/{b}"` strings works even though a team name contains "/".
- **Golden set and orientation.** `build_result` volleyball takes the winner from the sets on AET / AGS (`shadow.py:1187-1199`), and `t1_periods` / `winner` are already in Superbet orientation (`home_is_t1`). `VbPricer.p` swaps the simulation (`vb_point_pricer.py:190-199`, `swapped` = column swap), so "T1/T2" stays in Superbet orientation. "`VbPricer.p` / `swapped()` bez zmian" holds.
- **No same-event identity.** `leg_identity._scores_key` (:299-324) reads only `set_handicap` / `team_wins_set` / `exact_sets` / `winner`, so a `set1_match` leg gets no key. That is correct, since no single market is the same event.
- **No family whitelist elsewhere.** `set_winner` appears only in shadow / sport_confidence and in measurement scripts.

### D-F1 FIX (high) - do not put 230059 into `shadow.MARKETS` + `EXTENDED_MARKETS`
- **Plan:** step 1, `shadow.MARKETS["volleyball"][230059] = MarketSpec(...)`; step 6, `EXTENDED_MARKETS["volleyball"][230059]` plus "druga bramka w `_allowed`".
- **Code:**
  - (a) `parse_line` reads `MARKETS[sport].get(market_id)` and `reads_market` returns True for `market_id in MARKETS[sport]` with no switch (`shadow.py:713`, :910). Off is byte for byte only if the gate sits before those lookups.
  - (b) An `EXTENDED_MARKETS` key is allowed by `family_of` whenever line evidence is on, which is every day since 10-07.
  - (b) It also becomes a settled-only family automatically: `settled_only_families` = `allowed_markets(extended=True)` minus history markets (`sport_confidence.py:348-358`).
  - (b) `fit_sport_confidence.py:319-326` fits settled-only families on our own settled Superbet lines, at the score model's p. The next volleyball refit would then produce a `set1_match` curve from our days, which breaks "curves only from history". It would also be on the wrong estimator.
  - (c) `market_coverage._reader_reads` (:848-874), `leg_relations.mapped_sport_markets` (:785-796) and `measure_score_model.py:111` would treat the market as read with the switch off.
- **Correction:**
  - Use a separate table, e.g. `SET_MATCH_MARKETS`, gated by `set1_match` in `parse_line` / `parse_event` / `reads_market`.
  - Use an own allow-list passed through `allowed_markets` / `family_of` / `_allowed` / `settled_shadow_rows`.
  - Add the table to `spec_of`, `_shadow_spec`, `mapped_sport_markets` and `_reader_reads`.
  - Never put it in `EXTENDED_MARKETS`.
  - Note that `tests/sofa/test_sport_confidence.py:91-99` requires every `EXTENDED_MARKETS` key to be in `MARKETS`. The in-progress tree follows this correction.

### D-F2 FIX - verify_legs and audit U3 must get the flag
- Same as COM-1. Without it every printed `set1_match` leg is a verifier `sport_market` DEFECT (`verify_legs.py:457`) and "not in the snapshot" for audit U3 (`audit_variants.py:447`).

### D-F3 FIX - line evidence needs `settled_shadow_rows` and the backfill order
- **Code:**
  - `settled_shadow_rows` builds its allow-list per settled day (`sport_confidence.py:1257-1258`) and prices a row with the score model's `line_probability` → `shadow.actual_value` (`score_model.py:1306-1330`). Without the new family in that allow-list and a `set_match` branch in `actual_value`, no evidence row exists.
  - `fit_line_evidence.sport_rows` then swaps in the rally p from the backfill for `in_scope` markets and skips the row when the backfill lacks the key (`fit_line_evidence.py:282-298`).
- **Correction:**
  - Add the family to `settled_shadow_rows` by the settled day's switch.
  - Run `backfill_vb_point_p.py` with the widened `in_scope` before `refresh_line_evidence`.
- **Timing:** before the switch no 230059 line was ever graded; they sit only in `unmapped_prices`, which carry no result. The backfill therefore yields nothing on day D, and the key reads its curve plus the volleyball pooled offset. The plan's "Dowody: backfill..." should say that.

### D-N1 NOTE - the misgrade wording
- **Plan:** "T1/T1 ... jest zawsze LOSS".
- **Code:** the two-way branch computes `margin = actual + 0`.
  - With an indicator of 1 (it happened): margin > 0, but side != "T1", so LOSS.
  - With 0: margin == 0, so **VOID**.
- So a won T1/T1 grades LOSS and a lost one VOID. `win_loss` likewise counts only the happened case as decided, so p is 0 or None. The regression test must assert both outcomes.

### D-N2 NOTE - parse from the name only
- `unmapped_prices` records carry no `code`, `info` or `specifiers`; volleyball records have no `specialBetValue` either (`unmapped_prices.FIELDS`). The 230059 outcome `code` has never been seen.
- `_wide_side` cross-checks `code` where it knows a mapping. The joint branch must not depend on an unseen code: read the name only, or capture one live payload first.
- Add a test that the four candidate strings are unique for a pair of names containing "/".

### D-N3 NOTE - test events (DB `mode=ro`)
- 16562455: AET, winnerCode 1, 3-2, `overtime` present.
- 17267101: 1-3 (4 sets).
- 17193834: 3-2.
- **15609512 is a Superbet id, not a Sofascore id.** It is Ferro Carril Oeste - Waiwen, Sofascore 17246111, 0-3 in `runs/sofa/shadow/volleyball/2026-11-14/settled.json`. It is absent from `sofa_event_detail`. Label the ids.
- The golden-set case 16562455 has winnerCode equal to the sets' winner, so it does not test the dangerous case. Add a game where winnerCode names the tie, e.g. 12193496 cited at `shadow.py:135`: 3-1 in sets, winnerCode 2. It is not in `sofa_event_detail`; where it is cached is unconfirmed.

### D-N4 NOTE - `market_coverage`
- The rule `vb.set_and_match` already exists (`market_coverage.py:509-510`, text "model wyniku - łączny rozkład"). Update it; do not add it.
- `_reader_reads` must learn the new table (D-F1c).

### D-N5 NOTE - `leg_relations`
"set1_match w zbiorze score" needs an explicit Quantity. Suggestion: stat "sets", a new form "joint", period `_VOLLEY_ALL`. Make sure `_same_variable`-style comparisons against a "diff" form of the same stat (`winner` 745 is scope "sets", stat "sets") do not take a wrong path. Unconfirmed: what the relation code does today with an unknown form on the same stat. Test the `winner` / `set_winner` period 1 / `set1_match` pairs.

### D-N6 NOTE - registry
- `T-VB-SET1-MATCH-calibration` needs an existing evaluation script and `data_window.from` later than `registered_on`; the plan names no script.
- The plan's hold-out "2026-09-29..11-20" can only run on Sofascore history, not on Superbet lines (none were graded).

### D-N7 NOTE - small items
- `Kind` / `Shape` are Literals; mypy will force the new values through `complete_group`'s fall-through, which otherwise returns `group in EXACT_SETS`.
- `superbet_names._selection` needs a "joint" kind that renders "{A}/{B}" from "T1/T2".
- `lesser_loss` never marks these legs (margin ~0.138 > 0.086).
- `vb_point_rule` stamps `vb_point_model_rule` once `in_scope` is widened, in addition to the new leg field.

### D status after go-live (checked 2026-11-24, live days 11-22..11-24, read-only)

D went live 2026-11-22 00:00Z (aabe0fc2). D-F1 and D-F2 are implemented as corrected above. Verdict: **no defect found; the switch stays on.**

- **D-F3 - OK.**
  - `settled_shadow_rows` allows `set1_match` by the settled day's switch (`sport_confidence.py`, `allowed_markets(..., set1_match=epochs.vb_set1_match(date, _day_end(date)))`), and `actual_value` has the `set_match` branch.
  - `refresh_line_evidence.py` runs step 1 (rows), then 1b `backfill_vb_point_p.py`, then step 2 `fit_line_evidence.py`. `vb_point_pricer.in_scope` covers 230059, so `fit_line_evidence.sport_rows` reads these rows at the rally p.
  - The rows are there: `data/line_evidence/rows_before_2026-11-24/volleyball_superbet_settled.jsonl` holds 74 SAME + 74 SPLIT rows of 11-22 and 8 + 8 of 11-23. The backfill holds 164 keys with 230059 (41 events x 4).
  - `config/sofa_superbet_line_evidence.json` (before 2026-11-24, 6b157114) has `keys.volleyball.set1_match|SAME` (n 82, 41 games) and `|SPLIT` (n 82), plus their `bands`.
  - Both keys are below `MIN_OFFSET_ROWS` / `MIN_OFFSET_GAMES` on printable lines, so legs read the volleyball pooled offset (`calibrated_on ...-0.0043sb`), as the timing note above predicted.
  - New test: `test_the_settled_lines_reach_the_line_evidence_by_the_days_switch` (`tests/sofa/test_vb_set1_match.py`).
- **E2E SHADOW - OK.**
  - `shadow/volleyball/<d>/snapshots.jsonl` records with `vb_set1_match_rule` hold exactly 0 or 4 sides of 230059, never a partial group: 11-22 264 records / 39 events, 11-23 31 / 4, 11-24 43 / 11.
  - From 2026-11-22 00:00Z no 230059 price is in `unmapped_prices`. The 32 still there on 11-22 come from snapshots taken before the switch.
  - Every event with 230059 in the post-switch unmapped files was parsed (11-23 4/4, 11-24 11/11). Team names containing "/" were present on 11-22 (57 records).
- **E2E SPORT_CONFIDENCE / print - OK.**
  - Legs printed in `11_coupon.json` `singles`: 6 on 11-22, 1 on 11-23, 1 on 11-24. All are SAME sides and carry `vb_point_model_rule` + `vb_set1_match_rule` and `forecast_source: vb_point_model`.
  - Superbet's words are right, e.g. "1.Set/Mecz | Lvi Praga/Lvi Praga".
  - `overround` equals the 4-way group's sum(1/odds) - 1, recomputed from the snapshot at `price_fetched_at_utc` for all 8 legs (0.1115..0.1411, all under 15%). Refusals of 230059 lines were not broken down: `08_confidence_sports.json` counts refusals per sport only.
  - Confidence = the curve of `config/sofa_vb_set1_match_curves.json` minus the pooled offset, e.g. p 0.8788 -> bucket 0.875-0.900 0.8515 - 0.0043 = 0.8472.
  - The live `forecast_p` equals the backfill's rally p for all 7 settled printed legs. Each event's four backfilled p sum to 1.0.
  - The 11-22 verifier (`2026-11-22_weryfikacja.md`) listed the 6 legs with 0 DEFECT, so D-F2 holds live.
- **E2E SHADOW_SETTLE - OK.**
  - 11-22: 37 events graded, 11-23: 4, with exactly one WIN per group and no VOID or ungradeable 230059 line.
  - Hand-check of all 42 graded events (incl. 11-24's 1) against `sofa_event_detail` (`mode=ro`): set 1's winner from `period1`, the match's from the sets won, oriented by `home_is_team1`. 0 mismatches.
  - No golden-set or AET match occurred among them, so the golden-set rule is covered only by the unit tests (`test_a_golden_set_never_turns_the_match`).
  - Two 11-22 events with 230059 (Aris - Foinikas 15419975, Netzhoppers - Rottenburg 15830178) have no graded line of any market: their last pre-start snapshot (15:20Z) had 0 lines. That is SHADOW_SETTLE's general last-snapshot rule, not this market's; neither was printed.
- **E2E ledger - OK.**
  - `13_results.json` grades the 7 printed legs of 11-22 / 11-23 at the printed price, matching SHADOW_SETTLE (11-22: 4 WIN, 2 LOSS; 11-23: 1 WIN).
  - `runs/sofa/ledger/results.jsonl`: `official` volleyball section, `measure:volleyball` `by_family.set1_match` (11-22: 37 events; 11-23: 4); `audit_ledger.epoch_group` = "od 11-22".
- **Not verified:** no golden-set match live; 11-24 not settled yet; no live re-ask of a 230059 price (no network); the late-evening rebuild path for `window: "late"` legs of this market.

---

## Plan verification - A (hockey NHL 617 / 613 / 621 / 653, "z dogrywką i rzutami karnymi")

Plan: `docs/sofa/history/PLAN_NOWE_RYNKI_2026-11-20.md` section 2 (+ 0 / 1 / 6 where they concern A).
Code: `main` 7585bb54. Read-only check: no file changed, nothing run against live data.

## Claims confirmed in the code

| claim | code |
|---|---|
| `_hockey` adds one goal to the OT / shootout winner on a level score, `hk_ot_strength` 0.5 | `src/bet/sofa/score_model.py:1117-1129`, `:614-616` |
| `build_result` allows a shootout winner's `current` without the +1 (`{reg+ot, reg+ot+1}`) | `src/bet/sofa/shadow.py:1255-1277` (also `_final_only_result` :1107-1112) |
| `leg_relations._shadow_spec` searches only `MARKETS` / `DERIVED_MARKETS` | `src/bet/sofa/leg_relations.py:459-469` |
| `fit_sport_confidence.py` without `--out` writes the installed file | `scripts/sofa/fit_sport_confidence.py:545-546, 565, 612` |
| sport scripts read the DB from `SOFA_DB_PATH`, no `--db-path` | `src/bet/sofa/config.py:132`; `fit_sport_confidence.py:575` uses `config.db_path` |
| `BASKETBALL_PLAYER_V2` pattern | `src/bet/sofa/epochs.py:2268-2280` |
| `_audit_1023_on` | `src/bet/sofa/epochs.py:3240-3245` |
| `audit_ledger.EPOCH_GROUPS` :148, `epoch_group` top branch :328 | `scripts/sofa/audit_ledger.py:148-154, 327-331` |
| `run_shadow.py:210-226`, `build_slip.py:244-247` are the two `parse_event` callers | confirmed; `build_slip._same_line` (:197-209) compares `market_id`, so 604 / 613 do not collide there |
| 613@|h|>=1.5 dedups with 604@h already through family `handicap` | `src/bet/sofa/leg_identity.py:199-260`: family `handicap`, period 0 -> scope "reg", margin key; the key is by family, not market_id |
| `.next.2026-11-07.json` is the latest staged sport calibration | `config/`: `.next.json` (10-14), `.next.2026-10-24`, `.next.2026-10-28`, `.next.2026-11-06`, `.next.2026-11-07`; nothing later. `calibration_path_for` (`sport_confidence.py:119-135`) picks the latest `effective_from` <= day and refuses a file name / `effective_from` mismatch. A copy of 11-07 + 4 keys is the full set: no later file has keys to miss |
| no existing switch after 2026-11-19 | `epochs.py`: newest dated are `STAKES_GROUPS_FROM_UTC` 11-19 and `STABILITY_LABEL_FROM_UTC` 11-16; neither touches hockey. A 2026-11-22 00:00Z switch interacts with no switch or staged file |
| 613 names are "Team (h)" with no "+", sbv = team1's handicap | unmapped 11-1x: "Edmonton Oilers (1.5)" / sbv 1.5, "New York Islanders (-1.5)" / sbv 1.5 - fits `_HCP_IN_NAME` (`shadow.py:637`) and the check at :771-776 |

## Findings

### A1. FIX (high) - the verifier and audit U3 would flag every new leg
- **Plan:** section 1 says `verify_legs.py` gets the flag "przez `offer.day_flags` dla piłki / tenisa; dla sportów przez `parse_event`". Section 2 step 4 names only `run_sport_confidence.build_sport`.
- **Code:** for sports, `verify_legs.py` does not call `parse_event`. It re-checks each leg's family with its own `family_of` closure (`scripts/sofa/verify_legs.py:404-413`, used at :456-460). If the family is not allowed, the leg gets `DEFECT "family ... not allowed"`. `scripts/sofa/audit_variants.py:435-447` (`confidence_family`, U3 `audit_sport_legs`) calls `rsc._allowed(sport, line, evidence_on, derived, series_rounds)` with no new flag.
- **Effect:** without the flag, every printed 617 / 621 / 653 leg is a sport_market DEFECT for the verifier (`/sofa-verify` can turn that into a removal read) and "not in the snapshot" for audit U3.
- **Fix:** add the `ot_so` parameter to `scf.family_of` / `allowed_markets` / `rsc._allowed`. Pass `epochs.hk_ot_so_markets(date, at)` in all three places: `run_sport_confidence.py:530-538` and :588, `verify_legs.py:404-413`, `audit_variants.py:445-447`. Add a test for each.

### A2. FIX - no real payload of these markets exists, so the parser is untested
- **Plan:** test "parsowanie prawdziwego payloadu NHL". Step 2 reuses `parse_line` (totals from `specifiers["total"]`, handicap from `specifiers["hcp"]`, plus the `code` / name check).
- **Code:** `unmapped_prices.FIELDS` (`src/bet/sofa/unmapped_prices.py:37-41`) stores only marketName / name / specialBetValue / price / status / marketId. It keeps no `specifiers`, `code` or `info`. The golden payload `tests/sofa/golden/superbet_hockey_double_chance_2026-10-13.json` was trimmed to 606/616/623/630/640/660. The measurement never ran `parse_line` on these markets: `s08_checks.py` builds the `ShadowLine`s by hand. The report says the 617 `info` was never seen.
- **Effect:** if 617 / 621 / 653 carry the line under a key other than `total`, or 613 under one other than `hcp`, every line is dropped silently (`value is None` -> None, `shadow.py:767-768`). Nothing would fail and nothing would print.
- **Fix:** step 0 of A captures one live NHL `/events/{id}` payload into `tests/sofa/golden/` and checks the specifier keys and codes. Otherwise read the line from `specialBetValue` as a fallback, and say so in the plan. The off-equals-today test cannot catch this.

### A3. FIX - the four new keys must be registered as new-market curves, or a later refit drops them
- **Plan:** step 5 composes `.next.<D>.json` = copy of 11-07 + 4 keys + `staged_change`.
- **Code:** `fit_sport_confidence.py` replaces a sport's whole section (`:577-582`). It keeps only the keys listed in the top-level `new_market_curves_fitted_from`, through `fit_meta.carry_sport_new_market_curves` (`src/bet/sofa/fit_meta.py:186-212`).
- **Effect:** a later hockey refit without `--hk-ot-so` scores only `HISTORY_MARKETS` and silently drops `total_ot|*` / `team_total_ot|*`. Those legs would then read NO_LINE_EVIDENCE.
- **Fix:** add `"hockey:total_ot|OVER"` etc. to `new_market_curves_fitted_from`, with their `fitted_from` (script, flags, DB copy, competitions filter, window). Or make `--hk-ot-so` default to "auto" by the `--before` day's switch, as `--hk-late-in-mean` does with `switch_mode` (:529-533, :226-227). Then a refit for a day at or after D scores them itself.

### A4. FIX - name the compose script, and do not use `install_new_market_curves.py`
- **Plan:** "skrypt składa `config/sofa_sport_confidence_calibration.next.<D>.json`" - no script is named. Acceptance criterion 3 says "differs only by the new keys".
- **Code:** the existing tool `scripts/sofa/install_new_market_curves.py` merges a sport group into the installed file and into every staged `.next*.json` (header lines 13-19; tests `test_every_dated_staged_sport_file_is_merged_too`). That edits files read by days already built, which CLAUDE.md forbids.
- **Fix:**
  - Write a dedicated compose step (or a `--target-file` mode) that touches only the new dated file.
  - The diff test must allow exactly: `effective_from`, `staged_change`, `new_market_curves_fitted_from` (+4), and in `sports.hockey` the dicts `curves` (+4) and `curve_source` (+4).
  - Decide whether to touch `admitted` / `not_calibrated` / `oos`. With line evidence on they are not read: `lookup(require_admitted=False)` (`sport_confidence.py:601-612`).

### A5. FIX - `--hk-ot-so` / `--markets` do not exist; the fit needs four code changes
- **Plan:** `fit_sport_confidence.py --hk-ot-so on --markets 617,621,653 --out ...`
- **Code:** neither flag exists (`fit_sport_confidence.py:464-556`). `score_game` / `walk_forward_rows` take `markets=` (`sport_confidence.py:1014-1025, 1096-1110`), but `fit_sport` does not pass it (:292-304). Lines come from `LINE_QUANTILES` (`synthetic_lines` :860-931), not a fixed ladder. Thinning is `step = len(window) // max_games` over every competition (:1160-1161). No competition filter exists.
- **Fix:** list the four changes explicitly:
  - pass `markets` through to the fit;
  - a fixed line ladder for the `incl` families;
  - a competition filter for scoring (ratings still learn from every league);
  - no thinning for the filtered competitions.

  Keep `HISTORY_MARKETS` unchanged when the flag is off. `refresh_line_evidence.py` runs `fit_sport_confidence --dry-run --rows-out` every morning (`refresh_line_evidence.py:133-134`): a history scoring that is always on adds unthinned NHL rows to that run and changes its outputs.

### A6. FIX - 604 / 613 key collision: drop the line, do not assert
- **Plan:** step 7, "asercja rozłączności 604 / 613 albo `market_id` w kluczu".
- **Code:** these keys have no `market_id`:
  - `fit_line_evidence.graded_odds` (`scripts/sofa/fit_line_evidence.py:259-280`);
  - `coupon_sports.sport_key` (`src/bet/sofa/coupon_sports.py:138-147`, also used by `apply_reads`);
  - `locked_print.leg_key` (`src/bet/sofa/locked_print.py:64-86`);
  - `priced_view.leg_key` (:54-63), `read_set.leg_key` (`scripts/sofa/read_set.py:145`), `prepare_refit.leg_key`.

  Today Superbet does not quote 604 for NHL (report section 1), so the two never meet.
- **Fix:** an assertion in a live stage would crash SPORT_CONFIDENCE or COUPON on the first day both are quoted. Instead, in `parse_event` (hockey, under the switch), drop a 613 side when 604 quotes the same (line, side): the two are the same event. Test it. Adding `market_id` to `locked_print.leg_key` would break every stored key ("every stored key still reads", :72-73), so avoid it.

### A7. FIX - the `incl` rule for a `final_only` game is not specified
- **Plan:** step 2, "`final_only` analogicznie".
- **Code:** `_pair`'s final_only branch (`shadow.py:1307-1314`) returns `t1_full` / `t2_full` (Sofascore `current`) for "full" and `reg_score` for "reg". For an AP game, `current` may lack the shootout +1 (`_final_only_result` :1107-1112 allows it).
- **Fix:** state the rule and test it:
  - incl = (t1_full, t2_full) when they differ;
  - when they are level and `winner` is set, +1 to the winner;
  - when they are level and `winner` is None (a regulation draw, Ended), the level score as it stands.

  Same for the period path: sum of periods, +1 to `winner` when `overtime`.

  `sport_day.grade_leg` (`src/bet/sofa/sport_day.py:274-312`) rebuilds `GameResult` from settled.json (`t1_periods`, `t1_full`, winner, overtime). The new branch in `_pair` covers the ledger only if it reads nothing that is not stored there. It does not: periods, winner and overtime are all stored.

### A8. NOTE - ±0.5 on 613 must be refused (a correctness need, not only taste)
- `leg_identity._margin_wins` reads family `handicap` as a regulation margin. A 613 +0.5 T1 leg would get the key d >= 0, the same as `double_chance` 606 "1X". These are different events: 606 is regulation, 613 +0.5 is the OT/SO winner. SAME_EVENT_DEDUP would then drop one of them wrongly.
- The plan's "613 ±0,5 -> None" prevents this. Keep that test, and add a leg_identity test that 613 never shares a key with 606 / 640 / 630.

### A9. NOTE - leg_identity total vectors: half-point lines only, and keep today's families unchanged
- **Plan:** step 6, a score-state vector for `total` / `total_ot` / `team_total` / `team_total_ot`.
- Today hockey has only margin keys (`leg_identity.py:327-337`). A new total key would also cover 623 / 658 / 652, which print today.
- Restrict it to half-point lines, as `_margin_wins` already does (`line != int(line)`, :232).
- Add a test that no existing hockey leg pair on a replayed day gets a new shared key (byte-identical when off). The identity 617@odd k ≡ 623@k holds by logic and by the report's 9447/9447 pairs.

### A10. NOTE - leg_relations: add `incl` to `_shadow_period` and the new table to `mapped_sport_markets`
- `_shadow_period("hockey", "incl", 0)` would today return `{"P0"}`: the fallback, `leg_relations.py:438-441`. Map `incl` to `_HOCKEY_REG | {"OT"}`, as "full" already is.
- `_shadow_spec(sport, "handicap")` returns 604's spec ("reg") for 613. That is correct for |h| >= 1.5.
- `mapped_sport_markets` (`leg_relations.py:785-796`) iterates only `MARKETS` / `PLAYER_MARKETS`. Add the new table, or `tests/sofa/test_leg_relations.py:86-108` will not cover `total_ot` / `team_total_ot`.

### A11. NOTE - `market_coverage`: the note exists but its text is stale
- `hk.ot_so_scope` already exists (`src/bet/sofa/market_coverage.py:479-482`). Its text says "model wyniku liczy czas regulaminowy".
- `_reader_reads` (:848-874) knows only `MARKETS` ∪ `PLAYER_MARKETS`; it does not know DERIVED either.
- Under the switch, add the new table to `known` and update or retire the note.

### A12. NOTE - the 613 curve key pools regulation ±0.5 rows
- 613 reads `handicap|TEAM`. That curve is fitted on regulation-handicap lines at `LINE_QUANTILES`, ±0.5 included, which is exactly where the draw error (-5.3 pp) sits.
- 613 is offered only at |h| >= 1.5. A curve bucket mixes both kinds of row. Not a misgrade; report the 613 hold-out separately.

### A13. NOTE - shootout counted as one goal in 621 / 653: unconfirmed for Superbet's line settlement
- The report proves that Superbet's final-score metadata counts the shootout as +1 for the winner (Vegas - Dallas 3/4). It does not prove that Superbet settles 621 / 653 / 617 lines that way: we hold no Superbet grade of a line.
- Standard bookmaker practice agrees. Mark it unconfirmed until the first settled AP game is checked against Superbet's settled bet history, and put that in the E2E list.

### A14. NOTE - registered forward tests whose population grows
- These tests take all measured-sport or all coupon legs: T-SPORT-LATE-WINDOW, T-A4-bucket-deff, T-LESSER-LOSS-flag, T-TOP-BAND-090-after-price-gap-offset, T-KUPON-PRICE-RISE-DROP, T-STABILITY-LABEL-FORWARD (`config/sofa_test_registry.json`). About 44 NHL legs a day would join them.
- The plan raises this only for VB (`T-PRICE-EDGE-VB-RAW-FORWARD`). Either name them for A too, or exclude `hk_ot_so_rule` legs from them.

### A15. NOTE - test registry timing
- `check_test_registry.py:68-77` refuses a test whose `data_window.from` is <= `registered_on`. Register `T-HK-OT-SO-calibration` no later than D-1.
- The `evaluation` field must name a script that exists (:62-66). The plan names none for A.

### A16. NOTE - naming clash
- The plan uses the identifier `HK_OT_SO_MARKETS` twice: for the epochs switch name (step 1) and for the shadow table (step 2).
- Rename one, e.g. the table `HK_OT_SO_SPECS`, to avoid import confusion.

### A17. NOTE - smaller wiring the plan leaves implicit
- `spec_of` (`shadow.py:365-371`) must include the new table. Without it, history, settle, `sport_day.grade_leg` and `sample_hit_rate` all return None: UNGRADEABLE, not a misgrade.
- `group_shape` -> "two" for the new kinds is already right.
- `superbet_names.SPORT_MARKETS["hockey"]` entries:
  - 617 "Liczba goli (z dogrywką i rzutami karnymi)" / ou;
  - 621 "{T1} - liczba goli (z dogrywką i rzutami karnymi)" / ou;
  - 653 "{T2} - ..." / ou;
  - 613 "Handicap (z dogrywką i rzutami karnymi)" / hcp.
- `run_sport_confidence.py:766-800`: add the `hk_ot_so_rule` leg marker beside `derived_rule` / `player_v2_rule`.
- `docs/sofa/MODELE_HOKEJ_KOSZ_SIATKA.md` (listed for D) should get the hockey scope too, as should `.claude/skills/sport-analysis` (agents do not read CLAUDE.md).

### A18. NOTE - switch-day mechanics (checked, no conflict)
- On D, snapshots fetched before 00:00Z carry no 617. The 04:30Z loop snapshot replaces the record whole (`latest_pre_kickoff`).
- `settled_shadow_rows` gates by the settled file's day (`sport_confidence.py:1257-1258` pattern). D-1's late-window NHL games (D 00:00-05:00Z) can carry 617 lines in D's file. They are still refused on D-1's coupon (family gated by D-1) and graded only as SHADOW_SETTLE rows of D: correct.

## Byte-identical-when-off

Feasible:
- `parse_line` / `parse_event` / `reads_market` default `ot_so=False`.
- The `spec_of` / `_pair` / `_shadow_spec` additions are unreachable without lines.
- `settled_shadow_rows`, `allowed_markets` and `settled_only_families` stay unchanged while their gate is off.

Risks: A9 (leg_identity keys on existing families) and A5 (history scoring in the daily refresh dry-run). Both need gating or a replay test.

## Contradictions within the plan

- Section 1 says `verify_legs` gets the flag "dla sportów przez `parse_event`"; the code reads families instead (A1).
- Step 5 / acceptance 3 "differs only by 4 keys" cannot hold literally: `curve_source`, `effective_from`, `staged_change` and `new_market_curves_fitted_from` must change too (A3 / A4).
- The measurement graded with scope "full" (`t1_full`, 4020/4020). The plan grades `incl` from the periods. The plan is the safer rule (A7), but the 4020/4020 figure does not validate the new branch: re-run that check on the new branch.

---

## Plan verification - C (football half handicap + half double chance)

Plan: docs/sofa/history/PLAN_NOWE_RYNKI_2026-11-20.md section 4 (+ 0/1/6 where they touch C).
Code: HEAD 7585bb54. Read-only; DB read with mode=ro; no network.

## Confirmed claims (no action)

- `run_settle._settle_sim_market` scripts/sofa/run_settle.py:384-394 grades `settle_value(value, row["line"], ...)` - the docstring says "graded at line 0.5" but the code uses the row's line. A 1/0 indicator vs line 1.5 = LOSS on every win. Misgrade claim CONFIRMED. `regrade_settled.py:95,203` imports the same function, so one fix covers both.
- Sim chain has no line: `path_spec(market, subject, direction)` football_sim_markets.py:335, `path_holds(market, subject, ht, ft, first_1h)` :228, `sim_value(market, subject, event, incidents)` :300, `SimPricer.p(event_id, centres, market, subject, direction)` football_sim_sheet.py:118, `fit_football_sim_curves.SUBJECTS` (market, subject, direction) :96-117, `day_lines` key `(eid, market, subject, direction)` :311-313, `_price_job` :330. CONFIRMED.
- `SCHEDULE_TERM_MARKETS = {...} | (FOOTBALL_SIM_MARKETS - SCHEDULE_TERM_FLOOR_EXCLUDED)` epochs.py:3999-4003. CONFIRMED: adding keys to FOOTBALL_SIM_MARKETS would change the schedule-term population.
- `fit_football_sim_curves --schedule-term`: `excluded = replay.terms.excluded_markets` (:461-462) from config/sofa_schedule_terms.json `excluded_markets` (the 4 floor keys). CONFIRMED: new keys would be priced on corrected centres in a `--schedule-term` fit. Live SHEET prices them uncorrected (`schedule_term_rows` run_sheet.py:1992 `market not in SCHEDULE_TERM_MARKETS -> price(football, False)`).
- `football_sim_curves.py:199` `if day >= before or (switch_day ... and day >= switch_day)`; caller passes the FOOTBALL_SIM day (fit_line_evidence.py:432-445). CONFIRMED.
- `fit_football_sim_curves.py` has no `--awarded-excluded`; backfill refuses awarded via `settle_completed` (:386-389); the minute-history pickles exclude awarded (measure_football_sim.py:305 on the live part - the 11-06 pickle's history part NOT re-checked: unconfirmed).
- `offer._add_price` offer.py:381-424 keeps `min(existing, new)` on a collision. CONFIRMED.
- Key-name rule (no `handicap_` / `dc_and_` prefix) is well founded: `market_mapper.derived_base` / `is_derived` (:1109-1117), `confidence.is_derived` (:168), `superbet_names.py:397`, `run_settle.py:487`, `measure_football_sim.GROUP_MARKETS` (:1153), `dc_and_*` are SCORE_MARKETS. `result_1h_handicap` contains `_1h_`, so `leg_relations._period` (:103) reads it as 1ST (harmless; never in a builder).
- `RATING_ONLY_MARKETS` tennis_winner.py:66-69 includes `football_sim_markets.MARKETS` -> if `fsm.MARKETS = BASE | HALF`, the new keys are rating-only (no builder, own curve only, `coupon_results.EVENT_MARKETS` :72 shows "tak/nie / wynik" not "1 vs 1.5"). run_sheet routes `rung.market in RATING_ONLY_MARKETS` (~:2747) before the sample branch, so the `run_sheet.py:2994` "no metric" skip does NOT hit C.
- `leg_floor` epochs.py:3827-3842: the new keys are not in FOOTBALL_SIM_FLOOR_KEYS -> 0.70. "podłoga 0,70" needs no code.
- Superbet shapes (runs/sofa/2026-11-15..19 unmapped_prices): "1.połowa - handicap" / "2.połowa - handicap", selection "<team> (L)" no "+" sign, `specialBetValue` = home's line (svb -1.5 -> home (-1.5), away (1.5)); outcomeId 151894/151895 (1H), 151898/151899 (2H) = home/away. svb seen: ±0.5, ±1.5, ±2.5, ±3.5, ±4.5 (no integer lines in 11-15..19). Half DC: selections "1X" / "X2" / "12", no svb. Price check 17551008: DC 1X 1.32 vs home +0.5 1.35 - different prices, CONFIRMED.
- Test fixtures (DB, mode=ro): 15534188 Kazakhstan - Slovakia HT 1-0 FT 2-2; 15534056 Germany - Netherlands HT 1-0 FT 5-0; 15458641 IFK Stocksund - Enköpings HT 0-0 FT 1-3; 17551008 Montenegro U21 - Bosnia & Herzegovina U21 (not started). 11-16 has 05_sheet.json. CONFIRMED.
- `audit_ledger.EPOCH_GROUPS` :148, `epoch_group` :329 (top branch pattern). CONFIRMED. Last group "od 11-10".
- No staged file / switch dated after 11-19 exists (latest: `.next.2026-11-09.json` main + sim, STAKES_GROUPS 11-19). A `sofa_football_sim_curves.next.2026-11-22.json` would simply become the latest for 11-22+ (`path_for` :93-110).

## BLOCKER

C-B1. New keys outside `football_sim_curves` scope -> no curve, no backfill evidence, nothing prints.
- Plan: separate `FOOTBALL_SIM_HALF_MARKETS`, `fsm.MARKETS = BASE | HALF`; curves in `sofa_football_sim_curves.next.<D>.json`.
- Code: football_sim_curves.py:63-64 `_in_scope` = `key in epochs.FOOTBALL_SIM_MARKETS`; `_replace` (:113-117) keeps only in-scope keys from the doc, `no_pool` (:120) and `ours` (:213) likewise. The staged file's 4 new keys would be DROPPED by `overlay`; `merge_evidence` would not take their backfilled entries.
- Correction: make `_in_scope` / `no_pool` / `ours` read `FOOTBALL_SIM_MARKETS | FOOTBALL_SIM_HALF_MARKETS` (or `fsm.MARKETS`); test that a half key in the staged file survives `for_day` and that line evidence carries it. Also `rebuild_plan.py:605` uses `epochs.FOOTBALL_SIM_MARKETS` (plan already adds `offer_has_sim_half`).

C-B2. E2E as written cannot run.
- Plan: "kopia 11-16 ..., `rebuild_day.py --dry-run` musi pokazać OFFER + SHEET".
- Code: rebuild_plan.py:743-758 - with `open_fixtures == 0` (a past day) no OFFER step at all (DAY_OVER note); `sim_offer_stale`-style branches sit in the open-fixtures `else`. rebuild_day.py:150 and run_pipeline.py:182 refuse SOFA_NOW. A live OFFER would ask Superbet for 4-day-old events (network, and no prices).
- Correction: E2E offline - build the half rungs from the recorded `unmapped_prices` snapshot (e.g. 20261116T062608) through `classify_odd(..., football_sim_half=True)` into a scratch `04_offer.json`, then run SHEET / CONFIDENCE / COUPON stage scripts directly with `SOFA_NOW` and a scratch `SOFA_RUNS_DIR` (timeutil.py:35 only refuses the real runs dir). Test the rebuild_plan triggers (`sim_half_offer_stale`, `sheet_football_sim_half`) as unit tests with a frozen `now`. (Same objection applies to B's "kopia 11-19 SOFA_NOW 06:20Z" if it goes through rebuild_day - outside C.)

## FIX

C-F1. `fit_football_sim_curves.py --out` defaults to the INSTALLED file.
- Code: :424 `--out default=str(config_path(fsc.FILE))` = config/sofa_football_sim_curves.json (read by 11-06 17:30Z .. 11-09 11:30Z). Plan's section 1 warns only for `fit_sport_confidence.py`.
- Correction: `--out` mandatory (scratch `data/refit_<D>_sim_half/...`), never the default.

C-F2. Flags the plan uses do not exist.
- Plan step 6: `fit_football_sim_curves.py ... --keys, --base ..., --effective-from`.
- Code: argparse :418-435 has none of them; the script writes a whole file with no `effective_from` / `staged_change` (11-09's `effective_from` was added outside the script). `_staged_start` (:79-88) RAISES when `effective_from`'s date differs from the file name.
- Correction: say they are new; the composed file = 11-09 file byte-for-byte for every existing key + 4 new keys + `effective_from` = "<D>T00:00:00Z" (name and date equal) + `staged_change`; its `fitted_from` describes the 11-09 fit, so record the half fit's own `fitted_from` under `staged_change`.

C-F3. Backfill file name / script / cache unclear.
- Plan step 6: "`measure_football_sim.py --stage live_forecasts` (nowy etap), potem `--backfill-out data/line_evidence/football_sim_half_lines.jsonl.gz --backfill-from 2026-10-14 --backfill-to <D-1>`".
- Code: `--backfill-out` exists only in fit_football_sim_curves.py (:426-430); measure_football_sim.py `--stage` choices are inventory/forecast/fit/history/superbet (:1904-1905). `load_live_forecasts` (:323-338) returns the cached `forecasts_live.pkl` unchanged if it exists - data/football_sim_2026-11-06 ends at its 11-06 build.
- Correction: name the command as `fit_football_sim_curves.py --cache-dir <NEW dir> --backfill-out ...`; the new stage writes into a NEW cache dir (never data/football_sim_2026-11-06, which is the installed file's provenance and backs backfill_schedule_term_p). Also restrict the backfill to the half keys (today `day_lines` keeps every `fsm.classify` hit, so the base keys would be written again).

C-F4. The new backfill file is read by nobody.
- Code: `football_sim_curves.load_backfill()` (:174-185) reads only `BACKFILL` = football_sim_lines.jsonl.gz; fit_line_evidence.py:434 calls it without a path; `backfill_rows` takes ONE `switch_day`.
- Correction: load the half file in fit_line_evidence when `football_sim_half(args.before)` (gate it, so the line-evidence config and its `fitted_from.football_sim_backfill` count stay unchanged while off), with `switch_day` = FOOTBALL_SIM_HALF day for those rows. `schedule_term_evidence.sim_lines` (:144-158) passes out-of-scope rows through - OK.

C-F5. Half DC complement needs a second-rung path.
- Plan step 4: "nowe `half_dc_complement`"; DC UNDER = the omitted half result's price.
- Code: one "1.połowa - 1X2" odd is already classified as `result_1h` OVER by `classify_sim_market` (offer.py:241); `classify_odd` returns one rung. The only multi-rung path is `extra` (offer.py:500-505), wired solely to `classify_1x2_dnb` under `result_1x2_dnb`.
- Correction: compute the complement beside `extra` in `OfferFetcher.fetch_offers` (gated by the half flag), add it to the rung list, and delete `result_1h_dc` / `result_2h_dc` rungs whose `over_odds` is None (pattern offer.py:572-575). Byte-identical when off.

C-F6. Selection regex must keep "(K)".
- Data: "Internacional RS (K) (-1.5)", "Flamengo (K) (1.5)".
- Correction: greedy team, anchored last group, e.g. `^(?P<team>.+) \((?P<l>-?\d+\.5)\)$` (the full-match precedent `football_score_markets._HANDICAP_SEL` :108 is exactly this); svb check: home line == svb, away line == -svb. ±3.5 / ±4.5 refused.

C-F7. Tests that will fail and must be updated (not in the plan).
- football_sim_markets.py:84-86 module-level `assert MARKETS == frozenset({9 keys})`; tests/sofa/test_football_sim_wiring.py:424 `fsm.MARKETS == epochs.FOOTBALL_SIM_MARKETS`; tests/sofa/test_schedule_term_replay.py:382 `fsc.staged_paths(...) == [staged 11-09]` (breaks as soon as `.next.<D>.json` is committed).
- tests/sofa/off_scenarios.py `_NEW_MARKERS` (:23-69) must list `football_sim_half_rule`, else test_off_identical_head fails; and run_sheet `AUDIT_MARKER_FIELDS` (:2409) + rebuild_plan marker tuple (:337) + `stamp_marker` list (:4371).

C-F8. Fit the new keys WITHOUT `--schedule-term` (or the EXCLUDED patch) - and never by editing config/sofa_schedule_terms.json.
- Code: `excluded_markets` lives in that config; editing it changes its sha (recorded in the 11-09 sim curves `fitted_from.schedule_term.config_sha256` and the frozen T-SCHEDULE-TERM-FORWARD protocol).
- Correction: the plan's in-code `EXCLUDED |= fsm.MARKETS - SCHEDULE_TERM_MARKETS` is right if `--schedule-term` is used; simpler: fit the 4 keys without the flag (they are uncorrected live), and say so in `staged_change`.

## NOTE

C-N1. Precedent not cited: full-match `result_handicap` (football_score_markets.py:37-41, 179-189, `value_line` :309-312, slice curves "<market>@<subject>@<line>|OVER") is the same market type on the 90 minutes, graded at 0.5 via `value_line` - reuse the pattern (`sim_value` -> indicator, settle at `fsm.LINE`). It left +0.5 out because it equals the DC; the plan keeps +0.5 AND the half DC and relies on SAME_EVENT_DEDUP (higher price wins: handicap 1.35 > DC 1.32 on 17551008). Plan pools lines 0.5/1.5/2.5 and both subjects into one `market|OVER` curve; the precedent chose per-slice curves. Decide consciously.

C-N2. "UNDER only for the margin" vs step 8: `sim_rows` (run_sheet.py:1937-1938) emits UNDER only for `TWO_SIDED`; half keys OVER-only, so the "s@0.5 UNDER ≡ result_Xh other side" identity is moot (keep the test, but no UNDER leg can exist). DC line: say explicitly line = `fsm.LINE` 0.5.

C-N3. Mixed centres. Half keys priced on uncorrected centres while `result_1h` / `htft` use schedule-corrected ones: identical events (handicap s@0.5 OVER ≡ DC; DC 1X vs result_1h "2") carry inconsistent p; and `SimPricer` (football_sim_sheet.py:96-105) re-simulates whenever centres alternate on one event (4,000 sims per switch - SHEET time). Price half rungs with `base_sim_pricer` when it exists.

C-N4. Unmapped not fully emptied: DC "12" and handicap ±3.5/±4.5 odds still return a label -> the market name stays in `unmapped_markets` and `unmapped_prices` (section 1 says the market "znika"). Fine, but the C test "off = unmapped" / "on = mapped" must expect it, and nothing (rebuild_plan) should key off those labels.

C-N5. Price readers: build_slip.py:363-367, capture_closing.py:331-333, verify_legs.py:502, run_offer.py:129 all use `offer.day_flags` - adding `"football_sim_half"` there and an `OfferFetcher` kwarg covers them. `boosts.py:149` calls `classify_odd(item)` with no flags (boost legs never read the new keys - same as today's sim keys). verify_legs `CODE_SUBJECTS` (:99) already holds "1","2","1X","X2". `/kupon` pool requires own sample >= 8 (slip_builder.MIN_SAMPLE) - sim keys have none, so they enter only with `--allow-no-sample` (unconfirmed exact field; same as existing sim keys).

C-N6. F25 / neutral venue: subject codes "1"/"2"/"1X"/"X2" are Superbet's order, graded on Sofascore home/away - same assumption as `result_1h`; the open neutral-venue defect (memory, Godoy Cruz 11-15) applies equally. 2H = `regulation_score - period1` (football_sim_markets.py:315-322), extra time excluded via `normaltime`, HALF_TIME_DISAGREES and HALF_ABOVE_MATCH refusals already in `sim_value` - reuse, no new refusal needed.

C-N7. `fit_football_sim_curves.day_lines` `counter_odds` only for `TWO_SIDED` (:316-320): half handicap backfill rows would carry no margin -> any margin-based measurement (measure_football_sim_floor / _wiring style) of the half keys needs `counter_odds` keyed with the line.

C-N8. Registry: `T-FOOTBALL-HALF-HANDICAP-FORWARD` - check_test_registry REQUIRED fields (:30-31) do not include `evaluation`; fine, but the plan names no evaluation script or thresholds for it (unlike A / B / D).

C-N9. `superbet_words` must write UNDER as the other team "(-L)" and OVER "<team> (L)" with `{line:g}` (no "+"), matching `superbet_names.py:378-379` precedent; `_football_tennis` (:438-440) must pass `line`.

---

## Plan verification - market B (tennis "N+"), HEAD 7585bb54

Scope: `docs/sofa/history/PLAN_NOWE_RYNKI_2026-11-20.md` section 3 plus the parts of 0 / 1 / 6 that concern B. Read-only; no code run beyond reading fixtures.

## Confirmed as the plan says (no action)

- `offer._add_price` is at `src/bet/sofa/offer.py:381-424` and keeps the lower of two quotes for a key and records a collision (`:413-423`). `score_odds` is the model to copy: it lives in its own dict (`:451`, `:564-571`) and is merged only where `combined_odds` lacks the key and `over_odds` is set (`:580-582`).
- Blocked rungs are dropped at `offer.py:556` (`status != "active"`), after classification. The fixture also has blocked "3+" / "2+" rungs at price 1, so the plan is right that it is "not only 1+".
- `run_sheet.py:2994` is `elif rung.market not in samples.metrics: continue`, a silent skip with no gap entry. It runs before the point-model branch (`:3218`), so N+ rungs need the metric in `03_samples`. `samples.metrics_from_offer` (`src/bet/sofa/samples.py:240-266`) builds metrics from 04_offer rungs, so a fresh morning run (OFFER -> SAMPLES) adds them by itself. Only a switch moved into a built day needs rebuild_plan step 6(b).
- `contracts.py:291` is `PricedRung` (`extra="forbid"`, `strict`).
- `epochs._audit_1023_on` is at `epochs.py:3240`.
- `epochs.TENNIS_POINT_MODEL_MARKETS` (`epochs.py:3876-3881`) is {aces, double_faults, serve_points} x {match, set1, set2} x {for, total} plus games_set1/2_total. Every key the classifier can produce is in it. "asy + podwójne błędy" = `serve_points_*` (`market_mapper.py:92`, `:625`). The plan never names this mapping; see B-N1.
- One-sided by construction: `run_confidence.py:410-411` marks any OVER with `under_odds None` as `one_sided_market`. `confidence.one_sided_single` (`confidence.py:489-508`) needs `calibrated_on` to start with `OWN_CURVE_SOURCES = ("market:", "line:")` (`:513`) and `calibration_n >= 300`. The point-model direction curves give source `market:<key>|OVER` (`confidence.py:1482`). Their bucket n is large: aces_total|OVER 0.70-0.75 has n 13,850, double_faults_set1_for|OVER 0.70-0.75 has n 10,932. A line-evidence offset or price-band cap keeps the `market:` prefix (`line_evidence.py:356`, `:376`). So men's N+ legs can pass the one-sided gate.
- Women: a class read returns `f"{klass}:{hit[1]}"` = `tennis_women:market:...` (`confidence.py:1537`), which fails `startswith(("market:", "line:"))`. Operator decision 8 is correctly stated. The same holds for any other tennis class (team cups).
- Point-model rows are out of the tennis pool from a fit for 2026-11-08. `fit_line_evidence.py:95-100` and `:189-190` exclude them by **market name** (`point_priced_markets`). N+ rows share those market names, so they are excluded from the pool whatever their evidence key.
- `fit_line_evidence.py:216` and `run_confidence.py:806` are the evidence-key sites the plan names. `tennis_point_curves.merge_evidence.ours` uses `key.rpartition(":")[2]` (`tennis_point_curves.py:217-218`), so an `n_plus:aces_total|OVER` key, with or without a class prefix, counts as a point-model key and is merged.
- External price readers all build `OfferFetcher(**day_flags(date))`: `run_offer.py:129`, `build_slip.py:365-367`, `capture_closing.py:331-333`, `verify_legs.py:502`. `boosts.py:149` calls `classify_odd(item)` with defaults (off). One new `day_flags` key covers /kupon, closing and verify for tennis.
- The `runs/sofa/2026-11-19/unmapped_prices/20261119T061204.444294Z.jsonl.gz` fixture exists. Event 17537878 has 479 records, among them "Asy" "19+" sbv "19" at 1.25, and "1. set - Nishesh Basavareddy podwójne błędy" "2+" sbv "1-2" at 1.62 (active). Both test examples are correct.
- The bare "Podwójne błędy" with player selections ("kto więcej") exists. 11-10..11-19: 81 such selections, every one with `specialBetValue` None, against 7,420 N+ selections. The plan's "81" is confirmed.
- `run_settle.py` `row_extras` exists (`:1352`, `:1404`, merged at `:1745`). Today it carries only `schedule_term_view.leg_fields`. A reconstructed sheet (`sheet_from_settled`, `:1107-1136`) re-reads the 07_settled dicts, so a field written there survives a re-settle.
- `measure_price_edge.py` has the sha guard the plan cites (`:39-40`, `:738-740`).
- `leg_relations` reads tennis serve relations by metric name (`leg_relations.py:136`, `:182-194`). N+ rows reuse the market names, so builder / slip relations need no change. `leg_identity` has no tennis serve identities, and none are needed: OFFER keeps one rung per (market, subject, line).

## Findings

### B-F1 FIX - routing N+ prices "into a separate dict" cannot go through `classify_odd`
- Plan, step 2: `offer.classify_odd(..., tennis_serve_n_plus=False)` after the `tennis_sets` branch, and `OfferFetcher` with a separate `n_plus_odds`.
- Code: `classify_odd` returns a bare `ClassifiedOdd` tuple (`offer.py:84-102`). `fetch_offers` sends every classified odd to `_add_price` -> `combined_odds` (`:557-563`). Nothing marks a result as N+. Score markets avoid this by being classified outside `classify_odd`, only when it returned nothing (`:527-538`, `scored`).
- Correction: do it as `scored` does. When `classified_odd is None and not extra and not scored`, call `serve_ladder.classify` in `fetch_offers`, put the result in `n_plus_odds`, and clear `unmapped_label`. After the `score_odds` merge (`:580`), merge it only where the key is absent and `over_odds` is set. Leave `classify_odd`'s signature alone, or add a flag there only if `boosts.py` must read N+.

### B-F2 FIX - listing names are not computed unless one of the flags is in the `names = ...` condition
- Plan, step 1: "podmiot ... dokładnie jedna nazwa listingu".
- Code: `offer.py:498-505` computes `names = listing_sides(payload)` only when a listed flag is on, else `()`. Each flag is also gated by sport (`:484-497`, e.g. `set_markets = self.tennis_sets and fixture.sport == "tennis"`).
- Correction: add `n_plus = self.tennis_serve_n_plus and fixture.sport == "tennis"` and put it in the `names` condition. Without it, on a day where `tennis_sets` were off, every player N+ rung would be refused. `tennis_sets` is on today, so this only shows in tests or replays, but it is a latent bug.

### B-F3 FIX - `PricedRung.ladder_format` and `SheetRow.serve_ladder_rule` break "off byte for byte" unless popped when None
- Plan: section 1 (off = 04_offer / 05_sheet byte for byte) and step 4 (`PricedRung.ladder_format`, `SheetRow.serve_ladder_rule`).
- Code: `run_offer.py:178` dumps with `o.model_dump(mode="json")` and no `exclude_none`. `PricedRung` has no serializer. A new `ladder_format: str | None = None` writes `"ladder_format": null` on every rung of every 04_offer. SheetRow optional rules are removed one by one in `run_sheet.sheet_row_json` (`run_sheet.py:2449-2463...`); `model_dump` alone would emit `null`.
- Correction:
  - `PricedRung` gets a `model_serializer(mode="wrap")` that drops `ladder_format` when None, as `PlayerSample` does at `contracts.py:253-262`.
  - `sheet_row_json` pops `serve_ladder_rule` when None.
  - The leg dict in `run_confidence` (`:998-1089`) adds the field only when set (`**({...} if ... else {})`).
  - The 07_settled extra is added only when set.

### B-F4 FIX - `serve_ladder_rule` is a per-row flag, not a sheet marker; do not use `stamp_marker`
- Plan, step 4: "`SheetRow.serve_ladder_rule`", read as the leg's N+ flag (names, evidence key, shadow).
- Code: `stamp_marker` (`run_sheet.py:2438-2446`) writes the rule on **every** row of a sport. rebuild_plan's marker machinery (`rebuild_plan.py:334`, `:402`) assumes those whole-sheet semantics.
- Correction: name it as a per-row field set only on rows priced from an N+ rung (from `rung.ladder_format`). Do not register it in `stamp_marker`, `AUDIT_MARKER_FIELDS` or the rebuild_plan marker tables. The two rebuild triggers in step 6 (offer labels, missing metric) are the right mechanism.

### B-F5 FIX - rebuild_plan 6(a) and day_status step 10 cannot use bare `unmapped_markets` labels
- Plan: step 6(a) re-runs OFFER when "N+" labels are in `unmapped_markets` with the switch on; step 10 WARNs on such labels.
- Code: `unmapped_markets` holds market names only (`offer.py:542-543`), never selections. "Podwójne błędy" is also the "kto więcej" market (81 selections with sbv None, confirmed above). It stays unmapped after OFFER re-reads, so 6(a) would add an OFFER step to **every** rebuild and fail its own "idempotent" test. Player-name mismatches that the classifier correctly refuses would also stay as labels and WARN every day.
- Correction:
  - 6(a): detect "switch on, OFFER read before it" from the 04_offer rungs, i.e. any tennis rung with `ladder_format == "n_plus"`, the way `offer_has_sim` / `offer_has_score` work (`rebuild_plan.py:603`, `:734-742`). Only when none exists and the switch is on, re-run OFFER once.
  - day_status: read today's `unmapped_prices/*.jsonl.gz`, and WARN only on records whose `name` matches `^\d+\+$` and whose market matches the N+ templates, above a share threshold. Not on labels.

### B-F6 FIX - line-evidence backfill has no reader in the plan
- Plan, step 7: `backfill_serve_n_plus_lines.py --from 2026-10-20` -> `data/line_evidence/tennis_serve_n_plus_lines.jsonl.gz`.
- Code: `fit_line_evidence.py` reads only `07_settled.json` through `sheet_rows`, plus fixed backfills: `tennis_point_curves.load_backfill` (a `{key: p}` map that **needs a 07_settled row**, `:410-419`, `tennis_point_curves.py:192-208`), and `football_sim_curves.backfill_rows` for full lines (`:427-446`). N+ lines before the switch were never sheet or settled rows (they sat in unmapped_prices). A p-only backfill like the point model's would therefore yield nothing.
- Correction: the backfill must hold full lines (day, eid, key, subject, line, OVER, point-model p as of the start, WIN/LOSS from cached /statistics, Superbet price), like `football_sim_lines.jsonl.gz`. Add a reader in `fit_line_evidence` (`le.fit([*backfill_rows, *n_plus sheet_rows])`, merged through `tennis_point_curves.merge_evidence`) and a test.
- The backfill has to price every N+ line with the point model as of each match. That is a new pricing pass, not a replay of sheets, which were deleted 11-19 anyway. Budget for it. `unmapped_prices` exist from 2026-10-14 only (from 10-20 is fine).

### B-F7 FIX - the forward-test verdicts overlap
- Plan: PASSED = lower M1 >= -0.05 and M2 >= -0.05 and lower M3 > 0. FAILED = upper M1 < -0.03 or upper M2 < -0.05.
- Problem: an M1 interval like [-0.045, -0.035] is both PASSED-eligible (lower >= -0.05) and FAILED (upper < -0.03). "M2 >= -0.05" does not say point estimate or bound, and "ROI po kursie" does not say before or after the 12% tax.
- Correction: give an explicit evaluation order (FAILED checked first). State whether M2 is a point estimate or a bound, and whether it is before or after tax. Freeze all of this in `PROTOCOL.md`.

### B-F8 FIX - template count in the tests
- Plan, tests: "12 szablonów -> klucze".
- Fixture: there are 18 templates = {match, 1. set, 2. set} x {asy, podwójne błędy, asy + podwójne błędy} x {total, player}. All 18 occur for event 17537878.
- Correction: test all 18, including the serve_points (`asy + podwójne błędy`) mapping and the lowercase set-total names ("1. set - asy").

### B-N1 NOTE - the plan never says that "asy + podwójne błędy" maps to `serve_points_*`
It is implied by "klucz musi należeć do TENNIS_POINT_MODEL_MARKETS". State it in `serve_ladder.py`'s table, matching `market_mapper.py:92` / `:625`.

### B-N2 NOTE - `parse_line` takes the market key
- Plan: `offer.parse_line(sbv)`, "prefiks S-".
- Code: the signature is `parse_line(raw_line, market)` (`offer.py:36`). The scope check reads "set1" / "set2" from the key (`:63-75`), and an unscoped key with a prefix raises. The prefix is the set number ("1-7"), not literally "S-".
- Correction: classify the key first, then call `parse_line(sbv, key)`.

### B-N3 NOTE - the `n_plus:` evidence key starts from the tennis estimator pool's offset
- Code: a key with no own lines reads the price-gap offset fully shrunk to `sport_printable_by_gap["tennis"]` (`line_evidence.py:253-269`; n = 0 means the pool gap). From 11-08 that pool is the **estimator-priced** tennis rows (point-model rows excluded), not point-model lines. The pool is "clean", but it measures another estimator's miscalibration.
- Correction: say so in the report and in model-state.md (b). Optionally fall back to the point-model key's own entry (`aces_total|OVER`) before the pool. That is a design decision; state it either way.
- The class prefix order must also be fixed: `evidence_key` prepends the class (`line_evidence.py:167-169`), giving `tennis_women:n_plus:...`. `merge_evidence.ours` handles both orders, but CONFIDENCE and the fit must build it identically.

### B-N4 NOTE - mixing N+ rungs into an existing (market, subject) ladder
- Code: `run_sheet.py:2917` (`ladder_rungs`) and the ladder-sigma / NO_PRICE_ANCHOR verdict notes (`:3600-3640`) read every rung of the same (market, subject). The point model sets p and centre for these keys (`:3218-3240`), so p_central should not move. Verdicts and notes of existing two-sided rows can.
- Unconfirmed whether anything printed reads them in stats-only mode. The E2E check "legs bez zmian" should diff existing 05_sheet rows field by field (p_central, centre, notes, verdict), not only count legs.

### B-N5 NOTE - registered or proposed tests whose population grows
- T-TENNIS-DF-UNDER-FORWARD (NOT_PASSED, `measure_tennis_df_under_forward.py`; "sheet coverage" of double-faults lines) and the PROPOSED T-TENNIS-SERVE-MARKET-LINE / T-TENNIS-ACES-SETS-EXPOSURE define their population as "fixtures Superbet quotes serve markets on".
- Under the shadow switch the N+ rows land in 04_offer / 05_sheet / 07_settled under the same market names, which adds Challenger / WTA 125 fixtures. T-TENNIS-STEP-UP-FAVOURED reads 08_confidence legs (affected only at print).
- Decide and record in the registry: exclude rows with `serve_ladder_rule`, or say the population changed.

### B-N6 NOTE - `superbet_names` must reproduce the screen's casing per scope
Screen names (fixture): "Asy", "Podwójne błędy", "Asy + podwójne błędy" (match total); "<gracz> asy"; "1. set - asy" (set total, lowercase); "1. set - <gracz> asy + podwójne błędy". The selection is "19+". Today's table (`superbet_names.py:86-144`) is the two-sided "liczba asów" format. The N+ branch must be chosen by the leg's flag, since the market key is the same.

### B-N7 NOTE - `market_coverage` works on market names only
`classify_market_name` matches the name template (`market_coverage.py:564-566`). The bare template "podwojne bledy" is shared by N+ and "kto więcej" and is today `tn.double_faults_unknown_shape` (`:413-415`). The new `tn.serve_n_plus` rule cannot separate them by name. Document that, or classify with the selection where `_reader_reads` sees items.

### B-N8 NOTE - shadow jsonl written by CONFIDENCE
`run_confidence` today writes no append-only per-day file. Every rebuild re-runs CONFIDENCE and appends. Make sure E2E and tests point `SOFA_RUNS_DIR` at scratch (the plan does), and that `rebuild_day --dry-run` never appends. Unconfirmed whether any md5 / artifact guard lists the day's files.

### B-N9 NOTE - commit-order labels collide with the market letters
"Kolejność commitów: A kod ... -> E2E -> C zamrożenie" reuses A / C, which in this plan name hockey / football, and there is no "B". "D0" is undefined. Rename the steps (B1 code, B2 E2E, B3 freeze, B4 evaluation, B5 print decision) and define D0 as the day of the freeze commit.

### B-N10 NOTE - `day_flags` is by date only
`offer.day_flags(date)` (`offer.py:262-283`) has no build clock, like every existing OFFER flag. The shadow switch is honoured in OFFER by day only. CONFIDENCE (`TENNIS_SERVE_N_PLUS_PRINT`) can use the clock. That is fine at 00:00Z; say it in the epochs comment.

### B-N11 NOTE - unconfirmed claims
- "0 SAMPLES requests": SAMPLES fetches `/event/{id}/statistics` for every historical event regardless of metric (`samples.py:1101-1104`), so the suspicion is plausible. Confirm with the counter, as the plan says.
- Point-model coverage of Challenger / WTA 125 players (NOT_RATED share) was not checked.

## Section 0 / 1 / 6 items for B
- Decision 8 (women never print) is confirmed in code.
- Section 1, "czytelnicy ceny poza pipeline'em": for tennis it is automatic through `day_flags` (confirmed). No per-reader edit is needed beyond the `day_flags` key and the `OfferFetcher` parameter.
- Section 6, criterion 3 (staged curve file differs only by new keys): not applicable to B, since no curves change. Criterion 2 needs B-F3.
# Plan verification - A (hockey NHL 617 / 613 / 621 / 653, "z dogrywką i rzutami karnymi")

Plan: `docs/sofa/history/PLAN_NOWE_RYNKI_2026-11-20.md` section 2 (+ 0 / 1 / 6 where they concern A).
Code: `main` 7585bb54. Read-only check: no file changed, nothing run against live data.

## Claims confirmed in the code

| claim | code |
|---|---|
| `_hockey` adds one goal to the OT / shootout winner on a level score, `hk_ot_strength` 0.5 | `src/bet/sofa/score_model.py:1117-1129`, `:614-616` |
| `build_result` allows a shootout winner's `current` without the +1 (`{reg+ot, reg+ot+1}`) | `src/bet/sofa/shadow.py:1255-1277` (also `_final_only_result` :1107-1112) |
| `leg_relations._shadow_spec` searches only `MARKETS` / `DERIVED_MARKETS` | `src/bet/sofa/leg_relations.py:459-469` |
| `fit_sport_confidence.py` without `--out` writes the installed file | `scripts/sofa/fit_sport_confidence.py:545-546, 565, 612` |
| sport scripts read the DB from `SOFA_DB_PATH`, no `--db-path` | `src/bet/sofa/config.py:132`; `fit_sport_confidence.py:575` uses `config.db_path` |
| `BASKETBALL_PLAYER_V2` pattern | `src/bet/sofa/epochs.py:2268-2280` |
| `_audit_1023_on` | `src/bet/sofa/epochs.py:3240-3245` |
| `audit_ledger.EPOCH_GROUPS` :148, `epoch_group` top branch :328 | `scripts/sofa/audit_ledger.py:148-154, 327-331` |
| `run_shadow.py:210-226`, `build_slip.py:244-247` are the two `parse_event` callers | confirmed; `build_slip._same_line` (:197-209) compares `market_id`, so 604 / 613 do not collide there |
| 613@|h|>=1.5 dedups with 604@h already through family `handicap` | `src/bet/sofa/leg_identity.py:199-260`: family `handicap`, period 0 -> scope "reg", margin key; the key is by family, not market_id |
| `.next.2026-11-07.json` is the latest staged sport calibration | `config/`: `.next.json` (10-14), `.next.2026-10-24`, `.next.2026-10-28`, `.next.2026-11-06`, `.next.2026-11-07`; nothing later. `calibration_path_for` (`sport_confidence.py:119-135`) picks the latest `effective_from` <= day and refuses a file name / `effective_from` mismatch. A copy of 11-07 + 4 keys is the full set: no later file has keys to miss |
| no existing switch after 2026-11-19 | `epochs.py`: newest dated are `STAKES_GROUPS_FROM_UTC` 11-19 and `STABILITY_LABEL_FROM_UTC` 11-16; neither touches hockey. A 2026-11-22 00:00Z switch interacts with no switch or staged file |
| 613 names are "Team (h)" with no "+", sbv = team1's handicap | unmapped 11-1x: "Edmonton Oilers (1.5)" / sbv 1.5, "New York Islanders (-1.5)" / sbv 1.5 - fits `_HCP_IN_NAME` (`shadow.py:637`) and the check at :771-776 |

## Findings

### A1. FIX (high) - the verifier and audit U3 would flag every new leg
- **Plan:** section 1 says `verify_legs.py` gets the flag "przez `offer.day_flags` dla piłki / tenisa; dla sportów przez `parse_event`". Section 2 step 4 names only `run_sport_confidence.build_sport`.
- **Code:** for sports, `verify_legs.py` does not call `parse_event`. It re-checks each leg's family with its own `family_of` closure (`scripts/sofa/verify_legs.py:404-413`, used at :456-460). If the family is not allowed, the leg gets `DEFECT "family ... not allowed"`. `scripts/sofa/audit_variants.py:435-447` (`confidence_family`, U3 `audit_sport_legs`) calls `rsc._allowed(sport, line, evidence_on, derived, series_rounds)` with no new flag.
- **Effect:** without the flag, every printed 617 / 621 / 653 leg is a sport_market DEFECT for the verifier (`/sofa-verify` can turn that into a removal read) and "not in the snapshot" for audit U3.
- **Fix:** add the `ot_so` parameter to `scf.family_of` / `allowed_markets` / `rsc._allowed`. Pass `epochs.hk_ot_so_markets(date, at)` in all three places: `run_sport_confidence.py:530-538` and :588, `verify_legs.py:404-413`, `audit_variants.py:445-447`. Add a test for each.

### A2. FIX - no real payload of these markets exists, so the parser is untested
- **Plan:** test "parsowanie prawdziwego payloadu NHL". Step 2 reuses `parse_line` (totals from `specifiers["total"]`, handicap from `specifiers["hcp"]`, plus the `code` / name check).
- **Code:** `unmapped_prices.FIELDS` (`src/bet/sofa/unmapped_prices.py:37-41`) stores only marketName / name / specialBetValue / price / status / marketId. It keeps no `specifiers`, `code` or `info`. The golden payload `tests/sofa/golden/superbet_hockey_double_chance_2026-10-13.json` was trimmed to 606/616/623/630/640/660. The measurement never ran `parse_line` on these markets: `s08_checks.py` builds the `ShadowLine`s by hand. The report says the 617 `info` was never seen.
- **Effect:** if 617 / 621 / 653 carry the line under a key other than `total`, or 613 under one other than `hcp`, every line is dropped silently (`value is None` -> None, `shadow.py:767-768`). Nothing would fail and nothing would print.
- **Fix:** step 0 of A captures one live NHL `/events/{id}` payload into `tests/sofa/golden/` and checks the specifier keys and codes. Otherwise read the line from `specialBetValue` as a fallback, and say so in the plan. The off-equals-today test cannot catch this.

### A3. FIX - the four new keys must be registered as new-market curves, or a later refit drops them
- **Plan:** step 5 composes `.next.<D>.json` = copy of 11-07 + 4 keys + `staged_change`.
- **Code:** `fit_sport_confidence.py` replaces a sport's whole section (`:577-582`). It keeps only the keys listed in the top-level `new_market_curves_fitted_from`, through `fit_meta.carry_sport_new_market_curves` (`src/bet/sofa/fit_meta.py:186-212`).
- **Effect:** a later hockey refit without `--hk-ot-so` scores only `HISTORY_MARKETS` and silently drops `total_ot|*` / `team_total_ot|*`. Those legs would then read NO_LINE_EVIDENCE.
- **Fix:** add `"hockey:total_ot|OVER"` etc. to `new_market_curves_fitted_from`, with their `fitted_from` (script, flags, DB copy, competitions filter, window). Or make `--hk-ot-so` default to "auto" by the `--before` day's switch, as `--hk-late-in-mean` does with `switch_mode` (:529-533, :226-227). Then a refit for a day at or after D scores them itself.

### A4. FIX - name the compose script, and do not use `install_new_market_curves.py`
- **Plan:** "skrypt składa `config/sofa_sport_confidence_calibration.next.<D>.json`" - no script is named. Acceptance criterion 3 says "differs only by the new keys".
- **Code:** the existing tool `scripts/sofa/install_new_market_curves.py` merges a sport group into the installed file and into every staged `.next*.json` (header lines 13-19; tests `test_every_dated_staged_sport_file_is_merged_too`). That edits files read by days already built, which CLAUDE.md forbids.
- **Fix:**
  - Write a dedicated compose step (or a `--target-file` mode) that touches only the new dated file.
  - The diff test must allow exactly: `effective_from`, `staged_change`, `new_market_curves_fitted_from` (+4), and in `sports.hockey` the dicts `curves` (+4) and `curve_source` (+4).
  - Decide whether to touch `admitted` / `not_calibrated` / `oos`. With line evidence on they are not read: `lookup(require_admitted=False)` (`sport_confidence.py:601-612`).

### A5. FIX - `--hk-ot-so` / `--markets` do not exist; the fit needs four code changes
- **Plan:** `fit_sport_confidence.py --hk-ot-so on --markets 617,621,653 --out ...`
- **Code:** neither flag exists (`fit_sport_confidence.py:464-556`). `score_game` / `walk_forward_rows` take `markets=` (`sport_confidence.py:1014-1025, 1096-1110`), but `fit_sport` does not pass it (:292-304). Lines come from `LINE_QUANTILES` (`synthetic_lines` :860-931), not a fixed ladder. Thinning is `step = len(window) // max_games` over every competition (:1160-1161). No competition filter exists.
- **Fix:** list the four changes explicitly:
  - pass `markets` through to the fit;
  - a fixed line ladder for the `incl` families;
  - a competition filter for scoring (ratings still learn from every league);
  - no thinning for the filtered competitions.

  Keep `HISTORY_MARKETS` unchanged when the flag is off. `refresh_line_evidence.py` runs `fit_sport_confidence --dry-run --rows-out` every morning (`refresh_line_evidence.py:133-134`): a history scoring that is always on adds unthinned NHL rows to that run and changes its outputs.

### A6. FIX - 604 / 613 key collision: drop the line, do not assert
- **Plan:** step 7, "asercja rozłączności 604 / 613 albo `market_id` w kluczu".
- **Code:** these keys have no `market_id`:
  - `fit_line_evidence.graded_odds` (`scripts/sofa/fit_line_evidence.py:259-280`);
  - `coupon_sports.sport_key` (`src/bet/sofa/coupon_sports.py:138-147`, also used by `apply_reads`);
  - `locked_print.leg_key` (`src/bet/sofa/locked_print.py:64-86`);
  - `priced_view.leg_key` (:54-63), `read_set.leg_key` (`scripts/sofa/read_set.py:145`), `prepare_refit.leg_key`.

  Today Superbet does not quote 604 for NHL (report section 1), so the two never meet.
- **Fix:** an assertion in a live stage would crash SPORT_CONFIDENCE or COUPON on the first day both are quoted. Instead, in `parse_event` (hockey, under the switch), drop a 613 side when 604 quotes the same (line, side): the two are the same event. Test it. Adding `market_id` to `locked_print.leg_key` would break every stored key ("every stored key still reads", :72-73), so avoid it.

### A7. FIX - the `incl` rule for a `final_only` game is not specified
- **Plan:** step 2, "`final_only` analogicznie".
- **Code:** `_pair`'s final_only branch (`shadow.py:1307-1314`) returns `t1_full` / `t2_full` (Sofascore `current`) for "full" and `reg_score` for "reg". For an AP game, `current` may lack the shootout +1 (`_final_only_result` :1107-1112 allows it).
- **Fix:** state the rule and test it:
  - incl = (t1_full, t2_full) when they differ;
  - when they are level and `winner` is set, +1 to the winner;
  - when they are level and `winner` is None (a regulation draw, Ended), the level score as it stands.

  Same for the period path: sum of periods, +1 to `winner` when `overtime`.

  `sport_day.grade_leg` (`src/bet/sofa/sport_day.py:274-312`) rebuilds `GameResult` from settled.json (`t1_periods`, `t1_full`, winner, overtime). The new branch in `_pair` covers the ledger only if it reads nothing that is not stored there. It does not: periods, winner and overtime are all stored.

### A8. NOTE - ±0.5 on 613 must be refused (a correctness need, not only taste)
- `leg_identity._margin_wins` reads family `handicap` as a regulation margin. A 613 +0.5 T1 leg would get the key d >= 0, the same as `double_chance` 606 "1X". These are different events: 606 is regulation, 613 +0.5 is the OT/SO winner. SAME_EVENT_DEDUP would then drop one of them wrongly.
- The plan's "613 ±0,5 -> None" prevents this. Keep that test, and add a leg_identity test that 613 never shares a key with 606 / 640 / 630.

### A9. NOTE - leg_identity total vectors: half-point lines only, and keep today's families unchanged
- **Plan:** step 6, a score-state vector for `total` / `total_ot` / `team_total` / `team_total_ot`.
- Today hockey has only margin keys (`leg_identity.py:327-337`). A new total key would also cover 623 / 658 / 652, which print today.
- Restrict it to half-point lines, as `_margin_wins` already does (`line != int(line)`, :232).
- Add a test that no existing hockey leg pair on a replayed day gets a new shared key (byte-identical when off). The identity 617@odd k ≡ 623@k holds by logic and by the report's 9447/9447 pairs.

### A10. NOTE - leg_relations: add `incl` to `_shadow_period` and the new table to `mapped_sport_markets`
- `_shadow_period("hockey", "incl", 0)` would today return `{"P0"}`: the fallback, `leg_relations.py:438-441`. Map `incl` to `_HOCKEY_REG | {"OT"}`, as "full" already is.
- `_shadow_spec(sport, "handicap")` returns 604's spec ("reg") for 613. That is correct for |h| >= 1.5.
- `mapped_sport_markets` (`leg_relations.py:785-796`) iterates only `MARKETS` / `PLAYER_MARKETS`. Add the new table, or `tests/sofa/test_leg_relations.py:86-108` will not cover `total_ot` / `team_total_ot`.

### A11. NOTE - `market_coverage`: the note exists but its text is stale
- `hk.ot_so_scope` already exists (`src/bet/sofa/market_coverage.py:479-482`). Its text says "model wyniku liczy czas regulaminowy".
- `_reader_reads` (:848-874) knows only `MARKETS` ∪ `PLAYER_MARKETS`; it does not know DERIVED either.
- Under the switch, add the new table to `known` and update or retire the note.

### A12. NOTE - the 613 curve key pools regulation ±0.5 rows
- 613 reads `handicap|TEAM`. That curve is fitted on regulation-handicap lines at `LINE_QUANTILES`, ±0.5 included, which is exactly where the draw error (-5.3 pp) sits.
- 613 is offered only at |h| >= 1.5. A curve bucket mixes both kinds of row. Not a misgrade; report the 613 hold-out separately.

### A13. NOTE - shootout counted as one goal in 621 / 653: unconfirmed for Superbet's line settlement
- The report proves that Superbet's final-score metadata counts the shootout as +1 for the winner (Vegas - Dallas 3/4). It does not prove that Superbet settles 621 / 653 / 617 lines that way: we hold no Superbet grade of a line.
- Standard bookmaker practice agrees. Mark it unconfirmed until the first settled AP game is checked against Superbet's settled bet history, and put that in the E2E list.

### A14. NOTE - registered forward tests whose population grows
- These tests take all measured-sport or all coupon legs: T-SPORT-LATE-WINDOW, T-A4-bucket-deff, T-LESSER-LOSS-flag, T-TOP-BAND-090-after-price-gap-offset, T-KUPON-PRICE-RISE-DROP, T-STABILITY-LABEL-FORWARD (`config/sofa_test_registry.json`). About 44 NHL legs a day would join them.
- The plan raises this only for VB (`T-PRICE-EDGE-VB-RAW-FORWARD`). Either name them for A too, or exclude `hk_ot_so_rule` legs from them.

### A15. NOTE - test registry timing
- `check_test_registry.py:68-77` refuses a test whose `data_window.from` is <= `registered_on`. Register `T-HK-OT-SO-calibration` no later than D-1.
- The `evaluation` field must name a script that exists (:62-66). The plan names none for A.

### A16. NOTE - naming clash
- The plan uses the identifier `HK_OT_SO_MARKETS` twice: for the epochs switch name (step 1) and for the shadow table (step 2).
- Rename one, e.g. the table `HK_OT_SO_SPECS`, to avoid import confusion.

### A17. NOTE - smaller wiring the plan leaves implicit
- `spec_of` (`shadow.py:365-371`) must include the new table. Without it, history, settle, `sport_day.grade_leg` and `sample_hit_rate` all return None: UNGRADEABLE, not a misgrade.
- `group_shape` -> "two" for the new kinds is already right.
- `superbet_names.SPORT_MARKETS["hockey"]` entries:
  - 617 "Liczba goli (z dogrywką i rzutami karnymi)" / ou;
  - 621 "{T1} - liczba goli (z dogrywką i rzutami karnymi)" / ou;
  - 653 "{T2} - ..." / ou;
  - 613 "Handicap (z dogrywką i rzutami karnymi)" / hcp.
- `run_sport_confidence.py:766-800`: add the `hk_ot_so_rule` leg marker beside `derived_rule` / `player_v2_rule`.
- `docs/sofa/MODELE_HOKEJ_KOSZ_SIATKA.md` (listed for D) should get the hockey scope too, as should `.claude/skills/sport-analysis` (agents do not read CLAUDE.md).

### A18. NOTE - switch-day mechanics (checked, no conflict)
- On D, snapshots fetched before 00:00Z carry no 617. The 04:30Z loop snapshot replaces the record whole (`latest_pre_kickoff`).
- `settled_shadow_rows` gates by the settled file's day (`sport_confidence.py:1257-1258` pattern). D-1's late-window NHL games (D 00:00-05:00Z) can carry 617 lines in D's file. They are still refused on D-1's coupon (family gated by D-1) and graded only as SHADOW_SETTLE rows of D: correct.

## Byte-identical-when-off

Feasible:
- `parse_line` / `parse_event` / `reads_market` default `ot_so=False`.
- The `spec_of` / `_pair` / `_shadow_spec` additions are unreachable without lines.
- `settled_shadow_rows`, `allowed_markets` and `settled_only_families` stay unchanged while their gate is off.

Risks: A9 (leg_identity keys on existing families) and A5 (history scoring in the daily refresh dry-run). Both need gating or a replay test.

## Contradictions within the plan

- Section 1 says `verify_legs` gets the flag "dla sportów przez `parse_event`"; the code reads families instead (A1).
- Step 5 / acceptance 3 "differs only by 4 keys" cannot hold literally: `curve_source`, `effective_from`, `staged_change` and `new_market_curves_fitted_from` must change too (A3 / A4).
- The measurement graded with scope "full" (`t1_full`, 4020/4020). The plan grades `incl` from the periods. The plan is the safer rule (A7), but the 4020/4020 figure does not validate the new branch: re-run that check on the new branch.
# Plan verification - market B (tennis "N+"), HEAD 7585bb54

Scope: `docs/sofa/history/PLAN_NOWE_RYNKI_2026-11-20.md` section 3 plus the parts of 0 / 1 / 6 that concern B. Read-only; no code run beyond reading fixtures.

## Confirmed as the plan says (no action)

- `offer._add_price` is at `src/bet/sofa/offer.py:381-424` and keeps the lower of two quotes for a key and records a collision (`:413-423`). `score_odds` is the model to copy: it lives in its own dict (`:451`, `:564-571`) and is merged only where `combined_odds` lacks the key and `over_odds` is set (`:580-582`).
- Blocked rungs are dropped at `offer.py:556` (`status != "active"`), after classification. The fixture also has blocked "3+" / "2+" rungs at price 1, so the plan is right that it is "not only 1+".
- `run_sheet.py:2994` is `elif rung.market not in samples.metrics: continue`, a silent skip with no gap entry. It runs before the point-model branch (`:3218`), so N+ rungs need the metric in `03_samples`. `samples.metrics_from_offer` (`src/bet/sofa/samples.py:240-266`) builds metrics from 04_offer rungs, so a fresh morning run (OFFER -> SAMPLES) adds them by itself. Only a switch moved into a built day needs rebuild_plan step 6(b).
- `contracts.py:291` is `PricedRung` (`extra="forbid"`, `strict`).
- `epochs._audit_1023_on` is at `epochs.py:3240`.
- `epochs.TENNIS_POINT_MODEL_MARKETS` (`epochs.py:3876-3881`) is {aces, double_faults, serve_points} x {match, set1, set2} x {for, total} plus games_set1/2_total. Every key the classifier can produce is in it. "asy + podwójne błędy" = `serve_points_*` (`market_mapper.py:92`, `:625`). The plan never names this mapping; see B-N1.
- One-sided by construction: `run_confidence.py:410-411` marks any OVER with `under_odds None` as `one_sided_market`. `confidence.one_sided_single` (`confidence.py:489-508`) needs `calibrated_on` to start with `OWN_CURVE_SOURCES = ("market:", "line:")` (`:513`) and `calibration_n >= 300`. The point-model direction curves give source `market:<key>|OVER` (`confidence.py:1482`). Their bucket n is large: aces_total|OVER 0.70-0.75 has n 13,850, double_faults_set1_for|OVER 0.70-0.75 has n 10,932. A line-evidence offset or price-band cap keeps the `market:` prefix (`line_evidence.py:356`, `:376`). So men's N+ legs can pass the one-sided gate.
- Women: a class read returns `f"{klass}:{hit[1]}"` = `tennis_women:market:...` (`confidence.py:1537`), which fails `startswith(("market:", "line:"))`. Operator decision 8 is correctly stated. The same holds for any other tennis class (team cups).
- Point-model rows are out of the tennis pool from a fit for 2026-11-08. `fit_line_evidence.py:95-100` and `:189-190` exclude them by **market name** (`point_priced_markets`). N+ rows share those market names, so they are excluded from the pool whatever their evidence key.
- `fit_line_evidence.py:216` and `run_confidence.py:806` are the evidence-key sites the plan names. `tennis_point_curves.merge_evidence.ours` uses `key.rpartition(":")[2]` (`tennis_point_curves.py:217-218`), so an `n_plus:aces_total|OVER` key, with or without a class prefix, counts as a point-model key and is merged.
- External price readers all build `OfferFetcher(**day_flags(date))`: `run_offer.py:129`, `build_slip.py:365-367`, `capture_closing.py:331-333`, `verify_legs.py:502`. `boosts.py:149` calls `classify_odd(item)` with defaults (off). One new `day_flags` key covers /kupon, closing and verify for tennis.
- The `runs/sofa/2026-11-19/unmapped_prices/20261119T061204.444294Z.jsonl.gz` fixture exists. Event 17537878 has 479 records, among them "Asy" "19+" sbv "19" at 1.25, and "1. set - Nishesh Basavareddy podwójne błędy" "2+" sbv "1-2" at 1.62 (active). Both test examples are correct.
- The bare "Podwójne błędy" with player selections ("kto więcej") exists. 11-10..11-19: 81 such selections, every one with `specialBetValue` None, against 7,420 N+ selections. The plan's "81" is confirmed.
- `run_settle.py` `row_extras` exists (`:1352`, `:1404`, merged at `:1745`). Today it carries only `schedule_term_view.leg_fields`. A reconstructed sheet (`sheet_from_settled`, `:1107-1136`) re-reads the 07_settled dicts, so a field written there survives a re-settle.
- `measure_price_edge.py` has the sha guard the plan cites (`:39-40`, `:738-740`).
- `leg_relations` reads tennis serve relations by metric name (`leg_relations.py:136`, `:182-194`). N+ rows reuse the market names, so builder / slip relations need no change. `leg_identity` has no tennis serve identities, and none are needed: OFFER keeps one rung per (market, subject, line).

## Findings

### B-F1 FIX - routing N+ prices "into a separate dict" cannot go through `classify_odd`
- Plan, step 2: `offer.classify_odd(..., tennis_serve_n_plus=False)` after the `tennis_sets` branch, and `OfferFetcher` with a separate `n_plus_odds`.
- Code: `classify_odd` returns a bare `ClassifiedOdd` tuple (`offer.py:84-102`). `fetch_offers` sends every classified odd to `_add_price` -> `combined_odds` (`:557-563`). Nothing marks a result as N+. Score markets avoid this by being classified outside `classify_odd`, only when it returned nothing (`:527-538`, `scored`).
- Correction: do it as `scored` does. When `classified_odd is None and not extra and not scored`, call `serve_ladder.classify` in `fetch_offers`, put the result in `n_plus_odds`, and clear `unmapped_label`. After the `score_odds` merge (`:580`), merge it only where the key is absent and `over_odds` is set. Leave `classify_odd`'s signature alone, or add a flag there only if `boosts.py` must read N+.

### B-F2 FIX - listing names are not computed unless one of the flags is in the `names = ...` condition
- Plan, step 1: "podmiot ... dokładnie jedna nazwa listingu".
- Code: `offer.py:498-505` computes `names = listing_sides(payload)` only when a listed flag is on, else `()`. Each flag is also gated by sport (`:484-497`, e.g. `set_markets = self.tennis_sets and fixture.sport == "tennis"`).
- Correction: add `n_plus = self.tennis_serve_n_plus and fixture.sport == "tennis"` and put it in the `names` condition. Without it, on a day where `tennis_sets` were off, every player N+ rung would be refused. `tennis_sets` is on today, so this only shows in tests or replays, but it is a latent bug.

### B-F3 FIX - `PricedRung.ladder_format` and `SheetRow.serve_ladder_rule` break "off byte for byte" unless popped when None
- Plan: section 1 (off = 04_offer / 05_sheet byte for byte) and step 4 (`PricedRung.ladder_format`, `SheetRow.serve_ladder_rule`).
- Code: `run_offer.py:178` dumps with `o.model_dump(mode="json")` and no `exclude_none`. `PricedRung` has no serializer. A new `ladder_format: str | None = None` writes `"ladder_format": null` on every rung of every 04_offer. SheetRow optional rules are removed one by one in `run_sheet.sheet_row_json` (`run_sheet.py:2449-2463...`); `model_dump` alone would emit `null`.
- Correction:
  - `PricedRung` gets a `model_serializer(mode="wrap")` that drops `ladder_format` when None, as `PlayerSample` does at `contracts.py:253-262`.
  - `sheet_row_json` pops `serve_ladder_rule` when None.
  - The leg dict in `run_confidence` (`:998-1089`) adds the field only when set (`**({...} if ... else {})`).
  - The 07_settled extra is added only when set.

### B-F4 FIX - `serve_ladder_rule` is a per-row flag, not a sheet marker; do not use `stamp_marker`
- Plan, step 4: "`SheetRow.serve_ladder_rule`", read as the leg's N+ flag (names, evidence key, shadow).
- Code: `stamp_marker` (`run_sheet.py:2438-2446`) writes the rule on **every** row of a sport. rebuild_plan's marker machinery (`rebuild_plan.py:334`, `:402`) assumes those whole-sheet semantics.
- Correction: name it as a per-row field set only on rows priced from an N+ rung (from `rung.ladder_format`). Do not register it in `stamp_marker`, `AUDIT_MARKER_FIELDS` or the rebuild_plan marker tables. The two rebuild triggers in step 6 (offer labels, missing metric) are the right mechanism.

### B-F5 FIX - rebuild_plan 6(a) and day_status step 10 cannot use bare `unmapped_markets` labels
- Plan: step 6(a) re-runs OFFER when "N+" labels are in `unmapped_markets` with the switch on; step 10 WARNs on such labels.
- Code: `unmapped_markets` holds market names only (`offer.py:542-543`), never selections. "Podwójne błędy" is also the "kto więcej" market (81 selections with sbv None, confirmed above). It stays unmapped after OFFER re-reads, so 6(a) would add an OFFER step to **every** rebuild and fail its own "idempotent" test. Player-name mismatches that the classifier correctly refuses would also stay as labels and WARN every day.
- Correction:
  - 6(a): detect "switch on, OFFER read before it" from the 04_offer rungs, i.e. any tennis rung with `ladder_format == "n_plus"`, the way `offer_has_sim` / `offer_has_score` work (`rebuild_plan.py:603`, `:734-742`). Only when none exists and the switch is on, re-run OFFER once.
  - day_status: read today's `unmapped_prices/*.jsonl.gz`, and WARN only on records whose `name` matches `^\d+\+$` and whose market matches the N+ templates, above a share threshold. Not on labels.

### B-F6 FIX - line-evidence backfill has no reader in the plan
- Plan, step 7: `backfill_serve_n_plus_lines.py --from 2026-10-20` -> `data/line_evidence/tennis_serve_n_plus_lines.jsonl.gz`.
- Code: `fit_line_evidence.py` reads only `07_settled.json` through `sheet_rows`, plus fixed backfills: `tennis_point_curves.load_backfill` (a `{key: p}` map that **needs a 07_settled row**, `:410-419`, `tennis_point_curves.py:192-208`), and `football_sim_curves.backfill_rows` for full lines (`:427-446`). N+ lines before the switch were never sheet or settled rows (they sat in unmapped_prices). A p-only backfill like the point model's would therefore yield nothing.
- Correction: the backfill must hold full lines (day, eid, key, subject, line, OVER, point-model p as of the start, WIN/LOSS from cached /statistics, Superbet price), like `football_sim_lines.jsonl.gz`. Add a reader in `fit_line_evidence` (`le.fit([*backfill_rows, *n_plus sheet_rows])`, merged through `tennis_point_curves.merge_evidence`) and a test.
- The backfill has to price every N+ line with the point model as of each match. That is a new pricing pass, not a replay of sheets, which were deleted 11-19 anyway. Budget for it. `unmapped_prices` exist from 2026-10-14 only (from 10-20 is fine).

### B-F7 FIX - the forward-test verdicts overlap
- Plan: PASSED = lower M1 >= -0.05 and M2 >= -0.05 and lower M3 > 0. FAILED = upper M1 < -0.03 or upper M2 < -0.05.
- Problem: an M1 interval like [-0.045, -0.035] is both PASSED-eligible (lower >= -0.05) and FAILED (upper < -0.03). "M2 >= -0.05" does not say point estimate or bound, and "ROI po kursie" does not say before or after the 12% tax.
- Correction: give an explicit evaluation order (FAILED checked first). State whether M2 is a point estimate or a bound, and whether it is before or after tax. Freeze all of this in `PROTOCOL.md`.

### B-F8 FIX - template count in the tests
- Plan, tests: "12 szablonów -> klucze".
- Fixture: there are 18 templates = {match, 1. set, 2. set} x {asy, podwójne błędy, asy + podwójne błędy} x {total, player}. All 18 occur for event 17537878.
- Correction: test all 18, including the serve_points (`asy + podwójne błędy`) mapping and the lowercase set-total names ("1. set - asy").

### B-N1 NOTE - the plan never says that "asy + podwójne błędy" maps to `serve_points_*`
It is implied by "klucz musi należeć do TENNIS_POINT_MODEL_MARKETS". State it in `serve_ladder.py`'s table, matching `market_mapper.py:92` / `:625`.

### B-N2 NOTE - `parse_line` takes the market key
- Plan: `offer.parse_line(sbv)`, "prefiks S-".
- Code: the signature is `parse_line(raw_line, market)` (`offer.py:36`). The scope check reads "set1" / "set2" from the key (`:63-75`), and an unscoped key with a prefix raises. The prefix is the set number ("1-7"), not literally "S-".
- Correction: classify the key first, then call `parse_line(sbv, key)`.

### B-N3 NOTE - the `n_plus:` evidence key starts from the tennis estimator pool's offset
- Code: a key with no own lines reads the price-gap offset fully shrunk to `sport_printable_by_gap["tennis"]` (`line_evidence.py:253-269`; n = 0 means the pool gap). From 11-08 that pool is the **estimator-priced** tennis rows (point-model rows excluded), not point-model lines. The pool is "clean", but it measures another estimator's miscalibration.
- Correction: say so in the report and in model-state.md (b). Optionally fall back to the point-model key's own entry (`aces_total|OVER`) before the pool. That is a design decision; state it either way.
- The class prefix order must also be fixed: `evidence_key` prepends the class (`line_evidence.py:167-169`), giving `tennis_women:n_plus:...`. `merge_evidence.ours` handles both orders, but CONFIDENCE and the fit must build it identically.

### B-N4 NOTE - mixing N+ rungs into an existing (market, subject) ladder
- Code: `run_sheet.py:2917` (`ladder_rungs`) and the ladder-sigma / NO_PRICE_ANCHOR verdict notes (`:3600-3640`) read every rung of the same (market, subject). The point model sets p and centre for these keys (`:3218-3240`), so p_central should not move. Verdicts and notes of existing two-sided rows can.
- Unconfirmed whether anything printed reads them in stats-only mode. The E2E check "legs bez zmian" should diff existing 05_sheet rows field by field (p_central, centre, notes, verdict), not only count legs.

### B-N5 NOTE - registered or proposed tests whose population grows
- T-TENNIS-DF-UNDER-FORWARD (NOT_PASSED, `measure_tennis_df_under_forward.py`; "sheet coverage" of double-faults lines) and the PROPOSED T-TENNIS-SERVE-MARKET-LINE / T-TENNIS-ACES-SETS-EXPOSURE define their population as "fixtures Superbet quotes serve markets on".
- Under the shadow switch the N+ rows land in 04_offer / 05_sheet / 07_settled under the same market names, which adds Challenger / WTA 125 fixtures. T-TENNIS-STEP-UP-FAVOURED reads 08_confidence legs (affected only at print).
- Decide and record in the registry: exclude rows with `serve_ladder_rule`, or say the population changed.

### B-N6 NOTE - `superbet_names` must reproduce the screen's casing per scope
Screen names (fixture): "Asy", "Podwójne błędy", "Asy + podwójne błędy" (match total); "<gracz> asy"; "1. set - asy" (set total, lowercase); "1. set - <gracz> asy + podwójne błędy". The selection is "19+". Today's table (`superbet_names.py:86-144`) is the two-sided "liczba asów" format. The N+ branch must be chosen by the leg's flag, since the market key is the same.

### B-N7 NOTE - `market_coverage` works on market names only
`classify_market_name` matches the name template (`market_coverage.py:564-566`). The bare template "podwojne bledy" is shared by N+ and "kto więcej" and is today `tn.double_faults_unknown_shape` (`:413-415`). The new `tn.serve_n_plus` rule cannot separate them by name. Document that, or classify with the selection where `_reader_reads` sees items.

### B-N8 NOTE - shadow jsonl written by CONFIDENCE
`run_confidence` today writes no append-only per-day file. Every rebuild re-runs CONFIDENCE and appends. Make sure E2E and tests point `SOFA_RUNS_DIR` at scratch (the plan does), and that `rebuild_day --dry-run` never appends. Unconfirmed whether any md5 / artifact guard lists the day's files.

### B-N9 NOTE - commit-order labels collide with the market letters
"Kolejność commitów: A kod ... -> E2E -> C zamrożenie" reuses A / C, which in this plan name hockey / football, and there is no "B". "D0" is undefined. Rename the steps (B1 code, B2 E2E, B3 freeze, B4 evaluation, B5 print decision) and define D0 as the day of the freeze commit.

### B-N10 NOTE - `day_flags` is by date only
`offer.day_flags(date)` (`offer.py:262-283`) has no build clock, like every existing OFFER flag. The shadow switch is honoured in OFFER by day only. CONFIDENCE (`TENNIS_SERVE_N_PLUS_PRINT`) can use the clock. That is fine at 00:00Z; say it in the epochs comment.

### B-N11 NOTE - unconfirmed claims
- "0 SAMPLES requests": SAMPLES fetches `/event/{id}/statistics` for every historical event regardless of metric (`samples.py:1101-1104`), so the suspicion is plausible. Confirm with the counter, as the plan says.
- Point-model coverage of Challenger / WTA 125 players (NOT_RATED share) was not checked.

## Section 0 / 1 / 6 items for B
- Decision 8 (women never print) is confirmed in code.
- Section 1, "czytelnicy ceny poza pipeline'em": for tennis it is automatic through `day_flags` (confirmed). No per-reader edit is needed beyond the `day_flags` key and the `OfferFetcher` parameter.
- Section 6, criterion 3 (staged curve file differs only by new keys): not applicable to B, since no curves change. Criterion 2 needs B-F3.
# Plan verification - C (football half handicap + half double chance)

Plan: docs/sofa/history/PLAN_NOWE_RYNKI_2026-11-20.md section 4 (+ 0/1/6 where they touch C).
Code: HEAD 7585bb54. Read-only; DB read with mode=ro; no network.

## Confirmed claims (no action)

- `run_settle._settle_sim_market` scripts/sofa/run_settle.py:384-394 grades `settle_value(value, row["line"], ...)` - the docstring says "graded at line 0.5" but the code uses the row's line. A 1/0 indicator vs line 1.5 = LOSS on every win. Misgrade claim CONFIRMED. `regrade_settled.py:95,203` imports the same function, so one fix covers both.
- Sim chain has no line: `path_spec(market, subject, direction)` football_sim_markets.py:335, `path_holds(market, subject, ht, ft, first_1h)` :228, `sim_value(market, subject, event, incidents)` :300, `SimPricer.p(event_id, centres, market, subject, direction)` football_sim_sheet.py:118, `fit_football_sim_curves.SUBJECTS` (market, subject, direction) :96-117, `day_lines` key `(eid, market, subject, direction)` :311-313, `_price_job` :330. CONFIRMED.
- `SCHEDULE_TERM_MARKETS = {...} | (FOOTBALL_SIM_MARKETS - SCHEDULE_TERM_FLOOR_EXCLUDED)` epochs.py:3999-4003. CONFIRMED: adding keys to FOOTBALL_SIM_MARKETS would change the schedule-term population.
- `fit_football_sim_curves --schedule-term`: `excluded = replay.terms.excluded_markets` (:461-462) from config/sofa_schedule_terms.json `excluded_markets` (the 4 floor keys). CONFIRMED: new keys would be priced on corrected centres in a `--schedule-term` fit. Live SHEET prices them uncorrected (`schedule_term_rows` run_sheet.py:1992 `market not in SCHEDULE_TERM_MARKETS -> price(football, False)`).
- `football_sim_curves.py:199` `if day >= before or (switch_day ... and day >= switch_day)`; caller passes the FOOTBALL_SIM day (fit_line_evidence.py:432-445). CONFIRMED.
- `fit_football_sim_curves.py` has no `--awarded-excluded`; backfill refuses awarded via `settle_completed` (:386-389); the minute-history pickles exclude awarded (measure_football_sim.py:305 on the live part - the 11-06 pickle's history part NOT re-checked: unconfirmed).
- `offer._add_price` offer.py:381-424 keeps `min(existing, new)` on a collision. CONFIRMED.
- Key-name rule (no `handicap_` / `dc_and_` prefix) is well founded: `market_mapper.derived_base` / `is_derived` (:1109-1117), `confidence.is_derived` (:168), `superbet_names.py:397`, `run_settle.py:487`, `measure_football_sim.GROUP_MARKETS` (:1153), `dc_and_*` are SCORE_MARKETS. `result_1h_handicap` contains `_1h_`, so `leg_relations._period` (:103) reads it as 1ST (harmless; never in a builder).
- `RATING_ONLY_MARKETS` tennis_winner.py:66-69 includes `football_sim_markets.MARKETS` -> if `fsm.MARKETS = BASE | HALF`, the new keys are rating-only (no builder, own curve only, `coupon_results.EVENT_MARKETS` :72 shows "tak/nie / wynik" not "1 vs 1.5"). run_sheet routes `rung.market in RATING_ONLY_MARKETS` (~:2747) before the sample branch, so the `run_sheet.py:2994` "no metric" skip does NOT hit C.
- `leg_floor` epochs.py:3827-3842: the new keys are not in FOOTBALL_SIM_FLOOR_KEYS -> 0.70. "podłoga 0,70" needs no code.
- Superbet shapes (runs/sofa/2026-11-15..19 unmapped_prices): "1.połowa - handicap" / "2.połowa - handicap", selection "<team> (L)" no "+" sign, `specialBetValue` = home's line (svb -1.5 -> home (-1.5), away (1.5)); outcomeId 151894/151895 (1H), 151898/151899 (2H) = home/away. svb seen: ±0.5, ±1.5, ±2.5, ±3.5, ±4.5 (no integer lines in 11-15..19). Half DC: selections "1X" / "X2" / "12", no svb. Price check 17551008: DC 1X 1.32 vs home +0.5 1.35 - different prices, CONFIRMED.
- Test fixtures (DB, mode=ro): 15534188 Kazakhstan - Slovakia HT 1-0 FT 2-2; 15534056 Germany - Netherlands HT 1-0 FT 5-0; 15458641 IFK Stocksund - Enköpings HT 0-0 FT 1-3; 17551008 Montenegro U21 - Bosnia & Herzegovina U21 (not started). 11-16 has 05_sheet.json. CONFIRMED.
- `audit_ledger.EPOCH_GROUPS` :148, `epoch_group` :329 (top branch pattern). CONFIRMED. Last group "od 11-10".
- No staged file / switch dated after 11-19 exists (latest: `.next.2026-11-09.json` main + sim, STAKES_GROUPS 11-19). A `sofa_football_sim_curves.next.2026-11-22.json` would simply become the latest for 11-22+ (`path_for` :93-110).

## BLOCKER

C-B1. New keys outside `football_sim_curves` scope -> no curve, no backfill evidence, nothing prints.
- Plan: separate `FOOTBALL_SIM_HALF_MARKETS`, `fsm.MARKETS = BASE | HALF`; curves in `sofa_football_sim_curves.next.<D>.json`.
- Code: football_sim_curves.py:63-64 `_in_scope` = `key in epochs.FOOTBALL_SIM_MARKETS`; `_replace` (:113-117) keeps only in-scope keys from the doc, `no_pool` (:120) and `ours` (:213) likewise. The staged file's 4 new keys would be DROPPED by `overlay`; `merge_evidence` would not take their backfilled entries.
- Correction: make `_in_scope` / `no_pool` / `ours` read `FOOTBALL_SIM_MARKETS | FOOTBALL_SIM_HALF_MARKETS` (or `fsm.MARKETS`); test that a half key in the staged file survives `for_day` and that line evidence carries it. Also `rebuild_plan.py:605` uses `epochs.FOOTBALL_SIM_MARKETS` (plan already adds `offer_has_sim_half`).

C-B2. E2E as written cannot run.
- Plan: "kopia 11-16 ..., `rebuild_day.py --dry-run` musi pokazać OFFER + SHEET".
- Code: rebuild_plan.py:743-758 - with `open_fixtures == 0` (a past day) no OFFER step at all (DAY_OVER note); `sim_offer_stale`-style branches sit in the open-fixtures `else`. rebuild_day.py:150 and run_pipeline.py:182 refuse SOFA_NOW. A live OFFER would ask Superbet for 4-day-old events (network, and no prices).
- Correction: E2E offline - build the half rungs from the recorded `unmapped_prices` snapshot (e.g. 20261116T062608) through `classify_odd(..., football_sim_half=True)` into a scratch `04_offer.json`, then run SHEET / CONFIDENCE / COUPON stage scripts directly with `SOFA_NOW` and a scratch `SOFA_RUNS_DIR` (timeutil.py:35 only refuses the real runs dir). Test the rebuild_plan triggers (`sim_half_offer_stale`, `sheet_football_sim_half`) as unit tests with a frozen `now`. (Same objection applies to B's "kopia 11-19 SOFA_NOW 06:20Z" if it goes through rebuild_day - outside C.)

## FIX

C-F1. `fit_football_sim_curves.py --out` defaults to the INSTALLED file.
- Code: :424 `--out default=str(config_path(fsc.FILE))` = config/sofa_football_sim_curves.json (read by 11-06 17:30Z .. 11-09 11:30Z). Plan's section 1 warns only for `fit_sport_confidence.py`.
- Correction: `--out` mandatory (scratch `data/refit_<D>_sim_half/...`), never the default.

C-F2. Flags the plan uses do not exist.
- Plan step 6: `fit_football_sim_curves.py ... --keys, --base ..., --effective-from`.
- Code: argparse :418-435 has none of them; the script writes a whole file with no `effective_from` / `staged_change` (11-09's `effective_from` was added outside the script). `_staged_start` (:79-88) RAISES when `effective_from`'s date differs from the file name.
- Correction: say they are new; the composed file = 11-09 file byte-for-byte for every existing key + 4 new keys + `effective_from` = "<D>T00:00:00Z" (name and date equal) + `staged_change`; its `fitted_from` describes the 11-09 fit, so record the half fit's own `fitted_from` under `staged_change`.

C-F3. Backfill file name / script / cache unclear.
- Plan step 6: "`measure_football_sim.py --stage live_forecasts` (nowy etap), potem `--backfill-out data/line_evidence/football_sim_half_lines.jsonl.gz --backfill-from 2026-10-14 --backfill-to <D-1>`".
- Code: `--backfill-out` exists only in fit_football_sim_curves.py (:426-430); measure_football_sim.py `--stage` choices are inventory/forecast/fit/history/superbet (:1904-1905). `load_live_forecasts` (:323-338) returns the cached `forecasts_live.pkl` unchanged if it exists - data/football_sim_2026-11-06 ends at its 11-06 build.
- Correction: name the command as `fit_football_sim_curves.py --cache-dir <NEW dir> --backfill-out ...`; the new stage writes into a NEW cache dir (never data/football_sim_2026-11-06, which is the installed file's provenance and backs backfill_schedule_term_p). Also restrict the backfill to the half keys (today `day_lines` keeps every `fsm.classify` hit, so the base keys would be written again).

C-F4. The new backfill file is read by nobody.
- Code: `football_sim_curves.load_backfill()` (:174-185) reads only `BACKFILL` = football_sim_lines.jsonl.gz; fit_line_evidence.py:434 calls it without a path; `backfill_rows` takes ONE `switch_day`.
- Correction: load the half file in fit_line_evidence when `football_sim_half(args.before)` (gate it, so the line-evidence config and its `fitted_from.football_sim_backfill` count stay unchanged while off), with `switch_day` = FOOTBALL_SIM_HALF day for those rows. `schedule_term_evidence.sim_lines` (:144-158) passes out-of-scope rows through - OK.

C-F5. Half DC complement needs a second-rung path.
- Plan step 4: "nowe `half_dc_complement`"; DC UNDER = the omitted half result's price.
- Code: one "1.połowa - 1X2" odd is already classified as `result_1h` OVER by `classify_sim_market` (offer.py:241); `classify_odd` returns one rung. The only multi-rung path is `extra` (offer.py:500-505), wired solely to `classify_1x2_dnb` under `result_1x2_dnb`.
- Correction: compute the complement beside `extra` in `OfferFetcher.fetch_offers` (gated by the half flag), add it to the rung list, and delete `result_1h_dc` / `result_2h_dc` rungs whose `over_odds` is None (pattern offer.py:572-575). Byte-identical when off.

C-F6. Selection regex must keep "(K)".
- Data: "Internacional RS (K) (-1.5)", "Flamengo (K) (1.5)".
- Correction: greedy team, anchored last group, e.g. `^(?P<team>.+) \((?P<l>-?\d+\.5)\)$` (the full-match precedent `football_score_markets._HANDICAP_SEL` :108 is exactly this); svb check: home line == svb, away line == -svb. ±3.5 / ±4.5 refused.

C-F7. Tests that will fail and must be updated (not in the plan).
- football_sim_markets.py:84-86 module-level `assert MARKETS == frozenset({9 keys})`; tests/sofa/test_football_sim_wiring.py:424 `fsm.MARKETS == epochs.FOOTBALL_SIM_MARKETS`; tests/sofa/test_schedule_term_replay.py:382 `fsc.staged_paths(...) == [staged 11-09]` (breaks as soon as `.next.<D>.json` is committed).
- tests/sofa/off_scenarios.py `_NEW_MARKERS` (:23-69) must list `football_sim_half_rule`, else test_off_identical_head fails; and run_sheet `AUDIT_MARKER_FIELDS` (:2409) + rebuild_plan marker tuple (:337) + `stamp_marker` list (:4371).

C-F8. Fit the new keys WITHOUT `--schedule-term` (or the EXCLUDED patch) - and never by editing config/sofa_schedule_terms.json.
- Code: `excluded_markets` lives in that config; editing it changes its sha (recorded in the 11-09 sim curves `fitted_from.schedule_term.config_sha256` and the frozen T-SCHEDULE-TERM-FORWARD protocol).
- Correction: the plan's in-code `EXCLUDED |= fsm.MARKETS - SCHEDULE_TERM_MARKETS` is right if `--schedule-term` is used; simpler: fit the 4 keys without the flag (they are uncorrected live), and say so in `staged_change`.

## NOTE

C-N1. Precedent not cited: full-match `result_handicap` (football_score_markets.py:37-41, 179-189, `value_line` :309-312, slice curves "<market>@<subject>@<line>|OVER") is the same market type on the 90 minutes, graded at 0.5 via `value_line` - reuse the pattern (`sim_value` -> indicator, settle at `fsm.LINE`). It left +0.5 out because it equals the DC; the plan keeps +0.5 AND the half DC and relies on SAME_EVENT_DEDUP (higher price wins: handicap 1.35 > DC 1.32 on 17551008). Plan pools lines 0.5/1.5/2.5 and both subjects into one `market|OVER` curve; the precedent chose per-slice curves. Decide consciously.

C-N2. "UNDER only for the margin" vs step 8: `sim_rows` (run_sheet.py:1937-1938) emits UNDER only for `TWO_SIDED`; half keys OVER-only, so the "s@0.5 UNDER ≡ result_Xh other side" identity is moot (keep the test, but no UNDER leg can exist). DC line: say explicitly line = `fsm.LINE` 0.5.

C-N3. Mixed centres. Half keys priced on uncorrected centres while `result_1h` / `htft` use schedule-corrected ones: identical events (handicap s@0.5 OVER ≡ DC; DC 1X vs result_1h "2") carry inconsistent p; and `SimPricer` (football_sim_sheet.py:96-105) re-simulates whenever centres alternate on one event (4,000 sims per switch - SHEET time). Price half rungs with `base_sim_pricer` when it exists.

C-N4. Unmapped not fully emptied: DC "12" and handicap ±3.5/±4.5 odds still return a label -> the market name stays in `unmapped_markets` and `unmapped_prices` (section 1 says the market "znika"). Fine, but the C test "off = unmapped" / "on = mapped" must expect it, and nothing (rebuild_plan) should key off those labels.

C-N5. Price readers: build_slip.py:363-367, capture_closing.py:331-333, verify_legs.py:502, run_offer.py:129 all use `offer.day_flags` - adding `"football_sim_half"` there and an `OfferFetcher` kwarg covers them. `boosts.py:149` calls `classify_odd(item)` with no flags (boost legs never read the new keys - same as today's sim keys). verify_legs `CODE_SUBJECTS` (:99) already holds "1","2","1X","X2". `/kupon` pool requires own sample >= 8 (slip_builder.MIN_SAMPLE) - sim keys have none, so they enter only with `--allow-no-sample` (unconfirmed exact field; same as existing sim keys).

C-N6. F25 / neutral venue: subject codes "1"/"2"/"1X"/"X2" are Superbet's order, graded on Sofascore home/away - same assumption as `result_1h`; the open neutral-venue defect (memory, Godoy Cruz 11-15) applies equally. 2H = `regulation_score - period1` (football_sim_markets.py:315-322), extra time excluded via `normaltime`, HALF_TIME_DISAGREES and HALF_ABOVE_MATCH refusals already in `sim_value` - reuse, no new refusal needed.

C-N7. `fit_football_sim_curves.day_lines` `counter_odds` only for `TWO_SIDED` (:316-320): half handicap backfill rows would carry no margin -> any margin-based measurement (measure_football_sim_floor / _wiring style) of the half keys needs `counter_odds` keyed with the line.

C-N8. Registry: `T-FOOTBALL-HALF-HANDICAP-FORWARD` - check_test_registry REQUIRED fields (:30-31) do not include `evaluation`; fine, but the plan names no evaluation script or thresholds for it (unlike A / B / D).

C-N9. `superbet_words` must write UNDER as the other team "(-L)" and OVER "<team> (L)" with `{line:g}` (no "+"), matching `superbet_names.py:378-379` precedent; `_football_tennis` (:438-440) must pass `line`.
