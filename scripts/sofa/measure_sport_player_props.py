#!/usr/bin/env python3
"""Hockey / basketball player lines: does the player model's sample size
predict its calibration error, and does a no-curve key's p bucket realise
differently by Superbet's price band (read-only evidence, never a gate).

Pre-registered in docs/sofa/evidence/sport_player_props_2026-10-13.md.

Q1  per settled pre-game player line with model_p >= 0.70: gap = y - p;
    K1 = gap(n_team < 10) - gap(n_team >= 10), K2 = gap(moved) - gap(rest),
    n_team = model_n (games in the two teams' listings), n_all / n_other =
    the player's appearances in 365 days before the kickoff (any team; the
    lineups in data/sofa.db, opened mode=ro), moved = n_other >= 10 and
    n_team < 20.
Q2  M2 = Cochran-Mantel-Haenszel-style difference of the realised rate in
    the price band >= 1.30 minus 1.00-1.30 inside (sport, key, p bucket)
    strata of no-curve keys (player lines; the four sports' other no-curve
    keys from --rows-dir as a secondary population).
W   walk-forward: the line evidence fitted on the days before each test day
    (le.fit on player rows + fit_line_evidence.sport_rows), the test day's
    lines read as SPORT_CONFIDENCE reads them (v2, bucket design effect) -
    current rule, R1 (n_team < 10 -> no p), R2 (band cells widened downward
    only, never into higher-p buckets).

Every interval: bootstrap over games, 2000 resamples, seed 0, percentile 95%.

Usage:
  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_player_props.py \
      [--from 2026-09-29] [--to 2026-10-12] [--first-test 2026-10-02] \
      [--rows-dir data/line_evidence/rows_before_2026-10-13] \
      [--skip-db] [--skip-walk] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.sofa import line_evidence as le
from bet.sofa import sport_confidence as scf
from bet.sofa.comparability import is_friendly_event
from bet.sofa.config import SofaConfig
from bet.sofa.shadow import has_played

SPORTS = ("hockey", "basketball")
SLUG = {"hockey": "ice-hockey", "basketball": "basketball"}
FLOOR = 0.70
MIN_X = 0.90
MAX_MARGIN = 0.15
BOOT = 2000
SEED = 0
THIN_TEAM = 10
MOVED_OTHER = 10
MOVED_TEAM = 20
HI_BAND_FROM = 1.30
WINDOW_DAYS = 365
MISLABELLED = 5
MIN_THIN_LINES = 100
MIN_GAMES = 30
N_TEAM_BINS = ((5, 9), (10, 19), (20, 39), (40, 60))
VARIANTS = ("current", "R1", "R2")

Line = dict[str, Any]


# --- data ------------------------------------------------------------------------

def _ts(raw: object) -> int:
    return int(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp())


def player_line(sport: str, day: str, eid: str, g: Mapping[str, Any]) -> Line | None:
    """One graded side of a settled.json as a measured line, or None when it
    is not a pre-game player number graded WIN / LOSS with a price."""
    if not str(g.get("family", "")).startswith("player_") \
            or g.get("model_source") != "pregame" or g.get("model_p") is None \
            or g.get("outcome") not in ("WIN", "LOSS") or not g.get("odds"):
        return None
    return {"sport": sport, "day": day, "game": f"s:{day}:{eid}",
            "key": scf.curve_key(str(g["family"]), str(g["side"])),
            "p": float(g["model_p"]), "y": 1 if g["outcome"] == "WIN" else 0,
            "odds": float(g["odds"]),
            "overround": None if g.get("overround") is None
            else float(g["overround"]),
            "n_team": int(g.get("model_n") or 0),
            "player_id": g.get("model_player_id"),
            "kickoff_ts": None, "base": None, "kind": "player"}


def load_player_lines(runs_dir: Path, start: str, end: str) -> list[Line]:
    out: list[Line] = []
    for sport in SPORTS:
        root = runs_dir / "shadow" / sport
        if not root.exists():
            continue
        for day_dir in sorted(root.iterdir()):
            day = day_dir.name
            path = day_dir / "settled.json"
            if len(day) != 10 or not (start <= day <= end) or not path.exists():
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            for eid, ev in (doc.get("events") or {}).items():
                kick = ev.get("sofascore_start_utc") or ev.get("kickoff_utc")
                for g in ev.get("graded") or []:
                    row = player_line(sport, day, str(eid), g)
                    if row is not None:
                        row["kickoff_ts"] = _ts(kick) if kick else None
                        out.append(row)
    return out


def appearances_in(lineups: Mapping[str, Any], wanted: set[int],
                   home_id: int | None, away_id: int | None
                   ) -> list[tuple[int, int, int | None]]:
    """(player id, team he played for, the entry's `teamId`) of every wanted
    player who played (has_played). The team is read from the side (home /
    away) of the event: the entry's `teamId` is the player's team when the
    box was fetched (a player traded since carries his new team's id in his
    old team's games - measured 2026-10-13), so it is kept apart."""
    out: list[tuple[int, int, int | None]] = []
    for side, team in (("home", home_id), ("away", away_id)):
        if team is None:
            continue
        for entry in (lineups.get(side) or {}).get("players") or []:
            if not isinstance(entry, dict):
                continue
            player, stats = entry.get("player"), entry.get("statistics")
            if not isinstance(player, dict) or not isinstance(stats, dict):
                continue
            pid, tid = player.get("id"), entry.get("teamId")
            if pid in wanted and has_played(stats):
                out.append((int(pid), int(team), tid if isinstance(tid, int) else None))
    return out


def side_ids(event: Mapping[str, Any]) -> tuple[int | None, int | None]:
    ids = []
    for side in ("homeTeam", "awayTeam"):
        team = event.get(side)
        tid = team.get("id") if isinstance(team, dict) else None
        ids.append(tid if isinstance(tid, int) else None)
    return ids[0], ids[1]


def scan_appearances(conn: sqlite3.Connection, slug: str, wanted: set[int],
                     lo_ts: int, hi_ts: int
                     ) -> dict[int, list[tuple[int, int, int | None]]]:
    """player id -> [(start ts, team played for, entry teamId)] over the
    sport's stored lineups, friendlies (comparability.is_friendly_event) left
    out."""
    out: dict[int, list[tuple[int, int, int | None]]] = defaultdict(list)
    cur = conn.execute(
        "SELECT l.start_ts, l.event_json, s.lineups_json FROM sofa_listed_event l "
        "JOIN sofa_event_stats s ON s.sofascore_event_id = l.event_id "
        "WHERE l.sport = ? AND l.start_ts >= ? AND l.start_ts < ? "
        "AND s.lineups_json IS NOT NULL", (slug, lo_ts, hi_ts))
    for ts, event_json, lineups_json in cur:
        try:
            event = json.loads(event_json)
            if not isinstance(event, dict) or is_friendly_event(event, slug):
                continue
            lineups = json.loads(lineups_json)
        except ValueError:
            continue
        if isinstance(lineups, dict):
            home, away = side_ids(event)
            for pid, team, tid in appearances_in(lineups, wanted, home, away):
                out[pid].append((int(ts), team, tid))
    return out


def career_counts(apps: Sequence[tuple[int, int, int | None]], kickoff_ts: int,
                  window_days: int = WINDOW_DAYS) -> tuple[int, int, int]:
    """(n_all, n_other, n_mislabelled): appearances in the window before the
    kickoff, those for a team other than the one of his newest appearance,
    and those whose entry `teamId` is not the team he played for."""
    lo = kickoff_ts - window_days * 86400
    inside = sorted((ts, t, tid) for ts, t, tid in apps if lo <= ts < kickoff_ts)
    if not inside:
        return 0, 0, 0
    current = inside[-1][1]
    return (len(inside), sum(1 for _, t, _ in inside if t != current),
            sum(1 for _, t, tid in inside if tid is not None and tid != t))


def is_moved(n_team: int, n_other: int | None) -> bool:
    return n_other is not None and n_other >= MOVED_OTHER and n_team < MOVED_TEAM


# --- bootstrap ---------------------------------------------------------------------

def _resamples(games: Sequence[str], reps: int, seed: int) -> list[list[str]]:
    rng = random.Random(seed)
    return [[games[rng.randrange(len(games))] for _ in games] for _ in range(reps)]


def _ci(values: list[float]) -> list[float]:
    values = sorted(values)
    n = len(values)
    return [values[int(0.025 * n)], values[int(0.975 * n) - 1]]


def boot_contrast(items: Sequence[tuple[str, bool, float]], reps: int = BOOT,
                  seed: int = SEED) -> dict[str, Any]:
    """items (game, in group A, value): mean A, mean B and A - B with
    intervals; games resampled whole."""
    per: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for g, a, v in items:
        s = per[g]
        if a:
            s[0] += v
            s[1] += 1
        else:
            s[2] += v
            s[3] += 1
    games = sorted(per)
    na = sum(per[g][1] for g in games)
    nb = sum(per[g][3] for g in games)
    out: dict[str, Any] = {
        "a_lines": int(na), "a_games": sum(1 for g in games if per[g][1]),
        "b_lines": int(nb), "b_games": sum(1 for g in games if per[g][3])}
    if not games or not na or not nb:
        return out

    def stat(sample: Iterable[str]) -> tuple[float, float] | None:
        sa = ca = sb = cb = 0.0
        for g in sample:
            s = per[g]
            sa += s[0]
            ca += s[1]
            sb += s[2]
            cb += s[3]
        if not ca or not cb:
            return None
        return sa / ca, sb / cb

    point = stat(games)
    assert point is not None
    ma, mb, diffs = [], [], []
    for sample in _resamples(games, reps, seed):
        got = stat(sample)
        if got is None:
            continue
        ma.append(got[0])
        mb.append(got[1])
        diffs.append(got[0] - got[1])
    out.update({"a": round(point[0], 4), "a_ci": [round(x, 4) for x in _ci(ma)],
                "b": round(point[1], 4), "b_ci": [round(x, 4) for x in _ci(mb)],
                "diff": round(point[0] - point[1], 4),
                "diff_ci": [round(x, 4) for x in _ci(diffs)]})
    return out


def boot_mean(items: Sequence[tuple[str, float]], reps: int = BOOT,
              seed: int = SEED) -> dict[str, Any]:
    """items (game, value): the mean with its interval."""
    per: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for g, v in items:
        per[g][0] += v
        per[g][1] += 1
    games = sorted(per)
    if not games:
        return {"lines": 0, "games": 0, "mean": None, "ci": None}

    def stat(sample: Iterable[str]) -> float:
        s = c = 0.0
        for g in sample:
            s += per[g][0]
            c += per[g][1]
        return s / c

    means = [stat(s) for s in _resamples(games, reps, seed)]
    return {"lines": len(items), "games": len(games), "mean": round(stat(games), 4),
            "ci": [round(x, 4) for x in _ci(means)]}


def cmh_difference(items: Sequence[tuple[str, str, bool, int]], reps: int = BOOT,
                   seed: int = SEED) -> dict[str, Any]:
    """items (game, stratum, high band, y): sum_s w_s (rate_hi - rate_lo) /
    sum_s w_s, w_s = n_lo n_hi / (n_lo + n_hi), strata with both groups."""
    per: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0, 0, 0]))
    for g, s, hi, y in items:
        cell = per[g][s]
        if hi:
            cell[2] += 1
            cell[3] += y
        else:
            cell[0] += 1
            cell[1] += y
    games = sorted(per)

    def stat(sample: Iterable[str]) -> tuple[float, int, int, int] | None:
        tot: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
        for g in sample:
            for s, c in per[g].items():
                t = tot[s]
                for i in range(4):
                    t[i] += c[i]
        num = den = 0.0
        strata = n_lo = n_hi = 0
        for n0, k0, n1, k1 in tot.values():
            if n0 and n1:
                w = n0 * n1 / (n0 + n1)
                num += w * (k1 / n1 - k0 / n0)
                den += w
                strata += 1
                n_lo += n0
                n_hi += n1
        return None if not den else (num / den, strata, n_lo, n_hi)

    point = stat(games)
    if point is None:
        return {"strata": 0}
    hi_games = sum(1 for g in games if any(c[2] for c in per[g].values()))
    diffs = [got[0] for got in (stat(s) for s in _resamples(games, reps, seed))
             if got is not None]
    return {"diff": round(point[0], 4), "diff_ci": [round(x, 4) for x in _ci(diffs)],
            "strata": point[1], "lo_lines": point[2], "hi_lines": point[3],
            "games": len(games), "hi_games": hi_games}


