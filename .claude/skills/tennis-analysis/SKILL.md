---
name: tennis-analysis
description: How to analyse one tennis match's length and serve markets (total games, total sets, a player's games won, aces and double faults, match and per player) from this pipeline's artifacts the way the tennis-modelling literature and the operator's method say it should be done - surface first, format (best-of-three vs best-of-five) second, opponent quality, serve/return decomposition, hold vs break, tie-break frequency, fatigue and schedule, H2H decay, distribution over mean, scoreline arithmetic for every rung, price last. Use when reading a tennis stats sheet, grading VALUE rows, writing analyst vetoes, or judging a tennis Bet Builder. Preloaded into bet-analyst-tennis.
---

# Tennis analysis — the method, mapped to what this pipeline actually holds

Read `bet-analysis-core` first (preloaded with you). Tennis differs from
football in three ways that change everything below: **there is no source of
record** (bzzoiro-tennis answers `402 addon_required`; no MCP, no market
signal, no model), so every row is `NO_REFERENCE_SOURCE` and can never be
`CALL`; the sample is **two individuals**, each with their own surface,
format and schedule history; and every market is a function of **match
length**, so a short match settles every UNDER at once.

Reference files — open at the step that needs them:

| File | Open when |
|---|---|
| `references/data-inventory.md` | what is measured, from which provider, which rungs Superbet posts, what is scoped out, what is *not* carried (opponent rank, round, hold %, tie-breaks) |
| `references/methodology.md` | the model behind a claim (point-based hierarchy, serve/return combination, surface and format effects, Elo, H2H decay, fatigue, retirements) |
| `references/market-playbook.md` | grading a specific market — drivers, scoreline arithmetic, kill cases |
| `references/event-protocol.md` | writing a match section — the master matrix, scenario matrix, template, verdict mapping |

The operator's method: `docs/SUPERBET_BET_BUILDER_METHOD_v3.md` — for tennis
open §7, §18, §24 (tennis A–D), §50, §65–§69, §72–§76, §81–§88, §101, §113–
§114 in this run and say so.

## What a tennis analyst here is *for*

The code already: scopes each side's sample to tonight's **surface**
(`SURFACE_MISMATCH`) and **format** (`MATCH_FORMAT_*`, best-of-five only for
men's slam main draw), collapses duplicates, prices `p_low`/`p_central`,
frames every match total as **own + own** (never the pooled mean) and
suppresses a total when one side has no scoped observation, shrinks toward a
market prior, picks the rung, prices against Superbet. **It cannot** see who
the opponent was in each observation (only a name), the player's ranking or
the opponent's, the round, the previous match's length or hours of rest, a
retirement risk, a qualifier's route, whether the ten hard-court matches were
at 250 level or slams. That is your job.

## The protocol — surface first, format second, price last (method §66, §113)

For every fixture with a `VALUE` row in `<date>_superbet_comparison.json`
(sport tennis) and any fixture you intend to veto:

1. **Identity, time, format, surface.** `event_list.competition` (`ATP …` /
   `WTA …`) decides BO5/BO3 and surface through the pins; if the competition
   is not pinned, say the sample is **unscoped**. Verify the match is on the
   order of play at the artifact's time via WebFetch (official tournament
   site + one independent domain); a time disagreement of hours is common and
   must be reported, not resolved by guessing. Round from the web (R1/R2/QF;
   qualifying is BO3 even at a slam).
2. **Sample integrity.** Per side: retained observations after
   `sample_excluded`, their surfaces and levels (`surface`, `match_level` on
   each observation), their dates, the `opponent` names. A side with 0–3
   retained on tonight's surface is not a sample. `data_gaps` names retired
   matches (`RET`) and identity refusals (`MISIDENTIFIED`). Estimand: is the
   total framed own+own (`centre_note`)? Does `games_won` name the player you
   mean?
3. **Opponent quality of the sample** (method §67–§68). The `opponent` field
   is a name; look the names up (rankings via WebFetch) and classify the
   sample's opposition `LOW / MEDIUM / HIGH`; compare with tonight's opponent.
   A 12-game `games_won` mode built against WTA-125 fields says nothing about
   a slam finalist.
4. **Serve / return decomposition** (method §18, §84–§86). From
   `aces_for`, `double_faults_for`, `first_serve_pct`, `break_points_faced`
   (dossier-only, per player) and the web (hold %, return points won, tie-break
   record on this surface): is the match a high-hold/competitive OVER, a
   breaks-and-three-sets OVER, or a one-sided UNDER? Aces ≠ tie-breaks; big
   serve ≠ over games.
