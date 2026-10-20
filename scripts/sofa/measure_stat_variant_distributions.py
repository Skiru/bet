#!/usr/bin/env python3
# ruff: noqa: E501  - Superbet names and report keys read better unwrapped.
"""Read-only measurement: can a corner / card distribution market reach 0.70?

Evidence, not a price (a ``measure_*`` script): nothing here writes a config,
a curve, a run artifact or a database row. The question (night 2026-10-20/21,
class B of the unread Superbet football markets): Superbet posts, on the
counts SHEET already prices,

    "Nieparzysta/parzysta liczba rzutów rożnych"        nieparzysta / parzysta
    "1.połowa - nieparzysta/parzysta liczba rzutów rożnych"
    "Liczba rzutów rożnych - przedziały"                 <9 / 9-11 / 12+
    "1.połowa - przedział rzutów rożnych"                <5 / 5-6 / 7+
    "<team> - przedział rzutów rożnych"                  0-2 / 3-4 / 5-6 / 7+
    "Dokładna liczba kartek"                             0-3 / 4 / ... / 11 / 12+

Priced from SHEET's own predictive distribution of the count - the negative
binomial around the row's centre with the fitted dispersion
(bet.sofa.count_dispersion: var = mu + alpha mu^2; engine.nb_survival) - does
any selection ever reach the 0.70 confidence floor? A curve can only lower a
probability that never gets there, so a family whose p never reaches 0.70 can
never print and is declined by measurement.

Inputs, per day (runs/sofa/<d>/, read only): 02_fixtures.json (football,
competition), 05_sheet.json (the centre of corners_total, corners_1h_total,
corners_for, cards_points_total; the reconstruction is checked against the
rows' own p_central), 04_offer.json (the O/U rung an end band copies),
unmapped_prices/ (Superbet's band prices, the last active quote of the day)
and 07_settled.json (the count's actual value, for grading).

Two readings:
  history   every fixture with a centre: the largest p any parity side,
            interior band (a closed band not containing 0, the widths Superbet
            posts: 3 match, 2 half / team, 1 exact cards) or single exact
            value reaches;
  offered   every band Superbet quoted: its p, the kind (parity / interior /
            low end "<9" "0-2" "0-3" / high end "12+" "7+"), for an end band
            whether the O/U rung it equals (UNDER 8.5, OVER 11.5, ...) is on
            the same fixture's ladder and at what price, and - p >= 0.70 -
            the graded result.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_stat_variant_distributions.py \\
        --runs-dir runs/sofa --from 2026-10-14 --to 2026-10-20 \\
        [--history-from 2026-10-09] [--json-out f]

Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import unmapped_prices
from bet.sofa.count_dispersion import DispersionTable, load_table
from bet.sofa.engine import nb_survival
from bet.sofa.market_mapper import fold
from bet.sofa.superbet_names import side_of

FLOOR = 0.70
MIN_X = 0.90
KMAX = 80
MARKETS = ("corners_total", "corners_1h_total", "corners_for", "cards_points_total")
# the closed interior band width Superbet posts on each count
INTERIOR_WIDTH = {"corners_total": 3, "corners_1h_total": 2, "corners_for": 2,
                  "cards_points_total": 1}

_PARITY = re.compile(r"^(?P<half>1\.\s?polowa - )?nieparzysta/parzysta liczba rzutow roznych$")
_TOTAL_RANGE = re.compile(r"^liczba rzutow roznych - przedzialy$")
_HALF_RANGE = re.compile(r"^1\.\s?polowa - przedzial rzutow roznych$")
_TEAM_RANGE = re.compile(r"^(?P<team>.+?) - przedzial rzutow roznych$")
_EXACT_CARDS = re.compile(r"^dokladna liczba kartek$")

_BAND_LT = re.compile(r"^<(?P<n>\d+)$")
_BAND_PLUS = re.compile(r"^(?P<n>\d+)\+$")
_BAND_RANGE = re.compile(r"^(?P<a>\d+)-(?P<b>\d+)$")
_BAND_ONE = re.compile(r"^(?P<n>\d+)$")


@dataclass(frozen=True)
class Band:
    lo: int
    hi: int | None  # None: open above

    @property
    def kind(self) -> str:
        if self.lo == 0 and self.hi is not None:
            return "low_end"
        if self.hi is None:
            return "high_end"
        return "interior"

    def ou(self) -> tuple[float, str] | None:
        """The O/U rung this band equals (line, direction), ends only."""
        if self.kind == "low_end" and self.hi is not None:
            return self.hi + 0.5, "UNDER"
        if self.kind == "high_end":
            return self.lo - 0.5, "OVER"
        return None


def parse_band(selection: str) -> Band | None:
    s = selection.strip()
    m = _BAND_LT.match(s)
    if m:
        return Band(0, int(m.group("n")) - 1)
    m = _BAND_PLUS.match(s)
    if m:
        return Band(int(m.group("n")), None)
    m = _BAND_RANGE.match(s)
    if m:
        return Band(int(m.group("a")), int(m.group("b")))
    m = _BAND_ONE.match(s)
    if m:
        return Band(int(m.group("n")), int(m.group("n")))
    return None


def pmf(centre: float, variance: float, kmax: int = KMAX) -> list[float]:
    """P(X = k), k = 0..kmax, from SHEET's survival function."""
    surv = [nb_survival(centre, variance, k) for k in range(-1, kmax + 1)]
    return [max(0.0, surv[k] - surv[k + 1]) for k in range(kmax + 1)]


