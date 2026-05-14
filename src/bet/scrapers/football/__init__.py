from __future__ import annotations

__all__ = ["FootballFBrefScraper"]


def __getattr__(name: str):
    if name == "FootballFBrefScraper":
        from bet.scrapers.football.fbref import FootballFBrefScraper
        return FootballFBrefScraper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
