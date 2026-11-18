#!/usr/bin/env python3
# ruff: noqa: N803, N806
"""The ONE exam of the stakes term for hockey, basketball and volleyball
(pre-registration docs/sofa/evidence/stakes_prereg_sports_2026-11-18.md,
frozen in 646b1317, Aneks A in 32ba661e; rule (c) S1-S5 / P1-P6).

Read-only evidence: nothing in config/ or the database is written
(`data/sofa.db` opened `?mode=ro`). Three phases, in this order:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_stakes_exam_sports.py \\
        --phase record --sport hockey --work <dir>     # walk-forward, sealed
    ... --phase estimate --work <dir>                  # dev only -> frozen
    ... --phase exam --work <dir> --spec-sha 32ba661e   # opens 25/26 outcomes once

`record` writes, per sport, the dev rows (22/23..24/25, outcomes included) and
the exam rows (25/26) with the exam outcomes in a separate sealed file.
`estimate` reads dev rows only, fits the frozen coefficients, runs the
submission gates S1-S5, fits the dev curves, and writes
`coefficients_frozen.json` + `freeze_record.json` (sha256 of both frozen
files) into the evidence run directory. `exam` refuses unless the freeze
record matches byte for byte and the exam log holds no line of this study
(G2); it then opens the sealed outcomes, evaluates P1-P6 with Holm across the
submitted groups and appends one line to docs/sofa/evidence/stakes_exam_log.md.
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import importlib.util
import json
import math
import random
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import numpy.typing as npt

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa import score_model as sm  # noqa: E402
from bet.sofa import vb_point_pricer as vpp  # noqa: E402
from bet.sofa import volleyball_point_model as vpm  # noqa: E402
from bet.sofa.comparability import is_friendly_event  # noqa: E402
from bet.sofa.football_rating import FootballResult  # noqa: E402
from bet.sofa.resolve import sofascore_gender  # noqa: E402
from bet.sofa.shadow import SPORTS, ShadowSport  # noqa: E402

F64 = npt.NDArray[np.float64]
STUDY = "stakes_sports_2026-11-18"
SPEC_FILE = "docs/sofa/evidence/stakes_prereg_sports_2026-11-18.md"
EVIDENCE = REPO / "docs/sofa/evidence/stakes_sports_2026-11-18"
RUN = EVIDENCE / "run"
EXAM_LOG = REPO / "docs/sofa/evidence/stakes_exam_log.md"
DB = REPO / "data/sofa.db"
FROZEN_MODULES = {
    "states.py": ("826dfdd092ee757cd9d08da11feacf5a32568572e08c9dba8d719f7400bcb4cc"),
    "seasons_rules.py": (
        "7c88084b0bcf0653378cac52d985ba48e2664e3534399038fd934187f97b50f7"
    ),
}
SLUG = {"hockey": "ice-hockey", "basketball": "basketball", "volleyball": "volleyball"}
DEV_YEARS = (2022, 2023, 2024)
EXAM_YEAR = 2025
WINDOW = 0.75
STATES = ("MUST_WIN", "SECURED", "DEAD")  # ALIVE and EARLY are the reference
# Aneks A sides per state (dev, exam), the G1 check of the state rebuild
ANEKS_A = {
    "hockey": {"dev": (2456, 3992, 3562, 922), "exam": (959, 1508, 1516, 376)},
    "basketball": {"dev": (4565, 6738, 7882, 4767), "exam": (1447, 2570, 3122, 2027)},
    "volleyball": {"dev": (1118, 1798, 3307, 1848), "exam": (471, 654, 1199, 653)},
}
# Aneks A's main phase where two phases tie in game count (found by the G1
# check on 2026-11-18, before any estimation): states.py takes the first name
# in row order; Aneks A's snapshot listed Clausura first
MAIN_PHASE_TIE: dict[tuple[int, int], str] = {(17343, 74021): "LMB, Clausura"}
TIES: list[list[Any]] = []
TAU = {"hockey": 0.05, "basketball": 0.02, "volleyball": 0.02}
C_SPORT = {"hockey": 0.05, "basketball": 0.015, "volleyball": 0.015}
GROUPS = {
    "hockey": ("hk_goals", "hk_result"),
    "basketball": ("bb_points", "bb_result"),
    "volleyball": ("vb_points", "vb_result"),
}
# S3: the registered sign of the margin (own - opp) per state
SIGN = {"MUST_WIN": 1.0, "SECURED": -1.0, "DEAD": -1.0}
N_SIMS = 4000
REPS = 2000
PERMS = 200
ALPHA = 0.05
P3_UPPER = 2e-4
P4_SLACK = 0.005
P5_GROUP_UPPER = 1e-4
P5_STRATUM_UPPER = 5e-4
P5_MIN_ROWS = 2000
P2_MIN_SHARE = 0.02
REBUILD_DAYS = 30
BUCKET = 0.05
MIN_BUCKET_ROWS = 30


# ---------------------------------------------------------------------------
# frozen modules and inputs
# ---------------------------------------------------------------------------


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_rules() -> ModuleType:
    for name, want in FROZEN_MODULES.items():
        got = sha256(EVIDENCE / name)
        if got != want:
            raise SystemExit(f"G1: {name} sha256 {got} != frozen {want}")
    spec = importlib.util.spec_from_file_location(
        "stakes_seasons_rules", EVIDENCE / "seasons_rules.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load seasons_rules.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_gz(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with gzip.open(path, "wt") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def read_gz(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f]


# ---------------------------------------------------------------------------
# record: stream the sport's events (pages, then the index; newest wins)
# ---------------------------------------------------------------------------


def compact(e: dict[str, Any]) -> dict[str, Any] | None:
    """extract.py's row of one event."""
    try:
        t = e.get("tournament") or {}
        ut = t.get("uniqueTournament") or {}
        se = e.get("season") or {}
        ri = e.get("roundInfo") or {}
        st = e.get("status") or {}
        hs, as_ = e.get("homeScore") or {}, e.get("awayScore") or {}
        return {
            "id": int(e["id"]),
            "ts": int(e["startTimestamp"]),
            "ut_id": ut.get("id"),
            "ut_name": ut.get("name"),
            "t_name": t.get("name"),
            "cat": (t.get("category") or {}).get("name"),
            "season_id": se.get("id"),
            "season_name": se.get("name"),
            "season_year": se.get("year"),
            "round": ri.get("round"),
            "round_name": ri.get("name"),
            "h": e["homeTeam"]["id"],
            "a": e["awayTeam"]["id"],
            "hn": e["homeTeam"].get("name"),
            "an": e["awayTeam"].get("name"),
            "st": st.get("type"),
            "sdesc": st.get("description"),
            "win": e.get("winnerCode"),
            "hs": hs.get("current"),
            "as": as_.get("current"),
            "gender": e["homeTeam"].get("gender"),
        }
    except (KeyError, TypeError, ValueError):
        return None


def vb_sets(e: dict[str, Any]) -> tuple[list[int], list[int]] | None:
    """A completed best-of-five's set scores (golden set excluded)."""
    hs, as_ = e.get("homeScore") or {}, e.get("awayScore") or {}
    h: list[int] = []
    a: list[int] = []
    for n in range(1, 6):
        x, y = hs.get(f"period{n}"), as_.get(f"period{n}")
        if x is None and y is None:
            break
        if not isinstance(x, int) or not isinstance(y, int) or x == y:
            return None
        h.append(x)
        a.append(y)
    won = sum(1 for x, y in zip(h, a, strict=True) if x > y)
    if len(h) < 3 or max(won, len(h) - won) != 3:
        return None
    return h, a


