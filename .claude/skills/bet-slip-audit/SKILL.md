---
name: bet-slip-audit
description: Price a Superbet single, Bet Builder or SUPERBETS boost before recommending it and refuse what cannot be worth its price; build a chat slip (AKO) to a target price from the day's coupon with build_slip.py - sofa confidence (11_coupon.json) for a row of the day, an outside price only when the operator types it. Use for a screenshotted slip, a boost, a builder draft, team goals 0.5, range markets, per-team counts, props.
---

# Audit the price before the fixture

You are in the main session. This skill is **outside the pipeline**: no stage
calls it, and your answer says so. For a Bet Builder, first run the builder
method (`docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md` §39-§44: correlation,
contradiction test, common-outcome test, builder score - never the product of
leg probabilities); a slip correctly priced but internally contradictory is
still not a bet.

## Data rule

Sofascore and Superbet only. An outside number (a consensus 1X2, a totals
line) is used **only when the operator types it in**, and the answer labels it
"podane przez operatora". Never fetch one: no bzzoiro MCP tool, no bzzoiro API,
no other bookmaker feed. `scripts/sofa/audit_slip.py` does no network (its
docstring still names bzzoiro as the source of the numbers - ignore that; the
operator-typed rule governs). With no typed number and no sample, the answer is
**"brak dowodu"** - never a league-wide constant dressed as a read.

## Chat slips (CLAUDE.md hard rules, restated for this use)

A slip assembled in chat is not a coupon and has no gates.

