---
name: football-analysis
description: How to read one football match's coupon legs in sofa - counting markets (goals, corners, cards points, fouls, shots, offsides, halves, per team), the score markets and player props - sample integrity, stakes, second legs, derbies, referee, absences, venue, game script, distribution over mean, which rung. Preloaded into sofa-analyst-football.
---

# Football analysis - the method, mapped to what `sofa` holds

`sofa-pipeline` and `sofa-analysis-core` are preloaded: they hold the input,
the numbers, the verdicts and the output contract. This skill answers one
question: *given these rows, does the sample describe tonight's match?*

| reference | read it when |
|---|---|
| `references/data-inventory.md` | you need what is measured, from which Sofascore field, and what is absent |
| `references/market-playbook.md` | you grade a specific market: drivers, kill cases, score markets, player props, builders |
| `references/methodology.md` | you need the model behind a claim: counts, referee bias, game state, two-legged ties, congestion, shrinkage |
| `references/event-protocol.md` | you write a match section (the Polish template) |

The operator's method, `docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md`, predates
`sofa`: cite its sections for *what to look at*, never take pipeline
behaviour from it.

## What `sofa` holds and what it does not

On disk: the fixture's identity, round and both clocks; a referee on a small
minority of fixtures; a venue on few; **the raw observations**; the schedule
block; the table-stakes flag; and the rating behind the centre (its ratios
are in the row's `FOOTBALL_RATING` note). Not on disk: standings, aggregates,
absences, lineups, manager changes, weather, derby status, any 1X2 consensus.
That half comes from the open web (SKILL core: one pass per match, two
domains, tagged) or is `UNVERIFIED`.

## What the code already does - do not re-derive or veto for it

- **Centre.** The sample shrunk to the league baseline (`w_c = n/(n+K)`,
  K 15; per market `cards_points_for` 25, `fouls_total` 2, `shots_for` 8,
  `shots_total` 5 - `config/sofa_engine_constants.json`), then mixed with the
  opponent-adjusted rating at a per-market weight (`W=` in the
  `FOOTBALL_RATING` note; goals_for 0.95). `corners_total` and the corners
  half totals stay unrated. Game state, season phase, the opponent correction
  of the sample and the supremacy stretches each leave a note or `*_rule`
  marker. Current switches: `.claude/skills/sofa-pipeline/references/model-state.md`.
- **Spread.** A fitted negative-binomial dispersion per competition
  (`config/sofa_count_dispersion.json`, `dispersion_rule`) - `sample_sd` is
  not what `p` was built from; `shots_total` uses a normal.
- **Confidence.** The history curve (per line for the keys of
  `config/sofa_line_curves.json`: `calibrated_on` `line:<market>|<DIR>@<line>`;
  per slice for the score markets: `market:<market>@<subject>@<line>|OVER`;
  class prefixes `women:` / `season_early:`), lowered by line evidence.
- **Gates** (`sofa-analysis-core` `references/evidence-rules.md`): sample age
  and size, line beyond the sample, mode loses, `MODEL_ABOVE_OWN_SAMPLE`,
  `CROSS_LEAGUE_UNLINKED`, `NO_CLASS_CURVE`, `NOT_SETTLEABLE`,
  `NO_LINE_EVIDENCE`. A player leg on the six lineup markets carrying
  `player_sample_rule` had a shape gate lifted: its shape is yours.

## The protocol, per match of your read-set file

Template and step table: `references/event-protocol.md`.

1. **Identity and clocks.** `identity` (`FUZZY` = names differ beyond a
   folded match - compare them, never call it confirmed), both clocks,
   `fixture_status.json`. Started = dropped (decision point).
2. **Stakes.** `round_name`, `cup_round_type`, `previous_leg_event_id` (follow
   it for the first leg's score); table, dead rubber, derby from the web or
   `UNVERIFIED`. A leg with `stakes.effect` `przeciw` (cards / fouls UNDER,
   goals / shots OVER in a six-pointer or top-4 race) is read against it:
   say what this club's sample says in such a match, or WATCH.
3. **Schedule.** `schedule` block and `context_flags` (`MAKEUP_FIXTURE`,
   `LONG_LAYOFF` >= 21 d, `CONGESTED` >= 3 in 7 d). For a make-up fixture find
   out **why** it was postponed and whether the cause still holds.
   Congestion is a rotation / availability argument, not fatigue.
4. **Sample integrity.** `03_samples.json`, per side: n, dates, opponents,
   venues, competitions. Ask: a manager change, promotion or transfer window
   inside it? are the h2h the misses? one side thin while the other carries
   the mean? do `X_for(A) + X_for(B)` land near `X_total`'s mean? does
   `subject` resolve to the side you think? a cup or friendly observation in
   a league fixture's goal sample (a defect)? a placeholder 0-0?
5. **Shrinkage share.** State `w_c` and the rating's `W`; twice for a half
   row (half baselines rest on smaller populations).
6. **Distribution.** min, max, median, **mode**, where the line sits. A line
   beyond the sample's extreme is extrapolation; a line on the mode is a coin
   flip dressed as a lean.
7. **Opponent and venue.** Tonight's venue vs the sample's mix. Every `_for`
   observation carries `against` (the opponent's value in that match): the
   other side's `against` values are what tonight's opponent concedes. Built
   in already: the rating's defence ratio and the opponent correction
   (`opponent_rule`, `corrected_sample` on the row).
8. **Referee** (cards, fouls). `RefereeRecord` is a rate with `games` as its
   n; not in the centre; absence is normal - say what it costs on a tight
   line in a high-spread league.
9. **Absences and lineups.** Web, two domains; within ~1 h of kickoff the
   club's or league's page. Four starters out is a CONTEXT candidate
   (`ABSENCES`); a rested XI likewise (`ROTATION`).
10. **Game script A-D**: favourite ahead / underdog ahead / 0-0 to 60' /
    level. Weight it from Superbet's own ladders in `04_offer.json`
    (`goals_for`, `double_chance`, `result_1x2`, `handicap_corners`, `most_*`)
    or say it is unweighted; name the script that kills the leg.
11. **The ladder.** Every rung of the market with pewność, próbka, model,
    odds; why this rung. `NO_LADDER_CHECK` / `LADDER_DISAGREES` are the old
    selector's notes - CONFIDENCE does not gate on them; weigh them. A leg
    whose `peer.best` is another, surer leg of the match at a similar price:
    say why you keep the weaker one beside it.
12. **Correlation** (builder legs): the shared mechanism and the one scenario
    that kills every leg. Never multiply.
13. **Buy case / kill case -> verdict.** `BUY ≈ KILL` is WATCH at most. The
    price is the filter the code applied, never a reason.

## Markets with their own reading

- **Score markets** (`result_or_*`, `btts_or_over`, `result_or_btts`,
  `result_or_clean_sheet`, `result_handicap`, `dc_and_*`) and the
  rating-only markets (`double_chance`, `draw_no_bet`, `result_1x2`,
  `first_goal`, `red_cards_total`, `penalties_total`): no sample, no próbka,
  no `MODEL_ABOVE_OWN_SAMPLE` - judge the match (script, absences,
  motivation). Several rungs of one match are one script. Mapping to
  Superbet's words: `references/market-playbook.md`.
- **Player props** (`player_*_for`): the bet voids unless he starts, so a
  doubtful start is not a reason; the risk is what happens once he starts
  (early substitution, role or position change, minutes limit, red card).
  Check `PLAYER_MINUTES`, the identity rule (`PLAYER_NAME_TOKENS` /
  `PLAYER_NAME_SURNAME`: is `matched_name` the same person?), set pieces,
  opponent style, the referee for fouls. Key the read to the player exactly
  as the leg writes him. Details: `references/market-playbook.md`.
- **Derived joints** (`both_over_*`, `most_*`, `handicap_*`): no sample of
  their own. If one is in your file, report the two `*_for` rows and refuse
  the multiplication.

## Kill cases this repo has paid for

- A team-corner OVER with a total-corner UNDER and no tail test (12-2: one
  side can destroy the total alone).
- The misses are the h2h: 19/21 pooled, 1/3 in this pairing.
- A line on the mode (cards 7.5 with five 7s and two 8s).
- One observation deciding the bar (6 vs 8 on one match moved 19/21 to 20/21).
- A mean pulled by outliers against another class of opponent (shots 29.6
  mean, median 26, the four highest against continental sides).
- Sample centre far from the book's ladder centre (corners 2.80 vs 5.76: a
  different team-state).
- Past frequency read as an edge: a 12/12 streak is the sample, the
  pewność is the claim.
- Certainty for free: a 0.5 UNDER at 1.01-1.05 is not a bet (CONFIDENCE
  refuses < 1.0867); never lead with one.
- A cup tie with extra time: check whether the competition plays 30 minutes
  or goes to penalties - goals settle at 90 minutes, other counts after
  extra time stay unsettled.
- A make-up fixture nobody asked about (a round-5 make-up after a viral
  outbreak: UNDER 3.5 lost 4-0).

## Football output requirements

Per match, always state - even when the answer is "brak": round and stakes
and where you read them; the referee with `games`, or that there is none;
absences per side and how you checked; the venue; the modal game script;
`w_c` and `W`; which gates the code already applied.
