"""Legs a coupon printed before their match started stay on it (2026-10-05).

The operator's decision of 2026-10-05: "a leg printed on the coupon before
its match started counts". Until then a rebuild of CONFIDENCE after the first
kickoffs dropped every leg whose match had started (the kickoff gate refuses
it, rightly, as a NEW bet), and since 7c / 7d of audit_settlement and the
ledger grade what the artifact prints, those legs were never graded: on
2026-10-03 one official and 66 WARIANT legs vanished this way, on 10-04 21
WARIANT legs.

The fix is the per-sport coupons' (sport_coupon.locked_legs / select): before
a profile's artifact is overwritten, the previous artifact of the SAME profile
is read, and every leg it printed whose match has started - or is inside the
kickoff margin - at the rebuild is carried over unchanged, `locked: true`,
with its printed price and confidence, the build it was printed in
(`printed_at_utc`) and the dials that build applied (`printed_under`), so an
auditor can check it against the rule and the clock it was printed under.

Interpretation boundary, decided here and pinned by tests:

* Only a leg whose match had started (or was inside the margin) at the
  rebuild is locked. A leg a rebuild removes BEFORE its match starts - an
  analyst veto, a NO_BET / WATCH read, a moved price, any gate - stays
  removed: the operator saw the new PDF before the kickoff.
* A veto or a NO_BET / WATCH read that covers a locked leg does NOT remove
  it: the leg was printed and its match is under way, so it is a fact of the
  day, not a decision still open. Reads carry no timestamp, so "arrived after
  the start" cannot be told from "was there all along but the earlier build
  ignored it"; the second cannot happen (the earlier build applied the same
  rule), so every such refusal is recorded in the artifact as
  `locked_late_refusals` and printed on stderr - shown, never acted on.
* The kickoff clock is the one every CONFIDENCE gate uses
  (`kickoff_clocks` + `confidence.too_close_to_kickoff`, and Superbet's own
  start signal), so a fixture is locked exactly when its fresh rows are
  refused KICKED_OFF - a locked leg and a fresh copy of it cannot both exist.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bet.sofa.confidence import printed_builders, printed_singles, too_close_to_kickoff

LegKey = tuple[int, str, str, float, str]

# The dials a printed leg was selected under; carried with it so an auditor
# checks a locked leg against its own build's rule, not the rebuild's (the
# official profile's dials change on 2026-10-05 itself).
DIAL_FIELDS = ("confidence_floor", "min_ev", "max_overround")


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def leg_key(leg: Mapping[str, Any], event_id: Any = None) -> LegKey:
    """One rung and side of one fixture - the key every grader uses."""
    eid = leg.get("sofascore_event_id", event_id)
    return (
        int(eid),
        str(leg["market"]),
        str(leg.get("subject") or ""),
        float(leg["line"]),
        str(leg["direction"]),
    )


def kickoff_clocks(
    fixture: Mapping[str, Any] | None, seen_kickoff: str | None
) -> list[datetime]:
    """Every start time the pipeline holds for a fixture.

    Sofascore's and Superbet's as RESOLVE froze them, and Superbet's as OFFER
    last saw it (FixtureOffer.superbet_kickoff_seen_utc). The gates take the
    EARLIEST (too_close_to_kickoff): for ITF Sofascore's clock runs 7-9 h
    late, and Superbet moves starts earlier too.
    """
    raw = (
        (fixture or {}).get("kickoff_utc"),
        (fixture or {}).get("superbet_kickoff_utc"),
        seen_kickoff,
    )
    return [_utc(str(t)) for t in raw if t]


def kicked_off(
    fixture: Mapping[str, Any] | None,
    seen_kickoff: str | None,
    superbet_started: bool,
    now: datetime,
) -> bool:
    """CONFIDENCE's kickoff gate: Superbet reports the match under way, or the
    earliest clock is inside the margin (no clock at all counts as started).
    The one predicate for refusing a fresh row and for locking a printed one.
    """
    return superbet_started or too_close_to_kickoff(
        kickoff_clocks(fixture, seen_kickoff), now
    )


@dataclass
class LockedPrint:
    """What a rebuild carries over from the previous artifact."""

    singles: list[dict[str, Any]] = field(default_factory=list)
    builders: list[dict[str, Any]] = field(default_factory=list)
    # The full leg rows behind the locked singles and builder legs, for the
    # artifact's `legs` (the PDF reads a builder leg's numbers from there).
    legs: list[dict[str, Any]] = field(default_factory=list)
    previous_created_at_utc: str | None = None

    @property
    def keys(self) -> set[LegKey]:
        out = {leg_key(s) for s in self.singles}
        for b in self.builders:
            out |= {leg_key(x, b["sofascore_event_id"]) for x in b.get("legs") or []}
        return out

    @property
    def builder_fixtures(self) -> set[int]:
        return {int(b["sofascore_event_id"]) for b in self.builders}

    def __bool__(self) -> bool:
        return bool(self.singles or self.builders)


def _stamp(
    item: Mapping[str, Any], created: str, dials: dict[str, Any]
) -> dict[str, Any]:
    # A leg locked by an earlier rebuild keeps the build it was really printed
    # in and that build's dials: locking twice never moves the timestamp.
    return {
        **item,
        "locked": True,
        "printed_at_utc": item.get("printed_at_utc", created),
        "printed_under": item.get("printed_under", dials),
    }


def carry_over(
    previous: Mapping[str, Any] | None,
    profile_name: str,
    now: datetime,
    is_locked: Callable[[int, str | None], bool],
    pdf_printed: bool = True,
    sports: frozenset[str] | None = None,
) -> LockedPrint:
    """The printed legs and builders of `previous` that a rebuild at `now`
    must keep. `is_locked(event_id, printed_kickoff)` is the kickoff gate.

    `pdf_printed` False: no PDF was rendered from `previous` (the provisional
    build before the analysts' read), so only what it had already locked from
    an earlier printed build is carried; its own fresh legs were never seen.

    Nothing is carried from an artifact of another profile, or from one built
    after `now` (an as-of replay into the past must not import the future).

    `sports`: only singles of these sports (a leg without `sport` is
    football / tennis) - CONFIDENCE reading a coupon artifact (11_coupon.json)
    that also holds the measured sports' legs, which build_coupon.py locks.
    The dials of the build the leg was printed in include its `epoch`
    (bet.sofa.epochs) where that build wrote one; none is the old rule.
    """
    if not previous or previous.get("profile", "standard") != profile_name:
        return LockedPrint()
    created = previous.get("created_at_utc")
    if not isinstance(created, str) or _utc(created) > now:
        return LockedPrint()
    dials = {k: previous.get(k) for k in DIAL_FIELDS}
    if previous.get("epoch"):
        dials["epoch"] = previous["epoch"]
    doc = dict(previous)
    by_key = {leg_key(x): x for x in doc.get("legs") or []}
    out = LockedPrint(previous_created_at_utc=created)
    # A printed-coupon manifest (PRINTED_MANIFEST) knows when the PDF was
    # rendered; that, not the build, is when the operator saw the leg.
    rendered = previous.get("pdf_rendered_at_utc")
    created = str(rendered) if isinstance(rendered, str) else created
    seen: set[LegKey] = set()
    for s in printed_singles(doc):
        if not pdf_printed and not s.get("locked"):
            continue
        if sports is not None and str(s.get("sport") or "football") not in sports:
            continue
        if is_locked(int(s["sofascore_event_id"]), s.get("kickoff_utc")):
            out.singles.append(_stamp(s, created, dials))
            k = leg_key(s)
            if k not in seen:
                seen.add(k)
                out.legs.append(_stamp(by_key.get(k, s), created, dials))
    for b in printed_builders(doc):
        eid = int(b["sofascore_event_id"])
        if not pdf_printed and not b.get("locked"):
            continue
        if not is_locked(eid, b.get("kickoff_utc")):
            continue
        out.builders.append(_stamp(b, created, dials))
        for x in b.get("legs") or []:
            k = leg_key(x, eid)
            if k not in seen and k in by_key:
                seen.add(k)
                out.legs.append(_stamp(by_key[k], created, dials))
    return out


# The coupon as its PDF last printed it (plan 2026-10-05, review of K3): the
# PDF writes it after every render, so a rebuild carries over the legs of
# the last PRINTED coupon even when an unprinted rebuild (the provisional
# build before the analysts' read) came in between. Without it the next
# build read the newest artifact, whose PDF was older than it, and locked
# only what that artifact had locked itself - a leg on the PDF the operator
# held, starting during the analysts' read, was dropped.
PRINTED_MANIFEST = "12_printed.json"


def merge_locked(first: LockedPrint, second: LockedPrint) -> LockedPrint:
    """Both carry-overs, `first` winning a leg or a fixture both hold."""
    out = LockedPrint(
        previous_created_at_utc=first.previous_created_at_utc
        or second.previous_created_at_utc
    )
    seen: set[LegKey] = set()
    for s in [*first.singles, *second.singles]:
        if leg_key(s) not in seen:
            seen.add(leg_key(s))
            out.singles.append(s)
    fixtures: set[int] = set()
    for b in [*first.builders, *second.builders]:
        if int(b["sofascore_event_id"]) not in fixtures:
            fixtures.add(int(b["sofascore_event_id"]))
            out.builders.append(b)
    seen_legs: set[LegKey] = set()
    for x in [*first.legs, *second.legs]:
        if leg_key(x) not in seen_legs:
            seen_legs.add(leg_key(x))
            out.legs.append(x)
    return out


def printed_leg_keys(
    artifact: Mapping[str, Any], sheet_sports_only: bool = False
) -> set[LegKey]:
    """Every rung the PDF built from this artifact prints - singles and the
    legs of printed builders, locked or not. `sheet_sports_only`: football and
    tennis only (a coupon artifact also holds the measured sports' legs,
    which SETTLE does not grade)."""
    doc = dict(artifact)
    keys = {
        leg_key(s) for s in printed_singles(doc)
        if not sheet_sports_only or str(s.get("sport") or "football") in (
            "football", "tennis")
    }
    for b in printed_builders(doc):
        keys |= {leg_key(x, b["sofascore_event_id"]) for x in b.get("legs") or []}
    return keys
