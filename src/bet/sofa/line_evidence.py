"""Superbet line evidence: every key read through its own settled Superbet lines.

Operator, 2026-10-07 (epochs.LINE_EVIDENCE_FROM_UTC): sofa's job is to tell a
good 1.20 from a bad 1.20 by the statistics, for every sport alike, and no
market that could win is cut by name. The curves are fitted on the results
history (no price), but the coupon prints from the lines Superbet actually
posts, and those are a different population: basketball's handicap curve is
calibrated to 0.1 pp on its history holdout and overstates on the posted
lines - at p 0.70-0.80 they realised 0.81 below odds 1.30 and 0.62 at
1.60-2.20 (09-20..10-06). Before this module a key whose posted lines
overstated was refused whole (a sport key outside `admitted`,
`refused_markets`, the admitted_* lists, DERIVED_NOT_CALIBRATABLE). Now a
leg's confidence is the LOWEST of:

* the key's history curve at p (none for a derived joint, a hole, a market
  never fitted) - lowered by the key's OFFSET: realised minus confidence over
  its printable settled lines (confidence >= PRINTABLE_FROM), once they are
  MIN_OFFSET_ROWS lines of MIN_OFFSET_GAMES games; a key with fewer reads its
  SPORT's offset (every key's printable lines pooled, same minimum). Never
  above zero. (Until 2026-10-07 ~11:35Z an offset also needed its bootstrap
  below zero: out of sample - evidence fitted on the earlier days, legs
  printed on the later - that let tennis print 0.778 against 0.698 realised
  and basketball 0.748 against 0.647; the point offset with the sport
  fallback printed football 0.815 / 0.810, hockey 0.788 / 0.779, basketball
  0.755 / 0.694, tennis 0.738 / 0.661.)
* with no curve at p, the Wilson lower bound of the key's own settled lines
  in p's bucket (MIN_EVIDENCE_BUCKET lines) - else NO_LINE_EVIDENCE, never
  guessed;
* the PRICE-BAND CAP (operator's choice, 2026-10-07: "krzywa per pasmo
  kursu"): what lines of this key at this p realised in this band of
  Superbet's price - applied, as the offset is, only where it is measured
  below the confidence (the cell's Wilson UPPER bound under it), and then to
  the cell's realised rate. The cell is (key, p bucket, band); thin, the
  key's lines in the band from p's bucket up; thin, the sport's in the band
  (same two steps); thin too, the key's lines over EVERY band from p's
  bucket up, widened bucket by bucket downward (not below PRINTABLE_FROM)
  until MIN_CAP_CELL lines - no key may print above what its own Superbet
  lines showed at or under its p (verifier, 2026-10-07: hockey handicap
  printed 0.9448 at p 0.951 where no band had a cell; the key's lines at
  p >= 0.85 realised 35/51); none - no cap. The price
  only chooses the band and only ever lowers a confidence; inside a band the
  statistics still rank the legs. (A Wilson LOWER bound as the cap, tried
  first on 10-07, cut legs whose band realised above their curve - 63 lines
  at 0.81 read 0.69 - a cut on width, not on evidence.)

The file is config/sofa_superbet_line_evidence.json, written between days by
scripts/sofa/fit_line_evidence.py.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.config import config_path

EVIDENCE_FILE = "sofa_superbet_line_evidence.json"
DEFAULT_EVIDENCE = config_path(EVIDENCE_FILE)

# The same grid as the curves (fit_confidence.EDGES / sport_confidence.EDGES;
# a test holds the three equal).
EDGES = [0.0, 0.60, 0.70, 0.75, 0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 1.01]
# Superbet's price bands. Measured 2026-10-07 the curve's error turns at
# about 1.30 (hockey handicap) and 1.60 (basketball handicap, totals).
PRICE_BANDS: tuple[tuple[float, float], ...] = (
    (1.0, 1.30), (1.30, 1.60), (1.60, 2.20), (2.20, 1000.0))
# A cell of settled lines under this is not read. The Wilson lower bound is
# conservative at any n; this only keeps a handful of lines from standing for
# a market.
MIN_EVIDENCE_BUCKET = 50
# A price-band cap lowers a leg only where its cell's Wilson UPPER bound is
# under the confidence, so a small cell protects itself; it still needs this
# many lines (basketball handicap at 1.60-2.20 with p >= 0.925: 21 lines,
# realised 0.76, where the curve printed 0.934).
MIN_CAP_CELL = 20
# An offset is a measurement of a key's printable rows on Superbet's lines; one
# game's two lost lines have no spread for a bootstrap to see, and on the
# first fit (2026-10-07) such cells read "significant" offsets of -0.7.
# Below these the curve stands as fitted.
MIN_OFFSET_ROWS = 50
MIN_OFFSET_GAMES = 30
# The sport's pooled offset pools every key, so it is steadier at fewer games;
# CS2's 61 printable lines of 27 series read -0.204 [-0.323, -0.067] on
# 2026-10-07 and would have printed at the curve under the key minimum.
MIN_SPORT_OFFSET_GAMES = 20
# The rows the coupon could print (confidence.COUPON_PROFILE.floor).
PRINTABLE_FROM = 0.70
# v2 (epochs.LINE_EVIDENCE_V2_FROM_UTC). A bucket read with no curve needs this
# many GAMES (basketball: 2,956 lines were ~450 independent ones); a key
# holding more than CONCENTRATION_MAX of a sport's printable lines is left
# out of that sport's pooled offset (CS2 2026-10-07: 47 of 61 lines were one
# key).
MIN_EVIDENCE_GAMES = 15
CONCENTRATION_MAX = 0.5
BOOTSTRAP = 2000
NO_LINE_EVIDENCE = "NO_LINE_EVIDENCE"
SPORT_SCOPE = "*"  # the sport's lines of every key, in the `bands` section
UNFITTED_CONSTANTS = ("MIN_EVIDENCE_BUCKET", "MIN_CAP_CELL", "MIN_OFFSET_ROWS",
                      "MIN_OFFSET_GAMES", "MIN_SPORT_OFFSET_GAMES", "PRICE_BANDS",
                      "MIN_EVIDENCE_GAMES", "CONCENTRATION_MAX")


def bucket_of(p: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def bucket_label(b: int) -> str:
    return f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"


def band_label(odds: float) -> str:
    for lo, hi in PRICE_BANDS:
        if lo <= odds < hi:
            return f"{lo:.2f}-{hi:.2f}"
    lo, hi = PRICE_BANDS[-1]
    return f"{lo:.2f}-{hi:.2f}"


def wilson_lo(k: int, n: int, z: float = 1.959964) -> float:
    if n <= 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def wilson_hi(k: int, n: int, z: float = 1.959964) -> float:
    if n <= 0:
        return 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return min(1.0, c + m)


def evidence_key(key: str, klass: str | None = None) -> str:
    """A class leg (women's football, ...) keeps its own evidence."""
    return f"{klass}:{key}" if klass else key


@dataclass(frozen=True)
class Read:
    value: float
    source: str
    n: int
    offset: float = 0.0
    band_cap: float | None = None  # the cap that lowered the leg, if one did


@dataclass
class LineEvidence:
    doc: dict[str, Any] = field(default_factory=dict)
    v2: bool = False  # epochs.line_evidence_v2: the second rules (module doc)

    @staticmethod
    def load(path: Path | str = DEFAULT_EVIDENCE, v2: bool = False) -> LineEvidence:
        p = Path(path)
        if not p.exists():
            return LineEvidence({}, v2)
        return LineEvidence(json.loads(p.read_text(encoding="utf-8")), v2)

    @property
    def fitted(self) -> bool:
        return bool(self.doc.get("keys"))

    def _min(self) -> int:
        return int(self.doc.get("min_bucket", MIN_EVIDENCE_BUCKET))

    def _entry(self, sport: str, key: str) -> Mapping[str, Any]:
        return ((self.doc.get("keys") or {}).get(sport) or {}).get(key) or {}

    def _measured(self, pr: Mapping[str, Any], min_games: int | None = None
                  ) -> float | None:
        gap = pr.get("realised_minus_confidence")
        least = min_games if min_games is not None else int(
            self.doc.get("min_offset_games", MIN_OFFSET_GAMES))
        if not gap or int(pr.get("n") or 0) < int(
                self.doc.get("min_offset_rows", MIN_OFFSET_ROWS)) or int(
                pr.get("games") or 0) < least:
            return None
        return round(min(float(gap[0]), 0.0), 4)

    def offset(self, sport: str, key: str) -> float:
        """<= 0: the key's measured overstatement on its printable settled
        lines, else the sport's (all its keys pooled), else 0."""
        own = self._measured(self._entry(sport, key).get("printable") or {})
        if own is not None:
            return own
        pool = ((self.doc.get("sport_printable") or {}).get(sport)) or {}
        without = pool.get("without") or {}
        if self.v2 and without and without.get("key") != key:
            # v2: the pool minus the key that dominated it (fit() `without`);
            # unmeasurable without it -> the curve stands, offset 0.
            pool = without
        pooled = self._measured(
            pool, int(self.doc.get("min_sport_offset_games", MIN_SPORT_OFFSET_GAMES)))
        return pooled if pooled is not None else 0.0

    def bucket(self, sport: str, key: str, p: float) -> tuple[int, int] | None:
        b = (self._entry(sport, key).get("buckets") or {}).get(
            bucket_label(bucket_of(p)))
        if not b:
            return None
        return int(b["n"]), int(b["k"])

    def bucket_games(self, sport: str, key: str, p: float) -> int | None:
        """Games behind p's bucket of the key; None - an evidence file fitted
        before `games` was written (v2 then reads nothing from it)."""
        b = (self._entry(sport, key).get("buckets") or {}).get(
            bucket_label(bucket_of(p)))
        g = None if not b else b.get("games")
        return None if g is None else int(g)

    def band_cell(self, sport: str, key: str, p: float, odds: float | None
                  ) -> tuple[int, int, str] | None:
        """(n, k, cell) of the first cell with MIN_CAP_CELL lines:
        (key, p bucket, band), (key, band, p's bucket and up), the same two
        for the sport; None - no cell, no cap."""
        if odds is None:
            return None
        band = band_label(float(odds))
        b = bucket_of(p)
        scopes = ((self.doc.get("bands") or {}).get(sport) or {})
        least = int(self.doc.get("min_cap_cell", MIN_CAP_CELL))
        for scope in (key, SPORT_SCOPE):
            cells = (scopes.get(scope) or {}).get(band) or {}
            exact = cells.get(bucket_label(b))
            if exact and int(exact["n"]) >= least:
                return (int(exact["n"]), int(exact["k"]),
                        f"{scope}@{band}:{bucket_label(b)}")
            n = k = 0
            for label, cell in cells.items():
                if float(label.split("-")[0]) >= EDGES[b]:
                    n += int(cell["n"])
                    k += int(cell["k"])
            if n >= least:
                return n, k, f"{scope}@{band}:>={EDGES[b]:.3f}"
            if self.v2:
                floor_in = bucket_of(PRINTABLE_FROM)
                for lower in range(b - 1, floor_in - 1, -1):
                    n = k = 0
                    for label, cell in cells.items():
                        if float(label.split("-")[0]) >= EDGES[lower]:
                            n += int(cell["n"])
                            k += int(cell["k"])
                    if n >= least:
                        return n, k, f"{scope}@{band}:>={EDGES[lower]:.3f}"
        own = self._entry(sport, key).get("buckets") or {}
        floor_b = bucket_of(PRINTABLE_FROM)
        for lower in range(b, floor_b - 1, -1):
            n = k = 0
            for label, cell in own.items():
                if float(label.split("-")[0]) >= EDGES[lower]:
                    n += int(cell["n"])
                    k += int(cell["k"])
            if n >= least:
                return n, k, f"{key}@all:>={EDGES[lower]:.3f}"
        return None

    def band_cap(self, sport: str, key: str, p: float, odds: float | None,
                 value: float) -> tuple[float, str] | None:
        """(the cell's realised rate, cell) where the band's lines realised
        below `value` beyond their 95% interval; None - no such evidence."""
        cell = self.band_cell(sport, key, p, odds)
        if cell is None:
            return None
        n, k, label = cell
        if wilson_hi(k, n) >= value:
            return None
        return round(k / n, 4), label

    def read(self, sport: str, key: str, p: float,
             base: tuple[float, str, int] | None,
             odds: float | None = None) -> Read | None:
        """The confidence a leg prints - see the module doc; None =
        NO_LINE_EVIDENCE. `base` is the curve's (value, source, n) at p."""
        offset = 0.0
        if base is not None:
            offset = self.offset(sport, key)
            value = round(max(float(base[0]) + offset, 0.0), 4)
            source = f"{base[1]}{offset:+.4f}sb" if offset < 0.0 else base[1]
            n = int(base[2])
        else:
            hit = self.bucket(sport, key, p)
            if hit is None or hit[0] < self._min():
                return None
            n, k = hit
            if self.v2:
                games = self.bucket_games(sport, key, p)
                if games is None or games < int(
                        self.doc.get("min_evidence_games", MIN_EVIDENCE_GAMES)):
                    return None
                deff = max(float((self.doc.get("design_effect") or {}).get(
                    sport) or 1.0), 1.0)
                value = round(wilson_lo(round(k / deff), round(n / deff)), 4)
            else:
                value = round(wilson_lo(k, n), 4)
            source = f"sb:{sport}:{key}"
        cap = self.band_cap(sport, key, p, odds, value)
        if cap is not None and cap[0] < value:
            return Read(cap[0], f"{source}|cap:{cap[1]}", n, offset, cap[0])
        return Read(value, source, n, offset)


# --- the fit (scripts/sofa/fit_line_evidence.py) -----------------------------------

Row = dict[str, Any]  # sport, key, p, y, game, base (confidence or None), odds


def _bootstrap_gap(items: Sequence[tuple[str, float]], rng: random.Random
                   ) -> list[float]:
    """[point, lo95, hi95] of mean(y - confidence), resampling games."""
    games: dict[str, list[float]] = defaultdict(list)
    for game, d in items:
        games[game].append(d)
    ids = list(games)
    total = sum(sum(v) for v in games.values()) / max(len(items), 1)
    stats: list[float] = []
    for _ in range(BOOTSTRAP):
        s = c = 0.0
        for _ in ids:
            g = games[ids[rng.randrange(len(ids))]]
            s += sum(g)
            c += len(g)
        stats.append(s / c if c else 0.0)
    stats.sort()
    return [round(total, 4), round(stats[int(0.025 * BOOTSTRAP)], 4),
            round(stats[int(0.975 * BOOTSTRAP)], 4)]


def _cells(rows: Iterable[Row], games: bool = False) -> dict[str, dict[str, int]]:
    """p bucket -> {n, k}; `games` adds the distinct games (v2 reads it)."""
    counts: dict[int, list[int]] = defaultdict(list)
    seen: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        counts[bucket_of(float(r["p"]))].append(int(r["y"]))
        seen[bucket_of(float(r["p"]))].add(str(r["game"]))
    out: dict[str, dict[str, int]] = {}
    for b, ys in sorted(counts.items()):
        out[bucket_label(b)] = {"n": len(ys), "k": sum(ys)}
        if games:
            out[bucket_label(b)]["games"] = len(seen[b])
    return out


def design_effect(items: Sequence[tuple[str, int]]) -> float:
    """Variance inflation of a rate of lines that come in games: the
    game-clustered variance of the mean over the binomial one, >= 1
    (2026-10-07 audit: football 1.7, tennis 1.4, hockey 1.7, basketball 6.6,
    CS2 3.3, volleyball 2.5). `items`: (game, y)."""
    n = len(items)
    if n < 2:
        return 1.0
    p = sum(y for _, y in items) / n
    if p <= 0.0 or p >= 1.0:
        return 1.0
    by: dict[str, list[int]] = defaultdict(list)
    for g, y in items:
        by[g].append(y)
    num = sum((sum(v) - p * len(v)) ** 2 for v in by.values())
    return round(max(num / (n * p * (1 - p)), 1.0), 3)


def fit(rows: Iterable[Row], seed: int = 7) -> dict[str, Any]:
    """{"keys": sport -> key -> {n, games, buckets, printable?},
    "bands": sport -> key | SPORT_SCOPE -> band -> p bucket -> {n, k}}.
    A row without `odds` counts in `keys` and in no band."""
    by_key: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for r in rows:
        by_key[(str(r["sport"]), str(r["key"]))].append(r)
    rng = random.Random(seed)
    keys: dict[str, dict[str, Any]] = defaultdict(dict)
    banded: dict[str, dict[str, dict[str, list[Row]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    for (sport, key), rs in sorted(by_key.items()):
        entry: dict[str, Any] = {"n": len(rs),
                                 "games": len({str(r["game"]) for r in rs}),
                                 "buckets": _cells(rs, games=True)}
        printable = [r for r in rs if r.get("base") is not None
                     and float(r["base"]) >= PRINTABLE_FROM]
        if printable:
            m = len(printable)
            entry["printable"] = {
                "n": m, "games": len({str(r["game"]) for r in printable}),
                "confidence": round(sum(float(r["base"]) for r in printable) / m, 4),
                "realised": round(sum(int(r["y"]) for r in printable) / m, 4),
                "realised_minus_confidence": _bootstrap_gap(
                    [(str(r["game"]), int(r["y"]) - float(r["base"]))
                     for r in printable], rng)}
        keys[sport][key] = entry
        for r in rs:
            if r.get("odds"):
                band = band_label(float(r["odds"]))
                banded[sport][key][band].append(r)
                banded[sport][SPORT_SCOPE][band].append(r)
    bands = {sport: {scope: {band: _cells(rs) for band, rs in sorted(by_band.items())}
                     for scope, by_band in sorted(scopes.items())}
             for sport, scopes in sorted(banded.items())}
    pooled: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (sport, _), rs in by_key.items():
        pooled[sport] += [(str(r["game"]), int(r["y"]) - float(r["base"]))
                          for r in rs if r.get("base") is not None
                          and float(r["base"]) >= PRINTABLE_FROM]
    sport_printable = {
        sport: {"n": len(items), "games": len({g for g, _ in items}),
                "realised_minus_confidence": _bootstrap_gap(items, rng)}
        for sport, items in sorted(pooled.items()) if items}
    # v2: the pool without a key that dominates it, and the design effect of
    # each sport's printable lines.
    deff: dict[str, float] = {}
    for sport in sorted(pooled):
        per_key: dict[str, list[tuple[str, float]]] = {}
        clustered: list[tuple[str, int]] = []
        for (s, key), rs in by_key.items():
            if s != sport:
                continue
            pr = [(str(r["game"]), int(r["y"]), float(r["base"])) for r in rs
                  if r.get("base") is not None
                  and float(r["base"]) >= PRINTABLE_FROM]
            if pr:
                per_key[key] = [(g, y - b) for g, y, b in pr]
            # The design effect is read by the keys that have NO curve, whose
            # lines are never in `pr` (CS2 2026-10-07: 1.0 from 61 curve rows,
            # 2.5-3.2 from the stand-in keys' own lines): every line whose p
            # could print counts.
            clustered += [(str(r["game"]), int(r["y"])) for r in rs
                          if float(r["p"]) >= PRINTABLE_FROM]
        deff[sport] = design_effect(clustered)
        total = sum(len(v) for v in per_key.values())
        top = max(per_key, key=lambda k: len(per_key[k]), default=None)
        if top is not None and len(per_key) >= 2 \
                and len(per_key[top]) > CONCENTRATION_MAX * total:
            rest = [it for k, v in per_key.items() if k != top for it in v]
            sport_printable[sport]["without"] = {
                "key": top, "n": len(rest), "games": len({g for g, _ in rest}),
                "realised_minus_confidence": _bootstrap_gap(rest, rng)
                if rest else [0.0, 0.0, 0.0]}
    return {"keys": dict(keys), "bands": bands, "sport_printable": sport_printable,
            "design_effect": deff}
