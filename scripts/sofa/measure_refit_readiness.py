#!/usr/bin/env python3
"""Refit readiness of the installed curves and fits (audit 2026-11-05).

Read-only evidence for docs/sofa/evidence/audyt_krzywych_refit_2026-11-05.md.
Never refits, never installs, never writes config, never asks the network.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_refit_readiness.py \\
        growth --json-out <f>
    ... drift --from 2026-10-18 --to 2026-11-04 \\
        --rows-dir data/line_evidence/rows_before_2026-11-05 --json-out <f>
    ... sizes --json-out <f>          # walks every b-tree once (dbstat), minutes
    ... tables --dir <dir of the three> --json-out <f.md>   # markdown tables

`growth`: every installed fit's `fitted_from` (rows, matches, dates) beside
what the cache holds today for the same scope. Football / tennis: listed
events per sport in the replay DB the curves were fitted from
(`fitted_from.db_path`, if still on disk) and in data/sofa.db, through the
covering index (sport, fetched_at, event_id) - fetched_at is reset by a
re-fetch, so "fetched before the fit" is not used. Measured sports: the fit's
`history_games_before` / history rows beside today's dry-run of the same fit
(`refresh_line_evidence.py` runs `fit_sport_confidence.py --dry-run` every
morning; `<sport>_section.json` of the rows dir). CS2: cs2_series / cs2_map.

`drift`: the installed curves read on settled Superbet lines since their
install - an audit, never a source. Football / tennis: every graded,
priced row of runs/sofa/<d>/07_settled.json, its p_central read through the
curve that day reads exactly as fit_line_evidence.sheet_rows reads it (per
line where the day reads per line, live-only keys dropped, class curves).
Measured sports: `<sport>_superbet_settled.jsonl` of the rows dir (the score
model's / engine's p, no price) read through the sport curve today reads,
on lines dated at or after that sport's fit `before` (out of sample for it),
and through today's dry-run curve on the lines out of sample for both. Per
cell (sport, key or family, band 0.60-0.70 / >= 0.70 of the curve value):
n, games, mean confidence, realised, realised - confidence with a 95%
interval from 1,000 bootstraps over games. The confidence is the curve
alone: the line-evidence offset / band cap is fitted on these same lines
(in sample), so it is not part of this audit.

`sizes`: pages of every table / index (`dbstat`, aggregate), the
cache-calibration rows a replay rewrites, the DB copies on disk and the free
space - the input of the disk plan. Opened read-only (`mode=ro`).

Reads no priced-rows record (tests/sofa/test_priced_rows.py).
Exit 0 measured, 2 on a crash.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import live_only_curves  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    Calibration,
    calibration_path_for,
    curve_market,
    direction_key,
    is_derived,
    match_class,
)
from bet.sofa.line_curves import day_reads_per_line, leg_line  # noqa: E402
from scripts.sofa.fit_line_evidence import (  # noqa: E402
    _board_sides,
    reads_derived_curves,
)

CONFIG = _REPO / "config"
DB = _REPO / "data" / "sofa.db"
RUNS = _REPO / "runs" / "sofa"
BANDS = (("0.60-0.70", 0.60, 0.70), (">=0.70", 0.70, 1.01))
SHEET_SPORTS = ("football", "tennis")
LISTED_SLUG = {"football": "football", "tennis": "tennis", "hockey": "ice-hockey",
               "basketball": "basketball", "volleyball": "volleyball",
               "cs2": "esports"}
B = 1000
MIN_CELL = 100  # rows; a smaller cell is listed in the JSON, not flagged
_SUFFIX = re.compile(r"(_(1h|2h))?(_(for|total|against))?$")


def family(key: str) -> str:
    """'women:corners_1h_for|OVER' -> 'women:corners'; a key's market stem."""
    klass, _, rest = key.rpartition(":")
    market = rest.split("|")[0]
    stem = _SUFFIX.sub("", market) or market
    return f"{klass}:{stem}" if klass else stem


