# Artifact contract — every field an analyst reads, and what it means

Source of truth is `src/bet/simple_stats/contracts.py`. This file is the
reading guide; when it disagrees with the code, the code wins and this file
needs a fix.

## `EVENT_LIST_V1` — `<date>_event_list.json`

```json
{"event_id": "<sha256>", "sport": "football|tennis",
 "competition": "La Liga - Spain" | "ATP US Open" | "WTA US Open",
 "home_team": "...", "away_team": "...",             // football
 "player_one": "...", "player_two": "...",           // tennis
 "start_time": "2026-09-03T19:00:00+00:00",          // UTC, always
 "source_ids": {"bzzoiro": "213579", "odds-api": "...", "highlightly": "..."},
 "provider_team_ids": {"bzzoiro": {"home": "48", "away": "49"}},
 "identity_confidence": "CONFIRMED|FUZZY_MATCHED|...", "status": "ACTIVE",
 "fixture_context": {"referee_id", "venue_id", "league_id", "is_local_derby",
   "is_neutral_ground", "travel_distance_km", "weather": {...},
   "round_name", "group_name", "previous_leg_event_id",
   "previous_leg_goals_home", "previous_leg_goals_away", "home_team_id", "away_team_id"}}
```

- `competition` is the **only** carrier of competition name; it decides the
  best-of-five gate (`config/tennis_match_format.json`), the surface pin
  (`config/tennis_surface_map.json`) and the youth/friendly exclusion
  (`config/competition_tier_map.json`). Exact-name pins; unlisted = unknown =
  not gated.
- `source_ids.bzzoiro` is the integer you pass to `get_match_detail`. Tennis
  events carry none.
- `round_name / group_name / previous_leg_*` are **null in every dossier seen
  so far** even though `get_match_detail` returns them (memory:
  `fixture-context-stakes-never-populate`). Do not read null as "league
  fixture". For any cup tie, call `get_match_detail` and read `round_name`
  and `previous_leg_event_id` yourself.
- `is_local_derby` is the provider's flag and has been wrong (Grêmio–
  Internacional: `false` at 11 km). Treat `travel_distance_km < 25` as a
  derby candidate.

## `EventDossierV1` — `<date>_event_dossiers.json`

```
event_id, sport, team_a_name, team_b_name, lineup_status ("confirmed"|"predicted"|""),
readiness (READY|PARTIAL|BLOCKED), data_gaps[],
metrics: {canonical_name: {team_a_l10: [obs], team_b_l10: [obs], h2h: [obs]}},
player_metrics: [{player_id, player_name, team_name, canonical_name, l10: [obs]}],
fixture_context, referee, squad_availability[], season_form[]
```

One observation:

```json
{"provider": "bzzoiro", "match_id": "...", "match_date": "2026-08-27",
 "opponent": "...", "value": 4.0, "competition_id": "35", "season_id": "2026",
 "venue": "home|away|null", "surface": "Hard|Clay|Grass|null",
 "match_level": "GRAND_SLAM|GRAND_SLAM_QUALIFYING|TOUR|null",
 "quality_flag": null, "conflict_low": null, "conflict_high": null}
```

- `team_a_l10 / team_b_l10` are each side's **own** last matches; `h2h` the
  meetings. For a `*_total` market the row pools all three and collapses to
  one value per (bucket, day); for a `*_for` market only that side's bucket is
  used and `h2h` is deliberately empty (an h2h value carries no side marker).
- `readiness == READY` means the primary served ≥5 matches a side on the three
  priority metrics. It is what buys `CALL` in football. For tennis it only
  means the two providers agreed.
- `data_gaps` names what is missing and why: `not enriched: …` (slate gate),
  `MISIDENTIFIED` (payload named another player — dropped whole), provider
  identity failures, `VALID_EMPTY` standings.
- `referee`: `{name, matches, avg_yellow_per_match, avg_red_per_match,
  avg_fouls_per_match, avg_goals_per_match, career_games, career_yellow_cards,
  career_red_cards}`. **Read `matches` first**; null on roughly half the
  fixtures (the provider publishes no profile below 5 matches and names no
  official until close to kickoff). Blended into card-total centres only at
  `matches >= 15` (`_blend_referee`, `k=20`); flagged `ARGUES_AGAINST` only at
  `matches >= 8`.
- `squad_availability`: per side `{squad_size, unavailable_count,
  availability_unknown_count, unavailable: [{player_name, injury_type,
  injury_expected_return}]}`. Unknown is **not** folded into unavailable. A
  prop on an `unavailable` player never reaches the sheet (filtered in
  ANALYZE) but can go stale between ANALYZE and kickoff.
- `season_form`: per side `{position, xgf, xga, xg_games, form: "WDDDW", group}`
  — the only season-level xG in the system. **Read `xg_games` first.**
  `group` set ⇒ `position` ranks within the group.

## `StatsSheetRow` — `<date>_event_dossiers_stats_sheet[_top].json`

