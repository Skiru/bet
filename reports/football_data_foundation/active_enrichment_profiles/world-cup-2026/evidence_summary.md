# Active Certification Evidence Summary - Profile: world-cup-2026

- Timestamp UTC: `2026-06-19T19:53:01.105268+00:00`
- No secrets, cookies, proxy settings, Tor, or browser profiles were used.
- Unit tests remain offline and do not perform network calls.
- Betting decision logic and production route selection are unchanged.

## Verified Evidence Tuples

- **espn-fifa-worldcup/direct_scoreboard** / `verify_endpoint` -> `EVIDENCE_READY` (row_count=1, schema=`1adbcb1991fb`)
- **soccerdata/ESPN** / `read_schedule` -> `EVIDENCE_READY` (row_count=1, schema=`8cf5da8df404`)
- **soccerdata/FBref** / `read_schedule` -> `EVIDENCE_READY` (row_count=1, schema=`8cf5da8df404`)
- **soccerdata/Sofascore** / `read_schedule` -> `EVIDENCE_READY` (row_count=1, schema=`8cf5da8df404`)
- **open_reference/OpenFootball** / `read_matches` -> `EVIDENCE_READY` (row_count=1, schema=`8cf5da8df404`)

## Blocked or Deferred Tuples

- **soccerdata/Understat** / `read_schedule` -> `NOT_SUPPORTED`: operation_has_no_live_evidence
