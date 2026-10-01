#!/usr/bin/env python3
"""Verify every variant of one day against its own sources.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date 2026-09-30

audit_coupon.py covers the official coupon. This covers what sits beside it:
the four sport coupons and WARIANT WSZYSTKIE. Every check re-derives from the
files on disk, not from the artifact's own fields:

  S1  the sport coupon's JSON names its PDF (sha256)
  S2  every new (unlocked) leg obeys the rule it was printed under: fair_p,
      odds, margin, no player line, kickoff inside the window, price age
  S3  every leg's price and devig recomputed from the raw snapshot record it
      names (price_fetched_at_utc): odds, the whole group, fair_p, margin
  S4  one leg per event, no more than max_legs, no vetoed leg printed
  S5  the selection replayed from the snapshots as they stood at build time
      gives the same legs (locked legs taken as printed)
  M1  WARIANT WSZYSTKIE names its PDF (sha256)
  M2  each section equals its source as the source stands now: the official
      printed singles / builders, each sport's legs - a source rebuilt after
      the assembly makes the variant stale
  M3  nothing of either was written into runs/sofa/<d>/
  C1  the official coupon and WARIANT (08_confidence[_wariant].json): the
      artifact is of its profile, not older than 05_sheet.json / vetoes.json,
      and its PDF is not older than it
  C2  every printed single obeys the dials the artifact was built with:
      confidence >= floor, the price rule (official: confidence x odds > 1;
      WARIANT: >= min_ev), margin <= max_overround, not started at build

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

from bet.sofa import cs2, shadow  # noqa: E402
from bet.sofa import multi_coupon as mc  # noqa: E402
from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    PROFILES,
    confidence_artifact,
    printed_builders,
    printed_singles,
)
from bet.sofa.config import SofaConfig  # noqa: E402

TOL = 1e-4
# From this build time on, a sport coupon must name its PDF by sha256 and
# record what it read (snapshot_lines, vetoes_applied); earlier ones were
# written before those fields existed and are checked the lenient way.
HASH_CUTOVER = "2026-09-30T07:30:00Z"
# From this build time on, the replay fields must be there too.
REPLAY_CUTOVER = "2026-09-30T12:00:00Z"


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def leg_id(leg: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(leg.get(k) for k in sc.LEG_KEY)


def _shape(sport: sc.SportKey, leg: dict[str, Any]) -> cs2.Shape:
    if sport == "cs2":
        return cs2.group_shape(str(leg["family"]))
    return shadow.group_shape(sport, int(leg["market_id"]))


def _record_group(
    snaps: list[dict[str, Any]], leg: dict[str, Any]
) -> dict[str, float] | None:
    """The leg's whole outcome group in the snapshot record it names."""
    key = [
        k
        for k in ("market_id", "family", "period", "map_nr", "subject", "line")
        if k in leg
    ]
    for rec in snaps:
        if (
            rec["superbet_event_id"] != leg["superbet_event_id"]
            or rec["fetched_at_utc"] != leg["price_fetched_at_utc"]
        ):
            continue
        group = {
            ln["side"]: float(ln["odds"])
            for ln in rec["lines"]
            if all(ln.get(k) == leg.get(k) for k in key)
        }
        if group:
            return group
    return None


# The build log started on 2026-09-30; only a leg locked in a first record of
# that day can come from a build the log never saw.
BUILD_LOG_STARTED = "2026-09-30"


