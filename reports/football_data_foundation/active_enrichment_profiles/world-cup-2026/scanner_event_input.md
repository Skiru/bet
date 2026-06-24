# Scanner Acceptance Event Candidate - FIFA World Cup 2026

This report documents the simulated scanner event output used as input for the active enrichment validation.

## Event Metadata
- **Scanner Event ID**: `66456944`
- **Profile ID**: `world-cup-2026`
- **Sport**: `football`
- **Canonical Competition Scope**: `football:world:8/world-championship:lvUBR5F8`
- **Canonical Season Scope**: `2026`
- **Kickoff Local (Europe/Warsaw)**: `2026-06-19T21:00:00+02:00`
- **Kickoff UTC**: `2026-06-19T19:00:00Z`
- **Home Team**: `United States` (`USA`)
- **Away Team**: `Australia` (`AUS`)
- **Group Label**: `Group D`
- **Scanner Truth Kind**: `schedule_snapshot`
- **Scanner Confidence**: `high`
- **Scanner Source**: `acceptance_fixture_seed`

## Rules
- The scanner event candidate is only the triggering input and is *never* treated as provider evidence.
- Enrichment must retrieve actual live provider data to certify active active-enrichment tuples.
