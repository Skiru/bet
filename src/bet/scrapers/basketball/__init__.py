from __future__ import annotations

__all__ = ["BasketballNBAScraper", "BasketballBRefScraper"]

def __getattr__(name: str):
    if name == "BasketballNBAScraper":
        from bet.scrapers.basketball.nba_api_scraper import BasketballNBAScraper
        return BasketballNBAScraper
    if name == "BasketballBRefScraper":
        from bet.scrapers.basketball.bball_ref import BasketballBRefScraper
        return BasketballBRefScraper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")