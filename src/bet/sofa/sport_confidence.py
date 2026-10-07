"""Confidence for hockey, basketball, volleyball and CS2 legs - from statistics.

Plan 2026-10-05, part 5 (decision D2): these four sports go on the one coupon,
and their confidence comes from the score model (bet.sofa.score_model) or the
CS2 engine (bet.sofa.cs2_engine), calibrated on the results history without
a price. A price is never an input here - not to the model, not to the curve,
not to the order. It is only the condition of a bet (run_sport_confidence.py
applies the coupon's filters on it).

What this module holds:

* ALLOWED_MARKETS / CS2_FAMILIES (F2): the only markets a sport leg may come
  from. Each Superbet market id was checked against shadow.MARKETS; dnb,
  odd/even, yes/no, the exact score, basketball's second half and Q4 (whose
  overtime reading is ambiguous) and every player line are out.
* The walk-forward rows the calibration is fitted on (F4): each historical
  game forecast from a model built strictly before it, on synthetic lines
  placed at the quantiles of the game's own simulated distribution (no
  price places them), and the settled Superbet lines' model probability.
* The curve (EDGES and the Wilson lower bound as scripts/sofa/fit_confidence
  .py), the out-of-sample check and the admission rule (F6).
* The sample "k of n" (F3): the two teams' last ten league games graded on
  the leg's own line - shown beside the leg, never a gate.
"""

from __future__ import annotations

import json
import math
import random
from bisect import bisect_right
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from bet.sofa import cs2_engine
from bet.sofa.comparability import MatchKind, competition_id, match_kind
from bet.sofa.cs2 import Cs2Line
from bet.sofa.football_rating import FootballResult
from bet.sofa.score_model import (
    ScoreModel,
    _rated_values,
    build_model,
    line_probability,
    parse_event,
)
from bet.sofa.shadow import (
    MARKETS,
    ORIENTATION_FREE,
    PLAYER_MARKETS,
    GameResult,
    ShadowLine,
    ShadowSport,
    actual_value,
    build_result,
    grade,
)

SportKey = Literal["hockey", "basketball", "volleyball", "cs2"]
SPORT_KEYS: tuple[SportKey, ...] = ("hockey", "basketball", "volleyball", "cs2")
SHADOW_SPORT_KEYS: tuple[SportKey, ...] = ("hockey", "basketball", "volleyball")

CALIBRATION_FILE = "sofa_sport_confidence_calibration.json"
# A refit staged for a later day (never mid-day): the same document with
# `effective_from` (YYYY-MM-DD); a day at or after it reads this file instead
# of CALIBRATION_FILE. The refit procedure later moves it over CALIBRATION_FILE.
NEXT_CALIBRATION_FILE = "sofa_sport_confidence_calibration.next.json"


def calibration_path_for(date: str, config_dir: Path | None = None) -> Path:
    """The sport calibration a day reads: the staged one from its
    `effective_from`, else the installed one."""
    from bet.sofa.config import config_path

    main = (config_dir / CALIBRATION_FILE) if config_dir else config_path(
        CALIBRATION_FILE)
    nxt = (config_dir / NEXT_CALIBRATION_FILE) if config_dir else config_path(
        NEXT_CALIBRATION_FILE)
    if nxt.exists():
        eff = json.loads(nxt.read_text(encoding="utf-8")).get("effective_from")
        if isinstance(eff, str) and date >= eff:
            return nxt
    return main

# --- F2: the allow-list ---------------------------------------------------------
#
# market id -> family, every one read off shadow.MARKETS (a test holds the two
# equal). Hockey: winner incl. overtime and shootout (630), regulation total
# (623), regulation team totals (658 team1 / 652 team2), regulation handicap
# (604), regulation 1X2 (640); per period total (649), team totals (674 / 638),
# handicap (678), 1X2 (660). Basketball: winner incl. overtime (759), total
# (753), handicap (768), team totals (758 / 776), regulation 1X2 (777); first
# half total (748), handicap (773), team totals (200804 / 200797), 1X2 (763).
# Volleyball: match winner (745), sets total (230058), set handicap (100082),
# points total (230060), points handicap (1069), set winner (744 - a set has
# no draw, so its "dnb" kind is a winner), set points total (782).
ALLOWED_MARKETS: dict[str, dict[int, str]] = {
    "hockey": {
        630: "winner", 623: "total", 658: "team_total", 652: "team_total",
        604: "handicap", 640: "result_1x2",
        649: "period_total", 674: "period_team_total",
        638: "period_team_total", 678: "period_handicap", 660: "period_1x2",
    },
    "basketball": {
        759: "winner", 753: "total", 768: "handicap", 758: "team_total",
        776: "team_total", 777: "result_1x2",
        748: "h1_total", 773: "h1_handicap", 200804: "h1_team_total",
        200797: "h1_team_total", 763: "h1_1x2",
    },
    "volleyball": {
        745: "winner", 230058: "sets_total", 100082: "set_handicap",
        230060: "points_total", 1069: "points_handicap",
        744: "set_winner", 782: "set_points_total",
    },
}
# Operator, 2026-10-07 ("nie ucinać nic, co może wygrywać"): from
# epochs.LINE_EVIDENCE_FROM_UTC the families the score model can grade but the
# first allow-list left out go on too, each read through its own curve and its
# settled Superbet lines (bet.sofa.line_evidence) like every other key. The
# model already simulates every quarter, so nothing new is modelled: hockey's
# period draw-no-bet (662); basketball's first-half dnb (765), second half
# (233404 total, 233405 handicap, 233806 / 233807 team totals, 233499 dnb,
# 233400 1X2), quarters (788 total, 774 handicap, 200802 / 200795 team
# totals, 772 dnb, 779 1X2) and odd/even (775, team 230634 / 230640).
# Basketball's second half and Q4: Superbet names them without "(z
# dogrywką)" and its rules (support.superbet.pl, read 2026-10-07) do not say
# whether overtime is appended - a game that went to overtime grades them
# NOT_GRADED here (shadow._pair), the leg carries OT_RULE_UNKNOWN.
EXTENDED_MARKETS: dict[str, dict[int, str]] = {
    "hockey": {662: "period_dnb"},
    "basketball": {
        765: "h1_dnb", 233404: "h2_total", 233405: "h2_handicap",
        233806: "h2_team_total", 233807: "h2_team_total", 233499: "h2_dnb",
        233400: "h2_1x2", 788: "quarter_total", 774: "quarter_handicap",
        200802: "quarter_team_total", 200795: "quarter_team_total",
        772: "quarter_dnb", 779: "quarter_1x2", 775: "odd_even",
        230634: "team_odd_even", 230640: "team_odd_even",
    },
    # Volleyball (operator, 2026-10-07, same rule): the exact set score (785)
    # and the match's points parity (200896) are scored from the history;
    # a set's points parity (781) and "set on extra points" (100077) only
    # from settled Superbet lines, as the other set markets (plan F4).
    "volleyball": {785: "exact_sets", 200896: "points_odd_even",
                   781: "set_points_odd_even", 100077: "set_extra_points"},
}
OT_RULE_UNKNOWN = "OT_RULE_UNKNOWN"
# Player lines (shadow.PLAYER_MARKETS, hockey and basketball) under the same
# epoch: their p is player_model's pre-game number SHADOW writes beside every
# snapshot (player_model.jsonl, model `player_rate_v3`, no price); no history
# curve exists, so a leg reads its family's own settled Superbet lines
# (bet.sofa.line_evidence) or is NO_LINE_EVIDENCE.


