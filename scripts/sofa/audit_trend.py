"""AUDIT - the questions one settled day cannot answer, asked of every day so far.

A single day's settlement invites a single day's conclusion. On 2026-09-25 the
five legs MAX_OVERROUND kept off the PDF all won, and loosening the limit would
have turned the day from -0.1% into +6.4%; over 22-25.09 the same margin band
returned -12.8% (n=50) against -4.6% (n=78) below it. The day said "loosen",
the days said "keep". Likewise a market that lost on the day is a suspicion
until it has lost on several.

So this module answers two questions across ALL settled days up to the report's
date, and changes nothing:

  * margin bands - the confidence legs grouped by their ladder's margin, which
    is the measurement MAX_OVERROUND (and the coupon's 15% since 10-05) rests on. The
    constant's own comment asked to be re-measured once more days settled;
    this is that measurement, repeated every morning.
  * classes - printed singles by sport x market x direction, per day, with the
    classes that lost (or won) on EVERY day they appeared named as such.

Neither is a gate. The 22,680-setting gate sweep of 2026-09-2x measured that a
dial tuned on a handful of days loses out of sample (-7.35% nested against
-2.95% for production); a class listed here is a thing to watch, and becomes
a gate only after a separate, out-of-sample measurement.

Pure: reads run artifacts and settled rows, writes nothing.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.confidence import (
    COUPON_PROFILE,
    MAX_OVERROUND,
    coupon_artifact,
    printed_singles,
)
from bet.sofa.settle import line_value

# The band edges: the coupon's limit until 10-04 and its limit since 10-05.
COUPON_MAX_OVERROUND = COUPON_PROFILE.max_overround
MARGIN_BANDS: tuple[tuple[str, float, float], ...] = (
    (f"<= {MAX_OVERROUND:.1%}", -1.0, MAX_OVERROUND),
    (f"{MAX_OVERROUND:.1%} - {COUPON_MAX_OVERROUND:.0%}", MAX_OVERROUND,
     COUPON_MAX_OVERROUND),
    (f"> {COUPON_MAX_OVERROUND:.0%}", COUPON_MAX_OVERROUND, 10.0),
)
NO_MARGIN = "bez marży (drabina jednostronna)"

# A class is named in the report only past this much evidence. Below it every
# class "lost on every day" by the arithmetic of small numbers.
MIN_CLASS_BETS = 20
MIN_CLASS_DAYS = 3

Key = tuple[int, str, str, float, str]


def leg_key(leg: dict[str, Any]) -> Key:
    return (int(leg["sofascore_event_id"]), leg["market"], leg.get("subject") or "",
            line_value(leg), leg["direction"])


@dataclass
class Tally:
    bets: int = 0
    won: int = 0
    units: float = 0.0

    def add(self, won: bool, odds: float) -> None:
        self.bets += 1
        self.won += int(won)
        self.units += (odds - 1.0) if won else -1.0

    @property
    def roi(self) -> float | None:
        return self.units / self.bets if self.bets else None


@dataclass
class Trend:
    days: list[str] = field(default_factory=list)
    # profile -> band -> day -> tally
    margin: dict[str, dict[str, dict[str, Tally]]] = field(default_factory=dict)
    # profile -> (sport, market, direction) -> day -> tally
    classes: dict[str, dict[tuple[str, str, str], dict[str, Tally]]] = field(
        default_factory=dict
    )


def margin_band(overround: float | None) -> str:
    if overround is None:
        return NO_MARGIN
    for label, lo, hi in MARGIN_BANDS:
        if lo < overround <= hi:
            return label
    return MARGIN_BANDS[-1][0]


def _grade(leg: dict[str, Any], by_key: dict[Key, dict[str, Any]]) -> bool | None:
    """True/False for a decided leg, None for unsettled or PUSH."""
    row = by_key.get(leg_key(leg))
    if row is None or row["outcome"] not in ("WIN", "LOSS"):
        return None
    return bool(row["outcome"] == "WIN")


def build_trend(
    runs_dir: Path,
    up_to: str,
    load_settled: Callable[[str], Iterable[dict[str, Any]]],
) -> Trend:
    """Every day in `runs_dir` up to and including `up_to` that has settled rows."""
    trend = Trend()
    day_dirs = sorted(
        p for p in runs_dir.iterdir()
        if p.is_dir() and len(p.name) == 10 and p.name <= up_to
    ) if runs_dir.exists() else []
    for day_dir in day_dirs:
        day = day_dir.name
        by_key = {leg_key(r): r for r in load_settled(day)}
        if not by_key:
            continue
        path = coupon_artifact(day_dir)
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if "singles" not in doc:
            continue
        bands = trend.margin.setdefault("standard", {})
        for leg in doc.get("legs") or []:
            won = _grade(leg, by_key)
            if won is None:
                continue
            band = margin_band(leg.get("overround"))
            bands.setdefault(band, {}).setdefault(day, Tally()).add(
                won, leg["offered_odds"])
        classes = trend.classes.setdefault("standard", {})
        for leg in printed_singles(doc):
            won = _grade(leg, by_key)
            if won is None:
                continue
            cls = (leg.get("sport") or "?", leg["market"], leg["direction"])
            classes.setdefault(cls, {}).setdefault(day, Tally()).add(
                won, leg["offered_odds"])
        trend.days.append(day)
    return trend


def _total(per_day: dict[str, Tally]) -> Tally:
    out = Tally()
    for t in per_day.values():
        out.bets += t.bets
        out.won += t.won
        out.units += t.units
    return out


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100.0 * x:+.1f}%"


def consistent_sign(per_day: dict[str, Tally]) -> str | None:
    """'ujemne' / 'dodatnie' when every day with a bet had that sign, else None."""
    if len(per_day) < MIN_CLASS_DAYS or _total(per_day).bets < MIN_CLASS_BETS:
        return None
    if all(t.units < 0 for t in per_day.values()):
        return "ujemne"
    if all(t.units > 0 for t in per_day.values()):
        return "dodatnie"
    return None


def render(trend: Trend, heading: str) -> list[str]:
    lines = [heading, ""]
    if not trend.days:
        return lines + ["Brak rozliczonych dni z artefaktem CONFIDENCE.", ""]
    lines += [
        f"Dni: {', '.join(trend.days)}. Ta sekcja **niczego nie zmienia** - "
        "mierzy, na czym stoją progi, na wszystkich dniach naraz, bo jeden "
        "dzień podpowiada wniosek, którego kilka dni nie potwierdza. "
        "Przegląd 22 680 ustawień bramek zmierzył, że pokrętło nastrojone na "
        "kilku dniach traci poza próbką; nic stąd nie jest bramką bez osobnego "
        "pomiaru.",
        "",
        "### Marża drabiny - na czym stoi MAX_OVERROUND",
        "",
        f"Wszystkie nogi listy pewnościowej, po marży. Kupon drukuje pojedyncze "
        f"do {COUPON_MAX_OVERROUND:.0%} (do 10-04: {MAX_OVERROUND:.1%}). Jeśli "
        "pasmo powyżej progu wychodzi gorzej niż pod nim na kolejnych dniach, "
        "próg jest na miejscu - nawet w dniu, w którym akurat by pomogło.",
        "",
    ]
    for profile, bands in trend.margin.items():
        lines += [f"**{profile}**", "",
                  "| marża | nóg | weszło | wynik | ROI | dzień po dniu |",
                  "|---|---|---|---|---|---|"]
        order = [b[0] for b in MARGIN_BANDS] + [NO_MARGIN]
        for band in order:
            per_day = bands.get(band)
            if not per_day:
                continue
            t = _total(per_day)
            daily = " ".join(
                f"{d[5:]}: {x.bets}/{_pct(x.roi)}" for d, x in sorted(per_day.items()))
            lines.append(
                f"| {band} | {t.bets} | {t.won} | {t.units:+.2f} j. | "
                f"{_pct(t.roi)} | {daily} |")
        lines.append("")
    lines += [
        "### Klasy rynku - pojedyncze z PDF po sport x rynek x kierunek",
        "",
        f"Wymienione są tylko klasy z co najmniej {MIN_CLASS_BETS} rozliczonymi "
        f"pozycjami na co najmniej {MIN_CLASS_DAYS} dniach, które miały ten sam "
        "znak wyniku **każdego** dnia. To lista do obserwacji, nie do wycięcia.",
        "",
    ]
    for profile, classes in trend.classes.items():
        named = []
        for cls, per_day in classes.items():
            sign = consistent_sign(per_day)
            if sign:
                named.append((sign, cls, per_day))
        lines.append(f"**{profile}**")
        lines.append("")
        if not named:
            lines += ["Żadna klasa nie spełnia progu dowodu.", ""]
            continue
        lines += ["| znak | sport | rynek | kierunek | pozycji | weszło | wynik | "
                  "ROI | dzień po dniu |",
                  "|---|---|---|---|---|---|---|---|---|"]
        named.sort(key=lambda x: _total(x[2]).units)
        for sign, (sport, market, direction), per_day in named:
            t = _total(per_day)
            daily = " ".join(
                f"{d[5:]}: {x.bets}/{_pct(x.roi)}" for d, x in sorted(per_day.items()))
            lines.append(
                f"| {sign} każdego dnia | {sport} | {market} | {direction} | "
                f"{t.bets} | {t.won} | {t.units:+.2f} j. | {_pct(t.roi)} | "
                f"{daily} |")
        lines.append("")
    return lines
