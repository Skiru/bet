#!/usr/bin/env python3
"""Verify the coupon of one day against its own sources.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date 2026-09-30

audit_coupon.py checks the coupon's structure; this re-derives it from the
files on disk, not from the artifact's own fields:

  C1  the coupon artifact (11_coupon.json; 08_confidence.json on a day
      before the stats-only epoch) is not older than its sources, and its
      PDF is not older than it
  C2  every printed single obeys the dials the artifact was built with:
      confidence >= floor, confidence x odds >= min_ev (> 1 on an artifact
      without one), margin <= max_overround, not started at build;
      a locked single (bet.sofa.locked_print, since 2026-10-05: printed by an
      earlier build, its match started before this one) is checked against
      the build that printed it - its printed_at_utc and printed_under dials;
      a printed leg whose match started is on the coupon (locked) or in its
      printed_after_start - football / tennis and, since 2026-10-05, the
      measured sports' legs (audit_sport_print_record)
  U1  (11_coupon.json, stats-only days) the fresh singles stand in
      confidence.coupon_order, numbered 1..N, the locked ones first and
      unnumbered; U2 every fresh football / tennis single carries the
      stats-only epoch.
  U3  every fresh measured-sport leg re-derived from the raw Superbet
      snapshot: price, group margin, x, price age, calibration bucket.
  C3  (days from READS_CUTOVER on) every leg the PDF must have read
      (confidence.legs_requiring_read) was read by an analyst (reads.json,
      contracts.LegRead), and none it prints carries a WATCH or NO_BET read
      (2026-10-04, Farense - Chaves: a WATCH had no field and the leg was
      printed); a locked leg is read as of its print - a
      refusing read now covering it is a note (it came after the start, or
      the earlier build would have refused it), never a defect

No network. Exit 0 when nothing is found, 1 with findings, 2 on a bad file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import fixture_status as fs  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    COUPON_ARTIFACT,
    COUPON_PROFILE,
    MAX_OVERROUND,
    SHEET_SPORTS,
    coupon_artifact,
    coupon_order,
    legs_requiring_read,
    printed_builders,
    printed_singles,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.epochs import STATS_ONLY  # noqa: E402
from bet.sofa.locked_print import (  # noqa: E402
    PRINTED_HISTORY_DIR,
    PRINTED_MANIFEST,
    StartedBy,
    first_prints,
    history_keys,
    leg_key,
    leg_started_by,
    print_history,
    started_by_evidence,
)
from bet.sofa.veto import (  # noqa: E402
    load_reads,
    matching_reads,
    read_refusal,
)

TOL = 1e-4
# The first day whose flow writes reads.json (C3).
READS_CUTOVER = "2026-10-05"


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


notes: list[str] = []


def _superbet_started(run: Path) -> dict[int, str]:
    """{event id: superbet_started_utc} from the day's 04_offer.json."""
    path = run / "04_offer.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    offers = raw if isinstance(raw, list) else raw.get("fixtures") or []
    return {
        int(o["sofascore_event_id"]): str(o["superbet_started_utc"])
        for o in offers if o.get("superbet_started_utc")
    }


