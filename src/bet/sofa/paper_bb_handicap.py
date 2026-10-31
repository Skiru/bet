"""A pre-registered forward PAPER test: basketball point handicap, Superbet's
price against bet365's opening price (operator's go 2026-10-31).

Nothing here stakes, places or prints: the test's files live in
`runs/sofa/paper/bb_handicap/` and no stage that builds the coupon reads
them. bet365's price is read only here, never by SAMPLES / SHEET /
CONFIDENCE (`bet.sofa.market_lines` keeps it out of the model on purpose).

The rule is frozen exactly as the backtest of 2026-10-31 defined its
basketball handicap t=0 cell (scratchpad `secondprice2/rows.py`
`sport_rows` + `run.py` `fire`):

- Superbet's price: SHADOW_SETTLE's graded row of the line (family
  `handicap`, period 0, side T1 / T2, outcome WIN / LOSS) - the price of the
  last SHADOW snapshot before the start (`shadow.latest_pre_kickoff`).
  `line` is team1's handicap on both sides.
- bet365: Sofascore `/event/{id}/odds/1/all` (provider 1 = bet365),
  markets with `isLive` dropped; the one market
  named "Point spread" (no choiceGroup) with two choices. Its first choice
  is the home side, "(+16.0) Name": the line matches when that number equals
  the Superbet line on Sofascore's home side (team1's line when home is
  team1, else its negation). The choice of the Superbet side (home side ->
  0, away -> 1).
- Fair p: the OPENING price (`initialFractionalValue`) of both choices,
  fractional + 1, overround 1.00..1.25, margin removed by the power method
  (p_i = (1/o_i)^k, k in [1, 8] by 60 bisections so that the sum is 1).
- Selected when Superbet odds x fair p > 1 + T (T = 0).
- Graded by SHADOW_SETTLE's own outcome of that row. A unit stake: WIN =
  odds - 1, LOSS = -1; after Polish tax WIN = odds x 0.88 - 1.

Which bet365 payload (the one thing forward and backtest differ in):

- backtest days (before PRESTART_FROM): the payload asked AFTER the game, as
  the backtest did - its "Point spread" line is the one bet365 showed after
  the match, a look-ahead (`b365_source` "post_match_lookahead");
- from PRESTART_FROM: only the newest capture taken BEFORE the start (the
  earlier of Superbet's kickoff and Sofascore's start) by the capture loop
  (`scripts/sofa/paper_bb_handicap.py --capture --loop`), so the line and
  its opening price are what was visible before tip-off (`b365_source`
  "prestart"). A game with no such capture is excluded and counted
  (`no_b365_prestart`, "brak bet365 przed startem"); nothing is asked after
  the game for it.

The test is judged at TARGET_N graded selections of the forward window only
(days from START_DATE); the backtest days are a separate section, never
pooled with it.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from fractions import Fraction
from typing import Any

RULE_ID = "PAPER-BB-HANDICAP-B365-OPEN-T0"
FROZEN_AT = "2026-10-31"
T = 0.0
TARGET_N = 300
# The forward window. The operator's spec said 2026-10-31; the test registry
# (scripts/sofa/check_test_registry.py) refuses a window that starts on its
# registration day - part of 10-31's games had been played when the rule was
# frozen - so the forward window starts the day after.
START_DATE = "2026-11-01"
# From this day the payload is the pre-start capture (10-31: a dress
# rehearsal of the capture, in the backtest section's registration_day).
PRESTART_FROM = "2026-10-31"
CAPTURE_HORIZON_H = 3
CAPTURE_EVERY_MIN = 15
# A capture keeps only these markets (the rule reads "Point spread").
CAPTURE_MARKETS = ("Point spread", "Full time", "Game total")
B365_POST_MATCH = "post_match_lookahead"
B365_PRESTART = "prestart"
TAX = 0.88
FAMILY = "handicap"
PERIOD = 0
B365_MARKET = "Point spread"
OVERROUND_MIN = 1.0
OVERROUND_MAX = 1.25
POWER_LO = 1.0
POWER_HI = 8.0
POWER_ITER = 60
BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 7
# The backtest's windows (days are sport day windows, sport_identity.day_window).
BACKTEST_WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("dev", "2026-10-13", "2026-10-26"),
    ("holdout_posthoc", "2026-10-27", "2026-10-30"),
    ("registration_day", "2026-10-31", "2026-10-31"),
)

_HOME_LINE = re.compile(r"\(([-+]?\d+(?:\.\d+)?)\)")


# --- prices ------------------------------------------------------------------


def frac_to_decimal(raw: object) -> float | None:
    """Sofascore's fractional value ("5/6") as a decimal price; None when
    it is not a fraction."""
    try:
        return float(Fraction(str(raw))) + 1.0 if raw is not None else None
    except (ValueError, ZeroDivisionError):
        return None


def power_fair(prices: Sequence[float]) -> list[float]:
    """Margin removed by the power method: (1/o_i)^k summing to 1."""
    lo, hi = POWER_LO, POWER_HI
    for _ in range(POWER_ITER):
        k = (lo + hi) / 2
        if sum((1 / p) ** k for p in prices) > 1:
            lo = k
        else:
            hi = k
    return [(1 / p) ** k for p in prices]


def fair_open(choices: Sequence[Mapping[str, Any]], i: int) -> float | None:
    """Choice i's fair p from the opening prices; None when a price is
    missing or the overround is outside 1.00..1.25."""
    prices = [frac_to_decimal(c.get("initialFractionalValue")) for c in choices]
    clean = [p for p in prices if p is not None and p > 1]
    if len(clean) != len(prices):
        return None
    if not OVERROUND_MIN <= sum(1 / p for p in clean) <= OVERROUND_MAX:
        return None
    return power_fair(clean)[i]


# --- bet365's spread ---------------------------------------------------------


def b365_markets(payload: object) -> dict[tuple[str, Any], list[dict[str, Any]]] | None:
    """{(marketName, choiceGroup): choices} of the pre-match markets; None
    when the payload holds no market."""
    if not isinstance(payload, Mapping) or not payload.get("markets"):
        return None
    out: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for m in payload["markets"]:
        if m.get("isLive"):
            continue
        out[(m["marketName"], m.get("choiceGroup"))] = list(m["choices"])
    return out


def spread_home_line(choices: Sequence[Mapping[str, Any]]) -> float | None:
    """The home side's handicap from "(+16.0) Name"."""
    if len(choices) != 2:
        return None
    m = _HOME_LINE.match(str(choices[0].get("name", "")))
    return float(m.group(1)) if m else None


