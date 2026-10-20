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

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py --date <date> --target <X> \
    --start-from <HH:MM> --start-to <HH:MM> [--slips N] --allow-rest --reserve 1 \
    --read-set-dir runs/sofa/<date>/read_set_slip
```

then the skill's loop: one foreground analyst per `read_set_slip_<sport>.json`
(`sofa-analyst-football` / `sofa-analyst-tennis` / `sofa-analyst-sport` with the
sport named; report `runs/sofa/<date>/<date>_analiza_<sport>_kupon_<round>.md`),
`merge_reads.py --date <date> --report <each>`, re-run the same command, until
it prints "Każda noga kuponów ma KEEP analityka" - at most 3 rounds. Narrate a
line per step.

- The window starts less than 30 min from now: say so in the first line (legs
  that start while the analysts read drop out) and go on.
- No slip at all: relay the script's first line (with the reachable price) and
  offer a lower target or a wider window - never fill with legs outside the
  window.

## Answer (Polish)

First line: the script's "say no first" line. Then each slip's final table as
printed (Superbet's words, start in local time, price, 1/price, measured
chance, read verdict, "poza poparciem" where it says so), the slip's measured
chance, which legs fell out on which read and what replaced them, and any leg
still unread named as unread. No slip price (the price product line is a
target check), no stake, no "na minusie" labels; "kurs kuponu: sprawdź na
ekranie Superbetu". The family selection's advantage is not yet shown
(T-FAMILY-SELECTION).
