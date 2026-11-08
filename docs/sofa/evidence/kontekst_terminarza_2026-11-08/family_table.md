# Family table - football and tennis market keys, generated from code

HEAD `e4fb587d4efcbcae7299ea1c0e2b707e7a4ca595` + uncommitted changes under src/bet/sofa or config; dispatch as of 2026-11-09 23:59Z; generator `family_table.py` (this folder). Keys: football 171, tennis 54, unclassified 0.

Classified by market key against the code dispatch symbols (C3), never by row notes / `forecast_source`. Football path (i) = final-centre multiplier, (ii) = pure-rating consumer (`FootballForecast.centre`); tennis rating / point_model / sample. `mapped` = some classifier / module emits the key for a Superbet market; `curve` = a key in a curve file (`sofa_confidence_calibration.json`, `sofa_confidence_calibration.next.json`, `sofa_confidence_calibration.next.2026-11-07.json`, `sofa_line_curves.json`, `sofa_tennis_point_curves.json`, `sofa_tennis_handicap_point_curves.json`, `sofa_football_sim_curves.json`).

## Counts per (sport, group, path)

| sport | group | path | keys |
|---|---|---|---|
| football | cards_fouls | (i) | 20 |
| football | corners | (i) | 9 |
| football | football_result | (ii) | 21 |
| football | goals | (i) | 9 |
| football | not_reached | (i) | 20 |
| football | not_reached | none | 69 |
| football | offsides | (i) | 6 |
| football | shots_sot | (i) | 17 |
| tennis | not_reached | sample | 19 |
| tennis | tennis_games_sets | rating | 12 |
| tennis | tennis_serve | point_model | 22 |
| tennis | tennis_winner | rating | 1 |

## Keys