def boot_legs(legs: Sequence[tuple[str, float, int, float]], reps: int = BOOT,
              seed: int = SEED) -> dict[str, Any]:
    """legs (game, confidence, y, odds): confidence, realised, gap and ROI."""
    if not legs:
        return {"legs": 0, "games": 0}
    gap = boot_mean([(g, y - c) for g, c, y, _ in legs], reps, seed)
    roi = boot_mean([(g, y * o - 1.0) for g, _, y, o in legs], reps, seed)
    n = len(legs)
    return {"legs": n, "games": gap["games"],
            "confidence": round(sum(c for _, c, _, _ in legs) / n, 4),
            "realised": round(sum(y for _, _, y, _ in legs) / n, 4),
            "gap": gap["mean"], "gap_ci": gap["ci"],
            "roi": roi["mean"], "roi_ci": roi["ci"]}


# --- R2: band cells widened downward only -------------------------------------------

def pooled(cells: Mapping[str, Mapping[str, Any]], lo_edge: float, hi_edge: float
           ) -> tuple[int, int]:
    """(n, k) of the bucket cells starting in [lo_edge, hi_edge]."""
    n = k = 0
    for label, cell in cells.items():
        start = float(label.split("-")[0])
        if lo_edge <= start <= hi_edge:
            n += int(cell["n"])
            k += int(cell["k"])
    return n, k


