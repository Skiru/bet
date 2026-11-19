"""Guards of the pre-registered stakes exams (measure_stakes_exam.py and the
replay recorder stakes_replay_record.py). Measurement infrastructure only:
nothing here reads an outcome, every check is on file metadata, git state or
raw bytes.

Three guards, each one of the 2026-11-18 deviations made impossible:

1. Replay completion (deviation 15, "explore on a partial dev"): a replay
   run directory ``full/<run>/`` counts only with a ``DONE.json`` written at
   a clean exit (rc 0) whose file list (path, size) equals the chunk files on
   disk. ``replay_problems`` lists what is wrong; the exam stages refuse on
   any.
2. G1 by commit (deviation 4, "hashes, no commit"): ``uncommitted`` lists
   every path that is not tracked or differs from HEAD (worktree or index).
3. The seal (G2): exam outcome files are chmod 000 right after they are
   written and entered in a manifest (path, sha256, size, sealed_utc, the
   atime seen before sealing). Only ``Unsealer`` (used by the exam mode)
   makes one readable again: it checks the manifest, logs the path and UTC to
   the run's access log, and seals the file again when the exam ends.
   Hashing reads raw bytes through a streaming sha256 and never deserialises.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DONE_NAME = "DONE.json"
CHUNK_GLOB = "*/*/*.pkl.gz"  # <tier>/<kind>/<YYYY-MM>_<part>.pkl.gz
MANIFEST_NAME = "exam_seal_manifest.json"
DONE_KEYS = ("rc", "finished_utc", "files")


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _write_json_atomic(path: Path, obj: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# 1. replay completion
def chunk_listing(run_dir: Path) -> list[list[Any]]:
    """[relative path, size] of every chunk file of one replay run (stat
    only; a sealed file is listed too)."""
    return [
        [p.relative_to(run_dir).as_posix(), p.stat().st_size]
        for p in sorted(run_dir.glob(CHUNK_GLOB))
    ]


def write_done(
    run_dir: Path, rc: int, counts: dict[str, Any], note: str = "",
    finished_utc: str | None = None,
) -> dict[str, Any]:
    """The completion marker. Refuses rc != 0: a failed or killed replay
    never gets one."""
    if rc != 0:
        raise ValueError(f"DONE marker refused: rc {rc}")
    doc = {
        "rc": 0,
        "finished_utc": finished_utc or utc_now(),
        "counts": counts,
        "files": chunk_listing(run_dir),
        "note": note,
    }
    _write_json_atomic(run_dir / DONE_NAME, doc)
    return doc


def replay_problems(full_dir: Path) -> list[str]:
    """Every replay run under ``full_dir`` must carry a clean DONE.json
    whose file list is the chunk files on disk. No run at all is a problem."""
    out: list[str] = []
    runs = (
        sorted(p for p in full_dir.iterdir() if p.is_dir()) if full_dir.is_dir() else []
    )
    if not runs:
        return [f"no replay run under {full_dir}"]
    for run in runs:
        marker = run / DONE_NAME
        if not marker.is_file():
            out.append(f"{run.name}: no {DONE_NAME} (replay not finished cleanly)")
            continue
        try:
            doc = json.loads(marker.read_text())
        except ValueError as exc:
            out.append(f"{run.name}: {DONE_NAME} unreadable ({exc})")
            continue
        missing = [k for k in DONE_KEYS if k not in doc]
        if missing:
            out.append(f"{run.name}: {DONE_NAME} lacks {missing}")
            continue
        if doc["rc"] != 0:
            out.append(f"{run.name}: rc {doc['rc']}")
        listed = {tuple(x) for x in doc["files"]}
        disk = {tuple(x) for x in chunk_listing(run)}
        if listed != disk:
            extra = sorted(p for p, _ in disk - listed)[:5]
            gone = sorted(p for p, _ in listed - disk)[:5]
            out.append(
                f"{run.name}: chunk files differ from {DONE_NAME} "
                f"(new / changed {extra}, missing / changed {gone})"
            )
    return out


# --------------------------------------------------------------------------
# 2. G1 by commit
def uncommitted(repo: Path, paths: Sequence[Path]) -> list[str]:
    """Each path must be tracked and equal to HEAD in the worktree and the
    index."""
    out: list[str] = []
    for p in paths:
        rel = os.path.relpath(p, repo)
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", rel],
            cwd=repo, capture_output=True,
        ).returncode == 0
        if not tracked:
            out.append(f"{rel}: not committed")
            continue
        clean = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", rel], cwd=repo,
            capture_output=True,
        ).returncode == 0
        if not clean:
            out.append(f"{rel}: differs from HEAD")
    return out


# --------------------------------------------------------------------------
# 3. the seal
def sha256_stream(path: Path, block: int = 1 << 20) -> str:
    """sha256 of the raw bytes, read in blocks; never deserialises."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(block):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(manifest: Path) -> dict[str, dict[str, Any]]:
    if not manifest.is_file():
        return {}
    doc = json.loads(manifest.read_text())
    return {e["path"]: e for e in doc["files"]}


