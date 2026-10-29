# The match dossier - what it holds and how to read it

`runs/sofa/<d>/dossier/<sport>_<sofascore_event_id>.json`, path on every
read-set leg's `dossier` field. Built by `bet.sofa.dossier` when the read set
is written (`read_set.py`, `build_slip.py`), **offline** from `data/sofa.db`
and the day's artifacts - no request. Display only: it never changes a
confidence or a gate. Read it **first** for each match, before the legs'
numbers and before the web - through this fixed set, never `cat` (a whole
dossier does not fit a 6-match read):

```bash
jq '.schema, .header, .sides.home.summary, .sides.away.summary, .table.positions' <dossier>
jq -c '.lineups | {status, confirmed, asked_at_utc, player_legs, h: .home.missing_players, a: .away.missing_players, hr: .home.regulars_not_in_xi, ar: .away.regulars_not_in_xi}' <dossier>
jq -c '.samples.gaps' <dossier>
jq -c '.head_to_head_source, (.head_to_head[]? | {date, score, metrics})' <dossier>
# football - the style block (match-up, league rate):
jq '{h:.style?.home.means,a:.style?.away.means,hp:.style?.home.corners_by_own_possession,ap:.style?.away.corners_by_own_possession,lg:.style?.league,m:[.style?.matchup[]?|{leg,confidence,implied,s:[.sides[]|{team,own,opponent_conceded,games}],league}]}' <dossier>
jq -c '.style.home.games[]?' <dossier>             # one game a line, when a driver needs it
jq -c '.sides.home.last_games[]' <dossier>         # one game a line
jq -c '.market.rows[]? | select(.first != .last)' <dossier>   # moved lines - sports only
jq -c '.market.rungs_of_leg_markets[]?' <dossier>  # football / tennis: the legs' ladders at the offer fetch (no line-move history)
```

## Blocks

