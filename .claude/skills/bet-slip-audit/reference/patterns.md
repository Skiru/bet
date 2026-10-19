# The six ledger patterns, in full

> Read this when a slip matches one of the six patterns in `../SKILL.md` and you
> need the numbers behind it. Measured on the archived pipeline's 2026-08-30/31
> ledger and its sample; "the consensus" is the ~88-book consensus of that time
> (bzzoiro, archived - never a sofa source, never fetched today). Orders of
> magnitude, not priors for a sofa row.

## 1. Five bets, one market, none of them priced

Five of the thirteen were `drużyna – liczba goli powyżej 0.5` at 1.40–1.60.
Against the consensus: **−2.9%, −5.6%, −0.1%, −2.0%, −3.4%**. Not one had an
edge. Three lost, two won, and the two that won were no better as bets.

This is a house market. Superbet's price for a side to score sat at or under
the ~88-bookmaker consensus of the time, consistently. Treat any such leg as REJECT until a
devigged number says otherwise — and expect it not to.

The trap that made them look good: the historic scoring rate. Brommapojkarna had
scored in twelve straight; the consensus still said 64.3% against a price asking
70%. **A Wilson bound on past frequency is not an edge until it is compared with
the devigged price for *this* fixture.** Past frequency does not condition on the
opponent, the venue, or the day.

## 2. The winner that was the worst bet on the board

The Honduras slip — `1-3 goals in each half` + `2-6 goals` at 1.80 — won. Its
second leg is *implied by* its first, so it is one event, worth 48.6%, i.e.
2.06. At 1.80 it returned −12.5% in expectation. The Guatemala slip was the same
structure at 2.00 and lost.

Identical bets, opposite results, both bad. When a report says a bet "worked",
that is a fact about the day, not about the decision. Never let a settled result
into the reasoning for the next one.

## 3. Correlation runs one way and not the other

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

The loose claim that "corners, cards, fouls and shots in one match are strongly
positively correlated" is right for **shots and goals** and then some, not true
for **corners** in this sample, and points the wrong way for **fouls**. Cards
were not sampled, so the card half is untested here, not refuted.

`sofa` handles the part that matters structurally: `confidence.py` takes at
most one leg per **quantity family**, because a team's goals and the match
total are one quantity counted twice (measured lambda 2.165, up to 8.37), and
it refuses a builder whose legs disagree about tempo — `goals UNDER` with
`corners OVER` is negatively correlated, so the product *overstates* the joint
and the slip's EV would be reported too high. What it does not do is claim the
product is the price: that is the 12% haircut's job.

The shared conclusion — never print a combined price of your own — stands.
Treat the r-table above as the number to quote when the question is which legs
actually move together.

## 4. Where the edge is not, and the one place it is

Thirty of the archived run's own captured Superbet prices for `goals_total`
(over/under 1.5, 2.5 and 3.5) were priced against the consensus of the day for
the same fixture. Result: **0 TAKE, 1 MARGINAL, 29 REJECT**, with edges spread between
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
Monaco's identical-looking ⚡ moved a −43% bet to a −36% bet. The current
evidence on boosts is sofa's own: `run_boosts.py` snapshots them (`10_boosts.json`),
`audit_boosts.py --from --to` grades them.

**Markets the consensus does not carry** — per-team corners, fouls, shots,
player props — are the other place, because there is no consensus to be shaded
against. That is also where the evidence is weakest, so the bar is a real
sample with an extreme rate: Getafe's away fouls were 8 of 8 with a mean of
17.2 against a 45% league baseline, and its Wilson lower bound of 67.6% still
cleared the 1.73 price. Beşiktaş's corners were 5 of 6, which reads the same
way and is not the same thing at all — lower bound 43.6% against a price asking
70.4%.

## 5. Player props die on volume, not on the player

Lassana Coulibaly to commit a foul lost. It was not a bad read: 20 of his last
30 starts had one, ~1.4 fouls per 90. It was a **67% leg inside a slip paying
1.50**. Before quoting a player prop, get the team's own rate for the underlying
event — Lecce committed 9 fouls all match, spread over 16 players. A prop needs
minutes *and* team volume; `lineup_status` only covers the first.

## 6. Three of the losses were on fixtures the evidence could not see

On 2026-08-30/31 the then-source (bzzoiro, 83 leagues) did not cover Croatian
HNL, the Azerbaijani top flight, Guatemala or Honduras; four of the twenty bets
were in those leagues and a fifth (Real Madrid–Malaga) was not in the feed at
all. Three of those five lost. Coverage was also per-fixture: Inter Turku–KuPS
sat in a covered league and returned no statistics at all. The sofa
equivalents are the same shape: a fixture RESOLVE could not attach to a
Sofascore event (`NO_MATCHING_EVENT`), a sample with a gap, a key with no curve
and no measured lines (`NO_LINE_EVIDENCE`), a match `UNVERIFIED` by
FIXTURE_CHECK. There is no tennis odds source at all - sofa reads Sofascore and
Superbet only - so a tennis leg is priceable only against sofa's own
confidence and Superbet's offer.

When there is no number to compare against and no sample, say **"no evidence"**
and stop. Do not substitute a league-wide constant and present it as a read.
See [`coverage.md`](coverage.md) (historical).

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
- Nothing here overrides the hard rules in `../SKILL.md`: no combined
  price of your own, no stake sizing, no automated placement.
- The r-table and the base rates were measured on the archived pipeline's
  sample (bzzoiro data, 2026-01..08). They are orders of magnitude, **not
  priors you may substitute for a `sofa` row's `centre`** or for its
  confidence.

