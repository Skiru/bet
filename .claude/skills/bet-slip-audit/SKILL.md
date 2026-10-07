---
name: bet-slip-audit
description: Price a Superbet leg, Bet Builder or SUPERBETS slip before recommending it, and refuse the ones that cannot be worth their price - using sofa's own confidence (11_coupon.json) where the leg is a row of the day, and an outside price only when the operator types it in, never fetched from a provider (bzzoiro is not a sofa data source). Use when reviewing a slip the operator screenshotted, a boosted SUPERBETS price, a Bet Builder draft, or any single where a price is known - especially "drużyna - liczba goli powyżej 0.5", "gole 1-3 w każdej połowie", per-team corners/fouls/shots lines, and player props. Built from the 2026-08-30/31 ledger (archived pipeline), where nine of twenty placed bets lost and only two of the thirteen priceable ones were ever worth taking.
---

# Audit the price before you audit the fixture

> For a **Bet Builder** slip, this audit is the second half of the job. The
> first half is `docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md` §39-§44: correlation,
> the contradiction test (a concrete scoreline that satisfies every leg at
> once), the common-outcome test, and the builder score -- which is explicitly
> *not* the product of the leg probabilities. A slip that is correctly priced
> and internally contradictory is still not a bet.

## Where this sits relative to `sofa`

This skill is about a price on a screen, and it applies whether or not the
pipeline generated a row for it. It is **outside the pipeline**: no stage calls
it, it reads no sofa artifact, and it must say so in its answer.

**Data rule (CLAUDE.md, "Hard rules"): Sofascore and Superbet only.** bzzoiro -
its MCP tools, its API, its "~88-book consensus" - is NOT a source here and is
never called by this skill or its agents. The `audit_slip.py` tool does no
network at all: every outside number (a consensus 1X2, a totals line) is a
number the OPERATOR types on its command line, and the answer says "operator-
supplied". Without such numbers the honest answer is "no evidence" (below), or
`--market sample` on a Sofascore sample from the day's `03_samples.json`.

- **The leg is a row of the day** (a leg of `runs/sofa/<d>/11_coupon.json`, or a
  rung of `05_sheet.json`). Then `sofa` has already answered *how often does
  this happen*: read the leg's `confidence` (the lower bound of the measured
  rate, lowered by line evidence), `x = confidence × odds` (>= 0.90 prints),
  `forecast_p` ("model", uncalibrated) and the sample k/n - at the price the
  operator really sees. **`p_bar`, `required_odds`, `surplus` and VALUE are the
  old priced selector's numbers (`06_coupon.json`), anti-selective by
  construction (a surplus above +0.40 is suspect), and are not the verdict.**
  What this skill adds is the structural refusals below, which need no fixture
  at all, and - if the operator types one - an outside price to compare with.
- **The row does not exist.** `unmapped_markets` ran to ~28,000 lines on
  2026-10-07; sofa classifies a fraction of Superbet's screen (1X2, double
  chance, BTTS, match winner ... are not modelled yet). Then this skill is the
  only arithmetic available, and it must label itself as outside the pipeline.
- **It is a Bet Builder.** sofa prints no builder price: the PDF shows the legs,
  the `combined_probability` (the lower of the product and the empirical
  joint) and "kurs buildera: sprawdź na ekranie Superbetu". The haircut price
  in `odds_after_haircut` / `ev_after_haircut` is internal (the stakeable test,
  measured markup 8.8–19.6%) and is never quoted back as a price. **If the
  operator gives the screen price, it wins outright** (`confidence.builder_odds`:
  a measurement beats an estimate) and the question becomes
  `combined_probability × screen_odds − 1`, shown as his note, not ours.
- **`scripts/sofa/audit_slip.py`** (`bet.sofa.slip_audit`, moved from the
  retired `simple` tree on 2026-10-05) is the arithmetic below; run it as
  `.venv/bin/python scripts/sofa/audit_slip.py ...` (it adds `src` to the path
  itself). Tests: `tests/sofa/test_slip_audit.py`.

## What this is for

`sofa`'s CONFIDENCE answers *how often does this actually happen* (and the price
is only the betting condition x >= 0.90). It has no second book to compare
against, and the question that decided the 2026-08-30/31 results was exactly
that: **is the number on the Superbet screen bigger than the number this bet is
worth, measured somewhere other than at Superbet?**

