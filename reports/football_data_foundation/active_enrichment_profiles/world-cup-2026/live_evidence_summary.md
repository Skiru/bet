# Football Data Foundation Live Calibration

- Accepted foundation SHA: `c0aa63231cdb80aa0698bae30567b6df4a7c6d40`
- Current head before commit: `9869af6c88266b4e5df5e4d0a42638eb63219601`
- Branch: `feat/multisport-enrichment-v1`
- Upstream: `origin/feat/multisport-enrichment-v1`
- Generated at UTC: `2026-06-19T19:53:01.105268+00:00`
- No secrets, cookies, proxy settings, Tor, or browser profiles were used.
- Unit tests remain offline and do not perform network calls.
- Betting decision logic and production route selection are unchanged.

## Status Counts

- `EVIDENCE_READY`: 5
- `NOT_SUPPORTED`: 1

## Operation Results

- `espn-fifa-worldcup/direct_scoreboard` / `verify_endpoint` / `football:world:8/world-championship:lvUBR5F8` / `2026` => `EVIDENCE_READY`, row_count=1, evidence_identity=`1adbcb1991fb`
- `soccerdata/ESPN` / `read_schedule` / `football:world:8/world-championship:lvUBR5F8` / `2026` => `EVIDENCE_READY`, row_count=1, evidence_identity=`8cf5da8df404`
- `soccerdata/FBref` / `read_schedule` / `football:world:8/world-championship:lvUBR5F8` / `2026` => `EVIDENCE_READY`, row_count=1, evidence_identity=`8cf5da8df404`
- `soccerdata/Sofascore` / `read_schedule` / `football:world:8/world-championship:lvUBR5F8` / `2026` => `EVIDENCE_READY`, row_count=1, evidence_identity=`8cf5da8df404`
- `soccerdata/Understat` / `read_schedule` / `football:world:8/world-championship:lvUBR5F8` / `2026` => `NOT_SUPPORTED`, row_count=0, diagnostics=`mapped_from_source_result_status:UNSUPPORTED`
- `open_reference/OpenFootball` / `read_matches` / `football:world:8/world-championship:lvUBR5F8` / `2026` => `EVIDENCE_READY`, row_count=1, evidence_identity=`8cf5da8df404`
