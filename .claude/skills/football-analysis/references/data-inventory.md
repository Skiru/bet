# Football data inventory — what is measured, at which lines, and what is only context

Everything here is read from `src/bet/simple_stats/{contracts,analyze,enrich,
providers,context_flags,coupons}.py`, `src/bet/stats/market_ranking.py`,
`config/market_priors.json` and the 2026-09-03 artifacts. Re-check against the
code when in doubt; this is a reading guide.

## Providers

| Provider | Role | Serves |
|---|---|---|
| `bzzoiro` | **primary, source of record**, uncapped on PRO | 55 metrics per match (`/events/{id}/stats/`, `/incidents/` for card points), h2h, fixtures, squads, referees, standings (season xG), lineups, odds (~88 books, no Superbet), model `dc-blend-v1` |
| `espn-football` | corroborator | 6 metrics; agrees with bzzoiro on 92–98% of shared points — a second transcription, not a second measurement |
| `highlightly` | discovery + corroboration | 100 requests/day; exhaustion shrinks the *slate* ~77%, not just corroboration |
| `api-football` | suspended account | nothing (200 with empty body) |
| `understat`, `sackmann` | dead | nothing |

`READY` = primary served ≥5 matches a side on the three priority metrics;
`PARTIAL`/`BLOCKED` otherwise. Slate gate (since 2026-09-02) refuses fixtures
bzzoiro did not discover, already kicked off, or Superbet prices the
competition but not the fixture.

## Metrics collected per match (dossier `metrics`)

Match totals and per-team (`_for`), full match and by half (`_1h`, `_2h`):

```
goals_total / goals_for / goals_against / goals_1h_* / goals_2h_*
corners_total / corners_for / corners_1h_* / corners_2h_*
cards_total (yellow only) / cards_for / cards_1h_* / cards_2h_*
cards_points_total / cards_points_for            # yellow=1, straight red=2, second yellow=3 — off /incidents/
red_cards_total / red_cards_1h_total / red_cards_2h_total
fouls_total / fouls_for / fouls_1h_* / fouls_2h_*
shots_total / shots_for / shots_1h_* / shots_2h_*
shots_on_target_total / shots_on_target_for / *_1h_* / *_2h_*
shots_off_target_total / *_1h_total / *_2h_total
blocked_shots_total / *_1h_total / *_2h_total
offsides_total / offsides_for / *_1h_* / *_2h_*
```

**Not collected or not usable:** possession (constant 100.0 in every
observation — ignore), crosses, big chances, tackles/duels at team level,
passes, xG *per match* (only season-level via standings), any `*_against`
except `goals_against`, opponent ranking/Elo, manager tenure, kickoff-local
weather beyond the discovery-page snapshot.

Each observation carries `match_date`, `opponent`, `venue` (home/away — the
subject's side in that match), `competition_id`, `season_id`, provider. The
per-team bucket is that team's own last ten; h2h is the meetings (no side
marker, so never used for `_for` rows).

## Priced markets and lines (`STANDARD_MARKET_LINES["football"]`)

The sheet prices offer-driven ladders when the Superbet offer is present
(`select_lines` trims to the rungs nearest the sample median); the static grid
below is the fallback and the vocabulary.

| Market | Static lines | Superbet name |
|---|---|---|
| `corners_total` | 6.5 … 12.5 | Liczba rzutów rożnych |
| `cards_points_total` | 3.5 … 8.5 | **Liczba kartek** (settles booking points) |
| `fouls_total` | 20.5, 22.5, 24.5 | Liczba fauli (rarely offered; 30 lines/day) |
| `shots_on_target_total` | 4.5 … 7.5 | Liczba celnych strzałów (ladder often starts 7.5) |
| `shots_total` | 19.5 … 28.5 | Liczba strzałów (ladder often starts 24.5) |
| `goals_total` | 0.5 … 4.5 | Liczba goli |
| `goals_1h_total` / `goals_2h_total` | 0.5 | 1.połowa / 2.połowa - liczba goli |
| `offsides_total` | 1.5 … 4.5 | Liczba spalonych |
| `red_cards_total` | 0.5 | Liczba czerwonych kartek |
| `corners_for` | 2.5 … 7.5 | `<Team> - liczba rzutów rożnych` |
| `cards_points_for` | 1.5 … 4.5 | `<Team> - liczba kartek` |
| `fouls_for` | 8.5, 10.5, 12.5 | rarely offered |
| `shots_on_target_for` | 1.5 … 7.5 | `Liczba celnych strzałów - <Team>` |
| `shots_for` | 9.5, 11.5, 13.5 | `Liczba strzałów <Team>` |
| `goals_for` | 0.5, 1.5, 2.5 | `<Team> - liczba goli` (house market; consensus usually beats the sample) |
| `offsides_for` | 0.5, 1.5, 2.5 | — |
| Player props (`--player-props`): `player_total_shots`, `player_shots_on_target`, `player_fouls`, `player_was_fouled`, `player_cards` (0.5), `player_tackles`, `player_assists`, `player_offsides` | 0.5, 1.5, 2.5 | `Zawodnik - liczba strzałów / celnych strzałów / popełnionych fauli / fauli na zawodniku / odbiorów / asyst / spalonych / otrzyma kartkę` |

Not priced, by design: `both_teams_over` (no sample for the conjunction),
`red_cards_for` (no per-team red metric), per-team half lines, half
corners/cards/shots/fouls (real data, no observed screen line).