def days(a: str, b: str) -> list[str]:
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    return [(d0 + timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]


def ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --- statistics ------------------------------------------------------------------


def boot_gap(games: list[str], resid: np.ndarray, seed: int = 7
             ) -> tuple[float, float, float]:
    """mean(resid) and a 95% interval resampling games (lines of one game
    are not independent)."""
    ids: dict[str, int] = {}
    idx = np.fromiter((ids.setdefault(g, len(ids)) for g in games), dtype=np.int64,
                      count=len(games))
    s = np.bincount(idx, weights=resid)
    n = np.bincount(idx).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(ids), size=(B, len(ids)))
    stats = s[pick].sum(axis=1) / n[pick].sum(axis=1)
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(resid.mean()), float(lo), float(hi)


def cell(rows: list[tuple[str, float, int]]) -> dict[str, Any]:
    """rows: (game, confidence, outcome)."""
    games = [r[0] for r in rows]
    conf = np.array([r[1] for r in rows])
    y = np.array([r[2] for r in rows], dtype=float)
    gap, lo, hi = boot_gap(games, y - conf)
    return {"n": len(rows), "games": len(set(games)),
            "confidence": round(float(conf.mean()), 4),
            "realised": round(float(y.mean()), 4),
            "gap": round(gap, 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "flag": ("OVER_PROMISE" if hi < 0 else "UNDER_PROMISE" if lo > 0
                     else "") if len(rows) >= MIN_CELL else "SMALL"}


def band_of(conf: float) -> str | None:
    for name, a, b in BANDS:
        if a <= conf < b:
            return name
    return None


def cells(items: Iterable[tuple[str, str, str, float, int]]
          ) -> dict[str, dict[str, Any]]:
    """items: (sport, key, game, confidence, y) -> {sport|level|name|band: cell}
    for keys, families and the sport as a whole."""
    groups: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
    for sport, key, game, conf, y in items:
        band = band_of(conf)
        if band is None:
            continue
        for level, name in (("key", key), ("family", family(key)), ("sport", "ALL")):
            groups[f"{sport}|{level}|{name}|{band}"].append((game, conf, y))
    return {k: cell(v) for k, v in sorted(groups.items())}


def paired_brier(rows: list[tuple[str, float, float, int]]) -> dict[str, Any]:
    """rows: (game, conf_a, conf_b, y): Brier(b) - Brier(a), < 0 = b better."""
    games = [r[0] for r in rows]
    a = np.array([r[1] for r in rows])
    b = np.array([r[2] for r in rows])
    y = np.array([r[3] for r in rows], dtype=float)
    d, lo, hi = boot_gap(games, (b - y) ** 2 - (a - y) ** 2)
    return {"n": len(rows), "games": len(set(games)), "brier_diff": round(d, 6),
            "lo": round(lo, 6), "hi": round(hi, 6)}


# --- growth ----------------------------------------------------------------------


def _fit_meta(doc: dict[str, Any], key: str = "fitted_from") -> dict[str, Any]:
    ff = dict(doc.get(key) or {})
    ff.pop("replay_rules", None)
    return {k: v for k, v in ff.items() if not isinstance(v, (dict, list))
            or k in ("rows", "games", "fit_window_utc", "splits")}


def listed_by_sport(path: Path) -> dict[str, int]:
    with ro(path) as conn:
        return {str(s): int(n) for s, n in conn.execute(
            "SELECT sport, COUNT(*) FROM sofa_listed_event "
            "INDEXED BY sofa_listed_event_sport GROUP BY sport")}


def growth(rows_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"fits": {}, "cache": {}}
    cal = load(CONFIG / "sofa_confidence_calibration.json")
    out["fits"]["football_tennis_curves"] = {
        **_fit_meta(cal),
        "replay_flags": sorted(k for k, v in (
            (cal["fitted_from"].get("replay_rules") or {}).get("flags") or {}).items()
            if v),
        "keys": {"by_market": len(cal.get("by_market") or {}),
                 "by_market_direction": len(cal.get("by_market_direction") or {}),
                 "by_class": sum(len(v) for v in (cal.get("by_class") or {}).values()),
                 "by_market_direction_line": len(
                     cal.get("by_market_direction_line") or {})}}
    out["fits"]["line_curves"] = _fit_meta(cal, "line_curves_fitted_from")
    out["fits"]["match_won_for"] = _fit_meta(cal, "match_won_for_fitted_from")
    for name in ("sofa_engine_constants", "sofa_league_baselines"):
        out["fits"][name] = _fit_meta(load(CONFIG / f"{name}.json"))
    out["fits"]["sofa_market_reliability"] = _fit_meta(
        load(CONFIG / "sofa_market_reliability.json"), "_fitted_from")
    pm = load(CONFIG / "sofa_player_model.json")
    out["fits"]["player_model"] = {
        "fitted_at_utc": pm["fitted_from"].get("fitted_at_utc"),
        "cut_utc": pm["fitted_from"].get("cut_utc"),
        "splits": pm["fitted_from"].get("splits")}
    tt = load(CONFIG / "sofa_tennis_tier_baselines.json")
    out["fits"]["tennis_tier_baselines"] = {"fitted_at_utc": tt.get("fitted_at_utc")}

    today_path = scf.calibration_path_for(date.today().isoformat())
    sport_doc = load(today_path)
    sports: dict[str, Any] = {}
    for sport in scf.SPORT_KEYS:
        inst = (sport_doc.get("sports") or {}).get(sport) or {}
        ff = inst.get("fitted_from") or {}
        sec_path = rows_dir / f"{sport}_section.json"
        dry = (load(sec_path).get("fitted_from") or {}) if sec_path.exists() else {}
        g0, g1 = ff.get("history_games_before"), dry.get("history_games_before")
        sports[sport] = {
            "file": today_path.name, "before": ff.get("before"),
            "fit_window_utc": ff.get("fit_window_utc"),
            "max_games": ff.get("max_games"),
            "rows": ff.get("rows"), "games": ff.get("games"),
            "history_games_before": g0,
            "dry_run_before": dry.get("before"), "dry_run_rows": dry.get("rows"),
            "dry_run_games": dry.get("games"),
            "dry_run_history_games_before": g1,
            "dry_run_max_games": dry.get("max_games"),
            "growth_pct": None if not g0 or g1 is None
            else round(100 * (g1 / g0 - 1), 1),
            "admitted": len(inst.get("admitted") or []),
            "curves": len(inst.get("curves") or {}),
        }
    out["fits"]["sports"] = sports

    live = listed_by_sport(DB)
    replay = Path(str(cal["fitted_from"].get("db_path") or ""))
    replay = replay if replay.is_absolute() else _REPO / replay
    then = listed_by_sport(replay) if replay.exists() else {}
    out["cache"]["listed_events"] = {
        sport: {"fit_db": then.get(slug), "now": live.get(slug),
                "growth_pct": None if not then.get(slug) else round(
                    100 * (live.get(slug, 0) / then[slug] - 1), 1)}
        for sport, slug in LISTED_SLUG.items()}
    out["cache"]["fit_db"] = str(replay.relative_to(_REPO)) if replay.exists() else None
    with ro(DB) as conn:
        cs2_before = str(sports["cs2"]["before"] or "2026-10-13")
        ts = int(np.datetime64(cs2_before, "s").astype(np.int64))
        n_all, n_before = conn.execute(
            "SELECT COUNT(*), SUM(start_ts < ?) FROM cs2_series WHERE complete = 1",
            (ts,)).fetchone()
        out["cache"]["cs2_series_complete"] = {"before_fit": n_before, "now": n_all,
                                               "fit_before": cs2_before}
        out["cache"]["cs2_maps"] = conn.execute(
            "SELECT COUNT(*) FROM cs2_map").fetchone()[0]
    return out


# --- drift -----------------------------------------------------------------------


def sheet_items(day: str) -> Iterator[tuple[str, str, str, float, int, float | None]]:
    """(sport, evidence key, game, curve confidence, y, de-vigged price) of the
    day's graded priced football / tennis rows - fit_line_evidence.sheet_rows'
    reading, by the day's own rules."""
    run_dir = RUNS / day
    if not (run_dir / "07_settled.json").exists():
        return
    cal = dataclasses.replace(Calibration.load(calibration_path_for(day)),
                              gap_shrink_k=0.0, cap_market_by_thin=True,
                              cap_pool_by_neighbour=True)
    cal = live_only_curves.for_day(cal, day)
    per_line = day_reads_per_line(day)
    derived = reads_derived_curves(day)
    fixtures = {int(f["sofascore_event_id"]): f
                for f in load(run_dir / "02_fixtures.json")}
    sides = _board_sides(run_dir)
    for r in load(run_dir / "07_settled.json"):
        sport = r.get("sport")
        if sport not in SHEET_SPORTS or r.get("outcome") not in ("WIN", "LOSS"):
            continue
        if r.get("p_central") is None or not r.get("offered_odds") \
                or not r.get("direction"):
            continue
        if is_derived(r["market"]) and not derived:
            continue
        fx = fixtures.get(int(r["sofascore_event_id"])) or {}
        board = next((sides[str(i)] for i in fx.get("superbet_event_ids") or []
                      if str(i) in sides), None)
        klass = match_class(sport, fx.get("category_name") if sport == "tennis"
                            else fx.get("competition_name"), board,
                            fx.get("competition_id"))
        hit = cal.realised(curve_market(r), float(r["p_central"]), sport,
                           r["direction"], klass, line=leg_line(r, per_line))
        if hit is None:
            continue
        key = direction_key(r["market"], r["direction"])
        yield (str(sport), f"{klass}:{key}" if klass else key,
               f"{day}:{r['sofascore_event_id']}", float(hit[0]),
               1 if r["outcome"] == "WIN" else 0,
               None if r.get("market_p") is None else float(r["market_p"]))


def sport_lines(rows_dir: Path, sport: str) -> Iterator[dict[str, Any]]:
    path = rows_dir / f"{sport}_superbet_settled.jsonl"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def drift(a: str, b: str, rows_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"window": [a, b], "sheet": {}, "sports": {}}
    items: list[tuple[str, str, str, float, int]] = []
    price_rows: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
    for day in days(a, b):
        for sport, key, game, conf, y, mp in sheet_items(day):
            items.append((sport, key, game, conf, y))
            band = band_of(conf)
            if band and mp is not None:
                price_rows[f"{sport}|{band}"].append((game, mp, y))
    out["sheet"]["cells"] = cells(items)
    # the same printed-range rows read against the de-vigged price (two-sided
    # lines only): realised - price
    out["sheet"]["vs_price"] = {k: cell(v) for k, v in sorted(price_rows.items())}
    out["sheet"]["rows"] = len(items)

    today_path = scf.calibration_path_for(b)
    inst = scf.SportCalibration.load(today_path)
    assert inst is not None
    for sport in scf.SPORT_KEYS:
        ff = ((inst.doc.get("sports") or {}).get(sport) or {}).get("fitted_from") or {}
        since = str(ff.get("before") or a)
        sec_path = rows_dir / f"{sport}_section.json"
        sec = load(sec_path) if sec_path.exists() else None
        dry = scf.SportCalibration({"sports": {sport: sec},
                                    "min_bucket": inst.doc.get("min_bucket",
                                                               scf.MIN_BUCKET)}) \
            if sec else None
        oos = set((sec or {}).get("fitted_from", {}).get("settled_dates_oos") or [])
        inst_items: list[tuple[str, str, str, float, int]] = []
        dry_items: list[tuple[str, str, str, float, int]] = []
        common_inst: list[tuple[str, str, str, float, int]] = []
        paired: dict[str, list[tuple[str, float, float, int]]] = defaultdict(list)
        n_lines = 0
        for r in sport_lines(rows_dir, sport):
            day = str(r.get("date") or "")
            if day < since:
                continue
            n_lines += 1
            fam, side = str(r["key"]).split("|")
            p, y, game = float(r["p"]), int(r["y"]), str(r["game"])
            ci = inst.lookup(sport, fam, side, p, require_admitted=False)
            if ci is not None:
                inst_items.append((sport, str(r["key"]), game, ci.value, y))
            if dry is None or day not in oos:
                continue
            cd = dry.lookup(sport, fam, side, p, require_admitted=False)
            if cd is not None:
                dry_items.append((sport, str(r["key"]), game, cd.value, y))
            if ci is not None:
                common_inst.append((sport, str(r["key"]), game, ci.value, y))
            if ci is not None and cd is not None:
                paired["ALL"].append((game, ci.value, cd.value, y))
                paired[str(r["key"])].append((game, ci.value, cd.value, y))
        out["sports"][sport] = {
            "installed_file": today_path.name, "installed_before": since,
            "lines_since": n_lines,
            "installed": cells(inst_items),
            "installed_on_dry_oos": cells(common_inst),
            "dry_run": cells(dry_items),
            "dry_oos_dates": [min(oos), max(oos)] if oos else None,
            "dry_minus_installed_brier": {k: paired_brier(v) for k, v in
                                          sorted(paired.items()) if len(v) >= MIN_CELL},
            "admitted_installed": sorted(inst.admitted(sport)),
            "admitted_dry": sorted((sec or {}).get("admitted") or []),
        }
    return out


# --- sizes -----------------------------------------------------------------------


def sizes() -> dict[str, Any]:
    out: dict[str, Any] = {}
    with ro(DB) as conn:
        page = int(conn.execute("PRAGMA page_size").fetchone()[0])
        out["page_size"] = page
        out["page_count"] = int(conn.execute("PRAGMA page_count").fetchone()[0])
        out["freelist_count"] = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        objs = conn.execute(
            "SELECT name, type, tbl_name FROM sqlite_master "
            "WHERE type IN ('table', 'index') ORDER BY name").fetchall()
        res: dict[str, Any] = {}
        for name, kind, tbl in objs:
            got = conn.execute(
                "SELECT pageno, pgsize, ncell FROM dbstat "
                "WHERE name = ? AND aggregate = TRUE",
                (name,)).fetchone()
            if got is None:
                continue
            # ncell: the cells of every page - for a table about its rows
            # (interior pages add a fraction of a percent)
            res[name] = {"type": kind, "table": tbl, "pages": int(got[0]),
                         "bytes": int(got[1]), "cells": int(got[2])}
            print(f"{name} {got[1] / 1e9:.2f} GB", file=sys.stderr, flush=True)
        out["objects"] = res
        out["settled_rows"] = {str(k): int(n) for k, n in conn.execute(
            "SELECT CASE WHEN run_date LIKE '20%' THEN 'live' ELSE run_date END, "
            "COUNT(*) FROM sofa_settled_row GROUP BY 1")}
    copies = {}
    for path in sorted((_REPO / "data").glob("**/*.db")):
        st = path.stat()
        if st.st_size > 1 << 30:
            copies[str(path.relative_to(_REPO))] = {
                "bytes": st.st_size,
                "mtime": date.fromtimestamp(st.st_mtime).isoformat()}
    out["db_files_over_1gb"] = copies
    du = shutil.disk_usage(_REPO)
    out["disk"] = {"total": du.total, "free": du.free}
    return out


# --- tables (markdown from the three JSON files) ----------------------------------


def _pp(x: float) -> str:
    return f"{100 * x:+.1f}"


def _cell_row(label: str, c: dict[str, Any]) -> str:
    return (f"| {label} | {c['n']:,} | {c['games']:,} | {c['confidence']:.3f} | "
            f"{c['realised']:.3f} | {_pp(c['gap'])} [{_pp(c['lo'])}, {_pp(c['hi'])}] |")


_HEAD = ("| komórka | n | mecze | pewność | trafione | trafione - pewność, pp "
         "[95%] |\n|---|---:|---:|---:|---:|---|")


def _flagged(cs: dict[str, dict[str, Any]], level: str, min_n: int = 300
             ) -> list[tuple[str, dict[str, Any]]]:
    got = [(k, c) for k, c in cs.items() if f"|{level}|" in k and c["n"] >= min_n
           and c["flag"] in ("OVER_PROMISE", "UNDER_PROMISE")]
    return sorted(got, key=lambda kc: kc[1]["gap"])


def tables(dir_: Path) -> str:
    g = load(dir_ / "growth.json")
    d = load(dir_ / "drift.json")
    s = load(dir_ / "sizes.json") if (dir_ / "sizes.json").exists() else None
    out: list[str] = ["### T1. Dopasowanie a historia dziś", "",
                      "| sport | zdarzenia w bazie dopasowania | dziś | wzrost % |",
                      "|---|---:|---:|---:|"]
    for sport, v in g["cache"]["listed_events"].items():
        out.append(f"| {sport} | {v['fit_db'] or '-'} | {v['now']} | "
                   f"{v['growth_pct'] if v['growth_pct'] is not None else '-'} |")
    out += ["", "| sport (krzywe) | before | gry historii przed | dziś (dry-run) | "
            "wzrost % | gry w dopasowaniu | dziś | max_games |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
    for sport, v in g["fits"]["sports"].items():
        out.append(
            f"| {sport} | {v['before']} | {v['history_games_before']} | "
            f"{v['dry_run_history_games_before']} | {v['growth_pct']} | "
            f"{(v['games'] or {}).get('history_fit')} | "
            f"{(v['dry_run_games'] or {}).get('history_fit')} | {v['max_games']} |")
    cs = d["sheet"]["cells"]
    out += ["", f"### T2. Piłka / tenis: krzywa 10-17 na liniach Superbetu "
            f"{d['window'][0]}..{d['window'][1]}", "", _HEAD]
    for k, c in cs.items():
        if "|sport|" in k:
            sp, _, _, band = k.split("|")
            out.append(_cell_row(f"{sp} {band}", c))
    out += ["", "Te same wiersze (dwustronne linie) wobec ceny bez marży "
            "(trafione - cena):", "", _HEAD.replace("pewność", "cena")]
    for k, c in d["sheet"]["vs_price"].items():
        out.append(_cell_row(k.replace("|", " "), c))
    for level in ("family", "key"):
        rows = _flagged(cs, level)
        out += ["", f"### T3{'a' if level == 'family' else 'b'}. Piłka / tenis: "
                f"{'rodziny' if level == 'family' else 'klucze'} z przedziałem "
                f"bez zera (n >= 300): {len(rows)}", "", _HEAD]
        out += [_cell_row(k.replace("|family|", " ").replace("|key|", " ")
                          .replace("|", " "), c) for k, c in rows]
    out += ["", "### T4. Sporty mierzone: krzywa zainstalowana i dzisiejszy "
            "dry-run", "",
            "| sport | ramię | pasmo | n | mecze | pewność | trafione | "
            "trafione - pewność, pp [95%] |", "|---|---|---|---:|---:|---:|---:|---|"]
    for sport, v in d["sports"].items():
        for arm in ("installed", "installed_on_dry_oos", "dry_run"):
            for k, c in v[arm].items():
                if "|sport|" in k:
                    band = k.rsplit("|", 1)[1]
                    out.append(f"| {sport} | {arm} | {band} | {c['n']:,} | "
                               f"{c['games']:,} | {c['confidence']:.3f} | "
                               f"{c['realised']:.3f} | {_pp(c['gap'])} "
                               f"[{_pp(c['lo'])}, {_pp(c['hi'])}] |")
    out += ["", "| sport | zainstalowana od | linie | dry-run - zainstalowana, "
            "Brier [95%] | n | klucze lepsze / gorsze |", "|---|---|---:|---|---:|---|"]
    for sport, v in d["sports"].items():
        b = v["dry_minus_installed_brier"]
        al = b.get("ALL") or {}
        better = sum(1 for k, x in b.items() if k != "ALL" and x["hi"] < 0)
        worse = sum(1 for k, x in b.items() if k != "ALL" and x["lo"] > 0)
        out.append(f"| {sport} | {v['installed_before']} | {v['lines_since']:,} | "
                   f"{al.get('brier_diff', 0):+.5f} [{al.get('lo', 0):+.5f}, "
                   f"{al.get('hi', 0):+.5f}] | {al.get('n', 0):,} | "
                   f"{better} / {worse} z {len(b) - 1} |")
    rows = [(k, c) for v in d["sports"].values()
            for k, c in _flagged(v["installed"], "key")]
    out += ["", f"### T5. Sporty: klucze krzywej zainstalowanej z przedziałem bez "
            f"zera (n >= 300): {len(rows)}", "", _HEAD]
    out += [_cell_row(k.split("|key|")[0] + " " + k.split("|key|")[1].replace(
        "|", " "), c) for k, c in sorted(rows, key=lambda kc: kc[1]["gap"])]
    if s:
        objs = sorted(s["objects"].items(), key=lambda kv: -kv[1]["bytes"])
        out += ["", "### T6. data/sofa.db: tabele i indeksy (dbstat)", "",
                "| obiekt | typ | tabela | GB | komórki |", "|---|---|---|---:|---:|"]
        out += [f"| {n} | {o['type']} | {o['table']} | {o['bytes'] / 1e9:.2f} | "
                f"{o.get('cells', 0):,} |" for n, o in objs if o["bytes"] >= 1e8]
        out += ["", f"Strony: {s['page_count']:,} x {s['page_size']} B, wolne "
                f"{s['freelist_count']}; wiersze sofa_settled_row: "
                + ", ".join(f"{k} {v:,}" for k, v in s["settled_rows"].items())
                + f"; dysk wolny {s['disk']['free'] / 1e9:.1f} GB.", "",
                "| plik bazy > 1 GB | GB | zmieniony |", "|---|---:|---|"]
        out += [f"| {p} | {v['bytes'] / 1e9:.1f} | {v['mtime']} |"
                for p, v in s["db_files_over_1gb"].items()]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("section", choices=("growth", "drift", "sizes", "tables"))
    ap.add_argument("--dir", default="data/refit_readiness_2026-11-05",
                    help="tables: the directory holding the three JSON files")
    ap.add_argument("--from", dest="date_from", default="2026-10-18")
    ap.add_argument("--to", dest="date_to", default="2026-11-04")
    ap.add_argument("--rows-dir", default="data/line_evidence/rows_before_2026-11-05")
    ap.add_argument("--json-out", required=True,
                    help="the JSON file (tables: the markdown file)")
    args = ap.parse_args()
    rows_dir = Path(args.rows_dir)
    rows_dir = rows_dir if rows_dir.is_absolute() else _REPO / rows_dir
    if args.section == "tables":
        Path(args.json_out).write_text(tables(_REPO / args.dir), encoding="utf-8")
        print(f"wrote {args.json_out}", file=sys.stderr)
        return 0
    if args.section == "growth":
        res = growth(rows_dir)
    elif args.section == "drift":
        res = drift(args.date_from, args.date_to, rows_dir)
    else:
        res = sizes()
    Path(args.json_out).write_text(json.dumps(res, indent=1, ensure_ascii=False)
                                   + "\n", encoding="utf-8")
    print(f"wrote {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - exit code contract: 2 on a crash
        print(f"MEASURE_REFIT_READINESS_FAILED: {exc!r}", file=sys.stderr)
        sys.exit(2)
