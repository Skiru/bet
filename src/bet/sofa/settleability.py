"""Can a printed leg be settled - and when was it? (plan 2026-10-05, F0.6)

Three readers share this module:

* ``scripts/sofa/measure_settleability.py`` - for each day, the share of
  printed legs (the official coupon and, on older days, the WARIANT) that had
  no grade by the end of D+``horizon_days`` (UTC), by market family and by
  competition. Read-only.
* ``scripts/sofa/resettle_sweep.py`` - which of the days D-14..D-2 still hold a
  printed leg SETTLE could yet grade (`days_needing_resettle`), so the morning
  re-settle is no longer D-5 alone: statistics of some leagues close days
  later (Raith Rovers - Livingston, 09-25, corners in the DB on 10-03, and
  nobody settled 09-25 again; ANALIZA_WYNIKOW_2026-10-04 3.5).
* ``scripts/sofa/fit_settleability.py`` + CONFIDENCE - a (competition, market
  family) whose printed legs were not graded at D+3 for want of the
  statistic, often enough that the Wilson lower bound clears a threshold, is
  listed in ``config/sofa_settleability.json`` and refused NOT_SETTLEABLE from
  ``epochs.SETTLEABILITY_FROM_UTC`` on. A leg nobody can grade is a tip
  nobody can check, and if the statistic goes missing unevenly the graded
  part is a biased sample of the curve that priced it.

When a leg was first graded: ``sofa_settled_row.settled_at`` is overwritten
by ``regrade_settled.py --apply``, whose log (``runs/sofa/regrade_<ts>.json``)
keeps every ``old_settled_at`` by row id - the earliest of them is the first
grade (`first_graded_times`).
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.confidence import (
    PROFILES,
    is_sheet_sport,
    printed_builders,
    printed_singles,
    profile_artifact_path,
    quantity_family,
)
from bet.sofa.config import config_path
from bet.sofa.locked_print import LegKey, leg_key
from bet.sofa.market_mapper import derived_base
from bet.sofa.players import is_player_metric
from bet.sofa.settle import PRINTED_SETTLED_FILE, REFUND_REASONS
from bet.sofa.sport_confidence import wilson_lo

SETTLEABILITY_FILE = "sofa_settleability.json"
DEFAULT_SETTLEABILITY = config_path(SETTLEABILITY_FILE)
DEFAULT_HORIZON_DAYS = 3
REFUSAL_CODE = "NOT_SETTLEABLE"

# The fit's two dials (fit_settleability.py, docs/sofa/evidence/
# settleability_2026-10-05.md). A cell is refused when at least MIN_LEGS of
# its printed legs were judged and the Wilson 95% lower bound of their
# unsettled-for-want-of-data share is above MAX_UNSETTLED_LOWER: with 8 legs
# that needs >= 3 unsettled (3/8 -> 0.137), with 20 legs >= 5 (0.112), so one
# unlucky match cannot list a league, and the plan's criterion (< 2% of
# printed legs unsettled at D+3) is ten times below the bound.
MIN_LEGS = 8
MAX_UNSETTLED_LOWER = 0.10

# --- why a leg was not graded ---------------------------------------------
# SETTLE's skip reasons (07_settle_skips.json), read per leg: a reason
# "<market>:<gap>" belongs to that market's legs, a bare reason to the event.
DATA_GAP = "DATA_GAP"  # the statistic is missing or inconsistent
NOT_PLAYED = "NOT_PLAYED"  # postponed, cancelled, abandoned, retired, live
IDENTITY = "IDENTITY"  # a subject / player the grader could not place
PROVIDER = "PROVIDER"  # the request failed (breaker, error)
VOID = "VOID"  # moved > 48 h, awarded, an exact line (PUSH): no grade owed
UNKNOWN = "UNKNOWN"  # no reason on record (the day not settled, or no skip)

# run_settle.STAT_GAP_REASONS (the ones --refetch-stat-gaps re-asks for) plus
# the two inconsistencies a later payload repairs. test_settleability checks
# the first set stays inside this one.
DATA_GAP_REASONS = frozenset(
    {
        "NO_STATISTICS",
        "STAT_KEY_ABSENT",
        "ZERO_NOT_RECORDED",
        "CARDS_NOT_RECORDED",
        "INTERNAL_INCONSISTENT",
        "NO_INCIDENTS",
    }
)
NOT_PLAYED_REASONS = frozenset(
    {
        "NOT_FINISHED",
        "EVENT_NOT_FINISHED",
        "FINISHED_ABNORMALLY",
        "POSTPONED",
        "CANCELED",
        "ABANDONED",
        "NO_EVENT",
        "NO_FIXTURE",
    }
)
IDENTITY_REASONS = frozenset(
    {
        "SUBJECT_NOT_MATCHED",
        "DERIVED_SUBJECT",
        "PLAYER_NOT_MATCHED",
        "PLAYER_DID_NOT_PLAY",
        "PLAYER_AMBIGUOUS",
        "NO_LINEUPS",
    }
)
VOID_REASONS = frozenset(REFUND_REASONS | {"PUSH"})
# Worth another SETTLE: a statistic that may still arrive, a match that may
# still finish or be found moved beyond the void window, a failed request,
# or a day nobody settled. A cancelled match or an unplaceable subject is
# not (unfinished_reason: "Only NOT_FINISHED is worth re-running SETTLE for";
# a postponed one too - SETTLE decides MOVED_BEYOND_VOID on it).
RESETTLE_REASONS = DATA_GAP_REASONS | {
    "NOT_FINISHED", "EVENT_NOT_FINISHED", "POSTPONED", "PROVIDER_ERROR"}


def reason_class(reason: str | None) -> str:
    """The class of one SETTLE skip reason (the part after a ``market:``)."""
    if not reason:
        return UNKNOWN
    bare = reason.split(":")[-1]
    if bare in VOID_REASONS:
        return VOID
    if bare in DATA_GAP_REASONS:
        return DATA_GAP
    if bare in NOT_PLAYED_REASONS:
        return NOT_PLAYED
    if bare in IDENTITY_REASONS or bare.startswith("PLAYER_"):
        return IDENTITY
    if bare == "PROVIDER_ERROR":
        return PROVIDER
    return UNKNOWN


def settle_family(market: str) -> str:
    """The market family a settleability cell is keyed on.

    The quantity (confidence.quantity_family: corners_1h_for is corners) -
    a league that publishes no corners publishes none for a half either. A
    player prop is its own family: it is graded from /lineups, not from the
    statistics a team market needs, so its gaps are a different fact."""
    if is_player_metric(market):
        return "player_props"
    family = quantity_family(market)
    base = derived_base(market)
    if family == market and base is not None:
        family = quantity_family(base)
    return family


# --- the printed legs of a day --------------------------------------------


@dataclass
class PrintedLeg:
    run_date: str
    key: LegKey
    sport: str
    competition_id: int | None
    competition_name: str
    profiles: set[str] = field(default_factory=set)

    @property
    def market(self) -> str:
        return self.key[1]

    @property
    def family(self) -> str:
        return settle_family(self.key[1])


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_fixtures(run_dir: Path) -> dict[int, dict[str, Any]]:
    doc = _read_json(Path(run_dir) / "02_fixtures.json")
    if not isinstance(doc, list):
        return {}
    return {
        int(f["sofascore_event_id"]): f
        for f in doc
        if isinstance(f, dict) and f.get("sofascore_event_id") is not None
    }


def printed_legs(
    run_dir: Path, run_date: str, fixtures: Mapping[int, Mapping[str, Any]]
) -> list[PrintedLeg]:
    """Every football / tennis rung a profile's PDF printed for the day - the
    same lists SETTLE grades (run_settle.printed_legs: printed_singles and
    the legs of printed_builders, measured sports left to sport_coupon)."""
    out: dict[LegKey, PrintedLeg] = {}
    for profile in PROFILES.values():
        doc = _read_json(profile_artifact_path(Path(run_dir), profile))
        if not isinstance(doc, dict):
            continue
        raw: list[tuple[dict[str, Any], LegKey]] = []
        for s in printed_singles(doc):
            if is_sheet_sport(s):
                raw.append((s, leg_key(s)))
        for b in printed_builders(doc):
            eid = int(b["sofascore_event_id"])
            for x in b.get("legs") or []:
                if is_sheet_sport({**x, "sport": x.get("sport", b.get("sport"))}):
                    raw.append(({**x, "sofascore_event_id": eid}, leg_key(x, eid)))
        for leg, key in raw:
            fx = fixtures.get(key[0]) or {}
            if key not in out:
                cid = fx.get("competition_id")
                out[key] = PrintedLeg(
                    run_date=run_date,
                    key=key,
                    sport=str(leg.get("sport") or fx.get("sport") or "football"),
                    competition_id=int(cid) if isinstance(cid, int) else None,
                    competition_name=str(
                        fx.get("competition_name") or leg.get("competition") or "?"
                    ),
                )
            out[key].profiles.add(profile.name)
    return [out[k] for k in sorted(out, key=str)]


# --- when each leg was graded ---------------------------------------------


def _utc(raw: str) -> datetime:
    at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def first_graded_times(regrade_logs: Iterable[Any]) -> dict[int, datetime]:
    """{sofa_settled_row.id: earliest old_settled_at} over regrade logs (a
    list of changes; the --moved-void log is a dict and moves no grade)."""
    out: dict[int, datetime] = {}
    for log in regrade_logs:
        if not isinstance(log, list):
            continue
        for change in log:
            if not isinstance(change, dict):
                continue
            rid, old = change.get("id"), change.get("old_settled_at")
            if not isinstance(rid, int) or not isinstance(old, str):
                continue
            at = _utc(old)
            if rid not in out or at < out[rid]:
                out[rid] = at
    return out


def load_regrade_logs(runs_dir: Path) -> list[Any]:
    return [_read_json(p) for p in sorted(Path(runs_dir).glob("regrade_*.json"))]


@dataclass(frozen=True)
class Grade:
    outcome: str
    graded_at: datetime | None


def db_grades(
    conn: sqlite3.Connection,
    run_date: str,
    event_ids: set[int],
    first_times: Mapping[int, datetime],
) -> dict[LegKey, Grade]:
    """The grade of each key of these events: the day's own row, else the
    same key filed under another live date (audit_settlement.settled_by_key:
    the key is UNIQUE without run_date) - never a cache-replay row."""
    out: dict[LegKey, Grade] = {}
    ids = sorted(event_ids)
    own: dict[LegKey, Grade] = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        for row in conn.execute(
            "SELECT id, run_date, sofascore_event_id, market, subject, line, "
            "direction, outcome, settled_at FROM sofa_settled_row "
            "WHERE run_date != 'cache-calibration' "
            f"AND sofascore_event_id IN ({marks})",
            chunk,
        ):
            rid, rdate, eid, market, subject, line, direction, outcome, at = row
            key: LegKey = (int(eid), str(market), str(subject or ""), float(line),
                           str(direction))
            graded = _utc(str(at)) if at else None
            first = first_times.get(int(rid))
            if first is not None and (graded is None or first < graded):
                graded = first
            grade = Grade(str(outcome), graded)
            (own if rdate == run_date else out)[key] = grade
    out.update(own)
    return out


def printed_file_grades(run_dir: Path) -> dict[LegKey, Grade]:
    """07_settled_printed.json (A4): grades of printed legs without a sheet row."""
    doc = _read_json(Path(run_dir) / PRINTED_SETTLED_FILE)
    out: dict[LegKey, Grade] = {}
    for r in doc if isinstance(doc, list) else []:
        if not isinstance(r, dict):
            continue
        try:
            key = leg_key(r)
        except (KeyError, TypeError, ValueError):
            continue
        at = r.get("settled_at")
        when = _utc(at) if isinstance(at, str) else None
        out[key] = Grade(str(r.get("outcome")), when)
    return out


def skip_reasons(skips_doc: Mapping[str, Any] | None) -> dict[int, dict[str, int]]:
    """{event: {reason: n}} from a day's 07_settle_skips.json."""
    out: dict[int, dict[str, int]] = {}
    for entry in (skips_doc or {}).get("skipped_events") or []:
        if isinstance(entry, Mapping) and entry.get("sofascore_event_id") is not None:
            out[int(entry["sofascore_event_id"])] = {
                str(k): int(v) for k, v in (entry.get("skipped") or {}).items()
            }
    return out