Twenty bets were placed across those two days. Nine lost. Thirteen are football
fixtures the archived pipeline could price against an ~88-bookmaker consensus
(bzzoiro, then; not a sofa source), and reconstructing all thirteen gave a
result the win/loss column completely hides:

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

1. **Get the number to compare against.** A leg of the day: its `confidence` and
   x in `11_coupon.json`. Otherwise an outside consensus (1X2, over/under
   2.5, ideally BTTS) **that the operator types in** - never fetched by this
   skill. None: stop at "no evidence" or use `--market sample`.
2. **Fit and compare.** Run the tool below. It devigs, fits the match rate, and
   reports the edge. (It fits the market; it does not disagree with it.)
3. **Only then** read form, lineups, referee, absences. Those change a *fair*
   bet into a good one or a bad one. They cannot rescue a price below fair.

```bash
# team to score, from a consensus the operator supplied (typed, not fetched)
.venv/bin/python scripts/sofa/audit_slip.py --price 1.48 \
    --market team_to_score --side away \
    --home-win 1.50 --draw 4.43 --away-win 5.45 --over-25 1.52 --under-25 2.41

# a range builder
.venv/bin/python scripts/sofa/audit_slip.py --price 2.05 \
    --market 1h_over_0_5_under_2_5_and_2h_over_0_5 \
    --home-win 7.47 --draw 4.23 --away-win 1.45 --over-25 2.01 --under-25 1.81

# a market with no outside line: Wilson bound off a real sample
.venv/bin/python scripts/sofa/audit_slip.py --price 1.42 --market sample --hits 5 --sample-size 6

# also report a slip's hard price floor: repeat --leg-probability once per leg
```

The three examples were run on 2026-10-07 and answer REJECT (edge -2.9%, -5.3%,
-26.8%). `--market sample` is the weaker answer and labels itself as such. Use
it for corners, fouls, shots and player props (the k/n from `03_samples.json`),
and never dress it up as the market's opinion.

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

This is a house market. Superbet's price for a side to score sat at or under
the ~88-bookmaker consensus of the time, consistently. Treat any such leg as REJECT until a
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

### 4. Where the edge is not, and the one place it is

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

### 5. Player props die on volume, not on the player

Lassana Coulibaly to commit a foul lost. It was not a bad read: 20 of his last
30 starts had one, ~1.4 fouls per 90. It was a **67% leg inside a slip paying
1.50**. Before quoting a player prop, get the team's own rate for the underlying
event — Lecce committed 9 fouls all match, spread over 16 players. A prop needs
minutes *and* team volume; `lineup_status` only covers the first.

### 6. Three of the losses were on fixtures the evidence could not see

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
See [`reference/coverage.md`](reference/coverage.md) (historical).

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
- Nothing here overrides the hard rules in `sofa-analysis-core`: no combined
  price of your own, no stake sizing, no automated placement.
- The r-table and the base rates were measured on the archived pipeline's
  sample (bzzoiro data, 2026-01..08). They are orders of magnitude, **not
  priors you may substitute for a `sofa` row's `centre`** or for its
  confidence.

## Reference

- [`reference/ledger-2026-08-30-31.md`](reference/ledger-2026-08-30-31.md) —
  every one of the twenty bets, with its price, its fair price, and why.
- [`reference/base-rates.md`](reference/base-rates.md) — the measured tables:
  7,516 matches for goals and halves, 700 for corners, shots and fouls.
- [`reference/coverage.md`](reference/coverage.md) — historical: what the
  archived source could and could not price in 2026-08, and how to say "no
  evidence". Nothing there may be fetched today.
- `src/bet/sofa/slip_audit.py` — the arithmetic, with tests in
  `tests/sofa/test_slip_audit.py` that carry the ledger as a regression.
  Offline, reads no `sofa` artifact. (Its docstring still names bzzoiro as the
  consensus source; the operator-typed rule above governs.)
- `src/bet/sofa/confidence.py` — `sofa`'s own answer for a Bet Builder:
  `BUILDER_CORRELATION_HAIRCUT`, `QUANTITY_FAMILIES`, `builder_odds` (where a
  known screen price beats the estimate), and `is_stakeable`.
- `.claude/skills/sofa-pipeline/SKILL.md` — the rules in force (confidence,
  line evidence, the price only lowering it).