def audit_confidence(runs_dir: str, date: str) -> list[str]:
    """C1/C2 for the coupon. The dials are the artifact's own
    (confidence_floor, min_ev, max_overround): a day is checked against the
    rule it was printed under, not today's."""
    run = Path(runs_dir) / date
    # The coupon artifact (11_coupon.json on a stats-only day, K3).
    path = coupon_artifact(run)
    name = path.name
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    tag = "official"
    out: list[str] = []
    if doc.get("profile", "standard") != "standard":
        out.append(f"C1 {tag}: {name} was built with profile {doc.get('profile')!r}")
    sources = (
        ("08_confidence.json", "08_confidence_sports.json", "read_requests.json")
        if name == COUPON_ARTIFACT
        else ("05_sheet.json", "vetoes.json", "reads.json")
    )
    for newer in sources:
        other = run / newer
        if other.exists() and other.stat().st_mtime > path.stat().st_mtime:
            out.append(f"C1 {tag}: {name} is older than {newer} (STALE_CONFIDENCE)")
    if name == COUPON_ARTIFACT:
        out += audit_coupon_order(doc, tag)
        out += audit_sport_legs(runs_dir, date, doc, tag)
    pdf = run / f"KUPON_{date}.pdf"
    if not pdf.exists():
        out.append(f"C1 {tag}: {pdf.name} missing - the artifact was never printed")
    elif path.stat().st_mtime > pdf.stat().st_mtime:
        out.append(
            f"C1 {tag}: {pdf.name} is older than {name} - it prints another build"
        )
    doc_floor = float(doc.get("confidence_floor", COUPON_PROFILE.floor))
    # An artifact without the dials predates them and was printed under
    # x > 1.0 and MAX_OVERROUND (the rule until 2026-10-04).
    doc_min_ev = doc.get("min_ev")
    doc_max_ov = float(doc.get("max_overround", MAX_OVERROUND))
    doc_built = (
        _utc(str(doc["created_at_utc"])) if doc.get("created_at_utc") else None
    )
    # A locked single is judged on when its match REALLY started (the lock's
    # rule, locked_print.started_by_evidence), not on its printed clock: 10-05,
    # Grenier was printed 09:00Z, began 09:40Z, after the 09:19Z print.
    started_by = started_by_evidence(_superbet_started(run), fs.load(run))
    for single in printed_singles(doc):
        conf, odds = float(single["confidence"]), float(single["offered_odds"])
        label = f"{tag} {single['match']} {single['market']} {single['line']}"
        floor, min_ev, max_ov, built = doc_floor, doc_min_ev, doc_max_ov, doc_built
        if single.get("locked"):
            # Valid in the build it came from, not in this one: its clock and
            # its dials are the earlier build's (bet.sofa.locked_print).
            printed_at = single.get("printed_at_utc")
            under = single.get("printed_under")
            if not printed_at or not isinstance(under, dict):
                out.append(f"C2 {label}: locked without printed_at_utc / printed_under")
                continue
            floor = float(under.get("confidence_floor", doc_floor))
            min_ev = under.get("min_ev")
            max_ov = float(under.get("max_overround", doc_max_ov))
            built = _utc(str(printed_at))
        if conf < floor - TOL:
            out.append(f"C2 {label}: confidence {conf} below floor {floor}")
        if min_ev is None:
            if not conf * odds > 1.0:
                out.append(f"C2 {label}: confidence x odds {conf * odds:.4f} <= 1")
        elif round(conf * odds, 9) < float(min_ev):
            out.append(f"C2 {label}: confidence x odds {conf * odds:.4f} < {min_ev}")
        ov = single.get("overround")
        if ov is None or float(ov) > max_ov + TOL:
            out.append(f"C2 {label}: margin {ov} above {max_ov}")
        if built is not None and (
            started_by(int(single["sofascore_event_id"]),
                       str(single["kickoff_utc"]), built)
            if single.get("locked")
            else _utc(str(single["kickoff_utc"])) <= built
        ):
            out.append(f"C2 {label}: printed after its kickoff")
    if name == COUPON_ARTIFACT:
        out += audit_print_record(run, doc, tag, started_by)
    if date >= READS_CUTOVER:
        out += audit_reads(run, doc, tag)
    return out


