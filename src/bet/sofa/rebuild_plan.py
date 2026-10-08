"""The rebuild of one day, as a plan: which steps run, in which order, and why.

`scripts/sofa/rebuild_day.py` runs the plan; this module only decides it, so
the decision is testable offline (plan 2026-10-05 production grade, F0.2).

Before F0.2 the rebuild was a manual sequence in `/sofa-rebuild`, and on
2026-10-05 two rebuilds ran on stale prices: CONFIDENCE on an offer older
than its 45-minute limit emptied 08_confidence.json down to the locked legs
(STALE_PRICE everywhere, which reads like a modelling result), and SHADOW
with its default 3 h horizon skipped a hockey game starting at 15:30Z (an
event already on file and starting beyond the horizon is not fetched again),
so its leg went STALE_PRICE too. The plan refreshes a price BEFORE the gate
that would refuse it, with a margin for the rebuild's own duration:

1. freshness, only while the day is live - OFFER when the oldest rung of a
   fixture that can still be bet is older than the CONFIDENCE limit minus
   OFFER_REFRESH_MARGIN; SHADOW (with a horizon to the farthest open start)
   and CS2 when an open event's newest price is older than
   sport_day.MAX_PRICE_AGE minus SPORT_REFRESH_MARGIN, or a SHADOW event
   lagged the latest snapshot because it started beyond the horizon; then
   SPORT_IDENTITY (bridge) after a fresh snapshot;
2. SHEET only when CONFIDENCE would refuse the sheet (a stats-only build of a
   sheet not built under that rule: bet.sofa.epochs.sheet_epoch); COUPON
   (06_coupon.json, the priced selector audit_coupon checks - not the
   coupon) only when it is older than the sheet / vetoes / reads;
3. FIXTURE_CHECK (bridge), CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY,
   PDF, then the audits.

A day that is over (every match started) refreshes nothing - its prices are
historical and every gate downstream refuses them, which is correct - and
the plan says so in its notes.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import epochs, sport_day
from bet.sofa import fixture_status as fs
from bet.sofa import sport_identity as si
from bet.sofa.locked_print import starts_after

# run_offer.py --min-minutes-to-kickoff: a fixture starting sooner is not
# re-priced (CONFIDENCE refuses it at 15 min anyway).
OFFER_MIN_MINUTES_TO_KICKOFF = 20
# Refresh the offer this long BEFORE it reaches CONFIDENCE's limit: OFFER,
# FIXTURE_CHECK and a SHEET take minutes, and the limit is checked when
# CONFIDENCE runs, not when the rebuild starts.
OFFER_REFRESH_MARGIN = timedelta(minutes=15)
# The same for the measured sports' 3 h limit (SPORT_CONFIDENCE).
SPORT_REFRESH_MARGIN = timedelta(minutes=30)
# scripts/sofa/run_shadow.py DEFAULT_HORIZON_H (a test pins the two).
SHADOW_DEFAULT_HORIZON_H = 3.0
# An open SHADOW event whose newest record is this much older than the
# file's newest snapshot was skipped by that snapshot (beyond its horizon).
SHADOW_LAG = timedelta(minutes=15)
# ...and only counts when its own price is at least this old: shadow_daily
# snapshots every ~30 min with the 3 h horizon, so right after a rebuild's
# full-horizon SHADOW the loop's next snapshot made every later event look
# "skipped" while its price was 18 min old (10-05 12:01Z: 13 hockey and 15
# basketball events, a needless SHADOW on every rebuild).
SHADOW_LAG_MIN_AGE = timedelta(minutes=60)
SHADOW_SPORTS = ("hockey", "basketball", "volleyball")
SPORTS = (*SHADOW_SPORTS, "cs2")

PY = "PYTHON"  # replaced by the interpreter in the runner


@dataclass(frozen=True)
class SportState:
    """One measured sport's snapshot of the day, as SPORT_CONFIDENCE reads it."""

    sport: str
    events: int = 0  # day-window events with a price on file
    open_events: int = 0  # ... not yet inside the kickoff margin
    oldest_open_price: datetime | None = None  # min over open events of newest
    farthest_open_kickoff: datetime | None = None
    lagging_events: int = 0  # SHADOW: skipped by the latest snapshot (horizon)
    newest_snapshot: datetime | None = None


