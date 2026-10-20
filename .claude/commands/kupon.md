---
description: "A chat slip (AKO) from today's coupon for a kickoff window - every market, the exact knapsack of build_slip.py, every leg read by the analysts, a refused leg replaced by the next best and read too. The operator types only the hours."
argument-hint: "11-13 | 11:00-13:30 [~5] [x2]"
---

The operator wants a slip for the matches starting in a window of today. Run
the `bet-slip-audit` skill's **Building a slip to a target price** loop (load
the skill first; it owns the procedure and the rules) with these inputs.

Python: `PYTHONPATH=src:. .venv/bin/python`.

## Arguments: `$ARGUMENTS`

- **Window** (required): `H-H`, `H:MM-H:MM` or `H-H:MM`, local time
  (Europe/Warsaw) -> `--start-from HH:MM --start-to HH:MM` (`11-13` is
  `11:00`-`13:00`, the end exclusive; a bad hour exits 2 - ask again). Missing:
  ask for the hours, nothing else.
- **Target**: `~X`, `na X` or a bare decimal (e.g. `4`, `~5.5`) -> `--target X`;
  default **4**.
- **Slips**: `x2` / `2 kupony` -> `--slips 2`; default 1.
- **Date**: the UTC date (`date -u +%F`) - a day's coupon holds kickoffs up
  to 23:59Z (01:59 local), and the script moves a window that has already
  ended to the next local day (`22-2` crosses midnight; `24` is midnight). No
  `runs/sofa/<date>/11_coupon.json` -> say "brak kuponu dnia - najpierw
  /sofa-day" and stop.

## Run

The skill's loop, with `--start-from <HH:MM> --start-to <HH:MM> --target <X>
[--slips N] --allow-rest --read-set-dir runs/sofa/<date>/read_set_slip`, the
analysts' reports at `runs/sofa/<date>/<date>_analiza_<sport>_kupon_<hhmm>_<round>.md`
(`<hhmm>` = now, local) and `merge_reads.py --slip --author analyst ...
--read-set <file>` - every step as the skill states it. Narrate a line per
step.

- The window starts less than 30 min from now: warn in the answer's second
  line (legs that start while the analysts read drop out) and go on.
- No slip at all: relay the script's first line (with the reachable price) and
  offer a lower target or a wider window - never fill with legs outside the
  window.

## Answer (Polish)

Exactly the skill's **Relay**: line 1 the script's first line, then the
tables, the reads, what fell out and what replaced it, unread legs named as
unread. No slip price, no stake, no "na minusie" labels.
