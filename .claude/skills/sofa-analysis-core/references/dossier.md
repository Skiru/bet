# The match dossier - what it holds and how to read it

`runs/sofa/<d>/dossier/<sport>_<sofascore_event_id>.json`, path on every
read-set leg's `dossier` field. Built by `bet.sofa.dossier` when the read set
is written (`read_set.py`, `build_slip.py`), **offline** from `data/sofa.db`
and the day's artifacts - no request. Display only: it never changes a
confidence or a gate. Read it **first and whole** for each match, before the
legs' numbers and before the web.

```bash
jq '.header, .sides.home.summary, .sides.away.summary, .table.positions' <dossier>
jq -c '.sides.home.last_games[]' <dossier>         # one game a line
jq -c '.market.rows[] | select(.first != .last)' <dossier>   # moved lines (sports)
```

## Blocks

| block | holds | read it for |
|---|---|---|
| `header` | competition, stage, round, season, gender, both clocks (`kickoff_utc`, `kickoff_warsaw`, `kickoff_venue_local` + `venue_zone`), venue, city, country, capacity, coordinates, referee (football: games and cards), surface (tennis), `best_of` (CS2), identity, `first_leg` score | the estimand: knockout or league, second leg, women / youth, the weather hour, the referee |
| `sides.<home/away>` | `last_games` (10, newest first: date, competition, dom / wyjazd, opponent, score, periods / sets, result W / R / P, `friendly`, overtime status), `summary` (form, streak, record, home / away record, avg for / against, totals, avg per period, `rest_days`, `games_7d`, `games_14d`), `ranking` (tennis), `country` | form against the line, rest and congestion, scoring per period, a side that changed level |
| `head_to_head` | up to 6 newest meetings from the home side's view - the cached listings' and Sofascore's own h2h answer (`h2h.json`, asked for every read match), each with the legs' metrics (`metrics`, a `_for` metric as [home, away]); `head_to_head_source`: `sofascore_h2h` OK / NOT_ASKED / FAILED, `cache_listings_from` per side | a style matchup that repeats - never alone a reason; read it every match and say what it shows on the leg's metric; not OK = the web checklist's h2h line is obligatory, an empty list with OK = the sides never met |
| `lineups` (football, hockey, basketball) | Sofascore's pre-match line-up (`lineups_prematch.json`, asked for every read match not yet started; never the cache): `status` OK / NOT_PUBLISHED / FAILED / NOT_ASKED, `asked_at_utc`, `confirmed` + `kind` (predicted or confirmed), per side `formation`, `starters`, `substitutes`, `missing_players` (type missing / doubtful, Sofascore's reason code and description, copied), `regulars` (most starts in the last 10 cached games with a post-match line-up, each with its status today) and `regulars_not_in_xi`; `player_legs`: each prop's player XI / ławka / missing / doubtful / not listed (name rules as SAMPLES') | who plays. **Predicted is not confirmed** - name which and when it was asked. An absent regular or a prop's player on the bench / missing can at most give a WATCH through the leg's variable, never a promotion; `missing` = not known, never "no absences" |
| `table` | the season's table rebuilt from cached listings (`games_counted`, `teams`, `positions`, `rows`); football points 3 / 1 / 0, other sports by win % | stakes: title race, relegation, a dead rubber. **Not official** - it counts only what the cache holds; say so when you use it |
| `samples` (football / tennis) | every metric's observed values per side and h2h, mean and median; the `schedule` block; `gaps`; the leg subjects' player rows | the distribution around the line, not only the mean |
| `cs2` | per team: last 10 series, 90-day map pool (n, won, avg rounds), `roster_latest`, `roster_new_vs_previous` (a name not seen in the previous series), players' kills / deaths per map | a stand-in (a new name = search it), map pool against the line, a player's slump |
| `market` | sports: every Superbet line of the match through the day (`first` / `last` odds, `seen`, times; `moved` count); football / tennis: the offer's ladder of the legs' markets | a hard move is a **question** for the web (stand-in, lineup, weather), never a verdict |
| `legs` | every leg of the match on the coupon (Superbet words, confidence, odds, x, sample, price_gap, peer, reads so far, removed) | exposure: two legs that are one bet |
| `web_checklist` | the context pass with the match filled in (city and local hour, names, sport items) | your web pass - start here (`context-pass.md`) |

`missing` in any block = the cache could not fill it: a check you could not
make, named in **Czego zabrakło**, never a guess. No `dossier` field on the
leg = "brak dossier".

## Per sport - what to derive first

- **Football**: expected count from `samples` per side against the line;
  `table.positions` and `header.round` for stakes; `rest_days` / `games_7d`
  for rotation; `first_leg` for a decided tie; referee cards for card lines.
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
