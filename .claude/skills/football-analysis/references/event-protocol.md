# Football event protocol — the steps, and the report they produce

Steps are ordered by the evidence hierarchy. A hard fail early ends the
analysis with `NO BET`; no later step may reopen it.

## Which fixtures get the full protocol

1. Every football fixture with a leg in your read set - the first 30
   positions of `11_coupon.json`, every printed builder leg, every
   `read_requests.json` entry (`08_confidence.json` on a day before the
   stats-only epoch). **These are the ones actually staked and read.**
2. Other printed football legs, where you reach them.
3. Every fixture you intend to veto.
4. Rows in `06_dropped.json` whose reason surprises you.
5. Everything else: one line in *Pozostałe mecze*.

## The steps

| # | Step | Where the answer is | What you write |
|---|---|---|---|
| I1 | Identity and both clocks | `02_fixtures.json`: `identity`, `kickoff_utc`, `superbet_kickoff_utc`, `kickoff_disagreement_h`; `fixture_status.json` (fresh start and status); `04_offer.json` `superbet_started_utc` / `superbet_kickoff_seen_utc` (Superbet's own start signal). Started or not: the earliest clock against the artifact's time — never another provider. | "Liga X, kolejka N; start 20:00Z (Superbet 20:00Z); `CONFIRMED`; not started at 07:40Z (earlier clock)". A fixture already started on a live day → veto, all lines. |
| I2 | Stakes and round | `round_name`, `cup_round_type`, `previous_leg_event_id` in the fixture; aggregate and table from the web (two domains, tagged) | round, whether it is a second leg and what the first leg did, table position, dead rubber |
| I2b | Schedule | `03_samples.json` → the fixture's `schedule` block; the legs' `context_flags` | make-up fixture (and *why* it was postponed, from the web), each side's rest days and matches in 7 / 14 days |
| I3 | The sample, per side | `03_samples.json` → `metrics[<metric>].side_a / side_b / h2h` | n per bucket, date range, opponents, venues. Name anything that makes the mean. |
| I4 | Shrinkage share and the rating | `n/(n+15)`; the sheet row's `FOOTBALL_RATING` note (rating centre, home / away attack and defence, `sample centre was ...`, `link_rule`) | "n=10 → the sample owns 40% of the sample-side centre; 60% is the league baseline; the rating (half of the final centre) says 2.87 against the sample's 2.90" - or "unrated market" |
| I5 | Distribution | the observations themselves | min, max, median, **mode**, where the line sits. Flag a line on the mode, and a line beyond the sample's extreme. |
| I6 | Venue and opponent class | observation `venue`, `opponent`, `competition_id` | sample's home/away mix vs tonight; whether the sample's opponents are this opponent's class |
| I7 | Estimand check | compare `X_for(A)+X_for(B)` against `X_total`'s mean; check the metric's definition | "`cards_points` is booking points, not cards"; "`totalShotsOnGoal` is all shots" |
| I8 | Referee (cards/fouls only) | `RefereeRecord` — present on ~9% | `games`, yellow rate, red rate, **or** "brak sędziego" and what that costs. Not blended into the centre in `sofa`. |
| I9 | Absences and lineup | not in the artifacts — the web, two domains, tagged | per side: count, the names that matter, and how you checked |
| I10 | Game script A–D | no 1X2 in the artifacts (`unmapped_markets` names it, unpriced); the favourite from Superbet's own ladders in `04_offer.json` (`goals_for`, `handicap_corners`, `most_*`), or "unweighted" | which scenario is modal and whether the market survives it |
| I11 | The ladder | every rung of this market in `04_offer.json` + its sheet rows + the coupon legs | rung table with `p_central`, pewność, próbka k/n, model (`forecast_p`) and `offered`; note `NO_LADDER_CHECK` where it appears |
| I12 | Correlation | the mechanism, if this may become a builder leg | the one scenario that kills every leg at once. **Never multiply.** |
| I13 | Price, only the filter | `offered_odds`, x = confidence x odds, the rung's `fetched_at_utc` | "x 1.03 >= 0.90, cena z 09:05Z" - a condition the code applied, never a reason |
| I14 | Buy case / kill case | | strongest fact for, strongest fact against, which wins |
| I15 | Verdict | | `KEEP / WATCH / NO_BET` + the read entry per leg of the read set + the veto entry |

## The fixture section, in Polish

```markdown
### <Gospodarz> – <Gość> — <rozgrywki>, <runda>
**Start:** 2026-09-21 20:00Z (Superbet 20:00Z; rozjazd 0.0 h) · **identity:** CONFIRMED
**Status:** nierozpoczęty o 09:12Z (najwcześniejszy zegar: 20:00Z)

**Stawka.** <round, second leg + aggregate, table position, or "brak">

**Próbka.** corners_total: side_a n=10 (2026-07-14 … 2026-09-14), side_b n=10,
h2h n=3. Wartości side_a: 6 8 8 9 9 10 11 11 12 15 (mediana 9, moda 8/9/11,
zakres 6–15). Trzy najwyższe przeciw <opponents>.
**Udział próbki w centrum:** n=10 → 10/25 = 40% centrum z próbki; 60% to baza ligowa;
tam, gdzie wiersz ma notkę `FOOTBALL_RATING`, połowę końcowego centrum daje
rating (próbka: 20%).

**Rozkład.** <mode, tails, where the line sits>

**Kontekst.** Sędzia: <name>, <games> meczów, <yellow rate>/mecz — albo „brak".
Braki kadrowe: <…> `[WEB: domain, fetched …]`. Scenariusz modalny: <A/B/C/D>.

**Drabina.**
| poz. | linia | kier. | pewność | próbka k/n | model | kurs | x | uwagi |
|---|---|---|---|---|---|---|---|---|

**Cena (tylko warunek).** <kurs, x = pewność x kurs >= 0.90, fetched_at>

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