def leg_reason(market: str, reasons: Mapping[str, int] | None) -> str | None:
    """The reason SETTLE gave for this leg's event: the market's own
    ``market:GAP`` first, a void / event-level reason next, else None."""
    if not reasons:
        return None
    for reason in reasons:
        if reason.split(":")[-1] in REFUND_REASONS:
            return reason
    own = [r for r in reasons if ":" in r and r.split(":", 1)[0] == market]
    if own:
        return own[0]
    bare = [r for r in reasons if ":" not in r]
    if bare:
        # The most frequent bare reason of the event.
        return max(bare, key=lambda r: reasons[r])
    return None


# --- one leg's state ------------------------------------------------------

GRADED_BY_HORIZON = "GRADED_BY_HORIZON"
GRADED_LATER = "GRADED_LATER"
UNGRADED = "UNGRADED"
VOIDED = "VOIDED"


@dataclass(frozen=True)
class LegState:
    leg: PrintedLeg
    status: str  # GRADED_BY_HORIZON / GRADED_LATER / UNGRADED / VOIDED
    reason: str | None  # SETTLE's current reason for an ungraded / void leg
    reason_class: str
    graded_at: datetime | None
    # A leg graded after the horizon: PROCESS when the statistics it was
    # graded from were already in the cache before the horizon (nobody
    # settled the day again - 09-25..09-27), DATA when they were fetched only
    # after it (the feed closed late, or nobody asked; the two cannot be told
    # apart from the cache, which keeps only the last fetch).
    late_cause: str | None = None

    @property
    def unsettled_at_horizon(self) -> bool:
        return self.status in (GRADED_LATER, UNGRADED)


