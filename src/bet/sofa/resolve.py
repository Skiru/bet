import logging
import re
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
    # The shadow sports (src/bet/sofa/shadow.py). A hockey or volleyball side
    # plays the same opponent on consecutive days (back-to-back series), so a
    # 24 h window would match yesterday's game; kickoffs agree like football's.
    "ice-hockey": 6 * 3600,
    "basketball": 6 * 3600,
    "volleyball": 6 * 3600,
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
    # The shadow sports are only ever resolved by SHADOW_SETTLE, for a game
    # that is over, and a finished game is on the first page of events/last.
    # With next and three pages each a hockey side cost six listings a
    # lookup (measured 2026-09-29, ~1 req/s through the bridge). A postponed
    # game is then not found and ends GAVE_UP rather than VOID - either way
    # it is not graded.
    "ice-hockey": ("last",),
    "basketball": ("last",),
    "volleyball": ("last",),
}
DEFAULT_LISTING_KINDS: tuple[ListingKind, ...] = ("next", "last")
LISTING_PAGES_BY_SPORT: dict[str, int] = {
    "ice-hockey": 1,
    "basketball": 1,
    "volleyball": 1,
}
DEFAULT_LISTING_PAGES = 3

# Sports whose search is asked with &sport=<slug>. Sofascore's unscoped search
# returns 20 results ranked across every sport, and a volleyball or
# basketball side shares its name with a football club far more often than
# not: on 2026-09-29 only 7 of 22 volleyball games resolved, and "afturelding"
# / "hamar" / "estudiantes de la plata" returned no volleyball team at all
# unscoped while the scoped search put one first. Football and tennis keep the
# unscoped search they were measured with.
SPORT_SCOPED_SEARCH = frozenset({"ice-hockey", "basketball", "volleyball"})

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


# Sports whose sides are teams, which Superbet marks "(K)" when they are
# women's. The gender gate is right for every one of them and wrong only for
# tennis, where a side is a person (see match_quality).
TEAM_SPORTS = frozenset({"football", "ice-hockey", "basketball", "volleyball"})


def superbet_gender(name: str) -> str:
    """ "W" if Superbet marks this side as a women's team, else "M"."""
    lowered = f" {(name or '').lower().strip()}"
    return "W" if any(m in lowered for m in _WOMEN_SUPERBET_MARKERS) else "M"


def entity_gender(team: dict[str, Any]) -> str | None:
    """Sofascore's own gender field on a team: "W", "M", or None if absent."""
    raw = (team or {}).get("gender")
    if raw == "F":
        return "W"
    if raw == "M":
        return "M"
    return None


def sofascore_gender(event: dict[str, Any]) -> str:
    """ "W" if this is a women's match, else "M".

    The teams carry Sofascore's own `gender` field, and it is read first. The
    competition-name markers are only the fallback: they have no word for
    "NWSL", "WE-League", "Liga F" or "Damallsvenskan", and so called 4,919
    cached women's events (9.4% of them) men's - every one then failed the
    gender gate below (2026-09-28).
    """
    for side in ("homeTeam", "awayTeam"):
        gender = entity_gender(event.get(side) or {})
        if gender is not None:
            return gender
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


_SQUAD_MARKER_SUFFIX = re.compile(r"(?:\s*\((?:w|r)\))+\s*$")


# The shadow sports' opponent check (see `shadow_opponent_agrees`).
SHADOW_EXACT_KICKOFF_S = 15 * 60
# Words that name what a club is, not which one: two different clubs share them.
_GENERIC_NAME_TOKENS = frozenset(
    {
        "club", "clube", "klub", "basket", "basketball", "volley", "volleyball",
        "voley", "hockey", "team", "sport", "sports", "sporting", "city",
        "united", "women", "ladies", "feminin", "femenino", "feminino",
        "university", "universidad", "state", "academy", "reserves", "athletic",
        "atletico", "deportivo", "racing", "union", "olympic", "olimpia",
        "dynamo", "dinamo", "spartak", "lokomotiv", "real", "royal", "tenis",
        "hapoel", "maccabi", "beitar", "metallurg", "torpedo", "volei",
        "voleibol", "basquet", "pallavolo", "pallacanestro", "esporte",
    }
)  # fmt: skip


