# OddsAPI.io (odds-api-io) Recheck Report

**Recheck Date:** 2026-06-29  
**Auditor:** Kilo (gemini-3.5-flash)  
**Status:** PASS  

---

## 1. Configured Status

- **Status:** `PRIMARY_ACTIVE`
- **Key Location:** Configured in `config/api_keys.json` under `"odds-api-io"`.
- **Precedence:** Falls back to `config/api_keys.json` when the `ODDS_API_IO_KEY` environment variable is not defined.

---

## 2. Historical Metrics (From Previous Run Snapshot)

We parsed the cached snapshot (`src/betting/data/odds_api_io_snapshot.json` dated 2026-06-09) to recover baseline sport coverage metrics.

- **Total Events with Odds:** `296`
- **Total Value Bets (EV Opportunities):** `238`

### Events with Odds by Sport:
- **tennis:** `179`
- **football:** `99`
- **basketball:** `9`
- **cs2:** `5`
- **volleyball:** `2`
- **valorant:** `2`

### Point Lines (Handicaps / Totals):
A total of **1,351** market rows containing specific point lines (spreads, game totals, goal lines, over/under, draw-no-bet) were successfully parsed and attached.

---

## 3. Wimbledon Live Odds Recheck

We performed a live production query for Wimbledon events on **2026-06-29**:
- **Total Tennis Events Discovered:** `150`
- **Wimbledon Event Count:** `63` (representing WTA & ATP singles/doubles matches)
- **Sample Match:** `Bencic, Belinda vs Stojsavljevic, Mika (ID: 72362812)` inside league `WTA - Wimbledon, London, Great Britain`.
- **Live Odds Availability:** A cost-safe batch lookup (`/odds/multi`) successfully fetched real-time odds from major bookmakers (e.g., **Bet365**).

---

## 4. Provider Errors Check

- **OddsAPI.io Errors:** `None` (0 failures, stable rate limit remaining: `65`)
- **Other Providers:** Outdated key configurations on `odds-api` previously resulted in:
  `'odds-api/tennis: auth failed (401) — key expired or credits exhausted'`
  (This is resolved in our current run by refreshes and provider key routing updates).
