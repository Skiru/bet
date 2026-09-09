# Evidence rules — what counts, what merely informs, what is forbidden

## The hierarchy (method §64, §80)

```
CORE     — the scoped sample (hits/n at this line, its distribution), the
           market definition, current surface/format, opponent-adjusted read
SUPPORT  — season xG, referee profile, h2h (decayed), ranking/table, tipsters
CONTEXT  — travel, weather, schedule, narrative, market movement
```

`CORE > SUPPORT > CONTEXT`, never the reverse. SUPPORT and CONTEXT may
**downgrade or veto**. Only CORE produces `p_low`, and only code computes it.

## Signals, and the ceiling on each

| Signal | Where | May promote? | May demote/veto? | Enters `p_low`? |
|---|---|---|---|---|
| Sample (`hits/n`, distribution) | row, dossier | — (it *is* the tier) | — | yes, by code only |
| `cross_provider_agreement` | row | `AGREE` is part of the tier rule | `DISAGREE` caps at `LEAN` | no |
| `market_signal` | row / MCP | **one step, corners_total & goals_total only, CONFIRMS with both probabilities** | no (a market disagreeing is the ordinary case) | never |
| Superbet price / availability | row, offer | no — changes *recommendation order* only | `LINE_NOT_OFFERED` = no bet | never |
| Tipsters | row, signal file | never | never on its own; a sentence | never |
| Referee | dossier | never | yes (cards/fouls) | only via code's blend on card totals |
| Absences / lineups | dossier, MCP | never | yes; prop on unavailable player = void | no |
| Stakes: round, second leg, derby, table | MCP `get_match_detail`, standings | never | yes | no |
| Season xG (`season_form`) | dossier | never | yes (finishing/regression) | no |
| Web (order of play, injury news, weather) | WebFetch, 2 domains | never | yes; postponement = veto | never |
| Settled results of past coupons | backtest | never | inform your kill-case library | never |

## Independence (method §28, §71)

Two numbers derived from the same public data are one signal. `espn-football`
agreeing with `bzzoiro` is a second **transcription**, not a second measurement
(it agrees on 92–98% of points where both report). The bzzoiro model and the
bookmaker market are fitted to overlapping information. Five tipsters quoting
the same preview are one opinion. Say how many *independent* sources actually
support a read; never write "five sources" for one.

## Sample integrity checks (do them before anything else)

1. **Split.** `a/b/h2h` counts from the dossier. For a total, `a == 0` or
   `b == 0` means the total was estimated from **one** side — cap at `LEAN`
   and say so. One side with ≤3 retained observations after `sample_excluded`
   reads as `HIGH` confidence and is not.
2. **Exclusions.** `sample_excluded` says what was removed. Large
   `PRE_SEASON_FRIENDLY` / `STALE_SEASON` counts mean a side is early in its
   season; `SURFACE_MISMATCH` in tennis can empty a side entirely (the
   Badosa–Gauff case: n=9 was 100% Gauff). `STALE_H2H` is 12 months; but
   **`STALE_SEASON` cannot fire on h2h observations** (no competition/season
   id on that route) so a 15-month-old h2h can sit in a current-season sample.
3. **Conflicts.** `DISAGREE` with the disagreement **on the line** (one
   provider 6, the other 8, line 6.5) means the row passes only under the
   favourable reading — `DATA_CONFLICT`, downgrade. `CONFLICT_ON_LINE` in
   `sample_excluded` means the code already dropped such a point.
4. **Estimand.** Does the market settle what the sample measures? Cards
   markets settle *points* (yellow 1, straight red 2, second yellow 3) →
   `cards_points_*`; a tennis total is own-plus-own, never a pooled mean;
   `both_teams_over` has no sample at all; a per-team line needs the right
   `team_name`.
5. **Duplicates.** The same match appearing in `a`, `b` and `h2h` is
   collapsed by (bucket, day) before counting. `n` counts matches, not
   observations.

## Distribution over mean (method §15, §16, §37, §88)

