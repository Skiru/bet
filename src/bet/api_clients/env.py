"""The project ``.env`` is the single source of truth for provider settings.

Credentials and per-provider tunables are read from exactly two places, in
this order:

1. the process environment (``os.environ``) -- the standard override for CI,
   one-off shell runs and tests;
2. the project ``.env`` file -- the file you edit.

There is deliberately no third source. ``config/api_keys.json`` and
``config/odds_api_key.txt`` used to be silent fallbacks, which meant a key
could live in two files at once and disagree -- and it did: ``.env`` carried
TheSportsDB's demo key ``123`` while ``config/api_keys.json`` held a real one,
so the demo key silently won and nothing ever raised. Two stores with a quiet
fallback turn a credential problem into a behaviour problem you debug at the
provider instead of at the config.

Parsing is delegated to ``python-dotenv`` (already a project dependency)
rather than hand-rolled, so quoting, escapes, ``export`` prefixes and multi-line
values behave the way every other tool in the ecosystem expects.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"

# Prefix for per-provider quota overrides, e.g. BET_LIMIT_HIGHLIGHTLY=250.
LIMIT_ENV_PREFIX = "BET_LIMIT_"

_cache: dict[str, str] = {}
_cache_stamp: tuple[float, int] | None = None
_cache_lock = threading.Lock()


class MissingCredentialError(RuntimeError):
    """A required provider credential is absent from the process env and .env."""


def _dotenv() -> dict[str, str]:
    """Parsed ``.env``, re-read only when the file changes on disk.

    ``get_env`` is called once per client construction, so re-parsing on every
    call was pure overhead; keying the cache on (mtime, size) keeps an edit to
    ``.env`` visible without restarting a long-lived process.
    """
    global _cache, _cache_stamp
    try:
        stat = ENV_PATH.stat()
        stamp = (stat.st_mtime, stat.st_size)
    except OSError:
        with _cache_lock:
            _cache, _cache_stamp = {}, None
        return {}

    with _cache_lock:
        if _cache_stamp == stamp:
            return _cache
    parsed = {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}
    with _cache_lock:
        _cache, _cache_stamp = parsed, stamp
        return _cache


def reload_env() -> dict[str, str]:
    """Drop the cached ``.env`` and re-read it. For tests and long-running agents."""
    global _cache_stamp
    with _cache_lock:
        _cache_stamp = None
    return _dotenv()


def get_env(name: str, *aliases: str) -> str:
    """First non-empty value for ``name`` or any alias. ``""`` when absent."""
    values = _dotenv()
    for key in (name, *aliases):
        process_value = os.environ.get(key, "").strip()
        if process_value:
            return process_value
        dotenv_value = (values.get(key) or "").strip()
        if dotenv_value:
            return dotenv_value
    return ""


def require_env(name: str, *aliases: str) -> str:
    """``get_env`` that raises instead of returning an empty string.

    Use where a missing credential should stop the caller outright rather than
    surface later as an unexplained empty response.
    """
    value = get_env(name, *aliases)
    if not value:
        names = " / ".join((name, *aliases))
        raise MissingCredentialError(
            f"Missing required credential: set {names} in {ENV_PATH}"
        )
    return value


def get_env_int(name: str, *aliases: str, default: int | None = None) -> int | None:
    """Integer-valued setting, or ``default`` when unset or unparseable."""
    raw = get_env(name, *aliases)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def limit_env_var(api_name: str) -> str:
    """The ``.env`` variable that overrides one provider's quota.

    ``highlightly`` -> ``BET_LIMIT_HIGHLIGHTLY``,
    ``api-football`` -> ``BET_LIMIT_API_FOOTBALL``.
    """
    return LIMIT_ENV_PREFIX + api_name.upper().replace("-", "_")


def get_limit_override(api_name: str) -> int | None:
    """Per-provider quota from ``.env``, or None to fall back to the code default."""
    return get_env_int(limit_env_var(api_name))


# Back-compat shim: callers that used to parse .env themselves.
def load_project_dotenv() -> dict[str, str]:
    """Every key defined in the project ``.env`` (process env not merged in)."""
    return dict(_dotenv())
