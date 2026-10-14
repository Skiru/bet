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

_REPO = Path(__file__).resolve().parents[2]

GROUPS = ("shot_detail", "double_chance", "football_incidents", "tennis_sets",
          "sport_derived")
FOOTBALL_TARGET = "sofa_confidence_calibration.json"
SPORT_TARGET = "sofa_sport_confidence_calibration.json"
DEFAULT_TARGET = {g: FOOTBALL_TARGET for g in GROUPS} | {
    "sport_derived": SPORT_TARGET}
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
    else:
        for sport, section in sorted((doc.get("sports") or {}).items()):
            for key, curve in sorted((section.get("curves") or {}).items()):
                gk = f"{sport}:{key}"
                if not _passes(gate, gk):
                    plan.skipped.append(f"{group}: {gk} (gate not passed)")
                    continue
                adds.append((group, gk, ("sports", sport, "curves", key),
                             _check_curve(f"{group}:{gk}", curve)))


def _get(doc: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = doc
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def conflicts(target_doc: Mapping[str, Any], target: str,
              adds: list[tuple[str, str, tuple[str, ...], dict[str, Any]]]
              ) -> list[str]:
    """Keys the target already holds a curve for."""
    out = []
    seen: set[tuple[str, ...]] = set()
    for group, gk, path, _curve in adds:
        if path in seen:
            out.append(f"{group}: {gk} given twice")
        seen.add(path)
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
           fitted_from: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(json.dumps(target_doc))
    record = doc.setdefault(FITTED_FROM_KEY, {})
    for group, gk, path, curve in adds:
        cur = doc
        for p in path[:-1]:
            cur = cur.setdefault(p, {})
        cur[path[-1]] = curve
        if target == SPORT_TARGET:
            src = doc["sports"][path[1]].setdefault("curve_source", {})
            src[path[-1]] = "history"
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
            problems += [f"{path.name}: {c}" for c in conflicts(doc, target, adds)]
            files[path] = (target, merged(doc, target, adds, plan.fitted_from))
    for target, adds in sorted(plan.adds.items()):
        for group, gk, _p, curve in adds:
            print(f"ADD {target} {gk} ({group}): {len(curve)} buckets")
    for s in plan.skipped:
        print(f"SKIP {s}")
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