## Context blocks (never in `p_low`)

| Block | Fields | Code already does | You do |
|---|---|---|---|
| `fixture_context` | `referee_id, venue_id, league_id, is_local_derby, is_neutral_ground, travel_distance_km, weather{wind_speed, temperature_c, code}, round_name, group_name, previous_leg_event_id, previous_leg_goals_*` | `DERBY` and `KNOCKOUT_SECOND_LEG` ceilings when the flags are set; wind flag | read round/leg via MCP (fields are null in dossiers); derby by distance |
| `referee` | `name, matches, avg_yellow/red/fouls/goals_per_match, career_*` | blend into card-total centre at `matches ≥ 15` (`k=20`, see `centre_note`); `ARGUES_AGAINST` flag when ≥8 matches and average contradicts the line; `MISSING_REFEREE` ceiling + doubled `k` when `referee_id` null | judge the *league's* referee spread, red-card propensity, and whether the number of matches is a sample |
| `squad_availability` | per side `squad_size, unavailable_count, availability_unknown_count, unavailable[]` | drops props on unavailable players; `ARGUES_AGAINST` at ≥4 unavailable | who is missing (a centre-back changes fouls; a set-piece taker changes corners), whether the unknown count makes the picture incomplete |
| `season_form` | `position, xgf, xga, xg_games, form, group` | `ARGUES_AGAINST` when actual scoring exceeds xGF by ≥0.75/game over ≥5 games | regression to xG, table stakes, group vs league position |
| `lineup_status` | `confirmed / predicted / ""` | caps props at `LEAN` unless confirmed | expected minutes (method §21), role |

## Flags vocabulary (all on the row)

- `sample_excluded`: `PRE_SEASON_FRIENDLY` (competition tier map / provider
  flag), `STALE_SEASON` (needs competition_id + season_id — cannot fire on
  h2h), `STALE_H2H` (>12 months), `CONFLICT_ON_LINE` (providers straddle the
  line), plus tennis-only ones.
- `observation_flags`: `CONFLICT_RESOLVED_ADVERSE` (providers differed, the
  value against the row's direction was kept), `RED_TYPE_UNKNOWN` (a red whose
  type could not be read → points ambiguous), `RED_COUNT_CONFLICT`.
- `lean_ceiling_reasons`: `MISSING_REFEREE` (card markets, no `referee_id`),
  `DERBY`, `KNOCKOUT_SECOND_LEG`, `RUNG_SEPARATED_BY_MODEL`.
- `context_flags[]`: `{source, direction: ARGUES_AGAINST, magnitude, note}` —
  quote the `note`.

## Priors and shrinkage (`config/market_priors.json`, `analyze.SHRINKAGE_K = 10`)

`shrunk_mean = (n·mean + 10·prior)/(n+10)`. The prior is the market's pooled
mean over all enriched slates, with a **venue split** where measured at z>|3|
and ≥120 observations a side (e.g. `corners_for` home > away, `cards_for` home
1.60 vs away 2.11 — the referee home bias in one number). `cards_points_*`
priors are one slate old (2026-09-03) and have no venue pair yet. Read
`shrunk_mean` beside `mean`: the gap is how much of the row's price is the
market average standing in for observations the sample lacks.

## Base rates you may cite (measured in-repo, `bet-slip-audit/reference/base-rates.md`)

700 matches, ten leagues: corners 9.5/match (>8.5 in 61%, >9.5 in 49%),
shots on target 8.7 (>6.5 in 73%), fouls 24.3 (>20.5 in 75%); per team
corners 4.77 (>4.5 in 48%), SOT 4.35 (>2.5 in 77%), fouls 12.17 (>12.5 in
45%). 7,516 matches: first halves carry 44.7% of goals; over 2.5 in 55.4%.
League spread is real: Süper Lig fouls 27.9 vs Bundesliga 20.7; Bundesliga SOT
9.7 vs Premier League 8.1.

## MCP tools by question (football only; football is uncapped)

| Question | Tool |
|---|---|
| still on, at that time; round; first leg | `get_match_detail` (by `source_ids.bzzoiro`), then on `previous_leg_event_id` |
| who plays; expected minutes | `get_match_lineups`, `get_team_squad`, `get_player_stats` |
| referee profile / league referees | `list_referees`, dossier `referee` |
| table, stakes, congestion, recent results | `get_standings`, `get_team_fixtures`, `get_match_h2h` |
| manager, venue, altitude, pitch | `get_manager_detail`, `get_venue` |
| live prices / model (reference only) | `compare_odds`, `get_best_odds`, `get_predictions` |
| shot detail behind a shots row | `get_match_shotmap` |
| first-leg incidents (cards, added time) | `get_match_incidents` |

Dead on this account: `get_money*`, `list_money_movers` (Weight of Money
addon). `get_polymarket_odds` returns placeholders.

## DB probe (before claiming depth)

```bash
sqlite3 -header betting/data/betting.db "
select t.id, t.name, count(distinct m.fixture_id) matches, min(date(f.kickoff)) first, max(date(f.kickoff)) last
from teams t join match_stats m on m.team_id=t.id join fixtures f on f.id=m.fixture_id
where m.stat_key='corners' and t.name like '%<team>%' group by t.id order by matches desc limit 5;"
```

Group by `t.id` (the `teams` table holds ~49k rows with duplicates and
scoreboard fragments). Filter `analysis_results.source='simple_stats'`; the
`deep_stats_report` rows are a different, older methodology.
