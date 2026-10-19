---
description: Settle a finished sofa day through the sofa-settler agent - SETTLE and the sports' settles, identity audit, re-settle sweep, ledger, the coupon's real result (7c) and the read-removed legs (7i) apart, and a refit recommendation the operator decides.
argument-hint: wczoraj | YYYY-MM-DD
---

Settle one finished day. `sofa-settler` owns the whole procedure (bridge, SETTLE,
SHADOW_SETTLE / CS2_SETTLE under the loop conditions, identity audit, re-settle sweep,
ledger and coupon marking, audit_settlement, audit_day_deep, niche scanner, refit
judgement, config hygiene). Nothing runs in the main session except the launch.

## 1 - resolve the date

- `wczoraj` or no argument: `<date>` = yesterday in UTC (`date -u -v-1d +%F`).
- `YYYY-MM-DD`: that date.
- Refuse today or a future date: SETTLE against an unfinished day grades nothing.
- Settle before a live day's build starts - SETTLE and the build share the bridge.

## 2 - launch the settler

Launch `sofa-settler` in the **foreground** (`run_in_background: false`) with:

```
Settle <date> (D-1 = <date>, D = <date+1>). Scratch dir: <session scratchpad>/settle_<date>/.
Follow your procedure end to end and return your Polish report.
```

Do not run any of its scripts yourself and do not repeat its steps; if it stops
(bridge exit 2, a crash), relay where and why.

## 3 - relay the report

Relay the settler's report in substance, in Polish, keeping its order:

- open with the coupon's real result - 7c per sport and epoch group, "Suma kuponu",
  refunds at 0 u.;
- the legs removed by reads (7i) on their own line, never added to 7c;
- every `MISMATCH`, identity finding and `results on KUPON_<d>: FAILED` /
  `RENDER_FAILED` line as a defect;
- the refit recommendation with its evidence.

Check any number you can check locally before repeating it. Do not re-summarise
it into a different table and do not add a stake.

## 4 - decisions stay with the operator

A refit, an install or any constant change is the operator's call: present the
settler's recommendation and wait for his go. Never refit or install from this
command, never mid-day or into a built day. The next morning step,
`refresh_line_evidence.py --before <D>`, belongs to the day's run (`/sofa-day`), not here.