def match_spread(
    markets: Mapping[tuple[str, Any], Sequence[Mapping[str, Any]]],
    t1_line: float,
    side: str,
    home_is_team1: bool,
) -> dict[str, Any] | None:
    """bet365's spread choice for Superbet's (team1 line, side), or None when
    bet365's line is another one."""
    choices = markets.get((B365_MARKET, None))
    if not choices or len(choices) != 2:
        return None
    home_line = t1_line if home_is_team1 else -t1_line
    b365_line = spread_home_line(choices)
    if b365_line is None or abs(b365_line - home_line) > 1e-9:
        return None
    i = 0 if (side == "T1") == home_is_team1 else 1
    return {
        "b365_home_line": b365_line,
        "b365_choice": str(choices[i].get("name")),
        "b365_open": [str(c.get("initialFractionalValue")) for c in choices],
        "p_open": fair_open(choices, i),
    }


# --- pre-start captures --------------------------------------------------------


def uses_prestart(day: str) -> bool:
    return day >= PRESTART_FROM


def trim_payload(payload: object) -> Any:
    """A capture's payload: only CAPTURE_MARKETS kept, each market whole."""
    if not isinstance(payload, Mapping):
        return payload
    markets = [
        m
        for m in payload.get("markets") or []
        if m.get("marketName") in CAPTURE_MARKETS
    ]
    return {"markets": markets}