def horizon_end(run_date: str, horizon_days: int = DEFAULT_HORIZON_DAYS) -> datetime:
    """The end of day D+horizon_days, UTC (D+3: 00:00Z of D+4)."""
    day = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=UTC)
    return day + timedelta(days=horizon_days + 1)


LATE_PROCESS = "PROCESS"
LATE_DATA = "DATA"


def classify(
    legs: Iterable[PrintedLeg],
    grades: Mapping[LegKey, Grade],
    reasons: Mapping[int, Mapping[str, int]],
    horizon: datetime,
    stats_fetched_at: Mapping[int, datetime] | None = None,
) -> list[LegState]:
    """Each printed leg: graded by the horizon, graded later, still ungraded,
    or void (refund / push - no grade is owed). A graded row whose time is
    unknown counts as graded by the horizon. ``stats_fetched_at`` (the
    event's sofa_event_stats.fetched_at) splits a late grade into PROCESS /
    DATA; without it a late grade is DATA."""
    fetched = stats_fetched_at or {}
    out: list[LegState] = []
    for leg in legs:
        ev_reasons = reasons.get(leg.key[0])
        reason = leg_reason(leg.market, ev_reasons)
        cls = reason_class(reason)
        # A refund overrides any row, as in audit_settlement.coupon_settled_by_key.
        if reason is not None and reason.split(":")[-1] in REFUND_REASONS:
            out.append(LegState(leg, VOIDED, reason, VOID, None))
            continue
        grade = grades.get(leg.key)
        if grade is not None and grade.outcome in ("WIN", "LOSS", "PUSH"):
            late = grade.graded_at is not None and grade.graded_at >= horizon
            if not late:
                out.append(LegState(leg, GRADED_BY_HORIZON, None, "", grade.graded_at))
                continue
            at = fetched.get(leg.key[0])
            cause = LATE_PROCESS if at is not None and at < horizon else LATE_DATA
            out.append(LegState(leg, GRADED_LATER, None, "", grade.graded_at, cause))
            continue
        if cls == VOID:
            out.append(LegState(leg, VOIDED, reason, VOID, None))
            continue
        out.append(LegState(leg, UNGRADED, reason, cls, None))
    return out


