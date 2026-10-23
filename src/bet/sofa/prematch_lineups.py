"""Sofascore's pre-match line-ups and absences for every match an analyst reads.

Sofascore publishes a predicted XI (and its list of missing / doubtful
players) before a football match and replaces it with the confirmed one about
an hour before kick-off (`scripts/sofa/probe_lineup_availability.py`). The
read-set writers (`read_set.py`, `build_slip.py`) ask `/event/{id}/lineups`
for each read match not yet started, before the dossiers, and keep the answer
in `runs/sofa/<d>/lineups_prematch.json`; the dossier shows it beside the
legs (`bet.sofa.dossier`, block `lineups`).

Display only: the dossier reads this file; SAMPLES, SHEET, a confidence and
every gate never do.

The trap this module exists around: the cache keeps a match's `/lineups`
answer **forever** in `sofa_event_stats.lineups_json`
(`SofaCache.save_event_lineups`, `samples.fetch_lineups`) as the post-match
fact player samples and SETTLE read. A pre-match line-up written there would
be read as who played. So nothing here touches the cache: the client is the
only collaborator, and the answer lives in the day's artifact alone.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from bet.sofa.atomic import write_atomic
from bet.sofa.errors import CircuitOpenError, SofaError

FILE = "lineups_prematch.json"
OK = "OK"
NOT_PUBLISHED = "NOT_PUBLISHED"  # 404 or an answer with no squad
# Sports whose cached /lineups answers have football's shape (players with a
# `substitute` flag per side; checked on data/sofa.db 2026-10-23: football,
# basketball, hockey). Tennis has no squads, CS2 its own esports route.
SPORTS = frozenset({"football", "hockey", "basketball"})
REASK_AFTER_S = 30 * 60  # an unconfirmed answer is asked again after 30 min


class Client(Protocol):
    def event_lineups(self, id: int) -> Any | None: ...


def path(run: Path) -> Path:
    return run / FILE


def load(run: Path) -> dict[str, dict[str, Any]]:
    """{event id (str): entry}; {} when the file is missing or unreadable."""
    try:
        doc = json.loads(path(run).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    events = doc.get("events") if isinstance(doc, dict) else None
    return events if isinstance(events, dict) else {}


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: object) -> datetime | None:
    if not isinstance(stamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _player(node: object) -> dict[str, Any]:
    p = node if isinstance(node, Mapping) else {}
    return {k: v for k, v in (("id", p.get("id")), ("name", p.get("name")),
                              ("position", p.get("position")))
            if v not in (None, "")}


def parse_side(block: object) -> dict[str, Any] | None:
    """One side of a /lineups answer; None when it lists nobody."""
    if not isinstance(block, Mapping):
        return None
    players = [e for e in block.get("players") or [] if isinstance(e, Mapping)]
    if not players:
        return None
    starters: list[dict[str, Any]] = []
    subs: list[dict[str, Any]] = []
    for entry in players:
        row = _player(entry.get("player"))
        shirt = entry.get("shirtNumber") or entry.get("jerseyNumber")
        if shirt not in (None, ""):
            row["shirt"] = shirt
        if entry.get("position") and "position" not in row:
            row["position"] = entry["position"]
        (subs if entry.get("substitute") is True else starters).append(row)
    out: dict[str, Any] = {"starters": starters, "substitutes": subs}
    if block.get("formation"):
        out["formation"] = block["formation"]
    listed = block.get("missingPlayers")
    out["missing_listed"] = isinstance(listed, list)
    missing = []
    for m in listed if isinstance(listed, list) else []:
        if not isinstance(m, Mapping):
            continue
        row = _player(m.get("player"))
        # every scalar Sofascore gives (type missing / doubtful, its reason
        # code, a description, an expected return) - copied, never decoded
        row.update({k: v for k, v in m.items()
                    if k != "player" and isinstance(v, str | int | float | bool)})
        missing.append(row)
    out["missing"] = missing
    return out


def parse(payload: Any) -> dict[str, Any]:
    """status + confirmed + both sides of one /lineups answer (None = 404)."""
    if not isinstance(payload, Mapping):
        return {"status": NOT_PUBLISHED}
    sides = {s: parse_side(payload.get(s)) for s in ("home", "away")}
    if not any(sides.values()):
        return {"status": NOT_PUBLISHED, "note": "odpowiedź bez składów"}
    out: dict[str, Any] = {"status": OK, "confirmed": payload.get("confirmed") is True}
    for side, block in sides.items():
        out[side] = block if block is not None else {"missing_side": "brak składu"}
    return out


def fetch_one(client: Client, event_id: int, at: datetime) -> dict[str, Any]:
    """One match's entry. Raises CircuitOpenError (the caller stops); any
    other provider error is the entry's status."""
    entry: dict[str, Any] = {"asked_at_utc": _stamp(at)}
    try:
        payload = client.event_lineups(event_id)
    except CircuitOpenError:
        raise
    except SofaError as exc:
        return {**entry, "status": f"FAILED {type(exc).__name__}: {exc}"}
    return {**entry, **parse(payload)}


