import logging
from datetime import UTC, datetime
from typing import Any, Literal

from rapidfuzz import fuzz

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, RefereeRecord, Sport
from bet.sofa.names import levels_compatible, normalize_name

logger = logging.getLogger(__name__)

# Fuzzy threshold for the opponent's name (E4 step 6).
#
# 82 with `name_score` below, not 85 with a bare `fuzz.ratio`. The pair was
# measured together, on the 982 (board side -> Sofascore side) pairs of the
# 2026-09-18 slate, against every other team name of the same sport that day
# as the negative set — 496,058 comparisons:
#
#     fuzz.ratio            @85   recall 87.3%   11 false pairs (0.22 / 10k)
#     name_score + level    @82   recall 97.1%   11 false pairs (0.22 / 10k)
#     name_score + level    @85   recall 96.2%    6 false pairs (0.12 / 10k)
#
# (Both rows are measured through the shipped `normalize_name`, so the alias
# table's contribution is in the baseline too; the 9.8 pp is the scorer and the
# threshold alone.) So this is +9.8 pp of recall at exactly the false-positive
# rate production already ran at. What the old threshold was actually
# rejecting was club
# affixes, because `fuzz.ratio` is whole-string: "lens" against "rc lens"
# scores 72.7, "monaco" against "as monaco" 80.0. Two Ligue 1 and Bundesliga
# fixtures — Monaco·Lens and Bayern Monachium·Union Berlin — were dropped from
# the 2026-09-18 slate for exactly that, with the right event found, in
# window, and refused on the name (F50).
NAME_MATCH_THRESHOLD = 82.0
# At or above this, the two names are the same string after folding, so the
# identity is CONFIRMED rather than FUZZY. Compared on `fuzz.ratio` alone, and
# deliberately: a token-set score of 100 means "one name's words are a subset
# of the other's", which is a good reason to accept a match and no reason at
# all to call the two strings equal. "Lens" is not the string "RC Lens".
NAME_EXACT_THRESHOLD = 99.0


def name_score(a: str, b: str) -> float:
    """How alike two team names are, ignoring club affixes.

    `fuzz.ratio` measures the whole string, so every "FC", "AS", "RC", "1." and
    "SC" that one source prints and the other does not is charged as a
    difference — and on a short name that is most of the string. `token_set`
    compares the word sets instead, which is exactly the right question for
    "RC Lens" vs "Lens" and the wrong one for "Real Madrid" vs "Real Sociedad"
    (58.3 either way). Taking the larger keeps both readings.
    """
    return max(fuzz.ratio(a, b), fuzz.token_set_ratio(a, b))

# How far the two sources' kickoffs may differ and still be the same match.
#
# Per sport, and that is not tidiness. In football the median disagreement is
# 0 minutes, so ±24 h buys nothing and costs the F25 defect directly: 23 h was
# exactly the gap that let "the same two clubs, tomorrow, in the women's
# league" look like today's men's fixture. In tennis eight-hour disagreements
# are legal and routine — Sofascore publishes ITF kickoffs in the tournament's
# local time as though it were UTC (F26) — so the wide window has to stay
# there. Cutting it globally would have closed F25 and opened a bigger hole.
MATCH_WINDOW_S: dict[str, float] = {
    "football": 6 * 3600,
    "tennis": 24 * 3600,
}
DEFAULT_MATCH_WINDOW_S = 24 * 3600

# A reversal this clear is not a near-miss. Measured over the whole 2026-09-18
# artifact: 483 of 484 fixtures agreed on orientation, zero were ambiguous, and
# the single reversal scored 54.5 direct against 200.0 crossed.
ORIENTATION_MARGIN = 20.0

# Which listing routes exist, per sport.
#
# team/{id}/events/next/ does not exist for tennis entities. Not "no upcoming
# matches" — the route itself: 179 requests, 179 404s, a clean 100% (F17).
# Nothing is lost by not asking, because events/last for tennis carries
# notstarted matches too (179 of them in the cache), so the fallback already
# covered it. For football next works and is kept: 48 of 53 came back 200.
ListingKind = Literal["last", "next"]
LISTING_KINDS_BY_SPORT: dict[str, tuple[ListingKind, ...]] = {
    "football": ("next", "last"),
    "tennis": ("last",),
}
DEFAULT_LISTING_KINDS: tuple[ListingKind, ...] = ("next", "last")

# Markers Superbet uses for a women's team, in the side name.
_WOMEN_SUPERBET_MARKERS = (
    "(k)",
    "(w)",
    "(f)",
    " kobiety",
    " women",
)
# Markers Sofascore uses for a women's competition, in the competition name.
# The competition is the reliable carrier: entity 296052 is called plainly
# "IF Gnistan" and plays exclusively in women's competitions, so the team name
# says nothing (F25).
_WOMEN_COMPETITION_MARKERS = (
    "women",
    "kobiet",
    "feminin",
    "femenin",
    "femminil",
    "frauen",
    "damen",
    "girls",
)


