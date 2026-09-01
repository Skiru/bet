"""Name a Superbet fixture by id instead of by spelling.

The problem this solves, with the number attached
-------------------------------------------------
``superbet_offer.match_offer_events`` joins our events to Superbet's by
comparing normalised participant names inside a per-sport kickoff window. It is
careful and it is conservative -- it refuses rather than guesses -- and on a
real slate it still loses fixtures the book is plainly carrying.

Measured end to end on 2026-09-01: a real 179-fixture football DISCOVER run
(bzzoiro + highlightly + odds-api, so an event list this module had no hand in
producing) against Superbet PL's live offer, the same feed, minutes apart:

=================================  ========  =============  ==============
``--oddspapi-bridge``              Matched   Priced lines   Disagreements
=================================  ========  =============  ==============
``off``                            115       16,867         --
``on``                             123       17,111         0
=================================  ========  =============  ==============

Eight fixtures recovered, none lost, and on the 115 both matchers could name
they never once chose a different Superbet event. The eight are not spelling
variants a better normaliser would catch -- they are different *names* for the
same club:

    "Universitatea Cluj" / "U Cluj"          "Afc '34" / "Amsterdamsche"
    "Chadormalu SC" / "Chador Malu Yazd"     "Al Tadhamon" / "Al Tadamon"
    "Polonia Sroda Wielkopolska" / "Polonia Środa Wlkp."

(An earlier, separate fix -- transliterating ł, ø and friends in
``fold_club_name`` rather than deleting them -- recovered a different and
larger set, the Polish league. See ``tests/test_club_name_folding.py``. The two
are complementary: the fold fixes spellings, the bridge fixes names.)

How the bridge works
--------------------
OddsPapi's ``/v4/fixtures`` carries ``externalProviders.betradarId`` on **100%**
of soccer fixtures, and superbet.pl's own public offer publishes a
``betradarId`` on every real (non-virtual) event it lists. So:

    our event --(name + kickoff, against OddsPapi's canonical English names)-->
    OddsPapi fixture --(betradarId, exact integer)--> Superbet PL event

The first hop is still fuzzy, but it is fuzzy against a *cleaner* target: an
English canonical name with an exact UTC kickoff, rather than a Polish
abbreviation on a court-order estimate. The second hop is not fuzzy at all.

Why the price still does not come from here
-------------------------------------------
The free plan does not carry ``superbet.pl`` -- ``/v4/odds`` answers 403
``RESTRICTED_ACCESS`` for that slug and serves ``superbet`` (a clone of
``superbet.ro``) instead. Measured on West Ham-Wolves, the two post the *same*
line ladder at prices 0.5-1.5% apart. So OddsPapi is allowed to say **which
fixture** this is and is never allowed to say **what it costs**: the price of
record stays superbet.pl's own feed. A one-percent-optimistic price presented
as takeable is exactly the failure this whole step exists to prevent.

Cost, and the reserve
---------------------
The free plan is **250 requests in total**, not per day. A bridge run spends one
``/account`` probe (cached on disk, six hours) plus one ``/fixtures`` call per
sport -- so two on a normal football+tennis day. ``MIN_QUOTA_RESERVE`` stops the
bridge well before the allowance runs out, because an optional identity
improvement must never be the thing that spends the last request the pipeline
had for something else.

Every failure mode here is a no-op. No key, no quota, provider down, restricted
plan: the bridge returns empty and ``match_offer_events`` behaves exactly as it
did before it existed.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.simple_stats.contracts import EventListV1, EventRecord

# Sports OddsPapi can be asked about *and* this pipeline reads. Anything else in
# an event list is skipped rather than translated: spending a request on a sport
# whose fixtures nothing downstream will join is pure waste.
BRIDGED_SPORTS: frozenset[str] = frozenset({"football", "tennis"})

# Leave this many requests unspent. The bridge is a nice-to-have; the account
# probe and a healthcheck are not, and neither is whatever the operator wants to
# run by hand next week.
MIN_QUOTA_RESERVE = 40

ACCOUNT_CACHE_TTL_SECONDS = 6 * 3600
_DEFAULT_ACCOUNT_CACHE = (
    Path(__file__).resolve().parents[3] / "betting" / "data" / "stats_cache" / "oddspapi" / "account.json"
)


@dataclass(frozen=True)
class IdentityBridge:
    """Our ``event_id`` -> Betradar id, plus how it went and what it cost.

    ``notes`` are for the run summary, not for ``data_gaps``: a bridge that did
    not run is a missing optimisation, and a betting day is not degraded by it.
    """

    betradar_by_event_id: Mapping[str, str] = field(default_factory=dict)
    enabled: bool = False
    requests_made: int = 0
    quota_remaining: int | None = None
    sports: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.betradar_by_event_id)

    def as_metrics(self) -> dict[str, Any]:
        return {
            "oddspapi_bridge_enabled": self.enabled,
            "oddspapi_bridge_events": len(self.betradar_by_event_id),
            "oddspapi_bridge_requests": self.requests_made,
            "oddspapi_quota_remaining": self.quota_remaining,
            "oddspapi_bridge_notes": list(self.notes),
        }


def disabled(reason: str) -> IdentityBridge:
    return IdentityBridge(enabled=False, notes=(reason,))


# --- account snapshot, cached ----------------------------------------------


def _cache_path() -> Path:
    override = os.getenv("ODDSPAPI_ACCOUNT_CACHE")
    return Path(override) if override else _DEFAULT_ACCOUNT_CACHE


def read_cached_account(*, now: datetime | None = None) -> dict[str, Any] | None:
    """The last ``/account`` answer, if it is still fresh enough to trust.

    Freshness matters in one direction only: a stale snapshot can overstate the
    remaining quota and let the bridge start a run it cannot finish. Six hours
    is short enough that the reserve absorbs the drift, and long enough that a
    pipeline run twice a day does not pay for the probe twice.
    """
    path = _cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    fetched = payload.get("fetched_at")
    try:
        moment = datetime.fromisoformat(str(fetched).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    age = ((now or datetime.now(UTC)) - moment).total_seconds()
    if age < 0 or age > ACCOUNT_CACHE_TTL_SECONDS:
        return None
    snapshot = payload.get("account")
    return snapshot if isinstance(snapshot, dict) else None


def write_cached_account(snapshot: Mapping[str, Any], *, now: datetime | None = None) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"fetched_at": (now or datetime.now(UTC)).isoformat(), "account": dict(snapshot)},
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        # A cache that cannot be written costs one request next time. It is not
        # a reason to fail a betting day.
        return


# --- the bridge -------------------------------------------------------------


def build_identity_bridge(
    event_list: EventListV1,
    *,
    client: Any | None = None,
    window: tuple[datetime, datetime] | None = None,
    min_quota_reserve: int = MIN_QUOTA_RESERVE,
    now: datetime | None = None,
    use_cache: bool = True,
) -> IdentityBridge:
    """Resolve as many of our events as possible to a Betradar id.

    Returns an empty, ``enabled=False`` bridge for every reason a run might not
    happen -- no credential, no quota, provider error -- and never raises. The
    caller's fallback is the behaviour it already had.
    """
    from bet.api_clients.oddspapi import (  # imported late: optional dependency
        OddsPapiClient,
        OddspapiConfig,
    )

    sports = tuple(
        sport for sport in dict.fromkeys(event.sport for event in event_list.events)
        if sport in BRIDGED_SPORTS
    )
    if not sports:
        return disabled("no bridgeable sport on this event list")

    try:
        config = OddspapiConfig.from_env()
    except Exception as exc:  # noqa: BLE001 - a missing key is a skip, not a crash
        return disabled(f"oddspapi unavailable: {exc}")

    api = client or OddsPapiClient(config)
    notes: list[str] = []
    moment = now or datetime.now(UTC)

    snapshot = read_cached_account(now=moment) if use_cache else None
    if snapshot is None:
        try:
            account = api.account()
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return disabled(f"oddspapi account probe failed: {exc}")
        snapshot = account.as_dict()
        if use_cache:
            write_cached_account(snapshot, now=moment)
    else:
        notes.append("account snapshot served from cache")

    remaining = int(snapshot.get("remaining") or 0)
    needed = len(sports)
    if remaining - needed < min_quota_reserve:
        return disabled(
            f"oddspapi quota too low for the bridge: {remaining} left, "
            f"{needed} needed, reserve {min_quota_reserve}"
        )

    start, end = window or _default_window(event_list.date)
    events_by_sport: dict[str, list[EventRecord]] = {}
    for event in event_list.events:
        if event.sport in BRIDGED_SPORTS:
            events_by_sport.setdefault(event.sport, []).append(event)

    resolved: dict[str, str] = {}
    for sport in sports:
        try:
            fixtures = api.fixtures(sport, start, end)
        except Exception as exc:  # noqa: BLE001 - one dead sport is not a dead bridge
            notes.append(f"{sport}: fixtures call failed: {exc}")
            continue
        with_ids = [item for item in fixtures if item.betradar_id]
        if not with_ids:
            notes.append(f"{sport}: no fixture carried a betradarId")
            continue
        matched = _match_events_to_fixtures(events_by_sport.get(sport, ()), with_ids)
        resolved.update(matched)
        notes.append(
            f"{sport}: {len(matched)}/{len(events_by_sport.get(sport, ()))} events "
            f"resolved from {len(with_ids)} fixtures"
        )

    return IdentityBridge(
        betradar_by_event_id=resolved,
        enabled=True,
        requests_made=int(getattr(api, "request_count", 0)),
        quota_remaining=max(0, remaining - int(getattr(api, "request_count", 0))),
        sports=sports,
        notes=tuple(notes),
    )


def _default_window(date: str) -> tuple[datetime, datetime]:
    """The betting day, widened by six hours on each side.

    Widened because a fixture at 23:30 local is the next UTC day for half the
    year, and because OddsPapi's ``startTime`` is the true kickoff while our
    event list carries the scheduled one.
    """
    day = datetime.fromisoformat(f"{date}T00:00:00+00:00")
    return (day - timedelta(hours=6), day + timedelta(hours=30))


def _match_events_to_fixtures(
    events: Iterable[EventRecord],
    fixtures: Iterable[Any],
) -> dict[str, str]:
    """Pair our events with OddsPapi fixtures. Refuse anything ambiguous.

    Reuses ``superbet_offer``'s own comparison functions rather than restating
    them: two matchers that disagree about whether "Estudiantes" is
    "Estudiantes La Plata" would put the bridge and the fallback into a fight
    that only shows up on the fixtures nobody checked.
    """
    from bet.simple_stats.superbet_offer import (
        KICKOFF_TOLERANCE_MINUTES,
        _parse_kickoff,
        _side_key,
        _sides,
        sides_compatible,
    )

    pool = [
        (fixture, _side_key((fixture.home, fixture.away)))
        for fixture in fixtures
        if fixture.home and fixture.away
    ]
    resolved: dict[str, str] = {}
    claimed: dict[str, str] = {}

    for event in events:
        mine = _side_key(_sides(event))
        if len(mine) != 2:
            continue
        ours = _parse_kickoff(event.start_time)
        tolerance = KICKOFF_TOLERANCE_MINUTES.get(event.sport, 45.0)
        hits: list[tuple[float, Any]] = []
        for fixture, theirs in pool:
            if len(theirs) != 2:
                continue
            delta = _minutes_apart(ours, fixture.start_time)
            if delta is None or delta > tolerance:
                continue
            straight = sides_compatible(mine[0], theirs[0]) and sides_compatible(mine[1], theirs[1])
            crossed = sides_compatible(mine[0], theirs[1]) and sides_compatible(mine[1], theirs[0])
            if straight or crossed:
                hits.append((delta, fixture))
        if len(hits) != 1:
            # Zero is a miss and more than one is a coin flip. Both leave the
            # event to the name matcher, which is no worse than before.
            continue
        _, fixture = hits[0]
        betradar_id = str(fixture.betradar_id)
        # One Betradar id is one fixture. If two of our events claim the same
        # one, our own event list has a duplicate and neither claim is safe.
        previous = claimed.get(betradar_id)
        if previous is not None:
            resolved.pop(previous, None)
            continue
        claimed[betradar_id] = event.event_id
        resolved[event.event_id] = betradar_id
    return resolved


def _minutes_apart(ours: datetime | None, theirs: datetime | None) -> float | None:
    if ours is None or theirs is None:
        return None
    return abs((theirs - ours).total_seconds()) / 60.0