```
event_id, sport, market, line, direction, team_name, player_id, player_name, lineup_status,
hits, sample_size, pushes, hit_rate, p_low, p_central,
mean, median, mode, sample_min, sample_max, dispersion, shrunk_mean, centre_note, venue,
sources[], cross_provider_agreement, corroborated_matches, confidence, confidence_reason, data_quality,
tipster{}, market_signal{}, superbet{}, context_flags[], sample_excluded{}, lean_ceiling_reasons[], observation_flags{}
```

- `team_name` set ⇒ per-team (`*_for`) row; `player_id` set ⇒ prop row; both
  null ⇒ match total. Never infer the family from the market name.
- `pushes`: values exactly on an integer line; excluded from `hits` and
  `sample_size`. Every priced line ends in .5 so pushes are 0 there.
- `confidence` (`HIGH/MEDIUM/LOW`) is ANALYZE's coarse label on `n` and
  agreement; it does **not** see that one side contributed three
  observations. Check the split yourself.
- `venue`: the side the subject plays **tonight** (`home`/`away`) on football
  `*_for` rows; it selects the venue prior for `shrunk_mean`; null elsewhere.
- `superbet.implied_probability` is Superbet's own devigged number at this
  rung when both sides are posted.

### The three side columns (enums)

`tipster.verdict`: `CONFIRMS | CONTRADICTS | SPLIT | NO_COVERAGE`, with
`agree/oppose/exact/considered`, `lean` (1X2/BTTS tally — a *different*
market), `rated`, `*_record_low` (Wilson lower bound of the tipster's
self-reported record), `*_unproven`.

`market_signal.verdict`: `CONFIRMS | CONTRADICTS | SPLIT | NO_MARKET_DATA`;
`model_probability` (bzzoiro model at this exact line), `market_implied_
probability` (one bookmaker's paired over/under, pinnacle preferred),
`market_price`/`market_bookmaker` (best of ~88 books). Football only, and only
`corners_total` (model serves 8.5/9.5/10.5) and `goals_total` (model
1.5/2.5/3.5; feed has a price at 0.5, nothing at 4.5). **Tennis rows carry no
`market_signal` at all** since 2026-09-02 — not `NO_MARKET_DATA`, nothing.

`superbet.availability`: `OFFERED | LINE_NOT_OFFERED (nearest_offered_line/
price) | MARKET_NOT_OFFERED | OFFER_EMPTY | SCOPE_NOT_SUPPORTED | PLAYER_NOT_
MATCHED | EVENT_NOT_MATCHED | SUSPENDED`. `price` and `status` when `OFFERED`.

## `<date>_superbet_offer.json`

`generated_at` (snapshot time — quote it beside every price, and compare it with the sheet's and comparison's `generated_at`: a newer offer means row prices are from an older board), `events[]` with
`superbet_event_id, superbet_match_name, sport, kickoff, event_id,
match_quality (ID_MATCHED > EXACT > FUZZY; UNMATCHED), kickoff_delta_minutes,
lines[{market, line, direction, team_name, player_name, price, status,
source_market_name, source_outcome_name}], unmapped_markets`.
On an `ID_MATCHED` event a large kickoff delta is a clock fact, not a doubt;
on `EXACT`/`FUZZY` it is evidence worth a sentence.

## `<date>_superbet_comparison.json`

`generated_at`, `rows_considered`, `rows_compared`, `verdict_counts`
(`VALUE` / `PRICED_BELOW_THRESHOLD` / `MARKET_NOT_OFFERED` / `PLAYER_NOT_
MATCHED` / …, **both sports pooled**), `rows[]` (each with `sport, event_id,
match, market, line, direction, team_name, player_name, tier, p_low, hits,
sample_size, median, min_acceptable_odds, superbet_price,
superbet_implied_probability, superbet_status, superbet_market_name,
nearest_offered_line/price, odds_surplus, verdict`), `line_coverage` keyed
`"<sport>:<market>"` with `no_overlap`. This is the day's real yield; filter
`rows` by your sport. The
pipeline writes it **after** ANALYZE against the sheet that shipped; if you
re-ran ANALYZE by hand, re-run `run_superbet.py --offer … --stats-sheet …`
first or the counts describe a sheet that no longer exists.

## `<date>_market_context.json` (football)

Per fixture: bookmaker quotes (`total_corners`, `over_under_05/15/25/35`,
1X2, BTTS, handicaps), the consensus block, and the bzzoiro model
(`dc-blend-v1`: 1X2, xG, most likely score, over/under probabilities,
`confidence`). Use the 1X2 / xG to weight game-script scenarios A–D; never
convert them into a totals verdict.

## Coupon outputs (read-only for you)

`<date>_kupony.md` / `<date>_coupons.json`: header carries bar basis, gates
with counts, the supply funnel, and every applied veto with its reason.
`<date>_analyst_vetoes.json` is what the orchestrator saves from your JSON.
