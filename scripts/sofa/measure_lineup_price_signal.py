"""Does Sofascore's lineup information hold something Superbet's price lacks?
Two read-only measurements (operator 2026-11-05, "Sprawdzić!"); the frozen
rules and the results are in
``docs/sofa/evidence/skladow_sygnal_2026-11-05.md``.

M1 - teammates' player lines when the side's top shooter does not start:
football ``player_shots_for`` / ``player_shots_on_target_for`` /
``player_fouls_for`` OVER legs SETTLE graded (``07_settled.json``), grouped by
whether the side's top shooter (as-of shot share over its last 10 matches)
is in the actual XI; realised minus 1/odds (one-sided, no partner),
the ABSENT - PRESENT difference, ROI before / after the 12% tax, realised
minus our confidence (``08_refusals.json``), and the price's age from
``04_offer.json`` rung ``fetched_at_utc``.

M2 - closing-line value of printed football singles (``11_coupon.json`` +
``closing.jsonl``) whose price was taken >= 75 min before kickoff, split by
market family and by the direction the actual XI's missing regulars favour.

The actual XI is the post-match lineup cached in ``sofa_event_stats`` - an
UPPER BOUND on what was knowable before kickoff;
``lineups_prematch.json`` is counted as coverage only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_lineup_price_signal.py \\
        --db-path data/sofa.db --out <result.json>

The DB is opened read-only (``mode=ro`` URI); nothing the pipeline reads is
written; no network.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sqlite3
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
from numpy.typing import NDArray  # noqa: E402

from bet.sofa.comparability import is_friendly_event  # noqa: E402
from bet.sofa.players import (  # noqa: E402
    match_player,
    match_player_by_surname,
    match_player_by_tokens,
)

M1_MARKETS: dict[str, str] = {
    "player_shots_for": "shots",
    "player_shots_on_target_for": "sot",
    "player_fouls_for": "fouls",
}
SPLIT_DATE = "2026-10-21"
M1_FROM, M2_FROM, LAST_DAY = "2026-09-24", "2026-10-05", "2026-11-04"
WINDOW = 10
MIN_HISTORY = 5
MAX_GAP_DAYS = 45
MIN_TOP_STARTS = 5
MIN_TOP_SHARE = 0.15
CORE_SHARE = 0.7
PRE_MIN = 75.0
POST_MAX = 50.0
CLOSE_MIN, CLOSE_MAX = 3.0, 30.0
TAX = 0.12
BOOT = 2000
BH_Q = 0.10

FloatArray = NDArray[np.float64]


# ---------------------------------------------------------------- pure parts


def player_shots(stats: dict[str, Any]) -> float:
    value = stats.get("totalShots")
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    parts = [stats.get(k) for k in ("onTargetScoringAttempt", "shotOffTarget",
                                    "blockedScoringAttempt")]
    return float(sum(p for p in parts
                     if isinstance(p, int | float) and not isinstance(p, bool)))


@dataclass
class SideLineup:
    """One side's lineup in one match: starters, and shots / name per player."""

    xi: frozenset[int]
    shots: dict[int, float] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)


def side_lineup(lineups: dict[str, Any] | None, side: str) -> SideLineup | None:
    block = (lineups or {}).get(side) or {}
    xi: set[int] = set()
    shots: dict[int, float] = {}
    names: dict[int, str] = {}
    for entry in block.get("players") or []:
        player = (entry or {}).get("player") or {}
        pid = player.get("id")
        if not isinstance(pid, int):
            continue
        if entry.get("substitute") is False:
            xi.add(pid)
        shots[pid] = player_shots(entry.get("statistics") or {})
        names[pid] = str(player.get("name") or "")
    if len(xi) != 11:
        return None
    return SideLineup(frozenset(xi), shots, names)