def locked_leg_problem(d: Path, doc: dict[str, Any], leg: dict[str, Any]) -> str | None:
    """Why a locked leg is not provably the leg an earlier build printed.

    It must appear, identical, in a logged build that ran at least
    KICKOFF_MARGIN before its kickoff. Without any logged build before this
    one (the log started 2026-09-30) it cannot be checked - a note, not a
    defect."""
    log = d / sc.BUILDS_FILE
    earlier = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if str(rec.get("created_at_utc")) < str(doc["created_at_utc"]):
                earlier.append(rec)
    if not earlier:
        return "UNVERIFIABLE: locked, and no earlier build is logged"
    fields = (*sc.LEG_KEY, "odds", "fair_p", "price_fetched_at_utc")
    want = tuple(leg.get(k) for k in fields)
    # The leg's first logged appearance already locked means the build that
    # created it predates the log: it cannot be checked either. 2026-09-30:
    # Paqt-Rune Eaters and CSB-FEU were locked in the first logged build
    # (06:58Z), created at ~06:14Z before the log existed (sofa-verifier).
    # Only the log's very first record can hold a leg locked by a build the
    # log never saw; a leg that first appears locked in any later record was
    # inherited from nowhere and stays a defect.
    first_rec = min(earlier, key=lambda r: str(r.get("created_at_utc")))
    if str(first_rec.get("created_at_utc"))[:10] <= BUILD_LOG_STARTED and any(
        tuple(old.get(k) for k in sc.LEG_KEY) == want[: len(sc.LEG_KEY)]
        and old.get("locked")
        for old in first_rec.get("legs", [])
    ):
        return "UNVERIFIABLE: locked already in the log's first build"
    for rec in earlier:
        for old in rec.get("legs", []):
            if tuple(old.get(k) for k in fields) == want and (
                _utc(leg["kickoff_utc"]) - _utc(str(rec["created_at_utc"]))
                >= sc.KICKOFF_MARGIN
            ):
                return None
    return "locked leg not printed, as it stands, by any earlier build before kickoff"


notes: list[str] = []