def audit_print_record(
    run: Path, doc: dict[str, Any], tag: str, started_by: StartedBy
) -> list[str]:
    """C2 against the print history (F0.1, printed/; 12_printed.json alone on
    a day before it). 10-05: twelve tennis legs printed at 09:19Z left the
    record when a later render overwrote 12_printed.json, and nothing could
    tell. Football / tennis:

    * every printed leg whose match had REALLY started by CONFIDENCE's build
      (started_by_evidence) is on the coupon - locked - or listed in its
      printed_after_start: none vanishes;
    * with a history directory, every locked leg and every
      printed_after_start entry is on some printed render: nothing is
      locked or excused without a print record."""
    history = print_history(run)
    if not history:
        return []
    out: list[str] = []
    built_raw = (doc.get("built_from") or {}).get("08_confidence.json") or doc.get(
        "created_at_utc")
    if not built_raw:
        return out
    built = _utc(str(built_raw))
    on_coupon = {leg_key(s) for s in printed_singles(doc)
                 if str(s.get("sport") or "football") in SHEET_SPORTS}
    for b in printed_builders(doc):
        on_coupon |= {leg_key(x, b["sofascore_event_id"]) for x in b.get("legs") or []}
    late = doc.get("printed_after_start") or []
    late_keys = {tuple(x["key"]) for x in late if x.get("key") is not None}
    late_fixtures = {int(x["sofascore_event_id"]) for x in late
                     if x.get("kind") == "builder"}
    record = first_prints(history, built, leg_started_by(started_by)) or {}
    for s in printed_singles(record):
        if str(s.get("sport") or "football") not in SHEET_SPORTS:
            continue
        k = leg_key(s)
        if k in on_coupon or k in late_keys:
            continue
        if started_by(int(s["sofascore_event_id"]), s.get("kickoff_utc"), built):
            out.append(f"C2 {tag} {s.get('match')} {s['market']} {s.get('line')} "
                       f"{s['direction']}: printed {s.get('printed_at_utc')} "
                       f"({s.get('printed_in') or PRINTED_MANIFEST}), its match "
                       "started, gone from the coupon - neither locked nor "
                       "printed_after_start")
    for b in printed_builders(record):
        eid = int(b["sofascore_event_id"])
        keys = {leg_key(x, eid) for x in b.get("legs") or []}
        if keys <= on_coupon or eid in late_fixtures:
            continue
        if started_by(eid, b.get("kickoff_utc"), built):
            out.append(f"C2 {tag} builder {b.get('match')}: printed "
                       f"{b.get('printed_at_utc')}, its match started, gone from "
                       "the coupon")
    out += audit_sport_print_record(run, doc, tag, history, late_keys)
    if not (run / PRINTED_HISTORY_DIR).is_dir():
        return out
    on_record = history_keys(history)
    for s in printed_singles(doc):
        if not s.get("locked"):
            continue
        if str(s.get("sport") or "football") in SHEET_SPORTS:
            key: tuple[Any, ...] = tuple(leg_key(s))
        else:
            from bet.sofa.coupon_sports import sport_key

            key = tuple(sport_key(s))
        if key not in on_record:
            out.append(f"C2 {tag} {s.get('match')} {s['market']} {s.get('line')}: "
                       "locked but on no printed render")
    for x in late:
        if x.get("key") is not None and tuple(x["key"]) not in on_record:
            out.append(f"C2 {tag} {x.get('match')} {x['key']}: printed_after_start "
                       "without a print record")
    return out


def audit_sport_print_record(
    run: Path, doc: dict[str, Any], tag: str, history: list[dict[str, Any]],
    late_keys: set[tuple[Any, ...]],
) -> list[str]:
    """C2's "none vanishes" for the measured sports (hockey, basketball,
    volleyball, CS2), on COUPON_ASSEMBLY's own rule (build_coupon.
    prepare_sports): the print record as first_prints builds it on the
    sports' current clocks (coupon_sports.fresh_kickoffs / started_by_clock),
    at 11_coupon.json's build. Every printed sport leg whose game had started
    by then is on the coupon - locked - or in printed_after_start. Until
    2026-10-05 C2 checked football / tennis only."""
    from bet.sofa import coupon_sports as cs

    created = doc.get("created_at_utc")
    if not created:
        return []
    built = _utc(str(created))
    clock = cs.started_by_clock(cs.fresh_kickoffs(run.parent, run.name, built))
    record = first_prints(history, built, clock) or {}
    on_coupon = {tuple(cs.sport_key(s)) for s in printed_singles(doc)
                 if cs.is_measured(s)}
    out: list[str] = []
    for s in printed_singles(record):
        if not cs.is_measured(s):
            continue
        key = tuple(cs.sport_key(s))
        if key in on_coupon or key in late_keys:
            continue
        if clock(s, built):
            out.append(f"C2 {tag} {s.get('sport')} {s.get('match')} "
                       f"{s.get('family') or s.get('market')} p{s.get('period') or 0} "
                       f"{s.get('line')} {s.get('side') or s.get('direction')}: "
                       f"printed {s.get('printed_at_utc')} "
                       f"({s.get('printed_in') or PRINTED_MANIFEST}), its game "
                       "started, gone from the coupon - neither locked nor "
                       "printed_after_start")
    return out