def _name_parts(norm: str) -> list[str]:
    """A name without its squad marker, whole and split at "/" - Sofascore
    names a volleyball or basketball side "sponsor/club" ("Itambé/Minas Tênis
    Clube", "Dentil/Praia Clube") where Superbet prints the club alone."""
    bare = _SQUAD_MARKER_SUFFIX.sub("", norm).strip()
    parts = [p.strip() for p in bare.split("/") if p.strip()]
    return [bare, *parts] if len(parts) > 1 else [bare]


def _distinctive_tokens(norm: str) -> set[str]:
    return {
        t
        for part in _name_parts(norm)
        for t in re.split(r"[\s/\-]+", part)
        if len(t) >= 4 and t not in _GENERIC_NAME_TOKENS and not t.isdigit()
    }


def shadow_opponent_agrees(
    expected_opponent: str,
    side: str,
    kickoff_gap_s: float,
    searched: str = "",
    searched_side: str = "",
) -> bool:
    """The opponent check for the shadow sports, which RESOLVE's 82-point
    name score is too strict for.

    Measured 2026-09-29 on the day's board: the game was on Sofascore and the
    gate refused it for "Minas TC" / "Itambé/Minas Tênis Clube" (50),
    "Wisconsin Green Bay (K)" / "Green Bay Phoenix" (69) and "Helios VS (K)" /
    "Helios VS Basket" (81.8 - the "(w)" marker alone cost the point). The
    event comes from the searched side's OWN listing, already gender-, level-
    and window-gated, so the opponent only has to confirm it: the full score
    on the marker-free name and on each "/" part, or - when both clocks agree
    within 15 minutes - one shared distinctive word. Football and tennis never
    reach this: a wrong football pair prices the wrong sample.

    `side` is the event's OTHER side, never the one that is the searched team
    (`searched_side`), and a word the searched team's names carry does not
    count: "Dynamo Moscow - Spartak Moscow" must not confirm "Dynamo Moscow -
    Lokomotiv Yaroslavl" through "moscow" (review 2026-09-29).
    """
    for a in _name_parts(expected_opponent):
        for b in _name_parts(side):
            if name_score(a, b) > NAME_MATCH_THRESHOLD:
                return True
    if kickoff_gap_s > SHADOW_EXACT_KICKOFF_S:
        return False
    own = _distinctive_tokens(searched) | _distinctive_tokens(searched_side)
    return bool(
        (_distinctive_tokens(expected_opponent) - own) & _distinctive_tokens(side)
    )


def part_score(a: str, b: str) -> float:
    """`name_score` of two normalised names, marker-free and per "/" part -
    the full score the shadow opponent check applies first."""
    return max(name_score(x, y) for x in _name_parts(a) for y in _name_parts(b))


# Words that say what kind of competition it is, not which one. Superbet's
# tournament is Polish with a country prefix ("Francja - Ligue Magnus"),
# Sofascore's English ("Ligue Magnus"); only a word naming the competition
# itself may tie the two.
_GENERIC_TOURNAMENT_TOKENS = frozenset(
    {
        "liga", "league", "ligue", "lega", "division", "divisao", "women",
        "woman", "men", "kobiety", "group", "grupa", "kwalifikacje",
        "qualification", "qualifying", "qualifiers", "regular", "season",
        "super", "superliga", "superleague", "premier", "first", "second",
        "national", "nationale", "nacional", "cup", "puchar", "playoffs",
        "playoff", "play", "off", "round", "stage", "championship",
        "mecze", "towarzyskie", "klubowe", "club", "friendlies", "friendly",
        "games", "pool", "knockout", "final", "finals", "placement",
        "matches", "pro", "top", "elite", "the", "and", "serie", "series",
        "hockey", "ice", "basketball", "basket", "volleyball", "volley",
        "u17", "u18", "u19", "u20", "u21", "u23", "youth", "junior",
        "juniors", "university", "college", "amateur", "regional", "region",
        "conference", "east", "west", "north", "south", "central", "a1", "a2",
    }
)  # fmt: skip


def tournament_tokens(text: str) -> set[str]:
    """The words of a competition's name that name it (3+ letters)."""
    norm = normalize_name(text or "", split_elisions=True)
    return {
        t
        for t in re.split(r"[^a-z0-9]+", norm)
        if len(t) >= 3 and not t.isdigit() and t not in _GENERIC_TOURNAMENT_TOKENS
    }


