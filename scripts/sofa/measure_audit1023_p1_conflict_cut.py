#!/usr/bin/env python3
"""P1 of the coverage audit 2026-10-23 (B4): what cutting a football side's
sample at a two-squad clash (epochs.SAMPLE_CONFLICT_CUT_FROM_UTC) recovers,
and whether the recovered rows are calibrated. Read-only evidence.

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p1_conflict_cut.py \\
        --db-path data/refit_2026-10-23_allin/sofa_copy.db \\
        --from 2025-10-01 --to 2026-10-20 [--days 2026-10-21,2026-10-22,2026-10-23] \\
        [--control-every 20] [--json-out f]

Each football side's candidates are its newest CANDIDATES indexed listed
events before kick-off admitted as SAMPLES admits them (finished normally,
no friendly, the side in the match, not the target re-listed), made into a
sample by samples.finish_history with the switch off and on. A side is
CLEAN (no clash), RECOVERED (old: empty for ENTITY_CONFLICT; new: the newest
ten after the clash) or STILL_EMPTY (fewer than ten after it).

`--days`: the live days' 03_samples.json ENTITY_CONFLICT sides, re-read so,
and the priced rungs 04_offer.json holds for those fixtures.

History: the cache replay rows (sofa_settled_row run_date
'cache-calibration'; the replay runs no two-squad check, so it holds the
rows a RECOVERED side would price - its sample is the newest ten in both)
of RECOVERED fixtures (the side's `_for` rows and the totals) against those
of every `--control-every`-th CLEAN fixture, each read through the
installed curve (Calibration.realised, before line evidence). Reported:
realised minus confidence per group with a match bootstrap, and RECOVERED
minus CLEAN, on every row and on the printable ones (confidence >= 0.70).
Nothing is written but --json-out.
"""

from __future__ import annotations

import argparse
import collections
import json
import multiprocessing
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bet.sofa.confidence import Calibration, calibration_path_for  # noqa: E402
from bet.sofa.contracts import GapEntry, GapReason  # noqa: E402
from bet.sofa.samples import (  # noqa: E402
    CONFLICT_CUT_FRIENDLY_IDS,
    FRIENDLY_COMPETITION_IDS,
    _competition_id,
    finish_history,
)
from bet.sofa.settle import is_completed_event  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402

CANDIDATES = 30
SAMPLE_N = 10
FLOOR = 0.70
BOOT = 2000


def _ts(day: str, end: bool = False) -> int:
    t = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())
    return t + 86400 if end else t


def entity_listing(con: sqlite3.Connection, entity: int) -> list[dict[str, Any]]:
    out = []
    for (raw,) in con.execute(
        "SELECT e.event_json FROM sofa_listing_event m JOIN sofa_listed_event e "
        "ON e.event_id = m.event_id WHERE m.entity_id = ? AND m.kind = 'last' "
        "ORDER BY m.start_ts DESC, m.event_id DESC",
        (entity,),
    ):
        try:
            ev = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(ev, dict) and isinstance(ev.get("startTimestamp"), int):
            out.append(ev)
    return out


def classify(
    listing: list[dict[str, Any]], target: dict[str, Any], entity: int,
) -> tuple[str, int, str]:
    """(CLEAN / RECOVERED / STILL_EMPTY / OTHER_EMPTY, cut sample size, gap)."""
    kickoff = int(target["startTimestamp"])
    before = [e for e in listing if e["startTimestamp"] < kickoff][:CANDIDATES]
    admitted = [e for e in before
                if cfc.admitted_football_event(e, entity, kickoff)
                and not cfc.is_same_match(e, target)]
    comp = _competition_id(target)
    old_gaps: list[GapEntry] = []
    old = finish_history(admitted, entity, "football", comp, kickoff, SAMPLE_N,
                         old_gaps)
    conflict = any(g.reason == GapReason.ENTITY_CONFLICT for g in old_gaps)
    if not conflict:
        return ("CLEAN" if old else "OTHER_EMPTY"), len(old), ""
    new_admitted = [e for e in admitted
                    if _competition_id(e) not in CONFLICT_CUT_FRIENDLY_IDS]
    new_gaps: list[GapEntry] = []
    new = finish_history(new_admitted, entity, "football", comp, kickoff,
                         SAMPLE_N, new_gaps, conflict_cut=True)
    detail = next(g.detail for g in old_gaps
                  if g.reason == GapReason.ENTITY_CONFLICT)
    return ("RECOVERED" if new else "STILL_EMPTY"), len(new), detail


