# Football Data Foundation Pre-Certification Summary

- **Accepted A2 SHA**: `522c2f77a91bcbd68f38710039d4f18e7c80492e`
- **Calibration Profile**: `pre-certification`
- **Timestamp UTC**: `2026-06-19T17:27:13.199708+00:00`
- **Exact Command Parameters**: `{"league": "ENG-Premier League", "season": 2024, "max_rows": 5, "output_dir": "reports/football_data_foundation/certification_planning", "source_budget": 2, "operation_timeout_seconds": 90, "include_browser_sources": false, "include_heavy_sources": false, "offline_fixture_baseline": true, "write_samples": false, "sample_row_limit": 3, "invoked_command": "calibrate-live", "calibration_profile": "pre-certification"}`
- **No config, routing, or betting prediction/decision logic was changed.**
- **No secrets, cookies, proxy settings, Tor, or browser profiles were used.**
- **Unit tests remain offline and do not perform network calls.**

## Source Operations, Candidate Types, and Statuses

| Source ID | Operation | Scope | Status | Candidate Type | Row Count | Evidence Identity | Blocking Reason |
|-----------|-----------|-------|--------|----------------|-----------|-------------------|-----------------|
| `soccerdata/ClubElo` | `read_by_date` | `global/date:2024-08-15` | `PARSE_ERROR` | `needs_repair` | 0 | N/A | needs_repair |
| `soccerdata/ESPN` | `read_schedule` | `ENG-Premier League/2024` | `EVIDENCE_READY` | `schedule_current` | 380 | `70a866de6309` | N/A |
| `soccerdata/FBref` | `read_schedule` | `ENG-Premier League/2024` | `EVIDENCE_READY` | `schedule_current` | 380 | `3c0357042bd1` | N/A |
| `soccerdata/FBref` | `read_team_season_stats` | `ENG-Premier League/2024` | `EVIDENCE_READY` | `team_stats_current` | 20 | `fb731f6a95ab` | N/A |
| `soccerdata/FBref` | `read_team_match_stats` | `ENG-Premier League/2024` | `IMPLEMENTED_ACTIVE` | `not_candidate` | N/A | N/A | budget_exhausted |
| `soccerdata/FiveThirtyEight` | `availability_probe` | `ENG-Premier League/2024` | `NOT_SUPPORTED` | `not_candidate` | 0 | N/A | operation_has_no_live_evidence |
| `soccerdata/MatchHistory` | `read_games` | `ENG-Premier League/2024` | `PARSE_ERROR` | `needs_repair` | 0 | N/A | needs_repair |
| `soccerdata/Sofascore` | `read_leagues` | `ENG-Premier League/2024` | `EVIDENCE_READY` | `metadata_discovery` | 1 | `40cb2f968f90` | metadata_discovery_only |
| `soccerdata/Sofascore` | `read_schedule` | `ENG-Premier League/2024` | `EVIDENCE_READY` | `schedule_current` | 380 | `74f18ad00720` | N/A |
| `soccerdata/SoFIFA` | `read_versions` | `global/global` | `EVIDENCE_READY` | `ratings_context` | 855 | `4b3da2883009` | N/A |
| `soccerdata/Understat` | `read_schedule` | `ENG-Premier League/2024` | `EVIDENCE_READY` | `schedule_current` | 380 | `c6daae5c86be` | N/A |
| `soccerdata/Understat` | `read_team_match_stats` | `ENG-Premier League/2024` | `EVIDENCE_READY` | `xg_current` | 380 | `856d18345d44` | N/A |
| `soccerdata/Understat` | `read_shot_events` | `ENG-Premier League/2024` | `NOT_SUPPORTED` | `not_candidate` | N/A | N/A | operation_has_no_live_evidence |
| `soccerdata/WhoScored` | `read_schedule` | `ENG-Premier League/2024` | `NOT_SUPPORTED` | `event_context` | N/A | N/A | operation_has_no_live_evidence |
| `soccerdata/WhoScored` | `read_missing_players` | `ENG-Premier League/2024` | `NOT_SUPPORTED` | `event_context` | N/A | N/A | operation_has_no_live_evidence |
| `soccerdata/WhoScored` | `read_events` | `ENG-Premier League/2024` | `NOT_SUPPORTED` | `event_context` | N/A | N/A | operation_has_no_live_evidence |
| `open_reference/StatsBombOpenData` | `read_matches` | `statsbomb_open_data/fixture` | `EVIDENCE_READY` | `reference_fixture` | 1 | `166c8cc8f763` | fixture_only_reference_data |
| `open_reference/StatsBombPy` | `competitions` | `global/global` | `DEPENDENCY_MISSING` | `not_candidate` | N/A | N/A | operation_has_no_live_evidence |
| `open_reference/KaggleEuropeanSoccer` | `read_matches` | `kaggle_european_soccer/fixture` | `EVIDENCE_READY` | `historical_backtest` | 2 | `0535e7dde198` | fixture_only_reference_data |
| `open_reference/FootballDataOrg` | `get_fixtures_result` | `ENG-Premier League/2024` | `NOT_SUPPORTED` | `not_candidate` | N/A | N/A | operation_has_no_live_evidence |
| `open_reference/OpenFootball` | `read_matches` | `openfootball/fixture` | `EVIDENCE_READY` | `historical_backtest` | 1 | `3f104200be0d` | fixture_only_reference_data |
| `rich_unofficial/FotMobProbe` | `probe_matches` | `fixture_probe/fixture` | `VALID_EMPTY` | `reference_fixture` | 0 | N/A | operation_has_no_live_evidence |
| `rich_unofficial/SofaScoreRichProbe` | `probe_stats` | `fixture_probe/fixture` | `VALID_EMPTY` | `reference_fixture` | 0 | N/A | operation_has_no_live_evidence |
| `rich_unofficial/ScraperFCSofascore` | `read_match_stats` | `ENG-Premier League/2024` | `NOT_SUPPORTED` | `event_context` | N/A | N/A | operation_has_no_live_evidence |
| `event_model/socceraction_bridge` | `convert_events` | `global/global` | `DEPENDENCY_MISSING` | `not_candidate` | N/A | N/A | operation_has_no_live_evidence |
| `event_model/kloppy_bridge` | `load_tracking_data` | `global/global` | `DEPENDENCY_MISSING` | `not_candidate` | N/A | N/A | operation_has_no_live_evidence |
| `event_model/floodlight_bridge` | `load_events` | `global/global` | `DEPENDENCY_MISSING` | `not_candidate` | N/A | N/A | operation_has_no_live_evidence |
| `event_model/mplsoccer_bridge` | `draw_pitch` | `global/global` | `DEPENDENCY_MISSING` | `not_candidate` | N/A | N/A | operation_has_no_live_evidence |

