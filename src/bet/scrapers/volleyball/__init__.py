from __future__ import annotations

__all__ = ["VolleyboxScraper", "VolleySofascoreScraper"]


def __getattr__(name: str):
    if name == "VolleyboxScraper":
        from bet.scrapers.volleyball.volleybox import VolleyboxScraper
        return VolleyboxScraper
    if name == "VolleySofascoreScraper":
        from bet.scrapers.volleyball.sofascore_volley import VolleySofascoreScraper
        return VolleySofascoreScraper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
