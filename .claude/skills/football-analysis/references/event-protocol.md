# Football event protocol — the steps, and the report they produce

Steps are ordered by the evidence hierarchy. A hard fail early ends the
analysis with `NO BET`; no later step may reopen it.

## Which fixtures get the full protocol

1. Every football fixture with at least one `verdict == "VALUE"` row in
   `05_sheet.json`.
2. Every football fixture appearing in `08_confidence.json` — as a leg, and
   especially as a builder. **These are the ones actually staked.**
3. Every fixture you intend to veto.
4. Rows in `06_dropped.json` whose reason surprises you.
5. Everything else: one line in *Pozostałe mecze*.

## The steps

| # | Step | Where the answer is | What you write |
|---|---|---|---|
| I1 | Identity and both clocks | `02_fixtures.json`: `identity`, `kickoff_utc`, `superbet_kickoff_utc`, `kickoff_disagreement_h`. Then `get_match_detail(match_id=…)` by id for `status`. | "Liga X, kolejka N; start 20:00Z (Superbet 20:00Z); `CONFIRMED`; `notstarted` `[BZZOIRO-MCP: get_match_detail, fetched …]`". Anything but `notstarted` on a live day → veto, all lines. |
| I2 | Stakes and round | `round_name`, `cup_round_type`, `previous_leg_event_id` in the fixture; aggregate and table from MCP/web | round, whether it is a second leg and what the first leg did, table position, dead rubber |
| I3 | The sample, per side | `03_samples.json` → `metrics[<metric>].side_a / side_b / h2h` | n per bucket, date range, opponents, venues. Name anything that makes the mean. |
| I4 | Shrinkage share | `n/(n+25)` | "n=10 → the sample owns 29% of the centre; 71% is the league baseline" |
| I5 | Distribution | the observations themselves | min, max, median, **mode**, where the line sits. Flag a line on the mode, and a line beyond the sample's extreme. |
| I6 | Venue and opponent class | observation `venue`, `opponent`, `competition_id` | sample's home/away mix vs tonight; whether the sample's opponents are this opponent's class |
| I7 | Estimand check | compare `X_for(A)+X_for(B)` against `X_total`'s mean; check the metric's definition | "`cards_points` is booking points, not cards"; "`totalShotsOnGoal` is all shots" |
| I8 | Referee (cards/fouls only) | `RefereeRecord` — present on ~9% | `games`, yellow rate, red rate, **or** "brak sędziego" and what that costs. Not blended into the centre in `sofa`. |
| I9 | Absences and lineup | not in the artifacts — `get_match_lineups`, web | per side: count, the names that matter, and how you checked |
| I10 | Game script A–D | not in the artifacts; `compare_odds` is ~88 books, none of them Superbet | which scenario is modal and whether the market survives it |
| I11 | The ladder | every rung of this market in `04_offer.json` + its sheet rows | rung table with `p_central`, `p_bar`, `offered`, `required`, `surplus`; note `NO_LADDER_CHECK` where it appears |
| I12 | Correlation | the mechanism, if this may become a builder leg | the one scenario that kills every leg at once. **Never multiply.** |
| I13 | Price, last | `offered_odds`, `required_odds`, `surplus`, the rung's `fetched_at_utc` | value statement, and "surplus +0.52 — suspect by definition" where it applies |
| I14 | Buy case / kill case | | strongest fact for, strongest fact against, which wins |
| I15 | Verdict | | `KEEP / WATCH / NO BET` + the veto entry |

## The fixture section, in Polish

```markdown
### <Gospodarz> – <Gość> — <rozgrywki>, <runda>
**Start:** 2026-09-21 20:00Z (Superbet 20:00Z; rozjazd 0.0 h) · **identity:** CONFIRMED
**Status:** notstarted `[BZZOIRO-MCP: get_match_detail, fetched 2026-09-21T09:12Z]`

**Stawka.** <round, second leg + aggregate, table position, or "brak">

**Próbka.** corners_total: side_a n=10 (2026-07-14 … 2026-09-14), side_b n=10,
h2h n=3. Wartości side_a: 6 8 8 9 9 10 11 11 12 15 (mediana 9, moda 8/9/11,
zakres 6–15). Trzy najwyższe przeciw <opponents>.
**Udział próbki w centrum:** n=10 → 10/35 = 29%; 71% to baza ligowa.

**Rozkład.** <mode, tails, where the line sits>

**Kontekst.** Sędzia: <name>, <games> meczów, <yellow rate>/mecz — albo „brak".
Braki kadrowe: <…> `[WEB: domain, fetched …]`. Scenariusz modalny: <A/B/C/D>.

**Drabina.**
| linia | kier. | p_central | p_bar | oferta | próg | nadwyżka | uwagi |
|---|---|---|---|---|---|---|---|

**Cena.** <offered vs required, fetched_at, surplus and its suspicion>

**Za:** FAKT → RACHUNEK → IMPLIKACJA → RYZYKO
**Przeciw:** FAKT → RACHUNEK → IMPLIKACJA → RYZYKO

**Werdykt:** KEEP / WATCH / NO BET — <one sentence>
```

## Rules for the section

- Every non-artifact statement carries a source tag and a fetch time.
- Never present a `FUZZY` identity as confirmed.
- Never quote a combined price you computed. `confidence.py` owns that number.
- Do not repeat a gate the code already applied as if it were your finding;
  say "kod już to odrzucił jako `MODE_LOSES`" and move on.
- When you could not check something, it goes in **NIE PODANO** — never
  silently omitted. Silence about a skipped check reads as a passed check.
