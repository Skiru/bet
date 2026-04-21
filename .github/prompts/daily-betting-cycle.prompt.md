---
name: daily-betting-cycle
description: Settle the previous betting day, update betting memory, analyze today's slate, and write the daily report and coupon file.
agent: bet-analyst
argument-hint: "run_date=YYYY-MM-DD sports_focus=football,basketball,tennis,baseball,hockey bookmaker=Betclic"
tools:
  - search
  - edit
  - web
---

Use these inputs:
- run_date = ${input:run_date:YYYY-MM-DD}
- sports_focus = ${input:sports_focus:football,basketball,tennis,baseball,hockey}
- bookmaker = ${input:bookmaker:Betclic}
- bankroll_pln = 10
- local_timezone = Europe/Warsaw

Follow [repo instructions](../copilot-instructions.md), [artifact rules](../instructions/betting-artifacts.instructions.md), and [source registry](../../betting/sources/source-registry.md).

Tasks:
1. Resolve the current betting day from run_date using the repo betting-day window.
2. Ensure these paths exist and bootstrap them if missing with the exact headers and templates required by the artifact rules:
- betting/reports/
- betting/coupons/
- betting/journal/
- betting/sources/
- betting/journal/learning-log.md
- betting/journal/picks-ledger.csv
- betting/journal/coupons-ledger.csv
- betting/journal/source-log.csv
3. If betting/sources/source-registry.md is missing, stop and ask the user to add it instead of inventing a replacement.
4. Determine the previous betting day and settle every pending pick and coupon that should now be settled.
5. Use at least two verification sources when possible for settlement. If only one reliable source is available, say so explicitly in the report and notes.
6. Update the learning log with only process-level adjustments backed by settled results.
7. Update the source log for every important source checked during the run, including availability and whether it influenced final picks.
8. Scan the current betting-day slate across sports_focus. Prefer football, basketball, tennis, baseball, and hockey only if the source quality is strong enough that day.
9. Build a candidate board before final selection.
10. For each candidate, require at least one Tier A stats or fixture source and one Tier A market or price source. Tier B opinion sources may only support the case.
11. Compare bookmaker odds with market-best odds and compute price_gap_pct.
12. Reject low-risk candidates worse than -3% and higher-risk candidates worse than -5% unless the report explicitly documents why the reduced price is still acceptable and the stake is reduced.
13. Recheck all final odds immediately before writing the final artifacts.
14. Prefer 0 to 3 singles first. Then decide whether to include one low-risk coupon with a maximum of 3 legs and one higher-risk coupon with a maximum of 4 legs.
15. Never force both coupons. A no-bet day or one-coupon day is valid.
16. Enforce the 10 PLN total exposure cap and avoid correlated legs.
17. Overwrite the current betting-day report and coupon file.
18. Update the ledgers in place. Do not duplicate existing IDs for unchanged picks or coupons.
19. If no strong bets exist, still write the report and coupon file with NO BET TODAY and update the learning and source logs.

Required chat response after file updates:
- number of settled picks and coupons
- planned exposure for the current betting day
- number of singles and coupons created
- major source outages or data gaps