def event_tournament_tokens(event: dict[str, Any]) -> set[str]:
    """Sofascore's competition words, less its country's: "Germany Pro A"
    shares "germany" with Superbet's "Niemcy - Pro B" (the country alias),
    and a country is not a competition."""
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    category = tournament.get("category") or {}
    words = tournament_tokens(str(tournament.get("name") or "")) | tournament_tokens(
        str(unique.get("name") or "")
    )
    return words - tournament_tokens(str(category.get("name") or ""))


def _team_id(event: dict[str, Any], side: str) -> int | None:
    raw = (event.get(side) or {}).get("id")
    return int(raw) if isinstance(raw, int) else None


def mutual_listing_event(
    side_a_events: list[tuple[int, dict[str, Any]]],
    side_b_events: list[tuple[int, dict[str, Any]]],
) -> dict[str, Any] | None:
    """The one game both board sides' OWN listings hold at the board's time.

    Each list is (candidate team id, event) for the events of that side's
    search candidates (and verified entity) that start within
    SHADOW_EXACT_KICKOFF_S of the board's kickoff, gender-gated. An event is
    confirmed when one side's candidate is one of its teams and the other
    side's candidate - a different team - is the other: two independent
    searches landing on the two teams of one game at one time. That needs no
    name agreement at all, which is the point: "HC Mediolan" / "HC Milano
    Rossoblu" and "DAB Docler" / "Dunaujvarosi Acelbikak" share no word,
    and both were found by their own search (2026-09-30, 10-02). More than
    one such game is no answer.
    """
    found: dict[int, dict[str, Any]] = {}
    for cand_a, event in side_a_events:
        teams = {_team_id(event, "homeTeam"), _team_id(event, "awayTeam")}
        if None in teams or cand_a not in teams:
            continue
        for cand_b, other in side_b_events:
            same_game = other.get("id") == event.get("id")
            if same_game and cand_b != cand_a and cand_b in teams:
                found[int(event["id"])] = event
    return next(iter(found.values())) if len(found) == 1 else None


# How alike two single words must be to count as one name spelled two ways
# ("goverla" / "hoverla" 85.7, "budapeszt" / "budapest" 94.1), and how long
# both must be: on short words a ratio this high is chance.
OPPONENT_WORD_RATIO = 80.0
OPPONENT_WORD_MIN_LEN = 5


def opponent_resembles(board_opponent: str, sofascore_side: str) -> bool:
    """A weak, positive sign that two names denote one club - never enough
    alone, only beside `tournament_confirmed_event`'s other conditions.

    - one word spelled two ways: a pair of words of 5+ letters, neither a
      generic club word, with `fuzz.ratio` >= 80 (a transliteration or an
      exonym: Goverla / Hoverla, Budapeszt / Budapest);
    - an acronym: a 3-5 letter board word equal to the initials of the other
      name's words ("ASA" / "Alliance Sport Alsace"), or to the first two
      letters of consecutive words ("ToPo" / "Torpan Pojat").

    Without it the competition reading matched the same team's game two days
    later in the same league at the same hour - 15 of 17 hits in a negative
    control with every kickoff moved 48 h (Allsvenskan plays at 17:00).
    """
    a = normalize_name(board_opponent, split_elisions=True)
    b = normalize_name(sofascore_side, split_elisions=True)
    a_words = [w for p in _name_parts(a) for w in re.split(r"[\s/\-]+", p) if w]
    b_words = [w for p in _name_parts(b) for w in re.split(r"[\s/\-]+", p) if w]
    for x in a_words:
        if len(x) < OPPONENT_WORD_MIN_LEN or x in _GENERIC_NAME_TOKENS:
            continue
        for y in b_words:
            if len(y) < OPPONENT_WORD_MIN_LEN or y in _GENERIC_NAME_TOKENS:
                continue
            if fuzz.ratio(x, y) >= OPPONENT_WORD_RATIO:
                return True
    if not b_words:
        return False
    acronyms = {"".join(w[0] for w in b_words)}
    for n in (2, 3):
        for i in range(len(b_words) - n + 1):
            chunk = b_words[i : i + n]
            if all(len(w) >= 2 for w in chunk):
                acronyms.add("".join(w[:2] for w in chunk))
    return any(
        3 <= len(x) <= 5 and x.isalpha() and x in acronyms for x in a_words
    )


