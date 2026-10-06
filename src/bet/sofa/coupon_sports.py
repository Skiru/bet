"""The measured sports' legs on the one coupon (plan 2026-10-05, part 5, F7).

run_sport_confidence.py writes runs/sofa/<d>/08_confidence_sports.json -
hockey, basketball, volleyball and CS2 legs with a confidence from the
statistics (score_model / cs2_engine, calibrated without prices) and the
coupon's price filters. build_coupon.py puts them on 11_coupon.json beside
football and tennis. This module is what that needs:

* `normalize` - the reader-facing names every 11 reader expects
  (`market` = family, `direction` = side, `offered_odds`, `leg_ev`), the
  native fields kept, so sport_day.grade_legs grades the leg unchanged;
* `apply_reads` - vetoes / reads (reads.json, LegRead with `period`): NO_BET
  and WATCH remove, into removed_by_reads, like a football leg;
* `locked_sport_legs` - legs the last printed coupon carried whose match has
  started: kept as printed (locked_print's rule, for sport legs);
* `grade` - each leg graded at its printed price by sport_day.grade_legs
  from the sport's settled.json, after checking the settled record is the
  match identity pinned before the match (sport_fixtures.json); a different
  id is NOT_GRADED:ID_CHANGED.

Sport legs never reach sofa_settled_row or fit_confidence.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.sofa import sport_day as sd
from bet.sofa.confidence import SHEET_SPORTS, too_close_to_kickoff
from bet.sofa.contracts import LegRead, Veto
from bet.sofa.locked_print import printed_after_its_start, started_by_printed_kickoff
from bet.sofa.veto import read_refusal, veto_matches

MEASURED_SPORTS = ("hockey", "basketball", "volleyball", "cs2")
SPORT_FIXTURES_FILE = "sport_fixtures.json"

SportKey = tuple[int, str, int, str, float | None, str]


def is_measured(leg: Mapping[str, Any]) -> bool:
    return str(leg.get("sport") or "football") not in SHEET_SPORTS


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def normalize(leg: Mapping[str, Any]) -> dict[str, Any]:
    """The leg with the names 11's readers use, native fields kept."""
    odds = float(leg["odds"])
    out = dict(leg)
    out.setdefault("market", leg["family"])
    out.setdefault("direction", leg["side"])
    out.setdefault("subject", leg.get("subject") or "")
    out["offered_odds"] = odds
    out["leg_ev"] = round(float(leg["confidence"]) * odds - 1.0, 4)
    out.setdefault("sample_size", leg.get("sample_n"))
    out.setdefault("unfitted_constants", [])
    out["display_market"] = display_market(leg)
    # Selected under the stats-only rule (SPORT_CONFIDENCE exists only in
    # that epoch); a locked leg keeps the epoch of the build that printed it.
    out.setdefault("epoch", "stats_only")
    return out


def display_market(leg: Mapping[str, Any]) -> str:
    """How the PDF names a sport leg's market: the family, the team instead
    of T1 / T2 (T1 is the first name of `match`), the period / map."""
    teams = str(leg.get("match") or "").split(" - ", 1)
    def team(code: str) -> str:
        if code == "T1" and teams:
            return teams[0]
        if code == "T2" and len(teams) > 1:
            return teams[1]
        return code
    label = str(leg.get("family"))
    subject = str(leg.get("subject") or "")
    if subject:
        label += f" ({team(subject)})"
    if leg.get("sport") == "cs2" and leg.get("map_nr"):
        label += f", mapa {leg['map_nr']}"
    elif int(leg.get("period") or 0):
        label += f", okres {leg['period']}"
    side = str(leg.get("side") or "")
    if side in ("T1", "T2"):
        label += f" — {team(side)}"
    return label


def display_line(leg: Mapping[str, Any]) -> str:
    """How the PDF writes a leg's line. A measured sport's handicap `line` is
    TEAM 1's handicap (shadow.SportLine, cs2.Cs2Line - the settle reads it so),
    so the side T2 holds the opposite one: 10-05, "Herlev Eagles -1.5 T2"
    @1.30 printed beside Superbet's "Herlev Eagles (1.5)" - the priced and
    graded outcome was Herlev +1.5, and "Esbjerg Energy (-0.5)" @1.70 was a
    different live bet from the printed Esbjerg leg (verifier). The handicap
    is written signed, as the side's own."""
    line = leg.get("line")
    if line is None:
        return ""
    family = str(leg.get("family") or leg.get("market") or "")
    side = str(leg.get("side") or leg.get("direction") or "")
    if is_measured(leg) and family.endswith("handicap") and side in ("T1", "T2"):
        own = float(line) if side == "T1" else -float(line)
        return f"{own:+g}"
    return f"{line}"


def sport_key(leg: Mapping[str, Any]) -> SportKey:
    line = leg.get("line")
    return (
        int(leg["sofascore_event_id"]),
        str(leg.get("family") or leg.get("market")),
        int(leg.get("period") or 0),
        str(leg.get("subject") or ""),
        float(line) if line is not None else None,
        str(leg.get("side") or leg.get("direction")),
    )


