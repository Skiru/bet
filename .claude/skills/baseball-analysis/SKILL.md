---
name: baseball-analysis
description: How to analyse one MLB fixture's runs markets (match total runs and each team's own runs, both "(z dogrywką)" - final score including extra innings) from this pipeline's artifacts the way the operator's method says it should be, given what the code cannot know - starting pitcher identity, ballpark as a run-scoring multiplier, September roster expansion and bullpen fatigue, the extra-innings automatic runner, weather and wind - distribution over mean, scoreline arithmetic, price last. Use when reading a baseball stats sheet, grading VALUE rows, or writing analyst vetoes for MLB fixtures. Preloaded into bet-analyst-baseball.
---

# Baseball analysis — the method, mapped to what this pipeline actually holds

Read `bet-analysis-core` first (preloaded with you). MLB is architected as a
copy of tennis (docs/PLAN_MLB_2026-09-14.md section 2), not of football, and
three things follow from that: **there is no source of record** (a single
provider, `espn-baseball` — no bzzoiro, no corroborator, no MCP), so every row
is `NO_REFERENCE_SOURCE` and can never be `CALL`, only `LEAN`; the sample is
**team-level box scores**, ten per side plus head-to-head, with no player
identity attached; and the calibration curve every football market has is
**absent** here — `market_reliability.json` has no entry for `runs_total`, so
`p_central` ships with no correction and an `UNMEASURED` annotation. A
`LEAN` + `VALUE` row is the expected, correct combination on this sport, not a
bug — the ceiling is on the sample's ranking, not on whether the row can clear
a price.

## What the code already does, and what it cannot see

The code: collects each side's last ten completed games and the two teams'
head-to-head off ESPN's boxscore (`runs`, from `header.competitors[].score` —
the final score **including extra innings**, exactly what the `(z dogrywką)`
family settles), splits `runs_for`/`runs_against` by venue, prices
`runs_total` (match) and `runs_for` (per team) against Superbet's ladder,
shrinks toward a market prior, and tiers the row `LEAN` with an `UNMEASURED`
note. **It cannot see**: who is starting on the mound for either side, which
ballpark tonight's game is in, whether either bullpen threw 40 pitches
yesterday, today's date relative to the September roster-expansion cutoff, or
the wind at first pitch. That is the analyst's job, and on this sport it is
not a refinement of the code's number — it is most of the distribution the
code's number does not describe at all.

Only `runs_total` and `runs_for` are priced. Everything Superbet calls
`Pałkarz -*` / `Miotacz -*` / `Starter -*` is a player prop, mapped so the
offer artifact can say "offered, not priced" and nothing more — never grade
one, never write a veto that treats one as a market this pipeline supports.
Per-inning runs markets (`po X inningach`, `Inning X -`) are out of scope by
the same plan and are not even visible in the mapped offer; do not go looking
for them.

## The protocol — starter first, park second, price last

For every MLB fixture with a `VALUE` row in `<date>_superbet_comparison.json`
(sport `baseball`) and any fixture you intend to veto:

1. **Identity and time.** Confirm both teams and the scheduled first pitch
   against one independent domain (MLB.com, a beat-writer preview, or a stats
   site) — ESPN's own scoreboard time is usually reliable but a rainout or a
   doubleheader reschedule is not rare in September. A postponed or suspended
   game is a `VETO` on every line, not a stale price.

2. **Starting pitcher — the single largest thing the code does not know.** A
   ten-game team sample without starter identity describes ten different
   generative processes, not one repeatable one: a team's runs allowed with
   its ace on the mound and with its fifth starter are not the same
   distribution, and neither is its own scoring against a bullpen day.
   Identify tonight's two starters (web search, confirmed same-day — a
   scratch is common and changes the read entirely), their recent runs
   allowed / innings-pitched-per-start, and note explicitly whether the
   ten-game sample you are reading is dominated by starts from pitchers who
   are not pitching tonight. This is not a footnote to the sample; often it
   is the reason the sample and tonight's game are barely related.

3. **Ballpark — a multiplier, not a prior.** The same two teams, the same two
   lineups, produce a different runs distribution in different parks: Coors
   Field (Colorado, altitude) inflates runs sharply; pitcher-friendly parks
   (large foul territory, marine layer at night in some coastal parks) cut
   them. Identify tonight's park from the schedule (home team's park unless
   stated otherwise — check for a neutral-site or international game, rare
   but not unheard of) and its known run-scoring context (park factor, if you
   can source one; otherwise qualitative: known hitter's park / pitcher's
   park / neutral). State this before touching the sample's mean, not after.