def _save_manifest(manifest: Path, entries: dict[str, dict[str, Any]]) -> None:
    _write_json_atomic(
        manifest,
        {
            "_doc": (
                "Sealed exam outcome files (chmod 000; scripts/sofa/"
                "stakes_exam_guard.py). Only the exam mode unseals one, "
                "logging it to the run's access log."
            ),
            "files": [entries[k] for k in sorted(entries)],
        },
    )


def is_sealed(path: Path) -> bool:
    return stat.S_IMODE(path.stat().st_mode) == 0


def seal(paths: Iterable[Path], root: Path, manifest: Path) -> list[dict[str, Any]]:
    """Hash (streaming), chmod 000 and enter each file in the manifest. A
    file already sealed and listed with the same size is kept as it is."""
    entries = load_manifest(manifest)
    added: list[dict[str, Any]] = []
    for p in paths:
        rel = p.relative_to(root).as_posix()
        st = p.stat()
        if rel in entries and is_sealed(p) and entries[rel]["size"] == st.st_size:
            continue
        atime = dt.datetime.fromtimestamp(st.st_atime, dt.UTC)
        entry = {
            "path": rel,
            "sha256": sha256_stream(p),
            "size": st.st_size,
            "sealed_utc": utc_now(),
            "atime_before_seal_utc": atime.isoformat(timespec="seconds"),
        }
        os.chmod(p, 0)
        entries[rel] = entry
        added.append(entry)
    _save_manifest(manifest, entries)
    return added


def unlist(rel_paths: Iterable[str], manifest: Path) -> None:
    """Drop entries (the recorder deleting an unfinished month's chunks on
    resume)."""
    entries = load_manifest(manifest)
    for rel in rel_paths:
        entries.pop(rel, None)
    _save_manifest(manifest, entries)


def seal_problems(root: Path, manifest: Path, patterns: Sequence[str]) -> list[str]:
    """Every listed file present, still chmod 000, of its size; every file
    matching ``patterns`` (globs under root) listed."""
    entries = load_manifest(manifest)
    if not entries:
        return [f"no seal manifest at {manifest}"]
    out: list[str] = []
    for rel, e in entries.items():
        p = root / rel
        if not p.is_file():
            out.append(f"{rel}: sealed file missing")
        elif not is_sealed(p):
            mode = oct(stat.S_IMODE(p.stat().st_mode))
            out.append(f"{rel}: seal broken (mode {mode})")
        elif p.stat().st_size != e["size"]:
            out.append(f"{rel}: size differs from the manifest")
    for pat in patterns:
        for p in sorted(root.glob(pat)):
            if p.is_file() and p.relative_to(root).as_posix() not in entries:
                out.append(f"{p.relative_to(root).as_posix()}: outcome file not sealed")
    return out


class Unsealer:
    """The exam mode's only door to a sealed file: checks the manifest and
    the hash, makes the file readable (0400), appends ``UTC open <path>
    <sha256>`` to the access log and, when the exam ends (``close``),
    chmods every opened file back to 000 and logs it."""

    def __init__(self, root: Path, manifest: Path, access_log: Path) -> None:
        self.root = root
        self.entries = load_manifest(manifest)
        self.access_log = access_log
        self.opened: list[Path] = []

    def _log(self, what: str, rel: str, extra: str = "") -> None:
        self.access_log.parent.mkdir(parents=True, exist_ok=True)
        with self.access_log.open("a") as f:
            f.write(f"{utc_now()}\t{what}\t{rel}\t{extra}\n".rstrip("\t\n") + "\n")

    def open(self, path: Path) -> Path:
        rel = path.relative_to(self.root).as_posix()
        e = self.entries.get(rel)
        if e is None:
            raise PermissionError(f"{rel}: not in the seal manifest")
        os.chmod(path, 0o400)
        self.opened.append(path)
        got = sha256_stream(path)
        if got != e["sha256"]:
            raise PermissionError(f"{rel}: sha256 {got} differs from the manifest")
        self._log("open", rel, got)
        return path

    def close(self) -> None:
        for p in self.opened:
            os.chmod(p, 0)
            self._log("resealed", p.relative_to(self.root).as_posix())
        self.opened = []


@contextmanager
def unsealing(root: Path, manifest: Path, access_log: Path) -> Iterator[Unsealer]:
    u = Unsealer(root, manifest, access_log)
    try:
        yield u
    finally:
        u.close()