@dataclass(frozen=True)
class DayState:
    """What the plan needs to know about the day on disk, at `now`."""

    date: str
    now: datetime
    price_max_age: timedelta
    has_fixtures: bool = True
    has_sheet: bool = True
    has_offer: bool = True
    sheet_epoch: str | None = epochs.STATS_ONLY
    # every 05_sheet.json row rated under the shared-league link rule
    sheet_link_shared: bool = True
    offer_fixtures: int = 0  # fixtures on 04_offer.json with a rung
    open_fixtures: int = 0  # ... a refresh would re-price and CONFIDENCE gate
    oldest_open_rung: datetime | None = None
    newest_rung: datetime | None = None
    sports: Mapping[str, SportState] = field(default_factory=dict)
    has_sport_fixtures: bool = True
    # 06_coupon.json (the priced VALUE selector audit_coupon checks, not the
    # coupon) missing or older than the sheet / vetoes / reads it reads.
    coupon06_stale: bool = False


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]  # PY stands for the interpreter
    reason: str
    # A soft step's FAILED makes the rebuild PARTIAL and does not stop it:
    # no bridge is UNVERIFIED / NOT_IDENTIFIED downstream, nothing refused,
    # and a failed sport snapshot leaves only the sport legs STALE_PRICE.
    soft: bool = False


@dataclass
class Plan:
    date: str
    epoch: str
    sports_on_coupon: bool
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    refusal: str | None = None

    def names(self) -> list[str]:
        return [s.name for s in self.steps]


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)


def _age_min(now: datetime, t: datetime | None) -> str:
    return "none" if t is None else f"{(now - t).total_seconds() / 60:.0f} min"


def _z(t: datetime | None) -> str | None:
    return None if t is None else t.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- observation -------------------------------------------------------------


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def observe_offer(
    fixtures: list[Mapping[str, Any]],
    offers: list[Mapping[str, Any]],
    status: Mapping[int, Mapping[str, Any]],
    now: datetime,
) -> tuple[int, int, datetime | None, datetime | None]:
    """(fixtures with a rung, open ones, oldest open rung, newest rung).

    Open = a refresh with --min-minutes-to-kickoff re-prices it AND
    CONFIDENCE would not refuse it as kicked off: one predicate for both,
    locked_print.starts_after (every clock CONFIDENCE holds, with
    FIXTURE_CHECK's fresh start), and Superbet not reporting it under way.
    Only an open fixture's price can be refreshed and only its age empties a
    coupon. Until 10-05 this also required RESOLVE's two frozen clocks to be
    ahead (run_offer's old filter): a match moved later (Gaubas, 12:30Z ->
    13:30Z) was not open, so its stale price triggered no refresh.
    """
    by_id = {f.get("sofascore_event_id"): f for f in fixtures}
    cutoff = now + timedelta(minutes=OFFER_MIN_MINUTES_TO_KICKOFF)
    priced = open_n = 0
    oldest: datetime | None = None
    newest: datetime | None = None
    for o in offers:
        stamps = [_utc(str(r["fetched_at_utc"])) for r in o.get("rungs") or []
                  if r.get("fetched_at_utc")]
        if not stamps:
            continue
        priced += 1
        top = max(stamps)
        newest = top if newest is None or top > newest else newest
        eid = o.get("sofascore_event_id")
        fx = by_id.get(eid)
        if fx is None or o.get("superbet_started_utc"):
            continue
        entry = status.get(int(eid)) if eid is not None else None
        if not starts_after(fx, o.get("superbet_kickoff_seen_utc"), entry, cutoff):
            continue
        open_n += 1
        low = min(stamps)
        oldest = low if oldest is None or low < oldest else oldest
    if not offers:
        # No offer yet: open is what a first OFFER would price.
        open_n = sum(
            1 for fx in fixtures
            if starts_after(fx, None, status.get(int(fx["sofascore_event_id"]))
                            if fx.get("sofascore_event_id") is not None else None,
                            cutoff))
    return priced, open_n, oldest, newest