def audit_sport(
    runs_dir: str,
    sport: sc.SportKey,
    date: str,
    notes_out: list[str] | None = None,
) -> list[str]:
    """Findings for one sport coupon; notes (not defects) go to `notes_out`,
    or the module's `notes` for main."""
    notes_list = notes if notes_out is None else notes_out
    d = sc.day_dir(runs_dir, sport, date)
    path = d / sc.COUPON_FILE
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    why = sc.pdf_matches(doc, path, d / sc.pdf_name(sport, date))
    if why:
        out.append(f"S1 {sport}: {why}")
    modern = str(doc["created_at_utc"]) >= HASH_CUTOVER
    if modern and not doc.get("pdf_sha256"):
        out.append(f"S1 {sport}: no pdf_sha256 on a build after {HASH_CUTOVER}")
    if str(doc["created_at_utc"]) >= REPLAY_CUTOVER:
        for fld in ("snapshot_lines", "vetoes_applied"):
            if fld not in doc:
                out.append(f"S5 {sport}: no {fld} on a build after {REPLAY_CUTOVER}")
    rule_doc = doc["rule"]
    rule = sc.Rule(
        rule_doc["floor"],
        rule_doc["max_overround"],
        rule_doc["min_odds"],
        rule_doc["max_legs"],
    )
    at = _utc(doc["created_at_utc"])
    # Exactly what the build read: the first `snapshot_lines` of each file.
    # A snapshot loop that stamps a record before the build and writes it
    # after would otherwise read as a different selection.
    upto = doc.get("snapshot_lines") or {}
    for src, n in upto.items():
        _, lines_now, _ = sc.read_snapshots(
            sc.day_dir(runs_dir, sport, src) / cs2.SNAPSHOTS_FILE
        )
        if lines_now < n:
            out.append(
                f"S5 {sport}: {src} snapshots have {lines_now} lines, the build "
                f"read {n} - the file was truncated or restored"
            )
    snaps = {
        src: sc.load_snapshots(
            sc.day_dir(runs_dir, sport, src) / cs2.SNAPSHOTS_FILE,
            upto.get(src) if upto else None,
        )
        for src in (date, sc.next_date(date))
    }
    legs = doc["legs"]
    for leg in legs:
        name = (
            f"{sport} {leg['match_name']} {leg['family']} {leg['side']} "
            f"{leg.get('line')}"
        )
        if leg.get("locked"):
            why_locked = locked_leg_problem(d, doc, leg)
            if why_locked:
                (notes_list if why_locked.startswith("UNVERIFIABLE") else out).append(
                    f"S2 {name}: {why_locked}"
                )
            continue
        if leg["fair_p"] < rule.floor - TOL:
            out.append(f"S2 {name}: fair_p {leg['fair_p']} below floor")
        if leg["odds"] < round(rule.min_odds, 4) - TOL:
            out.append(f"S2 {name}: odds {leg['odds']} below min")
        if leg["overround"] > rule.max_overround + TOL:
            out.append(f"S2 {name}: margin {leg['overround']} above max")
        if sc.is_player_family(str(leg["family"])):
            out.append(f"S2 {name}: a player line")
        kickoff = _utc(leg["kickoff_utc"])
        if kickoff - at < sc.KICKOFF_MARGIN or kickoff >= sc.day_end(date):
            out.append(f"S2 {name}: kickoff outside the window at build")
        if at - _utc(leg["price_fetched_at_utc"]) > sc.MAX_PRICE_AGE:
            out.append(f"S2 {name}: price older than {sc.MAX_PRICE_AGE}")
        src = leg.get("source_date") or date
        group = _record_group(snaps.get(src, []), leg)
        if group is None:
            out.append(
                f"S3 {name}: no snapshot record at {leg['price_fetched_at_utc']}"
            )
            continue
        if group != {k: float(v) for k, v in leg["group_odds"].items()}:
            out.append(f"S3 {name}: group odds {leg['group_odds']} != snapshot {group}")
        if abs(group.get(leg["side"], -1) - leg["odds"]) > TOL:
            out.append(
                f"S3 {name}: odds {leg['odds']} != snapshot {group.get(leg['side'])}"
            )
        fair = cs2.group_fair(group, _shape(sport, leg))
        if fair is None:
            out.append(f"S3 {name}: the snapshot group is not a whole market")
        else:
            if abs(fair[leg["side"]] - leg["fair_p"]) > TOL:
                out.append(
                    f"S3 {name}: fair_p {leg['fair_p']} != {fair[leg['side']]:.4f}"
                )
            if abs(cs2.group_overround(group) - leg["overround"]) > TOL:
                out.append(
                    f"S3 {name}: margin {leg['overround']} recomputes differently"
                )
    events = [leg["superbet_event_id"] for leg in legs]
    if len(events) != len(set(events)):
        out.append(f"S4 {sport}: an event carries two legs")
    if len(legs) > rule.max_legs:
        out.append(f"S4 {sport}: {len(legs)} legs > max {rule.max_legs}")
    now_vetoes = sc.load_vetoes(d)
    vetoes = doc.get("vetoes_applied", now_vetoes)
    if "vetoes_applied" in doc and now_vetoes != vetoes:
        out.append(
            f"S4 {sport}: vetoes.json changed after the build - rebuild the coupon"
        )
    for leg in legs:
        if not leg.get("locked") and any(sc.veto_matches(v, leg) for v in vetoes):
            out.append(f"S4 {sport}: vetoed leg printed: {leg['match_name']}")
    # S5 - replay the selection from the snapshots as they stood at build time.
    events_then: dict[str, Any] = {}
    for src in (date, sc.next_date(date)):
        then = (
            snaps[src]
            if upto
            else [s for s in snaps[src] if _utc(s["fetched_at_utc"]) <= at]
        )
        for eid, ev in sc.latest_events(sport, then).items():
            ev.source_date = src
            have = events_then.get(eid)
            if have is None or max(ev.fetched_at.values(), key=_utc) > max(
                have.fetched_at.values(), key=_utc
            ):
                events_then[eid] = ev
    counts: dict[str, int] = {}
    since = sc.day_end(sc.prev_date(date)) if "window_start_utc" in doc else None
    cands = sc.candidates(
        sport, events_then, at, rule, counts, until=sc.day_end(date), since=since
    )
    locked = [leg for leg in legs if leg.get("locked")]
    replay, _ = sc.select(sport, cands, vetoes, rule, locked)
    if {leg_id(x) for x in replay} != {leg_id(x) for x in legs}:
        missing = {leg_id(x) for x in replay} - {leg_id(x) for x in legs}
        extra = {leg_id(x) for x in legs} - {leg_id(x) for x in replay}
        out.append(
            f"S5 {sport}: replayed selection differs: would print {sorted(missing)}, "
            f"printed {sorted(extra)}"
        )
    return out