def allowed_markets(sport: str, extended: bool = False) -> dict[int, str]:
    """The allow-list; `extended` (epochs.line_evidence) adds EXTENDED_MARKETS."""
    out = dict(ALLOWED_MARKETS.get(sport, {}))
    if extended:
        out.update(EXTENDED_MARKETS.get(sport, {}))
    return out


def ot_rule_unknown(sport: str, family: str, period: int) -> bool:
    """A basketball second-half or Q4 leg: overtime's reading is not known."""
    return sport == "basketball" and (
        family.startswith("h2_") or (family.startswith("quarter_") and period == 4))


# CS2: series and map winner (the engine's calibrated map Elo) and a team's
# rounds on one map. Out: map_rounds_total (the engine's constant base rate),
# maps_* (no number - the engine refuses them), team_kills, player_*.
CS2_FAMILIES: frozenset[str] = frozenset(
    {"map_winner", "match_winner", "map_team_rounds"})
# From epochs.LINE_EVIDENCE_FROM_UTC (operator, 2026-10-07): every other
# family the engine prices (cs2_engine.MODELLED) - a map's round handicap and
# total (the latter the history's base rate), a team's kills, a player's
# kills / deaths / assists / headshots. CS2_SETTLE attaches the engine's
# pre-match p to each graded side (settle_cs2.attach_model): their evidence.
# The series families (maps_*, team_maps, exact_maps, rounds_*) stay out:
# the engine prices none of them (it lost to a constant, cs2_engine).
CS2_EXTENDED_FAMILIES: frozenset[str] = frozenset(
    {"map_rounds_handicap", "map_rounds_total", "team_kills", "player_kills",
     "player_deaths", "player_assists", "player_headshots"})

# The families the results history fits, with the market id a synthetic line
# is built on. A team total is built twice (team1's id and team2's).
#
# Hockey's period families and basketball's first half are scored from the
# history too since 2026-10-05 (night): the model simulates every period and
# the history carries every period's score, while three settled days left no
# printable bucket of 200 rows - 339 hockey period legs NOT_CALIBRATED on
# 10-05. A period market is scored on each of its sport's PERIODS.
HISTORY_MARKETS: dict[str, tuple[int, ...]] = {
    "hockey": (630, 623, 658, 652, 604, 640, 649, 674, 638, 678, 660, 662),
    "basketball": (759, 753, 768, 758, 776, 777, 748, 773, 200804, 200797, 763,
                   *EXTENDED_MARKETS["basketball"]),
    "volleyball": (745, 230058, 100082, 230060, 1069, 785, 200896),
}
PERIODS: dict[str, tuple[int, ...]] = {"hockey": (1, 2, 3), "basketball": (1, 2, 3, 4)}
# The rest (volleyball's set markets): only from settled Superbet lines (plan F4).
SETTLED_ONLY_FAMILIES: dict[str, frozenset[str]] = {
    sport: frozenset(
        fam for mid, fam in allowed_markets(sport, extended=True).items()
        if mid not in HISTORY_MARKETS[sport])
    for sport in ALLOWED_MARKETS
}

# Where a synthetic line sits: the game's own simulated distribution at these
# quantiles (the model's, never a price's), half a point off an integer.
# Five quantiles (the first fit, 2026-10-05) left basketball's p bunched at
# ~0.75 and ~0.90 - every bucket between them empty, so a leg there could
# never be calibrated; thirteen fill the grid.
LINE_QUANTILES = (0.05, 0.1, 0.15, 0.2, 0.25, 0.35, 0.5, 0.65, 0.75, 0.8, 0.85,
                  0.9, 0.95)
# A synthetic line the simulation puts (almost) entirely on one side is past
# the game's support - volleyball's "sets UNDER 5.5" won every time and filled
# the 0.95-1.01 bucket with certainties no posted line has. Such a line is
# not scored.
DEGENERATE_P = 0.01
# CS2 team rounds on one map: the lines Superbet posted on the settled days
# 09-28..10-04 (10.5 / 11.5 / 12.5 are 85% of them).
CS2_TEAM_ROUND_LINES = (9.5, 10.5, 11.5, 12.5)
# A curve fitted only on these lines says nothing about another one: the
# lookup reads p alone, so without this a 6.5 line on a lopsided series read
# the 9.5-12.5 curve (2026-10-05 night: such printable rows on settled
# Superbet lines realised 0.30 at a confidence of 0.731, n=20, 8 series).
FITTED_LINES: dict[tuple[str, str], tuple[float, ...]] = {
    ("cs2", "map_team_rounds"): CS2_TEAM_ROUND_LINES,
}
LINE_OUTSIDE_FIT = "LINE_OUTSIDE_FIT"


