from __future__ import annotations

__all__ = ["TennisSackmannScraper"]

def __getattr__(name: str):
    if name == "TennisSackmannScraper":
        from bet.scrapers.tennis.sackmann import TennisSackmannScraper
        return TennisSackmannScraper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")