def clash_age_days(detail: str, kickoff: int,
                   con: sqlite3.Connection) -> float | None:
    words = detail.split()
    try:
        later = int(words[words.index("and") + 1])
    except (ValueError, IndexError):
        return None
    row = con.execute("SELECT start_ts FROM sofa_listed_event WHERE event_id=?",
                      (later,)).fetchone()
    return None if not row or row[0] is None else (kickoff - row[0]) / 86400


def live_days(con: sqlite3.Connection, days: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for day in days:
        run = ROOT / "runs" / "sofa" / day
        samples = json.loads((run / "03_samples.json").read_text())
        fixtures = {f["sofascore_event_id"]: f
                    for f in json.loads((run / "02_fixtures.json").read_text())
                    } if (run / "02_fixtures.json").exists() else {}
        offer = {o["sofascore_event_id"]: o
                 for o in json.loads((run / "04_offer.json").read_text())}
        sides = []
        for fx in samples:
            for g in fx.get("gaps") or []:
                if g.get("reason") != "ENTITY_CONFLICT":
                    continue
                eid = fx["sofascore_event_id"]
                entity = int(g["detail"].split()[1].rstrip(":"))
                payload = cfc._event_payloads(con, [eid], True).get(eid)
                if payload is None:
                    sides.append({"event": eid, "entity": entity,
                                  "group": "NO_PAYLOAD"})
                    continue
                group, n, detail = classify(entity_listing(con, entity),
                                            payload, entity)
                rungs = (offer.get(eid) or {}).get("rungs") or []
                sides.append({
                    "event": eid, "entity": entity, "group": group, "n": n,
                    "clash_age_days": clash_age_days(
                        g["detail"], int(payload["startTimestamp"]), con),
                    "offer_rungs": len(rungs),
                    "fixture": (fixtures.get(eid) or {}).get("home_name"),
                    "detail": detail or g["detail"],
                })
        out[day] = {
            "sides": sides,
            "by_group": dict(collections.Counter(s["group"] for s in sides)),
        }
    return out


WORKERS = 6
DB_PATH: list[str] = [""]
_CON: list[sqlite3.Connection] = []


def _init(db: str) -> None:
    _CON.append(sqlite3.connect(f"file:{db}?mode=ro", uri=True))


def _classify_chunk(
    work: list[tuple[int, list[int]]],
) -> dict[tuple[int, int], tuple[str, int, str]]:
    con = _CON[0]
    out: dict[tuple[int, int], tuple[str, int, str]] = {}
    for k, (entity, events) in enumerate(work):
        if k % 1000 == 0:
            print(f"worker entity {k}/{len(work)}", file=sys.stderr, flush=True)
        listing = entity_listing(con, entity)
        by_id = {int(e["id"]): e for e in listing if isinstance(e.get("id"), int)}
        for eid in events:
            ev = by_id.get(eid)
            if ev is not None:
                out[(eid, entity)] = classify(listing, ev, entity)
    return out


def history_targets(con: sqlite3.Connection, lo: int, hi: int
                    ) -> list[dict[str, Any]]:
    out = []
    for (raw,) in con.execute(
        "SELECT event_json FROM sofa_listed_event WHERE sport = 'football' "
        "AND start_ts >= ? AND start_ts < ?", (lo, hi),
    ):
        try:
            ev = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(ev, dict) or not is_completed_event(ev):
            continue
        if _competition_id(ev) in FRIENDLY_COMPETITION_IDS:
            continue
        out.append({"id": ev.get("id"),
                    "homeTeam": {"id": (ev.get("homeTeam") or {}).get("id")},
                    "awayTeam": {"id": (ev.get("awayTeam") or {}).get("id")}})
    return out


def replay_rows(con: sqlite3.Connection, event_id: int,
                subjects: set[str] | None) -> list[dict[str, Any]]:
    rows = []
    for market, subject, line, direction, p, outcome in con.execute(
        "SELECT market, subject, line, direction, p_central, outcome "
        "FROM sofa_settled_row WHERE sofascore_event_id = ? "
        "AND run_date = 'cache-calibration'", (event_id,),
    ):
        if outcome not in ("WIN", "LOSS"):
            continue
        if subjects is not None and subject and subject not in subjects:
            continue
        rows.append({"event_id": event_id, "market": market, "subject": subject,
                     "line": line, "direction": direction, "p": p,
                     "won": outcome == "WIN"})
    return rows


def boot(rows: list[dict[str, Any]], seed: int = 7) -> dict[str, Any]:
    if not rows:
        return {"rows": 0}
    ids = sorted({r["event_id"] for r in rows})
    col = {e: i for i, e in enumerate(ids)}
    a = np.zeros((3, len(ids)))
    for r in rows:
        j = col[r["event_id"]]
        a[0, j] += 1
        a[1, j] += r["won"]
        a[2, j] += r["confidence"]
    w = np.random.default_rng(seed).multinomial(
        len(ids), np.full(len(ids), 1 / len(ids)), size=BOOT)
    tot = a.sum(axis=1)
    d = a @ w.T
    draws = (d[1] - d[2]) / d[0]
    return {"rows": int(tot[0]), "fixtures": len(ids),
            "confidence": round(float(tot[2] / tot[0]), 4),
            "realised": round(float(tot[1] / tot[0]), 4),
            "gap": round(float((tot[1] - tot[2]) / tot[0]), 4),
            "lo": round(float(np.quantile(draws, 0.025)), 4),
            "hi": round(float(np.quantile(draws, 0.975)), 4)}


def boot_diff(g: list[dict[str, Any]], b: list[dict[str, Any]],
              seed: int = 11) -> dict[str, Any]:
    if not g or not b:
        return {}
    ids = sorted({r["event_id"] for r in g} | {r["event_id"] for r in b})
    col = {e: i for i, e in enumerate(ids)}

    def arr(rows: list[dict[str, Any]]) -> np.ndarray:
        a = np.zeros((3, len(ids)))
        for r in rows:
            j = col[r["event_id"]]
            a[0, j] += 1
            a[1, j] += r["won"]
            a[2, j] += r["confidence"]
        return a

    ga, ba = arr(g), arr(b)
    w = np.random.default_rng(seed).multinomial(
        len(ids), np.full(len(ids), 1 / len(ids)), size=BOOT)
    gt, bt = ga.sum(axis=1), ba.sum(axis=1)
    point = (gt[1] - gt[2]) / gt[0] - (bt[1] - bt[2]) / bt[0]
    gd, bd = ga @ w.T, ba @ w.T
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = (gd[1] - gd[2]) / gd[0] - (bd[1] - bd[2]) / bd[0]
    draws = draws[np.isfinite(draws)]
    return {"diff": round(float(point), 4),
            "lo": round(float(np.quantile(draws, 0.025)), 4),
            "hi": round(float(np.quantile(draws, 0.975)), 4)}


def history(con: sqlite3.Connection, lo: str, hi: str, control_every: int,
            cal: Calibration, groups_cache: str | None = None) -> dict[str, Any]:
    side_group = _side_groups(con, lo, hi, groups_cache)
    return _history_rows(con, side_group, control_every, cal)


def _side_groups(con: sqlite3.Connection, lo: str, hi: str,
                 groups_cache: str | None
                 ) -> dict[tuple[int, int], tuple[str, int, str]]:
    if groups_cache and Path(groups_cache).exists():
        raw = json.loads(Path(groups_cache).read_text())
        return {(int(e), int(t)): (g, n, d) for e, t, g, n, d in raw}
    targets = history_targets(con, _ts(lo), _ts(hi, end=True))
    print(f"targets {len(targets)}", file=sys.stderr)
    by_entity: dict[int, list[tuple[dict[str, Any], bool]]] = (
        collections.defaultdict(list))
    for ev in targets:
        for home in (True, False):
            team = ev.get("homeTeam" if home else "awayTeam") or {}
            if isinstance(team.get("id"), int):
                by_entity[team["id"]].append((ev, home))
    side_group: dict[tuple[int, int], tuple[str, int, str]] = {}
    work = [(entity, [int(ev["id"]) for ev, _ in items])
            for entity, items in sorted(by_entity.items())]
    del targets
    chunks = [work[i::WORKERS] for i in range(WORKERS)]
    with multiprocessing.Pool(WORKERS, initializer=_init,
                              initargs=(DB_PATH[0],)) as pool:
        for part in pool.imap_unordered(_classify_chunk, chunks):
            side_group.update(part)
    if groups_cache:
        Path(groups_cache).write_text(json.dumps(
            [[e, t, g, n, d] for (e, t), (g, n, d) in side_group.items()]))
    return side_group


def _history_rows(con: sqlite3.Connection,
                  side_group: dict[tuple[int, int], tuple[str, int, str]],
                  control_every: int, cal: Calibration) -> dict[str, Any]:
    counts = collections.Counter(g for g, _, _ in side_group.values())
    per_fixture: dict[int, dict[int, str]] = collections.defaultdict(dict)
    for (eid, entity), (g, _, _) in side_group.items():
        per_fixture[eid][entity] = g
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    clean_k = 0
    def take(name: str, rows: list[dict[str, Any]]) -> None:
        for r in rows:
            hit = cal.realised(r["market"], r["p"], "football", r["direction"],
                               None)
            if hit is None:
                continue
            groups[name].append({"event_id": r["event_id"], "market": r["market"],
                                 "won": r["won"], "confidence": float(hit[0])})

    for k, (eid, sides) in enumerate(sorted(per_fixture.items())):
        if k % 20000 == 0:
            print(f"rows fixture {k}/{len(per_fixture)} "
                  f"{ {n: len(v) for n, v in groups.items()} }",
                  file=sys.stderr, flush=True)
        recovered = {str(e) for e, g in sides.items() if g == "RECOVERED"}
        still = {str(e) for e, g in sides.items() if g == "STILL_EMPTY"}
        if recovered:
            take("RECOVERED", replay_rows(con, eid, recovered))
        elif still:
            take("STILL_EMPTY", replay_rows(con, eid, still))
        elif all(g == "CLEAN" for g in sides.values()):
            clean_k += 1
            if clean_k % control_every == 0:
                take("CLEAN", replay_rows(con, eid, None))
    out: dict[str, Any] = {"sides": dict(counts),
                           "recovered_fixtures": sum(
                               1 for s in per_fixture.values()
                               if "RECOVERED" in s.values())}
    for scope, keep in (("all", lambda r: True),
                        ("printable", lambda r: r["confidence"] >= FLOOR)):
        res: dict[str, Any] = {}
        for name, rows in groups.items():
            res[name] = boot([r for r in rows if keep(r)])
        res["RECOVERED_minus_CLEAN"] = boot_diff(
            [r for r in groups.get("RECOVERED", []) if keep(r)],
            [r for r in groups.get("CLEAN", []) if keep(r)])
        out[scope] = res
    by_market: dict[str, Any] = {}
    rec = [r for r in groups.get("RECOVERED", []) if r["confidence"] >= FLOOR]
    for market in sorted({r["market"] for r in rec}):
        by_market[market] = boot([r for r in rec if r["market"] == market])
    out["recovered_printable_by_market"] = by_market
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--from", dest="lo", default="2025-10-01")
    ap.add_argument("--to", dest="hi", default="2026-10-20")
    ap.add_argument("--days", default="")
    ap.add_argument("--control-every", type=int, default=200)
    ap.add_argument("--groups-cache")
    ap.add_argument("--skip-history", action="store_true")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    DB_PATH[0] = args.db_path
    report: dict[str, Any] = {}
    if args.days:
        report["live"] = live_days(con, args.days.split(","))
    if not args.skip_history:
        cal = Calibration.load(calibration_path_for(args.hi))
        report["history"] = history(con, args.lo, args.hi, args.control_every,
                                    cal, args.groups_cache)
    text = json.dumps(report, indent=1, ensure_ascii=False, default=str)
    if args.json_out:
        Path(args.json_out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
