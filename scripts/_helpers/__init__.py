"""Shared helper entry points for bounded enrichment adapters."""

from . import volleyball_rich_completion
from .volleyball_rich_completion import (
    get_missing_volleyball_rich_stat_keys,
    get_volleyball_rich_stat_keys,
)

_get_recent_volleyball_fixtures = volleyball_rich_completion._get_recent_volleyball_fixtures
_store_in_cache = volleyball_rich_completion._store_in_cache
get_client = volleyball_rich_completion.get_client
_ORIGINAL_GET_RECENT_VOLLEYBALL_FIXTURES = _get_recent_volleyball_fixtures
_ORIGINAL_STORE_IN_CACHE = _store_in_cache
_ORIGINAL_GET_CLIENT = get_client


def _sync_volleyball_helper_attr(name: str, package_value, original_value):
    if package_value is not original_value and getattr(volleyball_rich_completion, name) is not package_value:
        setattr(volleyball_rich_completion, name, package_value)


def complete_volleyball_rich_stats(*args, **kwargs):
    _sync_volleyball_helper_attr(
        "_get_recent_volleyball_fixtures",
        _get_recent_volleyball_fixtures,
        _ORIGINAL_GET_RECENT_VOLLEYBALL_FIXTURES,
    )
    _sync_volleyball_helper_attr("_store_in_cache", _store_in_cache, _ORIGINAL_STORE_IN_CACHE)
    _sync_volleyball_helper_attr("get_client", get_client, _ORIGINAL_GET_CLIENT)
    return volleyball_rich_completion.complete_volleyball_rich_stats(*args, **kwargs)


__all__ = [
    "volleyball_rich_completion",
    "complete_volleyball_rich_stats",
    "get_missing_volleyball_rich_stat_keys",
    "get_volleyball_rich_stat_keys",
    "_get_recent_volleyball_fixtures",
    "_store_in_cache",
    "get_client",
]
