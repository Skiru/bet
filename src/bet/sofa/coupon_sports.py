"""The measured sports' legs on the one coupon (plan 2026-10-05, part 5, F7).

run_sport_confidence.py writes runs/sofa/<d>/08_confidence_sports.json -
hockey, basketball, volleyball and CS2 legs with a confidence from the
statistics (score_model / cs2_engine, calibrated without prices) and the
coupon's price filters. build_coupon.py puts them on 11_coupon.json beside
football and tennis. This module is what that needs:

* `normalize` - the reader-facing names every 11 reader expects
  (`market` = family, `direction` = side, `offered_odds`, `leg_ev`), the
  native fields kept, so sport_coupon.grade_coupon grades the leg unchanged;
* `apply_reads` - vetoes / reads (reads.json, LegRead with `period`): NO_BET
  and WATCH remove, into removed_by_reads, like a football leg;
* `locked_sport_legs` - legs the last printed coupon carried whose match has
  started: kept as printed (locked_print's rule, for sport legs);
* `grade` - each leg graded at its printed price by sport_coupon.grade_coupon
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

from bet.sofa import sport_coupon as sc
from bet.sofa.confidence import SHEET_SPORTS, too_close_to_kickoff
from bet.sofa.contracts import LegRead, Veto
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
    return out


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
        refusal = read_refusal(covering, honours_watch=True)
        if refusal is not None:
            verdict = "NO_BET" if refusal == "READ_NO_BET" else "WATCH"
            removed.append({**leg, "refusal": refusal, "reason": "+".join(
                sorted({r.author for r in covering if r.verdict == verdict}))})
            continue
        kept.append(leg)
    return kept, removed, vetoed


def locked_sport_legs(
    printed: Mapping[str, Any] | None, now: datetime
) -> list[dict[str, Any]]:
    """The measured-sport singles of the last printed coupon whose match has
    started (or is inside the kickoff margin) at `now`: kept as printed."""
    if not printed:
        return []
    created = str(printed.get("pdf_rendered_at_utc")
                  or printed.get("created_at_utc") or "")
    if not created or _utc(created) > now:
        return []
    dials = {k: printed.get(k) for k in ("confidence_floor", "min_ev", "max_overround")}
    if printed.get("epoch"):
        dials["epoch"] = printed["epoch"]
    out = []
    for leg in printed.get("singles") or []:
        if not is_measured(leg):
            continue
        if not too_close_to_kickoff([_utc(str(leg["kickoff_utc"]))], now):
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


def grade(
    runs_dir: str,
    date: str,
    legs: list[dict[str, Any]],
    at: datetime,
    load: Callable[[str, Any, set[str]], dict[str, dict[str, Any] | None]]
    | None = None,
) -> list[dict[str, Any]]:
    """Every measured-sport leg graded at its printed price (grade_coupon),
    per sport, from the settled.json its event settles into. A settled
    record whose Sofascore id is not the one pinned before the match
    (sport_fixtures.json) is NOT_GRADED:ID_CHANGED - never graded off
    another match."""
    load = load or (lambda rd, sport, dates: sc.settled_for(rd, sport, dates))
    pinned = pinned_ids(Path(runs_dir) / date)
    out: list[dict[str, Any]] = []
    for sport in MEASURED_SPORTS:
        mine = [leg for leg in legs if leg.get("sport") == sport]
        if not mine:
            continue
        sources = {str(leg.get("source_date") or date) for leg in mine}
        settled = load(runs_dir, sport, sources | {date})
        graded = sc.grade_coupon({"sport": sport, "date": date, "legs": mine},
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