def tournament_confirmed_event(
    side: str,
    other_board_side: str,
    superbet_tournament: str,
    side_events: list[tuple[int, dict[str, Any]]],
    other_side_events: list[tuple[int, dict[str, Any]]],
) -> dict[str, Any] | None:
    """One side found by name, the opponent by the competition.

    For an opponent Superbet and Sofascore name apart - an exonym ("MAC
    Budapeszt" / "Budapest Jegkorong Akademia HC"), a short form ("ToPo" /
    "Torpan Pojat"), a transliteration ("Goverla" / "Hoverla") - the game is
    accepted when every one of these holds:

    - the searched side's candidate has exactly one game within
      SHADOW_EXACT_KICKOFF_S of the board's time (lists as for
      `mutual_listing_event`, so gender is already gated);
    - the searched side's own name passes the full score against its team in
      that game (`part_score` > NAME_MATCH_THRESHOLD);
    - the other team's squad level agrees with the other board side's;
    - a word naming the competition is in both Superbet's tournament and
      Sofascore's ("Ligue Magnus", "Erste Liga", "Korisliiga");
    - the other team's name resembles the other board side's
      (`opponent_resembles`: one word spelled two ways, or an acronym);
    - the other board side's own listings hold no different game at that
      time.

    Sofascore's "San Jose St. Spartans" is not Superbet's Costa Rican "San
    Jose", though the name passes: the competitions share no word.
    """
    norm_side = normalize_name(side)
    norm_other = normalize_name(other_board_side)
    wanted = tournament_tokens(superbet_tournament)
    if not wanted:
        return None
    per_candidate: dict[int, list[dict[str, Any]]] = {}
    for cand, event in side_events:
        per_candidate.setdefault(cand, []).append(event)
    found: dict[int, dict[str, Any]] = {}
    for cand, events in per_candidate.items():
        if len({e.get("id") for e in events}) != 1:
            continue
        event = events[0]
        if _team_id(event, "homeTeam") == cand:
            own_key, other_key = "homeTeam", "awayTeam"
        elif _team_id(event, "awayTeam") == cand:
            own_key, other_key = "awayTeam", "homeTeam"
        else:
            continue
        own_name = normalize_name(str((event.get(own_key) or {}).get("name") or ""))
        other_name = normalize_name(
            str((event.get(other_key) or {}).get("name") or "")
        )
        if part_score(norm_side, own_name) <= NAME_MATCH_THRESHOLD:
            continue
        if not levels_compatible(norm_other, other_name):
            continue
        if not wanted & event_tournament_tokens(event):
            continue
        if not opponent_resembles(
            other_board_side, str((event.get(other_key) or {}).get("name") or "")
        ):
            continue
        found[int(event["id"])] = event
    if len(found) != 1:
        return None
    event = next(iter(found.values()))
    if any(other.get("id") != event.get("id") for _, other in other_side_events):
        return None
    return event


def search_query(norm_side: str) -> str:
    """The name to send to Sofascore's search: our squad markers removed.

    "(w)" and "(r)" are this module's own notation, kept in the cache key so a
    women's or reserve side never shares an entity with the senior men's one.
    Sofascore's search does not know them and returns nothing: measured live
    2026-09-28, "chicago red stars (w)", "pogon szczecin (w)", "rio ave (w)",
    "club america (w)", "uks sms lodz (w)" and "ca penarol (r)" all came back
    empty, and every one found its team without the marker. That was most of
    the 481 women's names and 336 reserve names in sofa_entity_miss.
    """
    return _SQUAD_MARKER_SUFFIX.sub("", norm_side).strip()


_VIRTUAL_NAME = re.compile(r"\((?:cyber|e-?sports?|virtual)\)", re.IGNORECASE)


