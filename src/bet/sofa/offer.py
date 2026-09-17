from typing import Any

from bet.sofa.contracts import Fixture, FixtureOffer, PricedRung
from bet.sofa.market_mapper import classify_market
from bet.sofa.timeutil import now


class OfferFetcher:
    def __init__(self, client: Any) -> None:
        self.client = client

    def fetch_offers(self, fixtures: list[Fixture]) -> list[FixtureOffer]:
        results = []
        for fixture in fixtures:
            combined_odds: dict[tuple[str, str, float], dict[str, Any]] = {}
            unmapped = set()
            
            for su_id in fixture.superbet_event_ids:
                odds_data = self.client.event_odds(su_id)
                if not odds_data or "odds" not in odds_data:
                    continue
                    
                fetched_at = now()
                
                for item in odds_data["odds"]:
                    market_name = item.get("marketName")
                    if not market_name:
                        continue
                        
                    classified = classify_market(market_name)
                    if not classified:
                        unmapped.add(market_name)
                        continue
                        
                    market, subject = classified
                    
                    try:
                        line = float(item.get("specialBetValue", 0.0))
                    except ValueError:
                        continue
                        
                    name_lower = item.get("name", "").lower()
                    direction = None
                    if "poniżej" in name_lower or "under" in name_lower:
                        direction = "UNDER"
                    elif "powyżej" in name_lower or "over" in name_lower:
                        direction = "OVER"
                        
                    if not direction:
                        continue
                        
                    price = item.get("price")
                    if price is None:
                        continue
                        
                    key = (market, subject, line)
                    if key not in combined_odds:
                        combined_odds[key] = {
                            "over_odds": None, 
                            "under_odds": None, 
                            "fetched_at_utc": fetched_at
                        }
                        
                    if direction == "OVER":
                        combined_odds[key]["over_odds"] = float(price)
                    else:
                        combined_odds[key]["under_odds"] = float(price)
                        
            rungs = []
            for (market, subject, line), odds_dict in combined_odds.items():
                rungs.append(
                    PricedRung(
                        market=market,
                        subject=subject,
                        line=line,
                        over_odds=odds_dict["over_odds"],
                        under_odds=odds_dict["under_odds"],
                        fetched_at_utc=odds_dict["fetched_at_utc"]
                    )
                )
                
            results.append(
                FixtureOffer(
                    sofascore_event_id=fixture.sofascore_event_id,
                    status="PRICED" if rungs else "NO_PRICE",
                    rungs=rungs,
                    unmapped_markets=sorted(list(unmapped))
                )
            )
            
        return results