def band_p(dist: Sequence[float], band: Band) -> float:
    hi = len(dist) - 1 if band.hi is None else min(band.hi, len(dist) - 1)
    total = sum(dist[band.lo: hi + 1])
    if band.hi is None:
        total += max(0.0, 1.0 - sum(dist))
    return total


def parity_p(dist: Sequence[float]) -> tuple[float, float]:
    even = sum(p for k, p in enumerate(dist) if k % 2 == 0)
    odd = sum(p for k, p in enumerate(dist) if k % 2 == 1)
    return odd, even


def max_interior(dist: Sequence[float], width: int) -> float:
    return max(sum(dist[a: a + width]) for a in range(1, len(dist) - width))


@dataclass
class Centre:
    market: str
    subject: str
    centre: float
    variance: float
    competition_id: int | None
    recon_err: float = 0.0


@dataclass
class Day:
    fixtures: dict[int, Mapping[str, Any]]
    centres: dict[tuple[int, str, str], Centre]
    offer: dict[tuple[int, str, str, float], Mapping[str, Any]]
    actual: dict[tuple[int, str, str], float]
    bands: dict[tuple[int, str, str], float] = field(default_factory=dict)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_day(run: Path, table: DispersionTable) -> Day | None:
    fixtures_doc = _read(run / "02_fixtures.json")
    sheet = _read(run / "05_sheet.json")
    if not isinstance(fixtures_doc, list) or not isinstance(sheet, list):
        return None
    fixtures = {int(f["sofascore_event_id"]): f for f in fixtures_doc
                if f.get("sport") == "football"}
    centres: dict[tuple[int, str, str], Centre] = {}
    for r in sheet:
        eid = r.get("sofascore_event_id")
        if eid not in fixtures or r.get("market") not in MARKETS:
            continue
        if r.get("centre") is None:
            continue
        key = (int(eid), str(r["market"]), str(r.get("subject") or ""))
        c = centres.get(key)
        if c is None:
            disp = table.read("football", str(r["market"]),
                              fixtures[int(eid)].get("competition_id"))
            if disp is None:
                continue
            centre = float(r["centre"])
            c = Centre(str(r["market"]), key[2], centre, disp.variance(centre),
                       fixtures[int(eid)].get("competition_id"))
            centres[key] = c
        if r.get("p_central") is not None and r.get("line") is not None:
            s = nb_survival(c.centre, c.variance, math.floor(float(r["line"])))
            p = s if r.get("direction") == "OVER" else 1.0 - s
            c.recon_err = max(c.recon_err, abs(p - float(r["p_central"])))
    offer: dict[tuple[int, str, str, float], Mapping[str, Any]] = {}
    for entry in _read(run / "04_offer.json") or []:
        for rung in entry.get("rungs") or []:
            if rung.get("market") in MARKETS:
                offer[(int(entry["sofascore_event_id"]), str(rung["market"]),
                       str(rung.get("subject") or ""), float(rung["line"]))] = rung
    actual: dict[tuple[int, str, str], float] = {}
    for r in _read(run / "07_settled.json") or []:
        if r.get("market") in MARKETS and r.get("actual_value") is not None:
            actual[(int(r["sofascore_event_id"]), str(r["market"]),
                    str(r.get("subject") or ""))] = float(r["actual_value"])
    return Day(fixtures, centres, offer, actual)


