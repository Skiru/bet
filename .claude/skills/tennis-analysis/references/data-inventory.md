# Tennis data inventory — what is measured, by whom, at which rungs, and what is missing

Read from `src/bet/simple_stats/{providers,analyze,enrich,contracts}.py`,
`src/bet/api_clients/{tennis_abstract,tennis_score}.py`,
`config/tennis_match_format.json`, `config/tennis_surface_map.json`,
`config/market_priors.json` and the 2026-09-03 artifacts.

## Providers (both keyless and unmetered since 2026-09-02)

| Provider | Serves | Per observation | Does not serve |
|---|---|---|---|
| `tennis-abstract` | `aces_for/total`, `double_faults_for/total`, `first_serve_pct`, `break_points_faced`, `games_won`; **surface per match** (`surf`), draw level (`level`: G = slam incl. qualifying, separated by round pattern), the opponent's line for the same match; a whole career per page, no season/competition id | `surface`, `match_level` (`GRAND_SLAM / GRAND_SLAM_QUALIFYING / TOUR`), `opponent`, `match_date` | rankings (the client parses `orank` and it is **dropped before the dossier**), round (parsed, dropped), the score string (parsed, dropped), hold %, return %, tie-break counts, duration |
| `espn-tennis` | `total_games`, `total_sets` read off the published set score; tournament id + season; a rolling year of the daily scoreboard (~41 matches a player) | `competition_id`, `season_id`, surface via the competition pin only | serve statistics, opponent rank, round |
| `bzzoiro-tennis` | **nothing** — `402 addon_required` (Sports Addon $5/mo), withdrawn 2026-09-02, re-confirmed 2026-09-04 | — | everything (rankings, h2h, predictions, odds) |

Both compute games and sets from the published score, so an `AGREE` on
`total_games` means the two read the same match (before 2026-09-02
tennis-abstract ran one game low on every 7-6 set).

`READY` in tennis only means the two providers agreed — there is no primary,
hence `NO_REFERENCE_SOURCE` on every row and a `LEAN` ceiling always.

## Metrics per fixture (dossier `metrics`)

```
total_games, total_sets           # both sides pooled in the buckets; PRICED as own + own (framed centre)
games_won                         # per player (team_name = player)
aces_for, aces_total              # per player / framed total
double_faults_for, double_faults_total
break_points_faced                # per player, dossier-only (no market)
first_serve_pct                   # per player, dossier-only (no market)
```

`h2h` buckets exist for totals (meetings from both providers); per-player
rows use the player's own bucket only. There is **no** `breaks_total` any
more (bzzoiro-tennis was the only source of service games lost; break-*points*
are a different quantity and are not priced).

## Priced markets and rungs

| Market | Static lines (fallback) | Superbet 2026-09-03 ladder | Superbet name |
|---|---|---|---|
| `total_games` | 19.5, 21.5, 22.5, 23.5 | 12.5 … 36.5 (BO3 ~16.5–26.5; BO5 24.5–36.5) | Liczba gemów |
| `total_sets` | 2.5 | 2.5 (BO3); 3.5, 4.5 (BO5) | Liczba setów |
| `games_won` | 8.5, 10.5, 12.5 | 2.5 … 23.5 per player | `<Player> liczba gemów` |
| `aces_total` | 8.5, 10.5, 12.5 | 1.5 … 25.5 | Liczba asów |
| `aces_for` | 3.5 … 6.5 | 0.5 … 16.5 | `<Player> - liczba asów` |
| `double_faults_total` | 3.5, 5.5, 7.5 | 4.5 … 16.5 | Liczba podwójnych błędów |
| `double_faults_for` | 1.5 … 3.5 | 0.5 … 9.5 | `<Player> - liczba podwójnych błędów` |

Offer-driven ladders are trimmed to the rungs nearest the sample median
(`select_lines`) and to the sides the book posts. **No first-set market, no
tie-break market, no break market, no set-winner** on the sheet — the data to
price them is not collected (method §83: never infer a first-set read from
whole-match form).

## Scoping applied before counting (`sample_excluded`)

| Key | Rule | Config |
|---|---|---|
| `SURFACE_MISMATCH` | observation's surface ≠ tonight's pinned surface | `config/tennis_surface_map.json` — the four slams (ATP/WTA separately); unlisted competition = unknown = **no filter** |
| `MATCH_FORMAT_MISMATCH` | BO3 observation in a BO5 fixture's sample (length markets only) | `config/tennis_match_format.json` — men's slam main draws are BO5; slam qualifying is BO3 |
| `MATCH_FORMAT_UNKNOWN` | observation states no draw, fixture is BO5 | same |
| `STALE_H2H` | meeting older than 12 months | — |
| `CONFLICT_ON_LINE` | providers straddle the rung | — |

When the scoped sample of one side is empty, `analyze.suppressed_markets_for`
withholds the length-dependent markets (sets, games, aces, DFs) for that
fixture; a total whose framed centre cannot be computed (one side empty) is
no longer emitted from the pooled centre (fix of 2026-09-03). If you still
see a total with `a=0` or `b=0` in the dossier split, treat it as
`ESTIMAND_WRONG`.