1. **Say no first.** When the operator asks for N slips, a target price or
   disjoint slips and the day supports fewer, the first line says so ("dzień
   cienki - masz jeden kupon" / "dziś żadnego"). Never fill the request with
   weaker legs.
2. **"Supports" is measured.** Scan the whole window for legs of families whose
   printed legs realised at or above their price on the latest settled days -
   `runs/sofa/<d>/family_record.json` (`units`, `roi`, `hit` vs `implied`, 14
   days) and `measure_settled_by_market.py` for intervals. Name the days and N;
   match bootstrap; one family in twenty clearing zero is what chance gives -
   say so. Inside a match prefer such a leg.
3. **Every table the operator may stake from** carries that measured chance (a
   `price_gap` leg at its price, never its confidence) and says "na minusie"
   when it is below the price - in **every** re-summary, not only the first.
   The product of confidences is never the headline.
4. **Name each leg in Superbet's words**: `superbet_market: superbet_selection`
   from `11_coupon.json` (`bet.sofa.superbet_names.names` for a leg of another
   artifact), never a paraphrase like "Seattle +1.5 w 3. tercji".
5. **Never a combined / Bet Builder / parlay price**, never `odds_if_product`
   as one - Superbet does not price a slip as the product of its legs (markup
   measured 8.8-19.6%).
6. **No stake sizing, no placement.** The stake is the operator's.
7. **Judge the decision, never the result.** A settled win or loss never enters
   the next decision.

## Building a slip to a target price

When the operator asks for a slip (AKO) "na ~X" - in a time window ("od 10
do 12"), or several disjoint ones - build it with the script, never by hand,
have every leg read, and relay the script's first line first. Operator
2026-10-20: search **every market** (`--allow-rest`), the analysts read the
chosen legs, a refused leg is replaced by the next best and that one is read.

**The search** (`src/bet/sofa/slip_builder.py`): legs of `11_coupon.json`
singles, not started (10 min margin), odds 1.10-2.00, one per match; a leg's
measured chance = min(confidence, price for a `price_gap` leg, 1/odds + its
family's measured shortfall; a family on the plus reads its tier's
walk-forward shortfall, never a surplus). An exact multiple-choice knapsack
maximises the slip's measured chance under "price product >= target" - which
picks the fewest legs (every odds band loses about alike per leg,
10-13..10-19). A leg a veto or a WATCH / NO_BET read refuses (`vetoes.json`,
`reads.json`, or carried) never enters, so a re-run after a merge takes the
next best leg. `--reserve 1` also builds the next disjoint slip: read with
the slip, it is the buffer a refusal falls back on.

**The loop** (main session; at most 3 rounds):

1. Build and write the read set:
   ```bash
   PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py --date <d> --target <X> \
       [--start-from HH:MM --start-to HH:MM] [--slips N] --allow-rest --reserve 1 \
       --read-set-dir runs/sofa/<d>/read_set_slip
   ```
2. For each `read_set_slip_<sport>.json` it lists, spawn that sport's analyst
   (`sofa-analyst-football` / `-tennis` / `-sport` with the sport named) in
   the **foreground**, naming the file and the report path
   `runs/sofa/<d>/<d>_analiza_<sport>_kupon_<round>.md`; independent sports
   in one message.
3. `merge_reads.py --date <d> --report <each report>` (never re-type a
   report). The reads are real reads: the next rebuild applies them to the
   coupon too.
4. Re-run step 1. Done when it prints "Każda noga kuponów ma KEEP analityka"
   (`do przeczytania: nic`); otherwise the refused legs are gone, the
   replacements are listed - back to 2. After round 3, report the unread legs
   as unread; never present one as read.

Relay: the first line (the "say no first" answer about families on the
plus), then each slip's table as printed - Superbet's words, measured chance
beside 1/odds, the read verdict, "poza poparciem" where it says so - and
which legs fell out on which read. No slip price, no stake; the price
product line is a target check only. The family selection's advantage is not
yet shown (T-FAMILY-SELECTION). Legs starting while the analysts read drop
out on the re-run: name a window that starts >= 30 min ahead. Exit 0 all
supported, 1 fewer, 2 no coupon. Tests `tests/sofa/test_slip_builder.py`.

## Three cases

| the leg is | the number to compare with |
|---|---|
| a row of the day (`runs/sofa/<d>/11_coupon.json` leg, or a `05_sheet.json` rung) | its `confidence` (calibrated, lowered by line evidence) and x = confidence x `offered_odds` (>= 0.90 prints), at the price on the screen; `forecast_p` is "model", uncalibrated; sample k/n beside. `p_bar`, `required_odds`, `surplus` are the old VALUE selector's numbers, anti-selective (surplus > +0.40 suspect) - never the verdict |
| not a row (unread market, see `market_coverage.md`) | only an operator-typed consensus through `audit_slip.py`, or `--market sample` on a Sofascore k/n from `03_samples.json`; label it outside the pipeline |
| a Bet Builder | sofa prints no builder price: legs, `combined_probability` (the lower of the product and the empirical joint) and "kurs buildera: sprawdź na ekranie Superbetu". `odds_after_haircut` / `ev_after_haircut` are internal (stakeable test, `BUILDER_CORRELATION_HAIRCUT` 0.12), never quoted as a price. A screen price the operator gives wins outright (`confidence.builder_odds`): `combined_probability x screen_odds - 1`, shown as his note |

## Order of operations

Price first, fixture second - every losing bet of the ledger had a true team
story behind a price already at or under fair.

1. Get the number to compare with (table above). None: "brak dowodu", stop.
2. Fit and compare with the tool (it devigs, fits the match rate, reports the
   edge; it fits the market, it does not disagree with it).
3. Only then read form, lineups, referee, absences - they turn a fair bet good
   or bad; they never rescue a price below fair.

```bash
# team to score, from a consensus the operator typed
.venv/bin/python scripts/sofa/audit_slip.py --price 1.48 --market team_to_score --side away \
    --home-win 1.50 --draw 4.43 --away-win 5.45 --over-25 1.52 --under-25 2.41
# a range builder
.venv/bin/python scripts/sofa/audit_slip.py --price 2.05 --market 1h_over_0_5_under_2_5_and_2h_over_0_5 \
    --home-win 7.47 --draw 4.23 --away-win 1.45 --over-25 2.01 --under-25 1.81
# no outside line: Wilson lower bound off a real sample (weaker; says so)
.venv/bin/python scripts/sofa/audit_slip.py --price 1.42 --market sample --hits 5 --sample-size 6
```

`--market` is one of `team_to_score`, `sample`,
`1h_over_0_5_under_2_5_and_2h_over_0_5`, `each_half_1_3`; `--label` names the
row; repeat `--leg-probability` once per leg to also get the slip's hard price
floor. Verdict threshold `slip_audit.MINIMUM_EDGE` 0.02 (a tolerance, not a
discovered constant). Use `--market sample` for corners, fouls, shots and
props, and never present it as the market's opinion.

## Refusals before reading the fixture

| market on the screen | ceiling | never take below |
|---|---|---|
| `gole 1-3 w każdej połowie` (`each_half_1_3`) | 52.0% at a 3.6-goal match | 1.92 (in practice 2.10) |
| `1.poł pow. 0.5` + `1.poł pon. 2.5` + `2.poł pow. 0.5` | 50.5% at a 3.9-goal match | 1.98 (in practice 2.15) |

Range markets are two-sided and bounded by their own shape; no fixture makes
one a favourite. Derive the numbers with `slip_audit.range_market_ceiling()`,
never from memory.

- **A slip is never likelier than its weakest leg**: `slip_price_floor()` =
  1 / p_weakest; at or under it, the other legs ride for nothing.
- **A leg implied by another adds no risk and must add no price**
  (`redundant_legs()`; a clean result means "none of the known pairs", not
  "independent").
- **Per-team counting lines at short prices are almost always below fair**: a
  team clears 4.5 corners ~48% and 12.5 fouls ~45% league-wide; 1.42 asks 70%.
  Only an extreme team rate with a real sample (Wilson bound) clears it.

## The six ledger patterns (2026-08-30/31, archived pipeline)

Read `reference/patterns.md` when a slip matches one and you need its numbers.

1. **`drużyna - liczba goli powyżej 0.5` is a house market**: 5 of 5 at
   1.40-1.60 had no edge. REJECT until a devigged number says otherwise; a long
   scoring streak is not an edge.
2. **The best-looking winner was the worst bet**: an implied second leg makes
   one event; identical structures won and lost. Results say nothing about
   decisions.
3. **Correlation**: goals-shots on target +0.55, goals-corners ~0, fouls
   slightly negative - multiplying flatters shots-and-goals slips only. sofa
   takes one leg per quantity family (`confidence.QUANTITY_FAMILIES`) and
   refuses builders whose legs disagree about tempo.
4. **No edge on mainlines** (1X2, BTTS, match goals: 29 of 30 REJECT);
   the SUPERBETS boost (~+12%) rescues only a slip within ~11% of fair - price
   it **un-boosted first**. Current boost evidence: `run_boosts.py`
   (`10_boosts.json`), `audit_boosts.py --from <d> --to <d>`.
5. **Player props die on team volume**, not on the player: get the team's rate
   for the underlying event; minutes alone are not enough.
6. **No evidence is an answer**: a fixture with no Sofascore event
   (`NO_MATCHING_EVENT`), a gappy sample, `NO_LINE_EVIDENCE`, a match
   `UNVERIFIED` by FIXTURE_CHECK. Tennis has no outside price at all.

## References

- `reference/patterns.md` - the six patterns in full, and what not to conclude.
- `reference/ledger-2026-08-30-31.md` - every one of the twenty bets; read once.
- `reference/base-rates.md` - measured goals / halves / corners / shots / fouls
  tables (archived sample; orders of magnitude, never a prior for a sofa row).
- `reference/coverage.md` - historical: the archived source's holes; nothing
  there may be fetched today.
- `src/bet/sofa/slip_audit.py` (tests `tests/sofa/test_slip_audit.py`, the
  ledger as a regression); `src/bet/sofa/confidence.py` (`builder_odds`,
  `is_stakeable`, `QUANTITY_FAMILIES`).
