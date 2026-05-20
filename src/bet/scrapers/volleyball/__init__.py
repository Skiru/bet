from __future__ import annotations

__all__ = ["VolleyboxScraper"]


def __getattr__(name: str):
    if name == "VolleyboxScraper":
        from bet.scrapers.volleyball.volleybox import VolleyboxScraper
        return VolleyboxScraper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