5. **Distribution and scoreline arithmetic.** Q25–Q75, mode, min, max of the
   scoped sample; then the concrete scorelines that settle each rung
   (`6-3 6-4 = 19`; `7-6 6-7 7-6 = 39`; a player's games in `6-2 6-3` is 5).
   Which rung does the modal scoreline land on?
6. **Schedule and fatigue** (method §73). Previous match: sets, games,
   duration, date; back-to-back days; retirement in the last month;
   qualifiers with three extra matches. Web-sourced, tagged.
7. **H2H with decay** (method §65): weight 1.0 (<90 d), 0.75, 0.50, 0.25
   (>365 d); surface-matched or not. Supporting prior, never the primary
   signal; `STALE_H2H` already drops >12 months from the sample.
8. **Scenario matrix** (method §24 tennis A–D, §82): favourite pulls away /
   underdog holds serve / both first serves work / tie-break or deciding set —
   weighted by the price-implied favourite strength (Superbet's own match
   odds are in the offer's `result_market_lines`; label them as the book's
   opinion). Which scenario is modal; which kills the market.
9. **Ladder and tail** — every rung Superbet posts (total games 12.5–36.5,
   games_won per player, aces, DFs), `p_low`/`p_central`/price per rung,
   `RUNG_SEPARATED_BY_MODEL`, tail both ways (a 3-set match adds 12–15 games
   to a 2-set one).
10. **Price** — last, and there is **no consensus** to devig: `p_*` is all
    there is, it is weaker, say so. `min_acceptable_odds` vs `superbet.price`
    from the comparison; probability quality and value quality separately.
11. **Buy case / kill case → fresh eyes → verdict** `KEEP / WATCH / NO BET`,
    §32 grade, veto entry with the right `reason_class`.

## Kill cases this repo has already paid for

- **Pooled total priced absent third parties.** Oliynykova–Eala `aces_total`
  1.5 OVER at 13/13 from a pooled mean of 5.23 when own+own was 2.25; the
  book's 2.42 was right. Fixed in code; when `centre_note` is missing on a
  total, check the frame by hand.
- **One side scoped to zero.** Badosa–Gauff `double_faults_total` n=9 was
  100% Gauff after `SURFACE_MISMATCH` removed all of Badosa's clay matches.
  Code now suppresses one-sided totals; if a total's split shows `a=0` or
  `b=0`, `ESTIMAND_WRONG`.
- **Grass sample on a hard court.** Boulter–Muchová aces 5.5 OVER from
  Wimbledon/Bad Homburg observations at the US Open; hard-court medians were
  6.0/5.0 against a grass 9.0/11.0. Surface scoping now removes these; an
  unpinned competition does not — say when the surface is unknown.
- **Opponent class not conditioned.** Tagger `games_won` 9.5 OVER: mode 12
  against WTA-125 fields, tonight a two-time slam finalist; scenario A gives
  7 games. `ESTIMAND_WRONG`, line null.
- **Best-of-three tautologies under best-of-five prices.** Molcan–Bonzi
  `total_sets UNDER 3.5` at 15/15 from a BO3 sample vs a BO5 event priced at
  2.40. The format gate needs `--event-list`; if ATP slam rows show
  `total_sets 2.5` at 0.78+, the gate did not run — say it.
- **Identical `p_low` across three rungs** (7.5/8.5/9.5 at 8/9): no
  observation between them; the model, not the sample, separates the prices.
- **Fallback sample from 2018.** ATP players served off the `jsmatches` route
  carry an eight-year-old sample with no guard (memory
  `jsmatches-fallback-is-2018-vintage`) — check observation dates.
- **Wrong human.** Before 2026-08-28 tennis-abstract served Benoît Paire's
  page for 72 WTA names and espn-tennis recorded players as their own
  opponents. Never compare against a tennis number from before that date;
  `MISIDENTIFIED` gaps are the guard working.
- **Short match settles every UNDER at once.** Sets, games, aces, DFs are one
  mechanism; a two-leg tennis slip is one bet with two prices.

## Output additions specific to tennis

Per match, always state: tour and format (BO3/BO5), surface (pinned or
unknown), round and time as verified (two domains or "unconfirmed"), each
side's retained-on-surface `n` and the opposition class of those
observations, the previous match (score, date, duration when found), the
framed centre (`centre_note`) for every total, and that the row is
`NO_REFERENCE_SOURCE` **once**, not per row.