@dataclass
class DownOnlyEvidence(le.LineEvidence):
    """R2: every band cell (and the key's all-band cell) sums the buckets from
    a lower edge up to p's own bucket, never above it."""

    def band_cell(self, sport: str, key: str, p: float, odds: float | None
                  ) -> tuple[int, int, str] | None:
        if odds is None:
            return None
        band = le.band_label(float(odds))
        b = le.bucket_of(p)
        top = le.EDGES[b]
        lowest = min(b, le.bucket_of(le.PRINTABLE_FROM))
        scopes = (self.doc.get("bands") or {}).get(sport) or {}
        least = int(self.doc.get("min_cap_cell", le.MIN_CAP_CELL))
        for scope in (key, le.SPORT_SCOPE):
            cells = (scopes.get(scope) or {}).get(band) or {}
            for lower in range(b, lowest - 1, -1):
                n, k = pooled(cells, le.EDGES[lower], top)
                if n >= least:
                    return n, k, f"{scope}@{band}:{le.EDGES[lower]:.3f}..{top:.3f}"
        own = self._entry(sport, key).get("buckets") or {}
        for lower in range(b, lowest - 1, -1):
            n, k = pooled(own, le.EDGES[lower], top)
            if n >= least:
                return n, k, f"{key}@all:{le.EDGES[lower]:.3f}..{top:.3f}"
        return None