def audit_coupon_order(doc: dict[str, Any], tag: str) -> list[str]:
    """U1 (K7): the fresh singles of 11_coupon.json stand in coupon_order,
    numbered 1..N, the locked ones first and unnumbered; U2: every fresh
    single was selected in the stats-only epoch."""
    out: list[str] = []
    singles = printed_singles(doc)
    fresh = [s for s in singles if not s.get("locked")]
    if any(s.get("locked") for s in singles[len(singles) - len(fresh):]):
        out.append(f"U1 {tag}: a locked single stands after a fresh one")
    want = [x for b in coupon_order([dict(s) for s in fresh]) for x in b.legs]
    if [_read_key(x) for x in want] != [_read_key(x) for x in fresh]:
        out.append(f"U1 {tag}: the singles are not in coupon_order")
    if [s.get("position") for s in fresh] != list(range(1, len(fresh) + 1)):
        out.append(f"U1 {tag}: positions are not 1..{len(fresh)} in order")
    if any(s.get("position") is not None for s in singles if s.get("locked")):
        out.append(f"U1 {tag}: a locked single carries a position")
    for s in fresh:
        if s.get("epoch") != STATS_ONLY and str(s.get("sport") or "football") in (
                "football", "tennis"):
            out.append(f"U2 {tag} {s.get('match', '')} {s['market']} {s['line']}: "
                       f"fresh leg without the stats-only epoch")
    return out


def audit_reads(run: Path, doc: dict[str, Any], tag: str) -> list[str]:
    """C3: the printed official legs `legs_requiring_read` names (the best 30
    singles and every builder leg) were read, and no leg it prints is WATCH
    or NO_BET."""
    path = run / "reads.json"
    printed = [
        *printed_singles(doc),
        *(
            {**leg, "sofascore_event_id": b["sofascore_event_id"],
             "match": b.get("match", ""), "locked": bool(b.get("locked"))}
            for b in printed_builders(doc)
            for leg in b.get("legs") or []
        ),
    ]
    if not printed:
        return []
    required = {_read_key(x) for x in legs_requiring_read(doc)}
    if not path.exists():
        return [f"C3 {tag}: reads.json missing - none of {len(required)} legs "
                "that need a read has one"]
    reads = load_reads(path)
    out: list[str] = []
    for leg in printed:
        covering = matching_reads(
            reads,
            sofascore_event_id=int(leg["sofascore_event_id"]),
            market=str(leg["market"]),
            subject=str(leg.get("subject") or ""),
            # None on a winner / 1X2 sport leg; a sport read names its period
            line=float(leg["line"]) if leg.get("line") is not None else None,
            direction=str(leg["direction"]),
            period=int(leg["period"]) if leg.get("period") is not None else None,
        )
        label = f"{tag} {leg.get('match', '')} {leg['market']} {leg['line']}"
        # A locked single carries the reads it was printed with.
        carried = [r for r in leg.get("reads") or [] if isinstance(r, dict)]
        if (
            _read_key(leg) in required
            and not any(r.author == "analyst" for r in covering)
            and not any(r.get("author") == "analyst" for r in carried)
        ):
            out.append(f"C3 {label}: printed without an analyst's read")
        refused = read_refusal(covering)
        if refused is not None and leg.get("locked"):
            # Printed before its match started; a read refusing it now did
            # not remove it (bet.sofa.locked_print). Shown, not a defect.
            notes.append(
                f"C3 {label}: locked (printed before the start), now covered "
                f"by {refused}"
            )
        elif refused is not None:
            out.append(f"C3 {label}: printed despite {refused}")
    return out


def _read_key(leg: dict[str, Any]) -> tuple[Any, ...]:
    line = leg.get("line")
    return (
        int(leg["sofascore_event_id"]), str(leg["market"]),
        str(leg.get("subject") or ""),
        float(line) if line is not None else None, str(leg["direction"]),
        int(leg.get("period") or 0),
    )


