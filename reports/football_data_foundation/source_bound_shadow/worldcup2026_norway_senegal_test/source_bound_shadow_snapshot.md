# Source-Bound Shadow Snapshot Report
Fixture: worldcup2026-norway-senegal
Status: Match Finished
Competition: FIFA World Cup
Kickoff (UTC): 2026-06-23T00:00:00+00:00
Venue: MetLife Stadium
Referee: Sampaio W.
Teams: Norway vs Senegal
Score: Norway 3 - 2 Senegal

## Provider Mappings
- api-football: 1489401
- espn-baseline: 760454
- football-data-org: 537394
- highlightly: 1267481035
- sportdb: xSUJLPV8

## Verification Invariants
- Production Selectable: False
- Manual Authorization Required: True
- Shadow Status: SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW

## Facts Included (76)
- [api-football] provider_mapping.api-football.provider_match_id = 1489401 (SHA256: 934e96c9...)
- [api-football] fixture_identity.teams = {'home': 'Norway', 'away': 'Senegal'} (SHA256: 934e96c9...)
- [api-football] fixture_identity.fixture_slug = worldcup2026-norway-senegal (SHA256: 934e96c9...)
- [api-football] score.full_time_score = {'home': 3, 'away': 2} (SHA256: 934e96c9...)
- [api-football] match_status.status = Match Finished (SHA256: 934e96c9...)
- [api-football] kickoff.kickoff_utc = 2026-06-23T00:00:00+00:00 (SHA256: 934e96c9...)
- [api-football] venue.venue = MetLife Stadium (SHA256: 934e96c9...)
- [api-football] match_event_summary.event_summary = {'event_count': 15, 'goals': [{'minute': 43, 'team': 'Norway', 'player': 'M. Pedersen'}, {'minute': 48, 'team': 'Norway', 'player': 'E. Haaland'}, {'minute': 53, 'team': 'Senegal', 'player': 'I. Sarr'}, {'minute': 58, 'team': 'Norway', 'player': 'E. Haaland'}, {'minute': 90, 'team': 'Senegal', 'player': 'I. Sarr'}], 'cards_count': 0, 'substitutions_count': 10, 'provider_event_categories': ['goal', 'subst']} (SHA256: 934e96c9...)
- [api-football] lineup_summary.lineup_summary = {'teams_with_lineups': 2, 'formations': ['4-2-3-1', '4-3-3'], 'listed_player_count': 52, 'unavailable_suspension_injury_counts': {'unavailable': 0, 'suspension': 0, 'injury': 0}} (SHA256: 934e96c9...)
- [api-football] statistics_summary.statistics_summary = {'stat_group_count': 18, 'stat_groups': ['Ball Possession', 'Blocked Shots', 'Corner Kicks', 'Fouls', 'Goalkeeper Saves', 'Offsides', 'Passes %', 'Passes accurate', 'Red Cards', 'Shots insidebox', 'Shots off Goal', 'Shots on Goal', 'Shots outsidebox', 'Total Shots', 'Total passes', 'Yellow Cards', 'expected_goals', 'goals_prevented'], 'selected_numeric_stats': {'shots_on_goal_norway': 7, 'shots_off_goal_norway': 3, 'total_shots_norway': 13, 'blocked_shots_norway': 3, 'shots_insidebox_norway': 11, 'shots_outsidebox_norway': 2, 'fouls_norway': 13, 'corner_kicks_norway': 5, 'offsides_norway': 0, 'ball_possession_norway': 42, 'goalkeeper_saves_norway': 2, 'total_passes_norway': 352, 'passes_accurate_norway': 283, 'passes_%_norway': 80, 'expected_goals_norway': 2.1, 'goals_prevented_norway': -1.19, 'shots_on_goal_senegal': 4, 'shots_off_goal_senegal': 6, 'total_shots_senegal': 16, 'blocked_shots_senegal': 6, 'shots_insidebox_senegal': 10, 'shots_outsidebox_senegal': 6, 'fouls_senegal': 5, 'corner_kicks_senegal': 4, 'offsides_senegal': 4, 'ball_possession_senegal': 58, 'goalkeeper_saves_senegal': 3, 'total_passes_senegal': 487, 'passes_accurate_senegal': 429, 'passes_%_senegal': 88, 'expected_goals_senegal': 1.7, 'goals_prevented_senegal': -1.19}} (SHA256: 934e96c9...)
- [api-football] provider_mapping.api-football.provider_match_id = 1489401 (SHA256: 15a9b5a9...)
- [api-football] fixture_identity.teams = {'home': 'Norway', 'away': 'Senegal'} (SHA256: 15a9b5a9...)
- [api-football] fixture_identity.fixture_slug = worldcup2026-norway-senegal (SHA256: 15a9b5a9...)
- [api-football] score.full_time_score = {'home': 3, 'away': 2} (SHA256: 15a9b5a9...)
- [api-football] match_status.status = Match Finished (SHA256: 15a9b5a9...)
- [api-football] kickoff.kickoff_utc = 2026-06-23T00:00:00+00:00 (SHA256: 15a9b5a9...)
- [api-football] venue.venue = MetLife Stadium (SHA256: 15a9b5a9...)
- [football-data-org] provider_mapping.football-data-org.provider_match_id = 537394 (SHA256: c2d80956...)
- [football-data-org] fixture_identity.teams = {'home': 'Norway', 'away': 'Senegal'} (SHA256: c2d80956...)
- [football-data-org] fixture_identity.fixture_slug = worldcup2026-norway-senegal (SHA256: c2d80956...)
- ... and 56 more facts

## Active Conflicts
No active conflicts detected.
