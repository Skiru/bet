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

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from bet.sofa import fixture_status as fs
from bet.sofa.atomic import write_atomic
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
    line = leg.get("line")
    return (
        int(eid),
        str(leg["market"]),
        str(leg.get("subject") or ""),
        # None on a measured sport's winner / 1X2 leg (F7) - such a leg is
        # never a sheet row, so it never meets a float key.
        float(line) if line is not None else cast(float, None),
        str(leg["direction"]),
    )


def kickoff_clocks(
    fixture: Mapping[str, Any] | None,
    seen_kickoff: str | None,
    refreshed_start: str | None = None,
) -> list[datetime]:
    """Every start time the pipeline holds for a fixture.

    Sofascore's and Superbet's as RESOLVE froze them, and Superbet's as OFFER
    last saw it (FixtureOffer.superbet_kickoff_seen_utc). The gates take the
    EARLIEST (too_close_to_kickoff): for ITF Sofascore's clock runs 7-9 h
    late, and Superbet moves starts earlier too.

    `refreshed_start` (bet.sofa.fixture_status, K12): Sofascore's start read
    fresh from /event/{id}. It replaces both frozen clocks - RESOLVE's
    Sofascore one, and its Superbet one where OFFER saw a newer Superbet
    clock - so a match moved later is no longer gated on the start it had at
    dawn. Without it the clocks are exactly what they were.
    """
    if refreshed_start:
        superbet = seen_kickoff or (fixture or {}).get("superbet_kickoff_utc")
        return [_utc(str(t)) for t in (refreshed_start, superbet) if t]
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
    refreshed_start: str | None = None,
) -> bool:
    """CONFIDENCE's kickoff gate: Superbet reports the match under way, or the
    earliest clock is inside the margin (no clock at all counts as started).
    The one predicate for refusing a fresh row and for locking a printed one.
    """
    return superbet_started or too_close_to_kickoff(
        kickoff_clocks(fixture, seen_kickoff, refreshed_start), now
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
    # Printed legs whose match had started before the print they come from
    # (PDF rendered after the kickoff): never a bet made before the start, so
    # never locked - recorded here, not dropped in silence.
    printed_after_start: list[dict[str, Any]] = field(default_factory=list)

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


# "Had this match started by time t?" - (event id, printed kickoff, t).
StartedBy = Callable[[int, str | None, datetime], bool]


def started_by_printed_kickoff(
    event_id: int, printed_kickoff: str | None, at: datetime
) -> bool:
    """The fallback: only the clock the leg was printed with."""
    return bool(printed_kickoff) and _utc(str(printed_kickoff)) <= at


def started_by_evidence(
    superbet_started_utc: Mapping[int, str],
    fixture_status: Mapping[int, Mapping[str, Any]],
) -> StartedBy:
    """When a match REALLY started, from what the day holds: Superbet's start
    signal seen by then (OFFER's superbet_started_utc) says it had; else
    FIXTURE_CHECK's fresh read - a tennis match's real first point
    (`real_start_utc`, fixture_status.real_start: the 1st set's start, or an
    upper bound on it from a later set - F0.3), else a status of a match not
    yet begun, read at or after t, says it had not, any other status compares
    its fresh start; else the printed clock. The kickoff GATE stays on the
    earliest clock.

    `real_start_utc` comes before `start_utc` because the latter is the
    order of play's time: 10-05, Dedura-Palomero - Tarvet's said 09:10Z and
    the first set began 09:14:04Z; Grenier - Kravchenko's 09:40:00Z, the
    first point 09:40:52Z. As an upper bound in a later set it may call a
    match "not started by t" for the minutes of the breaks between sets."""

    def started_by(event_id: int, printed_kickoff: str | None, at: datetime) -> bool:
        seen = superbet_started_utc.get(event_id)
        if seen and _utc(seen) <= at:
            return True
        entry = fixture_status.get(event_id)
        if entry and entry.get("status") not in (None, fs.UNVERIFIED):
            if entry.get("real_start_utc"):
                return _utc(str(entry["real_start_utc"])) <= at
            checked = entry.get("checked_at_utc")
            if (entry["status"] in fs.NOT_YET_STARTED and checked
                    and _utc(str(checked)) >= at):
                return False
            if entry.get("start_utc"):
                return _utc(str(entry["start_utc"])) <= at
        return started_by_printed_kickoff(event_id, printed_kickoff, at)

    return started_by


def printed_after_its_start(
    item: Mapping[str, Any], created: str, started_by: StartedBy | None = None
) -> bool:
    """The print the leg is carried from (its own printed_at_utc if an earlier
    rebuild locked it, else this print) came after its match had REALLY
    started. `started_by` reads the real start (CONFIDENCE: Superbet's start
    signal, FIXTURE_CHECK's fresh status and start); without it the printed
    kickoff is all there is. 10-05: the PDF was rendered 09:19Z; Grenier's
    printed clock said 09:00Z but the match began 09:40Z, and Bronzetti -
    Crawley (printed 09:10Z) had not begun at 10:28Z - both printed before
    their start, both kept; the legs that really began 09:00-09:10Z are not."""
    printed_at = _utc(str(item.get("printed_at_utc") or created))
    kickoff = item.get("kickoff_utc")
    check = started_by or started_by_printed_kickoff
    return check(
        int(item["sofascore_event_id"]),
        str(kickoff) if isinstance(kickoff, str) and kickoff else None,
        printed_at,
    )


def _late(item: Mapping[str, Any], created: str, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "key": list(leg_key(item)) if kind == "single" else None,
        "sofascore_event_id": int(item["sofascore_event_id"]),
        "match": item.get("match"),
        "kickoff_utc": item.get("kickoff_utc"),
        "printed_at_utc": str(item.get("printed_at_utc") or created),
        # the render of the print history it comes from (F0.1), where known
        **({"printed_in": item["printed_in"]} if item.get("printed_in") else {}),
    }


def carry_over(
    previous: Mapping[str, Any] | None,
    profile_name: str,
    now: datetime,
    is_locked: Callable[[int, str | None], bool],
    pdf_printed: bool = True,
    sports: frozenset[str] | None = None,
    started_by: StartedBy | None = None,
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

    `started_by`: when the match really started (printed_after_its_start); a
    leg whose match had started before the print it comes from is never
    locked - it is listed in `printed_after_start`.
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
            if printed_after_its_start(s, created, started_by):
                out.printed_after_start.append(_late(s, created, "single"))
                continue
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
        if printed_after_its_start(b, created, started_by):
            out.printed_after_start.append(_late(b, created, "builder"))
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

# The print record is append-only (F0.1, plan 2026-10-05 production grade):
# every render also writes printed/<render time>.json, never overwritten.
# 12_printed.json alone was overwritten by every render, and on 10-05 twelve
# tennis legs left the record that way: a rebuild judged them on a stale
# clock as printed after their start, dropped them, the next render rewrote
# 12_printed.json without them, and no later rebuild - with the right
# evidence by then - could see that they had ever been printed. The lock now
# reads the whole history (first_prints); 12_printed.json stays as the
# latest render for every other reader.
PRINTED_HISTORY_DIR = "printed"


def _render_time(doc: Mapping[str, Any]) -> str | None:
    raw = doc.get("pdf_rendered_at_utc") or doc.get("created_at_utc")
    return str(raw) if isinstance(raw, str) and raw else None


def _history_stem(rendered_at: str) -> str:
    return _utc(rendered_at).strftime("%Y%m%dT%H%M%S.%fZ")


def _write_once(directory: Path, stem: str, text: str) -> Path:
    """Write a new file, never over an existing one: the same render twice is
    the same file, another render in the same microsecond gets a suffix."""
    directory.mkdir(parents=True, exist_ok=True)
    for n in range(1000):
        path = directory / (f"{stem}.json" if n == 0 else f"{stem}-{n}.json")
        try:
            with path.open("x", encoding="utf-8") as fh:
                fh.write(text)
            return path
        except FileExistsError:
            if path.read_text(encoding="utf-8") == text:
                return path
    raise RuntimeError(f"{directory}: no free name for {stem}")


def _dump(doc: Mapping[str, Any]) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def _in_history(history: Path, rendered_at: str) -> bool:
    if not history.is_dir():
        return False
    stem = _history_stem(rendered_at)
    return any(p.name == f"{stem}.json" or p.name.startswith(f"{stem}-")
               for p in history.glob("*.json"))


def record_print(run: Path, doc: Mapping[str, Any]) -> Path:
    """Record one PDF render: printed/<render time>.json (append-only) and
    12_printed.json (the latest render). A 12_printed.json whose render is
    not in the history yet - a day printed before F0.1, 10-05 - is seeded
    into it first, under its own pdf_rendered_at_utc, so the render it
    records is never lost to this overwrite. Returns the history file."""
    run = Path(run)
    history = run / PRINTED_HISTORY_DIR
    latest = run / PRINTED_MANIFEST
    if latest.exists():
        try:
            old = json.loads(latest.read_text(encoding="utf-8"))
        except ValueError:
            old = None
        seen = _render_time(old) if isinstance(old, dict) else None
        if isinstance(old, dict) and seen and not _in_history(history, seen):
            _write_once(history, _history_stem(seen), _dump(old))
    rendered = _render_time(doc)
    if not rendered:
        raise ValueError("a print record needs pdf_rendered_at_utc")
    text = _dump(doc)
    path = _write_once(history, _history_stem(rendered), text)
    write_atomic(latest, text)
    return path


def print_history(run: Path) -> list[dict[str, Any]]:
    """Every render of the day, oldest first, each with `printed_in` (its
    file). The history directory, plus 12_printed.json when its render is
    not in it (a day before F0.1: the latest render is all there is, exactly
    as before). Empty: nothing was ever printed."""
    run = Path(run)
    timed: list[tuple[datetime, str, dict[str, Any]]] = []
    untimed: list[dict[str, Any]] = []
    history = run / PRINTED_HISTORY_DIR
    if history.is_dir():
        for path in history.glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            rendered = _render_time(doc)
            name = f"{PRINTED_HISTORY_DIR}/{path.name}"
            if rendered:
                timed.append((_utc(rendered), name, {**doc, "printed_in": name}))
    latest = run / PRINTED_MANIFEST
    if latest.exists():
        doc = json.loads(latest.read_text(encoding="utf-8"))
        rendered = _render_time(doc)
        if not rendered:
            # no render time: a record still (its matches are asked), never
            # a print the lock can date (carry_over refuses it, as before)
            untimed.append({**doc, "printed_in": PRINTED_MANIFEST})
        elif all(t != _utc(rendered) for t, _, _ in timed):
            timed.append((_utc(rendered), PRINTED_MANIFEST,
                          {**doc, "printed_in": PRINTED_MANIFEST}))
    timed.sort(key=lambda x: (x[0], len(x[1]), x[1]))
    return [*untimed, *(doc for _, _, doc in timed)]


# "Had this leg's match started by t?" on whatever clock its sport reads.
LegStartedBy = Callable[[Mapping[str, Any], datetime], bool]


def leg_started_by(started_by: StartedBy | None = None) -> LegStartedBy:
    """A StartedBy for one leg / builder (its event id and printed clock)."""
    check = started_by or started_by_printed_kickoff

    def leg_check(item: Mapping[str, Any], at: datetime) -> bool:
        kickoff = item.get("kickoff_utc")
        return check(
            int(item["sofascore_event_id"]),
            str(kickoff) if isinstance(kickoff, str) and kickoff else None,
            at,
        )

    return leg_check


def _is_measured(item: Mapping[str, Any]) -> bool:
    # Same rule as coupon_sports.is_measured (which imports this module).
    from bet.sofa.confidence import SHEET_SPORTS

    return str(item.get("sport") or "football") not in SHEET_SPORTS


def _any_key(leg: Mapping[str, Any]) -> tuple[Any, ...]:
    # A measured sport's leg is keyed like coupon_sports.sport_key (its side
    # and period); football / tennis like every grader (leg_key).
    if _is_measured(leg):
        from bet.sofa.coupon_sports import sport_key

        return tuple(sport_key(leg))
    return tuple(leg_key(leg))


def _builder_key(b: Mapping[str, Any]) -> tuple[Any, ...]:
    return (int(b["sofascore_event_id"]), tuple(sorted(
        (str(x["market"]), str(x.get("subject") or ""), str(x.get("line")),
         str(x["direction"])) for x in b.get("legs") or [])))


def _dials_of(doc: Mapping[str, Any]) -> dict[str, Any]:
    dials = {k: doc.get(k) for k in DIAL_FIELDS}
    if doc.get("epoch"):
        dials["epoch"] = doc["epoch"]
    return dials


def _first_of_each(
    renders: list[dict[str, Any]],
    items_of: Callable[[dict[str, Any]], list[dict[str, Any]]],
    key_of: Callable[[Mapping[str, Any]], tuple[Any, ...]],
    started: LegStartedBy,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(item as it counts, the render it comes from) per key - first_prints'
    rule."""
    held = [{key_of(x): x for x in items_of(r)} for r in renders]
    order: list[tuple[Any, ...]] = []
    known: set[tuple[Any, ...]] = set()
    for h in held:
        for k in h:
            if k not in known:
                known.add(k)
                order.append(k)
    chosen: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for k in order:
        sample = next(h[k] for h in held if k in h)
        before = [i for i, r in enumerate(renders)
                  if not started(sample, _utc(str(_render_time(r))))]
        retime = False
        if before and k in held[before[-1]]:
            i = before[-1]
            while i > 0 and k in held[i - 1]:
                i -= 1
        elif before:
            after = [j for j in range(before[-1] + 1, len(renders)) if k in held[j]]
            if not after:
                continue  # removed by a render before its start: stays removed
            i, retime = after[0], True
        else:
            i = next(j for j, h in enumerate(held) if k in h)
        render = renders[i]
        item = dict(held[i][k])
        if retime or not item.get("printed_at_utc"):
            item["printed_at_utc"] = str(_render_time(render))
        if retime or not isinstance(item.get("printed_under"), dict):
            item["printed_under"] = _dials_of(render)
        if render.get("printed_in"):
            item["printed_in"] = render["printed_in"]
        chosen.append((item, render))
    return chosen


def first_prints(
    history: list[dict[str, Any]], now: datetime, started: LegStartedBy
) -> dict[str, Any] | None:
    """One print record from the whole history: every leg and builder as it
    was FIRST printed (its printed_at_utc, odds and confidence; the dials of
    that render in printed_under; the render in printed_in), for carry_over
    and coupon_sports.locked_sport_legs to judge exactly as they judge one
    12_printed.json. Renders after `now` are ignored (an as-of replay).

    Which print counts, per leg, with `started(leg, t)` its match's REAL
    start (started_by_evidence; a measured sport's current clocks):

    * The last render made before its match started decides whether it is
      on the coupon - the operator held that PDF at the kickoff. On it: the
      leg counts from the first render of the unbroken run of renders that
      ends there (a leg a pre-start render removed and a later one printed
      again was withdrawn in between; the later print is the bet).
    * Not on it: removed before its start - it stays removed, unless a later
      render (after the start) printed it; that one is carried with its own
      render time, so the lock lists it as printed after the start.
    * No render before its start: the earliest render that holds it, with
      the printed_at_utc it carries (a leg locked from a print older than
      the history - 10-05's seeded record), else that render's time.

    One render (a day before F0.1, or one print so far) is returned as it
    is: the lock behaves exactly as it did on 12_printed.json alone."""
    renders = [d for d in history
               if _render_time(d) and _utc(str(_render_time(d))) <= now]
    if not renders:
        return None
    latest = renders[-1]
    if len(renders) == 1:
        return latest
    singles = _first_of_each(renders, printed_singles, _any_key, started)
    builders = _first_of_each(renders, printed_builders, _builder_key, started)
    legs: dict[LegKey, dict[str, Any]] = {}

    def add_legs(item: Mapping[str, Any], render: Mapping[str, Any],
                 keys: list[LegKey]) -> None:
        by_key = {leg_key(x): x for x in render.get("legs") or []}
        for k in keys:
            if k in by_key and k not in legs:
                legs[k] = {**by_key[k], "printed_at_utc": item["printed_at_utc"],
                           "printed_under": item["printed_under"]}

    for item, render in singles:
        if not _is_measured(item):
            add_legs(item, render, [leg_key(item)])
    for item, render in builders:
        add_legs(item, render, [leg_key(x, item["sofascore_event_id"])
                                for x in item.get("legs") or []])
    return {
        **{k: v for k, v in latest.items()
           if k not in ("singles", "builders", "legs", "printed_in")},
        # every leg carries its own print, so no page cut applies again
        "pdf_max_singles": None,
        "singles": [x for x, _ in singles],
        "builders": [x for x, _ in builders],
        "legs": list(legs.values()),
        "printed_history": [r.get("printed_in") for r in renders],
    }


def history_keys(history: list[dict[str, Any]]) -> set[tuple[Any, ...]]:
    """Every printed single's key (leg_key; a measured sport's sport_key) and
    every printed builder's legs (leg_key) in any render of the history."""
    out: set[tuple[Any, ...]] = set()
    for r in history:
        out |= {_any_key(s) for s in printed_singles(r)}
        for b in printed_builders(r):
            out |= {tuple(leg_key(x, b["sofascore_event_id"]))
                    for x in b.get("legs") or []}
    return out


def history_event_ids(history: list[dict[str, Any]]) -> set[int]:
    """Every match any render of the history printed a single or a builder on."""
    out: set[int] = set()
    for r in history:
        out |= {int(s["sofascore_event_id"]) for s in printed_singles(r)}
        out |= {int(b["sofascore_event_id"]) for b in printed_builders(r)}
    return out


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
    late: set[tuple[Any, ...]] = set()
    locked_keys, locked_fixtures = out.keys, out.builder_fixtures
    for item in [*first.printed_after_start, *second.printed_after_start]:
        ident = (item["kind"], item["sofascore_event_id"], str(item["key"]))
        # Locked from one source (an earlier print), late in the other (a
        # later render of the same leg): it is locked, not late.
        if (item["kind"] == "single" and item["key"] is not None
                and tuple(item["key"]) in locked_keys) or (
                item["kind"] == "builder"
                and int(item["sofascore_event_id"]) in locked_fixtures):
            continue
        if ident not in late:
            late.add(ident)
            out.printed_after_start.append(item)
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
