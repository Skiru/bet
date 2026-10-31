---
description: "A chat slip (AKO) from today's coupon for a kickoff window - every market, the exact knapsack of build_slip.py, every leg read by the analysts, a refused leg replaced by the next best and read too. The operator types only the hours."
argument-hint: "11-13 | 11:00-13:30 [~2] [x2] [3 nogi] [buildery]"
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
  default **2** (two legs of ~1.4; a target above what 2 legs of up to 2.00
  reach makes the script say so first and build the closest).
- **Slips**: `x2` / `2 kupony` -> `--slips 2`; default 1.
- **Legs**: default **2** (the script's default - least loss, operator
  2026-10-31: `docs/sofa/evidence/slip_flow_backtest_2026-10-31.md`). Only
  when the operator says `3 nogi` / `N nóg` -> `--max-legs N`; the answer then
  relays the script's line with the measured cost of each extra leg. Never
  raise it yourself to reach a target.
- **Builders**: off. Only `buildery` / `z builderami` -> `--builders`; the
  answer then relays the script's line "Bet Buildery zmierzone po podatku:
  −16,6% ... −45,8%".
- **Date**: the UTC date (`date -u +%F`) - a day's coupon holds kickoffs up
  to 23:59Z (01:59 local in summer, 00:59 in winter), and the script moves a window that has already
  ended to the next local day (`22-2` crosses midnight; `24` is midnight). No
  `runs/sofa/<date>/11_coupon.json` -> say "brak kuponu dnia - najpierw
  /sofa-day" and stop.

## Run

First `.venv/bin/python scripts/sofa/ensure_bridge.py` (build_slip.py asks Sofascore for
h2h / lineups and writes dossiers - not read-only) and
`mkdir -p runs/sofa/<date>/slips`. Then the skill's loop, with `--start-from <HH:MM>
--start-to <HH:MM> --target <X> [--slips N] [--max-legs N] [--builders]
--read-set-dir runs/sofa/<date>/read_set_slip --md-out runs/sofa/<date>/slips/<HHMM>.md`
(`<HHMM>` = now, local, each round - always, so a staked slip can be traced)
(every market in one pass, each leg on its own statistics and reads - the
families on the plus removed by the operator 2026-10-31; 2 legs and no
builders unless the operator asked, see Arguments), the
analysts' reports at `runs/sofa/<date>/<date>_analiza_<sport>_kupon_<hhmm>_<round>.md`
(`<hhmm>` = the request's local time, fixed for all its rounds) and `merge_reads.py --slip --author analyst ...
--read-set <file>` - every step as the skill states it. Narrate a line per
step.

- The window starts less than 30 min from now: warn in the answer's second
  line (legs that start while the analysts read drop out) and go on. A leg
  marked ⚠ starts within 45 min (a read round takes 20-30 min): name it.
- The operator sends their own Bet Builder (screenshot) instead of hours: the
  skill's `--check` mode (one `--check` per leg in Superbet's words,
  `--screen-odds` from the screen; read-only) and its `--check`
  relay, never confidences multiplied by hand.
- No slip at all: relay the script's first line (with the reachable price) and
  offer a lower target or a wider window - never fill with legs outside the
  window.
- Target out of reach of the leg limit ("Na ~X trzeba N nóg - każda kolejna
  noga to ok. −4% więcej; z 2 nogami najbliżej ~Y"): relay that line first,
  the closest slip as built (marked "Cel ~X NIE osiągnięty"), and offer a
  lower target or `N nogi` - never add a leg the operator did not ask for.

## Answer (Polish)

Exactly the skill's **Relay**: line 1 the script's first line - how many of
the requested slips the day gives ("say no first": "dzień cienki - masz N" /
"dziś żadnego" / "na ~X trzeba N nóg ...") - line 2 the script's money line
("Oczekiwany zwrot po podatku ≈ 0,88 × 0,96^n − 1 = −X% stawki (zmierzone:
...) - przewagi nad ceną nie ma (...)"; a slip with a builder: the builders' measured numbers and "kurs buildera
decyduje ekran Superbetu", singles and builder stated apart), then the tables with every column read ("kurs kuponu → teraz" - the fresh
Superbet price the script re-asked, "nie dopytano" said as "sprawdź kurs na
ekranie" -, measured chance vs 1/kurs, "pewność < 1/kurs", model, próbka,
liga, h2h, sędzia, marża, zestawienie, ⚠, the header's chance vs 1/price and
its money line, "wygrana zwraca mniej niż gotówka" on a single below 1,136,
with `--builders` a builder's "<product> iloczyn", the builders' measured
line and "Superbet płacił 0,85-0,99 iloczynu (28.10)"), the reads, what fell
out and what replaced it (also "bez próbki meczu" / "mikropróbka" /
"kurs urósł > 2%" from the Odrzucone line), unread legs named as unread, the
`--md-out` path, and - for a slip answered more than ~30 min before its
first start - "przed postawieniem puść /kupon jeszcze raz: kurs może urosnąć
później" (31.10: Bernau 1.52 → 1.65 in the last 26 min). The pool and the
evidence columns are a quality filter, never "an edge"
(`docs/sofa/evidence/kupon_od_nowa_2026-10-31.md`).
No slip price, no stake, no "na minusie" labels, never a return computed
from our confidence.