def day_states(
    conn: sqlite3.Connection,
    runs_dir: Path,
    run_date: str,
    first_times: Mapping[int, datetime],
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> list[LegState]:
    """Every printed leg of one day with its state (read-only)."""
    run_dir = Path(runs_dir) / run_date
    fixtures = load_fixtures(run_dir)
    legs = printed_legs(run_dir, run_date, fixtures)
    if not legs:
        return []
    grades = db_grades(conn, run_date, {lg.key[0] for lg in legs}, first_times)
    for key, grade in printed_file_grades(run_dir).items():
        grades.setdefault(key, grade)
    skips = _read_json(run_dir / "07_settle_skips.json")
    reasons = skip_reasons(skips if isinstance(skips, dict) else None)
    return classify(
        legs, grades, reasons, horizon_end(run_date, horizon_days),
        stats_fetch_times(conn, {lg.key[0] for lg in legs}),
    )


def stats_fetch_times(
    conn: sqlite3.Connection, event_ids: set[int]
) -> dict[int, datetime]:
    """{event: sofa_event_stats.fetched_at} - the last fetch of its statistics."""
    out: dict[int, datetime] = {}
    ids = sorted(event_ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        for eid, at in conn.execute(
            "SELECT sofascore_event_id, fetched_at FROM sofa_event_stats "
            f"WHERE sofascore_event_id IN ({marks})",
            chunk,
        ):
            if at:
                out[int(eid)] = _utc(str(at))
    return out


# --- the measurement's tables ---------------------------------------------


@dataclass
class Tally:
    printed: int = 0
    voided: int = 0
    graded_by_horizon: int = 0
    graded_later: int = 0
    graded_later_process: int = 0
    ungraded: int = 0
    ungraded_by_class: dict[str, int] = field(default_factory=dict)
    # Unsettled at the horizon for want of the statistic: graded later from
    # statistics fetched after the horizon (LATE_DATA), or still ungraded
    # with a DATA_GAP reason. The settleability fit counts these.
    data_unsettled: int = 0
    # The legs the fit judges: graded (by the horizon or later) or ungraded
    # for want of data - never void, and never ungraded for a reason that
    # says nothing about the feed (not played, identity, provider, none).
    judged: int = 0

    def add(self, state: LegState) -> None:
        self.printed += 1
        if state.status == VOIDED:
            self.voided += 1
            return
        if state.status == GRADED_BY_HORIZON:
            self.graded_by_horizon += 1
            self.judged += 1
            return
        if state.status == GRADED_LATER:
            self.graded_later += 1
            self.judged += 1
            if state.late_cause == LATE_PROCESS:
                self.graded_later_process += 1
            else:
                self.data_unsettled += 1
            return
        self.ungraded += 1
        self.ungraded_by_class[state.reason_class] = (
            self.ungraded_by_class.get(state.reason_class, 0) + 1
        )
        if state.reason_class == DATA_GAP:
            self.data_unsettled += 1
            self.judged += 1

    @property
    def due(self) -> int:
        """Legs that owed a grade (void ones did not)."""
        return self.printed - self.voided

    @property
    def unsettled_at_horizon(self) -> int:
        return self.graded_later + self.ungraded

    def as_dict(self) -> dict[str, Any]:
        due = self.due
        return {
            "printed": self.printed,
            "voided": self.voided,
            "due": due,
            "graded_by_horizon": self.graded_by_horizon,
            "graded_later": self.graded_later,
            "graded_later_process": self.graded_later_process,
            "ungraded_now": self.ungraded,
            "ungraded_by_class": dict(sorted(self.ungraded_by_class.items())),
            "unsettled_at_horizon": self.unsettled_at_horizon,
            "unsettled_share": (
                round(self.unsettled_at_horizon / due, 4) if due else None),
            "unsettled_wilson_lo": round(wilson_lo(self.unsettled_at_horizon, due), 4)
            if due else None,
            "judged": self.judged,
            "data_unsettled": self.data_unsettled,
            "data_unsettled_wilson_lo": round(
                wilson_lo(self.data_unsettled, self.judged), 4
            ) if self.judged else None,
        }


def tally_by(
    states: Iterable[LegState], group: Any
) -> dict[Any, Tally]:
    out: dict[Any, Tally] = defaultdict(Tally)
    for s in states:
        out[group(s)].add(s)
    return dict(out)


# --- the fit ----------------------------------------------------------------


def cell_key(competition_id: int | None, market: str) -> tuple[int | None, str]:
    return competition_id, settle_family(market)


def fit_refusals(
    states: Iterable[LegState],
    *,
    min_legs: int = MIN_LEGS,
    max_unsettled_lower: float = MAX_UNSETTLED_LOWER,
) -> list[dict[str, Any]]:
    """The (competition, family) cells to refuse: judged >= min_legs and the
    Wilson 95% lower bound of data_unsettled / judged > max_unsettled_lower.
    A leg without a competition id is never listed (nothing to key it on)."""
    names: dict[int, str] = {}
    sports: dict[int, str] = {}
    cells: dict[tuple[int | None, str], Tally] = defaultdict(Tally)
    for s in states:
        cid = s.leg.competition_id
        if cid is None:
            continue
        names.setdefault(cid, s.leg.competition_name)
        sports.setdefault(cid, s.leg.sport)
        cells[cell_key(cid, s.leg.market)].add(s)
    out: list[dict[str, Any]] = []
    ordered = sorted(cells.items(), key=lambda kv: (str(kv[0][0]), kv[0][1]))
    for (cid, family), t in ordered:
        if cid is None or t.judged < min_legs:
            continue
        lo = wilson_lo(t.data_unsettled, t.judged)
        if lo <= max_unsettled_lower:
            continue
        out.append(
            {
                "competition_id": cid,
                "competition_name": names.get(cid, "?"),
                "sport": sports.get(cid, "?"),
                "family": family,
                "judged": t.judged,
                "data_unsettled": t.data_unsettled,
                "share": round(t.data_unsettled / t.judged, 4),
                "wilson_lo": round(lo, 4),
            }
        )
    return out


# --- the gate ---------------------------------------------------------------


@dataclass(frozen=True)
class Settleability:
    """The fitted list of (competition, family) cells CONFIDENCE refuses."""

    refused: frozenset[tuple[int, str]] = frozenset()
    fitted_before: str | None = None
    # False when no file was installed: the gate refuses nothing, and
    # CONFIDENCE says so (SETTLEABILITY_NOT_FITTED) rather than open silently.
    fitted: bool = False

    @staticmethod
    def load(path: Path | str | None = None) -> Settleability:
        """The installed list (DEFAULT_SETTLEABILITY, read at call time); an
        absent file is an empty, unfitted list, an unreadable one an error."""
        p = Path(path) if path is not None else DEFAULT_SETTLEABILITY
        if not p.exists():
            return Settleability()
        doc = json.loads(p.read_text(encoding="utf-8"))
        cells = frozenset(
            (int(e["competition_id"]), str(e["family"]))
            for e in doc.get("refused") or []
        )
        return Settleability(
            cells, (doc.get("fitted_from") or {}).get("before"), fitted=True)

    def refuses(self, competition_id: object, market: str) -> bool:
        if not isinstance(competition_id, int):
            return False
        return (competition_id, settle_family(market)) in self.refused


# --- the sweep --------------------------------------------------------------


def resettle_worthy(state: LegState) -> bool:
    """Could another SETTLE of the day still grade this leg?"""
    if state.status != UNGRADED:
        return False
    if state.reason is None:
        return True  # nothing on record: the day, or the event, was never reached
    return state.reason.split(":")[-1] in RESETTLE_REASONS


def days_needing_resettle(
    states_by_day: Mapping[str, Iterable[LegState]],
) -> dict[str, int]:
    """{day: printed legs SETTLE could still grade}, days with none left out."""
    out: dict[str, int] = {}
    for day in sorted(states_by_day):
        n = sum(1 for s in states_by_day[day] if resettle_worthy(s))
        if n:
            out[day] = n
    return out


def sweep_range(today: str, back_from: int = 14, back_to: int = 2) -> tuple[str, str]:
    """(D-back_from, D-back_to) as dates."""
    d = datetime.strptime(today, "%Y-%m-%d")
    return (
        (d - timedelta(days=back_from)).strftime("%Y-%m-%d"),
        (d - timedelta(days=back_to)).strftime("%Y-%m-%d"),
    )


def date_range(start: str, end: str) -> list[str]:
    a = datetime.strptime(start, "%Y-%m-%d")
    b = datetime.strptime(end, "%Y-%m-%d")
    out = []
    while a <= b:
        out.append(a.strftime("%Y-%m-%d"))
        a += timedelta(days=1)
    return out


# A bridge whose tab last pulled longer ago than this is not serving: the
# sweep's --refetch-stat-gaps would only collect PROVIDER_ERROR skips.
MAX_BRIDGE_PULL_AGE_S = 60.0


def bridge_ready(health: Mapping[str, Any] | None) -> tuple[bool, str]:
    """Is the bridge's /health answer good enough to refetch? (ok, why not)."""
    if health is None:
        return False, "bridge server not listening"
    age = health.get("last_pull_age_s")
    if age is None:
        return False, "no browser tab has ever polled the bridge"
    if float(age) > MAX_BRIDGE_PULL_AGE_S:
        return False, f"last browser poll {float(age):.0f}s ago"
    return True, ""


def sweep_verdict(settle_codes: Mapping[str, int], breaker_open: bool,
                  bridge_ok: bool, regrade_code: int | None) -> str:
    """OK / PARTIAL / FAILED for a sweep.

    run_settle's PARTIAL (1) is the normal shape of a settled day (some rows
    always skip), so it is not a sweep failure; a FAILED day (2), the
    breaker, no bridge or a failed regrade (2) make the sweep PARTIAL; every
    planned day FAILED makes it FAILED."""
    if not bridge_ok:
        return "PARTIAL"
    if settle_codes and all(c == 2 for c in settle_codes.values()):
        return "FAILED"
    if any(c == 2 for c in settle_codes.values()) or breaker_open:
        return "PARTIAL"
    if regrade_code == 2:
        return "PARTIAL"
    return "OK"