def stream_events(sport: ShadowSport) -> Iterator[tuple[int, str, dict[str, Any]]]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    try:
        for events_json, fetched_at in con.execute(
            "SELECT events_json, fetched_at FROM sofa_entity_events "
            "WHERE kind = 'last' AND events_json LIKE ?",
            (f'%"slug": "{sport.sofascore_slug}"%',),
        ):
            for e in json.loads(events_json).get("events", []):
                if isinstance(e.get("id"), int):
                    yield int(e["id"]), str(fetched_at), e
        for eid, fetched_at, ej in con.execute(
            "SELECT event_id, fetched_at, event_json FROM sofa_listed_event "
            "WHERE sport = ?",
            (sport.sofascore_slug,),
        ):
            yield int(eid), str(fetched_at) + "~index", json.loads(ej)
    finally:
        con.close()


def load_sport(
    sport: ShadowSport,
) -> tuple[list[dict[str, Any]], dict[int, FootballResult], dict[int, vpm.VbMatch]]:
    """Compact rows (the state rebuild's input), rating results and
    volleyball matches; per event the newest fetch wins (the index's copy
    replaces a page's when fetched strictly later, as load_events)."""
    best: dict[int, str] = {}
    rows: dict[int, dict[str, Any]] = {}
    results: dict[int, FootballResult] = {}
    vb: dict[int, vpm.VbMatch] = {}
    for eid, fetched, e in stream_events(sport):
        index = fetched.endswith("~index")
        stamp = fetched.removesuffix("~index")
        # a later page overwrites (load_events); the index's copy only when
        # fetched strictly later than what the pages gave
        if index and eid in best and stamp <= best[eid]:
            continue
        best[eid] = stamp
        c = compact(e)
        if c is None:
            continue
        c["sport"] = sport.sofascore_slug
        rows[eid] = c
        r = sm.parse_event(e, sport, golden_set=True)
        if r is None:
            results.pop(eid, None)
        else:
            results[eid] = r
        if sport.key == "volleyball":
            sets = vb_sets(e)
            st = e.get("status") or {}
            ok = (
                sets is not None
                and st.get("type") == "finished"
                and not is_friendly_event(e)
            )
            if ok and sets is not None:
                ut = (e.get("tournament") or {}).get("uniqueTournament") or {}
                vb[eid] = vpm.VbMatch(
                    eid,
                    int(e["startTimestamp"]),
                    int(ut.get("id", (e.get("tournament") or {}).get("id", -1))),
                    int(e["homeTeam"]["id"]),
                    int(e["awayTeam"]["id"]),
                    sofascore_gender(e) == "W",
                    tuple(sets[0]),
                    tuple(sets[1]),
                )
            else:
                vb.pop(eid, None)
    out_rows = [r for r in rows.values() if r["ts"] > 1500000000]
    out_rows.sort(key=lambda r: r["id"])
    return out_rows, results, vb


# ---------------------------------------------------------------------------
# record: states (states.py's rule, per game) and the placebo exposure
# ---------------------------------------------------------------------------


