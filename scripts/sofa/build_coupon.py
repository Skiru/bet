#!/usr/bin/env python3
"""COUPON_ASSEMBLY - the one coupon of a stats-only day: runs/sofa/<d>/11_coupon.json.

Plan 2026-10-05 (docs/sofa/history/PLAN_2026-10-05_SETTLE_I_KUPON.md, K3/K4). From
the stats-only epoch (bet.sofa.epochs) the coupon is one artifact for every
sport, ordered by confidence and never by price:

* the singles of 08_confidence.json (football, tennis) and, where it exists,
  of 08_confidence_sports.json (hockey, basketball, volleyball, CS2), in
  `confidence.coupon_order` - one block per match at the place of its best
  leg, the legs of a match together - numbered 1..N;
* the legs already printed whose match has started (bet.sofa.locked_print)
  first, outside the numbering;
* the printed Bet Builders, numbered B1.., each named in its match's block;
* the legs a read removed (removed_by_reads, graded on their own - 7i);
* the operator's extra read requests (read_requests.json), so C3 and the
  analysts read the same set (confidence.legs_requiring_read).

It is a superset of the 08 format - `singles`, `builders`, `legs` and the
dials - so every reader of "what was printed" (confidence.printed_singles /
printed_builders, locked_print, the settlement, the ledger) reads it the way
it read 08. 08_confidence.json stays the football / tennis selection and the
input of SETTLE and the refit; it is not changed.

Reads only files on disk; costs no provider call.

Usage:
    python scripts/sofa/build_coupon.py --date 2026-10-05
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import coupon_sports as cs  # noqa: E402
from bet.sofa import timeutil  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    COUPON_ARTIFACT,
    coupon_order,
    group_key,
    is_stakeable,
    load_read_requests,
    request_covers,
)
from bet.sofa.epochs import STATS_ONLY, artifact_epoch  # noqa: E402
from bet.sofa.locked_print import PRINTED_MANIFEST  # noqa: E402
from bet.sofa.veto import load_reads, load_vetoes  # noqa: E402

SPORTS_ARTIFACT = "08_confidence_sports.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def makeup_of(samples: dict[int, dict[str, Any]], eid: int) -> dict[str, Any] | None:
    """The original fixture a make-up fixture replaces (bet.sofa.schedule),
    so an analyst reads it from the coupon instead of guessing (K14)."""
    sched = (samples.get(eid) or {}).get("schedule") or {}
    if sched.get("makeup_of") is None:
        return None
    return {
        "sofascore_event_id": int(sched["makeup_of"]),
        "postponed_utc": sched.get("makeup_postponed_utc"),
    }


def assemble(
    conf: dict[str, Any],
    sports: dict[str, Any] | None,
    requests: list[dict[str, Any]],
    samples: dict[int, dict[str, Any]],
    now_utc: str,
    date: str | None = None,
) -> dict[str, Any]:
    """11_coupon.json from its sources. Pure, so a test can pin it.

    `date`: the day window (K3) - a fresh leg prints on the coupon of D only
    when its start is in [D 00:00Z, D+1 00:00Z), whatever its sport; a
    locked leg stays where it was printed."""
    singles = list(conf.get("singles") or [])
    # A locked leg was numbered in the build that printed it; it prints
    # outside the numbering now, so its old position / block go.
    locked = [
        {k: v for k, v in s.items() if k not in ("position", "block")}
        for s in singles if s.get("locked")
    ]
    fresh = [s for s in singles if not s.get("locked")]
    legs = list(conf.get("legs") or [])
    if sports:
        for leg in sports.get("legs") or []:
            (locked if leg.get("locked") else fresh).append(leg)
            legs.append(leg)

    builders = [dict(b) for b in conf.get("builders") or []]
    if date is not None:
        # K3's day window for builders too (a locked one stays).
        lo_b, hi_b = f"{date}T00:00:00", f"{day_after(date)}T00:00:00"
        builders = [b for b in builders if b.get("locked")
                    or lo_b <= str(b.get("kickoff_utc") or "") < hi_b]
    printed_by_match: dict[str, list[str]] = {}
    n_builder = 0
    for b in builders:
        if is_stakeable(b):
            n_builder += 1
            b["builder_no"] = f"B{n_builder}"
            printed_by_match.setdefault(group_key(b), []).append(b["builder_no"])

    outside_window = 0
    if date is not None:
        lo, hi = f"{date}T00:00:00", f"{day_after(date)}T00:00:00"
        kept = [s for s in fresh if lo <= str(s.get("kickoff_utc") or "") < hi]
        outside_window = len(fresh) - len(kept)
        fresh = kept
    blocks_out: list[dict[str, Any]] = []
    ordered: list[dict[str, Any]] = []
    position = 0
    for i, block in enumerate(coupon_order(fresh), 1):
        positions = []
        for leg in block.legs:
            position += 1
            positions.append(position)
            out = {**leg, "position": position, "block": i,
                   "group_key": block.group_key}
            mk = makeup_of(samples, int(leg["sofascore_event_id"]))
            if mk is not None:
                out["makeup_of"] = mk
            ordered.append(out)
        blocks_out.append({
            "block": i,
            "group_key": block.group_key,
            "match": block.legs[0].get("match", ""),
            "sport": block.legs[0].get("sport"),
            "kickoff_utc": block.legs[0].get("kickoff_utc"),
            "positions": positions,
            "builders": printed_by_match.get(block.group_key, []),
        })
    locked_out = [{**s, "group_key": group_key(s)} for s in locked]

    out_singles = [*locked_out, *ordered]
    asked = [
        {**r, "covers": [s.get("position") for s in out_singles
                         if request_covers(r, s)]}
        for r in requests
    ]
    doc = {
        k: v for k, v in conf.items()
        if k not in ("singles", "legs", "builders", "removed_by_reads")
    }
    doc.update({
        "created_at_utc": now_utc,
        "coupon": COUPON_ARTIFACT,
        "epoch": STATS_ONLY,
        "built_from": {
            "08_confidence.json": conf.get("created_at_utc"),
            **({SPORTS_ARTIFACT: sports.get("created_at_utc")} if sports else {}),
        },
        # Every single prints (the operator, 2026-10-05).
        "pdf_max_singles": None,
        "prints_builders": True,
        "positions": position,
        "blocks": blocks_out,
        "locked_singles": len(locked_out),
        "singles": out_singles,
        "builders": builders,
        "legs": legs,
        "removed_by_reads": [
            *(conf.get("removed_by_reads") or []),
            *((sports or {}).get("removed_by_reads") or []),
        ],
        "read_requests": asked,
        "outside_day_window": outside_window,
        **({"sports": sports.get("sports")} if sports else {}),
    })
    return doc


def day_after(date: str) -> str:
    return (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()


def prepare_sports(
    run: Path, sports: dict[str, Any], at: datetime.datetime
) -> dict[str, Any]:
    """The measured sports' legs as 11 prints them (F7): normalized for the
    readers, vetoes and reads applied (a WATCH / NO_BET goes to
    removed_by_reads), and the sport legs of the last printed coupon whose
    match has started carried over, locked, as printed."""
    vetoes = load_vetoes(run / "vetoes.json")
    reads = load_reads(run / "reads.json")
    # Only a coupon a PDF was rendered from is "printed" (12_printed.json,
    # else an 11 whose PDF is at least as new) - a provisional 11 built
    # before the analysts' read never was (review 2026-10-05).
    printed: dict[str, Any] | None = None
    eleven, pdf = run / COUPON_ARTIFACT, run / f"KUPON_{run.name}.pdf"
    if (run / PRINTED_MANIFEST).exists():
        printed = _load(run / PRINTED_MANIFEST)
    elif (eleven.exists() and pdf.exists()
          and pdf.stat().st_mtime >= eleven.stat().st_mtime):
        printed = _load(eleven)
    fresh_clock = cs.fresh_kickoffs(run.parent, run.name, at)
    locked = cs.locked_sport_legs(printed, at, fresh_clock)
    locked_keys = {cs.sport_key(x) for x in locked}
    fresh = [cs.normalize(x) for x in sports.get("legs") or []
             if cs.sport_key(cs.normalize(x)) not in locked_keys]
    # A fresh leg whose match has started since SPORT_CONFIDENCE ran is not
    # a bet any more (the artifact is not re-timed by itself).
    started = [x for x in fresh if cs.started(x, at, fresh_clock)]
    fresh = [x for x in fresh if not cs.started(x, at, fresh_clock)]
    kept, removed, vetoed = cs.apply_reads(fresh, vetoes, reads)
    # A veto / read covering a locked leg does not remove it (its match is
    # under way): shown, never acted on - like locked_late_refusals.
    _, late, _ = cs.apply_reads(locked, vetoes, reads)
    return {**sports, "legs": [*locked, *kept], "removed_by_reads": removed,
            "vetoed": vetoed, "started_since_build": len(started),
            "locked_late_refusals": [
                {"key": list(cs.sport_key(x)), "refusal": x["refusal"]} for x in late]}


def render_md(doc: dict[str, Any], date: str) -> str:
    lines = [
        f"# Kupon {date} - 11_coupon.json",
        "",
        f"Zbudowany {doc['created_at_utc']}; epoka {doc['epoch']}; "
        f"{doc['positions']} pozycji, {doc['locked_singles']} w grze, "
        f"{sum(1 for b in doc['builders'] if b.get('builder_no'))} Bet Builderów, "
        f"{len(doc['removed_by_reads'])} zdjętych przez odczyt.",
        "",
        "| # | mecz | rynek | linia | pewność | model | kurs | x | start |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in doc["singles"]:
        pos = s.get("position") or "w grze"
        model = s.get("forecast_p")
        odds = s.get("offered_odds")
        x = round(float(s["confidence"]) * float(odds), 3) if odds else None
        subj = f" {s['subject']}" if s.get("subject") else ""
        lines.append(
            f"| {pos} | {s.get('match', '')} | {s.get('market')}{subj} | "
            f"{s.get('line')} {s.get('direction')} | {s['confidence']:.3f} | "
            f"{'—' if model is None else f'{model:.3f}'} | {odds} | {x} | "
            f"{str(s.get('kickoff_utc') or '')[11:16]}Z |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    ap.add_argument(
        "--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa")
    )
    args = ap.parse_args()
    run = Path(args.runs_dir) / args.date
    frozen = timeutil.frozen_clock_refusal(args.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    conf_path = run / "08_confidence.json"
    if not conf_path.exists():
        print(f"REFUSED: {conf_path} is missing - run run_confidence.py first",
              file=sys.stderr)
        return 2
    conf = _load(conf_path)
    if conf.get("profile", "standard") != "standard":
        print("REFUSED: 08_confidence.json is not the standard profile",
              file=sys.stderr)
        return 2
    # 11 replaces 08 as the coupon for every reader; a day before the
    # stats-only epoch keeps 08.
    if artifact_epoch(conf) != STATS_ONLY:
        print(
            "REFUSED: 08_confidence.json was not built under the stats-only "
            "rule (bet.sofa.epochs) - an older day's coupon is its 08",
            file=sys.stderr,
        )
        return 2
    # The same staleness guard the PDF has: a coupon assembled from a
    # CONFIDENCE older than its sheet, vetoes or reads prints stale legs.
    from scripts.sofa.build_coupon_pdf import confidence_older_than_sheet

    stale = confidence_older_than_sheet(run, "08_confidence.json")
    if stale:
        print(stale, file=sys.stderr)
        return 2
    sports_path = run / SPORTS_ARTIFACT
    sports = _load(sports_path) if sports_path.exists() else None
    at = timeutil.now()
    if sports is not None:
        sports = prepare_sports(run, sports, at)
    try:
        requests = load_read_requests(run / "read_requests.json")
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    samples_path = run / "03_samples.json"
    samples = (
        {int(s["sofascore_event_id"]): s for s in _load(samples_path)}
        if samples_path.exists() else {}
    )
    now = at.isoformat().replace("+00:00", "Z")
    doc = assemble(conf, sports, requests, samples, now, args.date)
    write_atomic(run / COUPON_ARTIFACT,
                 json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    write_atomic(run / COUPON_ARTIFACT.replace(".json", ".md"),
                 render_md(doc, args.date))
    unmatched = [r for r in doc["read_requests"] if not r["covers"]]
    for r in unmatched:
        print(f"UNMATCHED_READ_REQUEST: {json.dumps(r)}", file=sys.stderr)
    print(json.dumps({
        "stage": "COUPON_ASSEMBLY",
        "verdict": "OK" if sports_path.exists() else "PARTIAL",
        "metrics": {
            "positions": doc["positions"], "blocks": len(doc["blocks"]),
            "locked_singles": doc["locked_singles"],
            "builders": sum(1 for b in doc["builders"] if b.get("builder_no")),
            "removed_by_reads": len(doc["removed_by_reads"]),
            "read_requests": len(doc["read_requests"]),
            "read_requests_unmatched": len(unmatched),
            "outside_day_window": doc["outside_day_window"],
            "sports_artifact": sports_path.exists(),
        },
        "output_path": str(run / COUPON_ARTIFACT),
    }))
    return 0 if sports_path.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
