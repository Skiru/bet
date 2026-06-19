# Event Identity Contract Mapping Report - FIFA World Cup 2026

This report documents the identity mapping results for the simulated World Cup seeds against live provider events.

## Seed-to-Provider Identity Matches

### 1. United States vs Australia (Acceptance Event ID: `66456944`)
- **Status**: `IDENTITY_CONFIRMED`
- **Matched Providers**:
  - `espn-fifa-worldcup`
  - `soccerdata-espn-worldcup`
  - `sportdb-worldcup`
- **Fuzzy Name Resolution Notes**: Normalized "United States / USA" to match "united states" / "usa". Normalized "Australia / AUS" to match "australia" / "aus". Kickoff timezone difference offset matched within tolerance.

### 2. Scotland vs Morocco (Test Event ID: `66456945`)
- **Status**: `IDENTITY_CONFIRMED`
- **Matched Providers**: `espn-fifa-worldcup`, `soccerdata-espn-worldcup`

### 3. Brazil vs Haiti (Test Event ID: `66456946`)
- **Status**: `IDENTITY_CONFIRMED`
- **Matched Providers**: `espn-fifa-worldcup`, `soccerdata-espn-worldcup`

### 4. Turkey vs Paraguay (Test Event ID: `66456947`)
- **Status**: `IDENTITY_CONFIRMED`
- **Matched Providers**: `espn-fifa-worldcup`, `soccerdata-espn-worldcup`

### 5. Switzerland vs Canada (Test Event ID: `66456948`)
- **Status**: `IDENTITY_CONFIRMED`
- **Matched Providers**: `espn-fifa-worldcup`, `soccerdata-espn-worldcup`

### 6. Scotland vs Brazil (Test Event ID: `66456949`)
- **Status**: `IDENTITY_CONFIRMED`
- **Matched Providers**: `espn-fifa-worldcup`, `soccerdata-espn-worldcup`

## Match Tolerance Parameters
- **Time Tolerance**: `18000` seconds (5 hours)
- **Normalization Policy**: Lowercased, stripped punctuation, and stripped common noise tokens ("fc", "sc", "united", abbreviation codes, etc.) to guarantee robust matching without assuming identical ID values.
