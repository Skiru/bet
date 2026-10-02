"""A club's second squad listed under its first team's id (2026-10-02).

Sofascore files the matches a club plays with its reserves / U23 under the
senior team's entity id when the competition has no separate "B" entity. Those
matches then entered the senior side's sample and rating: Londrina (Serie B)
carried five Copa Parana matches into its sample for Londrina - Criciuma on
2026-10-02, one of them 25 h after a Serie B match (sofa-verifier). The <24 h
guard in samples.one_squad_per_entity does not see that.

Measured on the cache (954,191 finished football matches, read-only,
2026-10-02):

  * The lineup signal is unusable where it matters. /lineups is cached for
    1,097 of 251,168 stats rows (459 of the 8,721 events in the 10-01/10-02
    samples), only for player-market events of covered leagues; the state cups
    in question publish none (Copa Parana: 14 stats rows, 0 lineups; Sofascore
    marks it hasEventPlayerStatistics false).
  * A schedule clash is proof of two squads. A side whose match in competition
    X lies 6-44 h from its match in its main competition cannot be one squad.
    Genuine national and continental cups (Copa do Brasil, Copa Argentina, FA
    Cup, DFB Pokal, Copa del Rey, Coppa Italia, Coupe de France, Libertadores,
    Sudamericana, UCL, UEL, US Open Cup, Leagues Cup, Canadian Championship):
    0 clashes in ~7,800 matches of sides from another main competition.
  * A clash is a property of the (side, competition) pair, not of one match:
    split by event-id parity, a match clashes in 27.6% of pairs whose other
    half clashes and in 0.34% of the rest (82x). So the whole pair is a second
    squad once it clashes twice (MIN_CLASHES). One clash is not enough: at 1 a
    single clash fired on genuine national cups (Slovnaft Cup 303, Israel State
    Cup 370); at 2 no national cup of a covered league fired.
  * Not every reserve match clashes (Londrina: 4 of 5). Where the clash
    evidence is per competition and per tier, a curated list decides
    (config/sofa_reserve_competitions.json): in a listed competition a side
    whose main competition is in ``reserve_when_main_in`` is a second squad.
    Six Brazilian state cups pooled: Serie A sides clashed in 7 of 8 teams
    (23 of 66 matches), Serie B 5 of 6 (18 of 40); Serie C 1 of 8, Serie D
    2 of 23, every state division 0 of ~95 teams - those keep their matches
    (their first team plays the cup out of season).

A match a side played with its second squad describes another team. SAMPLES
drops it from that side's sample, or, when the fixture itself is the second
squad's, leaves the side empty (its listing then describes the wrong team for
every other match). The rating does not move either side on it - see
football_rating.RatingBook.update.
"""

from __future__ import annotations

import bisect
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import NamedTuple

from bet.sofa.config import config_path

# A side's main competition: its modal competition within this window of the
# match (friendlies are out before this module sees a match).
MAIN_WINDOW_S = 182 * 86400
# Two matches of one side this close in two competitions are two squads. The
# lower bound keeps a match listed twice (same kick-off, two tournaments) out
# - that is one_listing_per_match's case, not a second squad.
CLASH_MIN_S = 6 * 3600
CLASH_MAX_S = 44 * 3600
# Clashes of one side in one competition (inside MAIN_WINDOW_S of a match)
# that make all its matches there a second squad's.
MIN_CLASHES = 2

_CONFIG_NAME = "sofa_reserve_competitions.json"


class TeamMatch(NamedTuple):
    event_id: int
    ts: int
    competition_id: int


