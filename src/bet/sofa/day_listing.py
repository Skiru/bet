"""A tournament's games of one day, and the match inside that small list
(identity plan K3, docs/sofa/history/PLAN_MAPA_DRUZYN_2026-10-14.md).

When neither Superbet name of a hockey / basketball / volleyball event has a
Sofascore id, there is no team to ask (`team/<id>/events/next`). Its
tournament may still be known: the entity map holds Superbet tournament ->
Sofascore unique tournament (sofa_tournament_map, K1), and
`unique-tournament/<ut>/scheduled-events/<day>` lists every game of it that
day with both teams' ids. Inside that list - one tournament, one hour - two
names need far less to tell one game from another than a search does.

`tournament_day_match` is that match: the games within MAX_START_GAP of the
start (sport, gender, not postponed), each read both ways round, scored by
its WEAKER side (resolve.part_score / sport_identity.side_score over
normalize_name, squad levels compatible); the best one is the event when its
weaker side reaches `min_score` and it leads the next game by `lead`. The
thresholds are measured, not chosen (scripts/sofa/measure_tournament_day.py).

Fetching goes through sofa_day_listing: a past day is asked once, today's
or a later day's again after LISTING_TTL. A refusal (provider error, open
breaker) raises and is never retried here (the bridge rule: slow down).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from bet.sofa.fixture_status import NOT_AS_SCHEDULED
from bet.sofa.names import normalize_name

LISTING_TTL = timedelta(minutes=45)
TOURNAMENT_DAY = "tournament_day"
SCHEDULED_TOURNAMENTS = "scheduled_tournaments"


class DayClient(Protocol):
    def tournament_day_events(
        self, unique_tournament_id: int, day: str
    ) -> Any | None: ...

    def scheduled_tournaments(
        self, sport_slug: str, day: str, page: int
    ) -> Any | None: ...


def _now() -> datetime:
    from bet.sofa import timeutil

    return timeutil.now()


def cached(
    conn: sqlite3.Connection, kind: str, key: str, day: str, at: datetime | None = None
) -> dict[str, Any] | None:
    """The stored payload, if still good: a day before today's (UTC) is
    final; today's and later expire after LISTING_TTL."""
    row = conn.execute(
        "SELECT fetched_at, payload_json FROM sofa_day_listing "
        "WHERE kind = ? AND key = ? AND day = ?",
        (kind, key, day),
    ).fetchone()
    if row is None:
        return None
    now = at or _now()
    fetched = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
    past_day = day < now.astimezone(UTC).strftime("%Y-%m-%d")
    if not past_day and now - fetched > LISTING_TTL:
        return None
    payload: dict[str, Any] = json.loads(row[1])
    return payload


