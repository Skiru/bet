# Football Data Foundation Certification Readiness Report

- **Accepted A2 SHA**: `522c2f77a91bcbd68f38710039d4f18e7c80492e`
- **Calibration Profile**: `pre-certification`
- **Timestamp UTC**: `2026-06-19T17:27:13.199708+00:00`

## Core Compliance Statements

- **no config files changed**: True (No configuration files under config/ were modified)
- **no routing changed**: True (No routing/decision routing rules were modified)
- **no betting decision logic changed**: True (No betting prediction/decision logic was modified)
- **no certified selectable written**: True (No certified selectable statuses were promoted or written)
- **all certification candidates are report-only**: True (All candidate recommendations remain report-only)

## Exact Next Recommended Certification Order

1. **soccerdata/ESPN** / `read_schedule` (Priority: high) - schedule_current capability
2. **soccerdata/FBref** / `read_schedule` (Priority: high) - schedule_current capability
3. **soccerdata/FBref** / `read_team_season_stats` (Priority: high) - team_stats_current capability
4. **soccerdata/Sofascore** / `read_schedule` (Priority: medium) - schedule_current capability
5. **soccerdata/Understat** / `read_schedule` (Priority: high) - schedule_current capability
6. **soccerdata/Understat** / `read_team_match_stats` (Priority: high) - xg_current capability

## Exact Blocked or Deferred Reasons

- **soccerdata/ClubElo / read_by_date**: needs_repair: PARSE_ERROR status indicates source requires code or protocol fix.
- **soccerdata/FBref / read_team_match_stats**: budget_exhausted
- **soccerdata/FiveThirtyEight / availability_probe**: not_supported: Source/operation is skipped or unsupported by default.
- **soccerdata/MatchHistory / read_games**: needs_repair: PARSE_ERROR status indicates source requires code or protocol fix.
- **soccerdata/Sofascore / read_leagues**: metadata_discovery_only: Metadata discovery is not route-certifiable as schedule/stats.
- **soccerdata/SoFIFA / read_versions**: context_only_ratings_context: Treated as ratings_context/context-only, not schedule/team stats route.
- **soccerdata/Understat / read_shot_events**: not_supported: Source/operation is skipped or unsupported by default.
- **soccerdata/WhoScored / read_schedule**: browser_heavy_source: skipped by default in this phase.
- **soccerdata/WhoScored / read_missing_players**: browser_heavy_source: skipped by default in this phase.
- **soccerdata/WhoScored / read_events**: browser_heavy_source: skipped by default in this phase.
- **open_reference/StatsBombOpenData / read_matches**: fixture_only_reference_data: Fixture-only references are excluded from route certification.
- **open_reference/StatsBombPy / competitions**: dependency_missing: Optional dependency bridge is missing/skipped.
- **open_reference/KaggleEuropeanSoccer / read_matches**: fixture_only_reference_data: Fixture-only references are excluded from route certification.
- **open_reference/FootballDataOrg / get_fixtures_result**: not_supported: Source/operation is skipped or unsupported by default.
- **open_reference/OpenFootball / read_matches**: fixture_only_reference_data: Fixture-only references are excluded from route certification.
- **rich_unofficial/FotMobProbe / probe_matches**: fixture_only_reference_data: Fixture-only references are excluded from route certification.
- **rich_unofficial/SofaScoreRichProbe / probe_stats**: fixture_only_reference_data: Fixture-only references are excluded from route certification.
- **rich_unofficial/ScraperFCSofascore / read_match_stats**: browser_heavy_source: skipped by default in this phase.
- **event_model/socceraction_bridge / convert_events**: dependency_missing: Optional dependency bridge is missing/skipped.
- **event_model/kloppy_bridge / load_tracking_data**: dependency_missing: Optional dependency bridge is missing/skipped.
- **event_model/floodlight_bridge / load_events**: dependency_missing: Optional dependency bridge is missing/skipped.
- **event_model/mplsoccer_bridge / draw_pitch**: dependency_missing: Optional dependency bridge is missing/skipped.