4. **September roster expansion and bullpen fatigue.** From September 1,
   active rosters expand and clubs carry more relievers; a manager already
   out of the race may rest regulars or audition rookies, changing the
   offense's true talent level independent of the box-score sample. Check
   bullpen usage over the preceding 2–3 days for both sides (a pen that threw
   extra innings or three high-leverage appearances yesterday is a real run
   input tonight, especially late). Check both teams' standing/motivation —
   a team eliminated from contention plays a different game than one fighting
   for a wild card.

5. **Extra-innings automatic runner.** The `(z dogrywką)` family settles on
   the *final* score, and extra innings start a runner on second base for
   both sides, which mechanically inflates late scoring versus a regulation
   nine. A close game is not just "a coin flip in the 9th" — it carries a
   meaningfully fatter right tail than the same score differential would in a
   sport without the rule. Do not price a tied or one-run game's OVER as if
   extra innings, when they happen, look like a normal inning.

6. **Weather and wind.** For outdoor parks, wind direction and speed at first
   pitch matters more in baseball than in most sports Superbet lists here —
   wind blowing out at Wrigley Field is the canonical case (a park that plays
   both extremes depending on wind alone), but any outdoor park in a strong
   wind is affected. Domed/retractable-roof parks (check whether the roof is
   closed tonight) are neutral, and stating that explicitly is itself useful
   information, not a null result.

7. **Home-side truncation.** A winning home team does not bat in the bottom
   of the last inning, so the home side's own `runs_for` sample is
   systematically short one plate-attack opportunity relative to the away
   side's — this is a structural fact about the sport (docs/PLAN_MLB section
   4.3), not sampling noise, and it does not average out. Read `runs_for`
   with the side's home/away split in mind (the dossier's observations carry
   `venue`); do not treat a thin home `runs_for` figure as evidence of a
   weaker offense without checking whether truncation explains it.

8. **Distribution and scoreline arithmetic.** Read the scoped sample's
   spread (min/max/Q25–Q75), not just its mean — single-game run totals in
   baseball are highly variable (a shutout and a 12-run game both happen
   routinely), so a `p_central` computed from ten games carries real spread
   the pipeline's shrinkage narrows but does not remove. State the modal
   range, not a point estimate, when arguing for or against a rung.

9. **Ladder and price.** Rungs actually offered cluster at 7.5–10.5 (match
   total) and 2.5–4.5 (team total) — see the offer artifact for what is
   really posted tonight, the fallback ladder in code is not a claim about
   any specific fixture. Price last: `p_low`/`p_central` against
   `superbet.price`, `min_acceptable_odds`, and state the `LEAN` margin
   (1.10, not 1.05) explicitly since every baseball row carries it.

10. **Verdict.** `KEEP / WATCH / NO BET` plus veto entries with the right
    `reason_class`. State once, per report rather than per row, that
    `runs_total`/`runs_for` are `UNMEASURED`: p_central carries no
    calibration correction on this sport yet, and that is a fact about the
    market, not a defect in any one row.

## Kill cases and traps specific to this sport

- **A sample with no starter identity is not "the team's runs".** Treat a
  ten-game sample as team-average-with-a-mixed-rotation unless you can name
  who actually started those ten games; if tonight's starter's own starts
  dominate the sample, say so — that is the strong case. If tonight's starter
  never appears in it, say that too.
- **Coors Field games run hot on both sides.** A road team's own average
  `runs_for` understates its output at Coors and overstates it at a strong
  pitcher's park; do not price a road team's line off its season average
  without adjusting for tonight's park.
- **A tied/close scoreline is not "settled" at nine.** The `(z dogrywką)`
  ladder prices the possibility of extra innings and its automatic-runner
  scoring; a UNDER priced as if the game ends at nine is priced on the wrong
  quantity.
- **A shutout or a 0-error, 0-home-run game is a real result, not a data
  gap.** `_is_absent_not_zero`'s baseball branch already treats these
  correctly on the sample side (anchored on `at_bats`, never on "all values
  are zero") — do not second-guess a genuine 2-1 final as suspicious data.
- **Never grade a Pałkarz/Miotacz/Starter market.** These are visible in the
  offer artifact as offered-and-not-priced by design (docs/PLAN_MLB section
  1.3.B, measured −30.5% ROI on football props with zero settlement history
  here); a veto or a VALUE read on one of these is out of scope, full stop.
- **September is not a normal month's sample.** A ten-game window spanning
  the trade deadline aftermath or the roster-expansion date can quietly mix
  two different rosters; check the dates on the retained observations.

## Output additions specific to baseball

Per match, always state: both starting pitchers (confirmed same-day, or
"unconfirmed" if not found), tonight's park and its run-scoring character
(and whether the roof is closed, where applicable), either bullpen's usage
load over the last 2–3 days, and that `runs_total`/`runs_for` are
`UNMEASURED` — stated once per report, not per row. State the `LEAN` tier and
its 1.10 margin explicitly on every row you grade.
