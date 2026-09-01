---
name: bet-slip-audit
description: Price a Superbet leg, Bet Builder or SUPERBETS slip against the bzzoiro consensus before recommending it, and refuse the ones that cannot be worth their price. Use when reviewing a proposed coupon, a Bet Builder draft, a slip the operator screenshotted, or any single where a price is known - especially "drużyna - liczba goli powyżej 0.5", "gole 1-3 w każdej połowie", per-team corners/fouls/shots lines, and player props. Built from the 2026-08-30/31 ledger, where nine of twenty placed bets lost and only two of the thirteen priceable ones were ever worth taking.
---

# Audit the price before you audit the fixture

## What this is for

`analyze.py` answers *how often has this happened*. `bet_builder_draft` answers
*which legs are worth assembling*. Neither answers the question that decided the
2026-08-30/31 results: **is the number on the Superbet screen bigger than the
number this bet is worth?**

Twenty bets were placed across those two days. Nine lost. Thirteen are football
fixtures bzzoiro prices, and reconstructing all thirteen against its consensus
gave a result the win/loss column completely hides:

| | count | settled |
|---|---|---|
| worth their price (edge ≥ +2pp) | **2** | both won |
| at or below fair | **11** | 6 lost, **5 won anyway** |

The losses were not unlucky reads of good spots. With one exception they were
negative-expectation bets that had no edge to lose. And five winners were just
as badly priced and simply landed — including the **best-looking** slip on the
board, a Honduras builder at 1.80 on a 48.6% event, which was the single worst
bet of the twenty and won.

The full dissection of every leg is in
[`reference/ledger-2026-08-30-31.md`](reference/ledger-2026-08-30-31.md). Read
it once. It is the argument for everything below.

## The order of operations

Price first, fixture second. Reversing these is what produced the ledger: every
losing bet had a plausible team story behind it, and the story was true — KuPS
had scored in five straight, Brommapojkarna in twelve straight — and it did not
matter, because the price was already at or under fair.

1. **Get the consensus.** `mcp__bzzoiro__get_match_detail`, or
   `/events/{id}/odds/`, gives 1X2 plus over/under 1.5/2.5/3.5 plus BTTS.
2. **Fit and compare.** Run the tool below. It devigs, fits the match rate, and
   reports the edge.
3. **Only then** read form, lineups, referee, absences. Those change a *fair*
   bet into a good one or a bad one. They cannot rescue a price below fair.

```bash
# team to score, from the consensus block
python3 scripts/simple/audit_slip.py --price 1.48 \
    --market team_to_score --side away \
    --home-win 1.50 --draw 4.43 --away-win 5.45 --over-25 1.52 --under-25 2.41

# a range builder
python3 scripts/simple/audit_slip.py --price 2.05 \
    --market 1h_over_0_5_under_2_5_and_2h_over_0_5 \
    --home-win 7.47 --draw 4.23 --away-win 1.45 --over-25 2.01 --under-25 1.81

# a market the odds feed has no line for: Wilson bound off a real sample
python3 scripts/simple/audit_slip.py --price 1.42 --market sample --hits 5 --sample-size 6
```

`--market sample` is the weaker answer and labels itself as such. Use it for
corners, fouls, shots and player props, and never dress it up as the market's
opinion.

## Refusals you can make before reading the fixture

These hold for every match, so they cost nothing to check. Four of the nine
losses die here, before a single team is looked up: the Lecce 1.50 builder on
the slip floor, Sumgayit over 2.5 on the league baseline, and both range
builders (Lecce 2.05, Aurora 2.00) on the practical ceiling margin — though not
on the hard ceiling, which both clear by a few points.

| Market on the screen | Ceiling | Never take below |
|---|---|---|
| `gole 1-3 w każdej połowie` | **52.0%**, at a 3.6-goal match | **1.92** (in practice 2.10) |
| `1.poł powyżej 0.5` + `1.poł poniżej 2.5` + `2.poł powyżej 0.5` | **50.5%**, at a 3.9-goal match | **1.98** (in practice 2.15) |

Range markets are bounded above **by their own shape**. They are two-sided: a
dull match fails the lower bound and a wild one fails the upper. There is no
fixture anywhere that makes one a favourite, so "the goals will flow here" is an
argument *against* the bet as often as for it. `range_market_ceiling()` derives
these; do not restate them from memory, run it.

