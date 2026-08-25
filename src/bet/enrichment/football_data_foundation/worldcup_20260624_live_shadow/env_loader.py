import os
from pathlib import Path
from typing import Any, Dict, Sequence, Optional

_env_store: Dict[str, str] = {}


def load_project_dotenv(project_root: Path) -> Dict[str, str]:
    """
    Read ${PROJECT_ROOT}/.env if present.
    Parse simple dotenv lines: KEY=value, optional quotes, ignore comments/invalid.
    """
    global _env_store
    _env_store.clear()

    env_path = project_root / ".env"
    if not env_path.exists():
        return {}

    try:
        content = env_path.read_text(encoding="utf-8")
    except Exception:
        return {}

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, val = stripped.split("=", 1)
        key = key.strip()
        val = val.strip()

        # Strip matching surrounding single or double quotes
        if len(val) >= 2 and (
            (val.startswith('"') and val.endswith('"')) or
            (val.startswith("'") and val.endswith("'"))
        ):
            val = val[1:-1]

        if key:
            _env_store[key] = val

    return _env_store.copy()


def get_credential(name: str, aliases: Sequence[str] = ()) -> Optional[str]:
    """
    Retrieve credential by name, trying aliases.
    Prefer process environment variable over .env if non-empty.
    """
    keys = [name] + list(aliases)
    for k in keys:
        proc_val = os.environ.get(k)
        if proc_val is not None and proc_val != "":
            return proc_val
        if k in _env_store:
            return _env_store[k]
    return None


def check_dotenv_preflight(project_root: Path) -> Dict[str, Any]:
    """
    Perform dotenv preflight checks and return the status without exposing credentials.
    """
    load_project_dotenv(project_root)

    keys_to_check = {
        "SPORTDB_API_KEY": ("SPORTDB_API_KEY",),
        "HIGHLIGHTLY_API_KEY": ("HIGHLIGHTLY_API_KEY",),
        "API_FOOTBALL_KEY": ("API_FOOTBALL_KEY", "API_FOOTBALL_API_KEY"),
        "FOOTBALL_DATA_ORG_KEY": ("FOOTBALL_DATA_ORG_KEY", "FOOTBALL_DATA_API_KEY"),
    }

    report = {}
    secret_leak_fail = False

    for canonical_name, aliases in keys_to_check.items():
        val = get_credential(canonical_name, aliases)
        present = val is not None and len(val.strip()) > 0

        # Determine source mode
        source_mode = "none"
        if present:
            is_in_proc = any(os.environ.get(k) for k in [canonical_name] + list(aliases))
            is_in_file = any(k in _env_store for k in [canonical_name] + list(aliases))
            if is_in_proc:
                source_mode = "environment"
            elif is_in_file:
                source_mode = "dotenv"

        report[canonical_name] = {
            "present": present,
            "source_mode": source_mode,
            "value_never_printed": True,
        }

        # Double check no leak occurs
        if val and (val in str(report) or val in canonical_name):
            secret_leak_fail = True

    return {
        "report": report,
        "secret_leak_check": "FAIL" if secret_leak_fail else "PASS"
    }