## Source Repair Plan Action Items

| Source ID | Operation | Suspected Cause | Recommended Next Action | Priority |
|-----------|-----------|-----------------|-------------------------|----------|
| `soccerdata/ClubElo` | `read_by_date` | ClubElo API has no league schedule filtering and expects global date queries. Upstream service can also be down with 503. | Use global/date semantics. Ensure date is correctly formatted, robust to service down times, and implements upstream retry classification. | `high` |
| `soccerdata/MatchHistory` | `read_games` | Upstream football-data.co.uk service was offline returning 503, or league/season human label was passed raw instead of using explicit alias resolution mapping. | Implement robust league alias resolution mapping. Gracefully handle HTTP 503 / ConnectionError from football-data.co.uk. | `high` |
| `soccerdata/SoFIFA` | `read_versions` | TypeError because SoFIFA constructor got unexpected seasons argument. SoFIFA does not accept leagues/seasons in constructor. | Remove init_kwargs like leagues and seasons for SoFIFA. Run read_versions globally without league schedule semantics. Treated as ratings_context/context-only, not schedule/team stats route. | `high` |
| `soccerdata/FBref` | `read_team_match_stats` | source_budget_exhausted | Increase source_budget parameter to 3 or run with specific rich stats selection under pre-certification profile. | `medium` |
| `soccerdata/Understat` | `read_team_match_stats` | source_budget_exhausted | Increase source_budget parameter to 2 or run with specific rich stats selection. | `medium` |
| `soccerdata/WhoScored` | `read_schedule` | browser_source_disabled | Ensure browser-heavy scrapers are correctly skipped by default. Enable only when headless Playwright is pre-certified and safe. | `low` |
| `soccerdata/WhoScored` | `read_missing_players` | browser_source_disabled | Skip by default. Playwright headless browser setup required. | `low` |
| `soccerdata/WhoScored` | `read_events` | browser_source_disabled | Skip by default. Requires headless browser and high source budget/time. | `low` |
| `rich_unofficial/ScraperFCSofascore` | `read_match_stats` | browser_source_disabled or optional dependency ScraperFC missing | Keep as optional smoke import bridge only. Playwright required. | `low` |
| `open_reference/StatsBombPy` | `competitions` | Optional dependency statsbombpy is missing or skipped as import smoke | Ensure statsbombpy optional bridge works offline via import checks. | `low` |
| `event_model/socceraction_bridge` | `convert_events` | Optional dependency socceraction is missing or skipped as import smoke | Check offline import bridge. | `low` |
| `event_model/kloppy_bridge` | `load_tracking_data` | Optional dependency kloppy is missing or skipped as import smoke | Check offline import bridge. | `low` |
| `event_model/floodlight_bridge` | `load_events` | Optional dependency floodlight is missing or skipped as import smoke | Check offline import bridge. | `low` |
| `event_model/mplsoccer_bridge` | `draw_pitch` | Optional dependency mplsoccer is missing or skipped as import smoke | Check offline import bridge. | `low` |

## Next Certification Recommendations

The following exact tuples are recommended for the next phase of candidate certification:

- **Tuple**: (`"soccerdata/ESPN"`, `"read_schedule"`, `"schedule_current"`, `"current_discovery"`) - Priority: high
- **Tuple**: (`"soccerdata/FBref"`, `"read_schedule"`, `"schedule_current"`, `"current_discovery"`) - Priority: high
- **Tuple**: (`"soccerdata/FBref"`, `"read_team_season_stats"`, `"team_stats_current"`, `"fixture_team_statistics"`) - Priority: high
- **Tuple**: (`"soccerdata/Sofascore"`, `"read_schedule"`, `"schedule_current"`, `"current_discovery"`) - Priority: medium
- **Tuple**: (`"soccerdata/Understat"`, `"read_schedule"`, `"schedule_current"`, `"current_discovery"`) - Priority: high
- **Tuple**: (`"soccerdata/Understat"`, `"read_team_match_stats"`, `"xg_current"`, `"fixture_team_statistics"`) - Priority: high
