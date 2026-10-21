"""RESOLVE's short-name search for a football pair no other rule found
(epochs.FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC).

Sofascore's search returns nothing fitting for some of Superbet's full names
while one word of the name finds the team: "Calcio Avola 1949" -> "avola"
(Avola), "Menemenspor" -> "menemen" (Menemen FK), "Muang Loei Utd" -> "loei"
(Muang Loei United). Measured 2026-10-21 on the football gaps of
10-13..10-20 with neither side known (22 such pairs,
docs/sofa/history/RAPORT_RESOLVE_KROTKA_NAZWA_2026-10-21.md).

A single word is weak evidence about one side, so a game is accepted only
when BOTH sides land on it: side A's candidates (its own verified entity, or
its normal search's fitting results, or a short query's) hold the game's home
team and side B's its away team - Superbet's order (F25) - within
FOOTBALL_ANCHOR_WINDOW_S of Superbet's start, the board's gender, both squad
levels and unmarked squad words, not postponed; at least one side came
through a short query; exactly one such game. Never from one side alone,
never cached as a verified name; the fixture's identity is FUZZY and its
`match_rule` "SHORT_NAME:<how>".
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from rapidfuzz import fuzz

from bet.sofa.names import levels_compatible, normalize_name
from bet.sofa.resolve import (
    FOOTBALL_ANCHOR_WINDOW_S,
    NAME_MATCH_THRESHOLD,
    _team_id,
    candidate_fits,
    is_virtual_event,
    name_stopwords,
    part_score,
    search_query,
    sofascore_gender,
    superbet_gender,
)

logger = logging.getLogger(__name__)

SPORT = "football"
# A short query is one word of the name, at least this long ("lask", "loei").
SHORT_NAME_MIN_TOKEN = 4
# The longest words of a name are asked, at most this many per side.
SHORT_NAME_MAX_TOKENS = 2
# Fitting results of one short query whose listings are read.
SHORT_NAME_RESULTS = 5
# Words that say what a club is, not which: besides resolve's stopwords.
SHORT_NAME_EXTRA_STOPWORDS = frozenset({
    "calcio", "belediye", "belediyespor", "polisportiva", "sportunion",
    "reserve", "football", "futbol", "futebol", "fudbal", "fussball",
    "sportiva", "associazione", "sportive", "sportif", "spor", "kulubu",
    "women", "youth", "juniors", "junior",
})  # fmt: skip
# A Turkish club name ends in "spor" where Sofascore may write the town alone
# ("Menemenspor" / "Menemen FK"): the town is asked too.
_SPOR = "spor"
_SPLIT = re.compile(r"[\s/\-\.&,'()]+")
# Trailing squad words `normalize_name` leaves unmarked; anywhere in the name
# here ("Polissya-2 Zhytomyr" for "FC Polissya Zhytomyr 2").
_SQUAD_WORDS = frozenset({"2", "3", "4", "c", "d", "iii"})

Listing = tuple[dict[str, Any], list[dict[str, Any]]]


def _words(norm: str) -> list[str]:
    return [w for w in _SPLIT.split(norm) if w]


_DASHED_SQUAD = re.compile(r"^[a-z]+-([234])$")


def squad_words(norm: str) -> frozenset[str]:
    """Unmarked squad words: a whole word ("inter turku 2") or a dashed
    digit ("polissya-2 zhytomyr"); never an initial ("a.s.d. sambiase")."""
    out = set()
    for w in norm.split():
        m = _DASHED_SQUAD.match(w)
        if w in _SQUAD_WORDS:
            out.add(w)
        elif m:
            out.add(m.group(1))
    return frozenset(out)


# Words that say what a club is and never tell two clubs apart, for the
# contradiction check; every other word of 4+ letters counts there - "real" /
# "atletico", "hapoel" / "maccabi", "town" / "united" do tell clubs apart.
CONTRADICTION_IGNORED = frozenset({
    "club", "clube", "klub", "calcio", "polisportiva", "sportunion", "union",
    "football", "futbol", "futebol", "fudbal", "fussball", "sportiva",
    "associazione", "sportive", "sportif", "spor", "kulubu", "belediye",
    "belediyespor", "women", "ladies", "feminin", "femenino", "feminino",
    "femminile", "reserve", "reserves", "youth", "academy", "sport", "sports",
    "team", "kvinner", "damen", "frauen", "femenil", "feminine",
})  # fmt: skip
# Two words are one when this close (`fuzz.ratio`): "gorodenka" / "horodenka",
# "petah" / "petach", "wieden" / "wien".
WORD_MATCH_RATIO = 80.0


def _significant(norm: str) -> set[str]:
    return {w for w in _words(search_query(norm))
            if len(w) >= SHORT_NAME_MIN_TOKEN and w not in CONTRADICTION_IGNORED
            and not any(ch.isdigit() for ch in w)}


def _word_in(w: str, words: set[str]) -> bool:
    return any(w == c or fuzz.ratio(w, c) >= WORD_MATCH_RATIO
               or (len(c) >= SHORT_NAME_MIN_TOKEN
                   and (w.startswith(c) or c.startswith(w)))
               for c in words)


def name_contradicts(norm_side: str, norm_team: str) -> bool:
    """Does the Sofascore team's name contradict the board side's: EACH
    carries a word of 4+ letters (`CONTRADICTION_IGNORED` aside) the other
    lacks - "Cheltenham Town" / "Swindon Town", "Nomme Kalju" / "Nomme
    United", "Real Madryt B" / "Atletico Madrid B". A word only one of them
    adds ("Calcio Avola 1949" / "Avola", "SV Wallern" / "SPG Wallern / ASV St
    Marienkirchen") is not a contradiction."""
    a, b = _significant(norm_side), _significant(norm_team)
    return (any(not _word_in(w, b) for w in a)
            and any(not _word_in(w, a) for w in b))


def short_name_queries(norm_side: str) -> list[str]:
    """The short searches for one board side: its longest distinctive words
    (SHORT_NAME_MAX_TOKENS, >= SHORT_NAME_MIN_TOKEN letters, no stopword, no
    digit), a "...spor" word also without "spor"; never the normal query."""
    full = search_query(norm_side)
    stop = name_stopwords() | SHORT_NAME_EXTRA_STOPWORDS
    words = [w for w in dict.fromkeys(_words(full))
             if len(w) >= SHORT_NAME_MIN_TOKEN and w not in stop
             and not any(ch.isdigit() for ch in w)]
    out: list[str] = []
    for w in sorted(words, key=len, reverse=True)[:SHORT_NAME_MAX_TOKENS]:
        out.append(w)
        if w.endswith(_SPOR) and len(w) > len(_SPOR) + 4:
            out.append(w[: -len(_SPOR)])
    return [q for q in dict.fromkeys(out) if q != full]


def short_candidate_fits(
    norm_side: str, norm_other: str, query: str, entity: dict[str, Any]
) -> bool:
    """Can a short query's result be this side: a football team of the
    side's gender and squad level (`candidate_fits`), its name holding the
    query as a whole word, the same unmarked squad words - and the query is
    not a word of the OTHER board side ("Linz" names neither of two Linz
    clubs)."""
    if (entity.get("sport") or {}).get("slug") != SPORT:
        return False
    if not candidate_fits(norm_side, entity, SPORT):
        return False
    name = normalize_name(str(entity.get("name") or ""))
    if query not in _words(name):
        return False
    if squad_words(name) != squad_words(norm_side):
        return False
    return query not in _words(search_query(norm_other))


def short_name_pair_event(
    cands_a: list[Listing],
    cands_b: list[Listing],
    kickoff_utc: datetime,
    board_side_a: str,
    board_side_b: str,
) -> dict[str, Any] | None:
    """The ONE football game within FOOTBALL_ANCHOR_WINDOW_S of Superbet's
    start whose home team is one of side A's candidates and away team one of
    side B's (F25: Superbet's order), with the board's gender, both sides'
    squad levels and unmarked squad words, not postponed / cancelled, not a
    simulation, neither side's name contradicted (`name_contradicts`). Read
    from both sides' listings; two games refuse."""
    from bet.sofa.fixture_status import NOT_AS_SCHEDULED

    norm_a, norm_b = normalize_name(board_side_a), normalize_name(board_side_b)
    ids_a = {c.get("id") for c, _ in cands_a if isinstance(c.get("id"), int)}
    ids_b = {c.get("id") for c, _ in cands_b if isinstance(c.get("id"), int)}
    expected = ("W" if "W" in (superbet_gender(norm_a), superbet_gender(norm_b))
                else "M")
    found: dict[int, dict[str, Any]] = {}
    for _, events in (*cands_a, *cands_b):
        for e in events:
            ts, eid = e.get("startTimestamp"), e.get("id")
            if not isinstance(ts, int) or not isinstance(eid, int):
                continue
            if abs(ts - kickoff_utc.timestamp()) > FOOTBALL_ANCHOR_WINDOW_S:
                continue
            if _team_id(e, "homeTeam") not in ids_a or _team_id(e, "awayTeam") \
                    not in ids_b:
                continue
            if str((e.get("status") or {}).get("type") or "") in NOT_AS_SCHEDULED:
                continue
            if sofascore_gender(e) != expected or is_virtual_event(e):
                continue
            home = normalize_name((e.get("homeTeam") or {}).get("name") or "")
            away = normalize_name((e.get("awayTeam") or {}).get("name") or "")
            if not (levels_compatible(norm_a, home)
                    and levels_compatible(norm_b, away)):
                continue
            if squad_words(home) != squad_words(norm_a) or squad_words(away) \
                    != squad_words(norm_b):
                continue
            if name_contradicts(norm_a, home) or name_contradicts(norm_b, away):
                continue
            found[eid] = e
    if len(found) != 1:
        return None
    event = next(iter(found.values()))
    if (named_elsewhere(cands_a, norm_a, event, kickoff_utc)
            or named_elsewhere(cands_b, norm_b, event, kickoff_utc)):
        return None
    return event


def named_elsewhere(
    cands: list[Listing], norm_side: str, event: dict[str, Any],
    kickoff_utc: datetime,
) -> bool:
    """The veto: one of the side's candidates carries the side's own name
    (`part_score` > NAME_MATCH_THRESHOLD, the same squad level and squad
    words), is not in the game, and plays ANOTHER game within the window -
    Sofascore knows the board's team and it is somewhere else ("Dundee FC"
    playing its own game while "Dundee United" plays the anchored one)."""
    from bet.sofa.fixture_status import NOT_AS_SCHEDULED

    in_game = {_team_id(event, "homeTeam"), _team_id(event, "awayTeam")}
    for cand, events in cands:
        cid = cand.get("id")
        if cid in in_game:
            continue
        name = normalize_name(str(cand.get("name") or ""))
        if (part_score(norm_side, name) <= NAME_MATCH_THRESHOLD
                or not levels_compatible(norm_side, name)
                or squad_words(name) != squad_words(norm_side)):
            continue
        for e in events:
            ts = e.get("startTimestamp")
            if (isinstance(ts, int) and e.get("id") != event.get("id")
                    and abs(ts - kickoff_utc.timestamp()) <= FOOTBALL_ANCHOR_WINDOW_S
                    and cid in (_team_id(e, "homeTeam"), _team_id(e, "awayTeam"))
                    and str((e.get("status") or {}).get("type") or "")
                    not in NOT_AS_SCHEDULED):
                return True
    return False


def _how(event: dict[str, Any], short_ids: tuple[set[int], set[int]]) -> str:
    """"BOTH" when both sides came through short queries, else the side that
    did ("A" / "B" = Superbet's side_a / side_b)."""
    a = _team_id(event, "homeTeam") in short_ids[0]
    b = _team_id(event, "awayTeam") in short_ids[1]
    return "BOTH" if a and b else ("A" if a else "B")


def short_miss_key(norm_a: str, norm_b: str) -> str:
    return f"(short) {norm_a} v {norm_b}"


def resolve_short_name_pair(
    resolver: Any,
    side_a: str,
    side_b: str,
    kickoff_utc: datetime,
    *,
    search: Callable[[str], Any] | None = None,
) -> dict[str, Any] | None:
    """The pair step: both board sides' candidates (verified entity alone, or
    the normal search's fitting results RESOLVE kept on the resolver plus the
    short queries' results) and `short_name_pair_event`. The event comes back
    tagged `_match_rule` "SHORT_NAME:<how>"; nothing is cached as verified;
    a pair that found nothing is remembered as a miss for its day (re-asked
    by the late pass after its freshness, like an entity miss)."""
    from bet.sofa import epochs
    from bet.sofa.timeutil import now

    cache = resolver.cache
    ask = search if search is not None else resolver.client.search
    norm_a, norm_b = normalize_name(side_a), normalize_name(side_b)
    key = short_miss_key(norm_a, norm_b)
    day_start = kickoff_utc.astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0)
    # A miss this run records blocks the rest of it, even before the kickoff day.
    started = getattr(resolver, "run_started_at", None) or now()
    bounds = [min(day_start, started)]
    if epochs.FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC is not None:
        bounds.append(epochs.FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC)
    fresh = getattr(resolver, "miss_fresh_min", None)
    if fresh is not None:
        bounds.append(now() - timedelta(minutes=fresh))
    if cache.get_entity_miss(SPORT, key, recorded_after=max(bounds)):
        return None

    short_ids: tuple[set[int], set[int]] = (set(), set())
    sides: list[list[Listing]] = []
    queries = 0
    for i, (side, norm, norm_other) in enumerate(
            ((side_a, norm_a, norm_b), (side_b, norm_b, norm_a))):
        cached = cache.get_entity(SPORT, norm)
        if cached and cached["status"] == "verified":
            sid = int(cached["sofascore_id"])
            sides.append([({"id": sid, "name": cached.get("sofascore_name") or ""},
                           resolver._fetch_events(sid, SPORT))])
            continue
        listings: list[Listing] = list(
            resolver.searched_listings.get(
                (SPORT, norm, int(kickoff_utc.timestamp())), []))
        seen = {c.get("id") for c, _ in listings}
        for q in short_name_queries(norm):
            queries += 1
            got = 0
            for r in (ask(q) or {}).get("results") or []:
                ent = r.get("entity") or {}
                if r.get("type") != "team" or not short_candidate_fits(
                        norm, norm_other, q, ent):
                    continue
                got += 1
                if isinstance(ent.get("id"), int):
                    short_ids[i].add(ent["id"])
                if isinstance(ent.get("id"), int) and ent["id"] not in seen:
                    seen.add(ent["id"])
                    listings.append((ent, resolver._fetch_events(ent["id"], SPORT)))
                if got == SHORT_NAME_RESULTS:
                    break
        sides.append(listings)
    event = short_name_pair_event(sides[0], sides[1], kickoff_utc, side_a, side_b)
    if event is not None and (_team_id(event, "homeTeam") in short_ids[0]
                              or _team_id(event, "awayTeam") in short_ids[1]):
        how = _how(event, short_ids)
        logger.info("RESOLVE short name: %s v %s -> %s (%s, %d searches)",
                    side_a, side_b, event.get("id"), how, queries)
        return {**event, "_match_rule": f"SHORT_NAME:{how}"}
    if queries:
        cache.save_entity_miss(SPORT, key)
    return None