| sport | key | group | path | reach_note | classified_by | mapped | curve | source |
|---|---|---|---|---|---|---|---|---|
| football | `both_over_cards_points` | cards_fouls | (i) | joint on marginal centres, as cards_points_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| football | `cards_points_1h_for` | cards_fouls | (i) | as cards_points_for (its live final centre x half share) | `football_card_halves.CARD_COUNT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `cards_points_1h_total` | cards_fouls | (i) | as cards_points_for (its live final centre x half share) | `football_card_halves.CARD_COUNT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `cards_points_2h_for` | cards_fouls | (i) | as cards_points_for (its live final centre x half share) | `football_card_halves.CARD_COUNT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `cards_points_2h_total` | cards_fouls | (i) | as cards_points_for (its live final centre x half share) | `football_card_halves.CARD_COUNT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `cards_points_for` | cards_fouls | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `cards_points_total` | cards_fouls | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `fouls_1h_for` | cards_fouls | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `fouls_1h_total` | cards_fouls | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `fouls_2h_for` | cards_fouls | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `fouls_2h_total` | cards_fouls | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `fouls_for` | cards_fouls | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `fouls_total` | cards_fouls | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `handicap_cards_points` | cards_fouls | (i) | joint on marginal centres, as cards_points_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| football | `handicap_cards_points_1h` | cards_fouls | (i) | as cards_points_1h_for (two half NBs on cards_points_for) | `football_card_halves.CARD_JOINT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `handicap_cards_points_2h` | cards_fouls | (i) | as cards_points_2h_for (two half NBs on cards_points_for); latent, no own curve: reach = as handicap_cards_points | `football_card_halves.CARD_JOINT_MARKETS` | yes | no | `football_card_halves.MARKETS` |
| football | `most_cards_points` | cards_fouls | (i) | joint on marginal centres, as cards_points_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_MOST)` |
| football | `most_cards_points_1h` | cards_fouls | (i) | as cards_points_1h_for (two half NBs on cards_points_for); latent, no own curve: reach = as most_cards_points | `football_card_halves.CARD_JOINT_MARKETS` | yes | no | `football_card_halves.MARKETS` |
| football | `most_cards_points_2h` | cards_fouls | (i) | as cards_points_2h_for (two half NBs on cards_points_for); latent, no own curve: reach = as most_cards_points | `football_card_halves.CARD_JOINT_MARKETS` | yes | no | `football_card_halves.MARKETS` |
| football | `player_fouls_for` | cards_fouls | (i) | share of fouls_for final centre (inherits the team term) | `config/sofa_player_share.json markets + player_share.TEAM_METRIC` | yes | yes | `market_mapper.PLAYER_MARKET_NAMES` |
| football | `both_over_corners` | corners | (i) | joint on marginal centres, as corners_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| football | `corners_1h_for` | corners | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `corners_1h_total` | corners | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `corners_2h_for` | corners | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `corners_2h_total` | corners | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `corners_for` | corners | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `corners_total` | corners | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `handicap_corners` | corners | (i) | joint on marginal centres, as corners_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| football | `most_corners` | corners | (i) | joint on marginal centres, as corners_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_MOST)` |
| football | `btts_any_half` | football_result | (ii) | minute simulator on pure rating goal centres; 0.60 floor key (D13, UNDER) - excluded until floor re-measured | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `btts_halves` | football_result | (ii) | minute simulator on pure rating goal centres; 0.60 floor key (D13, OVER) - excluded until floor re-measured | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `btts_or_over` | football_result | (ii) | pure rating NB goals (slice curves) | `football_score_markets.MARKETS` | yes | yes | `football_score_markets.MARKETS` |
| football | `dc_and_over` | football_result | (ii) | pure rating NB goals (slice curves) | `football_score_markets.MARKETS` | yes | yes | `football_score_markets.MARKETS` |
| football | `dc_and_under` | football_result | (ii) | pure rating NB goals (slice curves) | `football_score_markets.MARKETS` | yes | yes | `football_score_markets.MARKETS` |
| football | `double_chance` | football_result | (ii) | pure rating NB goals | `football_result.DOUBLE_CHANCE` | yes | yes | `football_result.DOUBLE_CHANCE` |
| football | `draw_no_bet` | football_result | (ii) | pure rating NB goals | `football_1x2_dnb.MARKETS` | yes | yes | `football_1x2_dnb.MARKETS` |
| football | `first_goal` | football_result | (ii) | pure rating NB goals (P(0-0), side share) | `football_incidents.FIRST_GOAL` | yes | yes | `football_incidents.INCIDENT_MARKETS` |
| football | `first_goal_1h` | football_result | (ii) | minute simulator on pure rating goal centres | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `half_goals_combo` | football_result | (ii) | minute simulator on pure rating goal centres; 0.60 floor key (D13, OVER) - excluded until floor re-measured | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `higher_scoring_half` | football_result | (ii) | minute simulator on pure rating goal centres | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `htft` | football_result | (ii) | minute simulator on pure rating goal centres | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `result_1h` | football_result | (ii) | minute simulator on pure rating goal centres | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `result_1x2` | football_result | (ii) | pure rating NB goals; latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `football_1x2_dnb.MARKETS` | yes | no | `football_1x2_dnb.MARKETS` |
| football | `result_2h` | football_result | (ii) | minute simulator on pure rating goal centres | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `result_handicap` | football_result | (ii) | pure rating NB goals (slice curves) | `football_score_markets.MARKETS` | yes | yes | `football_score_markets.MARKETS` |
| football | `result_or_btts` | football_result | (ii) | pure rating NB goals (slice curves) | `football_score_markets.MARKETS` | yes | yes | `football_score_markets.MARKETS` |
| football | `result_or_clean_sheet` | football_result | (ii) | pure rating NB goals (slice curves) | `football_score_markets.MARKETS` | yes | yes | `football_score_markets.MARKETS` |
| football | `result_or_over` | football_result | (ii) | pure rating NB goals (slice curves) | `football_score_markets.MARKETS` | yes | yes | `football_score_markets.MARKETS` |
| football | `result_or_under` | football_result | (ii) | pure rating NB goals (slice curves) | `football_score_markets.MARKETS` | yes | yes | `football_score_markets.MARKETS` |
| football | `team_scores_both_halves` | football_result | (ii) | minute simulator on pure rating goal centres; 0.60 floor key (D13, UNDER) - excluded until floor re-measured | `epochs.FOOTBALL_SIM_MARKETS` | yes | yes | `epochs.FOOTBALL_SIM_MARKETS` |
| football | `both_over_goals` | goals | (i) | joint on marginal centres, as goals_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| football | `goals_1h_for` | goals | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `goals_1h_total` | goals | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `goals_2h_for` | goals | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `goals_2h_total` | goals | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `goals_for` | goals | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `goals_total` | goals | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `handicap_goals` | goals | (i) | joint on marginal centres, as goals_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| football | `most_goals` | goals | (i) | joint on marginal centres, as goals_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_MOST)` |
| football | `goal_kicks_1h_for` | not_reached | (i) | team marginal (goal_kicks): path (i) would reach it mechanically; no exam group in rule (c) - not examined; no Superbet name maps to it (never priced) | `metrics.FOOTBALL_METRICS` | no | yes | `metrics.FOOTBALL_METRICS` |
| football | `goal_kicks_1h_total` | not_reached | (i) | team marginal (goal_kicks): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `goal_kicks_2h_for` | not_reached | (i) | team marginal (goal_kicks): path (i) would reach it mechanically; no exam group in rule (c) - not examined; no Superbet name maps to it (never priced) | `metrics.FOOTBALL_METRICS` | no | yes | `metrics.FOOTBALL_METRICS` |
| football | `goal_kicks_2h_total` | not_reached | (i) | team marginal (goal_kicks): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `goal_kicks_for` | not_reached | (i) | team marginal (goal_kicks): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `goal_kicks_total` | not_reached | (i) | team marginal (goal_kicks): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `saves_1h_for` | not_reached | (i) | team marginal (saves): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `saves_1h_total` | not_reached | (i) | team marginal (saves): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `saves_for` | not_reached | (i) | team marginal (saves): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `saves_total` | not_reached | (i) | team marginal (saves): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `tackles_for` | not_reached | (i) | team marginal (tackles): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `tackles_total` | not_reached | (i) | team marginal (tackles): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `throw_ins_1h_for` | not_reached | (i) | team marginal (throw_ins): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `throw_ins_1h_total` | not_reached | (i) | team marginal (throw_ins): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `throw_ins_2h_for` | not_reached | (i) | team marginal (throw_ins): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `throw_ins_2h_total` | not_reached | (i) | team marginal (throw_ins): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `throw_ins_for` | not_reached | (i) | team marginal (throw_ins): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `throw_ins_total` | not_reached | (i) | team marginal (throw_ins): path (i) would reach it mechanically; no exam group in rule (c) - not examined | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `xg_for` | not_reached | (i) | team marginal (xg): path (i) would reach it mechanically; no exam group in rule (c) - not examined; no Superbet name maps to it (never priced); latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `metrics.FOOTBALL_METRICS` | no | no | `metrics.FOOTBALL_METRICS` |
| football | `xg_total` | not_reached | (i) | team marginal (xg): path (i) would reach it mechanically; no exam group in rule (c) - not examined; no Superbet name maps to it (never priced); latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `metrics.FOOTBALL_METRICS` | no | no | `metrics.FOOTBALL_METRICS` |
| football | `both_over_corners_1h` | not_reached | none | raw sample joint (corners_1h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `both_over_corners_2h` | not_reached | none | raw sample joint (corners_2h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `both_over_fouls` | not_reached | none | raw sample joint (fouls_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| football | `both_over_fouls_1h` | not_reached | none | raw sample joint (fouls_1h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `both_over_fouls_2h` | not_reached | none | raw sample joint (fouls_2h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `both_over_goal_kicks` | not_reached | none | raw sample joint (goal_kicks_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_stat_variant` |
| football | `both_over_goals_1h` | not_reached | none | raw sample joint (goals_1h_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_mappable_family` |
| football | `both_over_goals_2h` | not_reached | none | raw sample joint (goals_2h_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_mappable_family` |
| football | `both_over_offsides` | not_reached | none | raw sample joint (offsides_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| football | `both_over_saves` | not_reached | none | raw sample joint (saves_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_mappable_family` |
| football | `both_over_saves_1h` | not_reached | none | raw sample joint (saves_1h_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_mappable_family` |
| football | `both_over_shots` | not_reached | none | raw sample joint (shots_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| football | `both_over_shots_1h` | not_reached | none | raw sample joint (shots_1h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `both_over_shots_2h` | not_reached | none | raw sample joint (shots_2h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `both_over_tackles` | not_reached | none | raw sample joint (tackles_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_stat_variant` |
| football | `both_over_throw_ins` | not_reached | none | raw sample joint (throw_ins_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_stat_variant` |
| football | `both_red_cards` | not_reached | none | league rate (reds/penalties) - not reached, power (M14); latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `football_card_halves.EVENT_MARKETS & TOTAL_MARKETS` | yes | no | `football_card_halves.MARKETS` |
| football | `handicap_corners_1h` | not_reached | none | raw sample joint (corners_1h_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_mappable_family` |
| football | `handicap_corners_2h` | not_reached | none | raw sample joint (corners_2h_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_mappable_family` |
| football | `handicap_fouls` | not_reached | none | raw sample joint (fouls_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| football | `handicap_fouls_1h` | not_reached | none | raw sample joint (fouls_1h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `handicap_fouls_2h` | not_reached | none | raw sample joint (fouls_2h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `handicap_goal_kicks` | not_reached | none | raw sample joint (goal_kicks_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `handicap_goals_1h` | not_reached | none | raw sample joint (goals_1h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `handicap_goals_2h` | not_reached | none | raw sample joint (goals_2h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `handicap_offsides` | not_reached | none | raw sample joint (offsides_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| football | `handicap_saves` | not_reached | none | raw sample joint (saves_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `handicap_saves_1h` | not_reached | none | raw sample joint (saves_1h_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `handicap_shots` | not_reached | none | raw sample joint (shots_for) - not reached; latent, no own curve: reach = as shots_for | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| football | `handicap_shots_1h` | not_reached | none | raw sample joint (shots_1h_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_stat_variant` |
| football | `handicap_shots_2h` | not_reached | none | raw sample joint (shots_2h_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_stat_variant` |
| football | `handicap_tackles` | not_reached | none | raw sample joint (tackles_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `handicap_throw_ins` | not_reached | none | raw sample joint (throw_ins_for) - not reached; no Superbet name maps to it (never priced) | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | no | yes | `curve file only` |
| football | `most_corners_1h` | not_reached | none | raw sample joint (corners_1h_for) - not reached; latent, no own curve: reach = as most_corners | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_corners_2h` | not_reached | none | raw sample joint (corners_2h_for) - not reached; latent, no own curve: reach = as most_corners | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_fouls` | not_reached | none | raw sample joint (fouls_for) - not reached; latent, no own curve: reach = as fouls_for | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST)` |
| football | `most_fouls_1h` | not_reached | none | raw sample joint (fouls_1h_for) - not reached; latent, no own curve: reach = as fouls_1h_for | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_fouls_2h` | not_reached | none | raw sample joint (fouls_2h_for) - not reached; latent, no own curve: reach = as fouls_2h_for | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_goals_1h` | not_reached | none | raw sample joint (goals_1h_for) - not reached; latent, no own curve: reach = as most_goals | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_goals_2h` | not_reached | none | raw sample joint (goals_2h_for) - not reached; latent, no own curve: reach = as most_goals | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_offsides` | not_reached | none | raw sample joint (offsides_for) - not reached; latent, no own curve: reach = as offsides_for | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST)` |
| football | `most_offsides_1h` | not_reached | none | raw sample joint (offsides_1h_for) - not reached; latent, no own curve: reach = as offsides_1h_for | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_offsides_2h` | not_reached | none | raw sample joint (offsides_2h_for) - not reached; latent, no own curve: reach = as offsides_2h_for | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_shots` | not_reached | none | raw sample joint (shots_for) - not reached | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_MOST)` |
| football | `most_shots_1h` | not_reached | none | raw sample joint (shots_1h_for) - not reached; latent, no own curve: reach = as most_shots | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_shots_2h` | not_reached | none | raw sample joint (shots_2h_for) - not reached; latent, no own curve: reach = as most_shots | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_shots_on_target_1h` | not_reached | none | raw sample joint (shots_on_target_1h_for) - not reached; latent, no own curve: reach = as most_shots_on_target | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `most_shots_on_target_2h` | not_reached | none | raw sample joint (shots_on_target_2h_for) - not reached; latent, no own curve: reach = as most_shots_on_target | `market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| football | `penalties_1h_for` | not_reached | none | league rate x exp(beta*supremacy) (side reds/penalties) - not reached, power (M14) | `football_card_halves.EVENT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `penalties_1h_total` | not_reached | none | league rate (reds/penalties) - not reached, power (M14) | `football_card_halves.EVENT_MARKETS & TOTAL_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `penalties_for` | not_reached | none | league rate x exp(beta*supremacy) (side reds/penalties) - not reached, power (M14) | `football_card_halves.EVENT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `penalties_total` | not_reached | none | league rate (reds/penalties) - not reached, power (M14) | `football_incidents.INCIDENT_MARKETS` | yes | yes | `football_incidents.INCIDENT_MARKETS` |
| football | `player_assists_for` | not_reached | none | non-share player prop - not reached | `players.PLAYER_METRICS` | yes | yes | `market_mapper.PLAYER_MARKET_NAMES` |
| football | `player_fouls_drawn_for` | not_reached | none | non-share player prop - not reached | `players.PLAYER_METRICS` | yes | yes | `market_mapper.PLAYER_PROPS_V2_NAMES` |
| football | `player_headed_shots_for` | not_reached | none | shot-detail prop (own starts, position pool) - not reached; latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `shot_detail.METRICS` | yes | no | `shot_detail.MARKET_NAMES` |
| football | `player_interceptions_for` | not_reached | none | non-share player prop - not reached; latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `players.PLAYER_METRICS` | yes | no | `market_mapper.PLAYER_MARKET_NAMES` |
| football | `player_left_foot_shots_for` | not_reached | none | shot-detail prop (own starts, position pool) - not reached | `shot_detail.METRICS` | yes | yes | `shot_detail.MARKET_NAMES` |
| football | `player_offsides_for` | not_reached | none | non-share player prop - not reached | `players.PLAYER_METRICS` | yes | yes | `market_mapper.PLAYER_MARKET_NAMES` |
| football | `player_right_foot_shots_for` | not_reached | none | shot-detail prop (own starts, position pool) - not reached | `shot_detail.METRICS` | yes | yes | `shot_detail.MARKET_NAMES` |
| football | `player_shots_outside_box_for` | not_reached | none | shot-detail prop (own starts, position pool) - not reached; latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `shot_detail.METRICS` | yes | no | `shot_detail.MARKET_NAMES` |
| football | `player_sot_headed_for` | not_reached | none | shot-detail prop (own starts, position pool) - not reached; latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `shot_detail.METRICS` | yes | no | `shot_detail.MARKET_NAMES` |
| football | `player_sot_left_foot_for` | not_reached | none | shot-detail prop (own starts, position pool) - not reached; latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `shot_detail.METRICS` | yes | no | `shot_detail.MARKET_NAMES` |
| football | `player_sot_outside_box_for` | not_reached | none | shot-detail prop (own starts, position pool) - not reached; latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `shot_detail.METRICS` | yes | no | `shot_detail.MARKET_NAMES` |
| football | `player_sot_right_foot_for` | not_reached | none | shot-detail prop (own starts, position pool) - not reached; latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured) | `shot_detail.METRICS` | yes | no | `shot_detail.MARKET_NAMES` |
| football | `player_tackles_for` | not_reached | none | non-share player prop - not reached (TEAM_METRIC lists it, config has no cell) | `players.PLAYER_METRICS` | yes | yes | `market_mapper.PLAYER_MARKET_NAMES` |
| football | `red_cards_1h_for` | not_reached | none | league rate x exp(beta*supremacy) (side reds/penalties) - not reached, power (M14) | `football_card_halves.EVENT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `red_cards_1h_total` | not_reached | none | league rate (reds/penalties) - not reached, power (M14) | `football_card_halves.EVENT_MARKETS & TOTAL_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `red_cards_for` | not_reached | none | league rate x exp(beta*supremacy) (side reds/penalties) - not reached, power (M14) | `football_card_halves.EVENT_MARKETS` | yes | yes | `football_card_halves.MARKETS` |
| football | `red_cards_total` | not_reached | none | league rate (reds/penalties) - not reached, power (M14) | `football_incidents.INCIDENT_MARKETS` | yes | yes | `football_incidents.INCIDENT_MARKETS` |
| football | `offsides_1h_for` | offsides | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `offsides_1h_total` | offsides | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `offsides_2h_for` | offsides | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `offsides_2h_total` | offsides | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `offsides_for` | offsides | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `offsides_total` | offsides | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `both_over_shots_on_target` | shots_sot | (i) | joint on marginal centres, as shots_on_target_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| football | `handicap_shots_on_target` | shots_sot | (i) | joint on marginal centres, as shots_on_target_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| football | `most_shots_on_target` | shots_sot | (i) | joint on marginal centres, as shots_on_target_for | `epochs.DERIVED_MARGINAL_CENTRES_METRICS` | yes | yes | `market_mapper.classify_derived_market(_MOST)` |
| football | `player_shots_for` | shots_sot | (i) | share of shots_for final centre (inherits the team term) | `config/sofa_player_share.json markets + player_share.TEAM_METRIC` | yes | yes | `market_mapper.PLAYER_MARKET_NAMES` |
| football | `player_shots_on_target_for` | shots_sot | (i) | share of shots_for final centre (inherits the team term) | `config/sofa_player_share.json markets + player_share.TEAM_METRIC` | yes | yes | `market_mapper.PLAYER_MARKET_NAMES` |
| football | `shots_1h_for` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `shots_1h_total` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `shots_2h_for` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `shots_2h_total` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `shots_for` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `shots_on_target_1h_for` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `shots_on_target_1h_total` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `shots_on_target_2h_for` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `shots_on_target_2h_total` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `shots_on_target_for` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| football | `shots_on_target_total` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| football | `shots_total` | shots_sot | (i) | team marginal, final centre | `metrics.FOOTBALL_METRICS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `both_over_aces` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as aces_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| tennis | `both_over_double_faults` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as double_faults_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| tennis | `both_over_games` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as games_won_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| tennis | `both_over_serve_points` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as serve_points_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_BOTH_OVER)` |
| tennis | `handicap_aces` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as aces_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| tennis | `handicap_double_faults` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as double_faults_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| tennis | `handicap_serve_points` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as serve_points_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| tennis | `most_aces` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as aces_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST)` |
| tennis | `most_aces_set1` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as aces_set1_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| tennis | `most_aces_set2` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as aces_set2_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| tennis | `most_double_faults` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as double_faults_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST)` |
| tennis | `most_double_faults_set1` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as double_faults_set1_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| tennis | `most_double_faults_set2` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as double_faults_set2_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| tennis | `most_games_won_set1` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as games_won_set1_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| tennis | `most_games_won_set2` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as games_won_set2_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| tennis | `most_serve_points` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as serve_points_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST)` |
| tennis | `most_serve_points_set1` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as serve_points_set1_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| tennis | `most_serve_points_set2` | not_reached | sample | raw sample joint - not reached (C14); latent, no own curve: reach = as serve_points_set2_for | `market_mapper.derived_base (tennis, not rating / point model)` | yes | no | `market_mapper.classify_derived_market(_MOST_SCOPED)` |
| tennis | `tiebreaks_total` | not_reached | sample | players' sample estimator - not reached (C14) | `metrics.TENNIS_METRICS (no rating / point-model symbol)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `games_total` | tennis_games_sets | rating | 0.5 rating neighbours + 0.5 sample NB: partly reached (C14); 0.60 floor key (D13) - excluded until floor re-measured | `tennis_rating.RATED_MARKETS + W_GAMES_TOTAL_RATING` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `games_won_for` | tennis_games_sets | rating | rating neighbours (subject's margin) | `tennis_rating.RATING_PRICED_MARKETS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `games_won_set1_for` | tennis_games_sets | rating | rating neighbours | `tennis_rating.SET_RATING_PRICED_MARKETS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `games_won_set2_for` | tennis_games_sets | rating | rating neighbours | `tennis_rating.SET_RATING_PRICED_MARKETS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `games_won_set3_for` | tennis_games_sets | rating | rating neighbours | `tennis_rating.SET_RATING_PRICED_MARKETS` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `handicap_games` | tennis_games_sets | rating | rating neighbours (subject's margin) (C3 trap: not the point model, unlike handicap_games_won_set1/2) | `tennis_rating.RATING_PRICED_MARKETS` | yes | yes | `market_mapper.classify_derived_market(_HANDICAP_PATTERNS)` |
| tennis | `most_games` | tennis_games_sets | rating | rating neighbours (subject's margin); draw subject stays on the sample | `tennis_rating.RATING_PRICED_MARKETS` | yes | yes | `market_mapper.classify_derived_market(_MOST)` |
| tennis | `set1_won_for` | tennis_games_sets | rating | home player's rating neighbours (set scores) | `tennis_sets.SET_MARKETS` | yes | yes | `tennis_sets.SET_MARKETS` |
| tennis | `set2_won_for` | tennis_games_sets | rating | home player's rating neighbours (set scores) | `tennis_sets.SET_MARKETS` | yes | yes | `tennis_sets.SET_MARKETS` |
| tennis | `set_score` | tennis_games_sets | rating | home player's rating neighbours (set scores) | `tennis_sets.SET_MARKETS` | yes | yes | `tennis_sets.SET_MARKETS` |
| tennis | `set_score_not` | tennis_games_sets | rating | home player's rating neighbours (set scores) | `tennis_sets.SET_MARKETS` | yes | yes | `tennis_sets.SET_MARKETS` |
| tennis | `sets_total` | tennis_games_sets | rating | rating neighbours; 0.60 floor key (D13) - excluded until floor re-measured | `tennis_rating.SET_RATING_PRICED_MARKETS` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `aces_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `aces_set1_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `aces_set1_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `aces_set2_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `aces_set2_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `aces_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `double_faults_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `double_faults_set1_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `double_faults_set1_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `double_faults_set2_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `double_faults_set2_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `double_faults_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `games_set1_total` | tennis_serve | point_model | point model replaces the neighbours' p (C3 trap: also in SET_RATING_PRICED_MARKETS, rows say forecast_source tennis_rating) | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `games_set2_total` | tennis_serve | point_model | point model replaces the neighbours' p (C3 trap: also in SET_RATING_PRICED_MARKETS, rows say forecast_source tennis_rating) | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `handicap_games_won_set1` | tennis_serve | point_model | point model set margin (C3 trap: handicap_games stays on the rating) | `epochs.tennis_point_markets (TENNIS_HANDICAP_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.classify_mappable_family` |
| tennis | `handicap_games_won_set2` | tennis_serve | point_model | point model set margin (C3 trap: handicap_games stays on the rating) | `epochs.tennis_point_markets (TENNIS_HANDICAP_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.classify_mappable_family` |
| tennis | `serve_points_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `serve_points_set1_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `serve_points_set1_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `serve_points_set2_for` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.TEAM_MARKET_PATTERNS` |
| tennis | `serve_points_set2_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `serve_points_total` | tennis_serve | point_model | point model serve counts | `epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)` | yes | yes | `market_mapper.MATCH_MARKET_NAMES` |
| tennis | `match_won_for` | tennis_winner | rating | calibrated p_home directly | `tennis_winner.MATCH_WON_FOR` | yes | yes | `tennis_winner.MATCH_WON_FOR` |

## Not classified from code

- none

## Comparison with the r1 inventories

Football inventory (r1 section 5b): 133 keys; tennis inventory: 44.

- in the inventory, not in the code table: none
- football: mapped in code, absent from r1 section 5b: `both_red_cards`, `goal_kicks_1h_total`, `goal_kicks_2h_total`, `handicap_fouls`, `handicap_goals`, `handicap_offsides`, `most_fouls`, `most_fouls_1h`, `most_fouls_2h`, `most_goals`, `most_goals_1h`, `most_goals_2h`, `most_offsides`, `most_offsides_1h`, `most_offsides_2h`, `most_shots_on_target_1h`, `most_shots_on_target_2h`, `player_interceptions_for`, `red_cards_1h_for`
- tennis: mapped in code, absent from r1 tennis: `both_over_aces`, `both_over_double_faults`, `both_over_games`, `both_over_serve_points`, `games_won_set3_for`, `handicap_double_faults`, `handicap_serve_points`, `most_double_faults`, `most_games_won_set1`, `most_games_won_set2`
- in a curve file but not mapped by any classifier: `goal_kicks_1h_for`, `goal_kicks_2h_for`, `both_over_corners_1h`, `both_over_corners_2h`, `both_over_fouls_1h`, `both_over_fouls_2h`, `both_over_shots_1h`, `both_over_shots_2h`, `handicap_fouls_1h`, `handicap_fouls_2h`, `handicap_goal_kicks`, `handicap_goals_1h`, `handicap_goals_2h`, `handicap_saves`, `handicap_saves_1h`, `handicap_tackles`, `handicap_throw_ins`