def top_shooter(history: Sequence[SideLineup]) -> tuple[int, float] | None:
    """The player with >= MIN_TOP_STARTS starts and the highest share of his
    side's shots in the matches he started; None below MIN_TOP_SHARE."""
    starts: collections.Counter[int] = collections.Counter()
    own: dict[int, float] = collections.defaultdict(float)
    team: dict[int, float] = collections.defaultdict(float)
    for rec in history:
        total = sum(rec.shots.values())
        for pid in rec.xi:
            starts[pid] += 1
            own[pid] += rec.shots.get(pid, 0.0)
            team[pid] += total
    best: tuple[int, float] | None = None
    for pid, n in sorted(starts.items()):
        if n < MIN_TOP_STARTS or team[pid] <= 0:
            continue
        share = own[pid] / team[pid]
        if best is None or share > best[1]:
            best = (pid, share)
    if best is None or best[1] < MIN_TOP_SHARE:
        return None
    return best


def core_missing(history: Sequence[SideLineup], xi: frozenset[int]) -> int:
    if not history:
        return 0
    starts: collections.Counter[int] = collections.Counter()
    for rec in history:
        starts.update(rec.xi)
    n = len(history)
    return sum(1 for pid, c in starts.items() if c / n >= CORE_SHARE and pid not in xi)


def devig(odds: float, partner: float) -> float:
    a, b = 1.0 / odds, 1.0 / partner
    return a / (a + b)


def family(market: str) -> str:
    if market.startswith("player_"):
        return "PLAYER"
    if "shots" in market:
        return "SHOTS"
    if "goals" in market:
        return "GOALS"
    return "OTHER"


def news_direction(market: str, direction: str, own_core: int | None,
                   opp_core: int | None, top_absent: bool | None) -> str:
    """M2's frozen direction of the lineup news for one leg."""
    if market.startswith("player_"):
        if top_absent is None:
            return "UNKNOWN"
        if direction == "OVER" and top_absent:
            return "FAVOURED"
        return "NEUTRAL" if not top_absent else "OTHER"
    if own_core is None:
        if opp_core is None:
            return "UNKNOWN"
        return "TOTAL_ANY_MISSING" if opp_core >= 1 else "TOTAL_NONE"
    if opp_core is None:
        return "UNKNOWN"
    if own_core == 0 and opp_core == 0:
        return "NEUTRAL"
    if own_core >= 1 and opp_core >= 1:
        return "MIXED"
    opp_weak = opp_core >= 1
    if direction == "OVER":
        return "FAVOURED" if opp_weak else "DISFAVOURED"
    if direction == "UNDER":
        return "DISFAVOURED" if opp_weak else "FAVOURED"
    return "OTHER"


def lead_minutes(kickoff: datetime, taken: datetime) -> float:
    return (kickoff - taken).total_seconds() / 60.0


def price_timing(minutes: float | None) -> str:
    if minutes is None:
        return "UNKNOWN"
    if minutes >= PRE_MIN:
        return "PRE"
    if minutes <= POST_MAX:
        return "POST"
    return "MID"