def audit_sport_legs(runs_dir: str, date: str, doc: dict[str, Any],
                     tag: str) -> list[str]:
    """U3 (F7): every fresh measured-sport leg of 11_coupon.json re-derived
    from the raw Superbet snapshot as it stood when 08_confidence_sports.json
    was built: the price, the group's margin, x, the price's age and the
    calibration bucket of its forecast_p."""
    from bet.sofa import coupon_sports as cs
    from bet.sofa import cs2
    from bet.sofa import sport_confidence as scf
    from bet.sofa import sport_day as spc
    from bet.sofa import sport_identity as si
    from bet.sofa.config import config_path
    from scripts.sofa import run_sport_confidence as rsc

    legs = [s for s in printed_singles(doc)
            if cs.is_measured(s) and not s.get("locked")]
    if not legs:
        return []
    built = (doc.get("built_from") or {}).get("08_confidence_sports.json")
    if not built:
        return [f"U3 {tag}: sport legs printed without 08_confidence_sports.json"]
    at = _utc(str(built))
    cal = scf.SportCalibration.load(config_path(scf.CALIBRATION_FILE))
    out: list[str] = []
    events: dict[str, dict[str, Any]] = {}
    for leg in legs:
        sport = str(leg["sport"])
        label = (f"{tag} {leg.get('match', '')} {leg['family']} p{leg.get('period')} "
                 f"{leg.get('line')} {leg['side']}")
        if sport not in events:
            events[sport] = si.snapshot_events(runs_dir, sport, date, at)
        ev = events[sport].get(str(leg["superbet_event_id"]))
        if ev is None:
            out.append(f"U3 {label}: no snapshot of the event")
            continue
        match = [
            (k, ln) for k, ln in ev.sides.items()
            if ln.side == leg["side"] and ln.line == leg.get("line")
            and str(ln.subject or "") == str(leg.get("subject") or "")
            and int(ln.map_nr if sport == "cs2" else ln.period) == int(
                leg.get("period") or 0)
            and rsc._allowed(sport, ln) == leg["family"]
        ]
        if not match:
            out.append(f"U3 {label}: the line is not in the snapshot")
            continue
        key, ln = match[0]
        if abs(float(ln.odds) - float(leg["odds"])) > 1e-9:
            out.append(f"U3 {label}: odds {leg['odds']} vs snapshot {ln.odds}")
        fetched = ev.fetched_at.get(key)
        if fetched != leg.get("price_fetched_at_utc"):
            out.append(f"U3 {label}: price time {leg.get('price_fetched_at_utc')} "
                       f"vs snapshot {fetched}")
        elif at - _utc(str(fetched)) > spc.MAX_PRICE_AGE:
            out.append(f"U3 {label}: price older than {spc.MAX_PRICE_AGE}")
        group = {x.side: x.odds for k2, x in ev.sides.items()
                 if rsc._group_key(sport, k2) == rsc._group_key(sport, key)
                 and ev.fetched_at.get(k2) == fetched}
        margin = cs2.group_overround(group)
        if leg.get("overround") is None or abs(round(margin, 4) - float(
                leg["overround"])) > 1e-4:
            out.append(f"U3 {label}: margin {leg.get('overround')} vs {margin:.4f}")
        if margin > MAX_SPORT_OVERROUND + TOL:
            out.append(f"U3 {label}: margin {margin:.4f} above {MAX_SPORT_OVERROUND}")
        if round(float(leg["confidence"]) * float(leg["odds"]), 9) < 0.90:
            out.append(f"U3 {label}: x below 0.90")
        if not scf.line_in_fit(sport, str(leg["family"]), leg.get("line")):
            out.append(f"U3 {label}: line {leg.get('line')} outside the curve's fit")
        conf = cal.lookup(sport, str(leg["family"]), str(leg["side"]),
                          float(leg["forecast_p"])) if cal else None
        if conf is None or abs(conf.value - float(leg["confidence"])) > 1e-4:
            out.append(f"U3 {label}: confidence {leg['confidence']} is not the "
                       f"calibration's {None if conf is None else conf.value}")
    return out


MAX_SPORT_OVERROUND = 0.15


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    findings: list[str] = []
    checked: list[str] = []
    notes.clear()
    try:
        if coupon_artifact(Path(runs_dir) / args.date).exists():
            checked.append("official")
        findings += audit_confidence(runs_dir, args.date)
    except (OSError, ValueError, KeyError) as exc:
        print(f"AUDIT_VARIANTS: bad file: {type(exc).__name__}: {exc}")
        return 2
    print(
        f"# audit_variants {args.date} - checked: {', '.join(checked) or 'nothing'}\n"
    )
    for f in findings:
        print(f"- {f}")
    if notes:
        print("\nnotes (not defects):")
        for n in notes:
            print(f"- {n}")
    if not findings:
        print("no findings" + ("" if checked else " (nothing to check - not a pass)"))
    print(
        "\nSOFA_SUMMARY: "
        + json.dumps(
            {
                "stage": "AUDIT_VARIANTS",
                "verdict": "OK" if not findings else "PARTIAL",
                "metrics": {"checked": checked, "findings": len(findings)},
            }
        )
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