def is_virtual_event(event: dict[str, Any]) -> bool:
    """A simulated game - Sofascore lists them beside the real sport.

    Measured 2026-09-29: the basketball search for "u bt cluj" returned
    "Cluj (Cyber)", "U-BT Cluj-Napoca (eSport)" and "U-BT Cluj-Napoca (Nerijus
    Jakubauskas)" after the real club, and their games (tournament category
    "virtual-basketball") run every hour - two of them in a real game's window
    made Maxima Roma - U BT Cluj AMBIGUOUS, and one alone could have been
    graded in the real game's place. Superbet's own e-sports twins (157, 70)
    are never read; this keeps Sofascore's out of the result side.
    """
    category = ((event.get("tournament") or {}).get("category")) or {}
    label = f"{category.get('slug') or ''} {category.get('name') or ''}".lower()
    if any(w in label for w in ("virtual", "esport", "cyber", "ebasketball")):
        return True
    names = [
        str((event.get(side) or {}).get("name") or "")
        for side in ("homeTeam", "awayTeam")
    ]
    return any(_VIRTUAL_NAME.search(n) for n in names)


def candidate_fits(norm_side: str, entity: dict[str, Any], sport: str) -> bool:
    """Can this search result be the side we are looking for at all?

    Only three candidates get their listings fetched, and without the marker
    the search ranks the senior men's club first: "rio ave" returns Rio Ave,
    Rio Ave U23 and Rio Ave FC U19 before the women's Rio Ave FC. So a
    candidate of the wrong gender or the wrong squad level is skipped before
    it takes one of the three places. Gender is team sports only, for the reason
    `match_quality` gives: a tennis side is a person and carries no marker.
    """
    if sport in TEAM_SPORTS:
        gender = entity_gender(entity)
        if gender is not None and gender != superbet_gender(norm_side):
            return False
    if sport in SPORT_SCOPED_SEARCH and _VIRTUAL_NAME.search(entity.get("name") or ""):
        # A simulated side takes none of the three places (is_virtual_event).
        return False
    return levels_compatible(
        search_query(norm_side), normalize_name(entity.get("name", ""))
    ) or levels_compatible(norm_side, normalize_name(entity.get("name", "")))


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
            for page in range(LISTING_PAGES_BY_SPORT.get(sport, DEFAULT_LISTING_PAGES)):
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
        check_orientation: bool = True,
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

        if sport in SPORT_SCOPED_SEARCH and is_virtual_event(event):
            return None

        window = MATCH_WINDOW_S.get(sport, DEFAULT_MATCH_WINDOW_S)
        event_time = datetime.fromtimestamp(start_ts, UTC)
        if abs((event_time - kickoff_utc).total_seconds()) > window:
            return None

        if superbet_side_a or superbet_side_b:
            # Gender: TEAM_SPORTS only, and that is not caution, it is what the
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
            if sport in TEAM_SPORTS:
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
            # A caller that reads the orientation itself (SHADOW_SETTLE grades a
            # reversed listing from team1's side) turns the refusal off.
            if check_orientation and orientation_is_reversed(
                event, superbet_side_a, superbet_side_b
            ):
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
            side for side in (home, away) if levels_compatible(expected_opponent, side)
        ]
        if not candidates:
            return None

        best_side = max(
            candidates, key=lambda side: name_score(expected_opponent, side)
        )
        if name_score(expected_opponent, best_side) <= NAME_MATCH_THRESHOLD:
            if sport not in SPORT_SCOPED_SEARCH:
                return None
            gap = abs((event_time - kickoff_utc).total_seconds())
            # The searched team is the board side that is not the opponent;
            # its side of the event is the one nearest its name, and only the
            # OTHER side may confirm the opponent.
            raw_board = (superbet_side_a, superbet_side_b)
            board = [normalize_name(x) for x in raw_board]
            searched = [b for b in board if b and b != expected_opponent]
            if len(searched) != 1:
                return None
            own_side = max((home, away), key=lambda side: name_score(searched[0], side))
            other = away if own_side == home else home
            # The relaxed check reads the raw names with an elision split
            # ("Gothiques d'Amiens" -> "gothiques d amiens"), so a word the
            # ASCII fold glued to its article still counts (2026-09-29/10-02:
            # Amiens Hockey Elite, C'Chartres Basket Feminin).
            raw_of = {
                home: str((event.get("homeTeam") or {}).get("name") or ""),
                away: str((event.get("awayTeam") or {}).get("name") or ""),
            }
            raw_searched = raw_board[board.index(searched[0])]
            raw_opponent = next(
                (r for r, b in zip(raw_board, board, strict=True)
                 if b == expected_opponent),
                expected_opponent,
            )

            def split(raw: str) -> str:
                return normalize_name(raw, split_elisions=True)

            if other not in candidates or not (
                shadow_opponent_agrees(
                    expected_opponent, other, gap, searched[0], own_side
                )
                or shadow_opponent_agrees(
                    split(raw_opponent),
                    split(raw_of[other]),
                    gap,
                    split(raw_searched),
                    split(raw_of[own_side]),
                )
            ):
                return None
            best_side = other

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
        check_orientation: bool = True,
    ) -> bool:
        return (
            self.match_quality(
                event,
                kickoff_utc,
                expected_opponent,
                sport=sport,
                superbet_side_a=superbet_side_a,
                superbet_side_b=superbet_side_b,
                check_orientation=check_orientation,
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
        record_miss: bool = True,
        check_orientation: bool = True,
    ) -> tuple[int | None, dict[str, Any] | None, bool]:
        """
        Returns (sofascore_id, matching_event, is_ambiguous).

        ``board_side_a``/``board_side_b`` are the board's sides in their
        original order, which ``side``/``expected_opponent`` lose because the
        caller retries with them swapped. The gender and orientation gates need
        the original order (F25).

        ``record_miss=False`` is for a caller that looks up one past game, not
        the team: SHADOW_SETTLE. A game missing from a listing there (not yet
        marked finished, rescheduled) says nothing about the team, and a
        recorded miss would block every game of it for a week.

        ``check_orientation=False`` keeps a listing that reads the other way
        round, for a caller that tells the orientation itself and grades
        from it (SHADOW_SETTLE). RESOLVE never passes it: a reversed football
        fixture would price the wrong team's sample.
        """
        norm_side = normalize_name(side)
        norm_opp = normalize_name(expected_opponent)

        cached = self.cache.get_entity(sport, norm_side)
        verified = bool(cached and cached["status"] == "verified")
        # A name we recently failed to resolve costs a search plus up to three
        # listings. Paying that again every run, forever, was ~20% of the
        # request budget spent re-learning the same negative fact.
        #
        # Never for a VERIFIED name, though: its miss was "no event for that
        # one fixture yet", not "this team cannot be found", and checked first
        # it stopped RESOLVE asking the known id for seven days - on
        # 2026-10-01 ~26 tennis matches that had not started (Tien-Hurkacz),
        # and Croatia U19 / Jerash in football.
        if not verified and self.cache.get_entity_miss(sport, norm_side):
            return None, None, False

        if cached and verified:
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
                    check_orientation=check_orientation,
                ):
                    return cached["sofascore_id"], e, False

        # Miss -> search/all
        if sport in SPORT_SCOPED_SEARCH:
            search_data = self.client.search(search_query(norm_side), sport=sport)
        else:
            search_data = self.client.search(search_query(norm_side))
        if not search_data or "results" not in search_data:
            if record_miss and not verified:
                self.cache.save_entity_miss(sport, norm_side)
            return None, None, False

        candidates = []
        for r in search_data["results"]:
            if (
                r.get("type") == "team"
                and r.get("entity", {}).get("sport", {}).get("slug") == sport
                and candidate_fits(norm_side, r["entity"], sport)
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
                    check_orientation=check_orientation,
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
        # as a miss would suppress a resolution that is still possible. A
        # verified name is never recorded: one fixture's absence from its
        # listing is a fact about the fixture, not about the name.
        if record_miss and not verified:
            self.cache.save_entity_miss(sport, norm_side)
        return None, None, False


def kickoff_gap_h(
    kickoff_utc: datetime, superbet_kickoff_utc: datetime | None
) -> float | None:
    """Hours between Sofascore's and Superbet's clocks, or None without the
    latter. Recomputed whenever either clock changes: on 2026-10-03 a second
    Superbet listing replaced a 00:00Z placeholder and the gap stayed at the
    placeholder's (Humbert - Lehecka: both clocks 08:10Z, gap 8.17 h)."""
    if superbet_kickoff_utc is None:
        return None
    return round(abs((kickoff_utc - superbet_kickoff_utc).total_seconds()) / 3600.0, 2)


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
        kickoff_disagreement_h=kickoff_gap_h(kickoff_utc, superbet_kickoff_utc),
        sofascore_status=(event.get("status") or {}).get("type"),
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
