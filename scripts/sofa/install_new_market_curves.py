#!/usr/bin/env python3
"""Install the history curves of the new markets (plan
docs/sofa/history/PLAN_KRZYWE_NOWE_RYNKI_2026-10-14.md step 5) - only the keys
that PASSED their holdout gate, never over an existing curve.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/install_new_market_curves.py \\
        --dir data/refit_new_markets_2026-10-15 (--dry-run | --confirm)

Installing changes what prints: it needs the operator's go, and never goes
into a day already built (CLAUDE.md "Changing the pipeline" 4).

Groups: every subdirectory of --dir named in GROUPS that holds a curves.json.
A group's `target` (relative to the repo, or a bare file name) says which
calibration it goes into; without one, sport_derived goes into
config/sofa_sport_confidence_calibration.json and every other group into
config/sofa_confidence_calibration.json. Where the target has a staged
`.next.json` beside it, that file is merged too (a day at or after its
`effective_from` reads it instead).

curves.json - which keys install:
  football / tennis target (sofa_confidence_calibration.json):
    `by_market_direction`: {"<market>|<DIR>": curve}
    `by_class`: {"<class>": {"by_market_direction": {...}}}   (optional)
    `gate`: {"<market>|<DIR>": {"pass": bool, ...},
             "<class>:<market>|<DIR>": {...}}
  sport target (sofa_sport_confidence_calibration.json):
    `sports`: {"<sport>": {"curves": {"<family>|<SIDE>": curve}}}
    `gate`: {"<sport>:<family>|<SIDE>": {"pass": bool, ...}}
  A key installs only when its `gate` entry says `"pass": true` (a key
  without a gate entry, or a group without `gate`, installs nothing). A curve
  is {"<lo>-<hi>": {"n", "realised", "realised_lo95"}}. The verdict is the
  fit scripts' (scripts/sofa/new_market_gate.py): ONE-SIDED since the
  operator's decision of 2026-10-14 ~18:55Z - a key fails only when its
  curve overstates on the holdout by more than 2 pp (n >= 300 at curve
  value >= 0.70); the two-sided verdict is `two_sided_pass`, never read
  here. A group re-gated under a new rule is re-read as is (the fit
  scripts' --regate).

A group whose curves.json names `replace_markets` (tennis_serve: the aces
family under epochs.TENNIS_ACES_OPPONENT and the serve markets the replay
never read) REPLACES those markets' curves instead: every curve of theirs in
the target - by_market, by_market_direction, thin_by_market_direction, top
level and every class - is removed first, then the group's passing direction
keys go in, plus its `by_market` curve of a market whose direction keys in
that section all passed, and its `thin_by_market_direction` buckets (they
only cap). Only the direction keys are recorded in
`new_market_curves_fitted_from` (with the group's `requires_replay_flags`,
which prepare_refit.install reads).

Refusals (exit 2, nothing written): a key already present in the target (its
direction curve or, football / tennis, its market curve - a refit replaces
curves, this does not), a malformed curve, an existing backup directory.
Each installed key's `fitted_from` (the group's) is kept in the target's
`new_market_curves_fitted_from`.

--confirm: the touched config files are copied to --backup-dir
(config/backup_2026-10-15_new_markets/) first, written atomically, then
`tests/sofa` run; on a failure every file is restored from the backup
(exit 2). --dry-run prints the plan and writes nothing. Exit 0 installed /
nothing to install, 2 refused or failed.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.confidence import AWAITING_OWN_CURVE, TENNIS_PER_SET

_REPO = Path(__file__).resolve().parents[2]

GROUPS = ("shot_detail", "double_chance", "football_incidents", "tennis_sets",
          "sport_derived", "football_result_1x2_dnb", "cs2_series_rounds",
          # scripts/sofa/fit_score_market_curves.py (2026-10-16)
          "football_score_markets", "tennis_set_complements",
          # scripts/sofa/fit_tennis_serve_curves.py (2026-10-17): REPLACES
          # its markets' curves (`replace_markets`), see below
          "tennis_serve",
          # epochs.FOOTBALL_PLAYER_PROPS_V2 (2026-10-21): fouls drawn, staged
          # by the measurement of docs/sofa/evidence/
          # football_player_props_v2_2026-10-21.md
          "player_props_v2")
FOOTBALL_TARGET = "sofa_confidence_calibration.json"
SPORT_TARGET = "sofa_sport_confidence_calibration.json"
DEFAULT_TARGET = {g: FOOTBALL_TARGET for g in GROUPS} | {
    "sport_derived": SPORT_TARGET, "cs2_series_rounds": SPORT_TARGET}
DEFAULT_BACKUP = "config/backup_2026-10-15_new_markets"
DEFAULT_TESTS = f"{sys.executable} -m pytest tests/sofa -q"
FITTED_FROM_KEY = "new_market_curves_fitted_from"


class RefusedError(Exception):
    pass


@dataclass
class Plan:
    # target file name -> list of (group, kind, path tuple, curve)
    adds: dict[str, list[tuple[str, str, tuple[str, ...], dict[str, Any]]]] = field(
        default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    fitted_from: dict[str, dict[str, Any]] = field(default_factory=dict)
    # target file name -> markets whose curves a group replaces
    replace: dict[str, set[str]] = field(default_factory=dict)


# the kind of an add that is not a direction key (never recorded)
EXTRA = "~"


def _target_name(group: str, doc: Mapping[str, Any]) -> str:
    raw = doc.get("target")
    name = Path(str(raw)).name if raw else DEFAULT_TARGET[group]
    if name not in (FOOTBALL_TARGET, SPORT_TARGET):
        raise RefusedError(f"{group}: unknown target {raw!r}")
    return name


def _check_curve(where: str, curve: Any) -> dict[str, Any]:
    if not isinstance(curve, dict) or not curve:
        raise RefusedError(f"{where}: empty or malformed curve")
    for bucket, e in curve.items():
        try:
            lo, hi = (float(x) for x in str(bucket).split("-"))
        except ValueError as exc:
            raise RefusedError(
                f"{where}: bucket {bucket!r} is not '<lo>-<hi>'") from exc
        ok = (isinstance(e, dict) and lo < hi
              and isinstance(e.get("n"), int) and e["n"] > 0
              and all(isinstance(e.get(k), int | float) and 0 <= e[k] <= 1
                      for k in ("realised", "realised_lo95")))
        if not ok:
            raise RefusedError(f"{where}: bucket {bucket} malformed: {e!r}")
    return curve


def _passes(gate: Mapping[str, Any], key: str) -> bool:
    g = gate.get(key)
    return isinstance(g, dict) and g.get("pass") is True


def plan_group(group: str, doc: Mapping[str, Any], plan: Plan) -> None:
    target = _target_name(group, doc)
    gate = doc.get("gate") or {}
    adds = plan.adds.setdefault(target, [])
    plan.fitted_from[group] = dict(doc.get("fitted_from") or {})
    if target == FOOTBALL_TARGET:
        for key, curve in sorted((doc.get("by_market_direction") or {}).items()):
            if not _passes(gate, key):
                plan.skipped.append(f"{group}: {key} (gate not passed)")
                continue
            adds.append((group, key, ("by_market_direction", key),
                         _check_curve(f"{group}:{key}", curve)))
        for klass, section in sorted((doc.get("by_class") or {}).items()):
            for key, curve in sorted((section.get("by_market_direction")
                                      or {}).items()):
                gk = f"{klass}:{key}"
                if not _passes(gate, gk):
                    plan.skipped.append(f"{group}: {gk} (gate not passed)")
                    continue
                adds.append((group, gk, ("by_class", klass, "by_market_direction",
                                         key), _check_curve(f"{group}:{gk}", curve)))
        markets = doc.get("replace_markets")
        if markets:
            # a market is replaced only when every top-level direction key of
            # it passed: otherwise its old curves stay whole and none of the
            # group's go in (a full-match market without a direction curve
            # would read the tennis pool)
            directions = doc.get("by_market_direction") or {}
            whole = set()
            for m in (str(x) for x in markets):
                keys = [k for k in directions if k.split("|")[0] == m]
                if keys and any(_passes(gate, k) for k in keys) and all(
                        _passes(gate, k) or _never_prints(gate, k, m)
                        for k in keys):
                    whole.add(m)
                else:
                    plan.skipped.append(
                        f"{group}: {m} not replaced (a direction key failed "
                        "or none was fitted) - its installed curves stay")
            mine = [a for a in adds if a[0] == group]
            adds[:] = [a for a in adds if a[0] != group]
            if whole:
                plan.replace.setdefault(target, set()).update(whole)
                extras: list[tuple[str, str, tuple[str, ...], dict[str, Any]]] = []
                _plan_replace_extras(group, doc, gate, extras)
                adds.extend(a for a in (*mine, *extras)
                            if _market_of(a[2]) in whole)
    else:
        for sport, section in sorted((doc.get("sports") or {}).items()):
            for key, curve in sorted((section.get("curves") or {}).items()):
                gk = f"{sport}:{key}"
                if not _passes(gate, gk):
                    plan.skipped.append(f"{group}: {gk} (gate not passed)")
                    continue
                adds.append((group, gk, ("sports", sport, "curves", key),
                             _check_curve(f"{group}:{gk}", curve)))


def _never_prints(gate: Mapping[str, Any], key: str, market: str) -> bool:
    """A failed key that would print nothing (no holdout forecast at the
    floor, or a final curve below it) of a market CONFIDENCE refuses outright
    without a curve of its own (confidence.AWAITING_OWN_CURVE /
    TENNIS_PER_SET: no pool stands in) - it does not keep the market's other
    directions out. Never for a market a pool could read."""
    g = gate.get(key)
    why = str(g.get("why") or "") if isinstance(g, dict) else ""
    return (market in AWAITING_OWN_CURVE or market in TENNIS_PER_SET) and (
        why.startswith("no holdout forecast") or why.startswith("final curve"))


def _plan_replace_extras(
    group: str, doc: Mapping[str, Any], gate: Mapping[str, Any],
    adds: list[tuple[str, str, tuple[str, ...], dict[str, Any]]],
) -> None:
    """A replacing group's by_market curves (only where every direction key
    of the market in that section passed) and thin buckets (always)."""
    sections: list[tuple[tuple[str, ...], str, Mapping[str, Any]]] = [((), "", doc)]
    for klass, sec in sorted((doc.get("by_class") or {}).items()):
        sections.append((("by_class", klass), f"{klass}:", sec))
    for prefix, label, sec in sections:
        directions = sec.get("by_market_direction") or {}
        for market, curve in sorted((sec.get("by_market") or {}).items()):
            keys = [k for k in directions if k.split("|")[0] == market]
            if keys and all(_passes(gate, f"{label}{k}") for k in keys):
                adds.append((group, f"{EXTRA}{label}market:{market}",
                             (*prefix, "by_market", market),
                             _check_curve(f"{group}:{label}{market}", curve)))
        for key, curve in sorted((sec.get("thin_by_market_direction")
                                  or {}).items()):
            adds.append((group, f"{EXTRA}{label}thin:{key}",
                         (*prefix, "thin_by_market_direction", key),
                         _check_curve(f"{group}:{label}thin:{key}", curve)))


def _market_of(path: tuple[str, ...]) -> str:
    return path[-1].split("|")[0]


def purge_markets(doc: dict[str, Any], markets: set[str]) -> list[str]:
    """Remove, in place, every curve of `markets` (by_market,
    by_market_direction, thin_by_market_direction; top level and classes) and
    their `new_market_curves_fitted_from` records; returns what went."""
    gone: list[str] = []
    sections: list[tuple[str, dict[str, Any]]] = [("", doc)]
    for klass, sec in (doc.get("by_class") or {}).items():
        if isinstance(sec, dict):
            sections.append((f"{klass}:", sec))
    for label, sec in sections:
        for field_name in ("by_market", "by_market_direction",
                           "thin_by_market_direction"):
            curves = sec.get(field_name)
            if not isinstance(curves, dict):
                continue
            for key in [k for k in curves if k.split("|")[0] in markets]:
                del curves[key]
                gone.append(f"{label}{field_name}:{key}")
    record = doc.get(FITTED_FROM_KEY)
    if isinstance(record, dict):
        for key in [k for k in record
                    if str(k).rpartition(":")[2].split("|")[0] in markets]:
            del record[key]
    return gone


def _get(doc: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = doc
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def conflicts(target_doc: Mapping[str, Any], target: str,
              adds: list[tuple[str, str, tuple[str, ...], dict[str, Any]]],
              replace: set[str] | None = None,
              ) -> list[str]:
    """Keys the target already holds a curve for (a replaced market's curves
    are removed first, so they are none)."""
    out = []
    seen: set[tuple[str, ...]] = set()
    for group, gk, path, _curve in adds:
        if path in seen:
            out.append(f"{group}: {gk} given twice")
        seen.add(path)
        if replace and _market_of(path) in replace:
            continue
        if _get(target_doc, path) is not None:
            out.append(f"{target}: {gk} already has a curve")
        if target == FOOTBALL_TARGET:
            market = path[-1].split("|")[0]
            market_path = (*path[:-2], "by_market", market)
            if _get(target_doc, market_path) is not None:
                out.append(f"{target}: {gk} - market {market} already has a "
                           "by_market curve")
        else:
            sport = path[1]
            if sport not in (target_doc.get("sports") or {}):
                out.append(f"{target}: sport {sport} not in the file")
    return out


def merged(target_doc: dict[str, Any], target: str,
           adds: list[tuple[str, str, tuple[str, ...], dict[str, Any]]],
           fitted_from: Mapping[str, Mapping[str, Any]],
           replace: set[str] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(json.dumps(target_doc))
    if replace:
        purge_markets(doc, replace)
    record = doc.setdefault(FITTED_FROM_KEY, {})
    for group, gk, path, curve in adds:
        cur = doc
        for p in path[:-1]:
            cur = cur.setdefault(p, {})
        cur[path[-1]] = curve
        if target == SPORT_TARGET:
            src = doc["sports"][path[1]].setdefault("curve_source", {})
            src[path[-1]] = "history"
        if gk.startswith(EXTRA):
            continue
        record[gk] = {"group": group, **fitted_from.get(group, {})}
    return doc


def _write_atomic(path: Path, doc: Mapping[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def install(args: argparse.Namespace) -> int:
    base = Path(args.dir)
    config_dir = Path(args.config_dir)
    plan = Plan()
    for group in GROUPS:
        f = base / group / "curves.json"
        if f.is_file():
            plan_group(group, json.loads(f.read_text(encoding="utf-8")), plan)
    files: dict[Path, tuple[str, dict[str, Any]]] = {}
    problems: list[str] = []
    for target, adds in plan.adds.items():
        if not adds:
            continue
        stem = target.removesuffix(".json")
        for path in (config_dir / target, config_dir / f"{stem}.next.json"):
            if not path.is_file():
                if path.name == target:
                    problems.append(f"{path} missing")
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            replace = plan.replace.get(target)
            problems += [f"{path.name}: {c}"
                         for c in conflicts(doc, target, adds, replace)]
            files[path] = (target, merged(doc, target, adds, plan.fitted_from,
                                          replace))
    for target, adds in sorted(plan.adds.items()):
        for group, gk, _p, curve in adds:
            print(f"ADD {target} {gk} ({group}): {len(curve)} buckets")
    for s in plan.skipped:
        print(f"SKIP {s}")
    for target, markets in sorted(plan.replace.items()):
        print(f"REPLACE {target}: every curve of {sorted(markets)}")
    if problems:
        for p in problems:
            print(f"REFUSED {p}", file=sys.stderr)
        return 2
    if not files:
        print("nothing to install")
        return 0
    if args.dry_run:
        print("dry run: nothing written; files " + ", ".join(
            str(p) for p in files))
        return 0
    backup = Path(args.backup_dir)
    if backup.exists():
        print(f"REFUSED backup {backup} exists", file=sys.stderr)
        return 2
    backup.mkdir(parents=True)
    for path in files:
        shutil.copy2(path, backup / path.name)
    for path, (_target, doc) in files.items():
        _write_atomic(path, doc)
    print(f"installed into {', '.join(str(p) for p in files)}; backup {backup}")
    proc = subprocess.run(shlex.split(args.test_cmd), cwd=args.test_cwd)
    if proc.returncode != 0:
        for path in files:
            shutil.copy2(backup / path.name, path)
        print(f"tests failed (exit {proc.returncode}): restored from {backup}",
              file=sys.stderr)
        return 2
    print("tests passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--dir", required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm", action="store_true")
    ap.add_argument("--config-dir", default=str(_REPO / "config"))
    ap.add_argument("--backup-dir", default=str(_REPO / DEFAULT_BACKUP))
    ap.add_argument("--test-cmd", default=DEFAULT_TESTS)
    ap.add_argument("--test-cwd", default=str(_REPO))
    args = ap.parse_args(argv)
    try:
        return install(args)
    except RefusedError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
