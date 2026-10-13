"""Measure the league-rate rule (audit 2026-10-13 A2, epochs.LEAGUE_RATE_RULE).

Pre-registered in docs/sofa/evidence/league_rate_rule_2026-10-13.md. Two tests:

  S (hockey / basketball / volleyball): Superbet's settled lines of the
    window in the games the rule refuses (a friendly / pre-season, or a
    competition below MIN_LEAGUE_MATCHES in the model as of the day) against
    the rest - the would-print lines' realised minus confidence and their ROI
    at Superbet's price, 95% from resampling games;
  F (football): one step ahead on the cached history, the sides of matches
    in a competition below MIN_LEAGUE_MATCHES: the centre with the rating at
    the all-league rate (0.5 rating + 0.5 own last ten, the old rule) against
    the own last ten alone (the new rule) - squared error per side, 95% from
    resampling matches.

Read-only: writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_league_rate_rule.py \\
        [--from 2026-09-29] [--to 2026-10-12] [--rows-dir <dir>] \\
        [--football-from 2025-08-01] [--skip-football] [--skip-sports]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict, deque
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import shadow  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.comparability import competition_id, is_friendly_event  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.line_evidence import DEFAULT_EVIDENCE, LineEvidence  # noqa: E402
from bet.sofa.score_model import _metrics, build_model, load_events  # noqa: E402
from scripts.sofa.run_sport_confidence import read_confidence  # noqa: E402

N_BOOT = 2000
FLOOR, MIN_X = 0.70, 0.90


def _days(start: str, end: str) -> list[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def boot_mean(groups: dict[str, list[float]], seed: int = 0
              ) -> tuple[float, float, float, int]:
    """(mean over items, lo, hi, n items) resampling the groups."""
    keys = sorted(groups)
    flat = [v for k in keys for v in groups[k]]
    if not flat:
        return float("nan"), float("nan"), float("nan"), 0
    rng = random.Random(seed)
    stats = []
    for _ in range(N_BOOT):
        tot, n = 0.0, 0
        for _k in range(len(keys)):
            vs = groups[keys[rng.randrange(len(keys))]]
            tot += sum(vs)
            n += len(vs)
        stats.append(tot / n if n else 0.0)
    stats.sort()
    return (sum(flat) / len(flat), stats[int(0.025 * N_BOOT)],
            stats[int(0.975 * N_BOOT) - 1], len(flat))


def _key(r: dict[str, Any]) -> tuple[Any, ...]:
    return (int(r["market_id"]), int(r.get("period") or 0), str(r.get("subject") or ""),
            r.get("line"), str(r["side"]))


def sports_test(days: Sequence[str], rows_dir: Path, runs_dir: Path, db: str
                ) -> dict[str, Any]:
    evidence = LineEvidence.load(DEFAULT_EVIDENCE, v2=True)
    out: dict[str, Any] = {}
    for key in ("hockey", "basketball", "volleyball"):
        sp = shadow.SPORTS[key]
        p_by: dict[str, dict[tuple[Any, ...], float]] = defaultdict(dict)
        path = rows_dir / f"{key}_superbet_settled.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("date") in days:
                p_by[r["game"]][_key(r)] = float(r["p"])
        events = load_events(db, sp)
        history = scf.parse_history(events, sp)
        ratings = [g.rating for g in history]
        metric = _metrics(sp)[0]
        allowed = scf.allowed_markets(key, extended=True)
        gaps: dict[str, dict[str, list[float]]] = {
            g: defaultdict(list) for g in ("refused", "kept")}
        rois: dict[str, dict[str, list[float]]] = {
            g: defaultdict(list) for g in ("refused", "kept")}
        counts: dict[str, int] = defaultdict(int)
        for day in days:
            settled = runs_dir / "shadow" / key / day / "settled.json"
            if not settled.exists():
                continue
            doc = json.loads(settled.read_text(encoding="utf-8"))
            model = build_model(ratings, sp, scf.day_ts(day))
            cal = scf.SportCalibration.load(scf.calibration_path_for(day))
            if cal is None:
                continue
            for sb_id, entry in (doc.get("events") or {}).items():
                game = f"s:{day}:{sb_id}"
                if game not in p_by:
                    continue
                try:
                    event = events.get(int(entry["sofascore_event_id"]))
                except (KeyError, TypeError, ValueError):
                    continue
                if event is None:
                    continue
                comp = competition_id(event) or int(event["tournament"]["id"])
                league = model.book.leagues.get((comp, metric))
                friendly = is_friendly_event(event, sp.sofascore_slug)
                thin = league is None or league.n < fr.MIN_LEAGUE_MATCHES
                group = "refused" if (friendly or thin) else "kept"
                counts[f"{group}_games"] += 1
                counts["friendly_games"] += friendly
                for g in entry.get("graded") or []:
                    if g.get("outcome") not in ("WIN", "LOSS"):
                        continue
                    p = p_by[game].get(_key(g))
                    fam = allowed.get(int(g["market_id"]))
                    if p is None or fam is None:
                        continue
                    odds = float(g.get("odds") or 0)
                    conf, *_ = read_confidence(cal, evidence, key, fam, str(g["side"]),
                                               p, odds or None)
                    if conf is None or conf.value < FLOOR or conf.value * odds < MIN_X:
                        continue
                    y = 1.0 if g["outcome"] == "WIN" else 0.0
                    gaps[group][game].append(y - conf.value)
                    rois[group][game].append(y * odds - 1.0)
                    counts[f"{group}_lines"] += 1
        out[key] = {"counts": dict(counts)}
        for group in ("refused", "kept"):
            m, lo, hi, n = boot_mean(gaps[group])
            rm, rlo, rhi, _ = boot_mean(rois[group])
            out[key][group] = {"gap": [m, lo, hi], "roi": [rm, rlo, rhi], "lines": n,
                               "games": len(gaps[group])}
        print(key, json.dumps(out[key]), flush=True)
    return {"per_sport": out}


def football_test(start: str, end: str, db: str) -> dict[str, Any]:
    history = fr.load_history(db, Path(db).parent / "cache")
    t0 = int(datetime.fromisoformat(start).replace(tzinfo=UTC).timestamp())
    t1 = int((datetime.fromisoformat(end) + timedelta(days=1)).replace(
        tzinfo=UTC).timestamp())
    book = fr.RatingBook()
    last: dict[tuple[int, str], deque[float]] = defaultdict(lambda: deque(maxlen=10))
    rated = sorted(m for m in fr.BASE_METRICS)
    diff: dict[str, list[float]] = defaultdict(list)
    per_metric: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    mse: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in history:
        if r.ts >= t1:
            break
        if r.ts >= t0:
            mid = f"{r.ts}:{r.home_id}:{r.away_id}"
            for m, (vh, va) in r.values.items():
                if m not in rated:
                    continue
                league = book.leagues.get((r.competition_id, m))
                if league is not None and league.n >= fr.MIN_LEAGUE_MATCHES:
                    continue
                if (book.team_matches(r.home_id, m) < fr.MIN_TEAM_MATCHES
                        or book.team_matches(r.away_id, m) < fr.MIN_TEAM_MATCHES):
                    continue
                lh, la = last[(r.home_id, m)], last[(r.away_id, m)]
                if len(lh) < 5 or len(la) < 5:
                    continue
                status, lf = book.link(r.home_id, r.away_id, m)
                exp = book.expected(r.competition_id, r.home_id, r.away_id, m, lf,
                                    cross=status != fr.LINKED)
                if exp is None:
                    continue
                for e_rat, own, v in ((exp[0], lh, vh), (exp[1], la, va)):
                    b = sum(own) / len(own)
                    a = fr.W_FOOTBALL_RATING * e_rat + (1 - fr.W_FOOTBALL_RATING) * b
                    d = (a - v) ** 2 - (b - v) ** 2
                    diff[mid].append(d)
                    per_metric[m][mid].append(d)
                    s = mse[m]
                    s[0] += (a - v) ** 2
                    s[1] += (b - v) ** 2
                    s[2] += 1
        for m, (vh, va) in r.values.items():
            last[(r.home_id, m)].append(vh)
            last[(r.away_id, m)].append(va)
        book.update(r)
    out: dict[str, Any] = {"pooled": list(boot_mean(diff)), "metrics": {}}
    for m, groups in sorted(per_metric.items()):
        s = mse[m]
        out["metrics"][m] = {"diff": list(boot_mean(groups)),
                             "mse_old": s[0] / s[2], "mse_new": s[1] / s[2],
                             "sides": int(s[2]), "matches": len(groups)}
    print("football", json.dumps(out), flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2026-09-29")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--rows-dir", default="data/line_evidence/rows_before_2026-10-13")
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--football-from", default="2025-08-01")
    ap.add_argument("--skip-football", action="store_true")
    ap.add_argument("--skip-sports", action="store_true")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    db = SofaConfig.from_env().db_path
    result: dict[str, Any] = {}
    if not args.skip_sports:
        result["sports"] = sports_test(_days(args.start, args.end), Path(args.rows_dir),
                                       Path(args.runs_dir), db)
    if not args.skip_football:
        result["football"] = football_test(args.football_from, args.end, db)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
