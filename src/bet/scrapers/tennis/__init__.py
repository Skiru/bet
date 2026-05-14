from __future__ import annotations

__all__ = ["TennisSackmannScraper", "TennisSofascoreScraper"]

def __getattr__(name: str):
    if name == "TennisSackmannScraper":
        from bet.scrapers.tennis.sackmann import TennisSackmannScraper
        return TennisSackmannScraper
    if name == "TennisSofascoreScraper":
        from bet.scrapers.tennis.sofascore_tennis import TennisSofascoreScraper
        return TennisSofascoreScraper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")