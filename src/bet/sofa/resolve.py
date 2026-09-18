import logging
from datetime import UTC, datetime
from typing import Any, Literal

from rapidfuzz import fuzz

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, RefereeRecord, Sport
from bet.sofa.names import normalize_name

logger = logging.getLogger(__name__)

# Fuzzy threshold for the opponent's name (E4 step 6).
NAME_MATCH_THRESHOLD = 85.0
# At or above this, the two names are the same string after folding, so the
# identity is CONFIRMED rather than FUZZY.
NAME_EXACT_THRESHOLD = 99.0


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

    def match_quality(
        self, event: dict[str, Any], kickoff_utc: datetime, expected_opponent: str
    ) -> float | None:
        """How well this event matches, or None if it does not.

        Both conditions are required (E4 step 6): the kickoff within an aware
        ±24 h window, AND the opponent's name clearing the fuzzy threshold.
        Either alone matches another fixture of the same team.
        """
        start_ts = event.get("startTimestamp")
        if not start_ts:
            return None

        event_time = datetime.fromtimestamp(start_ts, UTC)
        if abs((event_time - kickoff_utc).total_seconds()) > 24 * 3600:
            return None

        home = normalize_name(event.get("homeTeam", {}).get("name", ""))
        away = normalize_name(event.get("awayTeam", {}).get("name", ""))

        best = max(
            fuzz.ratio(expected_opponent, home),
            fuzz.ratio(expected_opponent, away),
        )
        return float(best) if best > NAME_MATCH_THRESHOLD else None

    def _is_match(
        self, event: dict[str, Any], kickoff_utc: datetime, expected_opponent: str
    ) -> bool:
        return self.match_quality(event, kickoff_utc, expected_opponent) is not None

    def resolve_entity(
        self, sport: str, side: str, kickoff_utc: datetime, expected_opponent: str
    ) -> tuple[int | None, dict[str, Any] | None, bool]:
        """
        Returns (sofascore_id, matching_event, is_ambiguous).
        """
        norm_side = normalize_name(side)
        norm_opp = normalize_name(expected_opponent)

        # A name we recently failed to resolve costs a search plus up to three
        # listings. Paying that again every run, forever, was ~20% of the
        # request budget spent re-learning the same negative fact.
        if self.cache.get_entity_miss(sport, norm_side):
            return None, None, False

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
            self.cache.save_entity_miss(sport, norm_side)
            return None, None, False

        candidates = []
        for r in search_data["results"]:
            if (
                r.get("type") == "team"
                and r.get("entity", {}).get("sport", {}).get("slug") == sport
            ):
                candidates.append(r["entity"])
            if len(candidates) == 3:
                break

        matching_events = []

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
                status="verified",
            )
            self.cache.clear_entity_miss(sport, norm_side)
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
                    status="verified",
                )
                return cand["id"], evt, False
            return None, None, True

        # Nothing matched. Note this is only reached when the fixture was not
        # ambiguous: an ambiguous name may disambiguate tomorrow, so caching it
        # as a miss would suppress a resolution that is still possible.
        self.cache.save_entity_miss(sport, norm_side)
        return None, None, False


def parse_fixture(
    event: dict[str, Any],
    sport: Sport,
    superbet_event_ids: list[str],
    client: SofascoreClient,
    identity: Literal["CONFIRMED", "FUZZY"] = "CONFIRMED",
) -> Fixture:
    # /event/{id} carries what the listing does not: referee, round_number,
    # ground_type, best_of.
    details = client.event(event["id"])
    if details and "event" in details:
        event = details["event"]

    start_ts = event["startTimestamp"]
    kickoff_utc = datetime.fromtimestamp(start_ts, UTC)

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
            yellow_red_cards=referee_data.get("yellowRedCards", 0),
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
        competition_id=event.get("tournament", {})
        .get("uniqueTournament", {})
        .get("id", 0),
        season_id=event.get("season", {}).get("id", 0),
        category_name=event.get("tournament", {}).get("category", {}).get("name", ""),
        identity=identity,
        round_number=round_number,
        round_name=round_name,
        cup_round_type=cup_round_type,
        previous_leg_event_id=event.get("previousLegEventId"),
        venue_name=venue,
        referee=referee,
        has_xg=event.get("hasXg", False),
        ground_type=event.get("groundType"),
        best_of=event.get("defaultPeriodCount"),
    )


def resolve_league(
    name: str, expected_country: str, client: SofascoreClient
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
            # L23: match on category.country, never on results[0] — the
            # search returns FIFA World Cup for "championship" and Serie A for
            # "brazil serie b".
            if country.lower() == expected_country.lower():
                entity_id = entity.get("id")
                return int(entity_id) if entity_id is not None else None
    return None