def line_in_fit(sport: str, family: str, line: float | None) -> bool:
    """Was the family's curve fitted on this line (True where the curve is
    not line-specific)?"""
    lines = FITTED_LINES.get((sport, family))
    if lines is None:
        return True
    return line is not None and any(abs(float(line) - x) < 1e-9 for x in lines)

# --- the curve (as scripts/sofa/fit_confidence.py; a test holds them equal) ------

EDGES = [0.0, 0.60, 0.70, 0.75, 0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 1.01]
MIN_BUCKET = 200  # a bucket under this is unused (plan F4)
MAX_OVERSTATEMENT = 0.03  # F6: OOS confidence above realised by more: refused
BOOTSTRAP = 2000
# The rows a coupon could print: confidence at or above the official floor
# (confidence.COUPON_PROFILE.floor; a test holds the two equal). The
# out-of-sample summary reports them on their own.
PRINTABLE_FROM = 0.70
UNFITTED_CONSTANTS = (
    "LINE_QUANTILES",
    "CS2_TEAM_ROUND_LINES",
    "MIN_BUCKET",
    "MAX_OVERSTATEMENT",
    "REBUILD_DAYS",
)


def bucket_of(p: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def bucket_label(b: int) -> str:
    return f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"


def wilson_lo(k: int, n: int, z: float = 1.959964) -> float:
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def side_class(side: str) -> str:
    """OVER / UNDER / DRAW / ODD / EVEN / YES / NO and an exact score ("3:1")
    keep their own curve; a team side is TEAM."""
    if side in ("OVER", "UNDER", "DRAW", "ODD", "EVEN", "YES", "NO") or ":" in side:
        return side
    return "TEAM"


def curve_key(family: str, side: str) -> str:
    return f"{family}|{side_class(side)}"


def family_of(sport: str, market_id: int | None, family: str,
              extended: bool = False) -> str | None:
    """The allowed family of a line, or None when it may not be a leg."""
    if sport == "cs2":
        allowed = CS2_FAMILIES | (CS2_EXTENDED_FAMILIES if extended else frozenset())
        return family if family in allowed else None
    if market_id is None:
        return None
    if extended and int(market_id) in PLAYER_MARKETS.get(sport, {}):  # type: ignore[call-overload]
        return str(PLAYER_MARKETS[sport][int(market_id)].family)  # type: ignore[index]
    return allowed_markets(sport, extended).get(int(market_id))


Row = dict[str, Any]


def fit_curves(rows: Iterable[Row], min_bucket: int = MIN_BUCKET
               ) -> dict[str, dict[str, dict[str, Any]]]:
    """key -> bucket label -> {n, realised, realised_lo95}; buckets under
    `min_bucket` rows are left out (unused)."""
    counts: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        counts[r["key"]][bucket_of(float(r["p"]))].append(int(r["y"]))
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for key, by_bucket in sorted(counts.items()):
        curve: dict[str, dict[str, Any]] = {}
        for b, ys in sorted(by_bucket.items()):
            if len(ys) < min_bucket:
                continue
            k, n = sum(ys), len(ys)
            curve[bucket_label(b)] = {
                "n": n, "realised": round(k / n, 4),
                "realised_lo95": round(wilson_lo(k, n), 4)}
        if curve:
            out[key] = curve
    return out


def _find(curve: Mapping[str, Mapping[str, Any]], p: float) -> Mapping[str, Any] | None:
    for label, entry in curve.items():
        lo, hi = (float(x) for x in label.split("-"))
        if lo <= p < hi:
            return entry
    return None


@dataclass(frozen=True)
class Confidence:
    value: float  # the bucket's realised_lo95
    n: int
    calibrated_on: str  # "<sport>:<family>|<side class>"


@dataclass
class SportCalibration:
    """The fitted curves of config/sofa_sport_confidence_calibration.json."""

    doc: dict[str, Any]

    @staticmethod
    def load(path: Path) -> SportCalibration | None:
        if not path.exists():
            return None
        return SportCalibration(json.loads(path.read_text(encoding="utf-8")))

    @property
    def fitted_from(self) -> dict[str, Any]:
        return dict(self.doc.get("fitted_from") or {})

    def has_sport(self, sport: str) -> bool:
        return sport in (self.doc.get("sports") or {})

    def admitted(self, sport: str) -> list[str]:
        return list(((self.doc.get("sports") or {}).get(sport) or {}).get(
            "admitted") or [])

    def has_curves(self, sport: str) -> bool:
        return bool(((self.doc.get("sports") or {}).get(sport) or {})
                     .get("curves"))

    def lookup(self, sport: str, family: str, side: str, p: float,
               require_admitted: bool = True) -> Confidence | None:
        """The confidence of a model probability, or None (NOT_CALIBRATED):
        a key that is not admitted, or a p outside every bucket it has.
        `require_admitted=False` (epochs.line_evidence): the curve of any
        fitted key - its settled Superbet lines correct it (bet.sofa.
        line_evidence) instead of the admission refusing it."""
        entry = (self.doc.get("sports") or {}).get(sport) or {}
        key = curve_key(family, side)
        if require_admitted and key not in (entry.get("admitted") or []):
            return None
        bucket = _find((entry.get("curves") or {}).get(key) or {}, p)
        if bucket is None or int(bucket["n"]) < int(
                self.doc.get("min_bucket", MIN_BUCKET)):
            return None
        return Confidence(float(bucket["realised_lo95"]), int(bucket["n"]),
                          f"{sport}:{key}")


# --- the out-of-sample check and the admission rule (F5, F6) ---------------------


def _logloss(p: float, y: int) -> float:
    q = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(q if y else 1.0 - q)


def evaluate(curves: Mapping[str, Mapping[str, Mapping[str, Any]]],
             rows: Sequence[Row], seed: int = 7) -> dict[str, Any]:
    """Each key's out-of-sample rows read through the fitted curve.

    Per bucket: n, the confidence the curve prints (its lo95), the realised
    rate. Per key: log-loss of the printed confidence and of the raw model
    probability on the rows the curve covers, and realised minus confidence
    with a 95% interval from a bootstrap over GAMES (a game's lines are not
    independent).
    """
    by_key: dict[str, list[tuple[Row, float]]] = defaultdict(list)
    uncovered: Counter[str] = Counter()
    for r in rows:
        entry = _find(curves.get(r["key"]) or {}, float(r["p"]))
        if entry is None:
            uncovered[r["key"]] += 1
            continue
        by_key[r["key"]].append((r, float(entry["realised_lo95"])))
    rng = random.Random(seed)
    out: dict[str, Any] = {}
    for key in sorted(set(by_key) | set(uncovered)):
        items = by_key.get(key, [])
        buckets: dict[str, dict[str, Any]] = {}
        per_bucket: dict[str, list[tuple[float, int]]] = defaultdict(list)
        for r, c in items:
            per_bucket[bucket_label(bucket_of(float(r["p"])))].append((c, int(r["y"])))
        for label, cy in sorted(per_bucket.items()):
            n = len(cy)
            realised = sum(y for _, y in cy) / n
            conf = sum(c for c, _ in cy) / n
            buckets[label] = {"n": n, "confidence": round(conf, 4),
                              "realised": round(realised, 4),
                              "gap": round(conf - realised, 4)}
        summary: dict[str, Any] = {"n": len(items),
                                   "uncovered": uncovered.get(key, 0),
                                   "buckets": buckets}
        if items:
            n = len(items)
            summary["games"] = len({r["game"] for r, _ in items})
            summary["logloss_confidence"] = round(
                sum(_logloss(c, int(r["y"])) for r, c in items) / n, 5)
            summary["logloss_model"] = round(
                sum(_logloss(float(r["p"]), int(r["y"])) for r, _ in items) / n, 5)
            summary["realised"] = round(sum(int(r["y"]) for r, _ in items) / n, 4)
            summary["confidence"] = round(sum(c for _, c in items) / n, 4)
            summary["realised_minus_confidence"] = _bootstrap_gap(items, rng)
            printable = [(r, c) for r, c in items if c >= PRINTABLE_FROM]
            if printable:
                m = len(printable)
                summary["printable"] = {
                    "n": m, "games": len({r["game"] for r, _ in printable}),
                    "confidence": round(sum(c for _, c in printable) / m, 4),
                    "realised": round(sum(int(r["y"]) for r, _ in printable) / m, 4),
                    "realised_minus_confidence": _bootstrap_gap(printable, rng)}
        out[key] = summary
    return out


def _bootstrap_gap(items: Sequence[tuple[Row, float]], rng: random.Random
                   ) -> list[float]:
    games: dict[str, list[float]] = defaultdict(list)
    for r, c in items:
        games[str(r["game"])].append(int(r["y"]) - c)
    ids = list(games)
    total = sum(sum(v) for v in games.values()) / sum(len(v) for v in games.values())
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


def admission(curves: Mapping[str, Any], checks: Mapping[str, Mapping[str, Any]],
              min_bucket: int = MIN_BUCKET,
              max_overstatement: float = MAX_OVERSTATEMENT
              ) -> tuple[list[str], dict[str, str]]:
    """(admitted keys, key -> why not). `checks` is population -> evaluate().

    F6 as planned: no out-of-sample bucket of `min_bucket` rows, in ANY
    population, may print a confidence more than `max_overstatement` above
    what it realised. Two conditions on top, both about the legs that can
    actually print (confidence >= PRINTABLE_FROM, the official floor):

    * evidence - at least one printable out-of-sample bucket of
      `min_bucket` rows. The 0.00-0.60 catch-all bucket is the only large
      bucket of many keys, and it says nothing about a printed leg; a key
      without a tested printable bucket is NOT_CALIBRATED, never admitted
      on the fit alone;
    * the printable rows of each population pooled: refused when they
      overstate by more than `max_overstatement` at n >= `min_bucket`, or
      when the bootstrap's (over games) upper 95% bound of realised minus
      confidence is below -`max_overstatement` at any n - the settled
      Superbet lines are few, and a bucket rule alone cannot read them.
    """
    admitted: list[str] = []
    refused: dict[str, str] = {}
    for key in sorted(curves):
        printable_tested = 0
        worst: tuple[float, str, str] | None = None
        pooled_bad: str | None = None
        for population, result in checks.items():
            entry = result.get(key) or {}
            for label, b in (entry.get("buckets") or {}).items():
                if int(b["n"]) < min_bucket:
                    continue
                if float(b["confidence"]) >= PRINTABLE_FROM:
                    printable_tested += 1
                gap = float(b["confidence"]) - float(b["realised"])
                if gap > max_overstatement and (worst is None or gap > worst[0]):
                    worst = (gap, population, label)
            pr = entry.get("printable")
            if pr and pooled_bad is None:
                point, _, hi = (float(x) for x in pr["realised_minus_confidence"])
                if hi < -max_overstatement or (
                        int(pr["n"]) >= min_bucket and point < -max_overstatement):
                    pooled_bad = (
                        f"OVERSTATES_PRINTABLE: {population} n={pr['n']} "
                        f"confidence {pr['confidence']:.4f} realised "
                        f"{pr['realised']:.4f} (realised-confidence {point:+.4f}, "
                        f"95% upper {hi:+.4f})")
        if worst is not None:
            refused[key] = (f"OVERSTATES: {worst[1]} bucket {worst[2]} "
                            f"confidence above realised by {worst[0]:.4f}")
        elif pooled_bad is not None:
            refused[key] = pooled_bad
        elif printable_tested == 0:
            refused[key] = (f"NO_OOS_PRINTABLE_BUCKET_WITH_N>={min_bucket} "
                            f"(confidence >= {PRINTABLE_FROM})")
        else:
            admitted.append(key)
    return admitted, refused


# --- walk-forward over the results history (F4) -----------------------------------

REBUILD_DAYS = 30  # the model's shares / spread are rebuilt this often


@dataclass(frozen=True)
class HistoryGame:
    rating: FootballResult  # what the book learns from
    result: GameResult | None  # home = team1; None: the score does not grade
    event: dict[str, Any] = field(repr=False, compare=False)


def parse_history(events: Mapping[int, dict[str, Any]], sport: ShadowSport
                  ) -> list[HistoryGame]:
    """Every rated finished game, oldest first (friendlies out, by
    score_model.parse_event -> comparability)."""
    out: list[HistoryGame] = []
    for e in events.values():
        r = parse_event(e, sport)
        if r is None:
            continue
        out.append(HistoryGame(r, build_result(e, sport, True), e))
    out.sort(key=lambda g: (g.rating.ts, g.rating.event_id))
    return out


def _probe(sport: ShadowSport, market_id: int, subject: str, period: int = 0
           ) -> ShadowLine:
    spec = MARKETS[sport.key][market_id]
    side = "OVER" if spec.kind in ("total", "team_total") else "T1"
    return ShadowLine("", market_id, spec.family, period, subject, 0.0, side, 1.0)


def market_periods(sport: ShadowSport, market_id: int) -> tuple[int, ...]:
    """The periods a market is scored on: (0,) unless it is a period market."""
    if MARKETS[sport.key][market_id].scope != "period":
        return (0,)
    return PERIODS.get(sport.key, ())


def _pair_sets(g: GameResult) -> tuple[int, int] | None:
    """(sets won by team1, by team2) of a volleyball game."""
    s1 = sum(1 for a, b in zip(g.t1_periods, g.t2_periods, strict=True) if a > b)
    s2 = len(g.t1_periods) - s1
    return (s1, s2) if s1 or s2 else None


def synthetic_lines(sport: ShadowSport, market_id: int, sims: Sequence[GameResult],
                    period: int = 0) -> list[ShadowLine]:
    """Both (all) sides of the lines a game is scored on for one market.

    A total / team total / handicap: at LINE_QUANTILES of the game's own
    simulated quantity, half a point off an integer (no push). A winner or a
    1X2 has no line.
    """
    spec = MARKETS[sport.key][market_id]
    subject = spec.team or ""
    if spec.kind in ("winner", "dnb"):
        return [ShadowLine("", market_id, spec.family, period, "", None, s, 1.0)
                for s in ("T1", "T2")]
    if spec.kind == "odd_even":
        return [ShadowLine("", market_id, spec.family, period, subject, None, s, 1.0)
                for s in ("ODD", "EVEN")]
    if spec.kind == "yes_no":
        return [ShadowLine("", market_id, spec.family, period, "", None, s, 1.0)
                for s in ("YES", "NO")]
    if spec.kind == "exact":
        # every set score the game's own simulation reaches
        scores = sorted({sc for g in sims if (sc := _pair_sets(g)) is not None})
        return [ShadowLine("", market_id, spec.family, period, "", None,
                           f"{a}:{b}", 1.0) for a, b in scores]
    if spec.kind == "three_way":
        return [ShadowLine("", market_id, spec.family, period, "", None, s, 1.0)
                for s in ("T1", "DRAW", "T2")]
    probe = _probe(sport, market_id, subject, period)
    values = sorted(v for g in sims if (v := actual_value(probe, g, sport)) is not None)
    if not values:
        return []
    cut = sorted({math.floor(values[int(q * (len(values) - 1))]) + 0.5
                  for q in LINE_QUANTILES})
    out: list[ShadowLine] = []
    for c in cut:
        if spec.kind == "handicap":
            # team1 covers when margin + hcp > 0: hcp = -c asks margin > c
            out += [ShadowLine("", market_id, spec.family, period, "", -c, s, 1.0)
                    for s in ("T1", "T2")]
        else:
            out += [ShadowLine("", market_id, spec.family, period, subject, c, s, 1.0)
                    for s in ("OVER", "UNDER")]
    return out


def score_game(sport: ShadowSport, model: ScoreModel, game: HistoryGame,
               n_sims: int, source: str) -> list[Row]:
    """The rows of one historical game, from the model as it stands."""
    if game.result is None:
        return []
    r = game.rating
    exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
    if exp is None:
        return []
    sims = model.simulate(exp[0], exp[1], seed=r.event_id, n=n_sims)
    rows: list[Row] = []
    three = {mid for mid, s in MARKETS[sport.key].items() if s.kind == "three_way"}
    lines = [ln for mid in HISTORY_MARKETS[sport.key]
             for period in market_periods(sport, mid)
             for ln in synthetic_lines(sport, mid, sims, period)]
    for line in lines:
        mid = line.market_id
        p = line_probability(line, sims, sport)
        if p is None:
            continue
        if line.line is not None and not DEGENERATE_P <= p <= 1 - DEGENERATE_P:
            continue
        actual = actual_value(line, game.result, sport)
        if actual is None:
            continue
        outcome = grade(line, actual, mid in three)
        if outcome == "VOID":
            continue
        rows.append({
            "sport": sport.key, "family": line.family, "market_id": mid,
            "period": line.period, "subject": line.subject, "line": line.line,
            "side": line.side, "key": curve_key(line.family, line.side),
            "p": round(p, 4), "y": 1 if outcome == "WIN" else 0,
            "game": f"h:{r.event_id}", "ts": r.ts, "source": source})
    return rows


def walk_forward_rows(history: Sequence[HistoryGame], sport: ShadowSport,
                      start_ts: int, end_ts: int, n_sims: int,
                      max_games: int | None, source: str) -> list[Row]:
    """Rows for the games in [start_ts, end_ts), each forecast from a model
    built only from games that started strictly before it.

    The model is rebuilt (score_model.build_model, cut at the game's start)
    every REBUILD_DAYS; in between the rating book is updated game by game,
    and games that share a start time are all forecast before any of them is
    learnt - no game ever sees its own score or a later one.
    """
    ratings = [g.rating for g in history]
    window = [g for g in history if start_ts <= g.rating.ts < end_ts]
    step = max(1, len(window) // max_games) if max_games else 1
    scored = {id(g) for i, g in enumerate(window) if i % step == 0}
    model: ScoreModel | None = None
    next_rebuild = start_ts
    rows: list[Row] = []
    i = 0
    while i < len(window):
        ts = window[i].rating.ts
        j = i
        while j < len(window) and window[j].rating.ts == ts:
            j += 1
        batch = window[i:j]
        if model is None or ts >= next_rebuild:
            model = build_model(ratings, sport, ts)
            next_rebuild = ts + REBUILD_DAYS * 86400
        for g in batch:
            if id(g) in scored:
                rows += score_game(sport, model, g, n_sims, source)
        for g in batch:
            model.book.update(_rated_values(g.rating, sport))
            if model.last_played is not None:
                model.last_played[g.rating.home_id] = g.rating.ts
                model.last_played[g.rating.away_id] = g.rating.ts
        i = j
    return rows


def day_ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def settled_shadow_rows(runs_dir: str, sport: ShadowSport, dates: Sequence[str],
                        events: Mapping[int, dict[str, Any]],
                        history: Sequence[HistoryGame], n_sims: int) -> list[Row]:
    """Superbet's settled lines of `dates` (runs/sofa/shadow/<sport>/<d>/
    settled.json), each with the model's probability from a model built
    strictly before the day - measure_score_model.py's reading. Only allowed
    markets; the price on the row is never read."""
    ratings = [g.rating for g in history]
    rows: list[Row] = []
    allowed = allowed_markets(sport.key, extended=True)
    for date in dates:
        path = Path(runs_dir) / "shadow" / sport.key / date / "settled.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        model = build_model(ratings, sport, day_ts(date))
        for sb_id, entry in (doc.get("events") or {}).items():
            if entry.get("state") != "SETTLED" or entry.get("orientation_unclear"):
                continue
            try:
                event = events.get(int(entry["sofascore_event_id"]))
            except (KeyError, TypeError, ValueError):
                continue
            if event is None:
                continue
            comp = competition_id(event) or int(event["tournament"]["id"])
            exp = model.expected(comp, int(event["homeTeam"]["id"]),
                                 int(event["awayTeam"]["id"]))
            if exp is None:
                continue
            mh, ma = exp
            mu1, mu2 = (mh, ma) if entry.get("home_is_team1") else (ma, mh)
            games = model.simulate(mu1, mu2, seed=int(entry["sofascore_event_id"]),
                                   n=n_sims)
            for g in entry.get("graded") or []:
                if g.get("outcome") not in ("WIN", "LOSS"):
                    continue
                fam = allowed.get(int(g.get("market_id") or 0))
                if fam is None:
                    continue
                line = ShadowLine(str(sb_id), int(g["market_id"]), str(g["family"]),
                                  int(g.get("period") or 0),
                                  str(g.get("subject") or ""),
                                  g.get("line"), str(g["side"]), 1.0)
                p = line_probability(line, games, sport)
                if p is None:
                    continue
                rows.append({
                    "sport": sport.key, "family": fam, "market_id": line.market_id,
                    "period": line.period, "subject": line.subject,
                    "line": line.line, "side": line.side,
                    "key": curve_key(fam, line.side), "p": round(p, 4),
                    "y": 1 if g["outcome"] == "WIN" else 0,
                    "game": f"s:{date}:{sb_id}", "ts": day_ts(date),
                    "date": date, "source": "superbet_settled"})
    return rows


# --- CS2 -------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesRow:
    event_id: int
    start_ts: int
    home_id: int
    away_id: int
    home_maps: int | None
    away_maps: int | None
    best_of: int | None


REFIT_DAYS_CS2 = 7  # the map Elo's calibration is refitted this often


def load_cs2(db_path: str, before_ts: int
             ) -> tuple[list[cs2_engine.MapRow], dict[int, SeriesRow]]:
    """The engine's map history (cs2_engine.load_history: finished maps of
    finished series, LOOKBACK_DAYS, show matches out) and each series' final
    maps and format, read-only."""
    import sqlite3

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        maps = cs2_engine.load_history(conn, before_ts, None)
        ids = {m.event_id for m in maps}
        series: dict[int, SeriesRow] = {}
        for eid, ts, h, a, hm, am, bo in conn.execute(
            "SELECT sofascore_event_id, start_ts, home_id, away_id, home_maps, "
            "away_maps, best_of FROM cs2_series WHERE status_type = 'finished' "
            "AND start_ts < ?", (before_ts,)
        ):
            if int(eid) in ids:
                series[int(eid)] = SeriesRow(int(eid), int(ts), int(h), int(a),
                                             hm, am, bo)
    finally:
        conn.close()
    return maps, series


def cs2_walk_forward_rows(maps: Sequence[cs2_engine.MapRow],
                          series: Mapping[int, SeriesRow], start_ts: int,
                          end_ts: int, source: str) -> list[Row]:
    """CS2 rows for the series in [start_ts, end_ts), each from the engine's
    state at the series' start: the map and player Elo replayed in time
    order (cs2_engine.walk_forward_players), their logistic calibration
    refitted every REFIT_DAYS_CS2 on the predictions made BEFORE the refit,
    the team's last MAX_SAMPLE maps and the base rate of every earlier map
    for the rounds. Numbers through the engine's own functions."""
    book = cs2_engine.EloBook()
    players = cs2_engine.PlayerEloBook()
    points: list[tuple[float, float]] = []
    ppoints: list[tuple[float, float]] = []
    model = cs2_engine.RatingModel(book)
    next_refit = 0
    team_rounds: dict[int, deque[int]] = defaultdict(
        lambda: deque(maxlen=cs2_engine.MAX_SAMPLE))
    all_rounds: Counter[int] = Counter()
    by_series: dict[int, list[cs2_engine.MapRow]] = {}
    for m in maps:
        by_series.setdefault(m.event_id, []).append(m)
    rows: list[Row] = []
    for eid, smaps in by_series.items():
        start = smaps[0].start_ts
        if start >= next_refit:
            model = _cs2_refit(book, players, points, ppoints)
            next_refit = start + REFIT_DAYS_CS2 * 86400
        home, away = smaps[0].home_id, smaps[0].away_id
        if start_ts <= start < end_ts:
            rows += _cs2_series_rows(eid, smaps, series.get(eid), model,
                                     team_rounds, all_rounds, source)
        if book.rated(home, away):
            d = cs2_engine.logit_diff(book, home, away)
            points.extend((d, 1.0 if m.home_won else 0.0) for m in smaps)
            gap = players.gap(home, away)
            if gap is not None:
                ppoints.extend((gap, 1.0 if m.home_won else 0.0) for m in smaps)
        for m in smaps:
            winner, loser = (m.home_id, m.away_id) if m.home_won else (m.away_id,
                                                                       m.home_id)
            book.update(winner, loser)
            players.update(m)
            if m.home_rounds is not None and m.away_rounds is not None:
                team_rounds[m.home_id].append(m.home_rounds)
                team_rounds[m.away_id].append(m.away_rounds)
                all_rounds[m.home_rounds] += 1
                all_rounds[m.away_rounds] += 1
    return rows


def counted_base_rate(values: Counter[int], line: float) -> float | None:
    """cs2_engine.base_rate over a value -> count table (the walk-forward
    keeps every earlier map's rounds as counts, not a list it re-reads)."""
    decided = sum(c for v, c in values.items() if v != line)
    if decided < cs2_engine.MIN_FIT:
        return None
    return sum(c for v, c in values.items() if v > line) / decided


def _cs2_refit(book: cs2_engine.EloBook, players: cs2_engine.PlayerEloBook,
               points: list[tuple[float, float]],
               ppoints: list[tuple[float, float]]) -> cs2_engine.RatingModel:
    """cs2_engine.build_ratings' calibration on the points so far, over the
    LIVE books (they move on after the refit; the calibration does not)."""
    if len(points) < cs2_engine.MIN_FIT:
        return cs2_engine.RatingModel(book, n_fit=len(points))
    a, b = cs2_engine.fit_logistic([x for x, _ in points], [y for _, y in points])
    model = cs2_engine.RatingModel(book, a, max(0.0, min(2.0, b)), len(points),
                                   players)
    if len(ppoints) >= cs2_engine.MIN_FIT:
        pa, pb = cs2_engine.fit_logistic([x for x, _ in ppoints],
                                         [y for _, y in ppoints])
        model.pa, model.pb, model.p_fit = pa, max(0.0, min(2.0, pb)), len(ppoints)
    return model


def _cs2_series_rows(eid: int, smaps: Sequence[cs2_engine.MapRow],
                     srow: SeriesRow | None, model: cs2_engine.RatingModel,
                     team_rounds: Mapping[int, deque[int]],
                     all_rounds: Counter[int], source: str) -> list[Row]:
    home, away = smaps[0].home_id, smaps[0].away_id
    rows: list[Row] = []

    def add(family: str, map_nr: int, subject: str, line: float | None,
            side: str, p: float, y: bool) -> None:
        rows.append({"sport": "cs2", "family": family, "market_id": None,
                     "period": map_nr, "subject": subject, "line": line,
                     "side": side, "key": curve_key(family, side),
                     "p": round(p, 4), "y": 1 if y else 0, "game": f"h:{eid}",
                     "ts": smaps[0].start_ts, "source": source})

    p_map = model.p_map(home, away, True)
    if p_map is not None:
        p = cs2_engine.clamp(p_map)
        for m in smaps:
            add("map_winner", m.order, "", None, "T1", p, m.home_won)
            add("map_winner", m.order, "", None, "T2", cs2_engine.clamp(1 - p_map),
                not m.home_won)
        if (srow is not None and srow.best_of and srow.home_maps is not None
                and srow.away_maps is not None and srow.home_maps != srow.away_maps):
            try:
                dist = cs2_engine.series_distribution(round(p_map, 6), srow.best_of)
            except ValueError:
                dist = {}
            if dist:
                p1 = sum(q for (a, b), q in dist.items() if a > b)
                p2 = sum(q for (a, b), q in dist.items() if a < b)
                won = srow.home_maps > srow.away_maps
                s1 = cs2_engine.side_given_no_push(p1, p2, True)
                s2 = cs2_engine.side_given_no_push(p1, p2, False)
                if s1 is not None and s2 is not None:
                    add("match_winner", 0, "", None, "T1", cs2_engine.clamp(s1), won)
                    add("match_winner", 0, "", None, "T2", cs2_engine.clamp(s2),
                        not won)
    for m in smaps:
        if m.home_rounds is None or m.away_rounds is None:
            continue
        for team, own, subject in ((home, m.home_rounds, "T1"),
                                   (away, m.away_rounds, "T2")):
            values = list(team_rounds.get(team, ()))
            for line in CS2_TEAM_ROUND_LINES:
                base = counted_base_rate(all_rounds, line)
                for over in (True, False):
                    mp = cs2_engine.shrunk_frequency(values, line, over, base)
                    if mp is None:
                        continue
                    add("map_team_rounds", m.order, subject, line,
                        "OVER" if over else "UNDER", mp.p,
                        (own > line) == over)
    return rows


def cs2_settled_rows(runs_dir: str, dates: Sequence[str]) -> list[Row]:
    """Settled CS2 sides with the engine's pre-match `model_p`
    (settle_cs2.attach_model), allowed families only; no price read."""
    rows: list[Row] = []
    for date in dates:
        path = Path(runs_dir) / "cs2" / date / "settled.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for sb_id, entry in (doc.get("events") or {}).items():
            for g in entry.get("graded") or []:
                if g.get("outcome") not in ("WIN", "LOSS"):
                    continue
                if g.get("family") not in CS2_FAMILIES | CS2_EXTENDED_FAMILIES \
                        or g.get("model_p") is None:
                    continue
                rows.append({
                    "sport": "cs2", "family": g["family"], "market_id": None,
                    "period": int(g.get("map_nr") or 0),
                    "subject": str(g.get("subject") or ""), "line": g.get("line"),
                    "side": str(g["side"]), "key": curve_key(g["family"], g["side"]),
                    "p": float(g["model_p"]), "y": 1 if g["outcome"] == "WIN" else 0,
                    "game": f"s:{date}:{sb_id}", "ts": day_ts(date), "date": date,
                    "source": "superbet_settled"})
    return rows


# --- F3: the sample, k of n -------------------------------------------------------

SAMPLE_GAMES = 10


@dataclass
class TeamGames:
    """Each team's finished, graded REGULAR games, oldest first."""

    by_team: dict[int, list[tuple[int, dict[str, Any]]]]

    @staticmethod
    def build(events: Iterable[dict[str, Any]], sport: ShadowSport) -> TeamGames:
        by_team: dict[int, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        for e in events:
            if parse_event(e, sport) is None:  # finished, rated, no friendly
                continue
            if match_kind(e, sport.sofascore_slug) != MatchKind.REGULAR:
                continue
            ts = int(e["startTimestamp"])
            for side in ("homeTeam", "awayTeam"):
                by_team[int(e[side]["id"])].append((ts, e))
        for games in by_team.values():
            games.sort(key=lambda x: (x[0], int(x[1]["id"])))
        return TeamGames(dict(by_team))

    def last(self, team: int, before_ts: int, n: int = SAMPLE_GAMES
             ) -> list[dict[str, Any]]:
        games = self.by_team.get(team) or []
        idx = bisect_right([ts for ts, _ in games], before_ts - 1)
        return [e for _, e in games[max(0, idx - n):idx]]


def sample_hit_rate(line: ShadowLine, sport: ShadowSport, team1_id: int,
                    team2_id: int, games: TeamGames, before_ts: int
                    ) -> tuple[int, int]:
    """(k, n): how often the leg's own line would have won over the two
    teams' last SAMPLE_GAMES league games each (a pushed game counts in
    neither). A team total reads its own team's games; a total either
    team's; a winner / handicap / 1X2 each team's games with the team on its
    own side of the line (team1's games as team1, team2's as team2). A game
    whose score does not grade is left out. Shown, never a gate."""
    spec = MARKETS[sport.key][line.market_id]
    free = spec.kind in ORIENTATION_FREE and spec.team is None
    if spec.kind == "team_total":
        teams = [(team1_id, "T1")] if line.subject == "T1" else [(team2_id, "T2")]
    else:
        teams = [(team1_id, "T1"), (team2_id, "T2")]
    seen: set[int] = set()
    k = n = 0
    for team, as_side in teams:
        for e in games.last(team, before_ts):
            if int(e["id"]) in seen:
                continue
            home_is_team = int(e["homeTeam"]["id"]) == team
            home_is_t1 = home_is_team if (as_side == "T1" or free) else not home_is_team
            result = build_result(e, sport, home_is_t1)
            if result is None:
                continue
            actual = actual_value(line, result, sport)
            if actual is None:
                continue
            outcome = grade(line, actual, spec.kind == "three_way")
            if outcome == "VOID":
                continue
            seen.add(int(e["id"]))
            n += 1
            k += outcome == "WIN"
    return k, n


def cs2_sample_hit_rate(line: Cs2Line, subject_side: str | None, team1_id: int,
                        team2_id: int, maps: Sequence[cs2_engine.MapRow],
                        series: Mapping[int, SeriesRow]) -> tuple[int, int]:
    """(k, n) for a CS2 leg over each team's last SAMPLE_GAMES maps (series
    for match_winner) in the history read: map / match winner with each team
    on its own side, a team's rounds on that team's own maps
    (`subject_side` T1 / T2 says which team the line is about). A map or a
    series of the two teams against each other counts once."""
    k = n = 0
    if line.family == "map_team_rounds":
        if subject_side not in ("T1", "T2") or line.line is None:
            return 0, 0
        team = team1_id if subject_side == "T1" else team2_id
        own_maps = [m for m in maps if team in (m.home_id, m.away_id)
                    and m.home_rounds is not None and m.away_rounds is not None]
        for m in own_maps[-SAMPLE_GAMES:]:
            own = m.home_rounds if m.home_id == team else m.away_rounds
            assert own is not None
            n += 1
            k += (own > line.line) == (line.side == "OVER")
        return k, n
    seen: set[tuple[int, int]] = set()
    for team, side in ((team1_id, "T1"), (team2_id, "T2")):
        wins_for_side = line.side == side
        if line.family == "map_winner":
            own_maps = [m for m in maps if team in (m.home_id, m.away_id)]
            for m in own_maps[-SAMPLE_GAMES:]:
                if (m.event_id, m.order) in seen:
                    continue
                seen.add((m.event_id, m.order))
                won = m.home_won == (m.home_id == team)
                n += 1
                k += won == wins_for_side
        elif line.family == "match_winner":
            done = [s for s in series.values()
                    if team in (s.home_id, s.away_id) and s.home_maps is not None
                    and s.away_maps is not None and s.home_maps != s.away_maps]
            done.sort(key=lambda s: s.start_ts)
            for s in done[-SAMPLE_GAMES:]:
                if (s.event_id, 0) in seen:
                    continue
                seen.add((s.event_id, 0))
                assert s.home_maps is not None and s.away_maps is not None
                won = (s.home_maps > s.away_maps) == (s.home_id == team)
                n += 1
                k += won == wins_for_side
    return k, n