def observe_sport(runs_dir: str, sport: str, date: str, now: datetime) -> SportState:
    """The sport's day-window events as SPORT_CONFIDENCE reads them
    (si.snapshot_events, newest price per event, Superbet's start)."""
    start, end = si.day_window(date)
    events = si.snapshot_events(runs_dir, sport, date, now)
    n = open_n = lagging = 0
    oldest: datetime | None = None
    farthest: datetime | None = None
    newest_any: datetime | None = None
    rows: list[tuple[datetime, datetime]] = []
    for ev in events.values():
        if not ev.fetched_at:
            continue
        top = max(_utc(t) for t in ev.fetched_at.values())
        newest_any = top if newest_any is None or top > newest_any else newest_any
        kickoff = _utc(ev.kickoff_utc)
        if not (start <= kickoff < end):
            continue
        n += 1
        if kickoff - now < sport_day.KICKOFF_MARGIN:
            continue
        open_n += 1
        rows.append((kickoff, top))
        oldest = top if oldest is None or top < oldest else oldest
        farthest = kickoff if farthest is None or kickoff > farthest else farthest
    if sport in SHADOW_SPORTS and newest_any is not None:
        horizon = timedelta(hours=SHADOW_DEFAULT_HORIZON_H)
        lagging = sum(1 for kickoff, top in rows
                      if newest_any - top > SHADOW_LAG
                      and now - top >= SHADOW_LAG_MIN_AGE
                      and kickoff - newest_any > horizon)
    return SportState(sport, n, open_n, oldest, farthest, lagging, newest_any)


def observe(runs_dir: str, date: str, now: datetime,
            price_max_age: timedelta) -> DayState:
    """Read the day's artifacts into a DayState (no network, read-only)."""
    run = Path(runs_dir) / date
    fixtures_path, sheet_path, offer_path = (
        run / "02_fixtures.json", run / "05_sheet.json", run / "04_offer.json")
    fixtures = _load_json(fixtures_path) if fixtures_path.exists() else []
    offers = _load_json(offer_path) if offer_path.exists() else []
    sheet_ep: str | None = None
    sheet_link_shared = True
    if sheet_path.exists():
        sheet = _load_json(sheet_path)
        sheet_ep = epochs.sheet_epoch(sheet) if sheet else epochs.STATS_ONLY
        sheet_link_shared = epochs.sheet_link_shared(sheet or [])
    priced, open_n, oldest, newest = observe_offer(
        fixtures, offers, fs.load(run), now)
    sports = ({s: observe_sport(runs_dir, s, date, now) for s in SPORTS}
              if epochs.sports_on_coupon(date, now) else {})
    c06 = run / "06_coupon.json"
    inputs = [p for p in (sheet_path, run / "vetoes.json", run / "reads.json")
              if p.exists()]
    coupon06_stale = not c06.exists() or any(
        p.stat().st_mtime > c06.stat().st_mtime for p in inputs)
    return DayState(
        date=date, now=now, price_max_age=price_max_age,
        has_fixtures=fixtures_path.exists(), has_sheet=sheet_path.exists(),
        has_offer=offer_path.exists(), sheet_epoch=sheet_ep,
        sheet_link_shared=sheet_link_shared,
        offer_fixtures=priced, open_fixtures=open_n,
        oldest_open_rung=oldest, newest_rung=newest, sports=sports,
        has_sport_fixtures=(run / si.FIXTURES_FILE).exists(),
        coupon06_stale=coupon06_stale,
    )


# --- the plan ----------------------------------------------------------------


def _pipeline(date: str, stage: str, run_id: str) -> tuple[str, ...]:
    return (PY, "scripts/sofa/run_pipeline.py", "--date", date, "--only", stage,
            "--run-id", run_id)


def shadow_horizon_h(now: datetime, farthest: datetime | None) -> float:
    """A horizon that reaches the farthest open start (never below the
    default), rounded up to a quarter hour, plus one quarter for the run."""
    if farthest is None:
        return SHADOW_DEFAULT_HORIZON_H
    hours = (farthest - now).total_seconds() / 3600
    return max(SHADOW_DEFAULT_HORIZON_H, math.ceil(hours * 4) / 4 + 0.25)