def _at(raw: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def prestart_payload(
    captures: Iterable[Mapping[str, Any]], clock_utc: str
) -> Mapping[str, Any] | None:
    """The newest capture fetched strictly before `clock_utc`, or None: a
    capture taken at or after the start is never read."""
    clock = _at(clock_utc) if clock_utc else None
    if clock is None:
        return None
    best: tuple[datetime, Mapping[str, Any]] | None = None
    for c in captures:
        at = _at(c.get("fetched_at_utc"))
        if at is not None and at < clock and (best is None or at > best[0]):
            best = (at, c)
    return None if best is None else best[1]


def start_clock(record: Mapping[str, Any]) -> str:
    """The earlier of Superbet's kickoff and Sofascore's start (ISO); "" when
    neither is known."""
    best: tuple[datetime, str] | None = None
    for raw in (record.get("kickoff_utc"), record.get("sofascore_start_utc")):
        at = _at(raw) if raw else None
        if at is not None and (best is None or at < best[0]):
            best = (at, str(raw))
    return "" if best is None else best[1]


# --- the rule ----------------------------------------------------------------


def fires(odds: float, p_open: float | None, t: float = T) -> bool:
    return p_open is not None and odds * p_open > 1 + t


def units(outcome: str | None, odds: float, taxed: bool) -> float | None:
    if outcome == "WIN":
        return odds * (TAX if taxed else 1.0) - 1.0
    if outcome == "LOSS":
        return -1.0
    return None


def handicap_rows(record: Mapping[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """(index, row) of the record's graded full-game handicap rows the
    backtest read: outcome WIN / LOSS, side T1 / T2, a line."""
    out: list[tuple[int, dict[str, Any]]] = []
    for i, g in enumerate(record.get("graded") or []):
        if g.get("outcome") not in ("WIN", "LOSS"):
            continue
        if (g.get("family"), g.get("period", g.get("map_nr"))) != (FAMILY, PERIOD):
            continue
        if g.get("side") not in ("T1", "T2") or g.get("line") is None:
            continue
        out.append((i, dict(g)))
    return out


def evaluate_event(
    record: Mapping[str, Any], payload: object, source_date: str, file_index: int
) -> tuple[str, list[dict[str, Any]]]:
    """(status, candidates) of one SETTLED SHADOW record against bet365.

    A candidate is every Superbet handicap row bet365's spread matches,
    `selected` when the rule fires; graded from the record's own outcome."""
    markets = b365_markets(payload)
    if markets is None:
        return "NO_B365_ODDS", []
    h1 = record.get("home_is_team1")
    if h1 is None:
        return "ORIENTATION_UNKNOWN", []
    out: list[dict[str, Any]] = []
    for gi, g in handicap_rows(record):
        t1_line = float(g["line"])
        hit = match_spread(markets, t1_line, str(g["side"]), bool(h1))
        if hit is None:
            continue
        odds = float(g["odds"])
        p = hit["p_open"]
        selected = fires(odds, p)
        outcome = str(g["outcome"])
        team = record.get("team1") if g["side"] == "T1" else record.get("team2")
        out.append(
            {
                "sofascore_event_id": int(record["sofascore_event_id"]),
                "superbet_event_id": str(g.get("superbet_event_id") or ""),
                "source_date": source_date,
                "order": [source_date, file_index, gi],
                "match": record.get("match_name"),
                "tournament": record.get("tournament"),
                "kickoff_utc": record.get("kickoff_utc"),
                "side": g["side"],
                "team": team,
                "t1_line": t1_line,
                "side_line": t1_line if g["side"] == "T1" else -t1_line,
                "odds": odds,
                "superbet_fetched_at_utc": g.get("fetched_at_utc"),
                "minutes_before_kickoff": g.get("minutes_before_kickoff"),
                **hit,
                "edge": None if p is None else odds * p - 1.0,
                "selected": selected,
                "outcome": outcome,
                "units": units(outcome, odds, False) if selected else None,
                "units_after_tax": units(outcome, odds, True) if selected else None,
            }
        )
    return (
        "SELECTED"
        if any(c["selected"] for c in out)
        else "NOT_SELECTED"
        if out
        else "NO_LINE_MATCH"
    ), out


# --- the ledger --------------------------------------------------------------


def _quantiles(values: list[float]) -> list[float]:
    values.sort()
    b = len(values)
    return [values[int(0.025 * b)], values[int(0.975 * b)]]


def summarize(
    selections: Iterable[Mapping[str, Any]],
    b: int = BOOTSTRAP_B,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """n, won, units and ROI pre-tax and after tax (x0.88), each with a 95%
    match-bootstrap interval (events resampled whole, as the backtest)."""
    graded = [s for s in selections if s.get("outcome") in ("WIN", "LOSS")]
    n = len(graded)
    if not n:
        return {"n": 0, "events": 0}
    by_event: dict[int, list[Mapping[str, Any]]] = {}
    for s in graded:
        by_event.setdefault(int(s["sofascore_event_id"]), []).append(s)
    events = list(by_event)
    rnd = random.Random(seed)
    boot: list[float] = []
    boot_tax: list[float] = []
    for _ in range(b):
        tot = tot_tax = 0.0
        k = 0
        for e in rnd.choices(events, k=len(events)):
            for s in by_event[e]:
                tot += units(s["outcome"], float(s["odds"]), False) or 0.0
                tot_tax += units(s["outcome"], float(s["odds"]), True) or 0.0
                k += 1
        boot.append(tot / k)
        boot_tax.append(tot_tax / k)
    u = sum(units(s["outcome"], float(s["odds"]), False) or 0.0 for s in graded)
    ut = sum(units(s["outcome"], float(s["odds"]), True) or 0.0 for s in graded)
    won = sum(s["outcome"] == "WIN" for s in graded)
    return {
        "n": n,
        "events": len(events),
        "won": won,
        "hit_rate": won / n,
        "mean_implied": sum(1 / float(s["odds"]) for s in graded) / n,
        "mean_fair_p": sum(float(s["p_open"]) for s in graded) / n,
        "units": u,
        "roi": u / n,
        "roi_ci95": _quantiles(boot),
        "units_after_tax": ut,
        "roi_after_tax": ut / n,
        "roi_after_tax_ci95": _quantiles(boot_tax),
        "bootstrap": {"b": b, "seed": seed, "unit": "sofascore event"},
    }


def section_of(day: str) -> str:
    return "forward" if day >= START_DATE else "backtest"


def window_of(day: str) -> str | None:
    for name, lo, hi in BACKTEST_WINDOWS:
        if lo <= day <= hi:
            return name
    return None


def build_ledger(days: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The ledger from every day file, forward and backtest apart (never
    pooled). A selection (event, line, side) is counted once, on its first
    day."""
    seen: set[tuple[int, float, str]] = set()
    picked: dict[str, list[dict[str, Any]]] = {}
    pending = {"forward": 0, "backtest": 0}
    no_prestart = {"forward": 0, "backtest": 0}
    dropped_duplicates = 0
    day_rows: dict[str, list[dict[str, Any]]] = {"forward": [], "backtest": []}
    for doc in sorted(days, key=lambda d: str(d["date"])):
        day = str(doc["date"])
        sec = section_of(day)
        sel = [c for c in doc.get("candidates") or [] if c.get("selected")]
        kept = []
        for s in sorted(sel, key=lambda c: tuple(c["order"])):
            key = (int(s["sofascore_event_id"]), float(s["t1_line"]), str(s["side"]))
            if key in seen:
                dropped_duplicates += 1
                continue
            seen.add(key)
            kept.append(s)
        group = sec if sec == "forward" else (window_of(day) or "other")
        picked.setdefault(group, []).extend(kept)
        pending[sec] += len(doc.get("pending") or [])
        no_pre = int((doc.get("counts") or {}).get("no_b365_prestart", 0))
        no_prestart[sec] += no_pre
        day_rows[sec].append(
            {
                "date": day,
                "status": doc.get("status"),
                "selections": len(kept),
                "won": sum(s["outcome"] == "WIN" for s in kept),
                "pending_events": len(doc.get("pending") or []),
                "fetch_gaps": len(doc.get("fetch_gaps") or []),
                "no_b365_prestart": no_pre,
                "b365_source": B365_PRESTART if uses_prestart(day) else B365_POST_MATCH,
            }
        )
    fwd = summarize(picked.get("forward", []))
    return {
        "rule_id": RULE_ID,
        "frozen_at": FROZEN_AT,
        "t": T,
        "target_n": TARGET_N,
        "start_date": START_DATE,
        "tax": TAX,
        "forward": {
            "summary": fwd,
            "pending_events": pending["forward"],
            "no_b365_prestart": no_prestart["forward"],
            "b365_source": B365_PRESTART,
            "evaluable": fwd["n"] >= TARGET_N,
            "days": day_rows["forward"],
        },
        "backtest": {
            "note": (
                "days before the forward window; the 2026-10-31 rule was "
                "chosen on them (dev) and checked post hoc (holdout) - "
                "never pooled with forward; up to 2026-10-30 bet365 was read "
                "from a payload fetched after the game (the spread line as "
                "bet365 showed it after the match: a look-ahead, the numbers "
                "may be optimistic); 10-31 (registration_day) from pre-start "
                "captures"
            ),
            "windows": {
                name: summarize(picked.get(name, [])) for name, _, _ in BACKTEST_WINDOWS
            },
            "pending_events": pending["backtest"],
            "no_b365_prestart": no_prestart["backtest"],
            "days": day_rows["backtest"],
        },
        "duplicates_dropped": dropped_duplicates,
    }


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def report_pl(ledger: Mapping[str, Any]) -> str:
    """The forward summary in Polish."""
    fwd = ledger["forward"]
    s = fwd["summary"]
    lines = [
        f"Test papierowy {ledger['rule_id']} (zamrożony {ledger['frozen_at']}, "
        f"t = {ledger['t']}, okno od {ledger['start_date']})",
        "Koszykówka, handicap punktowy: kurs Superbetu x uczciwe p z kursu "
        "OTWARCIA bet365 (metoda potęgowa) > 1; bet365 z ostatniego zapisu PRZED "
        "startem. Bez stawek, nic nie trafia na kupon.",
    ]
    if not s.get("n"):
        lines.append(
            f"Okno do przodu: 0 rozliczonych typów; oczekujące mecze: "
            f"{fwd['pending_events']}; brak bet365 przed startem: "
            f"{fwd['no_b365_prestart']}."
        )
    else:
        lines += [
            f"Okno do przodu: n = {s['n']} (mecze {s['events']}), trafione {s['won']} "
            f"({s['hit_rate']:.3f}), średnie 1/kurs {s['mean_implied']:.3f}, "
            f"średnie p bet365 {s['mean_fair_p']:.3f}",
            f"  ROI przed podatkiem {_pct(s['roi'])} "
            f"[{_pct(s['roi_ci95'][0])}, {_pct(s['roi_ci95'][1])}], "
            f"jednostki {s['units']:+.2f}",
            f"  ROI po podatku (x0.88) {_pct(s['roi_after_tax'])} "
            f"[{_pct(s['roi_after_tax_ci95'][0])}, "
            f"{_pct(s['roi_after_tax_ci95'][1])}], "
            f"jednostki {s['units_after_tax']:+.2f}",
            f"  oczekujące mecze: {fwd['pending_events']}; brak bet365 przed "
            f"startem: {fwd['no_b365_prestart']} meczów (wyłączone)",
        ]
    lines.append(
        f"Postęp: {s.get('n', 0)} / {ledger['target_n']}. "
        f"Ocena dopiero przy n >= {ledger['target_n']}; "
        "do tego czasu to nie jest przewaga."
    )
    if s.get("n", 0) >= ledger["target_n"]:
        ok = s["roi_after_tax_ci95"][0] > 0
        lines.append(
            "Kryterium (dolna granica 95% CI ROI po podatku > 0): "
            + (
                "SPEŁNIONE - decyzja operatora."
                if ok
                else "NIESPEŁNIONE - reguła odpada."
            )
        )
    lines.append(
        "Backtest (osobno, nigdy nie sumowany z oknem do przodu; do 10-30 linia "
        "bet365 odczytana po meczu - zajrzenie w przyszłość, liczby mogą być "
        "zawyżone):"
    )
    for name, w in ledger["backtest"]["windows"].items():
        if w.get("n"):
            lines.append(
                f"  {name}: n = {w['n']}, ROI {_pct(w['roi'])}, po podatku "
                f"{_pct(w['roi_after_tax'])}"
            )
    return "\n".join(lines)
