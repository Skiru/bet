"""Project dotenv access shared by API clients."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_project_dotenv() -> dict[str, str]:
    """Read the project .env without overriding process environment values."""
    values: dict[str, str] = {}
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return values

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def get_env(name: str, *aliases: str) -> str:
    """Return a non-empty process value, then a non-empty project .env value."""
    dotenv_values = load_project_dotenv()
    for key in (name, *aliases):
        process_value = os.environ.get(key, "").strip()
        if process_value:
            return process_value
        dotenv_value = dotenv_values.get(key, "").strip()
        if dotenv_value:
            return dotenv_value
    return ""