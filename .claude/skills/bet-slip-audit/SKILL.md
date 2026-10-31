---
name: bet-slip-audit
description: Price a Superbet single, Bet Builder or SUPERBETS boost before recommending it and refuse what cannot be worth its price; build a chat slip (AKO) to a target price from the day's coupon with build_slip.py - sofa confidence (11_coupon.json) for a row of the day, an outside price only when the operator types it. Use for a screenshotted slip, a boost, a builder draft, team goals 0.5, range markets, per-team counts, props.
---

# Audit the price before the fixture

You are in the main session. This skill is **outside the pipeline**: no stage
calls it, and your answer says so. Operator's own Bet Builder (screenshot) ->
`build_slip.py --check` first (section below); the method doc
(`docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md` §39-§44) only for its
contradiction / common-outcome tests - a slip correctly priced but internally
contradictory is still not a bet.

## Data rule

Sofascore and Superbet only. An outside number (a consensus 1X2, a totals
line) is used **only when the operator types it in**, and the answer labels it
"podane przez operatora". Never fetch one: no bzzoiro MCP tool, no bzzoiro API,
no other bookmaker feed - bzzoiro is never a source in the sofa flow
(Sofascore and Superbet only). `scripts/sofa/audit_slip.py` does no network and
takes an operator-typed consensus only (its docstring's bzzoiro wording is the
archived pipeline's). With no typed number and no sample, the answer is
**"brak dowodu"** - never a league-wide constant dressed as a read.

## Chat slips (CLAUDE.md hard rules, restated for this use)

A slip assembled in chat is not a coupon and has no gates.

1. **Say no first.** `build_slip.py`'s first line says how many of the
   requested slips the day gives; when it gives fewer than asked, that line is
   the answer's first line ("dzień cienki - masz jeden kupon" / "dziś
   żadnego"). Never fill the request with weaker legs without saying so.
2. **"Supports" = the leg's own statistics and the analysts' reads.** A leg's
   measured chance is its confidence (it carries its line evidence - offset
   and price-band cap), a `price_gap` leg at its price, never above it; a leg a
   read refuses is out. No market family is preferred, counted or quoted - the
   families' record "on the plus" (`family_record.json`) was removed by the
   operator 2026-10-31 ("the pipeline exists to analyse deeply and stand on
   statistics").
3. **Every table the operator may stake from** carries that measured chance (a
   `price_gap` leg at its price, never its confidence) with 1/odds beside it -
   in **every** re-summary, not only the first - and no "na minusie" label
   (operator 2026-10-15). The product of confidences is never the headline.
4. **Name each leg in Superbet's words**: `superbet_market: superbet_selection`
   from `11_coupon.json` (`bet.sofa.superbet_names.names` for a leg of another
   artifact), never a paraphrase like "Seattle +1.5 w 3. tercji".
5. **Never a combined / Bet Builder / parlay price**, never `odds_if_product`
   as one - Superbet does not price a slip as the product of its legs (markup
   measured 8.8-19.6%). One exception (operator 2026-10-26): a chat slip's
   builder row reads "<product> iloczyn" and the target is counted on that
   product - relayed as printed, never called "kurs", never our price; "kurs
   buildera: sprawdź na ekranie Superbetu". `--check` prints no product.
6. **No stake sizing, no placement.** The stake is the operator's.
7. **Judge the decision, never the result.** A settled win or loss never enters
   the next decision.

## Building a slip to a target price

When the operator asks for a slip (AKO) "na ~X" - in a time window ("od 10
do 12"), or several disjoint ones - build it with the script, never by hand,
have every leg read, and relay the script's first line first. Operator
2026-10-20: search **every market**, the analysts read the
chosen legs, a refused leg is replaced by the next best and that one is read.
One search over every leg (operator 2026-10-26; the family preference and
`--any-family` / `--allow-rest` are gone since 2026-10-31 - still accepted as
no-ops).

**The least-loss flow** (operator's go 2026-10-31; backtest walk-forward
10-13..10-26, hold-out 10-27..10-30, morning print prices, 12% turnover tax -
`docs/sofa/evidence/slip_flow_backtest_2026-10-31.md`): **no flow clears zero
after tax**. Hold-out after tax: singles −16.6%, random 2-leg −19.0%, 3 legs
−30.2%, 2-4 legs at ~3 −28.5%, the old objective at up to 5 legs −31.5%; a
coupon leg returns ~0.946 of its price (hit 0.782 vs 1/odds 0.827, 49,189
legs 10-20..10-30). So:

- **2 legs by default** (`--max-legs` default 2). Raise it only when the
  operator asks ("3 nogi"); the script then prints the measured cost of each
  leg (0.88 × 0.946^n − 1). Never raise it to reach a target.
- **Target out of reach of the limit** (e.g. ~4 with 2 legs of at most 2.00):
  the first line says so - "Na ~4 trzeba 3 nóg - każda kolejna noga to ok.
  −5% więcej; z 2 nogami najbliżej ~X" - and the slip is the closest under
  the target (the highest product the limit's legs reach, the best chance at
  it), marked "Cel ~X NIE osiągnięty"; exit 1. Never a silent extra leg.
- **Bet Builders off by default.** `--builders` only on the operator's
  request (the day's Bet Builders as one option of their match; odds in the
  search = the product of its legs' single prices - the operator's rule
  2026-10-26; chance = `combined_probability` lowered by each leg's own price
  cap; a refusal of any leg drops it; the row reads "<product> iloczyn", the
  builder line says Superbet paid 0.85-0.99 of the product, measured
  2026-10-28). With it the script names the builders' measured loss: −16.6%
  (dev, n 88) / −45.8% (hold-out, n 10) after tax at 0.90 × product.
- **Low margin preferred in a near-tie**: a leg of a two-sided ladder with
  overround < 0.08 gains +0.25% relative chance in the search only
  (`LOW_MARGIN_TIE`; measured +2.2 pp [+0.1, +4.2] within market on dev, not
  held out - so never a gate); column "marża" ("1-str." = one-sided).
- **The honest money line** replaces any return computed from our
  confidence: "oczekiwany zwrot po podatku ≈ 0,88 × 0,946^n − 1 = −X% stawki
  (zmierzone: nogi kuponu 10-20..10-30, n 49 189; podatek 12%)" - line 2 and
  every slip header; a single below 1/0.88 = 1.136 reads "wygrana zwraca
  mniej niż gotówka".

**What the script shows** (read every column into the answer): per leg
measured chance beside 1/odds, "pewność < 1/kurs" (confidence below the
price), the dossier's "zestawienie"
(`style.matchup`: own k/n vs what the opponent concedes / both sides' games /
league share); a leg starting within 45 min is marked ⚠ (a read round takes
20-30 min), and "marża" (the leg's ladder overround, bold below 8%; "1-str."
one-sided). The slip header gives the measured chance beside 1/price and the
money line (0.88 × 0.946^n − 1, measured - never chance × payout).

**Before running it:** `build_slip.py` is NOT read-only - with
`--read-set-dir` it asks Sofascore through the
bridge (h2h, lineups) and writes dossiers. Run `.venv/bin/python
scripts/sofa/ensure_bridge.py` first, and always pass `--md-out
runs/sofa/<d>/slips/<HHMM>.md` (`mkdir -p runs/sofa/<d>/slips`) so a staked
slip can be traced.

**The search** (`src/bet/sofa/slip_builder.py`): legs of `11_coupon.json`
singles, not started (15 min margin, = the analysts' started-skip), odds 1.10-2.00, one per match, at
most `--max-legs` (default 2); a leg's measured chance = min(confidence, 1/odds
for a leg more than `price_gap.GAP` above its price or flagged `price_gap`). An exact multiple-choice knapsack
maximises the slip's measured chance under "price product >= target" - which
picks the fewest legs (every odds band loses about alike per leg,
10-13..10-19) - with the low-margin near-tie-break above. A leg a veto or a WATCH / NO_BET read refuses (`vetoes.json`,
`reads.json`, the slip's `*_slip.json`, or carried) never enters, so a re-run after a merge takes the
next best leg (a refusal also drops the refused leg's harder rungs).

**The loop** (main session; at most 3 rounds). Two clocks: `<hhmm>` of the
analysts' reports = the request's local time, fixed for all its rounds (a
second slip of the day never collides with the first); `<HHMM>` of `--md-out`
= now, local, each round.

1. Build and write the read set (`ensure_bridge.py` first):
   ```bash
   .venv/bin/python scripts/sofa/ensure_bridge.py
   mkdir -p runs/sofa/<d>/slips
   PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py --date <d> --target <X> \
       [--start-from HH:MM --start-to HH:MM] [--slips N] [--max-legs N] [--builders] \
       --read-set-dir runs/sofa/<d>/read_set_slip --md-out runs/sofa/<d>/slips/<HHMM>.md
   ```
   (`--reserve 1` also reads the next disjoint slip ahead; off by default -
   the knapsack re-optimises globally, so a replacement rarely comes from it.)
2. **Done** when it prints "Każda noga kuponów ma KEEP analityka" (every
   leg kept by this slip's own read within 3 h; a morning or older KEEP is
   listed to read again) - go to the
   answer. No slip at all ("do przeczytania: nic - brak kuponu"): answer with
   the first line and stop. Otherwise, for each `read_set_slip_<sport>.json`
   it lists, spawn that sport's analyst (`sofa-analyst-football` /
   `sofa-analyst-tennis` / `sofa-analyst-sport` with the sport named) in the
   **foreground**, independent sports in one message, with exactly this
   prompt and nothing else:
   ```
   date <d>; run_id -; sport <s>; read set: runs/sofa/<d>/read_set_slip/read_set_slip_<s>.json; write your report to: runs/sofa/<d>/<d>_analiza_<s>_kupon_<hhmm>_<round>.md; kupon z czatu - waliduj z --slip; gdy powód dotyczy zmiennej, nie progu, daj odczyt dla progu, który czytasz
   ```
3. Merge what each analyst wrote - **the path on its `raport:` line**, never
   the one you named (it writes `_r<n>` on a collision):
   `merge_reads.py --date <d> --slip --author analyst --report <path> [--report ...] --read-set <each read_set_slip_<sport>.json>`.
   `--slip` writes `reads_slip.json` / `vetoes_slip.json`: the slip honours
   them, the coupon never reads them (a picks request does not touch the
   coupon). Exit 1 with `UNMATCHED_READ` / `LEG_WITHOUT_READ` = a read keyed
   to no leg or a leg without a read: send that analyst the listed legs again
   (same round). Exit 2 = refused, nothing merged (a removal without a fact):
   relaunch that analyst with the findings and the next `_r<n>`.
4. Back to 1. A refused leg is gone, and so are its harder rungs (a WATCH on
   OVER 7.5 also drops OVER 8.5); the knapsack searches first over the legs
   this slip's read kept, and takes a leg still to read only when those
   cannot reach the target (operator 2026-10-21), then lists its unread legs. After round 3, name every leg still unread as
   unread; never present one as read.

**Relay** (Polish): line 1 = the script's first line (the "say no first"
answer: how many of the requested slips the day gives, or "Na ~X trzeba N
nóg ..."); line 2 = the script's money line ("Oczekiwany zwrot po podatku ≈
..."), and with a raised limit / `--builders` its cost lines; then a warning when the window starts
< 30 min from the request. Then each slip's table as printed - Superbet's
words, start in local time (⚠ within 45 min), measured chance beside 1/odds,
"pewność < 1/kurs", marża, zestawienie, the header's
chance vs 1/price and its money line ("wygrana zwraca mniej niż gotówka" on a
single below 1.136), "Cel ~X NIE osiągnięty" where printed, a builder's "<product>
iloczyn" with the 0.85-0.99 line, the `--md-out` path, the read
("KEEP" = read for this slip within 3 h; "KEEP (10:42)" = a slip read of an
earlier request at that time; "KEEP (kupon dnia)" = the day's morning read -
both possibly before lineups, so neither counts as read: the script hands both
to the analysts like an unread leg, operator 2026-10-21), price age, the
"Uwaga: N z M nóg jednego rynku" line where printed (a warning, never a
reason to swap a leg by hand) - the stale-price line when printed (the screen's price decides; the day's
coupon is never rebuilt for a chat slip), and which legs fell out on which
read and what replaced them. No slip price and no stake: the script's "Cel ~X
osiągnięty" line carries no number; "kurs kuponu: sprawdź na ekranie
Superbetu". No "na minusie" labels. Exit 0 = all requested slips found, 1 =
fewer, 2 = no coupon / bad arguments.
Tests `tests/sofa/test_slip_builder.py`.

## Checking the operator's own Bet Builder (`--check`)

When the operator sends a screenshot of a Bet Builder they built themselves, never
multiply confidences by hand - run:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py --date <d> \
    --check "<mecz>|<superbet_market>|<superbet_selection>" [--check ...] [--screen-odds 2.25] \
    --md-out runs/sofa/<d>/slips/<HHMM>_check.md
```

No `--target`; one match only (legs of several matches = an error).
Read-only (it writes no read set; only `--md-out`). Each leg
is looked up in `11_coupon.json` singles, then `removed_by_reads`, then
`08_confidence*.json` legs - a refused / removed leg prints its refusal or read
reason. Per leg: measured chance vs 1/odds, zestawienie; the legs'
joint k/n in both sides' games where all hit together - **a frequency, never
a probability**; the screen price's 1/kurs. **No product of chances.** A leg
found nowhere has no numbers - "brak dowodu", never filled in. Exit 0 all legs
found, 1 some leg not found, 2 failure.

**Relay:** first line = the script's bold line; then its table as printed;
then the legs whose measured chance is below 1/odds, named in Superbet's
words. Never "dobre" / "warto": the screen price decides, our numbers say
which legs sit below their price. Analysts only if the operator asks.

## Four cases

| the leg is | the number to compare with |
|---|---|
| a row of the day (`runs/sofa/<d>/11_coupon.json` leg, or a `05_sheet.json` rung) | its `confidence` (calibrated, lowered by line evidence) and x = confidence x `offered_odds` (>= 0.90 prints), at the price on the screen; `forecast_p` is "model", uncalibrated; sample k/n beside. `p_bar`, `required_odds`, `surplus` are the old VALUE selector's numbers, anti-selective (surplus > +0.40 suspect) - never the verdict |
| not a row (unread market, see `market_coverage.md`) | only an operator-typed consensus through `audit_slip.py`, or `--market sample` on a Sofascore k/n from `03_samples.json`; label it outside the pipeline |
| the operator's own Bet Builder (screenshot) | `build_slip.py --check` (section above) - never the product of confidences by hand |
| a Bet Builder of the day | sofa prints no builder price: legs, `combined_probability` (the lower of the product and the empirical joint) and "kurs buildera: sprawdź na ekranie Superbetu". `odds_after_haircut` / `ev_after_haircut` are internal (stakeable test, `BUILDER_CORRELATION_HAIRCUT` 0.12), never quoted as a price. A screen price the operator gives wins outright (`confidence.builder_odds`): `combined_probability x screen_odds - 1`, shown as his note |

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
