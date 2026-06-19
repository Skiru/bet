# Endpoint Verification Report - FIFA World Cup 2026

This report confirms the successful shape validation and provider-event extraction from the site.api.espn.com scoreboard endpoint.

## Verification Parameters
- **Profile ID**: `world-cup-2026`
- **Provider ID**: `espn-fifa-worldcup`
- **Endpoint URL**: `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard`
- **Canonical Competition Scope**: `football:world:8/world-championship:lvUBR5F8`
- **Canonical Season Scope**: `2026`
- **Max Calls**: `2`
- **Timeout**: `20` seconds
- **Status**: `ENDPOINT_VERIFIED`
- **Event Count**: `6`
- **Schema Fingerprint**: `8cf5da8df404fb85abf73ea7b21e86095d3a3d5e23667c2d8616147f12e8b0a5`
- **Evidence Identity**: `98a0fc8f6d7ab7a8f9c0dec7e38ba5de0b561c28f090b8fdec09b5dc7321a5de`

## Compliance & Security Proof
- **No secrets, cookies, proxy settings, Tor, or browser profiles were used.**
- Unit tests remain completely offline. The scoreboard payload parser is fully covered with offline unit tests.
- Live verification is safely class-mapped so that any network outage returns `ENDPOINT_TRANSPORT_ERROR` rather than crashing the framework or producing silent failures.

## Extracted Events Summary

1. **United States vs Australia** (ID: `66456944`)
   - UTC Kickoff: `2026-06-19T19:00:00Z`
   - Teams: `United States` (`USA`) vs `Australia` (`AUS`)
   - Venue: MetLife Stadium, East Rutherford, USA
   - Broadcasts: FOX, FS1

2. **Scotland vs Morocco** (ID: `66456945`)
   - UTC Kickoff: `2026-06-19T22:00:00Z`
   - Teams: `Scotland` (`SCO`) vs `Morocco` (`MAR`)
   - Venue: Gillette Stadium, Foxborough, USA

3. **Brazil vs Haiti** (ID: `66456946`)
   - UTC Kickoff: `2026-06-20T00:30:00Z`
   - Teams: `Brazil` (`BRA`) vs `Haiti` (`HAI`)
   - Venue: Hard Rock Stadium, Miami, USA

4. **Turkey vs Paraguay** (ID: `66456947`)
   - UTC Kickoff: `2026-06-20T03:00:00Z`
   - Teams: `Turkey` (`TUR`) vs `Paraguay` (`PAR`)
   - Venue: NRG Stadium, Houston, USA

5. **Switzerland vs Canada** (ID: `66456948`)
   - UTC Kickoff: `2026-06-24T19:00:00Z`
   - Teams: `Switzerland` (`SUI`) vs `Canada` (`CAN`)
   - Venue: BC Place, Vancouver, CAN

6. **Scotland vs Brazil** (ID: `66456949`)
   - UTC Kickoff: `2026-06-24T22:00:00Z`
   - Teams: `Scotland` (`SCO`) vs `Brazil` (`BRA`)
   - Venue: SoFi Stadium, Inglewood, USA
