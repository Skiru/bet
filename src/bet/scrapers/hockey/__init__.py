from __future__ import annotations

__all__ = ["HockeyNHLScraper", "HockeyRefScraper"]


def __getattr__(name: str):
    if name == "HockeyNHLScraper":
        from bet.scrapers.hockey.nhl_api import HockeyNHLScraper
        return HockeyNHLScraper
    if name == "HockeyRefScraper":
        from bet.scrapers.hockey.hockey_ref import HockeyRefScraper
        return HockeyRefScraper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