def audit_confidence(runs_dir: str, date: str, profile_name: str) -> list[str]:
    """C1/C2 for one confidence profile. The dials are the artifact's own
    (confidence_floor, min_ev, max_overround): a day is checked against the
    rule it was printed under, not today's."""
    profile = PROFILES[profile_name]
    run = mc.official_dir(runs_dir, date)
    name = confidence_artifact(profile)
    path = run / name
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    tag = "official" if profile_name == "standard" else "wariant"
    out: list[str] = []
    if doc.get("profile", "standard") != profile_name:
        out.append(f"C1 {tag}: {name} was built with profile {doc.get('profile')!r}")
    for newer in ("05_sheet.json", "vetoes.json"):
        other = run / newer
        if other.exists() and other.stat().st_mtime > path.stat().st_mtime:
            out.append(f"C1 {tag}: {name} is older than {newer} (STALE_CONFIDENCE)")
    pdf = run / f"KUPON_{date}{profile.pdf_suffix}.pdf"
    if not pdf.exists():
        out.append(f"C1 {tag}: {pdf.name} missing - the artifact was never printed")
    elif path.stat().st_mtime > pdf.stat().st_mtime:
        out.append(
            f"C1 {tag}: {pdf.name} is older than {name} - it prints another build"
        )
    floor = float(doc.get("confidence_floor", profile.floor))
    min_ev = doc.get("min_ev", profile.min_ev)
    max_ov = float(doc.get("max_overround", profile.max_overround))
    built = _utc(str(doc["created_at_utc"])) if doc.get("created_at_utc") else None
    for single in printed_singles(doc):
        conf, odds = float(single["confidence"]), float(single["offered_odds"])
        label = f"{tag} {single['match']} {single['market']} {single['line']}"
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
        if built is not None and _utc(str(single["kickoff_utc"])) <= built:
            out.append(f"C2 {label}: printed after its kickoff")
    return out


def audit_multi(runs_dir: str, date: str) -> list[str]:
    out_dir = mc.multi_dir(runs_dir, date)
    path = out_dir / mc.MULTI_FILE
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    pdf = out_dir / mc.pdf_name(date)
    if not pdf.exists() or sc.file_sha256(pdf) != doc.get("pdf_sha256"):
        out.append("M1 multi: the PDF is not the one the JSON was printed as")
    for key, sec in doc["sections"].items():
        if sec["status"] != "OK":
            continue
        if key == "official":
            conf_path = mc.official_dir(runs_dir, date) / "08_confidence.json"
            conf = json.loads(conf_path.read_text(encoding="utf-8"))
            want = [
                (
                    s["sofascore_event_id"],
                    s["market"],
                    s.get("subject") or "",
                    s["line"],
                    s["direction"],
                    s["offered_odds"],
                )
                for s in printed_singles(conf)
            ]
            got = [
                (
                    p["source"]["sofascore_event_id"],
                    p["source"]["market"],
                    p["source"].get("subject") or "",
                    p["source"]["line"],
                    p["source"]["direction"],
                    p["odds"],
                )
                for p in sec["singles"]
            ]
            if want != got:
                out.append(
                    "M2 official: the section is not what KUPON prints now "
                    "(rebuild the variant)"
                )
            wb = [b["sofascore_event_id"] for b in printed_builders(conf)]
            if wb != [b["source"]["sofascore_event_id"] for b in sec["builders"]]:
                out.append("M2 official builders differ from KUPON's")
            continue
        sp: sc.SportKey = key
        spath = sc.day_dir(runs_dir, sp, date) / sc.COUPON_FILE
        if not spath.exists():
            out.append(f"M2 {key}: its source coupon is gone")
            continue
        sdoc = json.loads(spath.read_text(encoding="utf-8"))
        want_legs = [(leg_id(x), x["odds"], x["fair_p"]) for x in sdoc["legs"]]
        got_legs = [
            (leg_id(p["source"]), p["odds"], p["probability"]) for p in sec["singles"]
        ]
        if want_legs != got_legs:
            out.append(
                f"M2 {key}: the section is not what its coupon prints now "
                "(rebuild the variant)"
            )
    for name in (mc.MULTI_FILE, mc.pdf_name(date), sc.COUPON_FILE):
        if (mc.official_dir(runs_dir, date) / name).exists():
            out.append(f"M3 {name} found inside runs/sofa/{date}/")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    findings: list[str] = []
    checked: list[str] = []
    notes.clear()
    try:
        for sport in sc.SPORT_KEYS:
            if (sc.day_dir(runs_dir, sport, args.date) / sc.COUPON_FILE).exists():
                checked.append(sport)
            findings += audit_sport(runs_dir, sport, args.date)
        if (mc.multi_dir(runs_dir, args.date) / mc.MULTI_FILE).exists():
            checked.append("multi")
        findings += audit_multi(runs_dir, args.date)
        for prof, tag in (("standard", "official"), ("wariant", "wariant")):
            art = mc.official_dir(runs_dir, args.date) / confidence_artifact(
                PROFILES[prof]
            )
            if art.exists():
                checked.append(tag)
            findings += audit_confidence(runs_dir, args.date, prof)
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