Three more that need no fixture reading:

- **A slip cannot be more likely than its weakest leg.** `slip_price_floor()`
  returns `1 / p_weakest`. If the offered price is at or under that floor, every
  other leg is being carried for nothing. The 2026-08-31 Lecce three-leg builder
  was offered at **1.50 against a floor of 1.49**.
- **A leg implied by another leg adds no risk and must add no price.** `1-3 in
  each half` already forces a `2-6` total. `redundant_legs()` spots the pairs it
  knows; a clean result means "none of the known pairs", not "independent".
- **Per-team counting lines at short prices are almost always below fair.**
  League-wide, a team clears 4.5 corners 48% of the time and 12.5 fouls 45% of
  the time. A 1.42 price is asking for 70%. That gap needs an *extreme*
  team-specific rate with a real sample behind it, not a hunch.

## The six patterns the ledger actually contains

### 1. Five bets, one market, none of them priced

Five of the thirteen were `drużyna – liczba goli powyżej 0.5` at 1.40–1.60.
Against the consensus: **−2.9%, −5.6%, −0.1%, −2.0%, −3.4%**. Not one had an
edge. Three lost, two won, and the two that won were no better as bets.

This is a house market. Superbet's price for a side to score sits at or under
the ~88-bookmaker consensus, consistently. Treat any such leg as REJECT until a
devigged number says otherwise — and expect it not to.

The trap that made them look good: the historic scoring rate. Brommapojkarna had
scored in twelve straight; the consensus still said 64.3% against a price asking
70%. **A Wilson bound on past frequency is not an edge until it is compared with
the devigged price for *this* fixture.** Past frequency does not condition on the
opponent, the venue, or the day.

### 2. The winner that was the worst bet on the board

The Honduras slip — `1-3 goals in each half` + `2-6 goals` at 1.80 — won. Its
second leg is *implied by* its first, so it is one event, worth 48.6%, i.e.
2.06. At 1.80 it returned −12.5% in expectation. The Guatemala slip was the same
structure at 2.00 and lost.

Identical bets, opposite results, both bad. When a report says a bet "worked",
that is a fact about the day, not about the decision. Never let a settled result
into the reasoning for the next one.

### 3. Correlation runs one way and not the other

Measured over 700 matches in ten leagues:

| pair | r |
|---|---|
| goals ↔ shots on target | **+0.55** |
| goals ↔ corners | **+0.04** |
| goals ↔ fouls | −0.13 |
| corners ↔ fouls | −0.12 |

So the standing warning that multiplying leg prices flatters a slip is right for
shots-and-goals and **wrong for corners**. A goal-heavy match is a
shot-heavy match; it is not a corner-heavy one — the losing side takes
*marginally more* corners than the winner (4.78 vs 4.70).

Concretely: the Napoli–Como slip's three legs jointly land 46.1% of the time
against a 41.1% product — a real +5pp lift, carried entirely by shots-and-goals.
The Monaco slip's corners-plus-BTTS legs land 20.7% against a 21.1% product —
independent, no lift at all.

`bet_builder_draft.py`, `coupons.py`, `build_coupons.py` and `run-day.md` all
carry the same sentence: "corners, cards, fouls and shots in one match are
strongly positively correlated". For **shots and goals** that is right and then
some. For **corners** it is not true in this sample, and for **fouls** it points
the wrong way. Cards were not sampled, so the card half of the claim is
untested here, not refuted.

Their shared *conclusion* — never print a combined price — stands regardless,
so the wording has been left alone rather than edited across eight files on the
strength of 700 matches. Treat the r-table above as the number to quote when
the question is which legs actually move together.

### 4. Where the edge is not, and the one place it is

Thirty of the run's own captured Superbet prices for `goals_total` (over/under
1.5, 2.5 and 3.5) were priced against the bzzoiro consensus for the same
fixture. Result: **0 TAKE, 1 MARGINAL, 29 REJECT**, with edges spread between
+0.3% and −8.7% and clustered near −3%.

That is not the audit being harsh. It is Superbet's margin on a mainline market,
measured. **On 1X2, BTTS and match goals you are not going to find an edge, and
looking for one is wasted effort.** Skip them.