def due(entry: Mapping[str, Any] | None, at: datetime) -> bool:
    """A confirmed answer is final; an unconfirmed or unpublished one is asked
    again after REASK_AFTER_S; a failure or a never-asked match at once."""
    if not entry or not entry.get("asked_at_utc"):
        return True
    status = str(entry.get("status") or "")
    if status == OK and entry.get("confirmed") is True:
        return False
    if status not in (OK, NOT_PUBLISHED):
        return True
    asked = _parse(entry.get("asked_at_utc"))
    return asked is None or (at - asked).total_seconds() >= REASK_AFTER_S


def _kept(old: Mapping[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    """A failed attempt never erases an earlier answer: the answer stays and
    the attempt is recorded beside it."""
    if old.get("status") in (OK, NOT_PUBLISHED):
        return {**old, "last_attempt": attempt}
    return attempt


def fetch(
    run: Path,
    matches: Iterable[tuple[int, str, datetime | None]],
    client: Client,
    at: datetime,
) -> dict[str, int]:
    """Ask the line-ups of every (event id, sport, kick-off) that is of a
    covered sport, not yet started at `at` and due; every old entry kept.
    Writes the file after each match (a stopped run keeps its answers). A
    breaker refusal stops the pass: the rest are NOT_ASKED. Returns a status
    count."""
    entries = load(run)
    counts: dict[str, int] = {}

    def add(key: str, n: int = 1) -> None:
        counts[key] = counts.get(key, 0) + n

    todo: list[tuple[int, str, datetime | None]] = []
    seen: set[int] = set()
    for event_id, sport, kickoff in matches:
        if event_id in seen:
            continue
        seen.add(event_id)
        if sport not in SPORTS:
            add("sport_not_covered")
        elif kickoff is not None and kickoff <= at:
            add("started")
        elif not due(entries.get(str(event_id)), at):
            add("final" if entries[str(event_id)].get("confirmed") else "fresh")
        else:
            todo.append((event_id, sport, kickoff))
    for i, (event_id, sport, kickoff) in enumerate(todo):
        old = entries.get(str(event_id)) or {}
        try:
            entry = fetch_one(client, event_id, at)
        except CircuitOpenError:
            for rest_id, rest_sport, rest_kick in todo[i:]:
                attempt = {"asked_at_utc": _stamp(at),
                           "status": "NOT_ASKED breaker open", "sport": rest_sport}
                entries[str(rest_id)] = _kept(entries.get(str(rest_id)) or {}, attempt)
            add("NOT_ASKED", len(todo) - i)
            break
        entry["sport"] = sport
        if kickoff is not None:
            entry["kickoff_utc"] = _stamp(kickoff)
        entries[str(event_id)] = (entry if entry["status"] in (OK, NOT_PUBLISHED)
                                  else _kept(old, entry))
        add(entry["status"].split(" ")[0])
        _write(run, entries)
    _write(run, entries)
    return counts


def _write(run: Path, entries: Mapping[str, Any]) -> None:
    write_atomic(path(run), json.dumps(
        {"source": "Sofascore /event/{id}/lineups przed meczem (tylko do odczytu "
                   "analityka; nigdy w cache sofa_event_stats)",
         "events": entries},
        ensure_ascii=False, indent=1) + "\n")


def _kickoff(leg: Mapping[str, Any]) -> datetime | None:
    return _parse(leg.get("kickoff_utc"))


def matches_of(
    legs: Iterable[Mapping[str, Any]],
) -> list[tuple[int, str, datetime | None]]:
    """(event id, sport, earliest kick-off) per match of the read legs."""
    out: dict[int, tuple[str, datetime | None]] = {}
    for leg in legs:
        eid = leg.get("sofascore_event_id")
        if not isinstance(eid, int):
            continue
        sport = str(leg.get("sport") or "football")
        kick = _kickoff(leg)
        if eid in out:
            known = [k for k in (out[eid][1], kick) if k is not None]
            kick = min(known) if known else None
        out[eid] = (sport, kick)
    return [(eid, sport, kick) for eid, (sport, kick) in out.items()]


def fetch_for_legs(run: Path, legs: Iterable[Mapping[str, Any]],
                   client: Client | None = None) -> str:
    """fetch for a read-set writer, through the bridge: one line for its
    output. A failure is reported, never raised - the dossier then says the
    line-up was not asked."""
    from bet.sofa.timeutil import now

    matches = matches_of(legs)
    if not matches:
        return "składy: brak meczów"
    try:
        if client is None:
            from bet.sofa.client import SofascoreClient
            from bet.sofa.config import SofaConfig

            client = SofascoreClient(SofaConfig.from_env())
        counts = fetch(run, matches, client, now())
    except Exception as exc:  # noqa: BLE001 - reported, the read set goes on
        return (f"składy: BŁĄD {type(exc).__name__}: {exc}"
                " - dossier bez składów Sofascore")
    return "składy: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
