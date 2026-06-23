from pathlib import Path
from typing import Sequence
import os

_env_store: dict[str, str] = {}


def load_project_dotenv(project_root: Path) -> dict[str, str]:
    """
    Read ${PROJECT_ROOT}/.env if present.
    Do not fail if .env is missing; return empty dict.
    Parse simple dotenv lines: KEY=value, optional quotes, ignore comments/invalid.
    Do not support command substitution or shell evaluation.
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


def get_credential(name: str, aliases: Sequence[str] = ()) -> str | None:
    """
    Retrieve credential by name, trying aliases in sequence.
    If the same key exists in real process env and .env, prefer real process env 
    only if it is non-empty; otherwise use .env.
    """
    keys = [name] + list(aliases)
    for k in keys:
        proc_val = os.environ.get(k)
        if proc_val is not None and proc_val != "":
            return proc_val
        if k in _env_store:
            return _env_store[k]
        if proc_val is not None:
            return proc_val
    return None


def credential_presence_map() -> dict[str, bool]:
    """
    Return credential presence as true/false, never values.
    """
    return {
        "sportdb": bool(get_credential("SPORTDB_API_KEY")),
        "football_data_org": bool(get_credential("FOOTBALL_DATA_ORG_KEY", ("FOOTBALL_DATA_API_KEY",))),
        "highlightly": bool(get_credential("HIGHLIGHTLY_API_KEY")),
        "api_football": bool(get_credential("API_FOOTBALL_KEY", ("API_FOOTBALL_API_KEY",))),
        "espn_baseline": False,
    }