def game_states(
    rows: list[dict[str, Any]],
    rules: ModuleType,
    sport_slug: str,
    keep: set[tuple[str, int, int]],
) -> dict[int, dict[str, Any]]:
    """event id -> both sides' states, GP fractions, league-season, year; the
    exact walk of states.py (frozen 826dfdd0) for the kept league-seasons."""
    POST, OTHER = rules.POST, rules.OTHER
    out: dict[int, dict[str, Any]] = {}
    groups_all = rules.season_groups(rows)
    for (sport, ut, sid), allrows in groups_all.items():
        if sport != sport_slug or (sport, ut, sid) not in keep:
            continue
        g = [
            r
            for r in allrows
            if not POST.search(r["t_name"]) and not OTHER.search(r["t_name"])
        ]
        if not g:
            continue
        year = rules.start_year(min(r["ts"] for r in g))
        names = Counter(r["t_name"] for r in g).most_common()
        main = names[0][0]
        if len(names) > 1 and names[1][1] == names[0][1]:
            # a tie for the main phase: states.py takes the first-seen name,
            # which depends on row order; pinned to Aneks A's choice (G1)
            main = MAIN_PHASE_TIE.get((ut, sid), main)
            TIES.append([sport, ut, sid, [n for n, _ in names], main])
        g = [r for r in g if r["t_name"] == main]
        seen: dict[tuple[int, int, int], dict[str, Any]] = {}
        for r in sorted(g, key=lambda r: (r["st"] != "finished", r["id"])):
            seen.setdefault((r["h"], r["a"], r["ts"] // 86400), r)
        g = sorted(
            (r for r in seen.values() if r["st"] not in ("postponed", "canceled")),
            key=lambda r: r["ts"],
        )
        teams: Counter[int] = Counter()
        for r in g:
            teams[r["h"]] += 1
            teams[r["a"]] += 1
        name: dict[int, str] = {}
        for r in g:
            name[r["h"]] = r["hn"]
            name[r["a"]] = r["an"]
        conf = rules.conference_of(sport, ut, name)
        grp: dict[str, list[int]] = defaultdict(list)
        for t in teams:
            grp[(conf or {}).get(t, "ALL")].append(t)
        post = {
            t
            for r in allrows
            if POST.search(r["t_name"])
            and (not OTHER.search(r["t_name"]) or "Stanley" in r["t_name"])
            for t in (r["h"], r["a"])
        }
        K = rules.points_rule(sport, ut, len(post), conf, len(teams))
        maxpg, k = K["maxpg"], K["k"]
        fins = [r for r in g if r["st"] == "finished"]
        pts: Counter[int] = Counter()
        gp: Counter[int] = Counter()
        idx = 0
        for r in fins:
            while idx < len(fins) and fins[idx]["ts"] < r["ts"]:
                q = fins[idx]
                ph, pa = K["award"](q, sport)
                pts[q["h"]] += ph
                pts[q["a"]] += pa
                gp[q["h"]] += 1
                gp[q["a"]] += 1
                idx += 1
            pair: list[str] = []
            frac: list[float] = []
            for t in (r["h"], r["a"]):
                n_t = teams[t]
                gpt = gp[t]
                gr = n_t - gpt
                frac.append(gpt / n_t)
                if gpt < WINDOW * n_t:
                    pair.append("EARLY")
                    continue
                others = [u for u in grp[(conf or {}).get(t, "ALL")] if u != t]
                p_t = pts[t]
                can_pass = sum(
                    1 for u in others if pts[u] + maxpg * (teams[u] - gp[u]) >= p_t
                )
                beyond = sum(1 for u in others if pts[u] > p_t + maxpg * gr)
                if can_pass < k:
                    pair.append("SECURED")
                    continue
                if beyond >= k:
                    pair.append("DEAD")
                    continue
                order = sorted(others, key=lambda u: -pts[u])
                rank_in = sum(1 for u in others if pts[u] > p_t) < k
                gap = (
                    (p_t - pts[order[k - 1]]) if rank_in else (pts[order[k - 1]] - p_t)
                )
                pair.append(
                    "MUST_WIN" if abs(gap) / maxpg <= max(1.0, gr / 4) else "ALIVE"
                )
            out[r["id"]] = {
                "ut": ut,
                "sid": sid,
                "year": year,
                "home": r["h"],
                "away": r["a"],
                "sh": pair[0],
                "sa": pair[1],
                "fh": frac[0],
                "fa": frac[1],
                "ts": r["ts"],
                "women": r.get("gender") == "F",
                "ut_name": r.get("ut_name") or "",
            }
    # placebo: each side's state at its first window game, put on its games
    # with GP / N in [0.40, 0.60) of the same league-season
    first: dict[tuple[int, int, int], str] = {}
    for eid in sorted(out, key=lambda e: out[e]["ts"]):
        g2 = out[eid]
        for side, st, fr in (
            ("home", g2["sh"], g2["fh"]),
            ("away", g2["sa"], g2["fa"]),
        ):
            key = (g2[side], g2["ut"], g2["sid"])
            if st != "EARLY" and key not in first:
                first[key] = st
    for g2 in out.values():
        for side, fr, pk in (("home", g2["fh"], "ph"), ("away", g2["fa"], "pa")):
            key = (g2[side], g2["ut"], g2["sid"])
            g2[pk] = first.get(key, "ALIVE") if 0.40 <= fr < 0.60 else "ALIVE"
    return out


# ---------------------------------------------------------------------------
# record: the score model walk (hockey / basketball) and the rally model walk
# ---------------------------------------------------------------------------


def walk_score_model(
    sport: ShadowSport, results: dict[int, FootballResult], wanted: set[int]
) -> dict[int, dict[str, Any]]:
    """walk_forward_rows' loop with today's switches: each wanted game's
    regulation centres from a model built strictly before it (rebuilt every
    REBUILD_DAYS, learnt game by game in between), plus what its simulation
    needs (params, spread, noise, quarter length)."""
    history = sorted(results.values(), key=lambda r: (r.ts, r.event_id))
    want = [r for r in history if r.event_id in wanted]
    if not want:
        return {}
    start, end = want[0].ts, want[-1].ts + 1
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    strict = epochs.league_rate_rule(today)
    restart = epochs.league_season_restart(sport.key, today)
    fresh = sport.key == "basketball" and epochs.BB_FRESHNESS_FROM_UTC is not None
    window = [r for r in history if start <= r.ts < end]
    out: dict[int, dict[str, Any]] = {}
    model: sm.ScoreModel | None = None
    next_rebuild = start
    i = 0
    params_json: dict[str, Any] = {}
    while i < len(window):
        ts = window[i].ts
        j = i
        while j < len(window) and window[j].ts == ts:
            j += 1
        batch = window[i:j]
        if model is None or ts >= next_rebuild:
            prm = sm.empty_net_params(
                sm.overtime_params(None, sport.key, False), sport.key, False
            )
            prm = sm.late_goal_in_mean_params(prm, sport.key, False)
            model = sm.build_model(
                history,
                sport,
                ts,
                prm,
                strict_league_rate=strict,
                season_restart=restart,
            )
            next_rebuild = ts + REBUILD_DAYS * 86400
            if fresh and model.recent is None:
                model.recent = {}
            params_json = dataclasses.asdict(model.params)
        for r in batch:
            if r.event_id not in wanted:
                continue
            exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
            if exp is None:
                continue
            out[r.event_id] = {
                "mu1": exp[0],
                "mu2": exp[1],
                "period_sd": model.period_sd,
                "ref_total": model.ref_total,
                "noise": model.noise_mult(r.home_id, r.away_id, r.ts) if fresh else 1.0,
                "qmin": sm.quarter_minutes_for(r.competition_id),
                "params": params_json,
            }
        for r in batch:
            model.book.update(sm._rated_values(r, sport))
            model.note_game(r)
            if model.last_played is not None:
                model.last_played[r.home_id] = r.ts
                model.last_played[r.away_id] = r.ts
            if fresh and model.recent is not None:
                model.recent.setdefault(r.home_id, []).append(r.ts)
                model.recent.setdefault(r.away_id, []).append(r.ts)
        i = j
    return out


def walk_rally_model(
    vb: dict[int, vpm.VbMatch], wanted: set[int]
) -> dict[int, dict[str, Any]]:
    matches = sorted(vb.values(), key=lambda m: (m.ts, m.event_id))
    fc = vpm.walk_forward(matches, wanted, vpp.PARAMS)
    return {
        e: {"mu": f.mu, "var": f.var, "sideout": f.sideout, "women": f.women}
        for e, f in fc.items()
    }


def phase_record(sport_key: str, work: Path) -> int:
    rules = frozen_rules()
    sport = next(v for k, v in SPORTS.items() if k == sport_key)
    keep = {
        (s, int(u), int(i))
        for s, u, i in json.loads((RUN / "keep_aneksA.json").read_text())
    }
    snapshot = datetime.now(UTC).isoformat()
    rows, results, vb = load_sport(sport)
    states = game_states(rows, rules, sport.sofascore_slug, keep)
    # G1: the per-game rebuild reproduces Aneks A's counts
    got: dict[str, list[int]] = {"dev": [0, 0, 0, 0], "exam": [0, 0, 0, 0]}
    order = ("MUST_WIN", "ALIVE", "SECURED", "DEAD")
    for g in states.values():
        part = (
            "dev"
            if g["year"] in DEV_YEARS
            else ("exam" if g["year"] == EXAM_YEAR else None)
        )
        if part is None:
            continue
        for s in (g["sh"], g["sa"]):
            if s in order:
                got[part][order.index(s)] += 1
    check = {p: (tuple(v) == ANEKS_A[sport_key][p]) for p, v in got.items()}
    wanted = {e for e, g in states.items() if g["year"] in (*DEV_YEARS, EXAM_YEAR)}
    if sport_key == "volleyball":
        model = walk_rally_model(vb, wanted & set(vb))
    else:
        model = walk_score_model(sport, results, wanted & set(results))
    dev: list[dict[str, Any]] = []
    exam: list[dict[str, Any]] = []
    sealed: list[dict[str, Any]] = []
    missing = Counter[str]()
    for eid in sorted(wanted):
        g = states[eid]
        m = model.get(eid)
        if m is None:
            missing["no model centre"] += 1
            continue
        if sport_key == "volleyball":
            vm = vb[eid]
            outc: dict[str, Any] = {
                "sets_h": list(vm.home_sets),
                "sets_a": list(vm.away_sets),
            }
        else:
            r = results[eid]
            reg = r.values[sm.REG_METRIC[sport_key]]
            fin = r.final
            outc = {
                "yh": reg[0],
                "ya": reg[1],
                "fh": fin[0] if fin else None,
                "fa": fin[1] if fin else None,
            }
        row = {"id": eid, **g, **m}
        if g["year"] == EXAM_YEAR:
            exam.append(row)
            sealed.append({"id": eid, **outc})
        else:
            dev.append({**row, **outc})
    work.mkdir(parents=True, exist_ok=True)
    write_gz(work / f"{sport_key}_dev.jsonl.gz", dev)
    write_gz(work / f"{sport_key}_exam_centres.jsonl.gz", exam)
    write_gz(work / f"{sport_key}_exam_outcomes.SEALED.jsonl.gz", sealed)
    meta = {
        "sport": sport_key,
        "snapshot_utc": snapshot,
        "events_rows": len(rows),
        "state_counts": got,
        "aneks_a_match": check,
        "dev_rows": len(dev),
        "exam_rows": len(exam),
        "missing": dict(missing),
        "main_phase_ties": TIES,
    }
    (work / f"{sport_key}_record.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))
    return 0 if all(check.values()) else 1


# ---------------------------------------------------------------------------
# the term
# ---------------------------------------------------------------------------


def coef_index(state: str, role: str) -> int | None:
    if state not in STATES:
        return None
    return STATES.index(state) + (0 if role == "own" else 3)


def side_t(beta: F64, own: str, opp: str) -> float:
    t = 0.0
    i = coef_index(own, "own")
    if i is not None:
        t += float(beta[i])
    i = coef_index(opp, "opp")
    if i is not None:
        t += float(beta[i])
    return t


def design(
    rows: list[dict[str, Any]], key_h: str = "sh", key_a: str = "sa"
) -> tuple[F64, F64, F64, list[tuple[int, int, int]], list[int]]:
    """Two rows per game (home, away): X (own x3, opp x3), y, centre,
    FE key (team, ut, sid) and cluster (team)."""
    n = 2 * len(rows)
    X = np.zeros((n, 6))
    y = np.zeros(n)
    mu = np.zeros(n)
    fe: list[tuple[int, int, int]] = []
    cl: list[int] = []
    for i, r in enumerate(rows):
        for k, (own, opp, yy, c, team) in enumerate(
            (
                (r[key_h], r[key_a], r.get("yh", 0.0), sum(r["mu1"]), r["home"]),
                (r[key_a], r[key_h], r.get("ya", 0.0), sum(r["mu2"]), r["away"]),
            )
        ):
            row = 2 * i + k
            j = coef_index(own, "own")
            if j is not None:
                X[row, j] = 1.0
            j = coef_index(opp, "opp")
            if j is not None:
                X[row, j] = 1.0
            y[row] = float(yy)
            mu[row] = max(float(c), 1e-6)
            fe.append((int(team), int(r["ut"]), int(r["sid"])))
            cl.append(int(team))
    return X, y, mu, fe, cl


def fit_poisson_fe(
    X: F64,
    y: F64,
    mu: F64,
    fe: list[tuple[int, int, int]],
    cl: list[int],
    iters: int = 60,
) -> tuple[F64, F64]:
    """Poisson with offset log(mu) and team-season fixed effects (closed-form
    FE, beta by Newton, alternating); cluster-robust (team) covariance of
    beta with the FE partialled out."""
    codes: dict[tuple[int, int, int], int] = {}
    g = np.array([codes.setdefault(k, len(codes)) for k in fe])
    G = len(codes)
    beta = np.zeros(X.shape[1])
    a = np.zeros(G)
    active = X.any(axis=0)
    for _ in range(iters):
        eta0 = np.log(mu) + X @ beta
        num = np.bincount(g, weights=y, minlength=G)
        den = np.bincount(g, weights=np.exp(eta0), minlength=G)
        a = np.log(np.maximum(num, 1e-9) / np.maximum(den, 1e-12))
        lam = np.exp(eta0 + a[g])
        Xa = X[:, active]
        # partial the FE out of the Hessian (weighted within transform)
        wsum = np.bincount(g, weights=lam, minlength=G)
        xbar = (
            np.vstack(
                [
                    np.bincount(g, weights=lam * Xa[:, j], minlength=G)
                    for j in range(Xa.shape[1])
                ]
            ).T
            / np.maximum(wsum, 1e-12)[:, None]
        )
        Xt = Xa - xbar[g]
        H = Xt.T @ (Xt * lam[:, None])
        score = Xt.T @ (y - lam)
        step = np.linalg.solve(H + 1e-9 * np.eye(H.shape[0]), score)
        beta[active] += step
        if np.max(np.abs(step)) < 1e-9:
            break
    eta0 = np.log(mu) + X @ beta
    lam = np.exp(eta0 + a[g])
    Xa = X[:, active]
    wsum = np.bincount(g, weights=lam, minlength=G)
    xbar = (
        np.vstack(
            [
                np.bincount(g, weights=lam * Xa[:, j], minlength=G)
                for j in range(Xa.shape[1])
            ]
        ).T
        / np.maximum(wsum, 1e-12)[:, None]
    )
    Xt = Xa - xbar[g]
    H = Xt.T @ (Xt * lam[:, None])
    Hi = np.linalg.inv(H + 1e-9 * np.eye(H.shape[0]))
    cid: dict[int, int] = {}
    c = np.array([cid.setdefault(k, len(cid)) for k in cl])
    S = np.zeros((len(cid), Xa.shape[1]))
    np.add.at(S, c, Xt * (y - lam)[:, None])
    V_a = Hi @ (S.T @ S) @ Hi
    V = np.zeros((X.shape[1], X.shape[1]))
    idx = np.where(active)[0]
    V[np.ix_(idx, idx)] = V_a
    for j in np.where(~active)[0]:
        V[j, j] = 1e6
    return beta, V


def vb_share(d: F64, so: F64) -> F64:
    pa = 1 / (1 + np.exp(-(np.log((1 - so) / so) + d)))
    pb = 1 / (1 + np.exp(-(np.log(so / (1 - so)) + d)))
    pi = pb / (1 - pa + pb)
    return np.asarray(pi * pa + (1 - pi) * pb, dtype=float)


def vb_design(
    rows: list[dict[str, Any]], key_h: str = "sh", key_a: str = "sa"
) -> tuple[F64, F64, F64, F64, F64, list[int]]:
    """One row per match (home): Z = dt/dbeta of d' = mu + t_h - t_a
    (own and opp enter as own(h) - own(a) + opp(a) - opp(h))."""
    n = len(rows)
    Z = np.zeros((n, 6))
    ph = np.zeros(n)
    tot = np.zeros(n)
    mu = np.zeros(n)
    so = np.zeros(n)
    cl: list[int] = []
    for i, r in enumerate(rows):
        for st, role, sgn in (
            (r[key_h], "own", 1.0),
            (r[key_a], "opp", 1.0),
            (r[key_a], "own", -1.0),
            (r[key_h], "opp", -1.0),
        ):
            j = coef_index(st, role)
            if j is not None:
                Z[i, j] += sgn
        if "sets_h" in r:
            ph[i] = sum(r["sets_h"])
            tot[i] = sum(r["sets_h"]) + sum(r["sets_a"])
        mu[i] = r["mu"]
        so[i] = r["sideout"]
        cl.append(int(r["home"]))
    return Z, ph, tot, mu, so, cl


def fit_vb(
    Z: F64, ph: F64, tot: F64, mu: F64, so: F64, cl: list[int]
) -> tuple[F64, F64]:
    """Binomial points share = stationary_share(mu + Z beta): Gauss-Newton;
    own and opp enter only through own - opp (pairwise logit), so the fit is
    on the identifiable margin with sum 0 (beta_opp = -beta_own)."""
    D = np.hstack([Z[:, :3] - Z[:, 3:]]) / 2.0  # gamma_s = beta_own - beta_opp
    g = np.zeros(3)
    for _ in range(100):
        d = mu + D @ g
        s = vb_share(d, so)
        eps = 1e-4
        h = (vb_share(d + eps, so) - vb_share(d - eps, so)) / (2 * eps)
        w = tot / np.maximum(s * (1 - s), 1e-9)
        J = D * h[:, None]
        H = J.T @ (J * w[:, None])
        sc = J.T @ (w * (ph / np.maximum(tot, 1) - s))
        step = np.linalg.solve(H + 1e-9 * np.eye(3), sc)
        g += step
        if np.max(np.abs(step)) < 1e-10:
            break
    d = mu + D @ g
    s = vb_share(d, so)
    h = (vb_share(d + 1e-4, so) - vb_share(d - 1e-4, so)) / 2e-4
    w = tot / np.maximum(s * (1 - s), 1e-9)
    J = D * h[:, None]
    H = J.T @ (J * w[:, None])
    Hi = np.linalg.inv(H + 1e-9 * np.eye(3))
    cid: dict[int, int] = {}
    c = np.array([cid.setdefault(k, len(cid)) for k in cl])
    S = np.zeros((len(cid), 3))
    np.add.at(S, c, J * (w * (ph / np.maximum(tot, 1) - s))[:, None])
    Vg = Hi @ (S.T @ S) @ Hi
    beta = np.concatenate([g, -g])
    # cov of (g, -g)
    V = np.block([[Vg, -Vg], [-Vg, Vg]])
    return beta, V


def fit(
    sport: str, rows: list[dict[str, Any]], key_h: str = "sh", key_a: str = "sa"
) -> tuple[F64, F64]:
    if sport == "volleyball":
        Z, ph, tot, mu, so, cl = vb_design(rows, key_h, key_a)
        return fit_vb(Z, ph, tot, mu, so, cl)
    X, y, mu2, fe, cl2 = design(rows, key_h, key_a)
    return fit_poisson_fe(X, y, mu2, fe, cl2)


def shrink(beta: F64, V: F64, tau: float) -> F64:
    se2 = np.diag(V)
    return np.asarray(beta * tau**2 / (tau**2 + se2), dtype=float)


# ---------------------------------------------------------------------------
# simulations and the per-game scores
# ---------------------------------------------------------------------------


def simulate_game(sport: str, r: dict[str, Any], beta: F64 | None) -> dict[str, Any]:
    """The game's simulation in one arm (beta None = base), seeded by its id."""
    th = side_t(beta, r["sh"], r["sa"]) if beta is not None else 0.0
    ta = side_t(beta, r["sa"], r["sh"]) if beta is not None else 0.0
    if sport == "volleyball":
        f = vpm.VbForecast(r["mu"] + th - ta, r["var"], r["sideout"], r["women"])
        sim = vpm.simulate(f, vpp.PARAMS, N_SIMS, seed=int(r["id"]))
        pts = sim.points.sum(axis=(1, 2)).astype(float)
        hw = (sim.points[:, :, 0] > sim.points[:, :, 1]).sum(axis=1)
        aw = (sim.points[:, :, 1] > sim.points[:, :, 0]).sum(axis=1)
        cats = Counter(zip(hw.tolist(), aw.tolist(), strict=True))
        return {
            "tot_mean": float(pts.mean()),
            "tot_sd": float(pts.std() + 1e-6),
            "p_home": float((hw > aw).mean()),
            "sets": {f"{a}-{b}": c / N_SIMS for (a, b), c in cats.items()},
            "tot": pts,
        }
    kw: dict[str, Any] = {
        k: (tuple(v) if isinstance(v, list) else v) for k, v in r["params"].items()
    }
    prm = sm.SimParams(**kw)
    mu1 = [m * math.exp(th) for m in r["mu1"]]
    mu2 = [m * math.exp(ta) for m in r["mu2"]]
    rng = random.Random(int(r["id"]))
    if sport == "hockey":
        games = [sm._hockey(rng, mu1, mu2, prm) for _ in range(N_SIMS)]
    else:
        sd = r["period_sd"] * r["noise"]
        if r["noise"] != 1.0 and prm.bb_game_sd is not None:
            prm = dataclasses.replace(
                prm,
                bb_game_sd=prm.bb_game_sd * r["noise"],
                bb_team_sd=prm.bb_team_sd * r["noise"],
                bb_quarter_sd=prm.bb_quarter_sd * r["noise"],
            )
        level = sum(mu1) + sum(mu2)
        if prm.bb_sd_level_power and r["ref_total"] > 0 and level > 0:
            fct = (level / r["ref_total"]) ** prm.bb_sd_level_power
            sd *= fct
            if prm.bb_game_sd is not None:
                prm = dataclasses.replace(
                    prm,
                    bb_game_sd=prm.bb_game_sd * fct,
                    bb_team_sd=prm.bb_team_sd * fct,
                    bb_quarter_sd=prm.bb_quarter_sd * fct,
                )
        games = [
            sm._basketball(rng, mu1, mu2, sd, prm, r["qmin"]) for _ in range(N_SIMS)
        ]
    h = np.array([sum(gm.t1_periods) for gm in games], dtype=float)
    a = np.array([sum(gm.t2_periods) for gm in games], dtype=float)
    fh = np.array([gm.t1_full for gm in games], dtype=float)
    fa = np.array([gm.t2_full for gm in games], dtype=float)
    return {
        "h_mean": float(h.mean()),
        "h_sd": float(h.std() + 1e-6),
        "a_mean": float(a.mean()),
        "a_sd": float(a.std() + 1e-6),
        "p1": float((h > a).mean()),
        "px": float((h == a).mean()),
        "p2": float((h < a).mean()),
        "p_home": float((fh > fa).mean()),
        "tot": h + a,
        "mu_h": sum(mu1),
        "mu_a": sum(mu2),
        "disp": prm.hk_disp,
    }


def nb_logpmf(y: float, m: float, disp: float) -> float:
    if disp <= 0:
        return y * math.log(max(m, 1e-12)) - m - math.lgamma(y + 1)
    r = 1.0 / disp
    return (
        math.lgamma(y + r)
        - math.lgamma(r)
        - math.lgamma(y + 1)
        + r * math.log(r / (r + m))
        + y * math.log(max(m, 1e-12) / (r + m))
    )


def norm_logpdf(y: float, m: float, s: float) -> float:
    return -0.5 * math.log(2 * math.pi * s * s) - (y - m) ** 2 / (2 * s * s)


def bin_ll(p: float, y: int) -> float:
    return -(math.log(p) if y else math.log(1 - p))


def clip(p: float) -> float:
    return min(max(p, 1e-6), 1 - 1e-6)


def game_scores(
    sport: str, r: dict[str, Any], o: dict[str, Any], sim: dict[str, Any]
) -> dict[str, float]:
    """Negative log score of each group's primary metric for one game."""
    if sport == "volleyball":
        hs, as_ = o["sets_h"], o["sets_a"]
        tot = float(sum(hs) + sum(as_))
        hw = sum(1 for x, y in zip(hs, as_, strict=True) if x > y)
        aw = len(hs) - hw
        p_home = clip(sim["p_home"])
        p_sets = clip(sim["sets"].get(f"{hw}-{aw}", 0.0))
        return {
            "vb_points": -norm_logpdf(tot, sim["tot_mean"], sim["tot_sd"]),
            "vb_result": -(math.log(p_home) if hw > aw else math.log(1 - p_home))
            - math.log(p_sets),
        }
    yh, ya = float(o["yh"]), float(o["ya"])
    if sport == "hockey":
        pts = -(
            nb_logpmf(yh, sim["mu_h"], sim["disp"])
            + nb_logpmf(ya, sim["mu_a"], sim["disp"])
        )
        k = "p1" if yh > ya else ("px" if yh == ya else "p2")
        return {"hk_goals": pts, "hk_result": -math.log(clip(sim[k]))}
    pts = -(
        norm_logpdf(yh, sim["h_mean"], sim["h_sd"])
        + norm_logpdf(ya, sim["a_mean"], sim["a_sd"])
    )
    fh, fa = o.get("fh"), o.get("fa")
    won = (fh > fa) if fh is not None and fa is not None else yh > ya
    p = clip(sim["p_home"])
    return {"bb_points": pts, "bb_result": -(math.log(p) if won else math.log(1 - p))}


def line_event(
    sport: str, group: str, r: dict[str, Any], o: dict[str, Any], line: float
) -> int:
    if sport == "volleyball":
        hs, as_ = o["sets_h"], o["sets_a"]
        if group == "vb_points":
            return int(sum(hs) + sum(as_) > line)
        return int(sum(1 for x, y in zip(hs, as_, strict=True) if x > y) == 3)
    yh, ya = float(o["yh"]), float(o["ya"])
    if group in ("hk_goals", "bb_points"):
        return int(yh + ya > line)
    if group == "hk_result":
        return int(yh > ya)
    fh, fa = o.get("fh"), o.get("fa")
    return int((fh > fa) if fh is not None and fa is not None else yh > ya)


def line_p(group: str, sim: dict[str, Any], line: float) -> float:
    if group in ("hk_goals", "bb_points", "vb_points"):
        return float((sim["tot"] > line).mean())
    if group == "hk_result":
        return float(sim["p1"])
    return float(sim["p_home"])


def base_line(group: str, base_sim: dict[str, Any]) -> float:
    if group in ("hk_goals", "bb_points", "vb_points"):
        return math.floor(float(base_sim["tot"].mean())) + 0.5
    return 0.0


def in_window(r: dict[str, Any]) -> bool:
    return bool(r["sh"] != "EARLY" or r["sa"] != "EARLY")


# ---------------------------------------------------------------------------
# curves (dev) and the bootstrap
# ---------------------------------------------------------------------------


def fit_curve(p: F64, y: F64) -> list[float | None]:
    nb = int(round(1 / BUCKET))
    b = np.minimum((p / BUCKET).astype(int), nb - 1)
    out: list[float | None] = []
    for k in range(nb):
        m = b == k
        out.append(float(y[m].mean()) if m.sum() >= MIN_BUCKET_ROWS else None)
    return out


def apply_curve(curve: list[float | None], p: float) -> float:
    k = min(int(p / BUCKET), len(curve) - 1)
    v = curve[k]
    return min(max(p if v is None else v, 0.005), 0.995)


def cluster_boot(
    values: F64,
    home: list[int],
    away: list[int],
    reps: int = REPS,
    seed: int = 20261118,
) -> F64:
    """Pigeonhole two-way bootstrap of the mean (home team x away team)."""
    rng = np.random.default_rng(seed)
    hid: dict[int, int] = {}
    aid: dict[int, int] = {}
    h = np.array([hid.setdefault(x, len(hid)) for x in home])
    a = np.array([aid.setdefault(x, len(aid)) for x in away])
    out = np.zeros(reps)
    for k in range(reps):
        wh = rng.multinomial(len(hid), np.full(len(hid), 1 / len(hid)))
        wa = rng.multinomial(len(aid), np.full(len(aid), 1 / len(aid)))
        w = wh[h] * wa[a]
        out[k] = float((w * values).sum() / max(w.sum(), 1))
    return out


def one_sided_p(boot: F64) -> float:
    return max(float((boot >= 0).mean()), 1 / len(boot))


def holm(pv: dict[str, float]) -> dict[str, bool]:
    order = sorted(pv, key=lambda k: pv[k])
    out: dict[str, bool] = {}
    ok = True
    for i, k in enumerate(order):
        ok = ok and pv[k] <= ALPHA / (len(order) - i)
        out[k] = ok
    return out


# ---------------------------------------------------------------------------
# estimate (dev only)
# ---------------------------------------------------------------------------


def permute_states(
    rows: list[dict[str, Any]], rng: np.random.Generator
) -> list[dict[str, Any]]:
    """S1: side states permuted within league-season x ISO week."""
    cells: dict[tuple[int, int, int, int], list[tuple[int, str]]] = defaultdict(list)
    for i, r in enumerate(rows):
        wk = datetime.fromtimestamp(r["ts"], UTC).isocalendar()
        key = (r["ut"], r["sid"], wk[0], wk[1])
        cells[key].append((i, "sh"))
        cells[key].append((i, "sa"))
    new = [dict(r) for r in rows]
    for slots in cells.values():
        vals = [rows[i][k] for i, k in slots]
        perm = rng.permutation(len(vals))
        for (i, k), j in zip(slots, perm, strict=True):
            new[i][k] = vals[j]
    return new


def wald(beta: F64, V: F64) -> float:
    idx = [j for j in range(len(beta)) if V[j, j] < 1e5]
    b = beta[idx]
    Vi = np.linalg.pinv(V[np.ix_(idx, idx)])
    return float(b @ Vi @ b)


def phase_estimate(work: Path) -> int:
    frozen_rules()
    out: dict[str, Any] = {
        "study": STUDY,
        "created_utc": datetime.now(UTC).isoformat(),
        "spec": "646b1317 + Aneks A 32ba661e",
        "sports": {},
    }
    curves: dict[str, Any] = {}
    for sport in ("hockey", "basketball", "volleyball"):
        path = work / f"{sport}_dev.jsonl.gz"
        if not path.exists():
            print(f"{sport}: no dev rows", file=sys.stderr)
            continue
        rows = read_gz(path)
        beta, V = fit(sport, rows)
        se = np.sqrt(np.diag(V))
        bshr = shrink(beta, V, TAU[sport])
        # S1 permutation
        rng = np.random.default_rng(7)
        w0 = wald(beta, V)
        perm_stats = []
        for _ in range(PERMS):
            pb, _pv = fit(sport, permute_states(rows, rng))
            perm_stats.append(wald(pb, V))
        s1_p = (1 + sum(1 for s in perm_stats if s >= w0)) / (PERMS + 1)
        # S2 placebo
        pbeta, _pV = fit(sport, rows, "ph", "pa")
        material = [j for j in range(6) if abs(bshr[j]) >= C_SPORT[sport]]
        s2 = all(abs(pbeta[j]) < 0.5 * abs(beta[j]) for j in material)
        # S3 margin signs
        margin = {s: float(bshr[i] - bshr[i + 3]) for i, s in enumerate(STATES)}
        s3 = all(margin[s] * SIGN[s] > 0 for s in STATES)
        # S4 leave one season out, per group; curves on dev for P3 / P4
        # S4: leave one dev season out; one base and one treat simulation per
        # window game serve both groups of the sport
        base_cache: dict[int, dict[str, Any]] = {}
        sums = {g: [0.0, 0] for g in GROUPS[sport]}
        for yr in DEV_YEARS:
            trn = [r for r in rows if r["year"] != yr]
            b_f, v_f = fit(sport, trn)
            b_fs = shrink(b_f, v_f, TAU[sport])
            for r in rows:
                if r["year"] != yr or not in_window(r):
                    continue
                bs = base_cache.get(r["id"])
                if bs is None:
                    bs = base_cache[r["id"]] = simulate_game(sport, r, None)
                tr = simulate_game(sport, r, b_fs)
                sb, st_ = game_scores(sport, r, r, bs), game_scores(sport, r, r, tr)
                for g in GROUPS[sport]:
                    sums[g][0] += st_[g] - sb[g]
                    sums[g][1] += 1
        s4 = {g: {"delta": v[0] / max(v[1], 1), "games": v[1]} for g, v in sums.items()}
        win = [r for r in rows if in_window(r)]
        pre = s1_p < 0.05 and s2 and s3
        # dev curves of both arms (only needed for a sport that can submit)
        cv: dict[str, Any] = {}
        if pre and any(s4[g]["delta"] < 0 for g in GROUPS[sport]):
            acc: dict[str, tuple[list[float], list[float], list[float]]] = {
                g: ([], [], []) for g in GROUPS[sport]
            }
            for r in win:
                bs = base_cache.get(r["id"]) or simulate_game(sport, r, None)
                ts_ = simulate_game(sport, r, bshr)
                for g in GROUPS[sport]:
                    line = base_line(g, bs)
                    acc[g][0].append(line_p(g, bs, line))
                    acc[g][1].append(line_p(g, ts_, line))
                    acc[g][2].append(line_event(sport, g, r, r, line))
            for g, (pb_, pt_, yy) in acc.items():
                y_a = np.array(yy, dtype=float)
                cv[g] = {
                    "base": fit_curve(np.array(pb_), y_a),
                    "treat": fit_curve(np.array(pt_), y_a),
                }
        curves[sport] = cv
        s5 = True  # Aneks A: exam exposed sides >= n required for c_sport (all three)
        gates = {
            g: {
                "S1_p": s1_p,
                "S1": s1_p < 0.05,
                "S2": s2,
                "S3": s3,
                "S4": s4[g]["delta"] < 0,
                "S5": s5,
            }
            for g in GROUPS[sport]
        }
        for g in GROUPS[sport]:
            gates[g]["submitted"] = all(
                gates[g][k] for k in ("S1", "S2", "S3", "S4", "S5")
            )
        out["sports"][sport] = {
            "coef_names": [f"own_{s}" for s in STATES] + [f"opp_{s}" for s in STATES],
            "beta_raw": beta.tolist(),
            "se": se.tolist(),
            "beta_frozen": bshr.tolist(),
            "tau": TAU[sport],
            "c_sport": C_SPORT[sport],
            "placebo_beta": pbeta.tolist(),
            "margin_frozen": margin,
            "s1_wald": w0,
            "s4": s4,
            "gates": gates,
            "dev_games": len(rows),
            "dev_window_games": len(win),
            "unit": (
                "d (rally logit), own - opp only"
                if sport == "volleyball"
                else "log of the regulation centre"
            ),
        }
        print(json.dumps({sport: out["sports"][sport]["gates"]}))
    RUN.mkdir(parents=True, exist_ok=True)
    cpath, kpath = RUN / "coefficients_frozen.json", RUN / "curves_dev.json"
    cpath.write_text(json.dumps(out, indent=1))
    kpath.write_text(json.dumps(curves))
    rec = {
        "study": STUDY,
        "frozen_utc": datetime.now(UTC).isoformat(),
        "coefficients_frozen.json": sha256(cpath),
        "curves_dev.json": sha256(kpath),
        "exam_outcomes_opened": False,
    }
    (RUN / "freeze_record.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))
    return 0


# ---------------------------------------------------------------------------
# exam (once)
# ---------------------------------------------------------------------------


JUNIOR = ("U2", "U1", "Junior", "Juniors", "Jun.", "Youth", "U-2", "U-1")


def strata_of(sport: str, r: dict[str, Any]) -> list[str]:
    s = []
    if r.get("women"):
        s.append("women")
    if (sport, r["ut"]) in (("hockey", 234), ("basketball", 132)):
        s.append("NHL/NBA")
    else:
        s.append("not NHL/NBA")
    if any(k in r.get("ut_name", "") for k in JUNIOR):
        s.append("junior")
    return s


def exam_already_run() -> bool:
    return EXAM_LOG.exists() and any(
        f"| {STUDY} |" in ln for ln in EXAM_LOG.read_text().splitlines()
    )


def phase_exam(work: Path, spec_sha: str) -> int:
    frozen_rules()
    if exam_already_run():
        print(
            f"refused: {EXAM_LOG} already holds a line of {STUDY} (G2)", file=sys.stderr
        )
        return 2
    subprocess.run(
        ["git", "cat-file", "-e", f"{spec_sha}^{{commit}}"], cwd=REPO, check=True
    )
    rec = json.loads((RUN / "freeze_record.json").read_text())
    for name in ("coefficients_frozen.json", "curves_dev.json"):
        if sha256(RUN / name) != rec[name]:
            raise SystemExit(f"G1: {name} changed after the freeze record")
    coef = json.loads((RUN / "coefficients_frozen.json").read_text())
    curves = json.loads((RUN / "curves_dev.json").read_text())
    res: dict[str, Any] = {
        "study": STUDY,
        "spec_sha": spec_sha,
        "freeze_record": rec,
        "opened_utc": datetime.now(UTC).isoformat(),
        "groups": {},
    }
    pvals: dict[str, float] = {}
    if not any(
        gate["submitted"]
        for cs in coef["sports"].values()
        for gate in cs["gates"].values()
    ):
        # K = 0: no group passed S1-S5 on dev, so every verdict is fixed
        # (NOT_SUBMITTED) and the pass rule has nothing to test; the sealed
        # exam outcomes stay unopened (the conservative reading, a deviation)
        verdicts0 = {
            g: "NOT_SUBMITTED" for cs in coef["sports"].values() for g in cs["gates"]
        }
        res.update(
            {
                "verdicts": verdicts0,
                "holm_K": 0,
                "exam_outcomes_opened": False,
                "note": "no group submitted; sealed exam outcomes not opened",
            }
        )
        (RUN / "exam_result.json").write_text(json.dumps(res, indent=1))
        rec["exam_outcomes_opened"] = False
        rec["exam_closed_utc"] = res["opened_utc"]
        (RUN / "freeze_record.exam.json").write_text(json.dumps(rec, indent=1))
        append_log(
            res["opened_utc"], spec_sha, rec, verdicts0, "K=0, egzamin nieotwarty"
        )
        print(json.dumps(verdicts0))
        return 0
    for sport, cs in coef["sports"].items():
        beta = np.array(cs["beta_frozen"])
        rows = read_gz(work / f"{sport}_exam_centres.jsonl.gz")
        outc = {
            o["id"]: o for o in read_gz(work / f"{sport}_exam_outcomes.SEALED.jsonl.gz")
        }
        rows = [{**r, **outc[r["id"]]} for r in rows if r["id"] in outc]
        win = [r for r in rows if in_window(r)]
        sims = {
            r["id"]: (simulate_game(sport, r, None), simulate_game(sport, r, beta))
            for r in win
        }
        home = [r["home"] for r in win]
        away = [r["away"] for r in win]
        deltas: dict[str, F64] = {}
        for grp in GROUPS[sport]:
            deltas[grp] = np.array(
                [
                    game_scores(sport, r, r, sims[r["id"]][1])[grp]
                    - game_scores(sport, r, r, sims[r["id"]][0])[grp]
                    for r in win
                ]
            )
        # P6: refit on the exam season (descriptive)
        b6, _v6 = fit(sport, rows)
        b_dev = np.array(cs["beta_frozen"])
        material = [j for j in range(6) if abs(b_dev[j]) >= C_SPORT[sport]]
        p6 = (
            all(np.sign(b6[j]) == np.sign(b_dev[j]) for j in material)
            if material
            else False
        )
        # P2: material state with >= 2% of the exam window sides
        sides = Counter([r["sh"] for r in win] + [r["sa"] for r in win])
        n_sides = 2 * len(win)
        p2_states = []
        for i, s in enumerate(STATES):
            share = sides[s] / max(n_sides, 1)
            if share < P2_MIN_SHARE:
                continue
            if sport == "volleyball":
                dp = [
                    abs(sims[r["id"]][1]["p_home"] - sims[r["id"]][0]["p_home"])
                    for r in win
                    if s in (r["sh"], r["sa"])
                ]
                if dp and float(np.mean(dp)) >= 0.01:
                    p2_states.append(s)
            elif abs(b_dev[i]) >= C_SPORT[sport] or abs(b_dev[i + 3]) >= C_SPORT[sport]:
                p2_states.append(s)
        for grp in GROUPS[sport]:
            gate = cs["gates"][grp]
            d = deltas[grp]
            entry: dict[str, Any] = {
                "sport": sport,
                "submitted": gate["submitted"],
                "games": len(win),
                "delta": float(d.mean()) if len(d) else 0.0,
            }
            boot = cluster_boot(d, home, away)
            entry["delta_upper95"] = float(np.quantile(boot, 0.95))
            entry["p_one_sided"] = one_sided_p(boot)
            # P3 / P4
            cv = curves.get(sport, {}).get(grp)
            p3 = p4 = False
            if cv is None:
                entry["p3_p4"] = "no dev curves (sport not submittable)"
            else:
                dl, rows4 = [], []
                for r in win:
                    bs, ts_ = sims[r["id"]]
                    line = base_line(grp, bs)
                    y = line_event(sport, grp, r, r, line)
                    pb = apply_curve(cv["base"], line_p(grp, bs, line))
                    pt = apply_curve(cv["treat"], line_p(grp, ts_, line))
                    dl.append(bin_ll(pt, y) - bin_ll(pb, y))
                    for pbd, ptd, yd in ((pb, pt, y), (1 - pb, 1 - pt, 1 - y)):
                        if pbd >= 0.70:
                            rows4.append((pbd, ptd, yd))
                dl_a = np.array(dl)
                bl = cluster_boot(dl_a, home, away)
                entry["p3_delta_line"] = float(dl_a.mean())
                entry["p3_upper95"] = float(np.quantile(bl, 0.95))
                p3 = entry["p3_delta_line"] <= 0 and entry["p3_upper95"] < P3_UPPER
                if rows4:
                    a4 = np.array(rows4)
                    gb = abs(a4[:, 2].mean() - a4[:, 0].mean())
                    gt = abs(a4[:, 2].mean() - a4[:, 1].mean())
                    entry["p4"] = {
                        "rows": len(rows4),
                        "gap_base": float(gb),
                        "gap_treat": float(gt),
                    }
                    p4 = gt <= gb + P4_SLACK
                else:
                    entry["p4"] = {"rows": 0}
                    p4 = False
            # P5: the other group of the sport and the strata
            other = [g for g in GROUPS[sport] if g != grp][0]
            bo = cluster_boot(deltas[other], home, away)
            p5_other = float(np.quantile(bo, 0.95))
            strata: dict[str, Any] = {}
            p5 = p5_other < P5_GROUP_UPPER
            for sname in ("women", "NHL/NBA", "not NHL/NBA", "junior"):
                m = np.array([sname in strata_of(sport, r) for r in win])
                if m.sum() == 0:
                    continue
                bs_ = cluster_boot(
                    d[m],
                    [h for h, k in zip(home, m, strict=True) if k],
                    [a for a, k in zip(away, m, strict=True) if k],
                    reps=500,
                )
                up = float(np.quantile(bs_, 0.95))
                gating = int(m.sum()) >= P5_MIN_ROWS
                strata[sname] = {
                    "games": int(m.sum()),
                    "delta": float(d[m].mean()),
                    "upper95": up,
                    "gating": gating,
                }
                if gating and up >= P5_STRATUM_UPPER:
                    p5 = False
            entry.update(
                {
                    "p5_other_group_upper95": p5_other,
                    "strata": strata,
                    "p2_states": p2_states,
                    "p6": bool(p6),
                    "beta_exam_refit": b6.tolist(),
                    "checks": {
                        "P2": bool(p2_states),
                        "P3": bool(p3),
                        "P4": bool(p4),
                        "P5": bool(p5),
                        "P6": bool(p6),
                    },
                }
            )
            res["groups"][grp] = entry
            if gate["submitted"]:
                pvals[grp] = entry["p_one_sided"]
    passed_p1 = holm(pvals) if pvals else {}
    verdicts = {}
    for grp, e in res["groups"].items():
        if not e["submitted"]:
            verdicts[grp] = "NOT_SUBMITTED"
            continue
        e["checks"]["P1"] = bool(passed_p1.get(grp, False) and e["delta_upper95"] < 0)
        verdicts[grp] = "PASS" if all(e["checks"].values()) else "NOT_PASSED"
    res["verdicts"] = verdicts
    res["holm_K"] = len(pvals)
    (RUN / "exam_result.json").write_text(json.dumps(res, indent=1))
    rec["exam_outcomes_opened"] = res["opened_utc"]
    (RUN / "freeze_record.exam.json").write_text(json.dumps(rec, indent=1))
    append_log(res["opened_utc"], spec_sha, rec, verdicts, f"K={len(pvals)}")
    print(json.dumps(verdicts))
    return 0


def append_log(
    utc: str, spec_sha: str, rec: dict[str, Any], verdicts: dict[str, str], note: str
) -> None:
    """One line per study; created if absent, otherwise only appended."""
    if not EXAM_LOG.exists():
        EXAM_LOG.write_text(
            "# Log egzaminu: stawka meczu (G2; jedna linia na badanie)\n\n"
            "| UTC | badanie | spec SHA | sha256 współczynników | werdykty |\n"
            "|---|---|---|---|---|\n"
        )
    line = (
        f"| {utc} | {STUDY} | {spec_sha} | "
        f"{rec['coefficients_frozen.json'][:16]} | "
        + ", ".join(f"{g} {v}" for g, v in verdicts.items())
        + f" ({note}) |\n"
    )
    with EXAM_LOG.open("a") as f:
        f.write(line)
    print(line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--phase", choices=("record", "estimate", "exam"), required=True)
    ap.add_argument("--sport", choices=("hockey", "basketball", "volleyball"))
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--spec-sha", default=None)
    args = ap.parse_args(argv)
    if args.phase == "record":
        if args.sport is None:
            ap.error("--phase record needs --sport")
        return phase_record(args.sport, args.work)
    if args.phase == "estimate":
        return phase_estimate(args.work)
    if args.spec_sha is None:
        ap.error("--phase exam needs --spec-sha")
    return phase_exam(args.work, args.spec_sha)


if __name__ == "__main__":
    raise SystemExit(main())