def superbet_gender(name: str) -> str:
    """ "W" if Superbet marks this side as a women's team, else "M"."""
    lowered = f" {(name or '').lower().strip()}"
    return "W" if any(m in lowered for m in _WOMEN_SUPERBET_MARKERS) else "M"


def sofascore_gender(event: dict[str, Any]) -> str:
    """ "W" if this event's competition is a women's competition, else "M"."""
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    category = tournament.get("category") or {}
    text = " ".join(
        str(part or "").lower()
        for part in (
            tournament.get("name"),
            tournament.get("slug"),
            unique.get("name"),
            unique.get("slug"),
            category.get("name"),
        )
    )
    return "W" if any(m in text for m in _WOMEN_COMPETITION_MARKERS) else "M"


def orientation_is_reversed(
    event: dict[str, Any], superbet_side_a: str, superbet_side_b: str
) -> bool:
    """True when Superbet's (side_a, side_b) maps to Sofascore's (away, home).

    This has value of its own, beyond identity: per-team markets — a side's
    corners, a side's cards, every `*_for` — are attributed by position, so a
    reversal prices the wrong team's sample even when the match is right.
    """
    home = normalize_name((event.get("homeTeam") or {}).get("name", ""))
    away = normalize_name((event.get("awayTeam") or {}).get("name", ""))
    if not home or not away or not superbet_side_a or not superbet_side_b:
        return False

    a = normalize_name(superbet_side_a)
    b = normalize_name(superbet_side_b)
    direct = fuzz.ratio(a, home) + fuzz.ratio(b, away)
    crossed = fuzz.ratio(a, away) + fuzz.ratio(b, home)
    return crossed - direct > ORIENTATION_MARGIN


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

    def _fetch_events(
        self, entity_id: int, sport: str = "football"
    ) -> list[dict[str, Any]]:
        events = []
        for kind in LISTING_KINDS_BY_SPORT.get(sport, DEFAULT_LISTING_KINDS):
            for page in range(3):
                data = self.cache.get_entity_events(entity_id, kind, page)
                if not data:
                    # A 404 is a fact worth remembering for the day. It was the
                    # one cost nobody counted, because a 404 does not look like
                    # a cost in the log: 242 of RESOLVE's ~870 requests, 28%,
                    # went on rediscovering the same absence — 225 of them
                    # already known from the previous run (F17).
                    if self.cache.get_listing_miss(entity_id, kind, page):
                        break
                    data = self.client.entity_events(entity_id, kind, page)
                    if data:
                        self.cache.save_entity_events(entity_id, kind, page, data)
                    else:
                        self.cache.save_listing_miss(entity_id, kind, page)
                if data and "events" in data:
                    events.extend(data["events"])
                    if not data.get("hasNextPage"):
                        break
                else:
                    break
        return events

    def match_quality(
        self,
        event: dict[str, Any],
        kickoff_utc: datetime,
        expected_opponent: str,
        *,
        sport: str = "tennis",
        superbet_side_a: str = "",
        superbet_side_b: str = "",
    ) -> float | None:
        """How well this event matches, or None if it does not.

        Kickoff and opponent were the two original conditions (E4 step 6), and
        both were satisfied by a match that was the wrong day, the wrong gender
        and the wrong way round: IF Gnistan · HJK Helsinki of the men's
        Veikkausliiga matched the women's Kansallinen Liiga fixture 23 h later,
        and was recorded CONFIRMED (F25). Two clubs that field both a men's and
        a women's side make the opponent's name useless on its own, and the
        window was wide enough to reach the next day.

        Two further conditions close it, either of which catches that case
        alone, and both cheap:

        - the gender implied by the competition must agree with the gender
          Superbet marks on the side name;
        - Superbet's (side_a, side_b) must not map to Sofascore's (away, home).
        """
        start_ts = event.get("startTimestamp")
        if not start_ts:
            return None

        window = MATCH_WINDOW_S.get(sport, DEFAULT_MATCH_WINDOW_S)
        event_time = datetime.fromtimestamp(start_ts, UTC)
        if abs((event_time - kickoff_utc).total_seconds()) > window:
            return None

        if superbet_side_a or superbet_side_b:
            # Gender: football only, and that is not caution, it is what the
            # two sources make possible. In football both sides of the gate
            # name a *team*, and Superbet marks a women's team "(K)" — 285
            # agreeing men, 4 agreeing women, one caught mismatch.
            #
            # In tennis Superbet's side is a *person*, and a person's name
            # carries no marker: "Yidi Yang" reads male to any rule built on
            # the name. Sofascore puts the marker on the tournament instead
            # ("ITF W15 Monastir 25 Women"). So the comparison is not merely
            # unreliable there, it mismatches on **every** women's match by
            # construction — measured: it removed women's tennis entirely,
            # recall 84.3% -> 58.4%, and all 133 surviving fixtures were male.
            #
            # F25's evidence was football and only football; applying it to
            # tennis was my over-generalisation, not the finding's.
            if sport == "football":
                expected = (
                    "W"
                    if "W"
                    in (
                        superbet_gender(superbet_side_a),
                        superbet_gender(superbet_side_b),
                    )
                    else "M"
                )
                if sofascore_gender(event) != expected:
                    return None
            # Orientation applies to both sports: it compares the two names to
            # the two names, so it needs no marker anywhere.
            if orientation_is_reversed(event, superbet_side_a, superbet_side_b):
                return None

        home = normalize_name(event.get("homeTeam", {}).get("name", ""))
        away = normalize_name(event.get("awayTeam", {}).get("name", ""))

        # Squad level, on the same footing as gender and orientation, and for
        # the same reason: it is the one distinction a token-set score cannot
        # make. A senior club's name is a strict subset of its academy side's
        # — "Flamengo" inside "Flamengo de Guarulhos U20", "US Chaouia" inside
        # "US Chaouia U20" — so the subset reading scores those 100.0. Of the
        # 25 false pairs `name_score` admits on the 2026-09-18 slate, this gate
        # removes 14, taking the rate back to what `fuzz.ratio` alone ran at.
        candidates = [
            side
            for side in (home, away)
            if levels_compatible(expected_opponent, side)
        ]
        if not candidates:
            return None

        best_side = max(
            candidates, key=lambda side: name_score(expected_opponent, side)
        )
        if name_score(expected_opponent, best_side) <= NAME_MATCH_THRESHOLD:
            return None

        # Report the STRICT similarity of the side that matched, not the score
        # that let it through. This number's only consumer is the CONFIRMED /
        # FUZZY field, which claims the two strings are the same; answering it
        # with a subset score would mark "Lens" ~ "RC Lens" as CONFIRMED.
        return float(fuzz.ratio(expected_opponent, best_side))

    def _is_match(
        self,
        event: dict[str, Any],
        kickoff_utc: datetime,
        expected_opponent: str,
        *,
        sport: str = "tennis",
        superbet_side_a: str = "",
        superbet_side_b: str = "",
    ) -> bool:
        return (
            self.match_quality(
                event,
                kickoff_utc,
                expected_opponent,
                sport=sport,
                superbet_side_a=superbet_side_a,
                superbet_side_b=superbet_side_b,
            )
            is not None
        )

    def resolve_entity(
        self,
        sport: str,
        side: str,
        kickoff_utc: datetime,
        expected_opponent: str,
        *,
        board_side_a: str = "",
        board_side_b: str = "",
    ) -> tuple[int | None, dict[str, Any] | None, bool]:
        """
        Returns (sofascore_id, matching_event, is_ambiguous).

        ``board_side_a``/``board_side_b`` are the board's sides in their
        original order, which ``side``/``expected_opponent`` lose because the
        caller retries with them swapped. The gender and orientation gates need
        the original order (F25).
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
            events = self._fetch_events(cached["sofascore_id"], sport)
            for e in events:
                if self._is_match(
                    e,
                    kickoff_utc,
                    norm_opp,
                    sport=sport,
                    superbet_side_a=board_side_a,
                    superbet_side_b=board_side_b,
                ):
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
            events = self._fetch_events(cand["id"], sport)
            for e in events:
                if self._is_match(
                    e,
                    kickoff_utc,
                    norm_opp,
                    sport=sport,
                    superbet_side_a=board_side_a,
                    superbet_side_b=board_side_b,
                ):
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
    superbet_kickoff_utc: datetime | None = None,
    cache: SofaCache | None = None,
) -> Fixture:
    # /event/{id} carries what the listing does not: referee, round_number,
    # ground_type, default_period_count.
    #
    # Through the cache when one is supplied (F33). This was the only route in
    # the pipeline with no cache at all — one call per fixture, every run, 46%
    # of a whole RESOLVE stage's requests. A finished match's payload is kept
    # permanently; an unplayed one expires, because the referee is announced
    # late and a frozen empty referee is worse than the requests it saves.
    details = cache.get_event_detail(event["id"]) if cache else None
    if details is None:
        details = client.event(event["id"])
        if cache and details:
            cache.save_event_detail(
                event["id"],
                details,
                ((details.get("event") or {}).get("status") or {}).get("type"),
            )
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
        ground_type=event.get("groundType"),
        default_period_count=event.get("defaultPeriodCount"),
        superbet_kickoff_utc=superbet_kickoff_utc,
        kickoff_disagreement_h=(
            None
            if superbet_kickoff_utc is None
            else round(
                abs((kickoff_utc - superbet_kickoff_utc).total_seconds()) / 3600.0, 2
            )
        ),
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
