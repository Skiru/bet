"""Tiny, self-contained atomic JSON writer + SHA256 helper.

Deliberately does not import bet.pipeline.run_evidence: that module lives
under the bet.pipeline package, whose __init__.py pulls in a much larger
dependency graph (state/manifest/contracts/sharding/sports) this package has
no other reason to depend on. The behavior mirrors
bet.pipeline.run_evidence.write_json_atomic/sha256_file exactly (mkstemp in
the same directory, fsync best-effort, atomic os.replace).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path_str = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(temp_path, path)
    except Exception as exc:
        if temp_path.exists():
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise ValueError(f"Failed atomic write to {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()
