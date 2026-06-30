# Football Market Family Mapping Review

## 1. Market Family Mapping Overview
To support structured modeling and automated construction of Bet Builder coupons, raw markets/odds from providers must be mapped to standardized high-level "Market Families."

---

## 2. Standardized Mappings

Our pipeline standardizes raw outcomes and market types from odds APIs and shortlists into the following target families:

* **RESULT:** 
  * Raw markets: `ml`, `h2h`, `moneyline`, `match winner`, `winner`, `draw_no_bet`, `double_chance`
  * Standardized category: `RESULT`
* **GOALS_TOTALS:** 
  * Raw markets: `totals`, `goals_over/under`, `over_under`, `over`, `under`
  * Standardized category: `GOALS_TOTALS` (mapped from the legacy `TOTALS`)
* **CORNERS:** 
  * Raw markets: `corners`, `corners_over/under`
  * Standardized category: `CORNERS`
* **CARDS:** 
  * Raw markets: `cards`, `booking_points`, `yellow_cards`, `red_cards`
  * Standardized category: `CARDS`
* **SHOTS:** 
  * Raw markets: `shots`, `shots_over/under`
  * Standardized category: `SHOTS`
* **SHOTS_ON_TARGET:** 
  * Raw markets: `shots_on_target`, `shots_on_goal`
  * Standardized category: `SHOTS_ON_TARGET`
* **HANDICAP:** 
  * Raw markets: `spread`, `handicap`
  * Standardized category: `HANDICAP`

---

## 3. Unsupported Market Families & Player Props

To prevent high-risk, unmodelable markets from being promoted to coupon construction, any player-specific props or complex event types (such as player tackles, player passes, player cards) are strictly blocked.

* **Target Unmapped Case:** `player_tackles`
* **Standardized Category:** `UNSUPPORTED_PROP_MATCH`
* **Reason for Blocking:** 
  * Our core probability engine operates on team-level Poisson / Negative Binomial statistics.
  * Individual player performance data is highly dynamic, subject to lineup updates, and lacks the stable, historical, sample-size-compliant database coverage required to generate non-hallucinated probabilities.
  * Therefore, player prop matches like `player_tackles` map to `UNSUPPORTED_PROP_MATCH`, which does **not** exist in the supported family list (`_supported_analytical_family`), ensuring they are filtered out and remain blocked with status `MISSING_MARKET_FAMILY` or `UNSUPPORTED_MARKET_FAMILY`.