def build_plan(state: DayState, run_id: str = "rebuild",
               skip_audits: bool = False) -> Plan:
    d, now = state.date, state.now
    stats_only = epochs.stats_only(d, now)
    on_coupon = epochs.sports_on_coupon(d, now)
    plan = Plan(d, epochs.epoch_name(d, now), on_coupon)
    if not state.has_fixtures:
        plan.refusal = ("02_fixtures.json missing: no stage can name a fixture "
                        "- the day needs /sofa-day, not a rebuild")
        return plan
    if not state.has_sheet:
        plan.refusal = ("05_sheet.json missing: nothing to rebuild - the day "
                        "needs /sofa-day")
        return plan

    # 1a. the football / tennis price
    limit = state.price_max_age
    if state.open_fixtures == 0:
        if not state.has_offer:
            plan.refusal = ("04_offer.json missing and no fixture is still open: "
                            "nothing to price it from")
            return plan
        plan.notes.append(
            f"DAY_OVER football/tennis: none of {state.offer_fixtures} priced "
            "fixtures can still be bet - no OFFER refresh; the prices are "
            "historical and every price gate downstream refuses them "
            "(correct behaviour)")
    elif not state.has_offer or state.oldest_open_rung is None:
        plan.steps.append(Step(
            "OFFER", (PY, "scripts/sofa/run_offer.py", "--date", d,
                      "--min-minutes-to-kickoff", str(OFFER_MIN_MINUTES_TO_KICKOFF)),
            "04_offer.json missing"))
    else:
        age = now - state.oldest_open_rung
        trigger = limit - OFFER_REFRESH_MARGIN
        if age > trigger:
            plan.steps.append(Step(
                "OFFER", (PY, "scripts/sofa/run_offer.py", "--date", d,
                          "--min-minutes-to-kickoff",
                          str(OFFER_MIN_MINUTES_TO_KICKOFF)),
                f"oldest price of {state.open_fixtures} open fixtures is "
                f"{_age_min(now, state.oldest_open_rung)} old > "
                f"{trigger.total_seconds() / 60:.0f} min (CONFIDENCE STALE_PRICE "
                f"at {limit.total_seconds() / 60:.0f} min, minus the rebuild's "
                "margin)"))
        else:
            plan.notes.append(
                "OFFER fresh: oldest open price "
                f"{_age_min(now, state.oldest_open_rung)} old <= "
                f"{trigger.total_seconds() / 60:.0f} min")

    # 1b. the measured sports' prices and identities
    bridge_planned = False
    if on_coupon:
        refreshed = False
        shadow = [state.sports.get(s, SportState(s)) for s in SHADOW_SPORTS]
        sport_trigger = sport_day.MAX_PRICE_AGE - SPORT_REFRESH_MARGIN

        def stale(s: SportState) -> bool:
            return (s.oldest_open_price is not None
                    and now - s.oldest_open_price > sport_trigger)

        open_shadow = [s for s in shadow if s.open_events]
        if not open_shadow:
            plan.notes.append(
                "DAY_OVER hockey/basketball/volleyball: no open event on file - "
                "no SHADOW refresh")
        else:
            why = [f"{s.sport} oldest open price {_age_min(now, s.oldest_open_price)}"
                   f" > {sport_trigger.total_seconds() / 60:.0f} min"
                   for s in open_shadow if stale(s)]
            why += [f"{s.sport} {s.lagging_events} open events skipped by the "
                    f"last snapshot (start beyond its {SHADOW_DEFAULT_HORIZON_H:g} h "
                    "horizon)" for s in open_shadow if s.lagging_events]
            if why:
                farthest = max(s.farthest_open_kickoff for s in open_shadow
                               if s.farthest_open_kickoff is not None)
                horizon = shadow_horizon_h(now, farthest)
                plan.steps.append(Step(
                    "SHADOW", (PY, "scripts/sofa/run_shadow.py", "--date", d,
                               "--horizon-h", f"{horizon:g}"),
                    "; ".join(why) + f"; horizon {horizon:g} h reaches the "
                    f"farthest open start {_z(farthest)}", soft=True))
                refreshed = True
            else:
                plan.notes.append("SHADOW fresh: every open event priced within "
                                  f"{sport_trigger.total_seconds() / 60:.0f} min")
        cs2 = state.sports.get("cs2", SportState("cs2"))
        if not cs2.open_events:
            plan.notes.append("DAY_OVER cs2: no open event on file - no CS2 refresh")
        elif stale(cs2):
            plan.steps.append(Step(
                "CS2", _pipeline(d, "CS2", run_id),
                f"cs2 oldest open price {_age_min(now, cs2.oldest_open_price)} > "
                f"{sport_trigger.total_seconds() / 60:.0f} min", soft=True))
            refreshed = True
        else:
            plan.notes.append("CS2 fresh")
        if refreshed or not state.has_sport_fixtures:
            plan.steps.append(Step(
                "BRIDGE", (PY, "scripts/sofa/ensure_bridge.py"),
                "SPORT_IDENTITY and FIXTURE_CHECK ask Sofascore", soft=True))
            bridge_planned = True
            plan.steps.append(Step(
                "SPORT_IDENTITY", _pipeline(d, "SPORT_IDENTITY", run_id),
                "a fresh sport snapshot: pin the new events' Sofascore ids"
                if refreshed else "sport_fixtures.json missing", soft=True))

    # 2. SHEET only when CONFIDENCE would refuse it, or when the rating's
    # link rule of this build is not the one the sheet was rated under
    epoch_stale = stats_only and state.sheet_epoch != epochs.STATS_ONLY
    link_stale = (epochs.link_shared_league(d, now)
                  and not state.sheet_link_shared)
    sheet_rebuilt = epoch_stale or link_stale
    if epoch_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            f"05_sheet.json epoch {state.sheet_epoch!r} is not {epochs.STATS_ONLY!r}:"
            " CONFIDENCE refuses it on a stats-only build"))
    elif link_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json rated under the old link rule: the football rating "
            "links only through a shared league (epochs.link_shared_league)"))
    else:
        plan.notes.append(f"SHEET kept: built under {state.sheet_epoch!r}")
    if not skip_audits and (sheet_rebuilt or state.coupon06_stale):
        plan.steps.append(Step(
            "COUPON", _pipeline(d, "COUPON", run_id),
            "06_coupon.json older than the sheet / vetoes / reads: keeps "
            "audit_coupon in step (the priced selector, not the coupon)",
            soft=True))

    # 3. the coupon
    if stats_only:
        if not bridge_planned:
            plan.steps.append(Step(
                "BRIDGE", (PY, "scripts/sofa/ensure_bridge.py"),
                "FIXTURE_CHECK asks Sofascore", soft=True))
        plan.steps.append(Step(
            "FIXTURE_CHECK", _pipeline(d, "FIXTURE_CHECK", run_id),
            "fresh /event start and status before CONFIDENCE (K12/K14); "
            "no bridge = UNVERIFIED, nothing refused", soft=True))
    plan.steps.append(Step(
        "CONFIDENCE", (PY, "scripts/sofa/run_confidence.py", "--date", d),
        "football / tennis -> 08_confidence.json"))
    if on_coupon:
        plan.steps.append(Step(
            "SPORT_CONFIDENCE", _pipeline(d, "SPORT_CONFIDENCE", run_id),
            "measured sports -> 08_confidence_sports.json"))
    if stats_only:
        plan.steps.append(Step(
            "COUPON_ASSEMBLY", (PY, "scripts/sofa/build_coupon.py", "--date", d),
            "the one coupon -> 11_coupon.json"))
    else:
        plan.notes.append("old epoch: the PDF renders 08_confidence.json, no "
                          "FIXTURE_CHECK / COUPON_ASSEMBLY")
    plan.steps.append(Step(
        "PDF", (PY, "scripts/sofa/build_coupon_pdf.py", "--date", d),
        "KUPON_<d>.pdf + KUPON_<d>.html + 12_printed.json"))
    if skip_audits:
        plan.notes.append("AUDITS SKIPPED (--skip-audits): audit_variants and "
                          "audit_coupon were not run")
    else:
        plan.steps.append(Step(
            "AUDIT_VARIANTS", (PY, "scripts/sofa/audit_variants.py", "--date", d),
            "C1-C3 / U1-U3 on the coupon artifact"))
        plan.steps.append(Step(
            "AUDIT_COUPON", (PY, "scripts/sofa/audit_coupon.py", "--date", d),
            "06_coupon.json audit (the priced selector, not the coupon)"))
    return plan


def state_summary(state: DayState) -> dict[str, Any]:
    """The observation, JSON-ready, for the dry run and the final summary."""
    return {
        "now": _z(state.now),
        "offer_fixtures": state.offer_fixtures,
        "open_fixtures": state.open_fixtures,
        "oldest_open_rung": _z(state.oldest_open_rung),
        "newest_rung": _z(state.newest_rung),
        "sheet_epoch": state.sheet_epoch,
        "sports": {
            k: {"events": s.events, "open": s.open_events,
                "oldest_open_price": _z(s.oldest_open_price),
                "farthest_open_kickoff": _z(s.farthest_open_kickoff),
                "lagging": s.lagging_events}
            for k, s in state.sports.items()
        },
    }