The two positives on the ledger were the two exceptions to that, and they are
worth naming as the only places to look:

**The ⚡ SUPERBETS boost is worth about +12.6% on the price**, consistently:

| Slip | pre-boost | boosted | boost | EV before | EV after |
|---|---|---|---|---|---|
| Napoli–Como | 2.45 | 2.75 | +12.2% | −5.5% | **+6.1%** |
| Widzew–Lech | 2.35 | 2.67 | +13.6% | −14.0% | −2.3% |
| Raków–Jagiellonia | 2.15 | 2.42 | +12.6% | −17.0% | −6.6% |
| Monaco–Marseille | 3.10 | 3.45 | +11.3% | −42.6% | −36.2% |

So price the slip **at its un-boosted price first**. A boost of ~12% rescues a
slip sitting within roughly 11% of fair and does nothing at all for one sitting
30% below it. Napoli–Como is the whole pattern: −5.5% un-boosted, +6.1% boosted.
Monaco's identical-looking ⚡ moved a −43% bet to a −36% bet.

**Markets the consensus does not carry** — per-team corners, fouls, shots,
player props — are the other place, because there is no consensus to be shaded
against. That is also where the evidence is weakest, so the bar is a real
sample with an extreme rate: Getafe's away fouls were 8 of 8 with a mean of
17.2 against a 45% league baseline, and its Wilson lower bound of 67.6% still
cleared the 1.73 price. Beşiktaş's corners were 5 of 6, which reads the same
way and is not the same thing at all — lower bound 43.6% against a price asking
70.4%.

### 5. Player props die on volume, not on the player

Lassana Coulibaly to commit a foul lost. It was not a bad read: 20 of his last
30 starts had one, ~1.4 fouls per 90. It was a **67% leg inside a slip paying
1.50**. Before quoting a player prop, get the team's own rate for the underlying
event — Lecce committed 9 fouls all match, spread over 16 players. A prop needs
minutes *and* team volume; `lineup_status` only covers the first.

### 6. Three of the losses were on fixtures this project cannot see

bzzoiro covers **83 leagues**. Croatian HNL, the Azerbaijani top flight,
Guatemala and Honduras are not among them. Four of the twenty bets were in those
leagues and a fifth (Real Madrid–Malaga) is not in the feed at all. Three of
those five lost.

Coverage is also per-fixture, not just per-league: Inter Turku–KuPS is in a
covered league and returned **no `/stats/` at all** — no shots, no corners, no
possession. bzzoiro-tennis answers `addon_required`, so both tennis legs are
unpriceable too.

When there is no consensus and no stats, say **"no evidence"** and stop. Do not
substitute a league-wide constant and present it as a read. See
[`reference/coverage.md`](reference/coverage.md).

## What not to conclude from this

Thirteen bets is a tiny sample and the thresholds here were chosen after seeing
it. Specifically:

- `MINIMUM_EDGE = 0.02` is this project's tolerance, not a discovered constant.
- The +0.1% KuPS leg was as close to fair as anything gets and still lost. A
  refused bet that wins is not evidence the rule is wrong, and a taken bet that
  loses is not evidence it is right. **Judge the decision, never the result.**
- The Poisson fit assumes the two sides are independent, which under-predicts
  draws. It is anchored on the observed 1X2 *and* totals, so the bias lands in
  the fitted rates rather than in the answers — but a fit with no totals line
  barely pins the match rate, and the tool says so when you give it one.
- Nothing here overrides the existing hard rules in `bet-analyst.md`: no
  combined price, no stake sizing, no automated placement.

## Reference

- [`reference/ledger-2026-08-30-31.md`](reference/ledger-2026-08-30-31.md) —
  every one of the twenty bets, with its price, its fair price, and why.
- [`reference/base-rates.md`](reference/base-rates.md) — the measured tables:
  7,516 matches for goals and halves, 700 for corners, shots and fouls.
- [`reference/coverage.md`](reference/coverage.md) — what bzzoiro can and cannot
  price, and how to say so.
- `src/bet/simple_stats/slip_audit.py` — the arithmetic, with tests in
  `tests/simple_stats/test_slip_audit.py` that carry the ledger as a regression.
