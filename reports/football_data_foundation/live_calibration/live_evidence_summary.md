# Football Data Foundation Live Calibration

- Accepted foundation SHA: `c0aa63231cdb80aa0698bae30567b6df4a7c6d40`
- Current head before commit: `c0aa63231cdb80aa0698bae30567b6df4a7c6d40`
- Branch: `feat/multisport-enrichment-v1`
- Upstream: `origin/feat/multisport-enrichment-v1`
- Generated at UTC: `2026-06-19T16:04:26.224474+00:00`
- No secrets, cookies, proxy settings, Tor, or browser profiles were used.
- Unit tests remain offline and do not perform network calls.
- Betting decision logic and production route selection are unchanged.

## Status Counts

- `DEPENDENCY_MISSING`: 5
- `EVIDENCE_READY`: 7
- `IMPLEMENTED_ACTIVE`: 4
- `NOT_SUPPORTED`: 7
- `PARSE_ERROR`: 3
- `VALID_EMPTY`: 2

## Operation Results

- `soccerdata/ClubElo` / `read_by_date` / `ENG-Premier League` / `2024` => `PARSE_ERROR`, row_count=0, diagnostics=`mapped_from_source_result_status:PARSE_ERROR`
- `soccerdata/ESPN` / `read_schedule` / `ENG-Premier League` / `2024` => `EVIDENCE_READY`, row_count=380, evidence_identity=`70a866de6309`
- `soccerdata/FBref` / `read_schedule` / `ENG-Premier League` / `2024` => `EVIDENCE_READY`, row_count=380, evidence_identity=`3c0357042bd1`
- `soccerdata/FBref` / `read_team_season_stats` / `ENG-Premier League` / `2024` => `IMPLEMENTED_ACTIVE`, diagnostics=`source_budget_exhausted`
- `soccerdata/FBref` / `read_team_match_stats` / `ENG-Premier League` / `2024` => `IMPLEMENTED_ACTIVE`, diagnostics=`source_budget_exhausted`
- `soccerdata/FiveThirtyEight` / `availability_probe` / `ENG-Premier League` / `2024` => `NOT_SUPPORTED`, row_count=0, diagnostics=`mapped_from_source_result_status:NOT_SUPPORTED`
- `soccerdata/MatchHistory` / `read_games` / `ENG-Premier League` / `2024` => `PARSE_ERROR`, row_count=0, diagnostics=`mapped_from_source_result_status:PARSE_ERROR`
- `soccerdata/Sofascore` / `read_leagues` / `ENG-Premier League` / `2024` => `EVIDENCE_READY`, row_count=1, evidence_identity=`40cb2f968f90`
- `soccerdata/Sofascore` / `read_schedule` / `ENG-Premier League` / `2024` => `IMPLEMENTED_ACTIVE`, diagnostics=`source_budget_exhausted`
- `soccerdata/SoFIFA` / `read_versions` / `ENG-Premier League` / `2024` => `PARSE_ERROR`, row_count=0, diagnostics=`mapped_from_source_result_status:PARSE_ERROR`
- `soccerdata/Understat` / `read_schedule` / `ENG-Premier League` / `2024` => `EVIDENCE_READY`, row_count=380, evidence_identity=`c6daae5c86be`
- `soccerdata/Understat` / `read_team_match_stats` / `ENG-Premier League` / `2024` => `IMPLEMENTED_ACTIVE`, diagnostics=`source_budget_exhausted`
- `soccerdata/Understat` / `read_shot_events` / `ENG-Premier League` / `2024` => `NOT_SUPPORTED`, diagnostics=`heavy_source_disabled_by_default`
- `soccerdata/WhoScored` / `read_schedule` / `ENG-Premier League` / `2024` => `NOT_SUPPORTED`, diagnostics=`browser_source_disabled_by_default`
- `soccerdata/WhoScored` / `read_missing_players` / `ENG-Premier League` / `2024` => `NOT_SUPPORTED`, diagnostics=`browser_source_disabled_by_default`
- `soccerdata/WhoScored` / `read_events` / `ENG-Premier League` / `2024` => `NOT_SUPPORTED`, diagnostics=`browser_source_disabled_by_default`
- `open_reference/StatsBombOpenData` / `read_matches` / `statsbomb_open_data` / `fixture` => `EVIDENCE_READY`, row_count=1, evidence_identity=`166c8cc8f763`
- `open_reference/StatsBombPy` / `competitions` / `global` / `global` => `DEPENDENCY_MISSING`, diagnostics=`optional_dependency_missing`
- `open_reference/KaggleEuropeanSoccer` / `read_matches` / `kaggle_european_soccer` / `fixture` => `EVIDENCE_READY`, row_count=2, evidence_identity=`0535e7dde198`
- `open_reference/FootballDataOrg` / `get_fixtures_result` / `ENG-Premier League` / `2024` => `NOT_SUPPORTED`, diagnostics=`credential_required_but_not_enabled`
- `open_reference/OpenFootball` / `read_matches` / `openfootball` / `fixture` => `EVIDENCE_READY`, row_count=1, evidence_identity=`3f104200be0d`
- `rich_unofficial/FotMobProbe` / `probe_matches` / `fixture_probe` / `fixture` => `VALID_EMPTY`, row_count=0, diagnostics=`mapped_from_source_result_status:VALID_EMPTY`
- `rich_unofficial/SofaScoreRichProbe` / `probe_stats` / `fixture_probe` / `fixture` => `VALID_EMPTY`, row_count=0, diagnostics=`mapped_from_source_result_status:VALID_EMPTY`
- `rich_unofficial/ScraperFCSofascore` / `read_match_stats` / `ENG-Premier League` / `2024` => `NOT_SUPPORTED`, diagnostics=`browser_source_disabled_by_default`
- `event_model/socceraction_bridge` / `convert_events` / `global` / `global` => `DEPENDENCY_MISSING`, diagnostics=`optional_dependency_missing`
- `event_model/kloppy_bridge` / `load_tracking_data` / `global` / `global` => `DEPENDENCY_MISSING`, diagnostics=`optional_dependency_missing`
- `event_model/floodlight_bridge` / `load_events` / `global` / `global` => `DEPENDENCY_MISSING`, diagnostics=`optional_dependency_missing`
- `event_model/mplsoccer_bridge` / `draw_pitch` / `global` / `global` => `DEPENDENCY_MISSING`, diagnostics=`optional_dependency_missing`