def apply_reads(
    legs: Iterable[dict[str, Any]], vetoes: list[Veto], reads: list[LegRead]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """(kept, removed_by_reads, vetoed). A veto or a NO_BET read removes, a
    WATCH removes (the coupon honours it); the read rides on the leg."""
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    vetoed = 0
    for leg in legs:
        k = sport_key(leg)
        args = dict(sofascore_event_id=k[0], market=k[1], subject=k[3],
                    line=k[4], direction=k[5])
        if any(veto_matches(v, **args) for v in vetoes):  # type: ignore[arg-type]
            vetoed += 1
            continue
        covering = [r for r in reads if veto_matches(r, **args, period=k[2])]  # type: ignore[arg-type]
        if covering:
            leg = {**leg, "reads": [
                {"verdict": r.verdict, "author": r.author, "reason": r.reason}
                for r in covering]}
        refusal = read_refusal(covering)
        if refusal is not None:
            verdict = "NO_BET" if refusal == "READ_NO_BET" else "WATCH"
            removed.append({**leg, "refusal": refusal, "reason": "+".join(
                sorted({r.author for r in covering if r.verdict == verdict}))})
            continue
        kept.append(leg)
    return kept, removed, vetoed


FreshClock = Callable[[Mapping[str, Any]], list[datetime]]


def fresh_kickoffs(runs_dir: Path, date: str, at: datetime) -> FreshClock:
    """A leg's current start clocks: Superbet's in the latest snapshot of
    its event and Sofascore's from SPORT_IDENTITY (sport_fixtures.json) -
    replaced by FIXTURE_CHECK's fresh read of the pinned id where there is
    one (fixture_status.json, K12, as SPORT_CONFIDENCE's gate reads it).
    A printed kickoff goes stale when Superbet moves the match; the lock and
    the started check must read the clock as it is now (review 2026-10-05)."""
    from bet.sofa import fixture_status as fs
    from bet.sofa import sport_identity as si

    events: dict[str, dict[str, Any]] = {}
    starts: dict[str, str] = {}
    status = fs.load(Path(runs_dir) / date)
    path = Path(runs_dir) / date / SPORT_FIXTURES_FILE
    if path.exists():
        for f in json.loads(path.read_text(encoding="utf-8")).get("fixtures") or []:
            sid = f.get("sofascore_event_id")
            fresh = (fs.refreshed_start(status.get(int(sid)))
                     if sid is not None else None)
            start = fresh or f.get("sofascore_start_utc")
            if start:
                starts[str(f["superbet_event_id"])] = str(start)

    def clocks(leg: Mapping[str, Any]) -> list[datetime]:
        sport = str(leg.get("sport"))
        if sport not in events:
            try:
                events[sport] = si.snapshot_events(str(runs_dir), sport, date, at)
            except (OSError, ValueError):
                events[sport] = {}
        out: list[datetime] = []
        ev = events[sport].get(str(leg.get("superbet_event_id")))
        if ev is not None and getattr(ev, "kickoff_utc", None):
            out.append(_utc(str(ev.kickoff_utc)))
        if str(leg.get("superbet_event_id")) in starts:
            out.append(_utc(starts[str(leg["superbet_event_id"])]))
        return out

    return clocks


def started(leg: Mapping[str, Any], now: datetime,
            fresh: FreshClock | None = None) -> bool:
    """Inside the kickoff margin on the current clocks (the printed one when
    no current clock is known)."""
    clocks = fresh(leg) if fresh is not None else []
    if not clocks:
        clocks = [_utc(str(leg["kickoff_utc"]))]
    return too_close_to_kickoff(clocks, now)


def started_by_clock(
    fresh: FreshClock | None = None,
) -> Callable[[Mapping[str, Any], datetime], bool]:
    """"Had this sport leg's match started by t": its current clocks (the
    earliest), else its printed one - the lock's "printed before its start"
    for a measured sport (locked_sport_legs, locked_print.first_prints)."""

    def check(leg: Mapping[str, Any], at: datetime) -> bool:
        clocks = fresh(leg) if fresh is not None else []
        if clocks:
            return min(clocks) <= at
        kickoff = leg.get("kickoff_utc")
        return started_by_printed_kickoff(
            int(leg["sofascore_event_id"]),
            str(kickoff) if isinstance(kickoff, str) and kickoff else None, at)

    return check


def locked_sport_legs(
    printed: Mapping[str, Any] | None, now: datetime,
    fresh: FreshClock | None = None,
    printed_after_start: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The measured-sport singles of the last printed coupon whose match has
    started (or is inside the kickoff margin) at `now` on the current clocks:
    kept as printed. A leg whose match had started before that print (its
    current clock, else the printed one, at or before the print) is never
    locked; it is appended to `printed_after_start` when one is given."""
    if not printed:
        return []
    created = str(printed.get("pdf_rendered_at_utc")
                  or printed.get("created_at_utc") or "")
    if not created or _utc(created) > now:
        return []
    dials = {k: printed.get(k) for k in ("confidence_floor", "min_ev", "max_overround")}
    if printed.get("epoch"):
        dials["epoch"] = printed["epoch"]
    leg_started = started_by_clock(fresh)
    out = []
    for leg in printed.get("singles") or []:
        if not is_measured(leg):
            continue
        if not started(leg, now, fresh):
            continue
        # Its match had started before that print (PDF rendered after the
        # start): never a bet made before the start, never locked.
        def started_by(event_id: int, printed_kickoff: str | None, at: datetime,
                       leg: Mapping[str, Any] = leg) -> bool:
            return leg_started(leg, at)

        if printed_after_its_start(leg, created, started_by):
            if printed_after_start is not None:
                printed_after_start.append({
                    "kind": "single", "sport": leg.get("sport"),
                    "sofascore_event_id": int(leg["sofascore_event_id"]),
                    "key": list(sport_key(leg)),
                    "match": leg.get("match"),
                    "kickoff_utc": leg.get("kickoff_utc"),
                    "printed_at_utc": str(leg.get("printed_at_utc") or created),
                })
            continue
        out.append({
            **{k: v for k, v in leg.items() if k not in ("position", "block")},
            "locked": True,
            "printed_at_utc": leg.get("printed_at_utc", created),
            "printed_under": leg.get("printed_under", dials),
        })
    return out


def pinned_ids(run_dir: Path) -> dict[str, int]:
    """{superbet_event_id: sofascore_event_id} identified before the match."""
    path = Path(run_dir) / SPORT_FIXTURES_FILE
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(f["superbet_event_id"]): int(f["sofascore_event_id"])
        for f in doc.get("fixtures") or []
        if f.get("sofascore_event_id") is not None
        and f.get("status", "IDENTIFIED") == "IDENTIFIED"
    }


def pinned_seed(runs_dir: str, sport: str, date: str) -> dict[str, dict[str, Any]]:
    """{superbet id: a prior record} from SPORT_IDENTITY's sport_fixtures.json
    of `date` and the day before (a game after midnight UTC is snapshotted
    into D+1's file but identified on D's coupon). SETTLE takes it as the
    record's pinned id (B3): /event/{id} is asked directly, a search landing
    elsewhere is ID_CHANGED - the coupon leg is graded off the match it was
    identified as before the start (F7: "to id przypina SETTLE")."""
    from datetime import timedelta

    day = datetime.strptime(date, "%Y-%m-%d")
    out: dict[str, dict[str, Any]] = {}
    for d in ((day - timedelta(days=1)).strftime("%Y-%m-%d"), date):
        path = Path(runs_dir) / d / SPORT_FIXTURES_FILE
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for f in doc.get("fixtures") or []:
            if f.get("sport") != sport or f.get("status") != "IDENTIFIED":
                continue
            if f.get("sofascore_event_id") is None:
                continue
            out[str(f["superbet_event_id"])] = {
                "sofascore_event_id": int(f["sofascore_event_id"]),
                "home_is_team1": f.get("home_is_team1"),
                "sofascore_home_id": f.get("home_id"),
                "sofascore_away_id": f.get("away_id"),
                "match_method": f"SPORT_IDENTITY:{f.get('match_method')}",
                "matched_at_utc": f.get("matched_at_utc"),
            }
    return out


def seeded(prev: dict[str, Any] | None, seed: dict[str, Any] | None
           ) -> dict[str, Any] | None:
    """The earlier record, or SPORT_IDENTITY's pin where it has no id."""
    if seed is None or (prev and prev.get("sofascore_event_id") is not None):
        return prev
    # A seed alone is a record not yet graded (the loops read prev["state"]).
    return {"state": "PENDING", **(prev or {}), **seed}


def grade(
    runs_dir: str,
    date: str,
    legs: list[dict[str, Any]],
    at: datetime,
    load: Callable[[str, Any, set[str]], dict[str, dict[str, Any] | None]]
    | None = None,
) -> list[dict[str, Any]]:
    """Every measured-sport leg graded at its printed price (grade_legs),
    per sport, from the settled.json its event settles into. A settled
    record whose Sofascore id is not the one pinned before the match
    (sport_fixtures.json) is NOT_GRADED:ID_CHANGED - never graded off
    another match."""
    load = load or (lambda rd, sport, dates: sd.settled_for(rd, sport, dates))
    pinned = pinned_ids(Path(runs_dir) / date)
    out: list[dict[str, Any]] = []
    for sport in MEASURED_SPORTS:
        mine = [leg for leg in legs if leg.get("sport") == sport]
        if not mine:
            continue
        sources = {str(leg.get("source_date") or date) for leg in mine}
        settled = load(runs_dir, sport, sources | {date})
        graded = sd.grade_legs({"sport": sport, "date": date, "legs": mine},
                                 settled, at=at)
        for g in graded:
            src = str(g.get("source_date") or date)
            ev = ((settled.get(src) or {}).get("events") or {}).get(
                str(g["superbet_event_id"])) or {}
            want = pinned.get(str(g["superbet_event_id"]), g.get("sofascore_event_id"))
            got = ev.get("sofascore_event_id")
            if got is not None and want is not None and int(got) != int(want):
                g = {**g, "outcome": "NOT_GRADED:ID_CHANGED"}
            out.append(g)
    return out
