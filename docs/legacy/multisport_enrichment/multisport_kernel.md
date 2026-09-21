# Multisport Enrichment Kernel

This directory contains the shared multisport enrichment foundation kernel and profiles.

## Architecture

Instead of implementing seven separate, bloated modules for basketball, volleyball, hockey, tennis, CS2, Dota2, and Valorant, we use a single, profile-driven architecture.

### Supported Sports
- Basketball
- Volleyball
- Hockey
- Tennis
- CS2
- Dota 2
- Valorant

### Supported Providers
- SportDB (`sportdb`)
- Highlightly (`highlightly`)
- API-Sports Family (`api-sports-family`)
- TheSportsDB (`thesportsdb`)
- Pandascore (`pandascore`)
- Liquipedia Reference (`liquipedia-reference`)

### Success & Fail-Closed Policy
To prevent fake success, missing provider data must always result in `UNKNOWN` or `BLOCKED`. Real provider access observed but mapping insufficient is treated as a valid fail-closed outcome (`REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT`).
No production DB writes or live provider calls are allowed in Pass A.
