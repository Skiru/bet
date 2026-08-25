"""Runtime paths and environment builder for sandboxed execution."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

from bet.pipeline.runtime_modes import RuntimeMode


_BETTING_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def resolved_path(path: Path | str) -> Path:
    """Return one canonical filesystem spelling without requiring existence.

    macOS exposes ``/tmp`` through the ``/private/tmp`` symlink.  Pipeline
    lineage must compare filesystem locations, not the two lexical spellings.
    """
    return Path(path).expanduser().resolve(strict=False)


def paths_refer_to_same_location(left: Path | str, right: Path | str) -> bool:
    """Compare path identity after resolving aliases and symlinks."""
    try:
        return resolved_path(left) == resolved_path(right)
    except (OSError, RuntimeError, ValueError):
        return False


def system_temp_roots() -> tuple[Path, ...]:
    """Return canonical temporary roots supported by the current platform."""
    candidates = (tempfile.gettempdir(), "/tmp", "/var/tmp")
    roots: list[Path] = []
    for candidate in candidates:
        try:
            root = resolved_path(candidate)
        except (OSError, RuntimeError, ValueError):
            continue
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def is_system_temp_path(path: Path | str) -> bool:
    """Return whether *path* is within a canonical system temp root."""
    try:
        candidate = resolved_path(path)
    except (OSError, RuntimeError, ValueError):
        return False
    return any(
        candidate == root or candidate.is_relative_to(root)
        for root in system_temp_roots()
    )


def validate_run_identifiers(betting_day: str, run_id: str | None) -> tuple[str, str]:
    """Return safe run identifiers or fail before any path is created.

    Path components are deliberately much stricter than general filesystem names:
    absolute paths, traversal, separators, control characters, and empty IDs are
    never valid pipeline identity.
    """
    day = str(betting_day or "")
    rid = str(run_id or "default")
    if not _BETTING_DAY_RE.fullmatch(day):
        raise ValueError("INVALID_BETTING_DAY_IDENTIFIER")
    if not _RUN_ID_RE.fullmatch(rid) or rid in {".", ".."}:
        raise ValueError("INVALID_RUN_ID_IDENTIFIER")
    return day, rid


def _reject_symlinked_ancestors(path: Path, stop: Path) -> None:
    current = path
    while current != stop and current != current.parent:
        if current.exists() and current.is_symlink():
            raise ValueError("RUN_PATH_SYMLINK_FORBIDDEN")
        current = current.parent


def resolve_run_root(
    betting_day: str,
    run_id: str | None,
    base_dir: Path | None = None,
) -> Path:
    """Resolve the root path for a pipeline run.

    Default is reports/pipeline_runs/<betting_day>/<run_id>/
    """
    day, rid = validate_run_identifiers(betting_day, run_id)
    if base_dir is None:
        # Find repo root. 1: runtime_paths.py, 2: pipeline, 3: bet, 4: src, 5: repo_root
        repo_root = Path(__file__).resolve().parents[3]
        base_dir = repo_root / "reports" / "pipeline_runs"
    else:
        base_dir = Path(base_dir).resolve()
        if base_dir.name != "pipeline_runs" and "pipeline_runs" not in base_dir.parts:
            base_dir = base_dir / "pipeline_runs"

    base_dir = base_dir.resolve(strict=False)
    if base_dir.name == rid and base_dir.parent.name == day:
        candidate = base_dir
        approved_root = base_dir.parent.parent
    else:
        approved_root = base_dir
        candidate = base_dir / day / rid
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(approved_root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError("RUN_ROOT_ESCAPE_FORBIDDEN") from exc
    _reject_symlinked_ancestors(candidate, approved_root)
    return resolved


def runtime_data_dir(run_root: Path) -> Path:
    """Get the sandboxed data directory for the run."""
    return Path(run_root) / "data"


def runtime_coupon_dir(run_root: Path) -> Path:
    """Get the sandboxed coupon directory for the run."""
    return Path(run_root) / "coupons"


def runtime_artifact_dir(run_root: Path) -> Path:
    """Get the sandboxed artifact directory for the run."""
    return Path(run_root) / "artifacts"


def build_runtime_env(
    runtime_mode: RuntimeMode | str,
    betting_day: str,
    run_id: str | None,
    base_dir: Path | None = None,
) -> dict[str, str]:
    """Build environment dictionary with sandboxed path configurations."""
    from pathlib import Path

    from bet.pipeline.runtime_modes import parse_runtime_mode, runtime_mode_capabilities

    mode_enum = parse_runtime_mode(runtime_mode)

    run_root = resolve_run_root(betting_day, run_id, base_dir)
    data_dir = runtime_data_dir(run_root)
    coupon_dir = runtime_coupon_dir(run_root)
    artifact_dir = runtime_artifact_dir(run_root)

    # 1. Minimal platform allowlist
    allowed_platform_keys = {
        "PATH",
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "TZ",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "VIRTUAL_ENV",
        "NO_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "TERM",
        "SSH_AUTH_SOCK",
        "USER",
        "LOGNAME",
        "SHELL",
        "DATABASE_URL",
        "BET_DB_PATH",
        "BET_KEEP_TEMP_DB",
    }

    env = {}
    for k, v in os.environ.items():
        if k in allowed_platform_keys or k.startswith("LC_") or k == "LANG":
            env[k] = v

    # 2. Live and write acknowledgements
    from bet.pipeline.runtime_modes import LIVE_ACK_KEY, WRITE_ACK_KEY

    if mode_enum in (RuntimeMode.LIVE_ANALYSIS_SHADOW, RuntimeMode.LIVE_SHADOW, RuntimeMode.PRODUCTION):
        if LIVE_ACK_KEY in os.environ:
            env[LIVE_ACK_KEY] = os.environ[LIVE_ACK_KEY]
    if mode_enum == RuntimeMode.PRODUCTION:
        if WRITE_ACK_KEY in os.environ:
            env[WRITE_ACK_KEY] = os.environ[WRITE_ACK_KEY]

    # The S6 history source is the only caller-supplied pipeline path allowed
    # through.  It must be either the canonical journal or a run-local replay
    # fixture; arbitrary inherited BET_PIPELINE_* variables remain excluded.
    ledger_value = os.environ.get("BET_PIPELINE_LEDGER_PATH")
    if ledger_value:
        ledger_path = Path(ledger_value).resolve(strict=False)
        canonical_ledger = (
            Path(__file__).resolve().parents[3]
            / "betting"
            / "journal"
            / "picks-ledger.csv"
        ).resolve(strict=False)
        if (
            ledger_path == canonical_ledger
            or ledger_path == run_root
            or ledger_path.is_relative_to(run_root)
        ) and not Path(ledger_value).is_symlink():
            env["BET_PIPELINE_LEDGER_PATH"] = str(ledger_path)

    # 3. Provider credentials dynamically sourced from the registry
    from bet.provider_registry import load_provider_registry

    try:
        reg = load_provider_registry()
    except Exception as exc:
        raise ValueError(f"PROVIDER_REGISTRY_LOAD_FAILED: {exc}") from exc

    allowed_credentials_set = set()
    for provider in reg.values():
        cred_names = provider.policy.get("required_credential_names", [])
        for cred_name in cred_names:
            if not isinstance(cred_name, str) or not cred_name.strip():
                raise ValueError("PROVIDER_REGISTRY_CREDENTIAL_NAME_INVALID")
            allowed_credentials_set.add(cred_name.strip())

    allowed_credentials = sorted(allowed_credentials_set)

    for cred_name in allowed_credentials:
        if cred_name in os.environ:
            env[cred_name] = os.environ[cred_name]

    # 4. Sandbox controlled variables
    env.update(
        {
            "BET_PIPELINE_RUN_ROOT": str(run_root),
            "BET_PIPELINE_BETTING_DAY": betting_day,
            "BET_PIPELINE_RUN_ID": run_root.name,
            "BET_PIPELINE_DATA_DIR": str(data_dir),
            "BET_PIPELINE_COUPON_DIR": str(coupon_dir),
            "BET_PIPELINE_ARTIFACT_DIR": str(artifact_dir),
            "BET_PIPELINE_RUNTIME_MODE": mode_enum.value,
        }
    )

    capabilities = runtime_mode_capabilities(mode_enum)
    if mode_enum is RuntimeMode.LIVE_ANALYSIS_SHADOW:
        shadow_db = data_dir / "runtime_analysis_shadow.db"
        env.update(
            {
                "BET_DB_PATH": str(shadow_db),
                "DATABASE_URL": f"sqlite:///{shadow_db}",
                "BET_PIPELINE_SELECTION_RUN_ID": run_root.name,
                "BET_PIPELINE_SELECTION_HASH": "0" * 64,
                "BET_PIPELINE_STORAGE_SCOPE": "SHADOW",
                "BET_PIPELINE_SHADOW_WRITE_ALLOWED": "1",
                "BET_PIPELINE_CANONICAL_WRITE_ALLOWED": "0",
                "BET_PIPELINE_S9_ALLOWED": "0",
                "BET_PIPELINE_BOOKMAKER_ALLOWED": "0",
                "BET_PIPELINE_AUTOMATED_BET_PLACEMENT_ALLOWED": "0",
            }
        )

    repo_root = Path(__file__).resolve().parents[3]
    python_paths = [str(repo_root / "src"), str(repo_root)]
    locked_site_packages = (
        repo_root
        / ".venv"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    if locked_site_packages.is_dir():
        python_paths.append(str(locked_site_packages))
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    env["BET_REPO_ROOT"] = str(repo_root)

    if capabilities.synthetic_outputs:
        env["DRY_RUN"] = "1"
    elif mode_enum is RuntimeMode.LIVE_ANALYSIS_SHADOW:
        env["DRY_RUN"] = "0"

    return env


def verify_db_write_isolation(
    *,
    target_db_path: Path | str,
    canonical_db_path: Path | str,
    shadow_db_path: Path | str,
    storage_scope: str,
) -> tuple[bool, str]:
    """Fail closed before a runtime write target is opened."""
    target = resolved_path(target_db_path)
    canonical = resolved_path(canonical_db_path)
    shadow = resolved_path(shadow_db_path)
    if target == canonical:
        return False, "CANONICAL_DB_WRITE_PROHIBITED"
    if storage_scope != "SHADOW":
        return False, "RUNTIME_STORAGE_SCOPE_INVALID"
    if target != shadow:
        return False, "SHADOW_DB_TARGET_MISMATCH"
    return True, ""


def is_safe_run_path(
    path: Path | str | None,
    run_root: Path | str,
    betting_day: str | None = None,
    run_id: str | None = None,
) -> bool:
    """Enforce unified path safety rules.

    A path is safe when:
    - it is inside the exact current run root;
    - it does not escape via symlink or traversal;
    - it is not a protected operational DB or journal;
    - it is not another run;
    - it is not source/config/test code.
    """
    if not path:
        return False

    try:
        raw_path = Path(path)
        raw_root = Path(run_root)
        if raw_path.exists() and raw_path.is_symlink():
            return False
        current = raw_path if raw_path.is_absolute() else raw_root / raw_path
        while current != raw_root and current != current.parent:
            if current.exists() and current.is_symlink():
                return False
            current = current.parent
        path_p = raw_path.resolve()
        run_root_p = raw_root.resolve()
    except Exception:
        return False

    # Traversal check: must be inside run_root_p
    try:
        path_p.relative_to(run_root_p)
    except ValueError:
        return False

    # Must not contain operational databases or journals
    path_str = str(path_p).lower()
    if "journal" in path_str or path_p.suffix in {".db", ".sqlite", ".sqlite3"}:
        return False

    # Must not contain source/config/test code
    for parent in path_p.parents:
        if parent.name in {
            "src",
            "tests",
            "config",
            "scripts",
            ".git",
            ".github",
            ".kilo",
        }:
            return False

    return True
