---
applyTo: "betting/**/*"
---

Write betting artifacts in a strict, reusable format.

General rules:
- Use the Europe/Warsaw betting-day convention defined in the repo instructions.
- Use dot decimals for odds and PLN amounts.
- Use YYYY-MM-DD for dates and YYYY-MM-DD HH:MM for local timestamps.
- Use | as the separator inside CSV cells that contain multiple source names.
- On reruns for the same betting day, update or replace same-day artifacts instead of duplicating them.

Daily report path:
- betting/reports/YYYY-MM-DD.md

Daily report required sections and order:
1. # Betting Day YYYY-MM-DD
2. ## Run Metadata
3. ## Previous Day Settlement
4. ## Learning Update
5. ## Source Availability
6. ## Candidate Board
7. ## Final Coupons
8. ## Rejected Picks
9. ## Exposure Summary

Daily report required content:
- Run Metadata must include betting_day, run_timestamp_local, bookmaker, sports_focus, and bankroll_cap_pln.
- Previous Day Settlement must include settled picks summary, settled coupons summary, previous day pnl, and rolling 7-day pnl when available.
- Learning Update must contain at most 3 process-level changes.
- Source Availability must log each important source with role, availability, and a short note.
- Candidate Board must show the shortlist with verdict values approved, rejected, or watch.
- Final Coupons must have Pewniaki, Low-Risk, and Higher-Risk subsections. Each coupon must include coupon_id, leg list (minimum 2 legs), combined_odds, stake_pln, correlation check, and main logic. Minimum 5 coupons total. No singles allowed.
- Rejected Picks must state the event or market and the rejection reason.
- Exposure Summary must include total_planned_exposure_pln, unused_bankroll_pln, and note that total suggested exposure may exceed daily budget (user decides which coupons to place).
- If no bet is made, still write every section and state NO BET TODAY where appropriate.

Daily coupon text path:
- betting/coupons/YYYY-MM-DD.txt

Coupon text required order:
BETTING DAY:
RUN TIME LOCAL:
BOOKMAKER:
BANKROLL CAP PLN:
TOTAL PLANNED EXPOSURE PLN:
UNUSED BANKROLL PLN:

PEWNIAKI COUPONS:
- coupon_id
- legs (minimum 2)
- combined_odds
- stake_pln
- rationale

LOW-RISK COUPONS:
- coupon_id
- legs (minimum 2)
- combined_odds
- stake_pln
- rationale

HIGHER-RISK COUPONS:
- coupon_id
- legs (minimum 2)
- combined_odds
- stake_pln
- rationale

WATCH LIST:
- backup picks with promotion criteria

SKIPPED OR OMITTED:
- explain why a coupon variant or the full slate was skipped

Minimum 5 coupons total. No singles. No maximum legs per coupon.
Total suggested stakes may exceed daily budget — user decides which coupons to place.
If a coupon variant is not justified, write OMITTED instead of forcing it.

Use these exact CSV headers.

betting/journal/picks-ledger.csv
betting_day,pick_id,event,sport,competition,market,selection,bookmaker,bookmaker_odds,market_best_odds,price_gap_pct,odds_checked_at_local,stake_pln,risk_tier,confidence_1_5,status,pnl_pln,stat_sources,market_sources,verification_sources,main_reason,main_risk,notes

betting/journal/coupons-ledger.csv
betting_day,coupon_id,variant,selections_count,pick_ids,combined_odds,stake_pln,risk_level,status,pnl_pln,odds_checked_at_local,correlation_check,main_logic,notes

betting/journal/source-log.csv
betting_day,source_name,role,sport_scope,availability,used_in_analysis,used_in_final_picks,notes

Field conventions:
- risk_tier values are low, medium, high.
- confidence_1_5 uses integers from 1 to 5.
- variant values are low-risk or higher-risk.
- risk_level values are low-risk or higher-risk.
- correlation_check values are pass or flagged.
- availability values are available, partial, or unavailable.
- used_in_analysis and used_in_final_picks values are yes or no.

ID and update rules:
- Pick IDs use PK-YYYYMMDD-##.
- Reuse an existing same-day pick ID when event + market + selection are unchanged.
- Coupon IDs: CP-YYYYMMDD-LR1, CP-YYYYMMDD-LR2, CP-YYYYMMDD-LR3 for low-risk coupons. CP-YYYYMMDD-HR1, CP-YYYYMMDD-HR2 for higher-risk coupons. Number sequentially when multiple coupons of same type exist.
- Legacy single-coupon IDs CP-YYYYMMDD-LR and CP-YYYYMMDD-HR are also valid.
- Overwrite same-day report and coupon files on rerun.
- Update ledger rows in place where IDs already exist. Do not append duplicate rows for the same ID.

Allowed pick statuses:
- pending
- win
- loss
- push
- void
- half_win
- half_loss

Allowed coupon statuses:
- pending
- win
- loss
- void

PnL rules:
- win = stake_pln * (odds - 1)
- loss = -stake_pln
- push = 0
- void = 0
- half_win = stake_pln * (odds - 1) / 2
- half_loss = -stake_pln / 2
- pending uses an empty pnl_pln cell
- if a coupon leg is void or push, recalculate effective combined odds from the remaining active legs and settle the coupon from the adjusted price