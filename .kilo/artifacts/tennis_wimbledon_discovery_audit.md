# Tennis Wimbledon Discovery Audit

- as_of: `2026-06-29T06:00:27.938861+00:00`
- tennis_adapter_path: `src/bet/discovery/sources/odds_api_io.py`
- provider_used: `['odds-api-io']`
- command_run: `env PYTHONPATH=src:scripts .venv/bin/python3 scripts/discover_events.py --date 2026-06-29 --sports tennis`
- raw_tennis_event_count: `157`
- wimbledon_event_count: `63`
- player_a_player_b_present_count: `63`
- tournament_present_count: `63`
- round_present_count: `0`
- start_time_present_count: `63`
- surface_present_count: `0`
- provider_errors: `['odds-api/tennis: auth failed (401) — key expired or credits exhausted']`
- config_missing: `False`
- parser_errors: `False`
- TENNIS_COVERAGE_STATUS: `NO_MARKETS_OR_ODDS`

## Sample Wimbledon Events
- Bencic, Belinda vs Stojsavljevic, Mika | WTA - Wimbledon, London, Great Britain | 2026-06-29T10:00:00+00:00 | source=odds-api-io
- Cristian, Jaqueline vs Jovic, Iva | WTA - Wimbledon, London, Great Britain | 2026-06-29T10:00:00+00:00 | source=odds-api-io
- Sorribes Tormo, Sara vs Jimenez Kasintseva, Victoria | WTA - Wimbledon, London, Great Britain | 2026-06-29T10:00:00+00:00 | source=odds-api-io
- Pegula, Jessica vs Vidmanova, Darja | WTA - Wimbledon, London, Great Britain | 2026-06-29T10:00:00+00:00 | source=odds-api-io
- Sawangkaew, Mananchaya vs Chwalinska, Maja | WTA - Wimbledon, London, Great Britain | 2026-06-29T10:00:00+00:00 | source=odds-api-io
