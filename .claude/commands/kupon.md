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
  to 23:59Z (01:59 local in summer, 00:59 in winter), and the script moves a window that has already
  ended to the next local day (`22-2` crosses midnight; `24` is midnight). No
  `runs/sofa/<date>/11_coupon.json` -> say "brak kuponu dnia - najpierw
  /sofa-day" and stop.

## Run

First `.venv/bin/python scripts/sofa/ensure_bridge.py` (build_slip.py asks Sofascore for
h2h / lineups and writes dossiers and `family_record.json` - not read-only) and
`mkdir -p runs/sofa/<date>/slips`. Then the skill's loop, with `--start-from <HH:MM>
--start-to <HH:MM> --target <X> [--slips N] --any-family --builders --max-legs 10
--read-set-dir runs/sofa/<date>/read_set_slip --md-out runs/sofa/<date>/slips/<HHMM>.md`
(`<HHMM>` = now, local, each round - always, so a staked slip can be traced)
(operator 2026-10-26: every market in one pass, families on the plus not
preferred; the day's Bet Builders as an option of their match, priced as the
product of their legs - the table says Superbet prices a builder lower), the
analysts' reports at `runs/sofa/<date>/<date>_analiza_<sport>_kupon_<hhmm>_<round>.md`
(`<hhmm>` = the request's local time, fixed for all its rounds) and `merge_reads.py --slip --author analyst ...
--read-set <file>` - every step as the skill states it. Narrate a line per
step.

- The window starts less than 30 min from now: warn in the answer's second
  line (legs that start while the analysts read drop out) and go on. A leg
  marked ⚠ starts within 45 min (a read round takes 20-30 min): name it.
- The operator sends their own Bet Builder (screenshot) instead of hours: the
  skill's `--check` mode (one `--check` per leg in Superbet's words,
  `--screen-odds` from the screen, `--no-refresh-record`) and its `--check`
  relay, never confidences multiplied by hand.
- No slip at all: relay the script's first line (with the reachable price) and
  offer a lower target or a wider window - never fill with legs outside the
  window.

## Answer (Polish)

Exactly the skill's **Relay**: line 1 the script's first line - how many slips
stand on families on the plus ("say no first", `--any-family` too) - then the
tables with every column read (measured chance vs 1/kurs, "pewność < 1/kurs",
family hit vs price with n, zestawienie, ⚠, the header's chance vs 1/price and
"zwrot wg naszych liczb", a builder's "<product> iloczyn" with "Superbet
płacił 0,85-0,99 iloczynu (28.10)"), the reads, what fell out and what
replaced it, unread legs named as unread, the `--md-out` path. Carry the
skill's measured facts where a leg's family is among them (goal UNDER families
below price 10-14..10-27, e.g. `goals_total` UNDER -4.6 pp on 1,765 legs) - as
measurements with days and N, never as a result argument. No slip price, no
stake, no "na minusie" labels.