def store(
    conn: sqlite3.Connection,
    kind: str,
    key: str,
    day: str,
    payload: Mapping[str, Any],
    at: datetime | None = None,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO sofa_day_listing (kind, key, day, fetched_at, "
        "payload_json) VALUES (?, ?, ?, ?, ?)",
        (
            kind,
            key,
            day,
            (at or _now()).astimezone(UTC).isoformat(),
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def tournament_day_events(
    client: DayClient,
    conn: sqlite3.Connection,
    ut: int,
    day: str,
    at: datetime | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """(the unique tournament's games on `day`, served from the cache). A
    404 is an empty day, stored like any answer."""
    hit = cached(conn, TOURNAMENT_DAY, str(ut), day, at)
    if hit is not None:
        return list(hit.get("events") or []), True
    payload = client.tournament_day_events(ut, day)
    if not isinstance(payload, dict):
        payload = {"events": []}
    store(conn, TOURNAMENT_DAY, str(ut), day, payload, at)
    return list(payload.get("events") or []), False


def _start(e: Mapping[str, Any]) -> datetime | None:
    ts = e.get("startTimestamp")
    return datetime.fromtimestamp(int(ts), UTC) if isinstance(ts, int) else None


def _name(e: Mapping[str, Any], side: str) -> tuple[int | None, str]:
    team = e.get(side) or {}
    tid = team.get("id")
    return (tid if isinstance(tid, int) else None, str(team.get("name") or ""))


def tournament_day_match(
    sport: str,
    team1: str,
    team2: str,
    kickoff: datetime,
    events: Iterable[Mapping[str, Any]],
    slug: str,
    min_score: float,
    lead: float,
    max_gap: timedelta = timedelta(hours=1),
) -> dict[str, Any]:
    """The one game of the list that is this event by both names, or why
    not: NO_GAME_WITHIN_1H, BELOW_MIN_SCORE, NO_CLEAR_LEAD."""
    from bet.sofa.resolve import sofascore_gender, superbet_gender
    from bet.sofa.sport_identity import same_squad, side_score

    gender = "W" if "W" in {superbet_gender(team1), superbet_gender(team2)} else "M"
    a1, a2 = normalize_name(team1), normalize_name(team2)
    scored: list[tuple[float, bool, Mapping[str, Any], tuple[float, float]]] = []
    for e in events:
        e_slug = (
            ((e.get("tournament") or {}).get("category") or {}).get("sport") or {}
        ).get("slug")
        if e_slug is not None and e_slug != slug:
            continue
        start = _start(e)
        if start is None or abs(start - kickoff) > max_gap:
            continue
        if str((e.get("status") or {}).get("type") or "") in NOT_AS_SCHEDULED:
            continue
        if sofascore_gender(dict(e)) != gender:
            continue
        (_, hname), (_, aname) = _name(e, "homeTeam"), _name(e, "awayTeam")
        h, a = normalize_name(hname), normalize_name(aname)
        for home_t1, (x1, x2) in ((True, (h, a)), (False, (a, h))):
            if not (same_squad(a1, x1) and same_squad(a2, x2)):
                continue
            s1, s2 = side_score(sport, a1, x1), side_score(sport, a2, x2)
            scored.append((min(s1, s2), home_t1, e, (round(s1, 1), round(s2, 1))))
    if not scored:
        return {"status": "NOT_IDENTIFIED", "reason": "NO_GAME_WITHIN_1H"}
    scored.sort(key=lambda x: -x[0])
    best = scored[0]
    # the runner-up is the best reading of ANOTHER game (the same game read
    # the other way round is not a rival)
    rival = next((x[0] for x in scored[1:] if x[2].get("id") != best[2].get("id")), 0.0)
    if best[0] < min_score:
        return {
            "status": "NOT_IDENTIFIED",
            "reason": "BELOW_MIN_SCORE",
            "best_score": round(best[0], 1),
        }
    if best[0] - rival < lead:
        return {
            "status": "NOT_IDENTIFIED",
            "reason": "NO_CLEAR_LEAD",
            "best_score": round(best[0], 1),
            "rival_score": round(rival, 1),
        }
    return {
        "status": "IDENTIFIED",
        "event": dict(best[2]),
        "home_is_team1": best[1],
        "name_scores": {"team1": best[3][0], "team2": best[3][1]},
        "rival_score": round(rival, 1),
        "match_method": "TOURNAMENT_DAY",
    }


def tournament_day_source(client: DayClient, conn: sqlite3.Connection) -> Any:
    """SPORT_IDENTITY's `tournament_day` callable: a BoardEvent's
    tournament games of its Superbet day, through the entity map's
    tournament map (sofa_tournament_map: every Sofascore competition seen
    under that Superbet tournament) and the cache. A refusal raises
    sport_identity.BridgeAbortedError, which stops the run like any listing
    request; an unmapped tournament is no list (no request)."""
    from bet.sofa.errors import CircuitOpenError, ProviderError
    from bet.sofa.sport_identity import BridgeAbortedError

    comps: dict[tuple[str, str], list[int]] = {}

    def competitions(sport: str, tournament: str) -> list[int]:
        key = (sport, tournament)
        if key not in comps:
            comps[key] = [int(r[0]) for r in conn.execute(
                "SELECT competition_id FROM sofa_tournament_map WHERE sport = ? "
                "AND superbet_tournament = ? ORDER BY events DESC", key)]
        return comps[key]

    def source(ev: Any) -> list[dict[str, Any]]:
        if not ev.tournament:
            return []
        out: list[dict[str, Any]] = []
        for ut in competitions(str(ev.sport), str(ev.tournament).strip()):
            try:
                day = str(ev.kickoff_utc)[:10]
                events, _ = tournament_day_events(client, conn, ut, day)
                conn.commit()
            except (ProviderError, CircuitOpenError) as exc:
                raise BridgeAbortedError(str(exc)) from exc
            out += events
        return out

    return source
