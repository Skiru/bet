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
        base_dir = Path(base_dir).resolve()
        if base_dir.name != "pipeline_runs" and "pipeline_runs" not in base_dir.parts:
            base_dir = base_dir / "pipeline_runs"

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
    from pathlib import Path

    from bet.pipeline.runtime_modes import parse_runtime_mode

    mode_enum = parse_runtime_mode(runtime_mode)

    run_root = resolve_run_root(betting_day, run_id, base_dir)
    data_dir = runtime_data_dir(run_root)
    coupon_dir = runtime_coupon_dir(run_root)
    artifact_dir = runtime_artifact_dir(run_root)

    # 1. Minimal platform allowlist
    allowed_platform_keys = {
        "PATH", "HOME", "TMPDIR", "TMP", "TEMP", "TZ",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
        "VIRTUAL_ENV", "NO_PROXY", "HTTP_PROXY", "HTTPS_PROXY",
        "TERM", "SSH_AUTH_SOCK", "USER", "LOGNAME", "SHELL",
    }

    env = {}
    for k, v in os.environ.items():
        if k in allowed_platform_keys or k.startswith("LC_") or k == "LANG":
            env[k] = v

    # 2. Live and write acknowledgements
    from bet.pipeline.runtime_modes import LIVE_ACK_KEY, WRITE_ACK_KEY
    if mode_enum == RuntimeMode.LIVE_SHADOW or mode_enum == RuntimeMode.PRODUCTION:
        if LIVE_ACK_KEY in os.environ:
            env[LIVE_ACK_KEY] = os.environ[LIVE_ACK_KEY]
    if mode_enum == RuntimeMode.PRODUCTION:
        if WRITE_ACK_KEY in os.environ:
            env[WRITE_ACK_KEY] = os.environ[WRITE_ACK_KEY]

    # 3. Provider credentials dynamically sourced from the registry
    try:
        from bet.provider_registry import load_provider_registry
        reg = load_provider_registry()
        allowed_credentials = []
        for provider in reg.values():
            cred_names = provider.policy.get("required_credential_names", [])
            allowed_credentials.extend(cred_names)
    except Exception:
        allowed_credentials = ["ODDSPAPI_API_KEY", "THE_ODDS_API_KEY", "ODDS_API_IO_KEY", "API_FOOTBALL_KEY"]

    for cred_name in allowed_credentials:
        if cred_name in os.environ:
            env[cred_name] = os.environ[cred_name]

    # 4. Sandbox controlled variables
    env.update({
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_BETTING_DAY": betting_day,
        "BET_PIPELINE_RUN_ID": run_root.name,
        "BET_PIPELINE_DATA_DIR": str(data_dir),
        "BET_PIPELINE_COUPON_DIR": str(coupon_dir),
        "BET_PIPELINE_ARTIFACT_DIR": str(artifact_dir),
        "BET_PIPELINE_RUNTIME_MODE": mode_enum.value,
    })

    repo_root = Path(__file__).resolve().parents[3]
    env["PYTHONPATH"] = f"{repo_root}/src:{repo_root}"
    env["BET_REPO_ROOT"] = str(repo_root)

    if mode_enum != RuntimeMode.PRODUCTION:
        env["DRY_RUN"] = "1"

    return env