## `centre_note` is a football field. On tennis it is always `null`.

Verified in code (`analyze.py`): the framed centre (`_framed_tennis_total_centre`)
feeds in as `centre_override`, and `centre_note` is written only by
`_blend_referee`, which returns `None` for every market outside
`_CARD_TOTAL_MARKETS` — i.e. always, for tennis. **A `null` `centre_note` on a
tennis total is not evidence the row still uses the pooled centre** — it tells
you nothing either way. The only way to check which centre a row used is the
arithmetic in "The framed centre" below: sum each side's own scoped mean and
compare it with the row's `mean`.

## The framed centre (`centre_note` on tennis totals)

`analyze._framed_tennis_total_centre`: the match total's centre is `own_A +
own_B` from the two players' scoped `*_for` samples, not the pooled mean of
"player + whoever they played". Pooled means target `(X+Y)/2 + μ_opponents`,
which is a different quantity (memory
`pooled-estimator-targets-wrong-quantity`). `total_sets` still uses the
pooled centre (no per-player sets metric) — say so when a `total_sets` row
tops the sheet.

## Priors (`config/market_priors.json`)

`aces_total` 8.07 (1,262 obs), `break_points_faced` 7.52, others per market;
no venue split (tennis has no venue). Shrinkage `n/(n+10)` toward these.
`shrunk_mean` beside `mean` shows how much of a row is prior.

## Context available and not

| Need (method §) | Available? | Where |
|---|---|---|
| surface (§66) | yes, per observation + fixture pin | observation `surface`; `event_list.competition` |
| format BO3/BO5 (§8) | yes via pin | `competition` |
| round / stage (§22) | **no** in artifacts | WebFetch order of play / draw |
| ranking, opponent rank (§67) | **no** | WebFetch (atptour.com / wtatennis.com / tennisabstract.com player pages) |
| previous match length, rest, duration (§73) | **no** | WebFetch (tournament results, flashscore-type pages — two domains) |
| retirement / injury / MTO (§22) | partial: `RET` matches dropped with a `data_gap` | WebFetch |
| hold %, return %, BP conversion, TB record (§18, §81) | **no** (only `break_points_faced`, `first_serve_pct`, aces, DFs) | WebFetch (tennisabstract.com serve/return tables by surface) |
| tie-break frequency (§86) | **no** | infer from scores you fetch; never from ace counts |
| match odds / favourite strength (§24 weights) | Superbet's own match odds in `superbet_offer.events[].result_market_lines` | label as the book's opinion; no consensus, no devig target for totals |
| h2h (§65) | yes: `h2h` buckets on totals, `STALE_H2H` >12 months | decay by hand: 1.0/0.75/0.50/0.25 |

## Verification without a source of record

1. **"Official"** means, in order of preference: the tournament's own site
   (`usopen.org`, `ausopen.com`, `rolandgarros.com`, `wimbledon.com`) **or**,
   when that times out or is unreachable (it does, routinely), the ATP/WTA
   tour site (`atptour.com`, `wtatennis.com`) — either counts as the primary
   domain, and you should say which one you actually used.
2. One further independent domain (a results aggregator, a tennis news site)
   to corroborate. One domain total → "unconfirmed"; two agreeing → verified;
   two disagreeing → report both and mark the fixture *godzina sporna*, do
   not pick one.
3. If the primary domain is unreachable after one retry, say so and proceed
   on the secondary plus one more — never on a single aggregator alone.
3. `verify_tennis_providers.py` (run by the orchestrator, exit 0/1) tells
   you whether the providers resolved real people today; `MISIDENTIFIED`
   gaps in the dossier are payloads dropped for naming someone else.

Tag every web statement `[WEB: domain, fetched <UTC>]`. Never quote a tennis
figure from before 2026-08-28.

## Known limits to state, not discover

- **`tennis-abstract`'s `match_date` is the tournament's start date, not the
  match date** — every round of one event carries the same date (e.g. every
  Prague WTA 250 match dated `2026-07-20`). It is fine for surface/format
  scoping and for "how many matches ago" ordering within one tournament, but
  it **cannot** answer a schedule/fatigue/rest question ("3 days ago") —
  those need `espn-tennis` (`match_date` is real) or the web.
- Per-player form is ~10 matches from tennis-abstract (`n ≤ 10` before h2h);
  espn-tennis adds ~41 per player for games/sets only.
- ATP players served off the `jsmatches` fallback carry a 2018-vintage sample
  with no guard — check dates.
- No tennis row can be `CALL`; no `market_signal`; no MCP; Superbet's
  `match_quality` for tennis is usually `FUZZY` (published times disagree) or
  `ID_MATCHED` (Betradar id).
- Tennis is **not settled** by `backtest_slate.py`; no calibration evidence
  exists for tennis `p_low`. Say it when asked how well tennis reads have done.