def bh(pvalues: Sequence[float], q: float = BH_Q) -> list[bool]:
    """Benjamini-Hochberg rejections, in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    cut = -1
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= q * rank / m:
            cut = rank
    reject = [False] * m
    for rank, i in enumerate(order, start=1):
        if rank <= cut:
            reject[i] = True
    return reject


Row = dict[str, Any]


@dataclass(frozen=True)
class Mean:
    """Mean of ``key`` over the rows ``where`` accepts (None values skipped)."""

    key: str
    where: Callable[[Row], bool] | None = None

    def accepts(self, r: Row) -> bool:
        return r.get(self.key) is not None and (self.where is None or self.where(r))

    def __call__(self, rows: list[Row]) -> float | None:
        vals = [float(r[self.key]) for r in rows if self.accepts(r)]
        return sum(vals) / len(vals) if vals else None


@dataclass(frozen=True)
class Diff:
    a: Mean
    b: Mean

    def __call__(self, rows: list[Row]) -> float | None:
        x, y = self.a(rows), self.b(rows)
        return None if x is None or y is None else x - y


Stat = Mean | Diff


def mean_of(key: str, where: Callable[[Row], bool] | None = None) -> Mean:
    return Mean(key, where)


def diff_of(a: Mean, b: Mean) -> Diff:
    return Diff(a, b)


def _match_sums(rows: list[Row], m: Mean, index: dict[int, int]
                ) -> tuple[FloatArray, FloatArray]:
    s = np.zeros(len(index))
    n = np.zeros(len(index))
    for r in rows:
        if m.accepts(r):
            i = index[int(r["event"])]
            s[i] += float(r[m.key])
            n[i] += 1.0
    return s, n


def bootstrap(rows: list[Row], stat: Stat, reps: int = BOOT,
              seed: int = 20261105) -> dict[str, Any]:
    """Point, 95% percentile interval and one-sided p (share of resamples
    <= 0), resampling whole matches (``event`` key)."""
    point = stat(rows)
    index: dict[int, int] = {}
    for r in rows:
        index.setdefault(int(r["event"]), len(index))
    out: dict[str, Any] = {"point": point, "lo": None, "hi": None, "p": None,
                           "n": len(rows), "matches": len(index)}
    if point is None or len(index) < 2:
        return out
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(index), size=(reps, len(index)))

    def means(m: Mean) -> FloatArray:
        s, n = _match_sums(rows, m, index)
        ss, nn = s[draw].sum(axis=1), n[draw].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            res: FloatArray = np.where(nn > 0, ss / np.maximum(nn, 1.0), np.nan)
        return res

    vals = means(stat) if isinstance(stat, Mean) else means(stat.a) - means(stat.b)
    vals = vals[~np.isnan(vals)]
    if vals.size == 0:
        return out
    out["lo"] = float(np.percentile(vals, 2.5))
    out["hi"] = float(np.percentile(vals, 97.5))
    out["p"] = float((vals <= 0).mean())
    return out


def leg_metrics(r: Row) -> Row:
    """Per-leg numbers every summary averages."""
    win = 1.0 if r["outcome"] == "WIN" else 0.0
    odds = float(r["odds"])
    out = dict(r)
    out["win"] = win
    out["implied"] = 1.0 / odds
    out["res_minus_implied"] = win - 1.0 / odds
    out["roi"] = win * odds - 1.0
    out["roi_tax"] = win * odds * (1.0 - TAX) - 1.0
    conf = r.get("confidence")
    out["res_minus_conf"] = None if conf is None else win - float(conf)
    fair = r.get("fair_p")
    out["res_minus_fair"] = None if fair is None else win - float(fair)
    return out


def summarise(rows: list[Row], reps: int = BOOT) -> dict[str, Any]:
    days = {r["day"] for r in rows}
    return {
        "legs": len(rows), "matches": len({r["event"] for r in rows}),
        "days": len(days),
        "hit": mean_of("win")(rows), "implied": mean_of("implied")(rows),
        "res_minus_implied": bootstrap(rows, mean_of("res_minus_implied"), reps),
        "res_minus_fair": bootstrap(rows, mean_of("res_minus_fair"), reps),
        "roi": bootstrap(rows, mean_of("roi"), reps),
        "roi_tax": bootstrap(rows, mean_of("roi_tax"), reps),
        "res_minus_conf": bootstrap(rows, mean_of("res_minus_conf"), reps),
        "conf_legs": sum(1 for r in rows if r.get("confidence") is not None),
    }


# ---------------------------------------------------------------- data


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _days(runs: Path, first: str, last: str) -> list[str]:
    return sorted(p.name for p in runs.iterdir()
                  if p.is_dir() and len(p.name) == 10 and first <= p.name <= last)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


class Cache:
    """Read-only DB access with per-event caches."""

    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self._events: dict[int, dict[str, Any] | None] = {}
        self._lineups: dict[int, dict[str, SideLineup | None] | None] = {}
        self._listing: dict[int, list[tuple[int, int]]] = {}
        self._history: dict[tuple[int, int], list[SideLineup] | None] = {}

    def event(self, eid: int) -> dict[str, Any] | None:
        if eid not in self._events:
            row = self.conn.execute(
                "SELECT event_json FROM sofa_listed_event WHERE event_id = ?",
                (eid,)).fetchone()
            if row is None:
                row = self.conn.execute(
                    "SELECT detail_json FROM sofa_event_detail "
                    "WHERE sofascore_event_id = ?", (eid,)).fetchone()
            ev: dict[str, Any] | None = None
            if row is not None:
                try:
                    raw = json.loads(row[0])
                except ValueError:
                    raw = None
                if isinstance(raw, dict):
                    ev = raw.get("event") if isinstance(raw.get("event"), dict) else raw
            self._events[eid] = ev
        return self._events[eid]

    def lineups(self, eid: int) -> dict[str, SideLineup | None] | None:
        if eid not in self._lineups:
            row = self.conn.execute(
                "SELECT lineups_json FROM sofa_event_stats "
                "WHERE sofascore_event_id = ?", (eid,)).fetchone()
            parsed: dict[str, SideLineup | None] | None = None
            if row is not None and row[0]:
                try:
                    raw = json.loads(row[0])
                except ValueError:
                    raw = None
                if isinstance(raw, dict):
                    parsed = {s: side_lineup(raw, s) for s in ("home", "away")}
            self._lineups[eid] = parsed
        return self._lineups[eid]

    def listing(self, team: int) -> list[tuple[int, int]]:
        if team not in self._listing:
            rows = self.conn.execute(
                "SELECT DISTINCT event_id, start_ts FROM sofa_listing_event "
                "WHERE entity_id = ? AND start_ts IS NOT NULL ORDER BY start_ts",
                (team,)).fetchall()
            self._listing[team] = [(int(e), int(t)) for e, t in rows]
        return self._listing[team]

    def history(self, team: int, kickoff_ts: int) -> list[SideLineup] | None:
        key = (team, kickoff_ts)
        if key in self._history:
            return self._history[key]
        out: list[SideLineup] = []
        for eid, ts in reversed(self.listing(team)):
            if len(out) >= WINDOW:
                break
            if ts >= kickoff_ts or kickoff_ts - ts > 365 * 86400:
                continue
            ev = self.event(eid)
            if ev is None or (ev.get("status") or {}).get("type") != "finished":
                continue
            if is_friendly_event(ev, "football"):
                continue
            side = None
            for s in ("home", "away"):
                if ((ev.get(f"{s}Team") or {}).get("id")) == team:
                    side = s
            lu = self.lineups(eid)
            if side is None or lu is None or lu.get(side) is None:
                continue
            rec = lu[side]
            assert rec is not None
            if not out:
                if kickoff_ts - ts > MAX_GAP_DAYS * 86400:
                    break
            out.append(rec)
        result = out if len(out) >= MIN_HISTORY else None
        self._history[key] = result
        return result

    def side_info(self, eid: int) -> dict[str, Any] | None:
        """Per side: team id, name, actual XI, T, T absent, core missing."""
        ev = self.event(eid)
        lu = self.lineups(eid)
        if ev is None or lu is None or not isinstance(ev.get("startTimestamp"), int):
            return None
        kickoff = int(ev["startTimestamp"])
        out: dict[str, Any] = {"kickoff": kickoff}
        for s in ("home", "away"):
            team = (ev.get(f"{s}Team") or {})
            tid = team.get("id")
            today = lu.get(s)
            info: dict[str, Any] = {"team": tid, "name": str(team.get("name") or ""),
                                    "lineup": today, "top": None, "top_absent": None,
                                    "core_missing": None}
            if isinstance(tid, int) and today is not None:
                hist = self.history(tid, kickoff)
                if hist is not None:
                    top = top_shooter(hist)
                    info["core_missing"] = core_missing(hist, today.xi)
                    if top is not None:
                        info["top"] = top[0]
                        info["top_absent"] = top[0] not in today.xi
            out[s] = info
        return out


def find_player(name: str, info: dict[str, Any]) -> tuple[str, int] | None:
    """(side, player id) of a Superbet name among both sides' starters;
    None when missing or found on both sides."""
    hits: list[tuple[str, int]] = []
    for s in ("home", "away"):
        lu: SideLineup | None = info[s]["lineup"]
        if lu is None:
            continue
        cands = {lu.names[pid]: {"id": pid} for pid in lu.xi if lu.names.get(pid)}
        got = (match_player(name, cands) or match_player_by_tokens(name, cands)
               or match_player_by_surname(name, cands))
        if got is not None:
            hits.append((s, int(cands[got]["id"])))
    return hits[0] if len(hits) == 1 else None


def offer_rungs(day_dir: Path) -> dict[tuple[int, str, str, float], dict[str, Any]]:
    data = _load_json(day_dir / "04_offer.json")
    out: dict[tuple[int, str, str, float], dict[str, Any]] = {}
    for fx in data if isinstance(data, list) else []:
        eid = fx.get("sofascore_event_id")
        for r in fx.get("rungs") or []:
            try:
                out[(int(eid), str(r["market"]), str(r.get("subject") or ""),
                     float(r["line"]))] = r
            except (KeyError, TypeError, ValueError):
                continue
    return out


def refusal_confidence(day_dir: Path) -> dict[tuple[int, str, str, float, str], float]:
    data = _load_json(day_dir / "08_refusals.json")
    out: dict[tuple[int, str, str, float, str], float] = {}
    if not isinstance(data, dict):
        return out
    cols = data.get("columns") or []
    events = data.get("events") or []
    try:
        ix = {c: cols.index(c) for c in ("event", "market", "subject", "line",
                                         "direction", "confidence")}
    except ValueError:
        return out
    for row in data.get("rows") or []:
        conf = row[ix["confidence"]]
        if conf is None:
            continue
        try:
            eid = int(events[row[ix["event"]]]["sofascore_event_id"])
            out[(eid, str(row[ix["market"]]), str(row[ix["subject"]] or ""),
                 float(row[ix["line"]]), str(row[ix["direction"]]))] = float(conf)
        except (IndexError, KeyError, TypeError, ValueError):
            continue
    return out


def prematch_confirmed(runs: Path) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for day in _days(runs, "2026-10-23", LAST_DAY):
        data = _load_json(runs / day / "lineups_prematch.json")
        for eid, rec in ((data or {}).get("events") or {}).items():
            if isinstance(rec, dict) and rec.get("status") == "OK":
                out[int(eid)] = rec
    return out


# ---------------------------------------------------------------- M1


def collect_m1(runs: Path, cache: Cache, counts: collections.Counter[str],
               prematch: dict[int, dict[str, Any]]) -> list[Row]:
    rows: list[Row] = []
    seen: set[tuple[Any, ...]] = set()
    for day in _days(runs, M1_FROM, LAST_DAY):
        settled = _load_json(runs / day / "07_settled.json")
        if not isinstance(settled, list):
            continue
        legs = [r for r in settled if r.get("market") in M1_MARKETS
                and r.get("direction") == "OVER" and r.get("outcome") in ("WIN", "LOSS")
                and isinstance(r.get("offered_odds"), int | float)
                and r["offered_odds"] > 1]
        if not legs:
            continue
        rungs = offer_rungs(runs / day)
        conf = refusal_confidence(runs / day)
        print(f"  M1 {day}: {len(legs)} legs", file=sys.stderr, flush=True)
        for r in legs:
            eid = int(r["sofascore_event_id"])
            key = (eid, r["market"], r["subject"], float(r["line"]), "OVER")
            if key in seen:
                counts["m1_duplicate"] += 1
                continue
            seen.add(key)
            info = cache.side_info(eid)
            if info is None:
                counts["m1_no_event_or_lineup"] += 1
                continue
            hit = find_player(str(r["subject"]), info)
            if hit is None:
                counts["m1_player_unmatched"] += 1
                continue
            side, pid = hit
            si = info[side]
            if si["top"] is None:
                counts["m1_side_without_top"] += 1
                continue
            if pid == si["top"]:
                counts["m1_top_own_leg"] += 1
                continue
            rung = rungs.get((eid, r["market"], str(r["subject"]), float(r["line"])))
            minutes = None
            if rung and rung.get("fetched_at_utc") \
                    and rung.get("over_odds") == r["offered_odds"]:
                fetched = _ts(rung["fetched_at_utc"]).timestamp()
                minutes = (info["kickoff"] - fetched) / 60
            pm = prematch.get(eid)
            rows.append(leg_metrics({
                "day": day, "event": eid, "fam": M1_MARKETS[r["market"]],
                "group": "ABSENT" if si["top_absent"] else "PRESENT",
                "half": "dev" if day < SPLIT_DATE else "hold",
                "odds": float(r["offered_odds"]), "outcome": r["outcome"],
                "line": float(r["line"]),
                "confidence": conf.get(key), "timing": price_timing(minutes),
                "prematch_confirmed": bool(pm and pm.get("confirmed")),
            }))
            counts["m1_rows"] += 1
    return rows


def analyse_m1(rows: list[Row], reps: int) -> dict[str, Any]:
    out: dict[str, Any] = {"cells": {}, "did": {}}
    absent = mean_of("res_minus_implied", lambda r: r["group"] == "ABSENT")
    present = mean_of("res_minus_implied", lambda r: r["group"] == "PRESENT")
    for half in ("dev", "hold"):
        for fam in ("shots", "sot", "fouls"):
            sub = [r for r in rows if r["half"] == half and r["fam"] == fam]
            for grp in ("ABSENT", "PRESENT"):
                cell = [r for r in sub if r["group"] == grp]
                out["cells"][f"{half}|{fam}|{grp}"] = summarise(cell, reps)
                post = [r for r in cell if r["timing"] == "POST"]
                out["cells"][f"{half}|{fam}|{grp}|POST"] = summarise(post, reps)
            out["did"][f"{half}|{fam}"] = bootstrap(sub, diff_of(absent, present), reps)
            post = [r for r in sub if r["timing"] == "POST"]
            out["did"][f"{half}|{fam}|POST"] = bootstrap(post, diff_of(absent, present),
                                                         reps)
    keys = [f"hold|{f}" for f in ("shots", "sot", "fouls")]
    ps = [out["did"][k]["p"] if out["did"][k]["p"] is not None else 1.0 for k in keys]
    out["bh_hold_did"] = dict(zip(keys, bh(ps), strict=True))
    out["timing"] = dict(collections.Counter(r["timing"] for r in rows))
    out["prematch_confirmed_legs"] = sum(1 for r in rows if r["prematch_confirmed"])
    out["prematch_confirmed_absent_legs"] = sum(
        1 for r in rows if r["prematch_confirmed"] and r["group"] == "ABSENT")
    return out


# ---------------------------------------------------------------- M2


def _leg_key(x: dict[str, Any]) -> str:
    return (f"{x['sofascore_event_id']}|{x['market']}|{x.get('subject') or ''}"
            f"|{x['line']}|{x['direction']}")


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def collect_m2(runs: Path, cache: Cache, counts: collections.Counter[str],
               prematch: dict[int, dict[str, Any]]) -> list[Row]:
    rows: list[Row] = []
    for day in _days(runs, M2_FROM, LAST_DAY):
        coupon = _load_json(runs / day / "11_coupon.json")
        if not isinstance(coupon, dict):
            continue
        singles = {_leg_key(x): x for x in coupon.get("singles") or []
                   if x.get("sport") == "football"}
        closes: dict[str, dict[str, Any]] = {}
        try:
            with (runs / day / "closing.jsonl").open() as fh:
                for line in fh:
                    rec = json.loads(line)
                    if rec.get("leg_key") not in singles:
                        continue
                    mb = rec.get("minutes_before")
                    if not (isinstance(mb, int | float)
                            and CLOSE_MIN <= mb <= CLOSE_MAX):
                        continue
                    oc, pc = rec.get("odds_close"), rec.get("partner_close")
                    if not (isinstance(oc, int | float) and oc > 1
                            and isinstance(pc, int | float) and pc > 1):
                        continue
                    old = closes.get(rec["leg_key"])
                    if old is None or mb <= old["minutes_before"]:
                        closes[rec["leg_key"]] = rec
        except OSError:
            continue
        settled = _load_json(runs / day / "07_settled.json")
        outcome = {(int(r["sofascore_event_id"]), r["market"],
                    str(r.get("subject") or ""), float(r["line"]),
                    r["direction"]): r["outcome"]
                   for r in settled or [] if r.get("outcome") in ("WIN", "LOSS")}
        rungs = offer_rungs(runs / day)
        print(f"  M2 {day}: {len(closes)} closed singles", file=sys.stderr, flush=True)
        for key, rec in closes.items():
            x = singles[key]
            eid = int(x["sofascore_event_id"])
            subject = str(x.get("subject") or "")
            kickoff = _ts(x["kickoff_utc"])
            taken = float(rec["odds_taken"])
            rung = rungs.get((eid, x["market"], subject, float(x["line"])))
            rung_odds = None
            fair_taken = None
            if rung:
                mine, other = (("over_odds", "under_odds") if x["direction"] == "OVER"
                               else ("under_odds", "over_odds"))
                rung_odds = rung.get(mine)
                if rung_odds == taken and isinstance(rung.get(other), int | float) \
                        and rung[other] > 1:
                    fair_taken = devig(taken, float(rung[other]))
            t0 = None
            if x.get("printed_at_utc"):
                t0 = _ts(x["printed_at_utc"])
            elif rung and rung_odds == taken and rung.get("fetched_at_utc"):
                t0 = _ts(rung["fetched_at_utc"])
            if t0 is None:
                counts["m2_no_taken_time"] += 1
                continue
            timing = price_timing(lead_minutes(kickoff, t0))
            counts[f"m2_timing_{timing}"] += 1
            if timing != "PRE":
                continue
            info = cache.side_info(eid)
            if info is None:
                counts["m2_no_event_or_lineup"] += 1
                continue
            side = None
            if subject and not x["market"].startswith("player_"):
                for s in ("home", "away"):
                    if _norm(info[s]["name"]) == _norm(subject):
                        side = s
                if side is None:
                    parts = str(x.get("match") or "").split(" - ")
                    if len(parts) == 2:
                        for s, nm in (("home", parts[0]), ("away", parts[1])):
                            if _norm(nm) == _norm(subject):
                                side = s
            top_absent: bool | None = None
            own_core: int | None = None
            opp_core: int | None = None
            if x["market"].startswith("player_"):
                hit = find_player(subject, info)
                if hit is not None and info[hit[0]]["top"] is not None \
                        and hit[1] != info[hit[0]]["top"]:
                    top_absent = bool(info[hit[0]]["top_absent"])
            elif side is not None:
                other = "away" if side == "home" else "home"
                own_core = info[side]["core_missing"]
                opp_core = info[other]["core_missing"]
            elif subject and x["market"].endswith("_for"):
                counts["m2_side_unmatched"] += 1
                continue
            else:
                hc, ac = info["home"]["core_missing"], info["away"]["core_missing"]
                opp_core = None if hc is None or ac is None else max(hc, ac)
            news = news_direction(x["market"], x["direction"], own_core, opp_core,
                                  top_absent)
            res = outcome.get((eid, x["market"], subject, float(x["line"]),
                               x["direction"]))
            fair_close = devig(float(rec["odds_close"]), float(rec["partner_close"]))
            pm = prematch.get(eid)
            row: Row = {
                "day": day, "event": eid, "fam": family(x["market"]), "news": news,
                "half": "dev" if day < SPLIT_DATE else "hold",
                "odds": taken, "outcome": res or "PENDING",
                "clv": taken * fair_close - 1.0,
                "clv_raw": taken / float(rec["odds_close"]) - 1.0,
                "moved": float(rec["odds_close"]) != taken,
                "confidence": x.get("confidence"), "fair_p": fair_taken,
                "prematch_confirmed": bool(pm and pm.get("confirmed")),
            }
            rows.append(leg_metrics(row) if res else {**row, "win": None})
            counts["m2_rows"] += 1
    return rows


def analyse_m2(rows: list[Row], reps: int) -> dict[str, Any]:
    out: dict[str, Any] = {"cells": {}, "diff": {}}
    fav = mean_of("clv", lambda r: r["news"] == "FAVOURED")
    neu = mean_of("clv", lambda r: r["news"] == "NEUTRAL")
    anym = mean_of("clv", lambda r: r["news"] == "TOTAL_ANY_MISSING")
    none = mean_of("clv", lambda r: r["news"] == "TOTAL_NONE")
    for half in ("dev", "hold"):
        for fam in ("PLAYER", "SHOTS", "GOALS", "OTHER"):
            sub = [r for r in rows if r["half"] == half and r["fam"] == fam]
            for news in ("FAVOURED", "NEUTRAL", "DISFAVOURED", "MIXED",
                         "TOTAL_ANY_MISSING", "TOTAL_NONE", "UNKNOWN", "OTHER"):
                cell = [r for r in sub if r["news"] == news]
                if not cell:
                    continue
                graded = [r for r in cell if r.get("win") is not None]
                out["cells"][f"{half}|{fam}|{news}"] = {
                    "clv": bootstrap(cell, mean_of("clv"), reps),
                    "clv_raw_mean": mean_of("clv_raw")(cell),
                    "moved_share": (sum(1 for r in cell if r["moved"]) / len(cell)),
                    "days": len({r["day"] for r in cell}),
                    **{k: v for k, v in summarise(graded, reps).items()
                       if k not in ("legs", "matches", "days")},
                    "graded": len(graded),
                }
            out["diff"][f"{half}|{fam}|FAV-NEU"] = bootstrap(sub, diff_of(fav, neu),
                                                             reps)
            out["diff"][f"{half}|{fam}|ANY-NONE"] = bootstrap(sub, diff_of(anym, none),
                                                              reps)
    keys = [k for k in out["diff"] if k.startswith("hold|")
            and out["diff"][k]["point"] is not None]
    ps = [out["diff"][k]["p"] if out["diff"][k]["p"] is not None else 1.0 for k in keys]
    out["bh_hold"] = dict(zip(keys, bh(ps), strict=True))
    out["prematch_confirmed_legs"] = sum(1 for r in rows if r["prematch_confirmed"])
    out["prematch_confirmed_matches"] = len({r["event"] for r in rows
                                             if r["prematch_confirmed"]})
    return out


def _clean(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", type=Path, default=_REPO / "data" / "sofa.db")
    ap.add_argument("--runs", type=Path, default=_REPO / "runs" / "sofa")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=BOOT)
    ap.add_argument("--only", choices=("m1", "m2"), default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    counts: collections.Counter[str] = collections.Counter()
    cache = Cache(args.db_path)
    prematch = prematch_confirmed(args.runs)
    result: dict[str, Any] = {"split": SPLIT_DATE, "counts": counts}
    if args.only in (None, "m1"):
        m1 = collect_m1(args.runs, cache, counts, prematch)
        result["m1"] = analyse_m1(m1, args.reps)
    if args.only in (None, "m2"):
        m2 = collect_m2(args.runs, cache, counts, prematch)
        result["m2"] = analyse_m2(m2, args.reps)
    result["counts"] = dict(counts)
    args.out.write_text(json.dumps(_clean(result), indent=1, sort_keys=True))
    print(json.dumps(dict(counts), indent=1), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