def load_reserve_competitions(
    name: str = _CONFIG_NAME,
) -> dict[int, frozenset[int]]:
    """competition id -> the main competitions whose sides field reserves there.

    A missing or malformed file is an empty list: the clash rule still runs.
    """
    try:
        raw = json.loads(config_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = raw.get("competitions", []) if isinstance(raw, dict) else []
    out: dict[int, frozenset[int]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("competition_id")
        mains = entry.get("reserve_when_main_in")
        if isinstance(cid, int) and isinstance(mains, list):
            out[cid] = frozenset(m for m in mains if isinstance(m, int))
    return out


RESERVE_COMPETITIONS: Mapping[int, frozenset[int]] = load_reserve_competitions()


def reserve_fingerprint(
    listed: Mapping[int, frozenset[int]] = RESERVE_COMPETITIONS,
) -> str:
    """The rule and the list, for a cache key (football_rating history)."""
    entries = ";".join(
        f"{c}:{','.join(str(m) for m in sorted(listed[c]))}" for c in sorted(listed)
    )
    return (
        f"{MAIN_WINDOW_S}/{CLASH_MIN_S}/{CLASH_MAX_S}/{MIN_CLASHES}|{entries}"
    )


def _modal(counts: Counter[int]) -> int | None:
    if not counts:
        return None
    # Deterministic on a tie: the lower competition id.
    return max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]


def _mains(ms: Sequence[TeamMatch], probe_ts: Sequence[int]) -> list[int | None]:
    """The modal competition of ``ms`` within MAIN_WINDOW_S of each time."""
    tss = [m.ts for m in ms]
    out: list[int | None] = []
    for ts in probe_ts:
        lo = bisect.bisect_left(tss, ts - MAIN_WINDOW_S)
        hi = bisect.bisect_right(tss, ts + MAIN_WINDOW_S)
        out.append(_modal(Counter(m.competition_id for m in ms[lo:hi])))
    return out


def reserve_event_ids(
    matches: Iterable[TeamMatch],
    listed: Mapping[int, frozenset[int]] = RESERVE_COMPETITIONS,
    probe: tuple[int, int] | None = None,
) -> frozenset[int]:
    """Event ids among one side's ``matches`` played by a second squad.

    ``probe`` = (ts, competition_id) asks the same question of a match not in
    the list (the fixture being sampled); it is answered as event id -1 and
    does not count toward any main competition or clash.
    """
    ms = sorted(set(matches), key=lambda m: (m.ts, m.event_id))
    if not ms:
        return frozenset()
    tss = [m.ts for m in ms]
    mains = _mains(ms, tss)
    # Which matches clash with a match of the side's main competition.
    clash_ts: dict[int, list[int]] = defaultdict(list)
    for i, m in enumerate(ms):
        main = mains[i]
        if main is None or m.competition_id == main:
            continue
        lo = bisect.bisect_left(tss, m.ts - CLASH_MAX_S)
        hi = bisect.bisect_right(tss, m.ts + CLASH_MAX_S)
        if any(
            ms[j].competition_id == main
            and CLASH_MIN_S <= abs(ms[j].ts - m.ts) <= CLASH_MAX_S
            for j in range(lo, hi)
        ):
            clash_ts[m.competition_id].append(m.ts)  # ascending: ms is sorted

    def second_squad(ts: int, comp: int, main: int | None) -> bool:
        if main is None or comp == main:
            return False
        if main in listed.get(comp, frozenset()):
            return True
        times = clash_ts.get(comp, [])
        lo = bisect.bisect_left(times, ts - MAIN_WINDOW_S)
        hi = bisect.bisect_right(times, ts + MAIN_WINDOW_S)
        return hi - lo >= MIN_CLASHES

    out = {
        m.event_id
        for i, m in enumerate(ms)
        if second_squad(m.ts, m.competition_id, mains[i])
    }
    if probe is not None:
        p_ts, p_comp = probe
        if second_squad(p_ts, p_comp, _mains(ms, [p_ts])[0]):
            out.add(-1)
    return frozenset(out)


def describe(
    matches: Iterable[TeamMatch], reserve: frozenset[int]
) -> str:
    """'competition c: n matches' for the gap a sample records."""
    per = Counter(m.competition_id for m in matches if m.event_id in reserve)
    return ", ".join(f"competition {c}: {n}" for c, n in sorted(per.items()))