def prints(conf: float | None, odds: float, overround: float | None) -> bool:
    return conf is not None and conf >= FLOOR and conf * odds >= MIN_X \
        and (overround is None or overround <= MAX_MARGIN)


# --- the measurement --------------------------------------------------------------

def q1(lines: Sequence[Line]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for sport in SPORTS:
        pop = [r for r in lines if r["sport"] == sport and r["p"] >= FLOOR]
        if not pop:
            continue

        def gap(r: Line) -> float:
            return float(r["y"] - r["p"])

        res: dict[str, Any] = {
            "lines": len(pop), "games": len({r["game"] for r in pop}),
            "K1_thin_vs_rest": boot_contrast(
                [(r["game"], r["n_team"] < THIN_TEAM, gap(r)) for r in pop])}
        known = [r for r in pop if r.get("n_other") is not None]
        res["n_all_known"] = len(known)
        if known:
            res["K2_moved_vs_rest"] = boot_contrast(
                [(r["game"], is_moved(r["n_team"], r["n_other"]), gap(r))
                 for r in known])
            res["moved_and_thin"] = boot_mean(
                [(r["game"], gap(r)) for r in known
                 if is_moved(r["n_team"], r["n_other"]) and r["n_team"] < THIN_TEAM])
            res["thin_not_moved"] = boot_mean(
                [(r["game"], gap(r)) for r in known
                 if not is_moved(r["n_team"], r["n_other"])
                 and r["n_team"] < THIN_TEAM])
            # Not pre-registered (found while measuring): the lineups'
            # `teamId` names the player's team at fetch time, and
            # player_model attributes appearances by it.
            res["exploratory_mislabelled_vs_rest"] = boot_contrast(
                [(r["game"], r["n_mislabelled"] >= MISLABELLED, gap(r))
                 for r in known])
            thin = [r for r in known if r["n_team"] < THIN_TEAM]
            res["thin_composition"] = {
                "lines": len(thin),
                "moved": sum(1 for r in thin if is_moved(r["n_team"], r["n_other"])),
                "mislabelled": sum(1 for r in thin
                                   if r["n_mislabelled"] >= MISLABELLED),
                "n_all_lt_20": sum(1 for r in thin if r["n_all"] < 20),
                "players": len({r["player_id"] for r in thin}),
                "players_mislabelled": len({r["player_id"] for r in thin
                                            if r["n_mislabelled"] >= MISLABELLED})}
            res["lines_mislabelled"] = sum(1 for r in known
                                           if r["n_mislabelled"] >= MISLABELLED)
        res["by_n_team"] = {
            f"{lo}-{hi}": boot_mean([(r["game"], gap(r)) for r in pop
                                     if lo <= r["n_team"] <= hi])
            for lo, hi in N_TEAM_BINS}
        res["by_family_thin"] = {
            k: boot_mean([(r["game"], gap(r)) for r in pop
                          if r["key"] == k and r["n_team"] < THIN_TEAM])
            for k in sorted({r["key"] for r in pop if r["n_team"] < THIN_TEAM})}
        out[sport] = res
    return out


def band_items(rows: Iterable[Line]) -> list[tuple[str, str, bool, int]]:
    return [(str(r["game"]), f"{r['sport']}|{r['key']}|{le.bucket_of(float(r['p']))}",
             float(r["odds"]) >= HI_BAND_FROM, int(r["y"]))
            for r in rows if r.get("odds") and float(r["p"]) >= FLOOR]


def band_profile(rows: Sequence[Line]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for lo, hi in le.PRICE_BANDS:
        sel = [r for r in rows if r.get("odds") and lo <= float(r["odds"]) < hi
               and float(r["p"]) >= FLOOR]
        if sel:
            got = boot_mean([(str(r["game"]), r["y"] - float(r["p"])) for r in sel])
            got["mean_p"] = round(sum(float(r["p"]) for r in sel) / len(sel), 4)
            got["realised"] = round(sum(r["y"] for r in sel) / len(sel), 4)
            out[f"{lo:.2f}-{hi:.2f}"] = got
    return out


def fit_doc(train: Iterable[Line]) -> dict[str, Any]:
    fitted = le.fit(train)
    return {"keys": fitted["keys"], "bands": fitted["bands"],
            "sport_printable": fitted["sport_printable"],
            "design_effect": fitted["design_effect"]}


def read_all(doc: dict[str, Any], row: Line) -> dict[str, float | None]:
    base = None if row["base"] is None else (float(row["base"]), "curve", 0)
    args = (row["sport"], row["key"], float(row["p"]), base, row["odds"])
    cur = le.LineEvidence(doc, v2=True, bucket_deff=True).read(*args)
    down = DownOnlyEvidence(doc, v2=True, bucket_deff=True).read(*args)
    cur_v = None if cur is None else cur.value
    r1 = cur_v
    if row["kind"] == "player" and row["n_team"] < THIN_TEAM:
        r1 = None
    return {"current": cur_v, "R1": r1, "R2": None if down is None else down.value}


def walk(player: Sequence[Line], sport_rows_by_day: Callable[[str], list[Line]],
         days: Sequence[str]) -> dict[str, Any]:
    legs: dict[tuple[str, str, str], list[tuple[str, float, int, float]]] = \
        defaultdict(list)
    removed: dict[tuple[str, str, str], list[tuple[str, float, int, float]]] = \
        defaultdict(list)
    lowered: dict[tuple[str, str, str], list[tuple[str, float, int, float]]] = \
        defaultdict(list)
    roi_items: dict[tuple[str, str, str], list[tuple[str, bool, float]]] = \
        defaultdict(list)
    for day in days:
        srows = sport_rows_by_day(day)
        train = [r for r in player if r["day"] < day] + \
            [r for r in srows if r["day"] < day]
        test = [r for r in player if r["day"] == day] + \
            [r for r in srows if r["day"] == day and r["odds"]]
        doc = fit_doc(train)
        for r in test:
            if r["sport"] not in scf.SPORT_KEYS:
                continue
            kind = r["kind"] if r["base"] is None or r["kind"] == "player" \
                else "curve"
            reads = read_all(doc, r)
            odds = float(r["odds"])
            cur = reads["current"]
            if not prints(cur, odds, r["overround"]):
                continue
            assert cur is not None
            item = (str(r["game"]), cur, int(r["y"]), odds)
            for v in VARIANTS:
                value = reads[v]
                if prints(value, odds, r["overround"]):
                    assert value is not None
                    legs[(r["sport"], kind, v)].append(
                        (str(r["game"]), value, int(r["y"]), odds))
                    if v != "current" and value < cur:
                        lowered[(r["sport"], kind, v)].append(item)
                elif v != "current":
                    removed[(r["sport"], kind, v)].append(item)
                if v != "current":
                    roi_items[(r["sport"], kind, v)].append(
                        (str(r["game"]), not prints(value, odds, r["overround"]),
                         r["y"] * odds - 1.0))
        print(f"W {day}: train {len(train)} test {len(test)}", file=sys.stderr)
    out: dict[str, Any] = {}
    for (sport, kind, v), items in sorted(legs.items()):
        entry = boot_legs(items)
        if v != "current":
            entry["removed_vs_current"] = boot_legs(removed[(sport, kind, v)])
            entry["lowered_kept"] = boot_legs(lowered[(sport, kind, v)])
            entry["roi_removed_minus_kept"] = boot_contrast(
                roi_items[(sport, kind, v)])
        out[f"{sport}:{kind}:{v}"] = entry
    for (sport, kind, v), items in sorted(removed.items()):
        key = f"{sport}:{kind}:{v}"
        if key not in out:
            out[key] = {"legs": 0, "removed_vs_current": boot_legs(items)}
    return out


def verdict_q1(res: Mapping[str, Any]) -> str:
    k = res.get("K1_thin_vs_rest") or {}
    if k.get("a_lines", 0) < MIN_THIN_LINES or k.get("a_games", 0) < MIN_GAMES:
        return "N_TOO_SMALL"
    ci = k.get("diff_ci")
    if ci and ci[1] < 0:
        return "CONFIRMED"
    return "NOT_CONFIRMED"


def verdict_m2(res: Mapping[str, Any]) -> str:
    if res.get("hi_games", 0) < MIN_GAMES:
        return "N_TOO_SMALL"
    ci = res.get("diff_ci")
    return "CONFIRMED" if ci and ci[1] < 0 else "NOT_CONFIRMED"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="start", default="2026-09-29")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--first-test", default="2026-10-02")
    ap.add_argument("--rows-dir", default="data/line_evidence/rows_before_2026-10-13")
    ap.add_argument("--skip-db", action="store_true")
    ap.add_argument("--skip-walk", action="store_true")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir)

    lines = load_player_lines(runs_dir, args.start, args.end)
    print(f"player lines: {len(lines)}", file=sys.stderr)
    if not args.skip_db:
        conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
        for sport in SPORTS:
            mine = [r for r in lines if r["sport"] == sport and r["p"] >= FLOOR
                    and r["player_id"] is not None and r["kickoff_ts"]]
            if not mine:
                continue
            wanted = {int(r["player_id"]) for r in mine}
            lo = min(r["kickoff_ts"] for r in mine) - WINDOW_DAYS * 86400
            hi = max(r["kickoff_ts"] for r in mine)
            apps = scan_appearances(conn, SLUG[sport], wanted, lo, hi)
            for r in mine:
                r["n_all"], r["n_other"], r["n_mislabelled"] = career_counts(
                    apps.get(int(r["player_id"]), []), int(r["kickoff_ts"]))
            print(f"{sport}: {len(wanted)} players scanned", file=sys.stderr)
        conn.close()

    out: dict[str, Any] = {"from": args.start, "to": args.end, "boot": BOOT,
                           "seed": SEED, "q1": q1(lines)}
    out["q1_verdict"] = {s: verdict_q1(r) for s, r in out["q1"].items()}

    # Q2 - player lines (primary), other no-curve keys (secondary).
    cache: dict[str, list[Line]] = {}

    def sport_rows_by_day(day: str) -> list[Line]:
        path = scf.calibration_path_for(day)
        if str(path) not in cache:
            from scripts.sofa.fit_line_evidence import sport_rows
            cal = scf.SportCalibration.load(path)
            got: list[Line] = []
            if cal is not None:
                for r in sport_rows(Path(args.rows_dir), cal, config.runs_dir):
                    got.append({**r, "day": str(r["game"]).split(":")[1],
                                "overround": None, "n_team": None,
                                "kind": "other"})
            cache[str(path)] = got
            print(f"sport rows ({path.name}): {len(got)}", file=sys.stderr)
        return cache[str(path)]

    q2: dict[str, Any] = {}
    for sport in SPORTS:
        mine = [r for r in lines if r["sport"] == sport]
        q2[f"{sport}:player"] = {"M2": cmh_difference(band_items(mine)),
                                 "bands": band_profile(mine)}
    days = sorted({r["day"] for r in lines})
    other: list[Line] = []
    for day in days:
        other += [r for r in sport_rows_by_day(day)
                  if r["day"] == day and r["base"] is None]
    for sport in scf.SPORT_KEYS:
        mine = [r for r in other if r["sport"] == sport]
        if mine:
            q2[f"{sport}:other_no_curve"] = {"M2": cmh_difference(band_items(mine)),
                                             "bands": band_profile(mine)}
    out["q2"] = q2
    out["q2_verdict"] = {k: verdict_m2(v["M2"]) for k, v in q2.items()}

    if not args.skip_walk:
        test_days = [d for d in days if d >= args.first_test]
        out["walk"] = walk(lines, sport_rows_by_day, test_days)
    text = json.dumps(out, indent=1, ensure_ascii=False)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
