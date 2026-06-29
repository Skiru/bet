# The Odds API (odds-api) Key Refresh Probe

**Probe Date:** 2026-06-29  
**Auditor:** Kilo (gemini-3.5-flash)  
**Selected Key Source:** `config` (loaded from `config/api_keys.json`)  
**Auth Verdict:** PASS  

---

## 1. Authentication Status

The Odds API credentials was successfully refreshed and tested against the live production gateway.
- **Endpoint tested:** `/v4/sports` and `/v4/sports/soccer_epl/odds`
- **HTTP Response Code:** `200 OK`
- **Credits Used:** `1` (Listing sports is free / 0 credits; odds endpoint consumed 1 credit)
- **Quota Remaining:** `499` (Total monthly budget is `500` requests)
- **Status Verdict:** **PASS**

---

## 2. Active Sport Keys Coverage

The sports lookup returned **41** active/available sport keys.

| Sport Group | Number of Active Keys | Key Examples |
|---|---|---|
| **Football / Soccer** | 19 | `soccer_epl`, `soccer_germany_bundesliga`, `soccer_spain_la_liga`, `soccer_italy_serie_a`, `soccer_france_ligue_one`, `soccer_uefa_champs_league`, `soccer_uefa_europa_league`, `soccer_poland_ekstraklasa` |
| **Basketball** | 1 | `basketball_wnba` |
| **Tennis** | 2 | `tennis_atp_wimbledon`, `tennis_wta_wimbledon` |
| **Hockey** | 0 | None active today (off-season) |

---

## 3. Cost-Conservative Odds Probe

A miniature, budget-safe odds query was performed on the active sport key **`soccer_epl`**:
- **Event Count:** `10` events discovered on target date
- **Bookmaker Coverage Count:** `17` bookmakers returned
- **Market Count per Event:** `1` (`h2h` requested)
- **Errors Encountered:** `None`

---

## 4. Probe Metrics Summary

- **THE_ODDS_API_AUTH_VERDICT:** `PASS`
- **THE_ODDS_API_SELECTED_KEY_SOURCE:** `config`
- **THE_ODDS_API_EVENT_COUNT:** `10`
- **THE_ODDS_API_ODDS_COUNT:** `170` (10 events × 17 bookmakers)
- **THE_ODDS_API_ERRORS:** `[]`
