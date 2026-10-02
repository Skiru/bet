#!/usr/bin/env python3
"""The between-days refit, one deliberate step at a time.

A refit changes every number the next sheet is built from, and it is the one
operation in this pipeline that breaks comparability with yesterday on
purpose (docs/sofa/CONFIG.md sections 5-6). So it is never one command. Each
step below is its own subcommand, prints what it did, and refuses rather than
guesses:

  backup               config/*.json -> config/backup_<UTC date>/ with sha256s
                       (+ --db: data/sofa.db and its -wal/-shm to a given path)
  rebuild-cache-rows   optional, LONG: delete the run_date='cache-calibration'
                       rows and replay them with calibrate_from_cache.py; live
                       rows are fingerprinted per run_date and must not move
  fit                  fit_constants.py + fit_confidence.py into a scratch copy
                       of config/ (data/refit_<date>/config by default)
  compare              old vs new constants, baselines, reliability and
                       confidence curves, and a replay of CONFIDENCE + PDF on
                       settled days against the new files (scratch runs dir)
  install              --confirm: the fitted files into config/, operator keys
                       kept, tests/sofa run, automatic restore on failure
  restore              --confirm: config/ back from a backup directory
  all-prep             backup, [rebuild-cache-rows], fit, compare

Nothing here edits a constant by hand, and nothing writes config/ except
`install` and `restore`, both behind --confirm. The scratch directory may not
sit under runs/ (a scratch rebuild once overwrote the real coupon, 2026-09-23)
or under config/.

The 09-26 procedure this reproduces: back up DB and config, DELETE the cache
replay rows before re-running calibrate_from_cache (its upsert never removes a
row that has become unknown), diff the live rows per run_date afterwards, fit
to a scratch config dir first, run tests/sofa (TestShippedCurve guards the
installed curve).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.atomic import write_atomic, write_bytes_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    PROFILES,
    confidence_artifact,
    printed_builders,
    printed_singles,
)
from bet.sofa.config import REPO_CONFIG_DIR, SofaConfig  # noqa: E402
from bet.sofa.fit_meta import OPERATOR_KEYS  # noqa: E402
from bet.sofa.market_mapper import is_derived  # noqa: E402

CACHE_RUN_DATE = "cache-calibration"

# What the two fits write. `install` copies these and nothing else.
FIT_OUTPUTS: tuple[str, ...] = (
    "sofa_engine_constants.json",
    "sofa_league_baselines.json",
    "sofa_market_reliability.json",
    "sofa_confidence_calibration.json",
)
CONFIDENCE_FILE = "sofa_confidence_calibration.json"

# Gitignored secrets: never copied into a backup or a scratch dir, where a
# `git add config/` would then pick them up.
SECRET_FILES = frozenset({"api_keys.json"})

# Files in a real day that something else appends to while we look
# (capture_closing.py's loop, the logs) - excluded from the md5 guard, which
# is about the products a replay could clobber.
VOLATILE_SUFFIXES = (".log", ".pid")
VOLATILE_NAMES = frozenset({"closing.jsonl"})

MANIFEST = "backup_manifest.json"
FIT_MANIFEST = "fit_manifest.json"


class RefitError(RuntimeError):
    """A refusal. The message says what was refused and why."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def utc_today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def utc_stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_of(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config_files(config_dir: Path) -> list[Path]:
    """Every top-level config/*.json except the gitignored secrets."""
    return sorted(
        p
        for p in config_dir.glob("*.json")
        if p.is_file() and p.name not in SECRET_FILES
    )


def hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {p.name: sha256_of(p) for p in paths}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def say(message: str) -> None:
    print(message, flush=True)


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def processes_holding(path: Path) -> list[str]:
    """`lsof` lines of other processes with the file open (best effort)."""
    try:
        out = subprocess.run(
            ["lsof", "-F", "pc", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found: list[str] = []
    pid = ""
    for line in out.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("c") and pid and pid != str(os.getpid()):
            found.append(f"pid {pid} {line[1:]}")
    return found


@dataclass
class Paths:
    """Where every step reads and writes. Tests point all of it at tmp dirs."""

    config_dir: Path
    db_path: Path
    runs_dir: Path
    scratch: Path
    date: str
    repo: Path = _REPO
    python: str = sys.executable

    @property
    def scratch_config(self) -> Path:
        return self.scratch / "config"

    @property
    def backup_dir(self) -> Path:
        return self.config_dir / f"backup_{self.date}"


def check_scratch(paths: Paths) -> None:
    """The scratch dir may not overlap a real day or the live config."""
    scratch = paths.scratch.resolve()
    forbidden = [
        (paths.runs_dir, "the real runs dir"),
        (paths.repo / "runs", "runs/"),
        (paths.config_dir, "the live config dir"),
    ]
    for parent, label in forbidden:
        if is_within(scratch, parent) or is_within(parent, scratch):
            raise RefitError(
                f"scratch {scratch} overlaps {label} ({parent.resolve()}); "
                "use data/refit_<date>/ or another path outside runs/ and config/"
            )


def child_env(**overrides: str | None) -> dict[str, str]:
    """The environment for a child process: PYTHONPATH set, SOFA_CONFIG_DIR
    only where a step sets it on purpose."""
    env = dict(os.environ)
    env.pop("SOFA_CONFIG_DIR", None)
    env["PYTHONPATH"] = os.pathsep.join([str(_REPO / "src"), str(_REPO)])
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


Runner = Callable[[Sequence[str], dict[str, str], Path | None], tuple[int, list[str]]]


def run_logged(
    cmd: Sequence[str], env: dict[str, str], log_path: Path | None
) -> tuple[int, list[str]]:
    """Run, stream every line to stdout (and the log), return (rc, lines)."""
    say(f"$ {' '.join(cmd)}")
    lines: list[str] = []
    log = log_path.open("a", encoding="utf-8") if log_path else None
    try:
        proc = subprocess.Popen(
            list(cmd),
            cwd=str(_REPO),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            say(f"  | {line}")
            if log:
                log.write(line + "\n")
        rc = proc.wait()
    finally:
        if log:
            log.close()
    return rc, lines


def summaries(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Every SOFA_SUMMARY / bare-JSON stage summary a child printed."""
    out: list[dict[str, Any]] = []
    for line in lines:
        text = line.split("SOFA_SUMMARY:", 1)[1] if "SOFA_SUMMARY:" in line else line
        text = text.strip()
        if not text.startswith("{"):
            continue
        try:
            loaded = json.loads(text)
        except ValueError:
            continue
        if isinstance(loaded, dict) and "stage" in loaded:
            out.append(loaded)
    return out


# --------------------------------------------------------------------------
# 1. backup
# --------------------------------------------------------------------------


def db_files(db_path: Path) -> list[Path]:
    return [
        p
        for p in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm"))
        if p.exists()
    ]


def checkpoint(db_path: Path) -> dict[str, Any]:
    """PRAGMA wal_checkpoint(TRUNCATE), attempted; never fatal."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"attempted": True, "error": str(exc)}
    busy, log_frames, done = row or (None, None, None)
    return {
        "attempted": True,
        "busy": busy,
        "log_frames": log_frames,
        "checkpointed": done,
    }


def backup(paths: Paths, db_target: Path | None) -> dict[str, Any]:
    dest = paths.backup_dir
    if dest.exists():
        raise RefitError(f"{dest} exists - refusing to overwrite a backup")
    files = config_files(paths.config_dir)
    if not files:
        raise RefitError(f"no *.json in {paths.config_dir}")

    db_report: dict[str, Any] | None = None
    if db_target is not None:
        if not paths.db_path.exists():
            raise RefitError(f"DB {paths.db_path} does not exist")
        targets = [db_target, Path(f"{db_target}-wal"), Path(f"{db_target}-shm")]
        if any(t.exists() for t in targets):
            raise RefitError(f"{db_target} (or its -wal/-shm) exists - refusing")
        db_target.parent.mkdir(parents=True, exist_ok=True)
        size = sum(p.stat().st_size for p in db_files(paths.db_path))
        free = shutil.disk_usage(db_target.parent).free
        say(
            f"DB {paths.db_path}: {human_bytes(size)} (db+wal+shm); "
            f"free at {db_target.parent}: {human_bytes(free)}"
        )
        if free < 2 * size:
            raise RefitError(
                f"free {human_bytes(free)} < 2 x DB {human_bytes(size)} - refusing"
            )
        db_report = {
            "source": str(paths.db_path),
            "target": str(db_target),
            "size_bytes": size,
            "free_bytes_before": free,
        }

    dest.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "created_at_utc": utc_stamp(),
        "source_dir": str(paths.config_dir.resolve()),
        "excluded": sorted(
            p.name for p in paths.config_dir.glob("*.json") if p.name in SECRET_FILES
        ),
        "files": {},
    }
    for src in files:
        target = dest / src.name
        shutil.copy2(src, target)
        digest = sha256_of(src)
        if sha256_of(target) != digest:
            raise RefitError(f"copy of {src.name} does not match its source")
        manifest["files"][src.name] = {"sha256": digest, "size": src.stat().st_size}
    say(
        f"backup: {len(files)} files -> {dest}"
        + (
            f" (not copied: {', '.join(manifest['excluded'])})"
            if manifest["excluded"]
            else ""
        )
    )

    exit_code = 0
    if db_target is not None and db_report is not None:
        holders = processes_holding(paths.db_path)
        if holders:
            say(
                "DB is open in other processes (a writer there can make the "
                "copy inconsistent): " + "; ".join(holders)
            )
        db_report["other_processes"] = holders
        db_report["checkpoint"] = checkpoint(paths.db_path)
        say(f"checkpoint: {db_report['checkpoint']}")
        before = {
            p.name: (p.stat().st_size, p.stat().st_mtime_ns)
            for p in db_files(paths.db_path)
        }
        started = time.monotonic()
        for src in db_files(paths.db_path):
            suffix = src.name[len(paths.db_path.name) :]
            shutil.copy2(src, Path(f"{db_target}{suffix}"))
        after = {
            p.name: (p.stat().st_size, p.stat().st_mtime_ns)
            for p in db_files(paths.db_path)
        }
        db_report["copy_seconds"] = round(time.monotonic() - started, 1)
        db_report["changed_during_copy"] = before != after
        if before != after:
            exit_code = 1
            say(
                "WARNING: the DB changed while it was being copied - the copy "
                "may be inconsistent; re-run with no writer, or treat it as "
                "best effort"
            )
        say(f"DB copied to {db_target} in {db_report['copy_seconds']} s")
        manifest["db"] = db_report

    write_atomic(dest / MANIFEST, json.dumps(manifest, indent=1) + "\n")
    say(f"manifest: {dest / MANIFEST}")
    return {"exit": exit_code, "backup_dir": str(dest), "manifest": manifest}


# --------------------------------------------------------------------------
# 2. rebuild-cache-rows
# --------------------------------------------------------------------------


def ro_connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30.0)


def run_date_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        str(run_date): int(n)
        for run_date, n in conn.execute(
            "SELECT run_date, COUNT(*) FROM sofa_settled_row GROUP BY run_date"
        )
    }


def live_fingerprint(conn: sqlite3.Connection) -> dict[str, tuple[int, int, int]]:
    """(count, sum(id), max(id)) per live run_date.

    A replaced row gets a new id, so sum(id) moves even when the count does
    not - INSERT OR REPLACE swapped 3,154 live rows on 2026-09-26 without
    changing the total.
    """
    return {
        str(run_date): (int(n), int(s or 0), int(m or 0))
        for run_date, n, s, m in conn.execute(
            "SELECT run_date, COUNT(*), SUM(id), MAX(id) FROM sofa_settled_row "
            "WHERE run_date != ? GROUP BY run_date",
            (CACHE_RUN_DATE,),
        )
    }


def count_diff(before: dict[str, int], after: dict[str, int]) -> list[str]:
    lines = [f"{'run_date':<20}{'before':>12}{'after':>12}{'delta':>12}"]
    for key in sorted(set(before) | set(after)):
        b, a = before.get(key, 0), after.get(key, 0)
        lines.append(f"{key:<20}{b:>12,}{a:>12,}{a - b:>+12,}")
    return lines


def delete_cache_rows(db_path: Path, chunk: int) -> int:
    """Delete the replay rows in chunks, committing each, so a writer elsewhere
    (a settle loop) waits seconds, not the whole delete."""
    deleted = 0
    conn = sqlite3.connect(str(db_path), timeout=120.0)
    try:
        while True:
            cur = conn.execute(
                "DELETE FROM sofa_settled_row WHERE id IN ("
                " SELECT id FROM sofa_settled_row WHERE run_date = ? LIMIT ?)",
                (CACHE_RUN_DATE, chunk),
            )
            conn.commit()
            if cur.rowcount <= 0:
                break
            deleted += cur.rowcount
            say(f"  deleted {deleted:,} cache rows")
    finally:
        conn.close()
    return deleted


def rebuild_cache_rows(
    paths: Paths,
    *,
    dry_run: bool,
    confirm: bool,
    chunk: int = 500_000,
    calibrate_out: Path | None = None,
    runner: Runner = run_logged,
) -> dict[str, Any]:
    if not paths.db_path.exists():
        raise RefitError(f"DB {paths.db_path} does not exist")
    reliability = (paths.config_dir / "sofa_market_reliability.json").resolve()
    if calibrate_out is not None and (
        calibrate_out.resolve() == reliability
        or is_within(calibrate_out, paths.config_dir)
    ):
        # CONFIG.md hygiene rule 1: one file, one writer.
        raise RefitError(
            "calibrate_from_cache --out may never point into config/ "
            "(sofa_market_reliability.json belongs to fit_constants.py alone)"
        )

    started = time.monotonic()
    conn = ro_connect(paths.db_path)
    try:
        before = run_date_counts(conn)
        fingerprint_before = live_fingerprint(conn)
    finally:
        conn.close()
    count_seconds = round(time.monotonic() - started, 1)
    cache_rows = before.get(CACHE_RUN_DATE, 0)
    live_rows = sum(n for k, n in before.items() if k != CACHE_RUN_DATE)
    say(
        f"sofa_settled_row: {cache_rows:,} {CACHE_RUN_DATE} rows, "
        f"{live_rows:,} live rows over "
        f"{len([k for k in before if k != CACHE_RUN_DATE])} run_dates "
        f"(counted in {count_seconds} s)"
    )
    for key in sorted(before):
        say(f"  {key:<20}{before[key]:>12,}")
    holders = processes_holding(paths.db_path)
    if holders:
        say("DB is open in: " + "; ".join(holders))
    report: dict[str, Any] = {
        "before": before,
        "cache_rows": cache_rows,
        "live_rows": live_rows,
        "count_seconds": count_seconds,
        "other_processes": holders,
    }
    if dry_run:
        say("dry run: nothing deleted, calibrate_from_cache not run")
        report["exit"] = 0
        return report
    if not confirm:
        raise RefitError(
            "rebuild-cache-rows deletes and rewrites "
            f"{cache_rows:,} rows of {paths.db_path}; pass --confirm "
            "(and take `backup --db` first)"
        )

    t0 = time.monotonic()
    deleted = delete_cache_rows(paths.db_path, chunk)
    report["deleted"] = deleted
    report["delete_seconds"] = round(time.monotonic() - t0, 1)
    conn = ro_connect(paths.db_path)
    try:
        mid = run_date_counts(conn)
        fingerprint_mid = live_fingerprint(conn)
    finally:
        conn.close()
    if fingerprint_mid != fingerprint_before or mid.get(CACHE_RUN_DATE, 0) != 0:
        for line in count_diff(before, mid):
            say(line)
        raise RefitError(
            "live rows changed during the delete (or cache rows remain) - "
            "calibrate_from_cache NOT run; compare with the DB backup"
        )
    say(
        f"deleted {deleted:,} cache rows in {report['delete_seconds']} s; "
        "live rows unchanged"
    )

    cmd = [
        paths.python,
        str(paths.repo / "scripts/sofa/calibrate_from_cache.py"),
        "--db-path",
        str(paths.db_path),
    ]
    if calibrate_out is not None:
        cmd += ["--out", str(calibrate_out)]
    t1 = time.monotonic()
    # The replay prices with the constants and baselines it is about to be
    # fitted against: the live ones.
    rc, lines = runner(cmd, child_env(SOFA_CONFIG_DIR=str(paths.config_dir)), None)
    report["calibrate_seconds"] = round(time.monotonic() - t1, 1)
    report["calibrate_rc"] = rc
    report["calibrate_summary"] = summaries(lines)

    conn = ro_connect(paths.db_path)
    try:
        after = run_date_counts(conn)
        fingerprint_after = live_fingerprint(conn)
    finally:
        conn.close()
    report["after"] = after
    say("per run_date, before -> after:")
    for line in count_diff(before, after):
        say(line)
    if fingerprint_after != fingerprint_before:
        changed = sorted(
            k
            for k in set(fingerprint_before) | set(fingerprint_after)
            if fingerprint_before.get(k) != fingerprint_after.get(k)
        )
        raise RefitError(
            f"LIVE ROWS CHANGED on {changed} - stop, compare with the DB backup"
        )
    if rc != 0:
        raise RefitError(
            f"calibrate_from_cache exited {rc}; the cache rows are deleted and "
            "the replay did not finish - re-run this step or restore the DB"
        )
    checkpoint_result = checkpoint(paths.db_path)
    report["checkpoint_after"] = checkpoint_result
    say(f"live rows unchanged; checkpoint after: {checkpoint_result}")
    report["exit"] = 0
    return report


# --------------------------------------------------------------------------
# 3. fit
# --------------------------------------------------------------------------


def fit(paths: Paths, *, force: bool, runner: Runner = run_logged) -> dict[str, Any]:
    check_scratch(paths)
    if not paths.db_path.exists():
        raise RefitError(f"DB {paths.db_path} does not exist")
    target = paths.scratch_config
    if target.exists():
        if not force:
            raise RefitError(f"{target} exists - pass --force to refit into it")
        shutil.rmtree(target)
    target.mkdir(parents=True)
    base = config_files(paths.config_dir)
    for src in base:
        shutil.copy2(src, target / src.name)
    live_before = hashes(config_files(paths.config_dir))
    log = paths.scratch / "fit.log"
    env = child_env(SOFA_CONFIG_DIR=str(target))
    steps: list[dict[str, Any]] = []
    plan = [
        (
            "fit_constants",
            [
                paths.python,
                str(paths.repo / "scripts/sofa/fit_constants.py"),
                "--db-path",
                str(paths.db_path),
                "--config-dir",
                str(target),
            ],
            (0, 1),
        ),  # 1 = PARTIAL: K_PRICE NOT_FITTED is the expected shape
        (
            "fit_confidence",
            [
                paths.python,
                str(paths.repo / "scripts/sofa/fit_confidence.py"),
                "--db-path",
                str(paths.db_path),
                "--out",
                str(target / CONFIDENCE_FILE),
            ],
            (0,),
        ),
    ]
    failed: str | None = None
    for name, cmd, ok in plan:
        t0 = time.monotonic()
        rc, lines = runner(cmd, env, log)
        steps.append(
            {
                "step": name,
                "rc": rc,
                "seconds": round(time.monotonic() - t0, 1),
                "summary": summaries(lines),
            }
        )
        say(f"{name}: exit {rc} in {steps[-1]['seconds']} s")
        if rc not in ok:
            failed = name
            break
    live_after = hashes(config_files(paths.config_dir))
    if live_after != live_before:
        moved = sorted(
            k
            for k in set(live_before) | set(live_after)
            if live_before.get(k) != live_after.get(k)
        )
        raise RefitError(f"LIVE CONFIG CHANGED during the fit: {moved}")
    manifest = {
        "fitted_at_utc": utc_stamp(),
        "db_path": str(paths.db_path),
        "base_config_dir": str(paths.config_dir.resolve()),
        "base_sha256": {p.name: live_before[p.name] for p in base},
        "outputs_sha256": {
            name: sha256_of(target / name)
            for name in FIT_OUTPUTS
            if (target / name).exists()
        },
        "steps": steps,
        "complete": failed is None,
    }
    write_atomic(paths.scratch / FIT_MANIFEST, json.dumps(manifest, indent=1) + "\n")
    if failed:
        raise RefitError(f"{failed} failed - see {log}")
    say(
        f"fit written to {target}; live config unchanged; manifest "
        f"{paths.scratch / FIT_MANIFEST}"
    )
    return {"exit": 0, **manifest}


# --------------------------------------------------------------------------
# 4. compare - the config files
# --------------------------------------------------------------------------

META_KEYS = frozenset({"_doc", "fitted_from", "half_match_coherence", "_fitted_from"})


def _family(doc: dict[str, Any], key: str) -> dict[str, Any]:
    """doc[key] when it is a dict, else an empty one."""
    value = doc.get(key)
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _delta(old: Any, new: Any) -> float | None:
    a, b = _num(old), _num(new)
    return None if a is None or b is None else round(b - a, 6)


def compare_constants(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted((set(old) | set(new)) - META_KEYS):
        o, n = _family(old, name), _family(new, name)
        rows.append(
            {
                "constant": name,
                "old": o.get("value"),
                "new": n.get("value"),
                "old_status": o.get("status"),
                "new_status": n.get("status"),
            }
        )
        by_old, by_new = _family(o, "by_sport"), _family(n, "by_sport")
        for sport in sorted(set(by_old) | set(by_new)):
            rows.append(
                {
                    "constant": f"{name}.by_sport.{sport}",
                    "old": by_old.get(sport),
                    "new": by_new.get(sport),
                    "old_status": o.get("status"),
                    "new_status": n.get("status"),
                }
            )
    return rows


def compare_baselines(
    old: dict[str, Any], new: dict[str, Any], top: int = 20
) -> dict[str, Any]:
    changed: list[dict[str, Any]] = []
    added = removed = 0
    for market in sorted((set(old) | set(new)) - META_KEYS):
        o, n = _family(old, market), _family(new, market)
        for comp in set(o) | set(n):
            a, b = o.get(comp), n.get(comp)
            if not isinstance(a, dict):
                added += isinstance(b, dict)
                continue
            if not isinstance(b, dict):
                removed += 1
                continue
            d = _delta(a.get("mean"), b.get("mean"))
            if d is None or d == 0:
                continue
            old_mean = _num(a.get("mean")) or 0.0
            changed.append(
                {
                    "market": market,
                    "competition": comp,
                    "old_mean": a.get("mean"),
                    "new_mean": b.get("mean"),
                    "delta": d,
                    "relative": round(d / old_mean, 4) if old_mean else None,
                    "old_n": a.get("n"),
                    "new_n": b.get("n"),
                }
            )
    changed.sort(key=lambda r: -abs(r["delta"]))
    return {
        "top": changed[:top],
        # The derived margins (most_, handicap_) dominate |delta| on small n;
        # the count markets the sheet prices from a prior, ranked apart.
        "top_count_markets": [r for r in changed if not is_derived(r["market"])][:top],
        "changed_entries": len(changed),
        "added_entries": added,
        "removed_entries": removed,
        "half_match_coherence": {
            "old": old.get("half_match_coherence"),
            "new": new.get("half_match_coherence"),
        },
    }


def compare_reliability(
    old: dict[str, Any], new: dict[str, Any], top: int = 30
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    status_changes = 0
    markets_old = {k for k in old if k not in META_KEYS}
    markets_new = {k for k in new if k not in META_KEYS}
    for market in sorted(markets_old | markets_new):
        o, n = _family(old, market), _family(new, market)
        for bucket in sorted(set(o) | set(n)):
            a, b = _family(o, bucket), _family(n, bucket)
            if a.get("status") != b.get("status"):
                status_changes += 1
            dc = _delta(a.get("correction", 0.0), b.get("correction", 0.0))
            dr = _delta(a.get("realised"), b.get("realised"))
            if not dc and not dr and a.get("status") == b.get("status"):
                continue
            rows.append(
                {
                    "market": market,
                    "bucket": bucket,
                    "old_correction": a.get("correction"),
                    "new_correction": b.get("correction"),
                    "delta_correction": dc,
                    "old_realised": a.get("realised"),
                    "new_realised": b.get("realised"),
                    "delta_realised": dr,
                    "old_status": a.get("status"),
                    "new_status": b.get("status"),
                    "old_n": a.get("n"),
                    "new_n": b.get("n"),
                }
            )
    rows.sort(
        key=lambda r: (
            -abs(r["delta_correction"] or 0.0),
            -abs(r["delta_realised"] or 0.0),
        )
    )
    return {
        "top": rows[:top],
        "changed_buckets": len(rows),
        "status_changes": status_changes,
        "markets_added": sorted(markets_new - markets_old),
        "markets_removed": sorted(markets_old - markets_new),
        "fitted_from": {"old": old.get("_fitted_from"), "new": new.get("_fitted_from")},
    }


def curve_deltas(
    family: str, name: str, old: dict[str, Any], new: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in sorted(set(old) | set(new)):
        a = old.get(bucket) if isinstance(old.get(bucket), dict) else None
        b = new.get(bucket) if isinstance(new.get(bucket), dict) else None
        if a is not None and b is not None:
            d = _delta(a.get("realised_lo95"), b.get("realised_lo95"))
            if not d:
                continue
            change = "moved"
        else:
            d = None
            change = "added" if a is None else "removed"
        rows.append(
            {
                "family": family,
                "curve": name,
                "bucket": bucket,
                "change": change,
                "old_lo95": (a or {}).get("realised_lo95"),
                "new_lo95": (b or {}).get("realised_lo95"),
                "delta_lo95": d,
                "old_n": (a or {}).get("n"),
                "new_n": (b or {}).get("n"),
            }
        )
    return rows


def compare_confidence(
    old: dict[str, Any], new: dict[str, Any], top: int = 30
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    rows += curve_deltas(
        "pooled", "pooled", _family(old, "pooled"), _family(new, "pooled")
    )
    for family in ("pooled_by_sport", "by_market"):
        o, n = _family(old, family), _family(new, family)
        for name in sorted(set(o) | set(n)):
            rows += curve_deltas(family, name, _family(o, name), _family(n, name))
    moved = sorted(
        (r for r in rows if r["change"] == "moved"),
        key=lambda r: -abs(r["delta_lo95"] or 0.0),
    )
    appeared = [r for r in rows if r["change"] != "moved"]

    def coverage(o: dict[str, Any], n: dict[str, Any]) -> dict[str, Any]:
        def size(curve: Any) -> tuple[int, int]:
            if not isinstance(curve, dict):
                return 0, 0
            return len(curve), sum(
                int(b.get("n", 0)) for b in curve.values() if isinstance(b, dict)
            )

        return {
            "old_curves": len(o),
            "new_curves": len(n),
            "added": [
                {"curve": k, "buckets": size(n[k])[0], "n": size(n[k])[1]}
                for k in sorted(set(n) - set(o))
            ],
            "removed": sorted(set(o) - set(n)),
        }

    direction = coverage(
        _family(old, "by_market_direction"), _family(new, "by_market_direction")
    )
    by_class: dict[str, Any] = {}
    old_cls, new_cls = _family(old, "by_class"), _family(new, "by_class")
    for klass in sorted(set(old_cls) | set(new_cls)):
        oc, nc = _family(old_cls, klass), _family(new_cls, klass)
        entry: dict[str, Any] = {}
        class_rows: list[dict[str, Any]] = []
        for family in ("by_market", "by_market_direction", "pooled_by_sport"):
            of, nf = _family(oc, family), _family(nc, family)
            entry[family] = {
                "old": len(of),
                "new": len(nf),
                "added": sorted(set(nf) - set(of)),
                "removed": sorted(set(of) - set(nf)),
            }
            for name in sorted(set(of) | set(nf)):
                class_rows += curve_deltas(
                    f"{klass}.{family}", name, _family(of, name), _family(nf, name)
                )
        entry["top_moves"] = sorted(
            (r for r in class_rows if r["change"] == "moved"),
            key=lambda r: -abs(r["delta_lo95"] or 0.0),
        )[:10]
        by_class[klass] = entry

    players: list[dict[str, Any]] = []
    families: list[tuple[str, dict[str, Any]]] = [
        ("by_market", _family(new, "by_market")),
        ("by_market_direction", _family(new, "by_market_direction")),
    ]
    for klass in sorted(new_cls):
        for fam_key in ("by_market", "by_market_direction"):
            families.append(
                (
                    f"by_class.{klass}.{fam_key}",
                    _family(_family(new_cls, klass), fam_key),
                )
            )
    for fam_name, curves in families:
        for name in sorted(curves):
            if not name.startswith("player_"):
                continue
            for bucket, cell in sorted(_family(curves, name).items()):
                if isinstance(cell, dict):
                    players.append(
                        {
                            "family": fam_name,
                            "curve": name,
                            "bucket": bucket,
                            "n": cell.get("n"),
                            "realised": cell.get("realised"),
                            "realised_lo95": cell.get("realised_lo95"),
                        }
                    )
    return {
        "top_moves": moved[:top],
        "moved_buckets": len(moved),
        "buckets_added_or_removed": appeared,
        "by_market_direction": direction,
        "by_class": by_class,
        "player_curves": players,
        "admitted_player_markets": {
            "old": old.get("admitted_player_markets"),
            "new": new.get("admitted_player_markets"),
        },
        "fitted_from": {"old": old.get("fitted_from"), "new": new.get("fitted_from")},
        "by_class_fitted_from": {
            "old": old.get("by_class_fitted_from"),
            "new": new.get("by_class_fitted_from"),
        },
    }


def compare_configs(old_dir: Path, new_dir: Path) -> dict[str, Any]:
    old_c = load_json(old_dir / "sofa_engine_constants.json")
    new_c = load_json(new_dir / "sofa_engine_constants.json")
    old_b = load_json(old_dir / "sofa_league_baselines.json")
    new_b = load_json(new_dir / "sofa_league_baselines.json")
    return {
        "old_dir": str(old_dir),
        "new_dir": str(new_dir),
        "fitted_from": {
            "engine_constants": {
                "old": old_c.get("fitted_from"),
                "new": new_c.get("fitted_from"),
            },
            "league_baselines": {
                "old": old_b.get("fitted_from"),
                "new": new_b.get("fitted_from"),
            },
        },
        "constants": compare_constants(old_c, new_c),
        "baselines": compare_baselines(old_b, new_b),
        "reliability": compare_reliability(
            load_json(old_dir / "sofa_market_reliability.json"),
            load_json(new_dir / "sofa_market_reliability.json"),
        ),
        "confidence": compare_confidence(
            load_json(old_dir / CONFIDENCE_FILE), load_json(new_dir / CONFIDENCE_FILE)
        ),
    }


# --------------------------------------------------------------------------
# 4. compare - the coupon replay
# --------------------------------------------------------------------------

LegKey = tuple[int, str, str, float, str]


def leg_key(leg: dict[str, Any]) -> LegKey:
    return (
        int(leg["sofascore_event_id"]),
        str(leg["market"]),
        str(leg.get("subject") or ""),
        float(leg["line"]),
        str(leg["direction"]),
    )


def as_key(raw: Sequence[Any]) -> LegKey:
    return (int(raw[0]), str(raw[1]), str(raw[2]), float(raw[3]), str(raw[4]))


def printed_legs(artifact: dict[str, Any]) -> dict[LegKey, dict[str, Any]]:
    """Every leg the PDF built from this artifact prints: its singles and the
    legs of its printed builders."""
    out: dict[LegKey, dict[str, Any]] = {}
    for single in printed_singles(artifact):
        entry = out.setdefault(leg_key(single), {**_leg_view(single), "as": []})
        entry["as"].append("single")
    for index, builder in enumerate(printed_builders(artifact)):
        for raw in builder.get("legs") or []:
            # A builder leg carries no fixture of its own (the builder does)
            # and names its price `odds`.
            leg = {
                "sofascore_event_id": builder.get("sofascore_event_id"),
                "match": builder.get("match"),
                "offered_odds": raw.get("odds"),
                **raw,
            }
            entry = out.setdefault(leg_key(leg), {**_leg_view(leg), "as": []})
            entry["as"].append(f"builder#{index + 1}")
    return out


def _leg_view(leg: dict[str, Any]) -> dict[str, Any]:
    return {
        k: leg.get(k)
        for k in (
            "match",
            "market",
            "subject",
            "line",
            "direction",
            "confidence",
            "offered_odds",
            "model_p",
            "calibrated_on",
        )
    }


def diff_printed(
    before: dict[LegKey, dict[str, Any]], after: dict[LegKey, dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    dropped = [{"key": list(k), **before[k]} for k in sorted(set(before) - set(after))]
    added = [{"key": list(k), **after[k]} for k in sorted(set(after) - set(before))]
    moved = []
    for k in sorted(set(before) & set(after)):
        a, b = before[k].get("confidence"), after[k].get("confidence")
        if a != b or before[k]["as"] != after[k]["as"]:
            moved.append(
                {
                    "key": list(k),
                    **after[k],
                    "old_confidence": a,
                    "new_confidence": b,
                    "delta": _delta(a, b),
                    "old_as": before[k]["as"],
                }
            )
    return {"dropped": dropped, "added": added, "changed": moved}


def settled_lookup(
    db_path: Path, keys: Iterable[LegKey]
) -> dict[LegKey, dict[str, Any]]:
    out: dict[LegKey, dict[str, Any]] = {}
    if not db_path.exists():
        return out
    conn = ro_connect(db_path)
    try:
        for key in keys:
            row = conn.execute(
                "SELECT run_date, outcome, actual_value FROM sofa_settled_row "
                "WHERE sofascore_event_id = ? AND market = ? AND subject = ? "
                "AND line = ? AND direction = ?",
                key,
            ).fetchone()
            if row is not None:
                out[key] = {"run_date": row[0], "outcome": row[1], "actual": row[2]}
    finally:
        conn.close()
    return out


def _units(leg: dict[str, Any]) -> float | None:
    outcome = (leg.get("settled") or {}).get("outcome")
    odds = _num(leg.get("offered_odds"))
    if outcome == "WIN" and odds is not None:
        return round(odds - 1.0, 4)
    if outcome == "LOSS":
        return -1.0
    if outcome in {"VOID", "PUSH"}:
        return 0.0
    return None


def is_volatile(path: Path) -> bool:
    return path.name in VOLATILE_NAMES or path.name.endswith(VOLATILE_SUFFIXES)


def day_fingerprint(day_dir: Path) -> dict[str, str]:
    """md5 of every top-level product file of a real day."""
    return {
        p.name: md5_of(p)
        for p in sorted(day_dir.iterdir())
        if p.is_file() and not is_volatile(p)
    }


def guard_day(day_dir: Path, expected: dict[str, str]) -> None:
    now_fp = day_fingerprint(day_dir)
    if now_fp != expected:
        moved = sorted(
            k for k in set(expected) | set(now_fp) if expected.get(k) != now_fp.get(k)
        )
        raise RefitError(
            f"THE REAL DAY {day_dir} CHANGED during the replay: {moved} - "
            "stop; a scratch rebuild has written into the real day"
        )


def copy_day(src: Path, dst: Path) -> None:
    """Top-level files only, mtimes preserved (cp -p): the PDF builder refuses
    a confidence artifact older than its sheet, by mtime."""
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.iterdir()):
        if p.is_file() and not is_volatile(p):
            shutil.copy2(p, dst / p.name)


def frozen_at(artifact: Path) -> str:
    """The clock the real build ran at: its own created_at_utc."""
    doc = load_json(artifact)
    stamp = doc.get("created_at_utc")
    if not isinstance(stamp, str):
        raise RefitError(f"{artifact} has no created_at_utc to replay at")
    return stamp


def settled_days(db_path: Path, runs_dir: Path, count: int = 2) -> list[str]:
    """The newest `count` dated run_dates with a settled row and a day dir."""
    if not db_path.exists():
        return []
    conn = ro_connect(db_path)
    try:
        dates = [
            str(r[0])
            for r in conn.execute(
                "SELECT DISTINCT run_date FROM sofa_settled_row "
                "WHERE run_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
                "ORDER BY run_date DESC"
            )
        ]
    finally:
        conn.close()
    return sorted(d for d in dates if (runs_dir / d / "08_confidence.json").exists())[
        -count:
    ]


@dataclass
class ReplayResult:
    day: str
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def replay_day(
    paths: Paths,
    day: str,
    *,
    with_sheet: bool,
    runner: Runner = run_logged,
) -> ReplayResult:
    real = paths.runs_dir / day
    if not (real / "08_confidence.json").exists():
        raise RefitError(f"{real} has no 08_confidence.json to replay")
    expected = day_fingerprint(real)
    result = ReplayResult(day)
    configs = {"old": paths.scratch / "config_old", "new": paths.scratch_config}
    log = paths.scratch / "replay.log"
    for label, cfg in configs.items():
        runs = paths.scratch / "replay" / label / "runs" / "sofa"
        day_dir = runs / day
        if day_dir.exists():
            shutil.rmtree(day_dir)
        copy_day(real, day_dir)
        guard_day(real, expected)
        env = child_env(SOFA_RUNS_DIR=str(runs), SOFA_CONFIG_DIR=str(cfg))
        stages: list[tuple[str, list[str]]] = []
        at_standard = frozen_at(real / "08_confidence.json")
        if with_sheet:
            stages.append(("sheet", ["scripts/sofa/run_sheet.py", "--date", day]))
        for profile in sorted(PROFILES):
            if not (real / confidence_artifact(PROFILES[profile])).exists():
                continue
            stages.append(
                (
                    f"confidence_{profile}",
                    [
                        "scripts/sofa/run_confidence.py",
                        "--date",
                        day,
                        "--profile",
                        profile,
                        "--runs-dir",
                        str(runs),
                    ],
                )
            )
            stages.append(
                (
                    f"pdf_{profile}",
                    [
                        "scripts/sofa/build_coupon_pdf.py",
                        "--date",
                        day,
                        "--profile",
                        profile,
                        "--runs-dir",
                        str(runs),
                    ],
                )
            )
        for stage, argv in stages:
            profile = stage.split("_", 1)[-1]
            at = at_standard
            if profile in PROFILES and profile != "standard":
                at = frozen_at(real / confidence_artifact(PROFILES[profile]))
            cmd = [
                paths.python,
                str(Path(__file__).resolve()),
                "_frozen",
                "--at",
                at,
                "--",
                *argv,
            ]
            rc, _ = runner(cmd, env, log)
            guard_day(real, expected)
            if rc not in (0, 1):
                result.errors.append(f"{label}/{day}/{stage}: exit {rc}")
                break
    for profile_name, conf_profile in PROFILES.items():
        artifact = confidence_artifact(conf_profile)
        if not (real / artifact).exists():
            continue
        real_legs = printed_legs(load_json(real / artifact))
        replayed = {
            label: printed_legs(
                load_json(
                    paths.scratch / "replay" / label / "runs" / "sofa" / day / artifact
                )
            )
            for label in configs
        }
        config_effect = diff_printed(replayed["old"], replayed["new"])
        keys = {as_key(r["key"]) for part in config_effect.values() for r in part}
        settled = settled_lookup(paths.db_path, keys)
        for part in config_effect.values():
            for row in part:
                row["settled"] = settled.get(as_key(row["key"]))
                row["units_at_printed_odds"] = _units(row)
        # The real artifact against the old-config replay: what changed in
        # the code since the day was built, not in the config.
        drift = diff_printed(real_legs, replayed["old"])
        result.profiles[profile_name] = {
            "printed": {
                "real": len(real_legs),
                "old_config": len(replayed["old"]),
                "new_config": len(replayed["new"]),
            },
            "config_effect": config_effect,
            "code_drift_vs_real": {k: len(v) for k, v in drift.items()},
            "code_drift_detail": drift,
        }
    guard_day(real, expected)
    return result


def compare(
    paths: Paths,
    *,
    days: list[str] | None,
    with_sheet: bool,
    replay: bool = True,
    runner: Runner = run_logged,
) -> dict[str, Any]:
    check_scratch(paths)
    if not paths.scratch_config.exists():
        raise RefitError(f"{paths.scratch_config} missing - run `fit` first")
    old_snapshot = paths.scratch / "config_old"
    if old_snapshot.exists():
        shutil.rmtree(old_snapshot)
    old_snapshot.mkdir(parents=True)
    for src in config_files(paths.config_dir):
        shutil.copy2(src, old_snapshot / src.name)
    report: dict[str, Any] = {
        "created_at_utc": utc_stamp(),
        "configs": compare_configs(old_snapshot, paths.scratch_config),
        "replay": {},
        "replay_note": (
            "CONFIDENCE and the PDF re-run on each day's own artifacts, clock "
            "frozen at the real build's created_at_utc, once on a copy of the "
            "live config (old) and once on the fit (new); the effect of the "
            "fit is old vs new. "
            + (
                "SHEET was re-run too (--with-sheet)."
                if with_sheet
                else "SHEET was NOT re-run: p_bar, the reliability correction, the "
                "league priors and K_CENTRE act in SHEET, so the replay shows "
                "only the confidence curves' effect on legs the old sheet "
                "produced. Pass --with-sheet for the rest (~10 min per day "
                "the first time)."
            )
            + " Settled outcomes are in-sample: these days' rows are in the "
            "fit, so they are information, never evidence for the fit."
        ),
    }
    if replay:
        chosen = days or settled_days(paths.db_path, paths.runs_dir)
        if not chosen:
            say("replay: no settled day with an 08_confidence.json - skipped")
        for day in chosen:
            say(f"replay {day} ...")
            result = replay_day(paths, day, with_sheet=with_sheet, runner=runner)
            report["replay"][day] = {
                "profiles": result.profiles,
                "errors": result.errors,
            }
    write_atomic(
        paths.scratch / "compare_report.json",
        json.dumps(report, indent=1, default=str) + "\n",
    )
    write_atomic(paths.scratch / "compare_report.md", render_markdown(report))
    say(f"report: {paths.scratch / 'compare_report.md'} (+ .json)")
    errors = [e for d in report["replay"].values() for e in d["errors"]]
    report["exit"] = 1 if errors else 0
    return report


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:+.4f}" if abs(value) < 1 and value != 0 else f"{value:.4g}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    cfg = report["configs"]
    out = [
        f"# Refit comparison - {report['created_at_utc']}",
        "",
        f"old: `{cfg['old_dir']}`  new: `{cfg['new_dir']}`",
        "",
        "## fitted_from",
        "",
    ]
    for name, pair in cfg["fitted_from"].items():
        out.append(f"- {name}: old `{json.dumps(pair['old'])}`")
        out.append(f"  new `{json.dumps(pair['new'])}`")
    conf = cfg["confidence"]
    out.append(
        f"- reliability: old `{json.dumps(cfg['reliability']['fitted_from']['old'])}`"
        f" new `{json.dumps(cfg['reliability']['fitted_from']['new'])}`"
    )
    out.append(
        f"- confidence: old `{json.dumps(conf['fitted_from']['old'])}` "
        f"new `{json.dumps(conf['fitted_from']['new'])}`"
    )
    out += [
        "",
        "## Engine constants",
        "",
        "| constant | old | new | old status | new status |",
        "|---|---|---|---|---|",
    ]
    for r in cfg["constants"]:
        out.append(
            f"| {r['constant']} | {_fmt(r['old'])} | {_fmt(r['new'])} | "
            f"{r['old_status']} | {r['new_status']} |"
        )
    bl = cfg["baselines"]
    out += [
        "",
        "## League baselines",
        "",
        f"changed {bl['changed_entries']}, added {bl['added_entries']}, "
        f"removed {bl['removed_entries']}",
        "",
        f"half_match_coherence old: `{json.dumps(bl['half_match_coherence']['old'])}`",
        f"half_match_coherence new: `{json.dumps(bl['half_match_coherence']['new'])}`",
    ]
    for title, key in (
        ("all markets", "top"),
        ("count markets only (no most_/handicap_/both_over_)", "top_count_markets"),
    ):
        out += [
            "",
            f"Top by |delta|, {title}:",
            "",
            "| market | competition | old mean | new mean | delta | rel "
            "| n old | n new |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in bl[key]:
            out.append(
                f"| {r['market']} | {r['competition']} | {r['old_mean']} | "
                f"{r['new_mean']} | {r['delta']:+.4f} | {_fmt(r['relative'])} | "
                f"{r['old_n']} | {r['new_n']} |"
            )
    rel = cfg["reliability"]
    out += [
        "",
        "## Market reliability (SHEET's correction)",
        "",
        f"changed buckets {rel['changed_buckets']}, status changes "
        f"{rel['status_changes']}, markets added {rel['markets_added']}, "
        f"removed {rel['markets_removed']}",
        "",
        "| market | bucket | corr old | corr new | realised old | realised new | "
        "status old/new | n new |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rel["top"]:
        out.append(
            f"| {r['market']} | {r['bucket']} | {r['old_correction']} | "
            f"{r['new_correction']} | {r['old_realised']} | {r['new_realised']} | "
            f"{r['old_status']}/{r['new_status']} | {r['new_n']} |"
        )
    out += [
        "",
        "## Confidence curves (CONFIDENCE ranks on realised_lo95)",
        "",
        f"moved buckets {conf['moved_buckets']}; buckets added/removed "
        f"{len(conf['buckets_added_or_removed'])}",
        "",
        "| family | curve | bucket | lo95 old | lo95 new | delta | n new |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in conf["top_moves"]:
        out.append(
            f"| {r['family']} | {r['curve']} | {r['bucket']} | {r['old_lo95']} | "
            f"{r['new_lo95']} | {r['delta_lo95']:+.4f} | {r['new_n']} |"
        )
    gone = [r for r in conf["buckets_added_or_removed"] if r["change"] == "removed"]
    if gone:
        out += [
            "",
            "Buckets REMOVED (a leg there now falls back to its pool, or is "
            "refused NOT_CALIBRATED):",
            "",
        ]
        out += [
            f"- {r['family']} {r['curve']} {r['bucket']} (n old {r['old_n']})"
            for r in gone
        ]
    dirn = conf["by_market_direction"]
    out += [
        "",
        "### by_market_direction coverage",
        "",
        f"curves old {dirn['old_curves']} -> new {dirn['new_curves']}; "
        f"removed {dirn['removed']}",
        "",
    ]
    out += [
        f"- NEW {a['curve']}: {a['buckets']} buckets, n={a['n']:,}"
        for a in dirn["added"]
    ]
    out += ["", "### by_class", ""]
    for klass, entry in conf["by_class"].items():
        parts = ", ".join(
            f"{fam} {v['old']}->{v['new']}"
            for fam, v in entry.items()
            if fam != "top_moves"
        )
        out.append(f"- **{klass}**: {parts}")
        for r in entry["top_moves"][:5]:
            out.append(
                f"  - {r['family']} {r['curve']} {r['bucket']}: "
                f"{r['old_lo95']} -> {r['new_lo95']} (n {r['new_n']})"
            )
    out += [
        "",
        "### Player-prop curves (decision: admitted_player_markets)",
        "",
        f"admitted_player_markets now: "
        f"`{json.dumps(conf['admitted_player_markets']['old'])}` - a curve is not "
        "an admission; CONFIDENCE refuses a prop until it is named there "
        "(PLAYER_PROP_NOT_ADMITTED).",
        "",
    ]
    if conf["player_curves"]:
        out += [
            "| family | curve | bucket | n | realised | lo95 |",
            "|---|---|---|---|---|---|",
        ]
        out += [
            f"| {r['family']} | {r['curve']} | {r['bucket']} | {r['n']} | "
            f"{r['realised']} | {r['realised_lo95']} |"
            for r in conf["player_curves"]
        ]
    else:
        out.append("No player_* curve in the new fit.")
    out += ["", "## Coupon replay", "", report["replay_note"], ""]
    for day, entry in report["replay"].items():
        out.append(f"### {day}")
        for err in entry["errors"]:
            out.append(f"- ERROR {err}")
        for profile, data in entry["profiles"].items():
            p = data["printed"]
            out.append(
                f"- **{profile}**: printed legs real {p['real']}, replay old "
                f"config {p['old_config']}, new config {p['new_config']}; code "
                f"drift (real vs old-config replay): {data['code_drift_vs_real']}"
            )
            for part in ("dropped", "added", "changed"):
                rows = data["config_effect"][part]
                if not rows:
                    continue
                units = [
                    u for r in rows if (u := r.get("units_at_printed_odds")) is not None
                ]
                out.append(
                    f"  - {part} {len(rows)} (in-sample units at printed odds, "
                    f"settled {len(units)}: {sum(units):+.2f})"
                )
                for r in rows:
                    settled = r.get("settled") or {}
                    conf_txt = (
                        f"{r.get('old_confidence')} -> {r.get('new_confidence')}"
                        if part == "changed"
                        else f"{r.get('confidence')}"
                    )
                    out.append(
                        f"    - {r.get('match')} | {r['market']} "
                        f"{r.get('subject') or ''} "
                        f"{r['direction']} {r['line']} @ {r.get('offered_odds')} | "
                        f"conf {conf_txt} | {'/'.join(r['as'])} | "
                        f"{settled.get('outcome', 'unsettled')}"
                    )
        out.append("")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# 5. install / 6. restore
# --------------------------------------------------------------------------


def run_tests() -> int:
    """tests/sofa against the installed files (no SOFA_CONFIG_DIR leaks in)."""
    rc, _ = run_logged(
        [sys.executable, "-m", "pytest", "tests/sofa", "-q"], child_env(), None
    )
    return rc


def _serialise_like(name: str, doc: dict[str, Any]) -> str:
    # The writers' own formats: fit_confidence indent=1 + newline,
    # fit_constants indent=2, ensure_ascii=False, no newline.
    if name == CONFIDENCE_FILE:
        return json.dumps(doc, indent=1) + "\n"
    return json.dumps(doc, indent=2, ensure_ascii=False)


def install(
    paths: Paths,
    *,
    confirm: bool,
    backup_dir: Path | None = None,
    tests: Callable[[], int] = run_tests,
) -> dict[str, Any]:
    if not confirm:
        raise RefitError("install writes config/ - pass --confirm")
    check_scratch(paths)
    manifest = load_json(paths.scratch / FIT_MANIFEST)
    if not manifest.get("complete"):
        raise RefitError(
            f"{paths.scratch / FIT_MANIFEST} missing or the fit "
            "did not complete - run `fit`"
        )
    for name in FIT_OUTPUTS:
        src = paths.scratch_config / name
        if not src.exists():
            raise RefitError(f"{src} missing")
        if manifest["outputs_sha256"].get(name) != sha256_of(src):
            raise RefitError(f"{src} differs from what `fit` wrote - refit")
    bdir = backup_dir or paths.backup_dir
    bman = load_json(bdir / MANIFEST)
    if not bman:
        raise RefitError(f"no backup manifest in {bdir} - run `backup` first")
    for name in FIT_OUTPUTS:
        live = paths.config_dir / name
        recorded = (bman.get("files") or {}).get(name, {}).get("sha256")
        if live.exists() and recorded != sha256_of(live):
            raise RefitError(
                f"config/{name} changed since backup {bdir} - back up again "
                "before installing over it"
            )

    written: dict[str, str] = {}
    for name in FIT_OUTPUTS:
        src = paths.scratch_config / name
        live = paths.config_dir / name
        data = src.read_bytes()
        doc = json.loads(data)
        live_doc = load_json(live)
        # The operator's keys as they stand in config/ NOW - an admission
        # made after the fit started still wins, and one withdrawn stays out.
        changed = False
        for key in OPERATOR_KEYS:
            if key in live_doc and doc.get(key) != live_doc[key]:
                doc[key] = live_doc[key]
                changed = True
            elif key not in live_doc and key in doc:
                doc.pop(key)
                changed = True
        if changed:
            write_atomic(live, _serialise_like(name, doc))
        else:
            write_bytes_atomic(live, data)
        written[name] = sha256_of(live)
        say(f"installed {name}" + (" (operator keys carried)" if changed else ""))

    rc = tests()
    if rc != 0:
        say(f"tests/sofa FAILED (exit {rc}) - restoring {bdir}")
        restore(paths, confirm=True, backup_dir=bdir, only=FIT_OUTPUTS)
        raise RefitError(f"tests failed after install; config restored from {bdir}")
    record = {
        "installed_at_utc": utc_stamp(),
        "backup_dir": str(bdir),
        "installed_sha256": written,
        "fit_manifest": manifest.get("fitted_at_utc"),
    }
    write_atomic(
        paths.scratch / "install_manifest.json", json.dumps(record, indent=1) + "\n"
    )
    files = " ".join(f"config/{n}" for n in FIT_OUTPUTS)
    say("tests/sofa passed. Commit it as one epoch:")
    message = f"refit {paths.date}: new comparability epoch"
    say(f'  git add {files} && git commit -m "{message}"')
    return {"exit": 0, **record}


def restore(
    paths: Paths,
    *,
    confirm: bool,
    backup_dir: Path,
    only: Sequence[str] | None = None,
) -> dict[str, Any]:
    if not confirm:
        raise RefitError("restore writes config/ - pass --confirm")
    manifest = load_json(backup_dir / MANIFEST)
    files = manifest.get("files") or {}
    if not files:
        raise RefitError(f"no backup manifest in {backup_dir}")
    names = [n for n in files if only is None or n in only]
    for name in names:
        src = backup_dir / name
        if sha256_of(src) != files[name]["sha256"]:
            raise RefitError(
                f"backup {src} does not match its manifest - not restoring"
            )
    restored = []
    for name in names:
        target = paths.config_dir / name
        if target.exists() and sha256_of(target) == files[name]["sha256"]:
            continue
        write_bytes_atomic(target, (backup_dir / name).read_bytes())
        if sha256_of(target) != files[name]["sha256"]:
            raise RefitError(f"restored {target} does not match the manifest")
        restored.append(name)
    say(
        f"restore from {backup_dir}: {len(restored)} file(s) rewritten, "
        f"{len(names) - len(restored)} already identical"
    )
    return {"exit": 0, "restored": restored}


# --------------------------------------------------------------------------
# frozen clock for the replay
# --------------------------------------------------------------------------


def run_frozen(at: str, argv: list[str]) -> int:
    """Run one stage script with bet.sofa.timeutil.now fixed at `at`.

    A replay of a past day at today's clock refuses every leg (kickoff passed,
    price older than 45 min); at the real build's clock it answers the
    question asked - what would the new files have printed that day. Patched
    before the script imports anything, so `from ... import now` binds it too.
    """
    from bet.sofa import timeutil

    fixed = datetime.fromisoformat(at.replace("Z", "+00:00"))
    if fixed.tzinfo is None:
        fixed = fixed.replace(tzinfo=UTC)
    setattr(timeutil, "now", lambda: fixed)
    script = argv[0]
    sys.argv = list(argv)
    try:
        runpy.run_path(
            str(_REPO / script) if not Path(script).is_absolute() else script,
            run_name="__main__",
        )
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--date",
        default=None,
        help="refit label (UTC date): backup_<date>, data/refit_<date>",
    )
    parser.add_argument("--config-dir", default=str(REPO_CONFIG_DIR))
    parser.add_argument("--db-path", default=None)
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="the REAL runs dir the replay reads (never written)",
    )
    parser.add_argument(
        "--scratch",
        default=None,
        help="default data/refit_<date>/ (never under runs/ or config/)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backup", help="config/*.json (+ --db) with a sha256 manifest")
    b.add_argument(
        "--db", default=None, help="also copy the DB (+wal/shm) to this path"
    )

    r = sub.add_parser("rebuild-cache-rows", help="LONG: re-run the cache replay rows")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--confirm", action="store_true")
    r.add_argument("--chunk", type=int, default=500_000)
    r.add_argument(
        "--calibrate-out",
        default=None,
        help="calibrate_from_cache --out (inspection curve; never config/)",
    )

    f = sub.add_parser("fit", help="fit_constants + fit_confidence into scratch")
    f.add_argument("--force", action="store_true")

    c = sub.add_parser("compare", help="old vs new report + coupon replay")
    c.add_argument("--days", nargs="*", default=None)
    c.add_argument("--with-sheet", action="store_true")
    c.add_argument("--no-replay", action="store_true")

    i = sub.add_parser("install", help="scratch config -> config/, then tests/sofa")
    i.add_argument("--confirm", action="store_true")
    i.add_argument("--backup", default=None)

    s = sub.add_parser("restore", help="config/ back from a backup dir")
    s.add_argument("--confirm", action="store_true")
    s.add_argument("--backup", required=True)

    a = sub.add_parser("all-prep", help="backup, [rebuild-cache-rows], fit, compare")
    a.add_argument("--db", default=None)
    a.add_argument("--with-cache-rows", action="store_true")
    a.add_argument("--confirm", action="store_true")
    a.add_argument("--force", action="store_true")
    a.add_argument("--days", nargs="*", default=None)
    a.add_argument("--with-sheet", action="store_true")

    z = sub.add_parser("_frozen", help=argparse.SUPPRESS)
    z.add_argument("--at", required=True)
    z.add_argument("argv", nargs=argparse.REMAINDER)
    return parser


def resolve_paths(args: argparse.Namespace) -> Paths:
    date = args.date or utc_today()
    env = SofaConfig.from_env()

    def repo_rel(raw: str) -> Path:
        p = Path(raw)
        return p if p.is_absolute() else _REPO / p

    return Paths(
        config_dir=repo_rel(args.config_dir),
        db_path=repo_rel(args.db_path or env.db_path),
        runs_dir=repo_rel(args.runs_dir or env.runs_dir),
        scratch=repo_rel(args.scratch or f"data/refit_{date}"),
        date=date,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "_frozen":
        rest = (
            [a for a in args.argv if a != "--"]
            if args.argv[:1] == ["--"]
            else args.argv
        )
        return run_frozen(args.at, list(rest))
    if os.environ.get("SOFA_CONFIG_DIR"):
        say(
            f"note: SOFA_CONFIG_DIR={os.environ['SOFA_CONFIG_DIR']} is ignored here; "
            "the live config is --config-dir and children get it set explicitly"
        )
    paths = resolve_paths(args)
    try:
        if args.command == "backup":
            return int(backup(paths, Path(args.db) if args.db else None)["exit"])
        if args.command == "rebuild-cache-rows":
            return int(
                rebuild_cache_rows(
                    paths,
                    dry_run=args.dry_run,
                    confirm=args.confirm,
                    chunk=args.chunk,
                    calibrate_out=Path(args.calibrate_out)
                    if args.calibrate_out
                    else None,
                )["exit"]
            )
        if args.command == "fit":
            return int(fit(paths, force=args.force)["exit"])
        if args.command == "compare":
            return int(
                compare(
                    paths,
                    days=args.days,
                    with_sheet=args.with_sheet,
                    replay=not args.no_replay,
                )["exit"]
            )
        if args.command == "install":
            return int(
                install(
                    paths,
                    confirm=args.confirm,
                    backup_dir=Path(args.backup) if args.backup else None,
                )["exit"]
            )
        if args.command == "restore":
            return int(
                restore(paths, confirm=args.confirm, backup_dir=Path(args.backup))[
                    "exit"
                ]
            )
        if args.command == "all-prep":
            worst = int(backup(paths, Path(args.db) if args.db else None)["exit"])
            if args.with_cache_rows:
                rebuild_cache_rows(paths, dry_run=False, confirm=args.confirm)
            else:
                say("SKIPPED rebuild-cache-rows (pass --with-cache-rows --confirm)")
            fit(paths, force=args.force)
            worst = max(
                worst,
                int(compare(paths, days=args.days, with_sheet=args.with_sheet)["exit"]),
            )
            return worst
    except RefitError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr, flush=True)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
