"""Atomic artifact writes: a crash mid-write never leaves half a file.

A stage that dies inside a plain ``write_text`` leaves a truncated JSON that
the next stage then reads (or refuses with a parse error that names the wrong
cause). Every write goes to ``<name>.tmp`` beside the target and is moved into
place with ``os.replace``, which is atomic on one filesystem.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path


def tmp_path(path: Path) -> Path:
    """The temporary sibling a write goes through before ``os.replace``.

    Named per process and thread: two writers of one file (a rebuild beside a
    loop) sharing ``<name>.tmp`` would interleave into it before either
    replaced the target.
    """
    return path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")


def write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` through a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path(path)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path(path)
    tmp.write_bytes(data)
    os.replace(tmp, path)
