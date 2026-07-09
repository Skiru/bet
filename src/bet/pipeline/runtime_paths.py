"""Runtime paths and environment builder for sandboxed execution."""
from __future__ import annotations

import os
from pathlib import Path
from bet.pipeline.runtime_modes import RuntimeMode


def resolve_run_root(
    betting_day: str,
    run_id: str | None,
    base_dir: Path | None = None,
) -> Path:
    """Resolve the root path for a pipeline run.

    Default is reports/pipeline_runs/<betting_day>/<run_id>/
    """
    if base_dir is None:
        # Find repo root. 1: runtime_paths.py, 2: pipeline, 3: bet, 4: src, 5: repo_root
        repo_root = Path(__file__).resolve().parents[3]
        base_dir = repo_root / "reports" / "pipeline_runs"
    else:
        base_dir = Path(base_dir)

    rid = run_id if run_id else "default"
    if base_dir.name == rid and base_dir.parent.name == betting_day:
        return base_dir
    return base_dir / betting_day / rid


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
    from bet.pipeline.runtime_modes import parse_runtime_mode

    mode_enum = parse_runtime_mode(runtime_mode)

    run_root = resolve_run_root(betting_day, run_id, base_dir)
    data_dir = runtime_data_dir(run_root)
    coupon_dir = runtime_coupon_dir(run_root)
    artifact_dir = runtime_artifact_dir(run_root)

    env = {
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_BETTING_DAY": betting_day,
        "BET_PIPELINE_RUN_ID": run_root.name,
        "BET_PIPELINE_DATA_DIR": str(data_dir),
        "BET_PIPELINE_COUPON_DIR": str(coupon_dir),
        "BET_PIPELINE_ARTIFACT_DIR": str(artifact_dir),
        "BET_PIPELINE_RUNTIME_MODE": mode_enum.value,
    }
    if mode_enum != RuntimeMode.PRODUCTION:
        env["DRY_RUN"] = "1"

    return env