Report `typical Q25–Q75, tail to max`, never "the average is 6". Then:

- **Line vs mode.** A rung on the sample's mode is the least informative rung
  and the one whose hit rate moves most with one observation. Prefer the rung
  a half-point *beyond* the sample's extreme when the price still clears.
- **Sample crosses the line.** For UNDER, `sample_max > line` is a demonstrated
  failure at that rung; for OVER, `sample_min < line`. Say how many times.
- **Mean ≫ median** (right skew) argues against an OVER built on the mean and
  for an UNDER built on the median; check which observations make the gap and
  whether they are the same opponent class or competition as tonight.
- **Tail risk both ways.** For every OVER: is there a realistic much-higher
  scenario? For UNDER: a realistic much-lower one? A team that can produce
  10+ corners alone kills a match-total UNDER (Porto–Arouca 12–2).
- **Ladder.** Read all rungs the book posts (`superbet_offer`), not only the
  sheet's chosen one. `RUNG_SEPARATED_BY_MODEL` means adjacent rungs share the
  same `hits/n`; the only thing separating their prices is the count model.

## Price (method §26, §38, §89, §90, §104)

- Decide the line **blind** (which rung would you pick on statistics alone),
  then look at the price.
- The bar is `TIER_MARGIN / p_shrunk` and is on the comparison artifact as
  `min_acceptable_odds`. Report **probability quality** and **value quality**
  separately: `p_central 0.87 at 1.85` can be HIGH probability / HIGH value,
  `0.94 at 1.27` HIGH probability / no value.
- A short price is not a reason to drop a candidate; grade it `WATCH` and say
  the number that would make it a bet.
- Where the odds feed carries the market (goals, 1X2, BTTS) devig the
  consensus (`scripts/simple/audit_slip.py`) and compare — past frequency is
  not an edge until compared with the devigged price for *this* fixture. Where
  it does not (corners, cards, fouls, shots, props, all tennis) `p_*` is all
  there is; say it is weaker.
- Never quote a scraped price. `market_price` from the artifact or MCP is a
  reference across ~88 books; **Superbet is not among them**.

## Ladder gates the coupon already applies (do not duplicate, do cite)

- `needs_review` (`MAX_MARKET_DISAGREEMENT` 0.25): sample and book disagree
  about *how likely* at this rung — annotation only, because that is what an
  edge looks like.
- Ladder σ demotion (`MAX_LADDER_SIGMA` 1.25): sample and book disagree about
  *where the market sits* — the sample describes a different fixture, venue or
  competition. When you see it, look for the reason (surface, opponent class,
  competition mix) and name it.
- Low-line UNDER ≤ 1.5 pushed to the bottom; youth/friendly competitions
  excluded; kickoff passed excluded.

## Same-match correlation (measured, base-rates.md)

| pair | r |
|---|---|
| goals ↔ shots on target | +0.55 |
| corners ↔ shots on target | +0.16 |
| goals ↔ corners | +0.04 |
| corners ↔ fouls | −0.12 |
| goals ↔ fouls | −0.13 |

Legs pairing "lots of fouls" with "lots of goals" pull in opposite directions.
Tennis length markets (sets, games, aces, DFs) all grow together — a short
match settles every UNDER at once. Never multiply; describe the shared
mechanism and its direction (method §91), and name the scenario that kills all
legs at once (§92, §93).

## What a settled result may and may not teach

Post-mortem categories (method §47, §106): `DATA_ERROR, SOURCE_ERROR,
LINE_ERROR, MARKET_DEFINITION_ERROR, MATCHUP_ERROR, GAME_SCRIPT_ERROR,
SQUAD_ERROR, REFEREE_ERROR, MODEL_ERROR, CORRELATION_ERROR, PURE_VARIANCE`.
A won bet with a negative edge is still a bad decision; a lost bet in a category
that wins 84% is what 84% looks like. `scripts/simple/backtest_slate.py` settles
football rows against real results — use it to check a *class* of read, never
one row.