| block | holds | read it for |
|---|---|---|
| `header` | competition, stage, round, season, gender, both clocks (`kickoff_utc`, `kickoff_warsaw`, `kickoff_venue_local` + `venue_zone`), venue, city, country, capacity, coordinates, referee (football: `games` and cards - his career, all competitions), surface (tennis), `best_of` (CS2), identity, `first_leg` score | the estimand: knockout or league, second leg, women / youth, the weather hour, the referee |
| `sides.<home/away>` | `last_games` (10, newest first: date, competition, dom / wyjazd, opponent, score, periods / sets, result W / R / P, `friendly`, `awarded` (football, matches from 2026-10-30: a result awarded at the table - a forfeit / walkover, an unplayed 3-0 / 0-0 - never a game played), overtime status), `summary` (form, streak, record, home / away record, avg for / against, totals, avg per period, `rest_days`, `games_7d`, `games_14d`; an `awarded` row is not in it), `ranking` (tennis), `country` | form against the line, rest and congestion, scoring per period, a side that changed level |
| `head_to_head` | up to 6 newest meetings from the home side's view - the cached listings' and Sofascore's own h2h answer (`h2h.json`, asked for every read match), each with the legs' metrics (`metrics`, a `_for` metric as [home, away]; an `awarded` meeting carries none); `head_to_head_source`: `sofascore_h2h` OK / NOT_ASKED / FAILED, `cache_listings_from` per side | a style matchup that repeats - never alone a reason; read it every match and say what it shows on the leg's metric; not OK = the web checklist's h2h line is obligatory, an empty list with OK = the sides never met |
| `lineups` (football, hockey, basketball) | Sofascore's pre-match line-up (`lineups_prematch.json`, asked for every read match not yet started; never the cache): `status` OK / NOT_PUBLISHED / FAILED / NOT_ASKED, `asked_at_utc`, `confirmed` + `kind` (predicted or confirmed), per side `formation`, `starters`, `substitutes`, `missing_players` (type missing / doubtful, Sofascore's reason code and description, copied), `regulars` (most starts in the last 10 cached games with a post-match line-up, each with its status today) and `regulars_not_in_xi`; `player_legs`: each prop's player XI / ławka / missing / doubtful / not listed (first the sample's own `matched_name`, any `match_rule` incl. `slug`; else SAMPLES' name rules) | who plays. **Predicted is not confirmed** - name which and when it was asked. An absent regular or a prop's player on the bench / missing can at most give a WATCH through the leg's variable, never a promotion; `missing` = not known, never "no absences" |
| `table` | the season's table rebuilt from cached listings (`games_counted`, `teams`, `positions`, `rows`); football points 3 / 1 / 0, other sports by win % | stakes: title race, relegation, a dead rubber. **Not official** - it counts only what the cache holds; say so when you use it |
| `samples` (football / tennis) | every metric's observed values per side and h2h, mean and median; the `schedule` block; `gaps` (reason, metric, detail - the detail tells a kept "sample cut at the clash" from an emptied side and a used `PLAYER_HISTORY_ANY_TEAM` top-up from a refused thin sample); the leg subjects' player rows with `match_rule` | the distribution around the line, not only the mean |
| `style` (football) | `style.home` / `style.away` = {`n`, `games[]` (last 10 competitive games, all competitions, friendlies out: `date`, `opponent`, `venue`, `competition`, `corners` [za, przeciw], `corners_1h`, `corners_2h`, `possession`, `crosses` [attempted za, przeciw], `box_touches`, `shots_inside_box`, `shots`, `shots_on_target`, `offsides`, `fouls`, `saves`, `blocked_shots`, `shots_outside_box`, `big_chances`, `xg`, `final_third_entries`, `long_balls` (attempted), `throw_ins`, `goal_kicks`; a partial feed's 0 / 0 left out), `means`, `corners_by_own_possession` {`posiadanie_ponizej_50`, `posiadanie_50_plus`: {`n`, `rozne_za`, `srednia`, `uwaga` when n < 4 - a note, never a RYNEK WATCH}}}; `style.league` = {`competition`, `games`} (the match's competition; a cup tie falls back to the sides' league; absent below 30 games); `style.matchup[]` = {`leg`, `metric`, `market`, `subject`, `line`, `direction`, `confidence`, `implied`, `price_gap` (true when the leg carries one), `joint` (true on a `both_over_*` leg), `sides[]` (a side leg: `team`, `opponent`, `own`, `own_values`, `opponent_conceded`, `conceded_values`; a total or a joint: `team`, `games`, `values` - a joint's values are min(own, rival) per game, as SETTLE grades it), `league` {`competition`, `share`, `n`, `mean`}} - k/n counted **in the leg's direction**; football matches from 2026-10-30: a result awarded at the table is in no `style` game, matchup, league rate or joint k/n (SETTLE never grades one), as the samples leave it out (`AWARDED_EXCLUDED`); the rebuilt table keeps its points; schema 3 (from 2026-10-29) - a `RYNEK:` WATCH is checked against this row | the market drivers (`market-drivers.md`): who has the ball tonight, what the side without it does then, wide vs central play (crosses, box touches), blocked shots, whether the opponent concedes the line at all, the league rate - the **Styl gry i zestawienie** paragraph and its leg table (football event protocol); the same text rides as a "zestawienie" tag beside every printed football count leg of KUPON html. `own` here is the last 10 competitive games; the leg's próbka is SAMPLES' own selection - they can differ |
| `cs2` | per team: last 10 series, 90-day map pool (n, won, avg rounds), `roster_latest`, `roster_new_vs_previous` (a name not seen in the previous series), players' kills / deaths per map | a stand-in (a new name = search it), map pool against the line, a player's slump |
| `market` | sports: `rows`, every Superbet line of the match through the day (`first` / `last` odds, `seen`, times; `moved` count); football / tennis: `rungs_of_leg_markets`, the legs' ladders at the offer fetch - no line-move history | a hard move is a **question** for the web (stand-in, lineup, weather), never a verdict |
| `legs` | every leg of the match on the coupon (Superbet words, confidence, odds, x, sample, price_gap, peer, reads so far, removed) | exposure: two legs that are one bet |
| `web_checklist` | the context pass with the match filled in (city and local hour, names, sport items) | your web pass - start here (`context-pass.md`) |

`missing` in any block = the cache could not fill it: a check you could not
make, named in **Czego zabrakło**, never a guess. No `dossier` field on the
leg = "brak dossier". **Schema:** `schema` 2 (from 2026-10-29) holds the
whole `style` block above; a dossier with `schema` < 2 (10-28: no `style`
at all; schema 1: no `league`, `xg`, `blocked_shots`, `shots_outside_box`,
`big_chances`, `final_third_entries`, `long_balls`, `throw_ins`,
`goal_kicks`, `matchup[].metric`), or a key absent from every game, is
"dossier sprzed bloku stylu" in **Czego zabrakło** - never "brak danych";
read the style means from the games you have, and no `RYNEK:` rests on a
missing cell.

## Per sport - what to derive first

- **Football**: expected count from `samples` per side against the line;
  then `style` per market family (`market-drivers.md`) and the league rate
  (a second source, read-only:
  `jq '.<market>["<competition_id>"]' config/sofa_league_baselines.json`);
  `table.positions` and `header.round` for stakes; `rest_days` / `games_7d`
  for rotation (a note); `first_leg` for a decided tie; the referee (already
  in the cards / fouls centre - only a change is new).
- **Tennis**: `ranking` of both, `last_games` set scores (how long, retired?),
  `surface`, `rest_days` (played yesterday?), round.
- **Hockey**: `avg_periods` for period lines, totals in `summary.totals`
  against the line, overtime share in `last_games[].status`, back-to-back.
- **Basketball**: totals and per-quarter averages; back-to-back; a team on a
  losing run resting starters.
- **Volleyball**: sets per match from `last_games` (3:0 / 3:1 / 3:2), points
  per set in `periods`.
- **CS2**: `roster_new_vs_previous`, map pool against the map line,
  `best_of`, series this week (`games_7d`), player form for a player line.
