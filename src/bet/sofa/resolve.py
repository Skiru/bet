import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import BoardFixture, Fixture, GapReason, RefereeRecord
from bet.sofa.names import normalize_name

logger = logging.getLogger(__name__)

def split_match_name(match_name: str) -> tuple[str, str]:
    parts = match_name.split("·")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", ""

class SofaResolver:
    def __init__(self, config: SofaConfig, client: SofascoreClient, cache: SofaCache):
        self.config = config
        self.client = client
        self.cache = cache

    def _fetch_events(self, entity_id: int) -> list[dict[str, Any]]:
        events = []
        for kind in ("next", "last"):
            for page in range(3):
                data = self.cache.get_entity_events(entity_id, kind, page)
                if not data:
                    data = self.client.entity_events(entity_id, kind, page)
                    if data:
                        self.cache.save_entity_events(entity_id, kind, page, data)
                if data and "events" in data:
                    events.extend(data["events"])
                    if not data.get("hasNextPage"):
                        break
                else:
                    break
        return events
        
    def _is_match(
        self,
        event: dict[str, Any],
        kickoff_utc: datetime,
        expected_opponent: str
    ) -> bool:
        start_ts = event.get("startTimestamp")
        if not start_ts:
            return False
            
        event_time = datetime.fromtimestamp(start_ts, timezone.utc)
        diff = abs((event_time - kickoff_utc).total_seconds())
        if diff > 24 * 3600:
            return False
            
        home = normalize_name(event.get("homeTeam", {}).get("name", ""))
        away = normalize_name(event.get("awayTeam", {}).get("name", ""))
        
        ratio_home = fuzz.ratio(expected_opponent, home)
        ratio_away = fuzz.ratio(expected_opponent, away)
        
        return max(ratio_home, ratio_away) > 85.0

    def resolve_entity(
        self,
        sport: str,
        side: str,
        kickoff_utc: datetime,
        expected_opponent: str
    ) -> tuple[int | None, dict[str, Any] | None, bool]:
        """
        Returns (sofascore_id, matching_event, is_ambiguous).
        """
        norm_side = normalize_name(side)
        norm_opp = normalize_name(expected_opponent)
        
        cached = self.cache.get_entity(sport, norm_side)
        if cached and cached["status"] == "verified":
            # Just verify event exists
            events = self._fetch_events(cached["sofascore_id"])
            for e in events:
                if self._is_match(e, kickoff_utc, norm_opp):
                    return cached["sofascore_id"], e, False
                    
        # Miss -> search/all
        search_data = self.client.search(norm_side)
        if not search_data or "results" not in search_data:
            return None, None, False
            
        candidates = []
        for r in search_data["results"]:
            if r.get("type") == "team" and r.get("entity", {}).get("sport", {}).get("slug") == sport:
                candidates.append(r["entity"])
            if len(candidates) == 3:
                break
                
        matching_events = []
        best_candidate = None
        
        for cand in candidates:
            events = self._fetch_events(cand["id"])
            for e in events:
                if self._is_match(e, kickoff_utc, norm_opp):
                    matching_events.append((cand, e))
                    
        if len(matching_events) == 1:
            cand, evt = matching_events[0]
            self.cache.save_entity(
                sport=sport,
                query_key=norm_side,
                sofascore_id=cand["id"],
                sofascore_name=cand.get("name", ""),
                entity_type="team",
                country=cand.get("country", {}).get("name"),
                status="verified"
            )
            return cand["id"], evt, False
        elif len(matching_events) > 1:
            # Check if all matching events are the SAME event (duplicate candidates)
            event_ids = {e["id"] for _, e in matching_events}
            if len(event_ids) == 1:
                cand, evt = matching_events[0]
                self.cache.save_entity(
                    sport=sport,
                    query_key=norm_side,
                    sofascore_id=cand["id"],
                    sofascore_name=cand.get("name", ""),
                    entity_type="team",
                    country=cand.get("country", {}).get("name"),
                    status="verified"
                )
                return cand["id"], evt, False
            return None, None, True
            
        return None, None, False

def parse_fixture(
    event: dict[str, Any],
    sport: str,
    superbet_event_ids: list[str],
    client: SofascoreClient
) -> Fixture:
    # Need to fetch /event/{id} to get details (referee, round_number, ground_type, best_of)
    details = client.event(event["id"])
    if details and "event" in details:
        event = details["event"]
        
    start_ts = event["startTimestamp"]
    kickoff_utc = datetime.fromtimestamp(start_ts, timezone.utc)
    
    round_info = event.get("roundInfo", {})
    round_number = round_info.get("round")
    round_name = round_info.get("name")
    cup_round_type = round_info.get("cupRoundType")
    
    venue = event.get("venue", {}).get("name")
    
    referee_data = event.get("referee")
    referee = None
    if referee_data:
        referee = RefereeRecord(
            name=referee_data.get("name", ""),
            games=referee_data.get("games", 0),
            yellow_cards=referee_data.get("yellowCards", 0),
            red_cards=referee_data.get("redCards", 0),
            yellow_red_cards=referee_data.get("yellowRedCards", 0)
        )
        
    return Fixture(
        sofascore_event_id=event["id"],
        superbet_event_ids=superbet_event_ids,
        sport=sport,
        kickoff_utc=kickoff_utc,
        home_name=event.get("homeTeam", {}).get("name", ""),
        away_name=event.get("awayTeam", {}).get("name", ""),
        home_entity_id=event.get("homeTeam", {}).get("id", 0),
        away_entity_id=event.get("awayTeam", {}).get("id", 0),
        competition_name=event.get("tournament", {}).get("name", ""),
        competition_id=event.get("tournament", {}).get("uniqueTournament", {}).get("id", 0),
        season_id=event.get("season", {}).get("id", 0),
        category_name=event.get("tournament", {}).get("category", {}).get("name", ""),
        identity="CONFIRMED",
        round_number=round_number,
        round_name=round_name,
        cup_round_type=cup_round_type,
        previous_leg_event_id=event.get("previousLegEventId"),
        venue_name=venue,
        referee=referee,
        has_xg=event.get("hasXg", False),
        ground_type=event.get("groundType"),
        best_of=event.get("defaultPeriodCount")
    )

def resolve_league(
    name: str,
    expected_country: str,
    client: SofascoreClient
) -> int | None:
    """
    Used for backfill (E10) to find the correct uniqueTournament.id 
    based on category.country, avoiding the 'results[0]' trap.
    """
    search_data = client.search(name)
    if not search_data or "results" not in search_data:
        return None
        
    for r in search_data["results"]:
        if r.get("type") == "uniqueTournament":
            entity = r.get("entity", {})
            country = entity.get("category", {}).get("name", "")
            if country.lower() == expected_country.lower() or expected_country.lower() == "world" and country.lower() == "world":
                return entity.get("id")
    return None
