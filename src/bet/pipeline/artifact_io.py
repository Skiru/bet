"""Run-scoped immutable publication for canonical pipeline JSON artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ArtifactPublishError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class PublishedArtifact:
    path: Path
    sha256: str
    bytes_written: int
    already_present: bool


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _allowed_run_root(run_root: Path) -> Path:
    try:
        resolved = run_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ArtifactPublishError("ARTIFACT_RUN_ROOT_MISSING", str(run_root)) from exc
    if not resolved.is_dir() or (run_root.is_symlink() and run_root != Path("/tmp")):
        raise ArtifactPublishError("ARTIFACT_RUN_ROOT_INVALID", str(run_root))

    repo_reports = Path(__file__).resolve().parents[3] / "reports" / "pipeline_runs"
    temp_roots = {Path("/tmp").resolve(), Path(tempfile.gettempdir()).resolve()}
    allowed = any(resolved == root or resolved.is_relative_to(root) for root in temp_roots)
    allowed = allowed or resolved == repo_reports.resolve() or resolved.is_relative_to(repo_reports.resolve())
    if not allowed:
        raise ArtifactPublishError("ARTIFACT_RUN_ROOT_FORBIDDEN", str(resolved))
    return resolved


def _confined_target(run_root: Path, target: Path) -> Path:
    if ".." in target.parts:
        raise ArtifactPublishError("ARTIFACT_PATH_TRAVERSAL", str(target))
    candidate = target if target.is_absolute() else run_root / target
    if candidate.is_symlink():
        raise ArtifactPublishError("ARTIFACT_SYMLINK_ESCAPE", str(candidate))

    current = candidate.parent
    while current != current.parent and current != run_root:
        if current.exists() and current.is_symlink():
            is_macos_tmp_alias = current == Path("/tmp") and run_root.is_relative_to(Path("/private/tmp"))
            if not is_macos_tmp_alias:
                raise ArtifactPublishError("ARTIFACT_SYMLINK_ESCAPE", str(current))
        current = current.parent
    candidate = Path(os.path.realpath(candidate))
    try:
        candidate.parent.resolve(strict=False).relative_to(run_root)
    except ValueError as exc:
        raise ArtifactPublishError("ARTIFACT_CROSS_RUN_PATH", str(candidate)) from exc
    return candidate


def _validate_payload(
    payload: dict[str, Any], *, betting_day: str, run_id: str, artifact_type: str
) -> None:
    if payload.get("schema_version") not in {1, 2}:
        raise ArtifactPublishError("ARTIFACT_SCHEMA_INVALID", "schema_version must equal 1 or 2")
    if payload.get("betting_day") != betting_day:
        raise ArtifactPublishError("ARTIFACT_DAY_MISMATCH", str(payload.get("betting_day")))
    if payload.get("run_id") != run_id:
        raise ArtifactPublishError("ARTIFACT_RUN_MISMATCH", str(payload.get("run_id")))
    if payload.get("artifact_type") != artifact_type:
        raise ArtifactPublishError("ARTIFACT_TYPE_MISMATCH", str(payload.get("artifact_type")))


def publish_run_artifact(
    *,
    run_root: Path,
    target: Path,
    payload: dict[str, Any],
    betting_day: str,
    run_id: str,
    artifact_type: str,
    immutable: bool = True,
) -> PublishedArtifact:
    """Validate and atomically publish one current-run JSON artifact."""
    resolved_root = _allowed_run_root(Path(run_root))
    target_path = _confined_target(resolved_root, Path(target))
    _validate_payload(payload, betting_day=betting_day, run_id=run_id, artifact_type=artifact_type)
    content = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    expected_hash = _sha256_bytes(content)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path = _confined_target(resolved_root, target_path)
    if target_path.exists():
        existing = target_path.read_bytes()
        if immutable and existing != content:
            raise ArtifactPublishError("ARTIFACT_IMMUTABLE_CONFLICT", str(target_path))
        if existing == content:
            return PublishedArtifact(target_path, expected_hash, len(content), True)

    fd, temporary_name = tempfile.mkstemp(prefix=f".{target_path.name}.", suffix=".tmp", dir=target_path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        decoded = json.loads(temporary.read_text(encoding="utf-8"))
        _validate_payload(decoded, betting_day=betting_day, run_id=run_id, artifact_type=artifact_type)
        if immutable:
            # link(2) is an atomic create-if-absent operation on the same
            # filesystem.  Unlike an existence check followed by replace, it
            # cannot overwrite a competing publisher's artifact.
            try:
                os.link(temporary, target_path)
            except FileExistsError:
                existing = target_path.read_bytes()
                if existing != content:
                    raise ArtifactPublishError("ARTIFACT_IMMUTABLE_CONFLICT", str(target_path))
                return PublishedArtifact(target_path, expected_hash, len(content), True)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            os.replace(temporary, target_path)
        directory_fd = os.open(target_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    published = target_path.read_bytes()
    actual_hash = _sha256_bytes(published)
    if actual_hash != expected_hash:
        raise ArtifactPublishError("ARTIFACT_POST_PUBLISH_HASH_MISMATCH", str(target_path))
    return PublishedArtifact(target_path, actual_hash, len(published), False)


def publish_immutable_json_blob(
    *, run_root: Path, target: Path, payload: dict[str, Any]
) -> PublishedArtifact:
    """Exclusively publish a run-scoped JSON snapshot without stage metadata.

    Frozen configuration/history inputs are not pipeline artifacts themselves,
    but they require the same confinement and race guarantees.
    """
    resolved_root = _allowed_run_root(Path(run_root))
    target_path = _confined_target(resolved_root, Path(target))
    content = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    expected_hash = _sha256_bytes(content)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path = _confined_target(resolved_root, target_path)
    if target_path.exists():
        existing = target_path.read_bytes()
        if existing != content:
            raise ArtifactPublishError("ARTIFACT_IMMUTABLE_CONFLICT", str(target_path))
        return PublishedArtifact(target_path, expected_hash, len(content), True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.", suffix=".tmp", dir=target_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target_path)
        except FileExistsError:
            if target_path.read_bytes() != content:
                raise ArtifactPublishError("ARTIFACT_IMMUTABLE_CONFLICT", str(target_path))
            return PublishedArtifact(target_path, expected_hash, len(content), True)
        finally:
            temporary.unlink(missing_ok=True)
        directory_fd = os.open(target_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return PublishedArtifact(target_path, expected_hash, len(content), False)