def _family(folded: str) -> tuple[str, str, str | None] | None:
    """(family, market, team) of a band market name, or None."""
    m = _PARITY.match(folded)
    if m:
        half = bool(m.group("half"))
        return ("corners_1h_parity" if half else "corners_parity",
                "corners_1h_total" if half else "corners_total", None)
    if _TOTAL_RANGE.match(folded):
        return "corners_range", "corners_total", None
    if _HALF_RANGE.match(folded):
        return "corners_1h_range", "corners_1h_total", None
    if _EXACT_CARDS.match(folded):
        return "cards_exact", "cards_points_total", None
    m = _TEAM_RANGE.match(folded)
    if m and not folded.startswith(("1.", "2.")):
        return "corners_team_range", "corners_for", m.group("team").strip()
    return None


def offered_bands(run: Path) -> Iterator[tuple[int, str, str, str | None, str, float]]:
    """(event, family, market, team, selection, price): the day's last active
    quote of each band selection."""
    last: dict[tuple[int, str, str], tuple[str, float, str, str, str | None]] = {}
    for r in unmapped_prices.read(run):
        folded = fold(r.get("marketName"))
        fam = _family(folded)
        if fam is None or r.get("price") is None:
            continue
        if r.get("status", "active") != "active":
            continue
        key = (int(r["sofascore_event_id"]), folded, str(r.get("name") or ""))
        stamp = str(r.get("fetched_at_utc") or "")
        held = last.get(key)
        if held is None or stamp >= held[0]:
            last[key] = (stamp, float(r["price"]), fam[0], fam[1], fam[2])
    for (eid, _folded, selection), (_s, price, family, market, team) in last.items():
        yield eid, family, market, team, fold(selection), price


def _team_subject(day: Day, eid: int, team: str) -> str | None:
    subjects = [k[2] for k in day.centres if k[0] == eid and k[1] == "corners_for"]
    if len(subjects) != 2:
        return None
    i = side_of(team, (subjects[0], subjects[1]))
    return subjects[i] if i is not None else None


def _days(start: str, end: str) -> list[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def measure(runs: Path, start: str, end: str, history_from: str) -> dict[str, Any]:
    table = load_table()
    history: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    recon: list[float] = []
    offered: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(list))
    for d in _days(history_from, end):
        day = load_day(runs / d, table)
        if day is None:
            continue
        for c in day.centres.values():
            recon.append(c.recon_err)
            dist = pmf(c.centre, c.variance)
            odd, even = parity_p(dist)
            h = history[c.market]
            h["parity"].append(max(odd, even))
            h["interior"].append(max_interior(dist, INTERIOR_WIDTH[c.market]))
            h["single"].append(max(dist))
            h["centre"].append(c.centre)
        if d < start:
            continue
        for eid, family, market, team, selection, price in offered_bands(runs / d):
            subject = ""
            if team is not None:
                found = _team_subject(day, eid, team)
                if found is None:
                    offered[family]["no_centre"].append(1)
                    continue
                subject = found
            cell = day.centres.get((eid, market, subject))
            if cell is None:
                offered[family]["no_centre"].append(1)
                continue
            dist = pmf(cell.centre, cell.variance)
            actual = day.actual.get((eid, market, subject))
            if selection in ("nieparzysta", "parzysta"):
                odd, even = parity_p(dist)
                p = odd if selection == "nieparzysta" else even
                kind = "parity"
                won = (None if actual is None
                       else (int(actual) % 2 == (1 if selection == "nieparzysta" else 0)))
                copy = None
            else:
                band = parse_band(selection)
                if band is None:
                    offered[family]["unparsed"].append(selection)
                    continue
                p = band_p(dist, band)
                kind = band.kind
                won = (None if actual is None else
                       band.lo <= actual and (band.hi is None or actual <= band.hi))
                ou = band.ou()
                copy = None
                if ou is not None:
                    rung = day.offer.get((eid, market, subject, ou[0]))
                    side = None if rung is None else rung.get(
                        "over_odds" if ou[1] == "OVER" else "under_odds")
                    copy = {"ou_quoted": side is not None,
                            "ou_price": side, "band_price": price}
            offered[family]["rows"].append({
                "day": d, "event": eid, "selection": selection, "kind": kind,
                "p": round(p, 4), "price": price, "x": round(p * price, 4),
                "won": won, "copy": copy})
    return {"history": history, "recon": recon, "offered": offered}


def _q(values: Sequence[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))] if s else float("nan")


def report(res: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    recon = res["recon"]
    out["reconstruction"] = {"centres": len(recon), "max_abs_err": max(recon or [0.0]),
                             "share_le_0_001": (sum(e <= 1e-3 for e in recon)
                                                / len(recon) if recon else None)}
    hist: dict[str, Any] = {}
    for market, h in res["history"].items():
        hist[market] = {
            "fixtures": len(h["centre"]),
            "centre_min": round(min(h["centre"]), 3),
            "centre_median": round(_q(h["centre"], 0.5), 3),
            **{f"{kind}_max": round(max(h[kind]), 4) for kind in ("parity", "interior", "single")},
            **{f"{kind}_p99": round(_q(h[kind], 0.99), 4) for kind in ("parity", "interior", "single")},
            **{f"{kind}_ge_floor": sum(v >= FLOOR for v in h[kind])
               for kind in ("parity", "interior", "single")},
        }
    out["history"] = hist
    fams: dict[str, Any] = {}
    for family, f in res["offered"].items():
        rows = f.get("rows", [])
        by_kind: dict[str, Any] = {}
        for kind in ("parity", "interior", "low_end", "high_end"):
            ks = [r for r in rows if r["kind"] == kind]
            if not ks:
                continue
            hi = [r for r in ks if r["p"] >= FLOOR]
            printable = [r for r in hi if r["x"] >= MIN_X]
            graded = [r for r in hi if r["won"] is not None]
            entry: dict[str, Any] = {
                "selections": len(ks), "events": len({(r["day"], r["event"]) for r in ks}),
                "p_max": max(r["p"] for r in ks), "p_ge_floor": len(hi),
                "p_ge_floor_and_x_ge_0_90": len(printable),
                "graded_at_floor": len(graded),
                "realised_at_floor": (round(sum(bool(r["won"]) for r in graded) / len(graded), 4)
                                      if graded else None),
                "mean_p_at_floor": (round(sum(r["p"] for r in graded) / len(graded), 4)
                                    if graded else None),
            }
            copies = [r["copy"] for r in ks if r["copy"] is not None]
            if copies:
                quoted = [c for c in copies if c["ou_quoted"]]
                entry["ou_rung_quoted"] = len(quoted)
                entry["ou_rung_absent"] = len(copies) - len(quoted)
                entry["band_price_better"] = sum(c["band_price"] > c["ou_price"] for c in quoted)
                entry["band_price_equal"] = sum(c["band_price"] == c["ou_price"] for c in quoted)
                gains = sorted(c["band_price"] / c["ou_price"] - 1.0 for c in quoted)
                entry["band_vs_ou_price_median"] = round(_q(gains, 0.5), 4) if gains else None
                absent_hi = [r for r in ks if r["copy"] is not None and not r["copy"]["ou_quoted"]
                             and r["p"] >= FLOOR]
                entry["absent_p_ge_floor"] = len(absent_hi)
                entry["absent_p_ge_floor_and_x_ge_0_90"] = sum(r["x"] >= MIN_X for r in absent_hi)
            by_kind[kind] = entry
        fams[family] = {"no_centre": len(f.get("no_centre", [])),
                        "unparsed": sorted(set(f.get("unparsed", []))), "kinds": by_kind}
    out["offered"] = fams
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0] if __doc__ else None)
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--history-from", default=None,
                    help="first day of the history reading (default --from)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    try:
        res = measure(Path(args.runs_dir), args.start, args.end,
                      args.history_from or args.start)
        out = report(res)
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(out, indent=1, ensure_ascii=False, default=str)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
